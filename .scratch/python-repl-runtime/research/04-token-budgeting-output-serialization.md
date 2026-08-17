# Research 04: Token Budgeting & Output Serialization Specification

**Ticket**: `04-token-budgeting-output-serialization.md`  
**Status**: Completed  
**Type**: Prototype / HITL  
**Prototype Asset**: [.scratch/python-repl-runtime/token_budget_demo.html](../token_budget_demo.html)  
**Domain**: Python REPL Runtime, Output Formatting, Token Optimization, LLM Context Budgeting  

---

## 1. Executive Summary

In a persistent Python REPL runtime layer, AI drivers frequently execute scripts that iterate over hundreds of DOM nodes, scrape multi-column tables, print intermediate debug logs, or evaluate complex data structures.

Returning raw serialization (e.g. `json.dumps(obj)` or unbounded `sys.stdout`) risks blowing the model's active context window (30k–100k+ tokens), causing context overflow or high latency. Conversely, blind string truncation (`str[:1000]`) destroys syntactic validity (cutting JSON in half or losing closing delimiters) and hides critical tail data.

This specification defines a **Dual-Layer Structural Token Budgeting & Serialization Engine**:
1. **Layer 1: Structural AST & Object Pruning**:
   - Caps collection length (default: 10 items) and replaces remaining entries with `... (N more items)`.
   - Caps dictionary keys (default: 10 keys) and nesting depth (default: 3 levels) with `[... N items]` / `{... N keys}`.
   - Preserves high-density custom `__repr__` for SDK objects (e.g. `<Tab id=1 ...>`).
2. **Layer 2: Hard Character / Byte Safety Ceiling**:
   - Caps total response characters (default: 12,000 chars ≈ 3,000 tokens).
   - Allocates balanced sub-budgets across `[stdout]`, `[stderr]`, and `[result]`.
   - Uses Head-and-Tail preservation with explicit omission markers (`... [N chars / M tokens omitted] ...`) so the model sees both start and end results.

---

## 2. Output Formatting Layout Specification

The output returned by the MCP `execute_python` tool is serialized into a clean, tagged plaintext layout optimized for LLM comprehension:

```text
[stdout]
<captured stdout stream if present, truncated if exceeding sub-budget>

[stderr]
<captured stderr stream or warnings if present>

[result]
<structural pretty-printed representation of the final evaluated expression>
```

If an unhandled exception occurred, `[error]` is prepended:
```text
[error]
<Formatted exception class and human-readable diagnostic message>

[stderr]
<Python traceback frames>
```

### Layout Rules:
1. Empty sections are omitted entirely (e.g. if `stdout` is empty and no errors occurred, only `[result]` is returned).
2. If both `stdout` and `result` are empty (e.g. a script with only assignments `x = 5`), the tool returns `"(executed successfully with no output)"`.
3. If the final statement is an expression (e.g. `chrome.tabs`), its serialized value is rendered in `[result]`.

---

## 3. Structural Pruning Rules & Examples

### 3.1 Large Tabular Collections (Lists of Dicts)
When a driver scrapes 200 rows from a table:
```python
# Raw Python Evaluation:
rows = [{'rank': i, 'title': f'Item {i}', 'price': '$10.00'} for i in range(200)]
```
**Serialized Result:**
```text
[result]
[
  {'rank': 0, 'title': 'Item 0', 'price': '$10.00'},
  {'rank': 1, 'title': 'Item 1', 'price': '$10.00'},
  {'rank': 2, 'title': 'Item 2', 'price': '$10.00'},
  {'rank': 3, 'title': 'Item 3', 'price': '$10.00'},
  {'rank': 4, 'title': 'Item 4', 'price': '$10.00'},
  {'rank': 5, 'title': 'Item 5', 'price': '$10.00'},
  {'rank': 6, 'title': 'Item 6', 'price': '$10.00'},
  {'rank': 7, 'title': 'Item 7', 'price': '$10.00'},
  {'rank': 8, 'title': 'Item 8', 'price': '$10.00'},
  {'rank': 9, 'title': 'Item 9', 'price': '$10.00'},
  ... (190 more items)
]
```

### 3.2 Deeply Nested Objects
When depth exceeds `max_depth = 3`:
```text
[result]
{
  'tag': 'div',
  'class': 'container',
  'children': [
    {
      'tag': 'ul',
      'items': [... 45 items]
    }
  ],
  'metadata': {... 8 keys}
}
```

### 3.3 Large Multiline Strings (Article Text / Raw Snapshots)
When a single string property exceeds character budget:
```text
[result]
"Antigravity Chrome Bridge enables AI agent drivers to communicate directly with active Google Chrome sessions...
... [34,120 chars / 8,980 tokens omitted] ...
...final conclusions and footer summary."
```

### 3.4 SDK Objects Representation
SDK objects implement high-signal `__repr__` methods:
```text
[result]
[
  <Tab id=1 title="GitHub - Dashboard" url="https://github.com" active=True>,
  <Tab id=2 title="Hacker News" url="https://news.ycombinator.com" active=False>,
  <Tab id=3 title="Google Search" url="https://google.com" active=False>
]
```

---

## 4. Python Implementation Reference

