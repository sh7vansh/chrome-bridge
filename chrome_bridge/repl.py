import ast
import builtins
import contextlib
import io
import math
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

from .exceptions import ChromeBridgeError
from .security import defang_telemetry_payload


class AmbientStateCache:
    """In-memory memoization cache for ambient state headers to minimize live IPC roundtrips."""

    def __init__(self, ttl: float = 3.0):
        self.ttl = ttl
        self._cached_header: Optional[str] = None
        self._last_fetched: float = 0.0

    def get(self, chrome_inst: Any, force: bool = False) -> Optional[str]:
        """Retrieve cached ambient header or fetch fresh header if expired or forced."""
        now = time.time()
        if not force and self._cached_header is not None and (now - self._last_fetched) < self.ttl:
            return self._cached_header

        if hasattr(chrome_inst, "get_ambient_header"):
            try:
                fresh = chrome_inst.get_ambient_header()
                if fresh:
                    self._cached_header = fresh
                    self._last_fetched = now
                    return fresh
            except Exception:
                pass
        return self._cached_header

    def invalidate(self) -> None:
        """Clear cached ambient state."""
        self._cached_header = None
        self._last_fetched = 0.0


def compress_dom_snapshot(snapshot: str, max_chars: int = 4000) -> str:
    """Compress a Semantic DOM Snapshot by preserving interactive Ref-IDs and accessibility nodes."""
    if not snapshot or len(snapshot) <= max_chars:
        return snapshot

    lines = snapshot.splitlines()
    preserved = []
    header_lines = []

    for line in lines[:3]:
        if line.startswith("PAGE:") or line.startswith("URL:"):
            header_lines.append(line)

    for line in lines:
        stripped = line.strip()
        if "[#" in stripped or any(stripped.startswith(k) for k in ("- button", "- input", "- link", "- select", "- textarea", "heading", "main", "nav")):
            preserved.append(line)
        elif len("\n".join(preserved)) < max_chars // 2:
            preserved.append(line)

    res = "\n".join(header_lines + preserved)
    if len(res) > max_chars:
        res = res[:max_chars - 30] + "\n... [snapshot truncated]"
    return res


class ExecutionTimeoutContext:
    """Zero-overhead POSIX/thread execution watchdog timer."""

    def __init__(self, timeout: Optional[float] = 30.0):
        self.timeout = timeout
        self._old_handler = None

    def __enter__(self):
        if not self.timeout or self.timeout <= 0:
            return self

        import signal
        import threading
        if hasattr(signal, "SIGALRM") and threading.current_thread() is threading.main_thread():
            def _alarm_handler(signum, frame):
                raise TimeoutError(f"REPL execution timed out after {self.timeout:.1f}s")

            self._old_handler = signal.signal(signal.SIGALRM, _alarm_handler)
            signal.setitimer(signal.ITIMER_REAL, float(self.timeout))
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        import signal
        import threading
        if hasattr(signal, "SIGALRM") and self._old_handler is not None:
            try:
                signal.setitimer(signal.ITIMER_REAL, 0)
                signal.signal(signal.SIGALRM, self._old_handler)
            except Exception:
                pass


@dataclass
class DiagnosticReport:
    """Structured domain payload encapsulating diagnostics upon execution failure."""
    failing_line: Optional[int] = None
    failing_code: Optional[str] = None
    candidate_matches: Optional[List[Any]] = None
    auto_snapshot: Optional[str] = None


@dataclass
class ExecutionOutcome:
    """Cohesive domain representation of a Python REPL execution outcome."""
    stdout: str = ""
    stderr: str = ""
    result: Any = None
    has_result: bool = False
    error: Optional[str] = None
    diagnostic: Optional[DiagnosticReport] = None
    ambient_header: Optional[str] = None


