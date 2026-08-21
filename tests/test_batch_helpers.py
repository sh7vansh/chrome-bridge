"""Unit tests for Compound Subroutine Patterns and High-Level Batch Helpers."""
import pytest
from unittest.mock import MagicMock
from chrome_sdk import Chrome, Tab, ElementHandle


def test_fill_form_standard_fields():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)
    
    # Mock find_input / find to return element handles
    tab.find_input = MagicMock(side_effect=lambda name, *args, **kwargs: ElementHandle(tab=tab, target=f"input_{name}"))
    tab.type = MagicMock()
    tab.select = MagicMock()
    tab.press_key = MagicMock()

    form_data = {
        "Full Name": "Alice Smith",
        "Email": "alice@example.com",
    }
    
    res = tab.fill_form(form_data, submit=None)
    assert res["success"] is True
    assert res["filled"] == 2
    assert res["submitted"] is False

    assert tab.find_input.call_count == 2
    tab.find_input.assert_any_call("Full Name", timeout=1.0)
    tab.find_input.assert_any_call("Email", timeout=1.0)


def test_fill_form_with_checkbox_and_submit():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)

    name_handle = ElementHandle(tab=tab, target="[#1]")
    name_handle.type = MagicMock()

    agree_handle = ElementHandle(tab=tab, target="[#2]")
    agree_handle.eval_js = MagicMock(return_value=False)
    agree_handle.click = MagicMock()

    submit_btn = ElementHandle(tab=tab, target="[#3]")
    submit_btn.click = MagicMock()

    def mock_find_input(k, *args, **kwargs):
        if k == "Username":
            return name_handle
        elif k == "I agree":
            return agree_handle
        return ElementHandle(tab=tab, target=k)

    tab.find_input = MagicMock(side_effect=mock_find_input)
    tab.find_button = MagicMock(return_value=submit_btn)

    res = tab.fill_form(
        {"Username": "bob123", "I agree": True},
        submit="Register"
    )

    assert res["success"] is True
    assert res["filled"] == 2
    assert res["submitted"] is True

    name_handle.type.assert_called_once_with("bob123", clear=True)
    agree_handle.click.assert_called_once()
    tab.find_button.assert_called_once_with("Register", timeout=1.0)
    submit_btn.click.assert_called_once()


def test_extract_items():
    client = MagicMock()
    client.call.return_value = {
        "result": [
            {"title": "First Article", "url": "https://example.com/1", "author": "John"},
            {"title": "Second Article", "url": "https://example.com/2", "author": "Jane"},
        ]
    }
    tab = Tab(tab_id=1, client=client)

    items = tab.extract_items(
        container_selector="article.post",
        fields={"title": "h2.title", "url": "a@href", "author": ".author-name"}
    )

    assert len(items) == 2
    assert items[0]["title"] == "First Article"
    assert items[0]["url"] == "https://example.com/1"
    assert items[1]["title"] == "Second Article"
    assert client.call.call_count == 1
    # Check JS code evaluates container and field query
    call_args = client.call.call_args_list[0]
    assert call_args[0][0] == "execute_script"
    assert "article.post" in call_args[0][1]["code"]


def test_search_shortcut():
    client = MagicMock()
    client.call.side_effect = [
        {"result": None},  # eval_js execute_script for beforeunload
        {"url": "https://www.google.com/search?q=Python+MCP", "tabId": 1},  # navigate
    ]
    tab = Tab(tab_id=1, client=client)

    res = tab.search("Python MCP", engine="google")
    assert "google.com/search" in res.get("url", "")
    assert client.call.call_count == 2
    assert client.call.call_args_list[1][0] == ("navigate", {"url": "https://www.google.com/search?q=Python+MCP", "tabId": 1})


def test_chrome_proxies_batch_helpers():
    client = MagicMock()
    client.call.side_effect = [
        # list_tabs response for active_tab
        [{"id": 1, "title": "Home", "url": "https://example.com", "active": True}],
        # eval_js response
        {"result": None},
        # navigate response
        {"url": "https://duckduckgo.com/?q=test", "tabId": 1},
    ]
    chrome = Chrome(client=client)
    res = chrome.search("test", engine="duckduckgo")
    assert "duckduckgo.com" in res.get("url", "")
