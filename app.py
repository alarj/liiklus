from __future__ import annotations

import ast
import base64
import csv
import hashlib
import io
import json
import os
import re
import secrets
import struct
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Literal

import cv2
import httpx
import numpy as np
import onnxruntime as ort
from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

from database import ConflictError, NotFoundError, OracleRepository, User


def _model_confidence_from_environment() -> float:
    raw_value = os.getenv("MODEL_CONFIDENCE_THRESHOLD", "0.45")
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError("MODEL_CONFIDENCE_THRESHOLD must be a number") from exc
    if not 0.01 <= value <= 1.0:
        raise RuntimeError("MODEL_CONFIDENCE_THRESHOLD must be between 0.01 and 1.0")
    return value


MODEL_WIDTH = 1152
MODEL_HEIGHT = 576
PADDING_VALUE = 114
NMS_IOU_THRESHOLD = 0.5
DEFAULT_MODEL_CONFIDENCE = _model_confidence_from_environment()
ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png"}
EXPECTED_CLASSES = {"bus", "car", "tram"}
EXPORT_CLASS_IDS = {"bus": 0, "car": 1, "tram": 2}
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
JPEG_SOF_MARKERS = {
    0xC0,
    0xC1,
    0xC2,
    0xC3,
    0xC5,
    0xC6,
    0xC7,
    0xC9,
    0xCA,
    0xCB,
    0xCD,
    0xCE,
    0xCF,
}


class ImageSize(BaseModel):
    width: int
    height: int


class Detection(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    class_name: str = Field(alias="class")
    confidence: float
    bbox_xyxy: list[int]


class DetectionData(BaseModel):
    image_size: ImageSize
    counts: dict[str, int]
    total: int
    detections: list[Detection]


class DetectionResult(DetectionData):
    request_received_at: datetime
    processing_duration_ms: float
    filename: str | None
    conf: float
    model: str
    model_sha256: str
    cross_class_dedup: Literal[0, 1]
    cross_class_iou_threshold: float | None = None
    training_history: dict[str, Any] | None = None


class AnnotatedImage(BaseModel):
    media_type: str
    base64: str


class DetectionImageResult(DetectionResult):
    annotated_image: AnnotatedImage


class GoogleAuthRequest(BaseModel):
    id_token: str


class PackageCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=250)


class PackageImagesRequest(BaseModel):
    image_ids: list[str] = Field(min_length=1)


@dataclass(frozen=True)
class Settings:
    model_dir: Path
    model_files: tuple[str, ...]
    ort_intra_op_num_threads: int
    cross_class_dedup_default: Literal[0, 1]
    cross_class_iou_threshold: float
    max_upload_bytes: int
    max_image_pixels: int
    training_pool_dir: Path
    training_label_confidence: float
    training_image_max_dimension: int
    training_jpeg_quality: int
    training_quick_tags: tuple[str, ...]
    google_client_id: str
    session_secret: str

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            model_dir=Path(os.getenv("MODEL_DIR", "/app/models")).resolve(),
            model_files=_model_files_from_environment(),
            ort_intra_op_num_threads=_positive_int_environment(
                "ORT_INTRA_OP_NUM_THREADS", 3
            ),
            cross_class_dedup_default=_zero_or_one_environment(
                "CROSS_CLASS_DEDUP_DEFAULT"
            ),
            cross_class_iou_threshold=_required_float_environment(
                "CROSS_CLASS_IOU_THRESHOLD", minimum=0.01, maximum=1.0
            ),
            max_upload_bytes=_positive_int_environment(
                "MAX_UPLOAD_BYTES", 5 * 1024 * 1024
            ),
            max_image_pixels=_positive_int_environment(
                "MAX_IMAGE_PIXELS", 10_000_000
            ),
            training_pool_dir=Path(
                os.getenv("TRAINING_POOL_DIR", "/srv/liiklus/training_pool")
            ).resolve(),
            training_label_confidence=_float_environment(
                "TRAINING_LABEL_CONFIDENCE", 0.25, minimum=0.01, maximum=1.0
            ),
            training_image_max_dimension=_positive_int_environment(
                "TRAINING_IMAGE_MAX_DIMENSION", 1280
            ),
            training_jpeg_quality=_bounded_int_environment(
                "TRAINING_JPEG_QUALITY", 90, minimum=1, maximum=100
            ),
            training_quick_tags=_string_list_environment(
                "TRAINING_QUICK_TAGS_JSON",
                (
                    "Hämar/öö",
                    "Sõiduk okste taga",
                    "Sõiduk puudu",
                    "Valepositiivne",
                    "Vihm/lumi",
                ),
            ),
            google_client_id=os.getenv("GOOGLE_CLIENT_ID", "").strip(),
            session_secret=os.getenv("SESSION_SECRET", "").strip(),
        )

    @property
    def default_model(self) -> str:
        return self.model_files[0]


@dataclass(frozen=True)
class PreparedImage:
    original: np.ndarray
    tensor: np.ndarray
    original_width: int
    original_height: int
    resized_width: int
    resized_height: int


@dataclass(frozen=True)
class ProcessedImage:
    original: np.ndarray
    result: DetectionData


