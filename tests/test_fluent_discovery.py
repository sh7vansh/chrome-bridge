"""Unit tests for Fluent In-Script Element Discovery and ElementHandle Action API."""
import pytest
from unittest.mock import MagicMock
from chrome_sdk import (
    Chrome,
    Tab,
    ElementHandle,
    ElementNotFoundError,
)


def test_element_handle_chaining():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)
    
    handle = ElementHandle(tab=tab, target="[#10]", tag_name="button", role="button", text="Submit")
    
    # Click chaining
    res = handle.click()
    assert res is handle
    client.call.assert_called_with(
        "click",
        {"target": {"type": "ref", "refId": 10}, "button": "left", "count": 1, "tabId": 1},
        timeout=15.0,
    )
    
    # Type chaining
    res2 = handle.type("test value", clear=True, press_enter=True)
    assert res2 is handle
    client.call.assert_called_with(
        "type",
        {"target": {"type": "ref", "refId": 10}, "text": "test value", "clear": True, "pressEnter": True, "tabId": 1},
        timeout=15.0,
    )

    # Select chaining
    res3 = handle.select("option_1")
    assert res3 is handle
    client.call.assert_called_with(
        "select_option",
        {"target": {"type": "ref", "refId": 10}, "value": "option_1", "tabId": 1},
    )

    # Hover chaining
    res4 = handle.hover()
    assert res4 is handle
    client.call.assert_called_with(
        "hover",
        {"target": {"type": "ref", "refId": 10}, "tabId": 1},
    )


def test_element_handle_scroll_into_view_and_eval_js():
    client = MagicMock()
    client.call.side_effect = [
        {"result": None},  # scroll_into_view eval_js
        {"status": "ok"},  # hover
        {"status": "ok"},  # click
        {"result": "Custom Value"},  # eval_js
    ]
    tab = Tab(tab_id=1, client=client)
    handle = ElementHandle(tab=tab, target="[#12]", tag_name="button", role="button")

    # Multi-method chaining
    res = handle.scroll_into_view().hover().click()
    assert res is handle
    assert client.call.call_count == 3

    # Direct element eval_js
    custom_val = handle.eval_js("this.getAttribute('data-custom')")
    assert custom_val == {"result": "Custom Value"} or custom_val == "Custom Value"


def test_element_handle_properties():
    client = MagicMock()
    client.call.side_effect = [
        {"text": "Extracted Button Text"},
        {"value": "https://example.com/item"},
    ]
    tab = Tab(tab_id=1, client=client)
    handle = ElementHandle(tab=tab, target="[#5]", tag_name="a", role="link")

    assert handle.text == "Extracted Button Text"
    assert handle.tag_name == "a"
    assert handle.role == "link"
    assert handle.get_attribute("href") == "https://example.com/item"
    assert repr(handle).startswith("<ElementHandle")


def test_tab_find_text():
    client = MagicMock()
    # Mock eval_js returning element discovery info
    client.call.return_value = {
        "selector": '[data-cbridge-id="cb_1_abc"]',
        "tagName": "button",
        "role": "button",
        "text": "Sign In",
    }
    tab = Tab(tab_id=1, client=client)
    btn = tab.find_text("Sign In")

    assert isinstance(btn, ElementHandle)
    assert btn.target == '[data-cbridge-id="cb_1_abc"]'
    assert btn.tab is tab


def test_tab_find_input():
    client = MagicMock()
    client.call.return_value = {
        "selector": '[data-cbridge-id="cb_2_def"]',
        "tagName": "input",
        "role": "textbox",
        "text": "",
        "placeholder": "Email address",
    }
    tab = Tab(tab_id=2, client=client)
    inp = tab.find_input("Email address")

    assert isinstance(inp, ElementHandle)
    assert inp.target == '[data-cbridge-id="cb_2_def"]'


def test_tab_find_button():
    client = MagicMock()
    client.call.return_value = {
        "selector": '[data-cbridge-id="cb_3_ghi"]',
        "tagName": "button",
        "role": "button",
        "text": "Checkout",
    }
    tab = Tab(tab_id=1, client=client)
    btn = tab.find_button("Checkout")

    assert isinstance(btn, ElementHandle)
    assert btn.target == '[data-cbridge-id="cb_3_ghi"]'


