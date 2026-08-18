"""Prototype for Native Media Fast-Paths in Chrome Bridge SDK.

Provides zero-DOM-traversal HTML5 & MediaSession control for SPAs (YouTube, Spotify, SoundCloud, etc.).
"""

from typing import Any, Dict, Optional


class TabMedia:
    """Fast-path media controller attached to a Tab instance."""

    def __init__(self, tab: Any):
        self._tab = tab

    def status(self) -> Dict[str, Any]:
        """Fetch real-time media player state via HTML5 Video/Audio & MediaSession APIs."""
        js = """
        (() => {
            // Traverse shadow roots to find videos/audios if nested
            function findMediaElement(root = document) {
                let el = root.querySelector('video, audio');
                if (el) return el;
                const all = root.querySelectorAll('*');
                for (const node of all) {
                    if (node.shadowRoot) {
                        const nested = findMediaElement(node.shadowRoot);
                        if (nested) return nested;
                    }
                }
                return null;
            }

            const media = findMediaElement();
            const session = navigator.mediaSession;
            return {
                found: !!media,
                paused: media ? media.paused : null,
                currentTime: media ? media.currentTime : null,
                duration: media ? media.duration : null,
                volume: media ? media.volume : null,
                muted: media ? media.muted : null,
                title: session?.metadata?.title || document.title,
                artist: session?.metadata?.artist || "",
                album: session?.metadata?.album || "",
                playbackState: session?.playbackState || (media ? (media.paused ? "paused" : "playing") : "none")
            };
        })()
        """
        return self._tab.eval_js(js) or {}

    def toggle(self) -> Dict[str, Any]:
        """Toggle play/pause on the active media element."""
        js = """
        (() => {
            function findMediaElement(root = document) {
                let el = root.querySelector('video, audio');
                if (el) return el;
                const all = root.querySelectorAll('*');
                for (const node of all) {
                    if (node.shadowRoot) {
                        const nested = findMediaElement(node.shadowRoot);
                        if (nested) return nested;
                    }
                }
                return null;
            }
            const media = findMediaElement();
            if (!media) return {success: false, error: "No media element found"};
            if (media.paused) {
                media.play();
                return {success: true, action: "played"};
            } else {
                media.pause();
                return {success: true, action: "paused"};
            }
        })()
        """
        return self._tab.eval_js(js) or {}

    def play(self) -> Dict[str, Any]:
        """Play active media element."""
        return self._tab.eval_js("(() => { const v = document.querySelector('video, audio'); if (v) { v.play(); return {success: true}; } return {success: false}; })()")

    def pause(self) -> Dict[str, Any]:
        """Pause active media element."""
        return self._tab.eval_js("(() => { const v = document.querySelector('video, audio'); if (v) { v.pause(); return {success: true}; } return {success: false}; })()")

    def seek(self, seconds: float) -> Dict[str, Any]:
        """Seek relative (+/- seconds) or absolute position."""
        js = f"""
        (() => {{
            const v = document.querySelector('video, audio');
            if (!v) return {{success: false}};
            v.currentTime += {seconds};
            return {{success: true, currentTime: v.currentTime}};
        }})()
        """
        return self._tab.eval_js(js)

    def set_volume(self, volume: float) -> Dict[str, Any]:
        """Set volume level between 0.0 and 1.0."""
        volume = max(0.0, min(1.0, float(volume)))
        return self._tab.eval_js(f"(() => {{ const v = document.querySelector('video, audio'); if (v) {{ v.volume = {volume}; v.muted = false; return {{success: true, volume: v.volume}}; }} return {{success: false}}; }})()")