def _positive_int_environment(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def _zero_or_one_environment(name: str) -> Literal[0, 1]:
    raw_value = os.getenv(name)
    if raw_value not in {"0", "1"}:
        raise RuntimeError(f"{name} must be 0 or 1")
    return 1 if raw_value == "1" else 0


def _required_float_environment(
    name: str, *, minimum: float, maximum: float
) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        raise RuntimeError(f"{name} is required")
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _float_environment(
    name: str, default: float, *, minimum: float, maximum: float
) -> float:
    raw_value = os.getenv(name, str(default))
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _bounded_int_environment(
    name: str, default: int, *, minimum: int, maximum: int
) -> int:
    value = _positive_int_environment(name, default)
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


def _string_list_environment(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{name} must be a JSON array of strings") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise RuntimeError(f"{name} must be a JSON array of strings")
    tags = tuple(dict.fromkeys(item.strip() for item in value if item.strip()))
    if not tags:
        raise RuntimeError(f"{name} must contain at least one value")
    return tags


def _model_files_from_environment() -> tuple[str, ...]:
    model_files = _string_list_environment("MODEL_FILES_JSON", ("best.onnx",))
    for model_file in model_files:
        path = Path(model_file)
        if (
            path.name != model_file
            or path.suffix.lower() != ".onnx"
            or path.is_absolute()
        ):
            raise RuntimeError(
                "MODEL_FILES_JSON entries must be ONNX filenames without paths"
            )
    return model_files


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for chunk in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_class_names(raw_names: str | None) -> tuple[str, ...]:
    if not raw_names:
        raise RuntimeError("ONNX model metadata does not contain class names")
    try:
        parsed = ast.literal_eval(raw_names)
    except (SyntaxError, ValueError) as exc:
        raise RuntimeError("ONNX class metadata is invalid") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("ONNX class metadata must be a dictionary")

    normalized: dict[int, str] = {}
    for raw_index, raw_name in parsed.items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("ONNX class index is invalid") from exc
        if not isinstance(raw_name, str):
            raise RuntimeError("ONNX class name is invalid")
        normalized[index] = raw_name

    expected_indices = list(range(len(normalized)))
    if sorted(normalized) != expected_indices:
        raise RuntimeError("ONNX class indices must be consecutive and start at zero")
    names = tuple(normalized[index] for index in expected_indices)
    if set(names) != EXPECTED_CLASSES or len(names) != len(EXPECTED_CLASSES):
        raise RuntimeError("ONNX model must contain bus, car and tram classes exactly once")
    return names


def _png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise HTTPException(status_code=400, detail="Invalid PNG image")
    width, height = struct.unpack(">II", data[16:24])
    if width <= 0 or height <= 0:
        raise HTTPException(status_code=400, detail="Invalid PNG dimensions")
    return width, height


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        raise HTTPException(status_code=400, detail="Invalid JPEG image")

    position = 2
    while position < len(data):
        while position < len(data) and data[position] == 0xFF:
            position += 1
        if position >= len(data):
            break

        marker = data[position]
        position += 1
        if marker in {0x01, 0xD8, 0xD9} or 0xD0 <= marker <= 0xD7:
            continue
        if position + 2 > len(data):
            break

        segment_length = int.from_bytes(data[position : position + 2], "big")
        if segment_length < 2 or position + segment_length > len(data):
            break
        if marker in JPEG_SOF_MARKERS:
            if segment_length < 7:
                break
            height = int.from_bytes(data[position + 3 : position + 5], "big")
            width = int.from_bytes(data[position + 5 : position + 7], "big")
            if width <= 0 or height <= 0:
                break
            return width, height
        if marker == 0xDA:
            break
        position += segment_length

    raise HTTPException(status_code=400, detail="Invalid JPEG dimensions")


def _encoded_image_dimensions(data: bytes, media_type: str) -> tuple[int, int]:
    if media_type == "image/png":
        return _png_dimensions(data)
    return _jpeg_dimensions(data)


def _read_upload(file: UploadFile, settings: Settings) -> tuple[bytes, int, int]:
    if file.content_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Only image/jpeg and image/png uploads are supported",
        )
    if file.size is not None and file.size > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the 5 MiB limit")

    data = file.file.read(settings.max_upload_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="Image exceeds the 5 MiB limit")

    width, height = _encoded_image_dimensions(data, file.content_type)
    if width * height > settings.max_image_pixels:
        raise HTTPException(status_code=413, detail="Image exceeds the 10 megapixel limit")
    return data, width, height


def _decode_and_prepare(data: bytes, expected_width: int, expected_height: int) -> PreparedImage:
    encoded = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="Image could not be decoded")

    original_height, original_width = image.shape[:2]
    if (original_width, original_height) != (expected_width, expected_height):
        raise HTTPException(status_code=400, detail="Image dimensions are inconsistent")

    if original_width > MODEL_WIDTH or original_height > MODEL_HEIGHT:
        scale = min(MODEL_WIDTH / original_width, MODEL_HEIGHT / original_height)
        resized_width = max(1, min(MODEL_WIDTH, round(original_width * scale)))
        resized_height = max(1, min(MODEL_HEIGHT, round(original_height * scale)))
        resized = cv2.resize(
            image,
            (resized_width, resized_height),
            interpolation=cv2.INTER_AREA,
        )
    else:
        resized = image
        resized_width = original_width
        resized_height = original_height

    canvas = np.full(
        (MODEL_HEIGHT, MODEL_WIDTH, 3),
        PADDING_VALUE,
        dtype=np.uint8,
    )
    canvas[:resized_height, :resized_width] = resized
    rgb = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB)
    tensor = np.ascontiguousarray(rgb.transpose(2, 0, 1), dtype=np.float32)
    tensor = np.expand_dims(tensor / 255.0, axis=0)
    return PreparedImage(
        original=image,
        tensor=tensor,
        original_width=original_width,
        original_height=original_height,
        resized_width=resized_width,
        resized_height=resized_height,
    )


