"""Unit tests for TabMedia fast-path controller and Chrome media integration."""
import pytest
from unittest.mock import MagicMock
from chrome_sdk import Chrome, Tab, TabMedia


def test_tab_media_property_returns_tab_media_instance_and_caches():
    client = MagicMock()
    tab = Tab(tab_id=1, client=client)
    media1 = tab.media
    media2 = tab.media
    assert isinstance(media1, TabMedia)
    assert media1._tab == tab
    assert media1 is media2


def test_chrome_media_property_delegates_to_active_tab():
    client = MagicMock()
    chrome = Chrome(client=client)
    assert isinstance(chrome.media, TabMedia)
    assert chrome.media._tab == chrome


def test_chrome_get_tab_returns_tab_instance():
    client = MagicMock()
    chrome = Chrome(client=client)
    tab = chrome.get_tab(42)
    assert isinstance(tab, Tab)
    assert tab.id == 42
    assert getattr(tab._client, "raw", tab._client) == client


def test_media_status_evaluates_js_and_returns_dict():
    client = MagicMock()
    expected_status = {
        "found": True,
        "paused": False,
        "currentTime": 12.5,
        "duration": 180.0,
        "volume": 0.8,
        "muted": False,
        "title": "Never Gonna Give You Up",
        "artist": "Rick Astley",
        "album": "Whenever You Need Somebody",
        "playbackState": "playing",
    }
    client.call.return_value = expected_status

    tab = Tab(tab_id=1, client=client)
    status = tab.media.status()

    assert status == expected_status
    client.call.assert_called_once()
    call_args = client.call.call_args
    assert call_args[0][0] == "execute_script"
    assert "findMediaElement" in call_args[0][1]["code"]
    assert "navigator.mediaSession" in call_args[0][1]["code"]
    assert call_args[0][1]["tabId"] == 1


def test_media_toggle_evaluates_shadow_traversal_script():
    client = MagicMock()
    client.call.return_value = {"success": True, "action": "paused"}

    chrome = Chrome(client=client)
    res = chrome.media.toggle()

    assert res == {"success": True, "action": "paused"}
    client.call.assert_called_once()
    call_args = client.call.call_args
    assert call_args[0][0] == "execute_script"
    assert "findMediaElement" in call_args[0][1]["code"]
    assert "media.play()" in call_args[0][1]["code"]
    assert "media.pause()" in call_args[0][1]["code"]


def test_media_play_and_pause():
    client = MagicMock()
    client.call.return_value = {"success": True}

    tab = Tab(tab_id=5, client=client)
    res_play = tab.media.play()
    assert res_play == {"success": True}
    call_args_play = client.call.call_args
    assert "findMediaElement" in call_args_play[0][1]["code"]
    assert "v.play()" in call_args_play[0][1]["code"]

    res_pause = tab.media.pause()
    assert res_pause == {"success": True}
    call_args_pause = client.call.call_args
    assert "findMediaElement" in call_args_pause[0][1]["code"]
    assert "v.pause()" in call_args_pause[0][1]["code"]

    assert client.call.call_count == 2


def test_media_seek_clamps_and_formats_js():
    client = MagicMock()
    client.call.return_value = {"success": True, "currentTime": 45.0}

    tab = Tab(tab_id=2, client=client)
    res = tab.media.seek(15.5)

    assert res == {"success": True, "currentTime": 45.0}
    call_args = client.call.call_args
    assert call_args[0][0] == "execute_script"
    assert "findMediaElement" in call_args[0][1]["code"]
    assert "currentTime += 15.5" in call_args[0][1]["code"]


def test_media_set_volume_clamps_bounds():
    client = MagicMock()
    client.call.return_value = {"success": True, "volume": 1.0}

    tab = Tab(tab_id=1, client=client)
    # Test clamped high
    tab.media.set_volume(1.5)
    call_args_high = client.call.call_args
    assert "findMediaElement" in call_args_high[0][1]["code"]
    assert "volume = 1.0" in call_args_high[0][1]["code"]

    # Test clamped low
    tab.media.set_volume(-0.5)
    call_args_low = client.call.call_args
    assert "findMediaElement" in call_args_low[0][1]["code"]
    assert "volume = 0.0" in call_args_low[0][1]["code"]

    # Test within range
    tab.media.set_volume(0.65)
    call_args_mid = client.call.call_args
    assert "volume = 0.65" in call_args_mid[0][1]["code"]


def test_media_empty_response_fallback_dict():
    client = MagicMock()
    client.call.return_value = None

    tab = Tab(tab_id=1, client=client)
    assert tab.media.status() == {}
    assert tab.media.toggle() == {}
    assert tab.media.play() == {}
    assert tab.media.pause() == {}
    assert tab.media.seek(5.0) == {}
    assert tab.media.set_volume(0.5) == {}