```python
import io
import json
from typing import Any, Dict, List, Optional, Tuple


class OutputBudgetFormatter:
  """Serializes and caps Python REPL execution results to fit token budgets."""

  def __init__(
      self,
      max_chars: int = 12000,
      max_items: int = 10,
      max_depth: int = 3,
      string_head_tail: int = 600,
  ):
    self.max_chars = max_chars
    self.max_items = max_items
    self.max_depth = max_depth
    self.string_head_tail = string_head_tail

  def format_execution_result(
      self,
      stdout: str = "",
      stderr: str = "",
      result: Any = None,
      error: Optional[str] = None,
      has_result: bool = False,
  ) -> str:
    sections: List[str] = []

    # 1. Error / Exception
    if error:
      sections.append(f"[error]\n{self._truncate_string(error, 2000)}")

    # 2. Stderr
    if stderr and stderr.strip():
      sections.append(
          f"[stderr]\n{self._truncate_string(stderr.strip(), 1500)}"
      )

    # 3. Stdout
    if stdout and stdout.strip():
      stdout_budget = max(2000, int(self.max_chars * 0.4))
      truncated_stdout = self._truncate_string(stdout.strip(), stdout_budget)
      sections.append(f"[stdout]\n{truncated_stdout}")

    # 4. Result value
    if has_result:
      used_chars = sum(len(s) for s in sections)
      remaining_budget = max(2000, self.max_chars - used_chars)
      formatted_res = self._serialize_value(
          result, current_depth=0, budget=remaining_budget
      )
      sections.append(f"[result]\n{formatted_res}")

    if not sections:
      return "(executed successfully with no output)"

    return "\n\n".join(sections)

  def _serialize_value(
      self, val: Any, current_depth: int = 0, budget: int = 2000
  ) -> str:
    if val is None:
      return "None"
    if isinstance(val, bool):
      return "True" if val else "False"
    if isinstance(val, (int, float)):
      return str(val)
    if isinstance(val, str):
      if len(val) > budget or (len(val) > 800 and current_depth > 0):
        return f'"{self._truncate_string(val, min(budget, 800))}"'
      return repr(val)

    # Check for custom __repr__ on SDK types (e.g. Tab)
    if hasattr(val, "__repr__") and type(val).__module__ != "builtins":
      custom_repr = repr(val)
      if len(custom_repr) < 300:
        return custom_repr

    # Depth Cap
    if current_depth >= self.max_depth:
      if isinstance(val, (list, tuple, set)):
        return f"[... {len(val)} items]"
      if isinstance(val, dict):
        return f"{{... {len(val)} keys}}"

    # Lists / Tuples
    if isinstance(val, (list, tuple)):
      items_to_show = val[: self.max_items]
      rendered = [
          self._serialize_value(
              item, current_depth + 1, budget // max(1, len(items_to_show))
          )
          for item in items_to_show
      ]
      if len(val) > self.max_items:
        rendered.append(f"... ({len(val) - self.max_items} more items)")

      single_line = f"[{', '.join(rendered)}]"
      if len(single_line) <= 80 and "\n" not in single_line:
        return single_line

      indent = "  " * (current_depth + 1)
      closing_indent = "  " * current_depth
      nested_lines = ",\n".join(
          f"{indent}{r.replace(chr(10), chr(10) + indent)}" for r in rendered
      )
      return f"[\n{nested_lines}\n{closing_indent}]"

    # Dictionaries
    if isinstance(val, dict):
      keys = list(val.keys())
      keys_to_show = keys[: self.max_items]
      rendered = []
      for k in keys_to_show:
        v_str = self._serialize_value(
            val[k], current_depth + 1, budget // max(1, len(keys_to_show))
        )
        rendered.append(f"{repr(k)}: {v_str}")
      if len(keys) > self.max_items:
        rendered.append(f"... ({len(keys) - self.max_items} more keys)")

      single_line = f"{{{', '.join(rendered)}}}"
      if len(single_line) <= 80 and "\n" not in single_line:
        return single_line

      indent = "  " * (current_depth + 1)
      closing_indent = "  " * current_depth
      nested_lines = ",\n".join(
          f"{indent}{r.replace(chr(10), chr(10) + indent)}" for r in rendered
      )
      return f"{{\n{nested_lines}\n{closing_indent}}}"

    return repr(val)

  def _truncate_string(self, text: str, max_len: int) -> str:
    if len(text) <= max_len:
      return text
    keep_each = max(30, (max_len - 60) // 2)
    head = text[:keep_each]
    tail = text[-keep_each:]
    omitted = len(text) - (len(head) + len(tail))
    return f"{head}\n... [{omitted:,} chars / ~{omitted // 4:,} tokens omitted] ...\n{tail}"
```

---

## 5. REPL Driver Customization API

Drivers can inspect or modify output limits within their script when intentional deep dumps are needed:

```python
# Optional runtime adjustments within the REPL:
chrome.set_output_limits(max_chars=30000, max_items=50, max_depth=5)
```

Default standard limits:
- `max_chars`: `12,000` chars (~3,000 tokens)
- `max_items`: `10`
- `max_depth`: `3`
- `string_head_tail`: `600` chars
