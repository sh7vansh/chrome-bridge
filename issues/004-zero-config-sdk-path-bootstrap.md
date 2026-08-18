# Zero-Config SDK Path Resolution & Environment Auto-Bootstrap

**Type:** `wayfinder:task` (AFK/HITL)  
**Parent:** [Map: Adaptive & Context-Aware Chrome Bridge Architecture](file:///home/shivansh/chrome-bridge/issues/map.md)  
**Status:** Closed  
**Assignee:** Antigravity  
**Blocked by:** None  

## Question

How should the Python runtime environment (`PYTHONPATH`, package discovery, editable installs, or `.agents/skills/chrome-bridge/SKILL.md` environment setup) be standardized so that any subagent or REPL instance can immediately execute `from chrome_sdk import chrome` without directory searches or cold-start import errors?

## Resolution

1. **Editable Package Install in Setup Scripts:**
   - Updated `setup.sh` and `setup.ps1` to execute `pip install -e .` (or `uv pip install -e .`), registering `chrome_sdk` directly into Python site-packages.
2. **Skill Prompt Preamble:**
   - Standardized the subagent worker prompt template in `.agents/skills/chrome-bridge/SKILL.md` with guaranteed path injection:
     ```python
     import sys, os
     bridge_dir = os.path.expanduser("~/chrome-bridge")
     if bridge_dir not in sys.path:
         sys.path.insert(0, bridge_dir)
     from chrome_sdk import chrome
     ```
3. **MCP Server Direct Injection:**
   - Prepend `os.path.dirname(__file__)` to `sys.path` in `mcp_server.py` and `repl_engine.py` initialization routines.
