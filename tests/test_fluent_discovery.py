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


def test_element_handle_properties():
    client = MagicMock()
    client.call.side_effect = [
        {"text": "Extracted Button Text"},
        {"value": "https://example.com/item"},
    ]
    tab = Tab(tab_id=1, client=client)
    handle = ElementHandle(tab=tab, target="[#5]", tag_name="a", role="link")

    assert handle.text == "Extracted Button Text"
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


def test_find_timeout_raises_element_not_found_error():
    client = MagicMock()
    # Mock eval_js returning None (not found)
    client.call.return_value = None
    tab = Tab(tab_id=1, client=client)

    with pytest.raises(ElementNotFoundError) as exc_info:
        tab.find_text("Nonexistent Element", timeout=0.05)

    assert "Nonexistent Element" in str(exc_info.value)


def test_chrome_proxies_fluent_finders():
    client = MagicMock()
    client.call.side_effect = [
        # list_tabs response for active_tab
        [{"id": 1, "title": "Home", "url": "https://example.com", "active": True}],
        # eval_js response
        {
            "selector": '[data-cbridge-id="cb_99"]',
            "tagName": "button",
            "role": "button",
            "text": "Submit Form",
        },
    ]
    chrome = Chrome(client=client)
    btn = chrome.find_button("Submit Form")

    assert isinstance(btn, ElementHandle)
    assert btn.target == '[data-cbridge-id="cb_99"]'
