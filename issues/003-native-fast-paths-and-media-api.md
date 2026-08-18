# Native Media & SPA Fast-Path API Design in `chrome_sdk`

**Type:** `wayfinder:prototype` (HITL)  
**Parent:** [Map: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/map.md)  
**Status:** Closed  
**Assignee:** Antigravity  
**Blocked by:** None  

## Question

How should native browser fast-paths (HTML5 video/audio playback controls, SPA direct URL routing, shadow-DOM element queries) be structured and exposed directly as high-level Python methods in [`chrome_sdk.py`](file:///home/shivansh/chrome-bridge/chrome_sdk.py) to eliminate fragile DOM tree snapshots for common multimedia and navigation workflows?

## Resolution

1. **First-Class Media Controller (`TabMedia`):**
   - Implemented prototype in [`issues/assets/media_fastpath_prototype.py`](file:///home/shivansh/chrome-bridge/issues/assets/media_fastpath_prototype.py).
   - Exposed as `tab.media` on `Tab` instances and `chrome.media` on `Chrome`.
   - Core API methods: `.status()`, `.toggle()`, `.play()`, `.pause()`, `.seek(seconds)`, `.set_volume(level)`.
2. **Shadow-DOM & MediaSession Discovery:**
   - Traverses nested shadow roots to locate active `<video>` and `<audio>` tags in single-page apps (YouTube, YouTube Music, Spotify).
   - Queries `navigator.mediaSession` for track metadata (`title`, `artist`, `album`, `playbackState`).
3. **Execution Latency:**
   - Runs in `< 5ms` via direct evaluation, eliminating DOM outline generation and button Ref-ID lookups.
4. **Telemetry Feeder:**
   - Outputs match the parent agent's lean state handover schema directly.
