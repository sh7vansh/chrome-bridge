"""Unit tests for Compound Subroutine Patterns and High-Level Batch Helpers."""
import pytest
from unittest.mock import MagicMock
from chrome_sdk import Chrome, Tab, ElementHandle


def test_fill_form_standard_fields():
    client = MagicMock()
    client.call.return_value = {"success": True, "filled": 2, "submitted": False}
    tab = Tab(tab_id=1, client=client)

    form_data = {
        "Full Name": "Alice Smith",
        "Email": "alice@example.com",
    }
    
    res = tab.fill_form(form_data, submit=None)
    assert res["success"] is True
    assert res["filled"] == 2
    assert res["submitted"] is False

    client.call.assert_called_once_with("fill_form", {
        "mapping": form_data,
        "submit": None,
        "tabId": 1,
    })


def test_fill_form_with_checkbox_and_submit():
    client = MagicMock()
    client.call.return_value = {"success": True, "filled": 2, "submitted": True}
    tab = Tab(tab_id=1, client=client)

    res = tab.fill_form(
        {"Username": "bob123", "I agree": True},
        submit="Register"
    )

    assert res["success"] is True
    assert res["filled"] == 2
    assert res["submitted"] is True

    client.call.assert_called_once_with("fill_form", {
        "mapping": {"Username": "bob123", "I agree": True},
        "submit": "Register",
        "tabId": 1,
    })


def test_fill_form_with_radio_buttons():
    client = MagicMock()
    client.call.return_value = {"success": True, "filled": 1, "submitted": False}
    tab = Tab(tab_id=1, client=client)

    res = tab.fill_form({"Delivery Option": "Express Delivery"})
    assert res["success"] is True
    assert res["filled"] == 1
    client.call.assert_called_once_with("fill_form", {
        "mapping": {"Delivery Option": "Express Delivery"},
        "submit": None,
        "tabId": 1,
    })


def test_extract_items():
    client = MagicMock()
    client.call.return_value = {
        "items": [
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
    # Check structured Action RPC call
    call_args = client.call.call_args_list[0]
    assert call_args[0][0] == "extract_items"
    assert call_args[0][1]["item_selector"] == "article.post"
    assert call_args[0][1]["fields"] == {"title": "h2.title", "url": "a@href", "author": ".author-name"}
    assert call_args[0][1]["tabId"] == 1


def test_extract_items_complex_attributes():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)

    client.call.return_value = {
        "items": [
            {
                "title": "Pro Headphones",
                "image": "https://example.com/img1.jpg",
                "sku": "SKU-9901",
                "aria": "Add Pro Headphones to cart",
                "id": "prod-1",
            },
            {
                "title": "Wireless Mouse",
                "image": "https://example.com/img2.jpg",
                "sku": "SKU-9902",
                "aria": "Add Wireless Mouse to cart",
                "id": "prod-2",
            },
        ]
    }

    fields = {
        "title": "h3.prod-title",
        "image": "img.thumbnail@src",
        "sku": "@data-sku",
        "aria": "button.buy@aria-label",
        "id": "self@id",
    }
    items = tab.extract_items("div.product-card", fields=fields)

    assert len(items) == 2
    assert items[0]["sku"] == "SKU-9901"
    assert items[0]["image"] == "https://example.com/img1.jpg"
    assert items[0]["aria"] == "Add Pro Headphones to cart"
    assert items[0]["id"] == "prod-1"

    # Verify structured Action RPC payload contains all selector mappings
    call_args = client.call.call_args_list[0]
    assert call_args[0][0] == "extract_items"
    assert call_args[0][1]["item_selector"] == "div.product-card"
    assert call_args[0][1]["fields"] == fields

    # Verify DomBatchSynthesizer JS template compilation
    from chrome_sdk import DomBatchSynthesizer
    js_code = DomBatchSynthesizer.compile_extract_items_js("div.product-card", fields)
    assert "div.product-card" in js_code
    assert "img.thumbnail@src" in js_code
    assert "@data-sku" in js_code


def test_extract_items_text_keyword_does_not_query_selector():
    from chrome_sdk import DomBatchSynthesizer
    code = DomBatchSynthesizer.compile_extract_items_js("div.message", {"content": "text"})
    assert "sel !== 'text'" in code or "sel.toLowerCase() !== 'text'" in code or "toLowerCase() === 'text'" in code




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
        {"result": None},  # eval_js execute_script for beforeunload
        {"url": "https://duckduckgo.com/?q=test", "tabId": None},  # navigate
    ]
    chrome = Chrome(client=client)
    res = chrome.search("test", engine="duckduckgo")
    assert "duckduckgo.com" in res.get("url", "")
    assert client.call.call_count == 2
    # Verify no list_tabs was called
    actions_called = [c[0][0] for c in client.call.call_args_list]
    assert "list_tabs" not in actions_called
    assert client.call.call_args_list[1][0] == ("navigate", {"url": "https://duckduckgo.com/?q=test", "tabId": None})


def test_dom_batch_synthesizer_search_urls():
    from chrome_sdk import DomBatchSynthesizer
    assert "google.com/search?q=hello+world" in DomBatchSynthesizer.compile_search_url("hello world", "google")
    assert "duckduckgo.com/?q=python" in DomBatchSynthesizer.compile_search_url("python", "ddg")
    assert "youtube.com/results?search_query=music" in DomBatchSynthesizer.compile_search_url("music", "yt")
    assert "github.com/search?q=repo" in DomBatchSynthesizer.compile_search_url("repo", "gh")
    assert "custom.org/find?query=test" in DomBatchSynthesizer.compile_search_url("test", "https://custom.org/find?query={query}")


def test_dom_batch_synthesizer_js_compilation():
    from chrome_sdk import DomBatchSynthesizer

    extract_js = DomBatchSynthesizer.compile_extract_items_js(".card", {"title": "h2", "link": "a@href"})
    assert ".card" in extract_js
    assert "a@href" in extract_js
    assert "getAttribute" in extract_js

    query_all_js = DomBatchSynthesizer.compile_query_all_js("li.item")
    assert "li.item" in query_all_js
    assert "__cb_is_visible" in query_all_js

    find_css_js = DomBatchSynthesizer.compile_find_css_js("#submit-btn")
    assert "#submit-btn" in find_css_js

    text_finder_js = DomBatchSynthesizer.compile_text_finder_js("Sign In", exact=True)
    assert "Sign In" in text_finder_js
    assert "qLower" in text_finder_js

    input_finder_js = DomBatchSynthesizer.compile_input_finder_js("Search queries")
    assert "Search queries" in input_finder_js
    assert "placeholder" in input_finder_js

    btn_finder_js = DomBatchSynthesizer.compile_button_finder_js("Submit Order")
    assert "Submit Order" in btn_finder_js


