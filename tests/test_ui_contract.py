from __future__ import annotations

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_cross_class_filter_controls_and_result_metadata_are_present() -> None:
    html = (PROJECT_ROOT / "ui/index.html").read_text(encoding="utf-8")

    assert 'id="crossClassDedupInput"' in html
    assert 'id="crossClassThresholdGroup"' in html
    assert 'id="crossClassIouInput"' in html
    assert 'id="resultCrossClassDedup"' in html
    assert 'id="resultCrossClassIouRow"' in html
    assert 'id="profileSelect"' in html
    assert 'id="resultProfile"' in html
    assert 'id="detectionAreaInput"' in html
    assert 'id="detectionAreaRow"' in html
    assert 'id="detectionAreaOverlay"' in html
    assert 'id="liveTab"' in html
    assert 'id="liveProfileSelect"' in html
    assert 'id="liveAnnotatedImage"' in html
    assert 'id="liveDetectionAreaOverlay"' in html
    assert 'id="liveCandidateButton"' in html


def test_cross_class_filter_is_sent_to_analysis_and_training_requests() -> None:
    javascript = (PROJECT_ROOT / "ui/assets/app-v2.js").read_text(encoding="utf-8")

    assert "...crossClassRequestOptions()" in javascript
    assert "Object.entries(crossClassRequestOptions())" in javascript
    assert 'cross_class_dedup: "0"' in javascript
    assert 'cross_class_dedup: "1"' in javascript
    assert 'options.cross_class_iou_threshold = threshold' in javascript
    assert "profile: elements.profileSelect.value" in javascript
    assert 'body.append("profile", elements.profileSelect.value)' in javascript
    assert 'live-frame?' in javascript
    assert 'configureDetectionAreaOverlay(elements.liveDetectionAreaOverlay' in javascript
    assert 'viewer_id: state.live.viewerId' in javascript
    assert 'state.live.viewerId = crypto.randomUUID()' in javascript
    assert 'poll_interval_seconds: elements.liveIntervalInput.value' in javascript
    assert '"/training-pool/live-frame"' in javascript
    assert '!state.live.paused || !state.live.result' in javascript


def test_cross_class_filter_ui_texts_are_translated() -> None:
    translations = json.loads(
        (PROJECT_ROOT / "ui/assets/i18n/et.json").read_text(encoding="utf-8")
    )

    assert translations["upload.cross_class_dedup"]
    assert translations["upload.cross_class_iou_label"]
    assert translations["results.cross_class_dedup"]
    assert translations["results.cross_class_iou"]
    assert translations["upload.profile_label"]
    assert translations["upload.show_detection_area"]
    assert translations["results.profile"]
    assert translations["classes.van-truck"]
    assert translations["nav.live"]
    assert translations["live.start"]


def test_live_monitoring_requires_a_positive_integer_interval() -> None:
    javascript = (PROJECT_ROOT / "ui/assets/app-v2.js").read_text(encoding="utf-8")

    assert 'profile?.capture_interval_seconds == null ? ""' in javascript
    assert 'preventInvalidLiveIntervalKey' in javascript
    assert '["-", "+", ".", ",", "e", "E"]' in javascript
    assert '/^[1-9]\\d*$/.test(value)' in javascript
    assert 'input.value = input.dataset.lastValid || ""' in javascript
    assert 'Number.isInteger(value)' in javascript
    assert '!validLiveInterval()' in javascript


def test_user_role_opens_live_view_and_hides_training_controls() -> None:
    javascript = (PROJECT_ROOT / "ui/assets/app-v2.js").read_text(encoding="utf-8")

    assert 'state.user?.role === "ADMIN"' in javascript
    assert 'switchView(isAdmin() ? "analysis" : "live")' in javascript
    assert 'elements.trainingTab.classList.toggle("hidden", !admin)' in javascript
    assert 'elements.candidateButton.classList.toggle("hidden", !admin)' in javascript
    assert '!isAdmin() || !state.live.paused || !state.live.result' in javascript
