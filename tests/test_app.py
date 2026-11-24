from __future__ import annotations

import base64
import os
import struct
from datetime import datetime
from io import BytesIO
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

    def training_history(self, source_sha256: str) -> None:
        del source_sha256
        return None


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
        model_path=traffic_app.Settings.from_environment().model_path,
        ort_intra_op_num_threads=3,
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


def test_small_image_is_not_scaled_and_is_padded_right_and_bottom() -> None:
    image = np.full((550, 1150, 3), (10, 20, 30), dtype=np.uint8)
    data = _encode(image, ".png")

    prepared = traffic_app._decode_and_prepare(data, 1150, 550)

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

    prepared = traffic_app._decode_and_prepare(data, 2000, 500)

    assert (prepared.resized_width, prepared.resized_height) == (1152, 288)
    assert prepared.resized_width / prepared.resized_height == pytest.approx(4.0)
    rgb_tensor = prepared.tensor[0].transpose(1, 2, 0)
    np.testing.assert_allclose(
        rgb_tensor[288, 0],
        np.full(3, traffic_app.PADDING_VALUE / 255.0, dtype=np.float32),
        atol=1e-6,
    )


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
    original_process = client.app.state.detector.process_bytes

    def counted_process_bytes(
        image_data: bytes,
        width: int,
        height: int,
        confidence_threshold: float,
    ) -> traffic_app.ProcessedImage:
        nonlocal process_calls
        process_calls += 1
        return original_process(image_data, width, height, confidence_threshold)

    monkeypatch.setattr(client.app.state.detector, "process_bytes", counted_process_bytes)

    json_response = client.post("/api/detect", files=files)

    assert json_response.status_code == 200
    assert process_calls == 1
    payload = json_response.json()
    assert payload["filename"] == "blank.jpg"
    assert payload["conf"] == traffic_app.DEFAULT_MODEL_CONFIDENCE
    request_received_at = datetime.fromisoformat(
        payload["request_received_at"].replace("Z", "+00:00")
    )
    assert request_received_at.utcoffset().total_seconds() == 0
    assert payload["processing_duration_ms"] >= 0
    assert payload["image_size"] == {"width": 64, "height": 64}
    assert list(payload["counts"]) == ["bus", "car", "tram"]
    assert payload["total"] == sum(payload["counts"].values())
    assert len(json_response.headers["X-Model-SHA256"]) == 64

    image_response = client.post("/api/detect/image?conf=0.25", files=files)

    assert image_response.status_code == 200
    assert process_calls == 2
    assert image_response.headers["content-type"] == "application/json"
    assert len(image_response.headers["X-Model-SHA256"]) == 64
    image_payload = image_response.json()
    assert image_payload["filename"] == "blank.jpg"
    assert image_payload["conf"] == 0.25
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
