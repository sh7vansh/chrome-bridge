"""Persistent Python REPL Session Engine & Output Budgeting for Chrome Bridge."""

import ast
import builtins
import contextlib
import io
import math
import os
import sys
import traceback
from typing import Any, Dict, List, Optional, Tuple, Union

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from chrome_sdk import ChromeBridgeError, auto_bootstrap_environment, defang_telemetry_payload
    auto_bootstrap_environment()
except ImportError:
    from chrome_sdk import ChromeBridgeError
    defang_telemetry_payload = lambda x: x


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
        auto_snapshot: Optional[str] = None,
    ) -> str:
        sections: List[str] = []

        # 1. Error / Exception
        if error:
            sections.append(f"[error]\n{self._truncate_string(error, 2000)}")

        # 2. Diagnostic Auto-Snapshot (if present from error recovery)
        if auto_snapshot and auto_snapshot.strip():
            snapshot_budget = max(2000, int(self.max_chars * 0.4))
            truncated_snapshot = self._truncate_string(auto_snapshot.strip(), snapshot_budget)
            sections.append(f"[diagnostic_auto_snapshot]\n{truncated_snapshot}")

        # 3. Stderr
        if stderr and stderr.strip():
            sections.append(f"[stderr]\n{self._truncate_string(stderr.strip(), 1500)}")

        # 4. Stdout
        if stdout and stdout.strip():
            stdout_budget = max(2000, int(self.max_chars * 0.4))
            truncated_stdout = self._truncate_string(stdout.strip(), stdout_budget)
            sections.append(f"[stdout]\n{truncated_stdout}")

        # 5. Result value
        if has_result:
            used_chars = sum(len(s) for s in sections)
            remaining_budget = max(200, self.max_chars - used_chars)
            formatted_res = self._serialize_value(
                result, current_depth=0, budget=remaining_budget
            )
            # Apply hard ceiling safety check to formatted_res if needed
            if len(formatted_res) > remaining_budget:
                formatted_res = self._truncate_string(formatted_res, remaining_budget)
            sections.append(f"[result]\n{formatted_res}")

        if not sections:
            return "(executed successfully with no output)"

        raw_output = "\n\n".join(sections)
        return defang_telemetry_payload(raw_output)

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


class PythonReplSession:
    """Stateful, in-memory Python REPL session that persists globals across executions."""

    def __init__(self, globals_dict: Optional[Dict[str, Any]] = None, formatter: Optional[OutputBudgetFormatter] = None):
        from chrome_sdk import chrome as default_chrome
        self.formatter = formatter or OutputBudgetFormatter()
        self._globals: Dict[str, Any] = {
            "__name__": "__main__",
            "__doc__": None,
            "__builtins__": builtins,
            "_": None,
            "chrome": default_chrome,
        }
        if globals_dict:
            self._globals.update(globals_dict)

    def execute(self, code: str, timeout: Optional[float] = 30.0) -> str:
        """Executes a Python code block against the persistent session."""
        code_str = code.strip()
        if not code_str:
            return "(executed successfully with no output)"

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        result_value = None
        has_result = False
        error_msg = None
        auto_snapshot = None

        try:
            tree = ast.parse(code_str, filename="<repl>", mode="exec")
        except SyntaxError as e:
            tb_lines = traceback.format_exception_only(type(e), e)
            return self.formatter.format_execution_result(
                error="SyntaxError: " + str(e),
                stderr="".join(tb_lines),
            )

        if not tree.body:
            return "(executed successfully with no output)"

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
            # Check for auto-snapshot attribute on exception or session
            if hasattr(e, "auto_snapshot") and getattr(e, "auto_snapshot"):
                auto_snapshot = getattr(e, "auto_snapshot")
            elif isinstance(e, ChromeBridgeError) and "chrome" in self._globals and hasattr(self._globals["chrome"], "snapshot"):
                try:
                    auto_snapshot = self._globals["chrome"].snapshot()
                except Exception:
                    pass

        return self.formatter.format_execution_result(
            stdout=stdout_buf.getvalue(),
            stderr=stderr_buf.getvalue(),
            result=result_value,
            error=error_msg,
            has_result=has_result,
            auto_snapshot=auto_snapshot,
        )

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


def main():
    """CLI entrypoint to execute Python code in the persistent session."""
    import argparse

    parser = argparse.ArgumentParser(description="Chrome Bridge Python REPL Runner")
    parser.add_argument("-c", "--code", type=str, help="Python code string to execute")
    parser.add_argument("file", nargs="?", type=str, help="Python script file to execute")
    args = parser.parse_args()

    session = PythonReplSession()
    if args.code:
        out = session.execute(args.code)
        print(out)
    elif args.file:
        with open(args.file, "r", encoding="utf-8", errors="replace") as f:
            code = f.read()
        out = session.execute(code)
        print(out)
    else:
        if not sys.stdin.isatty():
            code = sys.stdin.read()
            if code.strip():
                print(session.execute(code))
        else:
            parser.print_help()


if __name__ == "__main__":
    main()