def test_tab_find_polymorphic():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)

    # Numeric ref-id
    h1 = tab.find(14)
    assert isinstance(h1, ElementHandle)
    assert h1.target == 14

    # Bracket ref-id
    h2 = tab.find("[#14]")
    assert isinstance(h2, ElementHandle)
    assert h2.target == "[#14]"


def test_tab_query_all():
    client = MagicMock()
    client.call.return_value = [
        {"selector": '[data-cbridge-id="cb_10"]', "tagName": "li", "role": "listitem", "text": "Item 1"},
        {"selector": '[data-cbridge-id="cb_11"]', "tagName": "li", "role": "listitem", "text": "Item 2"},
    ]
    tab = Tab(tab_id=1, client=client)
    items = tab.query_all("ul.results > li")

    assert len(items) == 2
    assert all(isinstance(item, ElementHandle) for item in items)
    assert items[0].target == '[data-cbridge-id="cb_10"]'
    assert items[1].target == '[data-cbridge-id="cb_11"]'


def test_tab_query_all_various_response_structures():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)

    # 1. Dict payload wrapping results with mixed selector/ref/target fields
    client.call.return_value = {
        "result": [
            {"selector": '[data-cbridge-id="cb_1"]', "tagName": "div", "role": "button", "text": "Card 1"},
            {"ref": "#2", "tagName": "div", "role": "button", "text": "Card 2"},
            {"target": "[#3]", "tagName": "div", "role": "button", "text": "Card 3"},
        ]
    }
    items = tab.query_all("div.card")
    assert len(items) == 3
    assert items[0].target == '[data-cbridge-id="cb_1"]'
    assert items[1].target == "#2"
    assert items[2].target == "[#3]"

    # 2. None / invalid result returns empty list cleanly
    client.call.return_value = None
    assert tab.query_all("nonexistent") == []

    client.call.return_value = {"result": "not a list"}
    assert tab.query_all("nonexistent") == []



def test_find_timeout_raises_element_not_found_error():
    client = MagicMock()
    # Mock eval_js returning None (not found)
    client.call.return_value = None
    tab = Tab(tab_id=1, client=client)

    with pytest.raises(ElementNotFoundError) as exc_info:
        tab.find_text("Nonexistent Element", timeout=0.05)

    assert "Nonexistent Element" in str(exc_info.value)


def test_chrome_fluent_actions_single_roundtrip_without_list_tabs():
    client = MagicMock()
    client.call.return_value = {
        "selector": '[data-cbridge-id="cb_99"]',
        "tagName": "button",
        "role": "button",
        "text": "Submit Form",
    }
    chrome = Chrome(client=client)
    btn = chrome.find_button("Submit Form")

    assert isinstance(btn, ElementHandle)
    assert btn.target == '[data-cbridge-id="cb_99"]'
    # Must NOT have called list_tabs - single roundtrip directly on active context
    assert client.call.call_count == 1
    action_called, params = client.call.call_args[0][0], client.call.call_args[0][1]
    assert action_called == "execute_script"
    assert params.get("tabId") is None


def test_tab_find_allocates_remaining_deadline_across_fallbacks():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)

    tab.find_button = MagicMock(side_effect=ElementNotFoundError("target", tab_id=1))
    tab.find_input = MagicMock(side_effect=ElementNotFoundError("target", tab_id=1))
    tab.find_text = MagicMock(return_value=ElementHandle(tab=tab, target="[#9]"))

    h = tab.find("Sign Up Here", timeout=1.5)
    assert h.target == "[#9]"

    # Must allocate remaining budget (> 1.0s) rather than a rigid 1/3 (0.5s)
    args, kwargs = tab.find_text.call_args
    passed_timeout = kwargs.get("timeout")
    assert passed_timeout > 1.0


def test_poll_find_sleep_interval():
    from unittest.mock import patch

    client = MagicMock()
    tab = Tab(tab_id=1, client=client)

    sleep_calls = []
    with patch("time.sleep", side_effect=lambda s: sleep_calls.append(s)):
        with pytest.raises(ElementNotFoundError):
            tab._poll_find(lambda: None, query="missing", timeout=0.25)

    assert len(sleep_calls) > 0
    # Spec 035 asks for 100ms (0.1s) polling intervals
    assert all(abs(s - 0.1) < 1e-3 for s in sleep_calls)


