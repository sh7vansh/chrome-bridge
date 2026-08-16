---
name: chrome-bridge
description: Interact with the user's active Google Chrome browser via Native Messaging MCP tools. Trigger when the user asks to inspect open tabs, read page content, navigate, click, fill forms, or take screenshots in their live browser.
---

# Chrome Bridge

Controls the user's everyday Google Chrome browser in real-time via Native Messaging MCP tools (`chrome_*`).

* **Setup / Re-register**: Run `npm run setup` in the repository root
* **Test Suite**: Run `npm test`

### Guidelines
* Use `chrome_get_page_content` for reading text and articles (fast, token-efficient).
* Use `chrome_screenshot` when visual UI layout or design verification is needed.
* Tools are registered natively in MCP (`chrome_navigate`, `chrome_click`, `chrome_type`, `chrome_execute_script`, etc.).
