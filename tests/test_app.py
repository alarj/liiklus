from __future__ import annotations

import base64
import os
import struct
from decimal import Decimal
from datetime import datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

import cv2
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import Headers, UploadFile

import app as traffic_app


class FakeRepository:
    def close(self) -> None:
        pass

    def training_history(self, source_sha256: str, camera_profile_id: int) -> None:
        del source_sha256, camera_profile_id
        return None

    def list_camera_profiles(self) -> list[dict[str, object]]:
        return [
            {
                "camera_profile_id": 1,
                "profile_code": "parnu-mnt-karja",
                "profile_version": 1,
                "profile_name": "Pärnu mnt - Karja",
                "sort_order": 10,
                "is_default": 1,
                "source_image_url": None,
                "model_files_json": ["best.onnx"],
                "vehicle_classes_json": [
                    {"model_index": 0, "code": "bus", "name": "Buss"},
                    {"model_index": 1, "code": "car", "name": "Auto"},
                    {"model_index": 2, "code": "tram", "name": "Tramm"},
                ],
                "roi_mask_json": None,
                "default_confidence": 0.45,
            }
        ]


TEST_USER = traffic_app.User(
    user_id=1,
    public_id="00000000-0000-0000-0000-000000000001",
    email="user@example.test",
    display_name="Test User",
    role_code="USER",
    enabled=True,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    environment = {
        "CROSS_CLASS_DEDUP_DEFAULT": "1",
        "CROSS_CLASS_IOU_THRESHOLD": "0.80",
        "GOOGLE_CLIENT_ID": "test.apps.googleusercontent.com",
        "SESSION_SECRET": "test-session-secret",
        "TRAINING_POOL_DIR": "/tmp/liiklus-test-training-pool",
    }
    traffic_app.app.dependency_overrides[traffic_app.current_user] = lambda: TEST_USER
    with patch.dict(os.environ, environment), patch.object(
        traffic_app.OracleRepository, "from_env", return_value=FakeRepository()
    ):
        with TestClient(traffic_app.app) as test_client:
            yield test_client
    traffic_app.app.dependency_overrides.clear()


def _encode(image: np.ndarray, extension: str) -> bytes:
    success, encoded = cv2.imencode(extension, image)
    assert success
    return encoded.tobytes()


def _upload(data: bytes, media_type: str, *, size: int | None = None) -> UploadFile:
    return UploadFile(
        file=BytesIO(data),
        filename="image",
        size=len(data) if size is None else size,
        headers=Headers({"content-type": media_type}),
    )


def _settings() -> traffic_app.Settings:
    return traffic_app.Settings(
        model_dir=traffic_app.Path("/tmp"),
        ort_intra_op_num_threads=3,
        cross_class_dedup_default=1,
        cross_class_iou_threshold=0.80,
        max_upload_bytes=5 * 1024 * 1024,
        max_image_pixels=10_000_000,
        training_pool_dir=traffic_app.Path("/tmp/liiklus-test-training-pool"),
        training_label_confidence=0.25,
        training_image_max_dimension=1280,
        training_jpeg_quality=90,
        training_quick_tags=(
            "Hämar/öö",
            "Sõiduk okste taga",
            "Sõiduk puudu",
            "Valepositiivne",
            "Vihm/lumi",
        ),
        google_client_id="test.apps.googleusercontent.com",
        session_secret="test-session-secret",
    )


def test_camera_profiles_require_exactly_one_default() -> None:
    rows = FakeRepository().list_camera_profiles()
    rows[0]["is_default"] = 0

    with pytest.raises(RuntimeError, match="Exactly one active default"):
        traffic_app._camera_profiles(rows)


def test_camera_profile_preserves_model_order() -> None:
    rows = FakeRepository().list_camera_profiles()
    rows[0]["model_files_json"] = ["best v3.onnx", "best v2.onnx", "best.onnx"]

    profile = traffic_app._camera_profiles(rows)[0]

    assert profile.default_model == "best v3.onnx"
    assert profile.model_files == ("best v3.onnx", "best v2.onnx", "best.onnx")


def test_camera_profile_accepts_oracle_json_decimal_numbers() -> None:
    rows = FakeRepository().list_camera_profiles()
    rows[0]["vehicle_classes_json"][0]["model_index"] = Decimal("0")
    rows[0]["roi_mask_json"] = {
        "type": "polygon",
        "fill_rgb": [Decimal("114"), Decimal("114"), Decimal("114")],
        "normalized_points": [
            [Decimal("0"), Decimal("0")],
            [Decimal("1"), Decimal("0")],
            [Decimal("1"), Decimal("1")],
        ],
    }

    profile = traffic_app._camera_profiles(rows)[0]

    assert profile.vehicle_classes[0].model_index == 0
    assert profile.roi_mask is not None
    assert profile.roi_mask.fill_rgb == (114, 114, 114)


def test_small_image_is_not_scaled_and_is_padded_right_and_bottom() -> None:
    image = np.full((550, 1150, 3), (10, 20, 30), dtype=np.uint8)
    data = _encode(image, ".png")

    prepared = traffic_app._decode_and_prepare(data, 1150, 550, 1152, 576, None)

    assert (prepared.resized_width, prepared.resized_height) == (1150, 550)
    rgb_tensor = prepared.tensor[0].transpose(1, 2, 0)
    np.testing.assert_allclose(
        rgb_tensor[549, 1149],
        np.array([30, 20, 10], dtype=np.float32) / 255.0,
        atol=1e-6,
    )
    np.testing.assert_allclose(
        rgb_tensor[550, 0],
        np.full(3, traffic_app.PADDING_VALUE / 255.0, dtype=np.float32),
        atol=1e-6,
    )
    np.testing.assert_allclose(
        rgb_tensor[0, 1150],
        np.full(3, traffic_app.PADDING_VALUE / 255.0, dtype=np.float32),
        atol=1e-6,
    )


def test_large_image_is_scaled_with_aspect_ratio_and_padded() -> None:
    image = np.full((500, 2000, 3), (10, 20, 30), dtype=np.uint8)
    data = _encode(image, ".jpg")

    prepared = traffic_app._decode_and_prepare(data, 2000, 500, 1152, 576, None)

    assert (prepared.resized_width, prepared.resized_height) == (1152, 288)
    assert prepared.resized_width / prepared.resized_height == pytest.approx(4.0)
    rgb_tensor = prepared.tensor[0].transpose(1, 2, 0)
    np.testing.assert_allclose(
        rgb_tensor[288, 0],
        np.full(3, traffic_app.PADDING_VALUE / 255.0, dtype=np.float32),
        atol=1e-6,
    )


def test_roi_mask_keeps_inside_pixel_and_fills_outside_pixel() -> None:
    image = np.full((100, 200, 3), (10, 20, 30), dtype=np.uint8)
    roi_mask = traffic_app.RoiMask(
        normalized_points=((0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)),
        fill_rgb=(114, 114, 114),
    )

    masked = traffic_app._apply_roi_mask(image, roi_mask)

    np.testing.assert_array_equal(masked[0, 0], (114, 114, 114))
    np.testing.assert_array_equal(masked[50, 100], (10, 20, 30))


def test_cam_sized_image_is_masked_and_padded_on_one_canvas() -> None:
    image = np.full((720, 1280, 3), (10, 20, 30), dtype=np.uint8)
    data = _encode(image, ".png")
    roi_mask = traffic_app.RoiMask(
        normalized_points=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)),
        fill_rgb=(114, 114, 114),
    )

    prepared = traffic_app._decode_and_prepare(
        data, 1280, 720, 1280, 736, roi_mask
    )

    assert prepared.tensor.shape == (1, 3, 736, 1280)
    rgb_tensor = prepared.tensor[0].transpose(1, 2, 0)
    np.testing.assert_allclose(
        rgb_tensor[719, 640],
        np.array([30, 20, 10], dtype=np.float32) / 255.0,
        atol=1e-6,
    )
    np.testing.assert_allclose(
        rgb_tensor[720, 640],
        np.full(3, traffic_app.PADDING_VALUE / 255.0, dtype=np.float32),
        atol=1e-6,
    )


