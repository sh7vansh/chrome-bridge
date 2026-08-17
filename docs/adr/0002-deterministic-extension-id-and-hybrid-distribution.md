# Deterministic Extension Key Pinning and Hybrid Distribution

We decided to pin the extension's public key directly inside `extension/manifest.json` while publishing the extension package to the Chrome Web Store.

This guarantees that both unpacked developer installs from GitHub and 1-click Chrome Web Store installs share the exact same Extension ID (`nbghhppoiigjbdjbhefiaijofpnhgepb`), eliminating host manifest origin mismatches and drift across environments.