def extract_diagnostic_report(
    exc: BaseException,
    code_str: str,
    session_globals: Optional[Dict[str, Any]] = None,
) -> DiagnosticReport:
    """Extract failing frame line, candidate suggestions, and auto-snapshot from exception context."""
    failing_line = None
    failing_code = None
    candidate_matches = None
    auto_snapshot = None

    if exc.__traceback__:
        for frame in traceback.extract_tb(exc.__traceback__):
            if frame.filename == "<repl>" and frame.lineno is not None:
                failing_line = frame.lineno
                lines = code_str.splitlines()
                if 1 <= failing_line <= len(lines):
                    failing_code = lines[failing_line - 1].strip()
                break

    if hasattr(exc, "suggestions") and getattr(exc, "suggestions"):
        candidate_matches = getattr(exc, "suggestions")

    if hasattr(exc, "auto_snapshot") and getattr(exc, "auto_snapshot"):
        auto_snapshot = getattr(exc, "auto_snapshot")
    elif isinstance(exc, ChromeBridgeError) and session_globals and "chrome" in session_globals:
        chrome_inst = session_globals.get("chrome")
        if hasattr(chrome_inst, "snapshot"):
            try:
                auto_snapshot = chrome_inst.snapshot()
            except Exception:
                pass

    if auto_snapshot:
        auto_snapshot = compress_dom_snapshot(auto_snapshot)

    return DiagnosticReport(
        failing_line=failing_line,
        failing_code=failing_code,
        candidate_matches=candidate_matches,
        auto_snapshot=auto_snapshot,
    )


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

    def render(self, outcome: ExecutionOutcome) -> str:
        """Render a strongly-typed ExecutionOutcome into a token-budgeted, defanged text payload."""
        sections: List[str] = []

        # 0. Ambient header banner (if provided)
        if outcome.ambient_header and outcome.ambient_header.strip():
            sections.append(outcome.ambient_header.strip())

        # 1. Error / Exception
        if outcome.error:
            error_text = outcome.error
            diag = outcome.diagnostic
            if diag and diag.failing_line is not None and diag.failing_code and not outcome.error.startswith("Line "):
                error_text = f"Line {diag.failing_line}: {diag.failing_code}\n{outcome.error}"
            sections.append(f"[error]\n{self._truncate_string(error_text, 2000)}")

        # 2. Stdout or Partial Stdout
        if outcome.stdout and outcome.stdout.strip():
            stdout_budget = max(2000, int(self.max_chars * 0.4))
            truncated_stdout = self._truncate_string(outcome.stdout.strip(), stdout_budget)
            tag = "[partial_stdout]" if outcome.error else "[stdout]"
            sections.append(f"{tag}\n{truncated_stdout}")

        # 3. Candidate Matches (Fuzzy matches on failure)
        if outcome.diagnostic and outcome.diagnostic.candidate_matches:
            match_lines = []
            for m in outcome.diagnostic.candidate_matches:
                if isinstance(m, dict):
                    ref = m.get("ref", "")
                    if ref and not str(ref).startswith("["):
                        ref = f"[{ref}]" if str(ref).startswith("#") else f"[#{ref}]"
                    role = m.get("role", "element")
                    name = m.get("name", "")
                    match_lines.append(f"- {ref} ({role} '{name}')")
                else:
                    match_lines.append(f"- {m}")
            if match_lines:
                sections.append(f"[candidate_matches]\n" + "\n".join(match_lines))

        # 4. Diagnostic Auto-Snapshot (if present from error recovery)
        if outcome.diagnostic and outcome.diagnostic.auto_snapshot and outcome.diagnostic.auto_snapshot.strip():
            snapshot_budget = max(2000, int(self.max_chars * 0.4))
            truncated_snapshot = self._truncate_string(outcome.diagnostic.auto_snapshot.strip(), snapshot_budget)
            sections.append(f"[diagnostic_auto_snapshot]\n{truncated_snapshot}")

        # 5. Stderr
        if outcome.stderr and outcome.stderr.strip():
            sections.append(f"[stderr]\n{self._truncate_string(outcome.stderr.strip(), 1500)}")

        # 6. Result value (only if no error)
        if outcome.has_result and not outcome.error:
            used_chars = sum(len(s) for s in sections)
            remaining_budget = max(200, self.max_chars - used_chars)
            formatted_res = self._serialize_value(
                outcome.result, current_depth=0, budget=remaining_budget
            )
            # Apply hard ceiling safety check to formatted_res if needed
            if len(formatted_res) > remaining_budget:
                formatted_res = self._truncate_string(formatted_res, remaining_budget)
            sections.append(f"[result]\n{formatted_res}")

        if not sections:
            return "(executed successfully with no output)"

        if len(sections) == 1 and outcome.ambient_header and sections[0] == outcome.ambient_header.strip():
            return f"{outcome.ambient_header.strip()}\n\n(executed successfully with no output)"

        raw_output = "\n\n".join(sections)
        return defang_telemetry_payload(raw_output)

    def format_execution_result(
        self,
        stdout: str = "",
        stderr: str = "",
        result: Any = None,
        error: Optional[str] = None,
        has_result: bool = False,
        auto_snapshot: Optional[str] = None,
        candidate_matches: Optional[List[Any]] = None,
        failing_line: Optional[int] = None,
        failing_code: Optional[str] = None,
        ambient_header: Optional[str] = None,
    ) -> str:
        diag = None
        if failing_line is not None or failing_code or candidate_matches or auto_snapshot:
            diag = DiagnosticReport(
                failing_line=failing_line,
                failing_code=failing_code,
                candidate_matches=candidate_matches,
                auto_snapshot=auto_snapshot,
            )
        outcome = ExecutionOutcome(
            stdout=stdout,
            stderr=stderr,
            result=result,
            has_result=has_result,
            error=error,
            diagnostic=diag,
            ambient_header=ambient_header,
        )
        return self.render(outcome)

    def _truncate_string(self, text: str, budget: int) -> str:
        if len(text) <= budget:
            return text
        half = max(100, budget // 2 - 40)
        head = text[:half]
        tail = text[-half:]
        omitted_chars = len(text) - len(head) - len(tail)
        omitted_tokens = max(1, omitted_chars // 4)
        return f"{head}\n... [{omitted_chars:,} chars / {omitted_tokens:,} tokens omitted] ...\n{tail}"

    @staticmethod
    def _format_multiline_block(item_strs: List[str], current_depth: int) -> str:
        indent = "  " * (current_depth + 1)
        close_indent = "  " * current_depth
        return f"\n{indent}" + f",\n{indent}".join(item_strs) + f"\n{close_indent}"

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
            if len(val) > budget or (len(val) > self.string_head_tail and current_depth > 0):
                return f'"{self._truncate_string(val, min(budget, self.string_head_tail))}"'
            return repr(val)

        # Depth truncation
        if current_depth >= self.max_depth:
            if isinstance(val, (list, tuple, set)):
                return f"[... {len(val)} items]"
            if isinstance(val, dict):
                return f"{{... {len(val)} keys}}"
            return repr(val)

        # Collections (list / tuple)
        if isinstance(val, (list, tuple)):
            is_tuple = isinstance(val, tuple)
            open_bracket, close_bracket = ("(", ")") if is_tuple else ("[", "]")
            if not val:
                return f"{open_bracket}{close_bracket}"
            
            items = list(val)
            item_strs = []
            for i, item in enumerate(items[: self.max_items]):
                item_strs.append(
                    self._serialize_value(
                        item, current_depth=current_depth + 1, budget=budget // min(len(items), self.max_items)
                    )
                )
            if len(items) > self.max_items:
                omitted = len(items) - self.max_items
                item_strs.append(f"... ({omitted} more items)")
            
            # Formatted multiline if nested or long
            inner = ", ".join(item_strs)
            if len(inner) > 80 or any("\n" in s for s in item_strs):
                inner = self._format_multiline_block(item_strs, current_depth)
            return f"{open_bracket}{inner}{close_bracket}"

        # Dictionaries
        if isinstance(val, dict):
            if not val:
                return "{}"
            keys = list(val.keys())
            item_strs = []
            for k in keys[: self.max_items]:
                k_str = repr(k)
                v_str = self._serialize_value(
                    val[k], current_depth=current_depth + 1, budget=budget // min(len(keys), self.max_items)
                )
                item_strs.append(f"{k_str}: {v_str}")
            if len(keys) > self.max_items:
                omitted = len(keys) - self.max_items
                item_strs.append(f"... ({omitted} more keys)")
            
            inner = self._format_multiline_block(item_strs, current_depth)
            return f"{{{inner}}}"

        # Custom repr for objects
        return repr(val)


class ReplSessionEngine:
    """Stateful, in-memory Python REPL session engine that persists globals across executions."""

    def __init__(
        self,
        globals_dict: Optional[Dict[str, Any]] = None,
        formatter: Optional[OutputBudgetFormatter] = None,
        include_ambient: bool = True,
    ):
        try:
            from chrome_sdk import chrome as default_chrome
        except ImportError:
            default_chrome = None

        self.formatter = formatter or OutputBudgetFormatter()
        self.include_ambient = include_ambient
        self.ambient_cache = AmbientStateCache()

        self._initial_globals: Dict[str, Any] = {
            "__name__": "__main__",
            "__doc__": None,
            "__builtins__": builtins,
            "_": None,
            "chrome": default_chrome,
        }
        if globals_dict:
            self._initial_globals.update(globals_dict)

        self._globals: Dict[str, Any] = dict(self._initial_globals)

    def reset(self) -> None:
        """Reset execution session variables back to initial state."""
        self._globals = dict(self._initial_globals)
        self.ambient_cache.invalidate()

    def execute_raw(self, code: str, timeout: Optional[float] = 30.0) -> ExecutionOutcome:
        """Executes a Python code block and returns the strongly-typed ExecutionOutcome domain object."""
        code_str = code.strip()
        if not code_str:
            return ExecutionOutcome()

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        result_value = None
        has_result = False
        error_msg = None
        auto_snapshot = None
        failing_line = None
        failing_code = None
        candidate_matches = None
        ambient_header = None

        diagnostic_report: Optional[DiagnosticReport] = None

        try:
            tree = ast.parse(code_str, filename="<repl>", mode="exec")
        except SyntaxError as e:
            tb_lines = traceback.format_exception_only(type(e), e)
            return ExecutionOutcome(
                error="SyntaxError: " + str(e),
                stderr="".join(tb_lines),
            )

        if not tree.body:
            return ExecutionOutcome()

        # Check if the last node is an expression statement
        last_is_expr = isinstance(tree.body[-1], ast.Expr)

        try:
            with ExecutionTimeoutContext(timeout):
                with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                    if last_is_expr:
                        # Split statements and final expression
                        stmt_nodes = tree.body[:-1]
                        expr_node = tree.body[-1]

                        if stmt_nodes:
                            stmt_module = ast.Module(body=stmt_nodes, type_ignores=[])
                            stmt_code = compile(stmt_module, filename="<repl>", mode="exec")
                            exec(stmt_code, self._globals, self._globals)

                        # Evaluate the trailing expression
                        expr_ast = ast.Expression(body=expr_node.value)
                        ast.copy_location(expr_ast, expr_node)
                        expr_code = compile(expr_ast, filename="<repl>", mode="eval")
                        result_value = eval(expr_code, self._globals, self._globals)
                        has_result = True
                        if result_value is not None:
                            self._globals["_"] = result_value
                    else:
                        code_compiled = compile(tree, filename="<repl>", mode="exec")
                        exec(code_compiled, self._globals, self._globals)
                        has_result = False

        except BaseException as e:
            error_msg = self._format_exception_message(e)
            stderr_buf.write(self._sanitize_traceback(e))
            diagnostic_report = extract_diagnostic_report(
                exc=e,
                code_str=code_str,
                session_globals=self._globals,
            )

        # Retrieve ambient state header via cache if enabled
        if self.include_ambient:
            chrome_inst = self._globals.get("chrome")
            if chrome_inst:
                ambient_header = self.ambient_cache.get(chrome_inst)

        return ExecutionOutcome(
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            result=result_value,
            has_result=has_result,
            error=error_msg,
            diagnostic=diagnostic_report,
            ambient_header=ambient_header,
        )

    def execute(self, code: str, timeout: Optional[float] = 30.0) -> str:
        """Executes a Python code block against the persistent session and returns the rendered output."""
        outcome = self.execute_raw(code, timeout=timeout)
        return self.formatter.render(outcome)

    def _format_exception_message(self, exc: BaseException) -> str:
        return f"{type(exc).__name__}: {str(exc)}"

    def _sanitize_traceback(self, exc: BaseException) -> str:
        tb = exc.__traceback__
        if not tb:
            return "".join(traceback.format_exception_only(type(exc), exc))

        extracted = traceback.extract_tb(tb)
        clean_frames = []
        for frame in extracted:
            fn = frame.filename
            if fn == "<repl>":
                clean_frames.append(frame)
            elif "chrome_sdk.py" in fn:
                # Include high-level public methods, exclude socket client / IPC internals
                if not frame.name.startswith("_") and frame.name not in ("call", "connect", "close", "ping"):
                    clean_frames.append(frame)
            elif not fn.startswith("<") and "site-packages" not in fn and "lib/python" not in fn:
                clean_frames.append(frame)

        if clean_frames:
            formatted_tb = "".join(traceback.format_list(clean_frames))
            exc_only = "".join(traceback.format_exception_only(type(exc), exc))
            return f"Traceback (most recent call last):\n{formatted_tb}{exc_only}"

        return "".join(traceback.format_exception_only(type(exc), exc))


# Backward compatibility alias
PythonReplSession = ReplSessionEngine
