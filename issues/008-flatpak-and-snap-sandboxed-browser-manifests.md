# 008 — Sandboxed Linux Browser Manifest Registration (Flatpak & Snap)

**Parent:** [Map: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/map.md)

**What to build:**
Extend the `setup-host.mjs` installer and diagnostic `status` command to detect and register Native Messaging manifests in Flatpak (`~/.var/app/*/config/.../NativeMessagingHosts`) and Snap (`~/snap/*/current/.config/.../NativeMessagingHosts`) sandbox directories for Google Chrome, Chromium, Brave, and Microsoft Edge on Linux.

## Acceptance criteria

- [x] `setup-host.mjs` registers Native Messaging manifests for Flatpak Chrome, Chromium, Brave, and Edge when running on Linux.
- [x] `setup-host.mjs` registers Native Messaging manifests for Snap Chromium, Brave, and Edge when running on Linux.
- [x] The `status` command lists detected Flatpak and Snap Native Messaging manifests alongside traditional paths.
- [x] Manifest registration safely handles missing or non-existent parent directories without throwing unhandled exceptions.
- [x] Unit tests verify all target Flatpak and Snap path configurations.

## Blocked by

- [006 — POSIX Native Host Launcher Wrapper & Path Pinning](file:///home/shivansh/chrome-bridge/issues/006-posix-gui-path-blindspot-and-host-wrapper.md)

**Status:** closed