def test_detector_reads_fixed_input_dimensions_from_onnx_shape() -> None:
    detector = traffic_app.Detector.__new__(traffic_app.Detector)
    detector.input = SimpleNamespace(shape=[1, 3, 736, 1280])

    detector._validate_model_input()

    assert detector.input_height == 736
    assert detector.input_width == 1280


def test_detector_rejects_dynamic_image_dimensions() -> None:
    detector = traffic_app.Detector.__new__(traffic_app.Detector)
    detector.input = SimpleNamespace(shape=[1, 3, "height", "width"])

    with pytest.raises(RuntimeError, match="height and width"):
        detector._validate_model_input()


def test_unsupported_media_type_is_rejected() -> None:
    with pytest.raises(HTTPException) as error:
        traffic_app._read_upload(_upload(b"not-an-image", "text/plain"), _settings())

    assert error.value.status_code == 415


def test_file_over_five_mib_is_rejected() -> None:
    upload = _upload(
        b"small-placeholder",
        "image/png",
        size=5 * 1024 * 1024 + 1,
    )

    with pytest.raises(HTTPException) as error:
        traffic_app._read_upload(upload, _settings())

    assert error.value.status_code == 413


def test_image_over_ten_megapixels_is_rejected_before_decode() -> None:
    png_header = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + struct.pack(">II", 4000, 3000)
    )

    with pytest.raises(HTTPException) as error:
        traffic_app._read_upload(_upload(png_header, "image/png"), _settings())

    assert error.value.status_code == 413


