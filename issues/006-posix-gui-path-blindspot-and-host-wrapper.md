# 006 — POSIX Native Host Launcher Wrapper & Path Pinning

**Parent:** [Map: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/map.md)

**What to build:**
Generate an executable shell script wrapper `native-host.sh` during setup on macOS and Linux that embeds the resolved Node.js binary path (`process.execPath`) with fallback search logic for standard package manager paths (`/opt/homebrew/bin`, `~/.nvm`, `~/.fnm`, `~/.local/bin`, `/usr/bin`), and point the browser Native Messaging manifest `path` property to this launcher wrapper so Chrome GUI desktop launches connect reliably.

## Acceptance criteria

- [x] `setup-host.mjs` generates an executable `native-host.sh` wrapper script on POSIX platforms containing the active Node binary path and fallback PATH probes.
- [x] Both `native-host.sh` and `native-host.mjs` receive `0755` executable permissions during installation.
- [x] The generated Native Messaging JSON manifests on Linux and macOS point to `native-host.sh` in the `path` field.
- [x] Windows continues to use `native-host.bat` without regression.
- [x] Unit tests verify launcher script generation and manifest `path` correctness across OS targets.

## Blocked by

- None — can start immediately.

**Status:** closed

