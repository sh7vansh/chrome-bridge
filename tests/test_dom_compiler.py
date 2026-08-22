"""Unit tests for the deep DomCompiler module, JavaScript synthesis, and error decoding."""

import pytest
from chrome_bridge.compiler import DomCompiler
from chrome_bridge.exceptions import (
    ElementNotFoundError,
    ActionInterceptionError,
    NavigationTimeoutError,
    ChromeBridgeError,
)


def test_dom_compiler_search_url_generation():
    assert DomCompiler.compile_search_url("python 3.11", engine="google") == "https://www.google.com/search?q=python+3.11"
    assert DomCompiler.compile_search_url("chrome bridge", engine="github") == "https://github.com/search?q=chrome+bridge"
    assert DomCompiler.compile_search_url("music", engine="yt") == "https://www.youtube.com/results?search_query=music"
    assert DomCompiler.compile_search_url("test", engine="https://custom.com/find") == "https://custom.com/find?q=test"


def test_dom_compiler_extract_items_js():
    js = DomCompiler.compile_extract_items_js("tr.row", {"title": "td.title", "url": "a@href"})
    assert 'const containerSelector = "tr.row";' in js
    assert 'const fields = {"title": "td.title", "url": "a@href"};' in js
    assert "document.querySelectorAll(containerSelector)" in js


def test_dom_compiler_finder_templates():
    js_text = DomCompiler.compile_text_finder_js("Sign In", exact=True)
    assert 'const query = "Sign In";' in js_text
    assert "const exact = true;" in js_text

    js_input = DomCompiler.compile_input_finder_js("Email Address")
    assert 'const query = "Email Address";' in js_input
    assert "placeholder" in js_input
    assert "aria-label" in js_input

    js_btn = DomCompiler.compile_button_finder_js("Submit")
    assert 'const query = "Submit";' in js_btn
    assert "button, input[type=\"button\"]" in js_btn


def test_dom_compiler_decode_error_element_not_found():
    err_payload = {
        "code": "ELEMENT_NOT_FOUND",
        "target": "[#99]",
        "tabId": 3,
        "stale": True,
        "suggestions": [{"ref": 12, "role": "button", "name": "Log In"}],
        "url": "https://app.com",
    }
    with pytest.raises(ElementNotFoundError) as exc_info:
        DomCompiler.decode_error(err_payload, params={"target": "[#99]", "tabId": 3}, auto_snapshot="PAGE: App")

    exc = exc_info.value
    assert exc.target == "[#99]"
    assert exc.tab_id == 3
    assert exc.stale is True
    assert exc.auto_snapshot == "PAGE: App"
    assert "[#12] (button 'Log In')" in str(exc)


def test_dom_compiler_decode_error_action_intercepted():
    err_payload = {
        "code": "ACTION_INTERCEPTED",
        "target": "[#5]",
        "interceptorTag": "div.modal-backdrop",
        "interceptorRef": 88,
        "interceptorDesc": "Cookie Banner",
        "tabId": 2,
    }
    with pytest.raises(ActionInterceptionError) as exc_info:
        DomCompiler.decode_error(err_payload, params={"target": "[#5]", "tabId": 2})

    exc = exc_info.value
    assert exc.target == "[#5]"
    assert exc.tab_id == 2
    assert exc.interceptor_ref == 88
    assert "[#88] (Cookie Banner)" in str(exc)


def test_dom_compiler_decode_error_timeout():
    err_payload = {
        "code": "TIMEOUT",
        "target": "[#header]",
        "timeout": 5.0,
        "url": "https://slow.com",
        "readyState": "interactive",
        "domState": "loading",
        "tabId": 1,
    }
    with pytest.raises(NavigationTimeoutError) as exc_info:
        DomCompiler.decode_error(err_payload, params={"target": "[#header]", "tabId": 1})

    exc = exc_info.value
    assert exc.timeout == 5.0
    assert exc.ready_state == "interactive"
    assert "Timed out after 5.0s" in str(exc)


def test_dom_compiler_in_page_synchronizer():
    """Verify in-page event-driven DOM synchronizer with MutationObserver."""
    js_text = DomCompiler.compile_text_finder_js("Checkout", exact=False, timeout=2.0)
    assert "__cb_wait_for" in js_text
    assert "MutationObserver" in js_text
    assert "2000" in js_text
    assert "requestAnimationFrame" in js_text

    js_css = DomCompiler.compile_find_css_js("button.primary", timeout=3.5)
    assert "__cb_wait_for" in js_css
    assert "3500" in js_css


def test_dom_compiler_compile_fill_form_js():
    """Verify single-roundtrip batch form compiler."""
    mapping = {
        "First Name": "John",
        "Subscribe": True,
        "Plan": "pro",
    }
    js_form = DomCompiler.compile_fill_form_js(mapping, submit="Register")
    assert 'const mapping = {"First Name": "John", "Subscribe": true, "Plan": "pro"};' in js_form
    assert 'const submit = "Register";' in js_form
    assert "findField" in js_form
    assert "filledCount++" in js_form
    assert "dispatchEvent(new Event('input'" in js_form
    assert "dispatchEvent(new Event('change'" in js_form


def test_dom_compiler_unified_discovery_helpers():
    """Verify compiler JavaScript templates contain unified accessible name and computed role helpers."""
    from chrome_bridge.compiler import _DISCOVERY_HELPER_JS
    assert "__cb_is_visible" in _DISCOVERY_HELPER_JS
    assert "__cb_get_accessible_name" in _DISCOVERY_HELPER_JS
    assert "__cb_get_computed_role" in _DISCOVERY_HELPER_JS
    assert "__cb_tag" in _DISCOVERY_HELPER_JS
    assert "aria-labelledby" in _DISCOVERY_HELPER_JS
    assert "aria-label" in _DISCOVERY_HELPER_JS


def test_dom_compiler_action_rpc_compilation():
    """Verify structured Action RPC compilation and parameter normalization."""
    rpc = DomCompiler.compile_action_rpc("click", target=14, button="right", count=2)
    assert rpc["action"] == "click"
    assert rpc["params"]["target"] == {"type": "ref", "refId": 14}
    assert rpc["params"]["button"] == "right"
    assert rpc["params"]["count"] == 2

    css_rpc = DomCompiler.compile_action_rpc("type", target="#input", text="hello")
    assert css_rpc["action"] == "type"
    assert css_rpc["params"]["target"] == {"type": "css", "selector": "#input"}
    assert css_rpc["params"]["text"] == "hello"


def test_dom_compiler_media_control_compilation():
    """Verify media control fast-path JavaScript compilation."""
    status_js = DomCompiler.compile_media_control("status")
    assert "findMediaElement" in status_js
    assert "playbackState" in status_js

    toggle_js = DomCompiler.compile_media_control("toggle")
    assert "media.paused" in toggle_js
    assert "media.play()" in toggle_js

    seek_js = DomCompiler.compile_media_control("seek", seconds=15.0)
    assert "v.currentTime += 15.0" in seek_js

    vol_js = DomCompiler.compile_media_control("set_volume", volume=0.8)
    assert "v.volume = 0.8" in vol_js



