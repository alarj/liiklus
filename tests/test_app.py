from __future__ import annotations

import struct
from io import BytesIO

import cv2
import numpy as np
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.datastructures import Headers, UploadFile

import app as traffic_app


@pytest.fixture(scope="module")
def client() -> TestClient:
    with TestClient(traffic_app.app) as test_client:
        yield test_client


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


def test_detection_endpoints_with_synthetic_image(client: TestClient) -> None:
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    data = _encode(image, ".jpg")
    files = {"file": ("blank.jpg", data, "image/jpeg")}

    json_response = client.post("/api/detect", files=files)

    assert json_response.status_code == 200
    payload = json_response.json()
    assert payload["image_size"] == {"width": 64, "height": 64}
    assert list(payload["counts"]) == ["bus", "car", "tram"]
    assert payload["total"] == sum(payload["counts"].values())
    assert len(json_response.headers["X-Model-SHA256"]) == 64

    image_response = client.post("/api/detect/image", files=files)

    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/jpeg"
    assert len(image_response.headers["X-Model-SHA256"]) == 64
    assert image_response.content.startswith(b"\xff\xd8")