def _iou(reference: np.ndarray, others: np.ndarray) -> np.ndarray:
    left = np.maximum(reference[0], others[:, 0])
    top = np.maximum(reference[1], others[:, 1])
    right = np.minimum(reference[2], others[:, 2])
    bottom = np.minimum(reference[3], others[:, 3])
    intersection = np.maximum(0.0, right - left) * np.maximum(0.0, bottom - top)
    reference_area = max(0.0, reference[2] - reference[0]) * max(
        0.0, reference[3] - reference[1]
    )
    other_areas = np.maximum(0.0, others[:, 2] - others[:, 0]) * np.maximum(
        0.0, others[:, 3] - others[:, 1]
    )
    union = reference_area + other_areas - intersection
    return np.divide(
        intersection,
        union,
        out=np.zeros_like(intersection),
        where=union > 0,
    )


def _class_aware_nms(
    boxes: np.ndarray,
    confidences: np.ndarray,
    class_ids: np.ndarray,
) -> list[int]:
    kept: list[int] = []
    for class_id in np.unique(class_ids):
        class_indices = np.flatnonzero(class_ids == class_id)
        order = class_indices[np.argsort(confidences[class_indices])[::-1]]
        while order.size:
            current = int(order[0])
            kept.append(current)
            if order.size == 1:
                break
            remaining = order[1:]
            order = remaining[_iou(boxes[current], boxes[remaining]) <= NMS_IOU_THRESHOLD]
    return sorted(kept, key=lambda index: float(confidences[index]), reverse=True)


def _cross_class_deduplicate(
    kept_indices: list[int],
    boxes: np.ndarray,
    confidences: np.ndarray,
    class_ids: np.ndarray,
    iou_threshold: float,
) -> list[int]:
    deduplicated: list[int] = []
    ordered = sorted(
        kept_indices,
        key=lambda index: float(confidences[index]),
        reverse=True,
    )
    for current in ordered:
        earlier = np.asarray(
            [
                index
                for index in deduplicated
                if class_ids[index] != class_ids[current]
            ],
            dtype=np.int64,
        )
        if earlier.size and np.any(
            _iou(boxes[current], boxes[earlier]) >= iou_threshold
        ):
            continue
        deduplicated.append(current)
    return deduplicated


