# Cross-Platform IPC Transport and Automated Native Host Registration

We decided to use cross-platform Unix domain sockets (`AF_UNIX`) located in the OS temporary directory (`tempfile.gettempdir()` / `%TEMP%`) across POSIX systems (Linux/macOS) and Windows (supported natively in Windows 10+ and Node/Python without external dependencies), paired with an automated Node-based installer that manages Windows Registry keys (`HKCU\Software\Google\Chrome\NativeMessagingHosts\...`) and executable batch wrappers (`native-host.bat`).

This preserves zero-network, local-only IPC security without exposing network ports, while eliminating manual Windows registry manipulation for end users installing via `npx` or Git clone.
