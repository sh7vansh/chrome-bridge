# 02 — Deterministic Extension Key Pinning & Manifest V3 Parity

**What to build:**
The Chrome Extension `manifest.json` is configured with a pinned RSA public key so that unpacked installations from GitHub automatically resolve to the fixed Extension ID (`nbghhppoiigjbdjbhefiaijofpnhgepb`) matching the Chrome Web Store package, guaranteeing that Native Messaging permissions work immediately without identifier mismatches.

**Blocked by:** None — can start immediately.

**Status:** done

- [x] Extension `manifest.json` contains the pinned `key` property matching Extension ID `nbghhppoiigjbdjbhefiaijofpnhgepb`.
- [x] Loading the unpacked extension in Chrome Developer Mode assigns the fixed Extension ID.
- [x] Chrome Native Messaging Host manifests across all platforms allow `chrome-extension://nbghhppoiigjbdjbhefiaijofpnhgepb/` seamlessly.