class Detector:
    def __init__(self, settings: Settings, model_name: str) -> None:
        model_path = settings.model_dir / model_name
        if not model_path.is_file():
            raise RuntimeError(f"ONNX model not found: {model_path}")

        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = settings.ort_intra_op_num_threads
        session_options.inter_op_num_threads = 1
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        self.settings = settings
        self.model_name = model_name
        self.model_sha256 = _sha256(model_path)
        self.class_names = _parse_class_names(
            self.session.get_modelmeta().custom_metadata_map.get("names")
        )
        self.input = self.session.get_inputs()[0]
        self.output = self.session.get_outputs()[0]
        self._validate_model_input()
        self._inference_lock = threading.Lock()

    def _validate_model_input(self) -> None:
        shape = self.input.shape
        if len(shape) != 4 or shape[1:] != [3, MODEL_HEIGHT, MODEL_WIDTH]:
            raise RuntimeError(
                "ONNX input shape must be [batch, 3, 576, 1152]"
            )
        if isinstance(shape[0], int) and shape[0] != 1:
            raise RuntimeError("ONNX model batch size must be one")

    def process(
        self,
        file: UploadFile,
        confidence_threshold: float,
        cross_class_iou_threshold: float | None = None,
    ) -> ProcessedImage:
        data, width, height = _read_upload(file, self.settings)
        return self.process_bytes(
            data,
            width,
            height,
            confidence_threshold,
            cross_class_iou_threshold,
        )

    def process_bytes(
        self,
        data: bytes,
        width: int,
        height: int,
        confidence_threshold: float,
        cross_class_iou_threshold: float | None = None,
    ) -> ProcessedImage:
        prepared = _decode_and_prepare(data, width, height)
        with self._inference_lock:
            raw_output = self.session.run(
                [self.output.name],
                {self.input.name: prepared.tensor},
            )[0]
        detections = self._postprocess(
            raw_output,
            prepared,
            confidence_threshold,
            cross_class_iou_threshold,
        )
        counts = {name: 0 for name in self.class_names}
        for detection in detections:
            counts[detection.class_name] += 1
        return ProcessedImage(
            original=prepared.original,
            result=DetectionData(
                image_size=ImageSize(width=width, height=height),
                counts=counts,
                total=len(detections),
                detections=detections,
            ),
        )

    def _postprocess(
        self,
        raw_output: np.ndarray,
        prepared: PreparedImage,
        confidence_threshold: float,
        cross_class_iou_threshold: float | None,
    ) -> list[Detection]:
        predictions = np.asarray(raw_output)
        if predictions.ndim == 3 and predictions.shape[0] == 1:
            predictions = predictions[0]
        if predictions.ndim != 2:
            raise RuntimeError("Unsupported ONNX detection output shape")

        feature_count = 4 + len(self.class_names)
        if predictions.shape[0] == feature_count:
            predictions = predictions.T
        elif predictions.shape[1] != feature_count:
            raise RuntimeError("ONNX detection output does not match model classes")

        class_scores = predictions[:, 4:]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[np.arange(class_scores.shape[0]), class_ids]
        selected = confidences >= confidence_threshold
        if not np.any(selected):
            return []

        xywh = predictions[selected, :4]
        confidences = confidences[selected].astype(np.float32, copy=False)
        class_ids = class_ids[selected].astype(np.int64, copy=False)
        boxes = np.empty_like(xywh, dtype=np.float32)
        boxes[:, 0] = xywh[:, 0] - xywh[:, 2] / 2.0
        boxes[:, 1] = xywh[:, 1] - xywh[:, 3] / 2.0
        boxes[:, 2] = xywh[:, 0] + xywh[:, 2] / 2.0
        boxes[:, 3] = xywh[:, 1] + xywh[:, 3] / 2.0

        boxes[:, [0, 2]] = np.clip(boxes[:, [0, 2]], 0, prepared.resized_width)
        boxes[:, [1, 3]] = np.clip(boxes[:, [1, 3]], 0, prepared.resized_height)
        valid = (boxes[:, 2] > boxes[:, 0]) & (boxes[:, 3] > boxes[:, 1])
        boxes = boxes[valid]
        confidences = confidences[valid]
        class_ids = class_ids[valid]
        if boxes.size == 0:
            return []

        scale_x = prepared.resized_width / prepared.original_width
        scale_y = prepared.resized_height / prepared.original_height
        boxes[:, [0, 2]] /= scale_x
        boxes[:, [1, 3]] /= scale_y
        kept = _class_aware_nms(boxes, confidences, class_ids)
        if cross_class_iou_threshold is not None:
            kept = _cross_class_deduplicate(
                kept,
                boxes,
                confidences,
                class_ids,
                cross_class_iou_threshold,
            )

        detections: list[Detection] = []
        for index in kept:
            rounded_box = [
                int(round(float(np.clip(boxes[index, 0], 0, prepared.original_width)))),
                int(round(float(np.clip(boxes[index, 1], 0, prepared.original_height)))),
                int(round(float(np.clip(boxes[index, 2], 0, prepared.original_width)))),
                int(round(float(np.clip(boxes[index, 3], 0, prepared.original_height)))),
            ]
            if rounded_box[2] <= rounded_box[0] or rounded_box[3] <= rounded_box[1]:
                continue
            detections.append(
                Detection(
                    class_name=self.class_names[int(class_ids[index])],
                    confidence=round(float(confidences[index]), 6),
                    bbox_xyxy=rounded_box,
                )
            )
        return detections


def _annotation_scale(image: np.ndarray) -> float:
    height, width = image.shape[:2]
    return max(1.0, max(width, height) / MODEL_WIDTH)


def _annotate(image: np.ndarray, detections: list[Detection]) -> bytes:
    annotated = image.copy()
    scale = _annotation_scale(image)
    box_thickness = max(2, round(2 * scale))
    font_scale = 0.55 * scale
    text_thickness = max(1, round(scale))
    horizontal_padding = max(4, round(4 * scale))
    vertical_padding = max(3, round(3 * scale))
    colors = {
        "bus": (60, 180, 75),
        "car": (230, 130, 40),
        "tram": (60, 60, 220),
    }
    for detection in detections:
        x1, y1, x2, y2 = detection.bbox_xyxy
        color = colors[detection.class_name]
        cv2.rectangle(
            annotated,
            (x1, y1),
            (x2, y2),
            color,
            box_thickness,
        )
        label = f"{detection.class_name} {detection.confidence:.2f}"
        (text_width, text_height), baseline = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            text_thickness,
        )
        label_top = max(
            0,
            y1 - text_height - baseline - 2 * vertical_padding,
        )
        label_right = min(
            annotated.shape[1],
            x1 + text_width + 2 * horizontal_padding,
        )
        cv2.rectangle(
            annotated,
            (x1, label_top),
            (label_right, y1),
            color,
            thickness=-1,
        )
        cv2.putText(
            annotated,
            label,
            (
                x1 + horizontal_padding,
                max(
                    text_height + vertical_padding,
                    y1 - baseline - vertical_padding,
                ),
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            font_scale,
            (255, 255, 255),
            text_thickness,
            cv2.LINE_AA,
        )

    encoded, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not encoded:
        raise RuntimeError("Annotated JPEG encoding failed")
    return jpeg.tobytes()


def _safe_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    return basename or None


def _resolve_cross_class_options(
    settings: Settings,
    cross_class_dedup: int | None,
    cross_class_iou_threshold: float | None,
) -> tuple[Literal[0, 1], float | None]:
    enabled = (
        settings.cross_class_dedup_default
        if cross_class_dedup is None
        else cross_class_dedup
    )
    if enabled == 0:
        if cross_class_iou_threshold is not None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "cross_class_iou_threshold is only allowed when cross_class_dedup is 1",
            )
        return 0, None
    return 1, (
        settings.cross_class_iou_threshold
        if cross_class_iou_threshold is None
        else cross_class_iou_threshold
    )


