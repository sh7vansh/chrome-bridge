"""Persistent Python REPL Session Engine & Output Budgeting Facade for Chrome Bridge."""

import os
import sys

_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)

try:
    from chrome_sdk import auto_bootstrap_environment
    auto_bootstrap_environment()
except ImportError:
    pass

# Re-export core REPL subsystem components with 100% backward compatibility
from chrome_bridge.repl import (
    DiagnosticReport,
    ExecutionOutcome,
    ExecutionTimeoutContext,
    OutputBudgetFormatter,
    PythonReplSession,
    ReplMetadataCatalog,
    ReplSessionEngine,
    extract_diagnostic_report,
)

__all__ = [
    "ExecutionTimeoutContext",
    "DiagnosticReport",
    "ExecutionOutcome",
    "extract_diagnostic_report",
    "OutputBudgetFormatter",
    "ReplMetadataCatalog",
    "ReplSessionEngine",
    "PythonReplSession",
    "main",
]


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
