from __future__ import annotations

import ast
import hashlib
import os
import struct
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import cv2
import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import Response as FastAPIResponse
from pydantic import BaseModel, ConfigDict, Field


def _model_confidence_from_environment() -> float:
    raw_value = os.getenv("MODEL_CONFIDENCE_THRESHOLD", "0.45")
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError("MODEL_CONFIDENCE_THRESHOLD must be a number") from exc
    if not 0.0 <= value <= 1.0:
        raise RuntimeError("MODEL_CONFIDENCE_THRESHOLD must be between 0.0 and 1.0")
    return value


MODEL_WIDTH = 1152
MODEL_HEIGHT = 576
PADDING_VALUE = 114
NMS_IOU_THRESHOLD = 0.5
DEFAULT_MODEL_CONFIDENCE = _model_confidence_from_environment()
ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png"}
EXPECTED_CLASSES = {"bus", "car", "tram"}
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


class DetectionResult(BaseModel):
    image_size: ImageSize
    counts: dict[str, int]
    total: int
    detections: list[Detection]


@dataclass(frozen=True)
class Settings:
    model_path: Path
    ort_intra_op_num_threads: int
    max_upload_bytes: int
    max_image_pixels: int

    @classmethod
    def from_environment(cls) -> Settings:
        return cls(
            model_path=Path(os.getenv("MODEL_PATH", "/app/models/best.onnx")),
            ort_intra_op_num_threads=_positive_int_environment(
                "ORT_INTRA_OP_NUM_THREADS", 3
            ),
            max_upload_bytes=_positive_int_environment(
                "MAX_UPLOAD_BYTES", 5 * 1024 * 1024
            ),
            max_image_pixels=_positive_int_environment(
                "MAX_IMAGE_PIXELS", 10_000_000
            ),
        )


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
    result: DetectionResult


def _positive_int_environment(name: str, default: int) -> int:
    raw_value = os.getenv(name, str(default))
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


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


class Detector:
    def __init__(self, settings: Settings) -> None:
        if not settings.model_path.is_file():
            raise RuntimeError(f"ONNX model not found: {settings.model_path}")

        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = settings.ort_intra_op_num_threads
        session_options.inter_op_num_threads = 1
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(
            str(settings.model_path),
            sess_options=session_options,
            providers=["CPUExecutionProvider"],
        )
        self.settings = settings
        self.model_sha256 = _sha256(settings.model_path)
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

    def process(self, file: UploadFile, confidence_threshold: float) -> ProcessedImage:
        data, width, height = _read_upload(file, self.settings)
        prepared = _decode_and_prepare(data, width, height)
        with self._inference_lock:
            raw_output = self.session.run(
                [self.output.name],
                {self.input.name: prepared.tensor},
            )[0]
        detections = self._postprocess(raw_output, prepared, confidence_threshold)
        counts = {name: 0 for name in self.class_names}
        for detection in detections:
            counts[detection.class_name] += 1
        return ProcessedImage(
            original=prepared.original,
            result=DetectionResult(
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


def _annotate(image: np.ndarray, detections: list[Detection]) -> bytes:
    annotated = image.copy()
    colors = {
        "bus": (60, 180, 75),
        "car": (230, 130, 40),
        "tram": (60, 60, 220),
    }
    for detection in detections:
        x1, y1, x2, y2 = detection.bbox_xyxy
        color = colors[detection.class_name]
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = f"{detection.class_name} {detection.confidence:.2f}"
        (text_width, text_height), baseline = cv2.getTextSize(
            label,
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            1,
        )
        label_top = max(0, y1 - text_height - baseline - 6)
        label_right = min(annotated.shape[1], x1 + text_width + 8)
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
            (x1 + 4, max(text_height + 2, y1 - baseline - 3)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    encoded, jpeg = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not encoded:
        raise RuntimeError("Annotated JPEG encoding failed")
    return jpeg.tobytes()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.detector = Detector(Settings.from_environment())
    yield
    del app.state.detector


app = FastAPI(
    title="Tallinna liikluse tuvastuse API",
    version="1.0.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
    lifespan=lifespan,
)


def _detector(request: Request) -> Detector:
    return request.app.state.detector


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/detect", response_model=DetectionResult)
def detect(
    request: Request,
    response: Response,
    file: Annotated[UploadFile, File(description="JPEG or PNG image")],
    conf: Annotated[
        float,
        Query(
            ge=0.0,
            le=1.0,
            description="Minimum model confidence required for a detection",
        ),
    ] = DEFAULT_MODEL_CONFIDENCE,
) -> DetectionResult:
    detector = _detector(request)
    processed = detector.process(file, conf)
    response.headers["X-Model-SHA256"] = detector.model_sha256
    return processed.result


@app.post(
    "/api/detect/image",
    response_class=FastAPIResponse,
    responses={200: {"content": {"image/jpeg": {}}}},
)
def detect_image(
    request: Request,
    file: Annotated[UploadFile, File(description="JPEG or PNG image")],
    conf: Annotated[
        float,
        Query(
            ge=0.0,
            le=1.0,
            description="Minimum model confidence required for a detection",
        ),
    ] = DEFAULT_MODEL_CONFIDENCE,
) -> FastAPIResponse:
    detector = _detector(request)
    processed = detector.process(file, conf)
    return FastAPIResponse(
        content=_annotate(processed.original, processed.result.detections),
        media_type="image/jpeg",
        headers={"X-Model-SHA256": detector.model_sha256},
    )
