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


def test_cross_class_filter_is_sent_to_analysis_and_training_requests() -> None:
    javascript = (PROJECT_ROOT / "ui/assets/app-v2.js").read_text(encoding="utf-8")

    assert "...crossClassRequestOptions()" in javascript
    assert "Object.entries(crossClassRequestOptions())" in javascript
    assert 'cross_class_dedup: "0"' in javascript
    assert 'cross_class_dedup: "1"' in javascript
    assert 'options.cross_class_iou_threshold = threshold' in javascript


def test_cross_class_filter_ui_texts_are_translated() -> None:
    translations = json.loads(
        (PROJECT_ROOT / "ui/assets/i18n/et.json").read_text(encoding="utf-8")
    )

    assert translations["upload.cross_class_dedup"]
    assert translations["upload.cross_class_iou_label"]
    assert translations["results.cross_class_dedup"]
    assert translations["results.cross_class_iou"]
