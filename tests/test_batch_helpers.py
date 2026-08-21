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


def test_fill_form_with_radio_buttons():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)

    radio_handle = ElementHandle(tab=tab, target="[#15]", tag_name="input", role="radio")
    radio_handle.eval_js = MagicMock(return_value={"isRadio": True, "checked": False})
    radio_handle.click = MagicMock()
    radio_handle.type = MagicMock()

    tab.find_input = MagicMock(return_value=radio_handle)

    res = tab.fill_form({"Delivery Option": "Express Delivery"})
    assert res["success"] is True
    assert res["filled"] == 1
    radio_handle.click.assert_called_once()
    radio_handle.type.assert_not_called()


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


def test_extract_items_complex_attributes():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)

    client.call.return_value = {
        "result": [
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

    # Verify generated JS contains all selector mappings
    call_args = client.call.call_args_list[0]
    code = call_args[0][1]["code"]
    assert "div.product-card" in code
    assert "img.thumbnail@src" in code
    assert "@data-sku" in code


def test_extract_items_text_keyword_does_not_query_selector():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)
    client.call.return_value = {"result": [{"content": "Hello World"}]}

    tab.extract_items("div.message", fields={"content": "text"})
    call_args = client.call.call_args_list[0]
    code = call_args[0][1]["code"]
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


