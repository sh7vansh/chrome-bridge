# Cross-Platform IPC Transport and Automated Native Host Registration

We decided to use platform-aware OS temp-directory sockets on POSIX systems (Linux/macOS) and Named Pipes / `%TEMP%` on Windows, paired with an automated Node-based installer that manages Windows Registry keys (`HKCU\Software\Google\Chrome\NativeMessagingHosts\...`) and executable batch wrappers (`native-host.bat`).

This preserves zero-network, local-only IPC security without exposing network ports, while eliminating manual Windows registry manipulation for end users installing via `npx` or Git clone.