def _detection_result(
    processed: ProcessedImage,
    request_received_at: datetime,
    processing_duration_ms: float,
    filename: str | None,
    confidence_threshold: float,
    model_name: str,
    model_sha256: str,
    cross_class_dedup: Literal[0, 1],
    cross_class_iou_threshold: float | None,
    training_history: dict[str, Any] | None,
) -> DetectionResult:
    return DetectionResult(
        request_received_at=request_received_at,
        processing_duration_ms=round(processing_duration_ms, 3),
        filename=_safe_filename(filename),
        conf=confidence_threshold,
        model=model_name,
        model_sha256=model_sha256,
        cross_class_dedup=cross_class_dedup,
        cross_class_iou_threshold=cross_class_iou_threshold,
        training_history=training_history,
        image_size=processed.result.image_size,
        counts=processed.result.counts,
        total=processed.result.total,
        detections=processed.result.detections,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_environment()
    if not settings.session_secret:
        raise RuntimeError("SESSION_SECRET is required")
    if not settings.google_client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID is required")
    settings.training_pool_dir.mkdir(parents=True, exist_ok=True)
    app.state.settings = settings
    app.state.detectors = {
        model_name: Detector(settings, model_name)
        for model_name in settings.model_files
    }
    app.state.repository = OracleRepository.from_env()
    try:
        yield
    finally:
        app.state.repository.close()
        del app.state.repository
        del app.state.detectors


app = FastAPI(
    title="Tallinna liikluse tuvastuse API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "configure-session-secret"),
    session_cookie="liiklus_session",
    same_site="lax",
    https_only=True,
    max_age=12 * 60 * 60,
)


def _detector(request: Request, model_name: str | None = None) -> Detector:
    settings: Settings = request.app.state.settings
    selected_model = model_name or settings.default_model
    try:
        return request.app.state.detectors[selected_model]
    except KeyError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"Unknown model: {selected_model}",
        ) from exc


def _repository(request: Request) -> OracleRepository:
    return request.app.state.repository


async def current_user(request: Request) -> User:
    user_id = request.session.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    try:
        user = await run_in_threadpool(_repository(request).get_user, user_id)
    except NotFoundError as exc:
        request.session.clear()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required") from exc
    if not user.enabled:
        request.session.clear()
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    return user


