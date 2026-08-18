# 009 — Flexible Multi-Root Skill Source Discovery & Synchronization

**Parent:** [Map: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/map.md)

**What to build:**
Implement a prioritized multi-candidate skill source locator in `setup-host.mjs` that resolves `SKILL.md` across multiple possible repository layouts (`.agents/skills/chrome-bridge/SKILL.md`, `SKILL.md`, `skills/chrome-bridge/SKILL.md`) and synchronizes it to all target agent skill directories (`~/.agent`, `~/.agents`, `~/.gemini/antigravity-cli`, `~/.gemini/config`).

## Acceptance criteria

- [x] `setup-host.mjs` checks an ordered array of candidate source paths for `SKILL.md` and selects the first match.
- [x] Found skill file is copied to all supported agent destination directories (`.agent`, `.agents`, `.gemini/antigravity-cli`, `.gemini/config`).
- [x] Installer logs informative feedback showing the exact resolved source and destination paths.
- [x] Unit tests verify skill source discovery when `SKILL.md` is positioned in root vs nested directories.

## Blocked by

- [005 — Runtime Directory Standardization & Multi-Path SDK Bootstrap](file:///home/shivansh/chrome-bridge/issues/005-runtime-directory-and-import-path-unification.md)

**Status:** closed