def test_cross_class_deduplication_keeps_higher_confidence_duplicate() -> None:
    boxes = np.asarray([[0, 0, 100, 100], [2, 2, 100, 100]], dtype=np.float32)
    confidences = np.asarray([0.78, 0.76], dtype=np.float32)
    class_ids = np.asarray([0, 2], dtype=np.int64)

    kept = traffic_app._cross_class_deduplicate(
        [1, 0], boxes, confidences, class_ids, 0.80
    )

    assert kept == [0]


def test_cross_class_deduplication_keeps_low_iou_different_classes() -> None:
    boxes = np.asarray([[0, 0, 100, 100], [20, 20, 50, 50]], dtype=np.float32)
    confidences = np.asarray([0.78, 0.76], dtype=np.float32)
    class_ids = np.asarray([0, 1], dtype=np.int64)

    kept = traffic_app._cross_class_deduplicate(
        [0, 1], boxes, confidences, class_ids, 0.80
    )

    assert kept == [0, 1]


def test_cross_class_deduplication_does_not_touch_same_class() -> None:
    boxes = np.asarray([[0, 0, 100, 100], [1, 1, 100, 100]], dtype=np.float32)
    confidences = np.asarray([0.78, 0.76], dtype=np.float32)
    class_ids = np.asarray([1, 1], dtype=np.int64)

    kept = traffic_app._cross_class_deduplicate(
        [0, 1], boxes, confidences, class_ids, 0.80
    )

    assert kept == [0, 1]


def test_cross_class_deduplication_suppresses_at_exact_threshold() -> None:
    boxes = np.asarray([[0, 0, 10, 10], [0, 0, 8, 10]], dtype=np.float32)
    confidences = np.asarray([0.78, 0.76], dtype=np.float32)
    class_ids = np.asarray([0, 2], dtype=np.int64)

    kept = traffic_app._cross_class_deduplicate(
        [0, 1], boxes, confidences, class_ids, 0.80
    )

    assert kept == [0]