def _csrf_token(request: Request) -> str:
    token = request.session.get("csrf_token")
    if not isinstance(token, str):
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def _verify_csrf(request: Request) -> None:
    expected = request.session.get("csrf_token")
    supplied = request.headers.get("X-CSRF-Token")
    if (
        not isinstance(expected, str)
        or not isinstance(supplied, str)
        or not secrets.compare_digest(expected, supplied)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid CSRF token")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


async def _verify_google_id_token(id_token: str, client_id: str) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(
                GOOGLE_TOKENINFO_URL, params={"id_token": id_token}
            )
    except httpx.RequestError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google is unavailable") from exc
    if response.status_code >= 400:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google login failed")
    try:
        profile = response.json()
    except ValueError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Google is unavailable") from exc
    if (
        not isinstance(profile, dict)
        or profile.get("aud") != client_id
        or profile.get("email_verified") not in (True, "true")
        or not isinstance(profile.get("sub"), str)
        or not isinstance(profile.get("email"), str)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Google login failed")
    return profile


@app.get("/api/auth/google/config")
def google_config(request: Request) -> dict[str, str]:
    return {"client_id": request.app.state.settings.google_client_id}


@app.post("/api/auth/google")
async def google_login(body: GoogleAuthRequest, request: Request) -> dict[str, bool]:
    profile = await _verify_google_id_token(
        body.id_token, request.app.state.settings.google_client_id
    )
    email = str(profile["email"]).strip().lower()
    user = await run_in_threadpool(
        _repository(request).get_or_create_google_user,
        str(profile["sub"]),
        email,
        str(profile.get("name") or email),
    )
    if not user.enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Account is disabled")
    request.session.clear()
    request.session["user_id"] = user.user_id
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(request: Request, user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    return {
        "public_id": user.public_id,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role_code,
        "csrf_token": _csrf_token(request),
        "training_quick_tags": settings.training_quick_tags,
        "models": settings.model_files,
        "default_model": settings.default_model,
        "cross_class_dedup_default": settings.cross_class_dedup_default,
        "cross_class_iou_threshold_default": settings.cross_class_iou_threshold,
    }


@app.post("/api/auth/logout")
def auth_logout(
    request: Request, user: Annotated[User, Depends(current_user)]
) -> dict[str, bool]:
    del user
    _verify_csrf(request)
    request.session.clear()
    return {"ok": True}


def _detect_upload(
    request: Request,
    detector: Detector,
    file: UploadFile,
    confidence_threshold: float,
    cross_class_iou_threshold: float | None,
) -> tuple[ProcessedImage, dict[str, Any] | None]:
    data, width, height = _read_upload(file, detector.settings)
    processed = detector.process_bytes(
        data,
        width,
        height,
        confidence_threshold,
        cross_class_iou_threshold,
    )
    history = _repository(request).training_history(hashlib.sha256(data).hexdigest())
    return processed, history


@app.post(
    "/api/detect",
    response_model=DetectionResult,
    response_model_exclude_none=True,
)
def detect(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File(description="JPEG or PNG image")],
    user: Annotated[User, Depends(current_user)],
    model: Annotated[
        str | None,
        Query(description="ONNX model filename; defaults to the first configured model"),
    ] = None,
    conf: Annotated[
        float,
        Query(
            ge=0.01,
            le=1.0,
            description="Minimum model confidence required for a detection",
        ),
    ] = DEFAULT_MODEL_CONFIDENCE,
    cross_class_dedup: Annotated[
        int | None,
        Query(
            ge=0,
            le=1,
            description="Enable cross-class duplicate filtering: 1 or 0",
        ),
    ] = None,
    cross_class_iou_threshold: Annotated[
        float | None,
        Query(
            ge=0.01,
            le=1.0,
            description="Cross-class IoU threshold; only allowed when filtering is enabled",
        ),
    ] = None,
) -> DetectionResult:
    del user
    request_received_at = datetime.now(timezone.utc)
    processing_started_at = time.perf_counter()
    detector = _detector(request, model)
    effective_dedup, effective_cross_class_iou = _resolve_cross_class_options(
        request.app.state.settings,
        cross_class_dedup,
        cross_class_iou_threshold,
    )
    processed, history = _detect_upload(
        request,
        detector,
        file,
        conf,
        effective_cross_class_iou,
    )
    result = _detection_result(
        processed,
        request_received_at,
        (time.perf_counter() - processing_started_at) * 1000,
        file.filename,
        conf,
        detector.model_name,
        detector.model_sha256,
        effective_dedup,
        effective_cross_class_iou,
        history,
    )
    response.headers["X-Model-SHA256"] = detector.model_sha256
    return result


@app.post(
    "/api/detect/image",
    response_model=DetectionImageResult,
    response_model_exclude_none=True,
)
def detect_image(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File(description="JPEG or PNG image")],
    user: Annotated[User, Depends(current_user)],
    model: Annotated[
        str | None,
        Query(description="ONNX model filename; defaults to the first configured model"),
    ] = None,
    conf: Annotated[
        float,
        Query(
            ge=0.01,
            le=1.0,
            description="Minimum model confidence required for a detection",
        ),
    ] = DEFAULT_MODEL_CONFIDENCE,
    cross_class_dedup: Annotated[
        int | None,
        Query(
            ge=0,
            le=1,
            description="Enable cross-class duplicate filtering: 1 or 0",
        ),
    ] = None,
    cross_class_iou_threshold: Annotated[
        float | None,
        Query(
            ge=0.01,
            le=1.0,
            description="Cross-class IoU threshold; only allowed when filtering is enabled",
        ),
    ] = None,
) -> DetectionImageResult:
    del user
    request_received_at = datetime.now(timezone.utc)
    processing_started_at = time.perf_counter()
    detector = _detector(request, model)
    effective_dedup, effective_cross_class_iou = _resolve_cross_class_options(
        request.app.state.settings,
        cross_class_dedup,
        cross_class_iou_threshold,
    )
    processed, history = _detect_upload(
        request,
        detector,
        file,
        conf,
        effective_cross_class_iou,
    )
    annotated_jpeg = _annotate(processed.original, processed.result.detections)
    result = _detection_result(
        processed,
        request_received_at,
        (time.perf_counter() - processing_started_at) * 1000,
        file.filename,
        conf,
        detector.model_name,
        detector.model_sha256,
        effective_dedup,
        effective_cross_class_iou,
        history,
    )
    response.headers["X-Model-SHA256"] = detector.model_sha256
    return DetectionImageResult(
        **result.model_dump(),
        annotated_image=AnnotatedImage(
            media_type="image/jpeg",
            base64=base64.b64encode(annotated_jpeg).decode("ascii"),
        ),
    )


def _parse_tags(raw_tags: str) -> list[str]:
    try:
        value = json.loads(raw_tags)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid tags") from exc
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid tags")
    return list(dict.fromkeys(item.strip() for item in value if item.strip()))


def _prepare_training_image(
    data: bytes,
    media_type: str,
    width: int,
    height: int,
    settings: Settings,
) -> tuple[bytes, str, str, int, int]:
    if max(width, height) <= settings.training_image_max_dimension:
        extension = ".png" if media_type == "image/png" else ".jpg"
        return data, media_type, extension, width, height
    image = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Image could not be decoded")
    scale = settings.training_image_max_dimension / max(width, height)
    stored_width = max(1, round(width * scale))
    stored_height = max(1, round(height * scale))
    resized = cv2.resize(
        image, (stored_width, stored_height), interpolation=cv2.INTER_AREA
    )
    encoded, jpeg = cv2.imencode(
        ".jpg", resized, [cv2.IMWRITE_JPEG_QUALITY, settings.training_jpeg_quality]
    )
    if not encoded:
        raise RuntimeError("Training JPEG encoding failed")
    return jpeg.tobytes(), "image/jpeg", ".jpg", stored_width, stored_height


def _training_filename(public_id: str, original_filename: str, extension: str) -> str:
    stem = Path(original_filename).stem
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")[:100]
    return f"{public_id}_{safe_stem or 'image'}{extension}"


def _yolo_labels(result: DetectionData) -> str:
    width = result.image_size.width
    height = result.image_size.height
    lines: list[str] = []
    for detection in result.detections:
        x1, y1, x2, y2 = detection.bbox_xyxy
        x_center = ((x1 + x2) / 2.0) / width
        y_center = ((y1 + y2) / 2.0) / height
        box_width = (x2 - x1) / width
        box_height = (y2 - y1) / height
        lines.append(
            f"{EXPORT_CLASS_IDS[detection.class_name]} "
            f"{x_center:.6f} {y_center:.6f} {box_width:.6f} {box_height:.6f}"
        )
    return "\n".join(lines) + ("\n" if lines else "")


def _pool_path(settings: Settings, relative_path: str) -> Path:
    target = (settings.training_pool_dir / relative_path).resolve()
    if target.parent != settings.training_pool_dir:
        raise RuntimeError("Invalid training pool path")
    return target


@app.post("/api/training-pool", status_code=status.HTTP_201_CREATED)
def create_training_candidate(
    request: Request,
    file: Annotated[UploadFile, File(description="JPEG or PNG image")],
    reason: Annotated[str, Form(max_length=2000)] = "",
    tags: Annotated[str, Form()] = "[]",
    model: Annotated[str | None, Form()] = None,
    cross_class_dedup: Annotated[int | None, Form(ge=0, le=1)] = None,
    cross_class_iou_threshold: Annotated[
        float | None,
        Form(ge=0.01, le=1.0),
    ] = None,
    user: User = Depends(current_user),
) -> dict[str, Any]:
    _verify_csrf(request)
    reason = reason.strip()
    settings: Settings = request.app.state.settings
    source_data, source_width, source_height = _read_upload(file, settings)
    source_sha256 = hashlib.sha256(source_data).hexdigest()
    history = _repository(request).training_history(source_sha256)
    if history and any(item["file_available"] for item in history["selections"]):
        raise HTTPException(status.HTTP_409_CONFLICT, "Image is already a training candidate")
    original_filename = _safe_filename(file.filename) or "image"
    stored_data, stored_media_type, extension, stored_width, stored_height = (
        _prepare_training_image(
            source_data,
            file.content_type or "",
            source_width,
            source_height,
            settings,
        )
    )
    detector = _detector(request, model)
    effective_dedup, effective_cross_class_iou = _resolve_cross_class_options(
        settings,
        cross_class_dedup,
        cross_class_iou_threshold,
    )
    processed = detector.process_bytes(
        stored_data,
        stored_width,
        stored_height,
        settings.training_label_confidence,
        effective_cross_class_iou,
    )
    public_id = str(uuid.uuid4())
    image_relative_path = _training_filename(public_id, original_filename, extension)
    label_relative_path = f"{Path(image_relative_path).stem}.txt"
    image_path = _pool_path(settings, image_relative_path)
    label_path = _pool_path(settings, label_relative_path)
    image_temp = image_path.with_name(f".{image_path.name}.tmp")
    label_temp = label_path.with_name(f".{label_path.name}.tmp")
    try:
        image_temp.write_bytes(stored_data)
        label_temp.write_text(_yolo_labels(processed.result), encoding="utf-8")
        image_temp.replace(image_path)
        label_temp.replace(label_path)
        _repository(request).create_training_image(
            {
                "public_id": public_id,
                "candidate_by_user_id": user.user_id,
                "original_filename": original_filename,
                "image_relative_path": image_relative_path,
                "label_relative_path": label_relative_path,
                "source_media_type": file.content_type,
                "stored_media_type": stored_media_type,
                "source_size_bytes": len(source_data),
                "stored_size_bytes": len(stored_data),
                "source_width": source_width,
                "source_height": source_height,
                "stored_width": stored_width,
                "stored_height": stored_height,
                "source_sha256": source_sha256,
                "stored_sha256": hashlib.sha256(stored_data).hexdigest(),
                "reason": reason or None,
                "tags_json": _parse_tags(tags),
                "analysis_json": {
                    "conf": settings.training_label_confidence,
                    "model": detector.model_name,
                    "model_sha256": detector.model_sha256,
                    "cross_class_dedup": effective_dedup,
                    **(
                        {"cross_class_iou_threshold": effective_cross_class_iou}
                        if effective_cross_class_iou is not None
                        else {}
                    ),
                    "image_size": processed.result.image_size.model_dump(),
                    "counts": processed.result.counts,
                    "total": processed.result.total,
                    "detections": [
                        item.model_dump(by_alias=True) for item in processed.result.detections
                    ],
                },
                "model_sha256": detector.model_sha256,
                "label_confidence": settings.training_label_confidence,
            }
        )
    except ConflictError as exc:
        image_temp.unlink(missing_ok=True)
        label_temp.unlink(missing_ok=True)
        image_path.unlink(missing_ok=True)
        label_path.unlink(missing_ok=True)
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except Exception:
        image_temp.unlink(missing_ok=True)
        label_temp.unlink(missing_ok=True)
        image_path.unlink(missing_ok=True)
        label_path.unlink(missing_ok=True)
        raise
    return {
        "id": public_id,
        "candidate_at": datetime.now(timezone.utc),
        "candidate_by": user.display_name or user.email,
    }


@app.get("/api/training-pool")
def list_training_candidates(
    request: Request,
    user: Annotated[User, Depends(current_user)],
    q: str = "",
    package: str = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    del user
    result = _repository(request).list_training_images(
        q.strip(), limit, offset, package.strip()
    )
    for item in result["items"]:
        item.pop("image_relative_path", None)
        tags = item.pop("tags_json", None) or []
        if isinstance(tags, str):
            try:
                tags = json.loads(tags)
            except json.JSONDecodeError:
                tags = []
        item["tags"] = tags if isinstance(tags, list) else []
        analysis = item.pop("analysis_json", None) or {}
        if isinstance(analysis, str):
            try:
                analysis = json.loads(analysis)
            except json.JSONDecodeError:
                analysis = {}
        item["detections_summary"] = {
            "counts": analysis.get("counts", {}),
            "total": analysis.get("total", 0),
        }
    return result


@app.get("/api/training-pool/{image_id}/image")
def training_candidate_image(
    image_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    thumbnail: bool = False,
) -> Response:
    del user
    try:
        item = _repository(request).get_training_image(image_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    path = _pool_path(request.app.state.settings, item["image_relative_path"])
    if not path.is_file():
        raise HTTPException(status.HTTP_410_GONE, "Training image file is missing")
    if not thumbnail:
        return FileResponse(path, media_type=item["stored_media_type"])
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Image could not be read")
    height, width = image.shape[:2]
    scale = min(1.0, 320 / max(width, height))
    if scale < 1.0:
        image = cv2.resize(
            image, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA
        )
    encoded, jpeg = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 82])
    if not encoded:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Thumbnail failed")
    return Response(jpeg.tobytes(), media_type="image/jpeg")


@app.delete("/api/training-pool/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_training_candidate(
    image_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    del user
    _verify_csrf(request)
    try:
        item = _repository(request).close_training_image(image_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    settings: Settings = request.app.state.settings
    _pool_path(settings, item["image_relative_path"]).unlink(missing_ok=True)
    _pool_path(settings, item["label_relative_path"]).unlink(missing_ok=True)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/api/training-packages", status_code=status.HTTP_201_CREATED)
def create_training_package(
    body: PackageCreateRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    _verify_csrf(request)
    name = body.name.strip()
    if not name:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Package name is required")
    try:
        return _repository(request).create_training_package(name, user.user_id)
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@app.get("/api/training-packages")
def list_training_packages(
    request: Request, user: Annotated[User, Depends(current_user)]
) -> list[dict[str, Any]]:
    del user
    return _repository(request).list_training_packages()


@app.get("/api/training-packages/{package_id}")
def get_training_package(
    package_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    del user
    try:
        package = _repository(request).package_export_snapshot(package_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    package["items"] = [
        {
            "id": item["public_id"],
            "original_filename": item["original_filename"],
            "added_at": item["added_at"],
            "added_by": item["added_by_name"] or item["added_by_email"],
            "file_available": item["end_date"] is None,
        }
        for item in package["items"]
    ]
    return package


@app.post("/api/training-packages/{package_id}/images")
def add_training_package_images(
    package_id: str,
    body: PackageImagesRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, Any]:
    _verify_csrf(request)
    try:
        return _repository(request).add_images_to_package(
            package_id, body.image_ids, user.user_id
        )
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@app.delete("/api/training-packages/{package_id}/images/{image_id}", status_code=204)
def remove_training_package_image(
    package_id: str,
    image_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    del user
    _verify_csrf(request)
    try:
        _repository(request).remove_image_from_package(package_id, image_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return Response(status_code=204)


def _safe_archive_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return value or "training-package"


def _delete_file(path: str) -> None:
    Path(path).unlink(missing_ok=True)


@app.post("/api/training-packages/{package_id}/download")
def download_training_package(
    package_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FileResponse:
    _verify_csrf(request)
    try:
        package = _repository(request).package_export_snapshot(package_id)
    except NotFoundError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    items = package["items"]
    if not items:
        raise HTTPException(status.HTTP_409_CONFLICT, "Training package is empty")
    settings: Settings = request.app.state.settings
    temporary = tempfile.NamedTemporaryFile(prefix="liiklus-training-", suffix=".zip", delete=False)
    temporary.close()
    try:
        with zipfile.ZipFile(temporary.name, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("classes.txt", "bus\ncar\ntram\n")
            manifest_buffer = io.StringIO()
            writer = csv.writer(manifest_buffer)
            writer.writerow(
                ["id", "filename", "original_filename", "candidate_at", "reason", "candidate_by"]
            )
            for item in items:
                if item["end_date"] is not None:
                    raise ConflictError("Training package contains a deleted image")
                image_path = _pool_path(settings, item["image_relative_path"])
                label_path = _pool_path(settings, item["label_relative_path"])
                if not image_path.is_file() or not label_path.is_file():
                    raise ConflictError("Training package contains a missing file")
                archive.write(image_path, arcname=image_path.name)
                archive.write(label_path, arcname=label_path.name)
                writer.writerow(
                    [
                        item["public_id"],
                        image_path.name,
                        item["original_filename"],
                        item["created"],
                        item["reason"],
                        item["candidate_by_name"],
                    ]
                )
            archive.writestr("manifest.csv", manifest_buffer.getvalue())
        _repository(request).record_package_download(
            package_id, user.user_id, [str(item["public_id"]) for item in items]
        )
    except (ConflictError, NotFoundError) as exc:
        _delete_file(temporary.name)
        status_code = (
            status.HTTP_404_NOT_FOUND if isinstance(exc, NotFoundError) else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code, str(exc)) from exc
    except Exception:
        _delete_file(temporary.name)
        raise
    filename = f"{_safe_archive_name(package['package_name'])}.zip"
    return FileResponse(
        temporary.name,
        media_type="application/zip",
        filename=filename,
        background=BackgroundTask(_delete_file, temporary.name),
    )
