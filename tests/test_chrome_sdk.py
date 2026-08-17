"""Unit tests for Chrome Python SDK, Polymorphic Locators, and Tab handles."""
import pytest
from unittest.mock import MagicMock
from chrome_sdk import (
    Chrome,
    Tab,
    normalize_locator,
    ChromeBridgeError,
    ElementNotFoundError,
    ActionInterceptionError,
    NavigationTimeoutError,
)


def test_normalize_locator():
    assert normalize_locator(14) == {"type": "ref", "refId": 14}
    assert normalize_locator("[#14]") == {"type": "ref", "refId": 14}
    assert normalize_locator("#14") == {"type": "ref", "refId": 14}
    assert normalize_locator("ref:14") == {"type": "ref", "refId": 14}
    assert normalize_locator("button.submit") == {"type": "css", "selector": "button.submit"}
    assert normalize_locator("#main-nav > li:first-child") == {"type": "css", "selector": "#main-nav > li:first-child"}


def test_tab_repr():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client, title="GitHub", url="https://github.com", active=True)
    assert repr(tab) == '<Tab id=1 title="GitHub" url="https://github.com" active=True>'


def test_tab_actions_dispatch_correct_payloads():
    client = MagicMock()
    client.call.return_value = {"status": "ok", "action": "click", "target": "[#14]"}

    tab = Tab(tab_id=2, client=client)
    res = tab.click(14)

    client.call.assert_called_once_with(
        "click",
        {"target": {"type": "ref", "refId": 14}, "button": "left", "count": 1, "tabId": 2},
        timeout=15.0
    )
    assert res["status"] == "ok"


def test_tab_type_action():
    client = MagicMock()
    client.call.return_value = {"status": "ok", "action": "type", "target": "[#3]"}

    tab = Tab(tab_id=1, client=client)
    tab.type("[#3]", "Hello World", clear=True, press_enter=True)

    client.call.assert_called_once_with(
        "type",
        {
            "target": {"type": "ref", "refId": 3},
            "text": "Hello World",
            "clear": True,
            "pressEnter": True,
            "tabId": 1,
        },
        timeout=15.0
    )


def test_chrome_singleton_delegates_to_active_tab():
    client = MagicMock()
    client.call.side_effect = [
        # list_tabs response
        [{"id": 10, "title": "Active Tab", "url": "https://example.com", "active": True}],
        # snapshot response
        {"snapshot": 'PAGE: "Active Tab"\n- button [#1] "Submit"', "totalInteractive": 1},
    ]

    chrome = Chrome(client=client)
    snapshot = chrome.snapshot()

    assert "- button [#1]" in snapshot
    assert client.call.call_count == 2