def test_annotation_scale_grows_with_large_images() -> None:
    small = np.zeros((550, 1150, 3), dtype=np.uint8)
    large = np.zeros((2250, 4000, 3), dtype=np.uint8)

    assert traffic_app._annotation_scale(small) == 1.0
    assert traffic_app._annotation_scale(large) == pytest.approx(4000 / 1152)


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_detection_endpoints_with_synthetic_image(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    data = _encode(image, ".jpg")
    files = {"file": ("blank.jpg", data, "image/jpeg")}
    process_calls = 0
    default_model = client.app.state.default_camera_profile.default_model
    default_detector = client.app.state.detectors[default_model]
    original_infer = default_detector.infer

    def counted_infer(tensor: np.ndarray) -> np.ndarray:
        nonlocal process_calls
        process_calls += 1
        return original_infer(tensor)

    monkeypatch.setattr(default_detector, "infer", counted_infer)

    json_response = client.post("/api/detect", files=files)

    assert json_response.status_code == 200
    assert process_calls == 1
    payload = json_response.json()
    assert payload["filename"] == "blank.jpg"
    assert payload["conf"] == traffic_app.DEFAULT_MODEL_CONFIDENCE
    assert payload["profile"] == {
        "code": "parnu-mnt-karja",
        "version": 1,
        "name": "Pärnu mnt - Karja",
    }
    assert payload["model"] == default_model
    assert payload["cross_class_dedup"] == 1
    assert payload["cross_class_iou_threshold"] == 0.8
    request_received_at = datetime.fromisoformat(
        payload["request_received_at"].replace("Z", "+00:00")
    )
    assert request_received_at.utcoffset().total_seconds() == 0
    assert payload["processing_duration_ms"] >= 0
    assert payload["image_size"] == {"width": 64, "height": 64}
    assert list(payload["counts"]) == ["bus", "car", "tram"]
    assert payload["total"] == sum(payload["counts"].values())
    assert len(json_response.headers["X-Model-SHA256"]) == 64

    image_response = client.post(
        "/api/detect/image?conf=0.25&cross_class_dedup=0",
        files=files,
    )

    assert image_response.status_code == 200
    assert process_calls == 2
    assert image_response.headers["content-type"] == "application/json"
    assert len(image_response.headers["X-Model-SHA256"]) == 64
    image_payload = image_response.json()
    assert image_payload["filename"] == "blank.jpg"
    assert image_payload["conf"] == 0.25
    assert image_payload["profile"] == payload["profile"]
    assert image_payload["model"] == default_model
    assert image_payload["cross_class_dedup"] == 0
    assert "cross_class_iou_threshold" not in image_payload
    image_request_received_at = datetime.fromisoformat(
        image_payload["request_received_at"].replace("Z", "+00:00")
    )
    assert image_request_received_at.utcoffset().total_seconds() == 0
    assert image_payload["processing_duration_ms"] >= 0
    assert image_payload["image_size"] == payload["image_size"]
    assert image_payload["counts"] == payload["counts"]
    assert image_payload["total"] == payload["total"]
    assert image_payload["detections"] == payload["detections"]
    assert image_payload["annotated_image"]["media_type"] == "image/jpeg"
    annotated_jpeg = base64.b64decode(
        image_payload["annotated_image"]["base64"],
        validate=True,
    )
    assert annotated_jpeg.startswith(b"\xff\xd8")

    invalid_model_response = client.post(
        "/api/detect?model=missing.onnx",
        files=files,
    )

    assert invalid_model_response.status_code == 400

    invalid_profile_response = client.post(
        "/api/detect?profile=missing",
        files=files,
    )

    assert invalid_profile_response.status_code == 400
    assert "parnu-mnt-karja" in invalid_profile_response.json()["detail"]

    invalid_dedup_response = client.post(
        "/api/detect?cross_class_dedup=true",
        files=files,
    )
    assert invalid_dedup_response.status_code == 422

    out_of_range_dedup_response = client.post(
        "/api/detect?cross_class_dedup=2",
        files=files,
    )
    assert out_of_range_dedup_response.status_code == 422

    conflicting_response = client.post(
        "/api/detect?cross_class_dedup=0&cross_class_iou_threshold=0.8",
        files=files,
    )
    assert conflicting_response.status_code == 422
