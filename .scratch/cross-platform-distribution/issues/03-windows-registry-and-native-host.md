# 03 — Automated Windows Registry & Native Messaging Host Setup

**What to build:**
The host setup utility (`setup-host.mjs`) provides first-class Windows support by detecting `win32`, generating the `native-host.bat` executable wrapper, writing Windows-formatted manifest JSON files, and automatically registering the Native Messaging Host in the Windows Registry under `HKCU\Software\Google\Chrome\NativeMessagingHosts` (and Chromium, Brave, Edge) without requiring administrator rights.

**Blocked by:** 01 — Cross-Platform IPC Transport Layer & Diagnostic Recovery, 02 — Deterministic Extension Key Pinning & Manifest V3 Parity

**Status:** done

- [x] On Windows (`win32`), `setup-host.mjs` generates a `native-host.bat` wrapper in the repository root that executes `node native-host.mjs %*`.
- [x] Windows Native Messaging manifest points to `native-host.bat` with properly escaped Windows paths.
- [x] `setup-host.mjs` executes `reg.exe add` commands targeting `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.antigravity.chrome_bridge` (and Brave, Chromium, Edge) to register the manifest.
- [x] POSIX behavior (Linux & macOS directory manifests) continues to execute without regression.
