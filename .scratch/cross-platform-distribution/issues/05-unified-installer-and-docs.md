# 05 — Unified Cross-Platform Installer & Zero-Friction Documentation

**What to build:**
The project provides a streamlined npm entry point (`npx antigravity-chrome-bridge setup`), cross-platform setup scripts (`setup.sh`, `setup.ps1`), and a refreshed `README.md` containing 60-second quickstarts and troubleshooting guidance for macOS, Windows, and Linux.

**Blocked by:** 04 — Smart Python Bootstrapping & Multi-Client MCP Auto-Discovery

**Status:** done

- [x] `package.json` specifies bin / setup scripts ready for `npx antigravity-chrome-bridge setup` and local execution.
- [x] `setup.ps1` script provided for Windows PowerShell users who clone the repo.
- [x] `setup.sh` updated for POSIX users running bash/zsh on macOS and Linux.
- [x] `README.md` updated with clear, friction-free 60-second installation instructions for macOS, Windows, and Linux.
- [x] Full end-to-end verification and test suite passes across all test modules (`pytest tests/`).
