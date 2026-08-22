"""Unit tests for Chrome Python SDK, Polymorphic Locators, and Tab handles."""
import pytest
from unittest.mock import MagicMock
from chrome_sdk import (
    Chrome,
    Tab,
    normalize_locator,
    ChromeBridgeError,
    BrowserUnavailableError,
    ElementNotFoundError,
    ActionInterceptionError,
    NavigationTimeoutError,
    ChromeSocketClient,
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


def test_tab_close_on_last_tab_spawns_blank_tab_first():
    client = MagicMock()
    client.call.side_effect = [
        # list_tabs response (only 1 tab remaining)
        [{"id": 2, "url": "https://example.com", "title": "Last Tab"}],
        # navigate (newTab: True) response
        {"tabId": 3, "url": "about:blank"},
        # close_tab response
        {"success": True, "closedTabId": 2},
    ]

    tab = Tab(tab_id=2, client=client)
    res = tab.close()

    assert res["success"] is True
    assert client.call.call_count == 3
    assert client.call.call_args_list[0][0] [0] == "list_tabs"
    assert client.call.call_args_list[1][0] == ("navigate", {"url": "about:blank", "newTab": True})
    assert client.call.call_args_list[2][0] == ("close_tab", {"tabId": 2})


def test_tab_close_with_multiple_tabs_does_not_spawn_new_tab():
    client = MagicMock()
    client.call.side_effect = [
        # list_tabs response (2 tabs)
        [
            {"id": 2, "url": "https://example.com", "title": "Tab 1"},
            {"id": 3, "url": "https://google.com", "title": "Tab 2"},
        ],
        # close_tab response
        {"success": True, "closedTabId": 2},
    ]

    tab = Tab(tab_id=2, client=client)
    res = tab.close()

    assert res["success"] is True
    assert client.call.call_count == 2
    assert client.call.call_args_list[0][0] [0] == "list_tabs"
    assert client.call.call_args_list[1][0] == ("close_tab", {"tabId": 2})


def test_tab_close_fallback_on_list_tabs_error():
    client = MagicMock()
    client.call.side_effect = [
        # list_tabs fails
        RuntimeError("Transient error"),
        # direct close_tab fallback
        {"success": True, "closedTabId": 2},
    ]

    tab = Tab(tab_id=2, client=client)
    res = tab.close()

    assert res["success"] is True
    assert client.call.call_count == 2
    assert client.call.call_args_list[0][0] [0] == "list_tabs"
    assert client.call.call_args_list[1][0] == ("close_tab", {"tabId": 2})


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


def test_tab_navigate_neutralizes_beforeunload_and_dispatches_navigation():
    client = MagicMock()
    client.call.side_effect = [
        # eval_js execute_script call
        {"result": None},
        # navigate call
        {"status": "ok", "url": "https://example.com/target", "tabId": 5},
    ]

    tab = Tab(tab_id=5, client=client)
    res = tab.navigate("https://example.com/target")

    assert tab.url == "https://example.com/target"
    assert res["status"] == "ok"
    assert client.call.call_count == 2
    # Verify first call neutralizes beforeunload handlers via execute_script
    first_call = client.call.call_args_list[0]
    assert first_call[0][0] == "execute_script"
    assert "onbeforeunload" in first_call[0][1]["code"]
    assert "stopImmediatePropagation" in first_call[0][1]["code"]
    assert first_call[0][1]["tabId"] == 5

    # Verify second call is navigate
    second_call = client.call.call_args_list[1]
    assert second_call[0][0] == "navigate"
    assert second_call[0][1] == {"url": "https://example.com/target", "tabId": 5}


def test_chrome_singleton_dispatches_single_roundtrip_action():
    client = MagicMock()
    client.call.return_value = {"snapshot": 'PAGE: "Active Tab"\n- button [#1] "Submit"', "totalInteractive": 1}

    chrome = Chrome(client=client)
    snapshot = chrome.snapshot()

    assert "- button [#1]" in snapshot
    # Verifies single-roundtrip optimization (tabId=None) without redundant list_tabs call
    client.call.assert_called_once_with("get_page_content", {"tabId": None, "compact": True}, timeout=15.0)


def test_chrome_active_tab_resolves_scoped_handle():
    client = MagicMock()
    client.call.side_effect = [
        # list_tabs response
        [{"id": 10, "title": "Active Tab", "url": "https://example.com", "active": True}],
        # snapshot response on scoped tab
        {"snapshot": 'PAGE: "Active Tab"\n- button [#1] "Submit"', "totalInteractive": 1},
    ]

    chrome = Chrome(client=client)
    scoped_tab = chrome.active_tab
    assert scoped_tab.id == 10
    snapshot = scoped_tab.snapshot()

    assert "- button [#1]" in snapshot
    assert client.call.call_count == 2


def test_browser_unavailable_error_subclasses_chrome_bridge_error():
    err = BrowserUnavailableError("Browser session is not reachable.")
    assert isinstance(err, ChromeBridgeError)
    assert "not reachable" in str(err)


def test_socket_connection_failure_raises_browser_unavailable_error():
    client = ChromeSocketClient(socket_path="/tmp/nonexistent_test_socket.sock")
    with pytest.raises(BrowserUnavailableError) as exc_info:
        client.connect(retries=1, backoff=0.01)
    
    err_str = str(exc_info.value).lower()
    assert "browser" in err_str
    # Verify zero leakage of internal terms
    for forbidden in ["extension", "socket", "/tmp/", "native-host", "manifest"]:
        assert forbidden not in err_str, f"Forbidden term '{forbidden}' leaked in error message: {err_str}"


def test_default_socket_path_resolution():
    import tempfile
    import os
    from chrome_sdk import DEFAULT_SOCKET_PATH
    expected = os.path.join(tempfile.gettempdir(), "antigravity_chrome_bridge.sock")
    assert DEFAULT_SOCKET_PATH == expected


def test_browser_unavailable_actionable_checklist_zero_leakage():
    from chrome_sdk import DEFAULT_BROWSER_UNAVAILABLE_MSG
    assert "Troubleshooting checklist" in DEFAULT_BROWSER_UNAVAILABLE_MSG
    assert "Ensure Google Chrome" in DEFAULT_BROWSER_UNAVAILABLE_MSG
    assert "setup" in DEFAULT_BROWSER_UNAVAILABLE_MSG
    lower_msg = DEFAULT_BROWSER_UNAVAILABLE_MSG.lower()
    for forbidden in ["extension", "socket", "/tmp/", "native-host", "manifest"]:
        assert forbidden not in lower_msg, f"Forbidden term '{forbidden}' leaked in checklist: {DEFAULT_BROWSER_UNAVAILABLE_MSG}"


def test_manifest_pinned_key_matches_expected_extension_id():
    import json
    import os
    manifest_path = os.path.join(os.path.dirname(__file__), "..", "extension", "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)
    assert "key" in manifest
    assert len(manifest["key"]) > 100

