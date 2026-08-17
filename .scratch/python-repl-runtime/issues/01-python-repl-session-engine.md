Type: research
Status: closed

## Question

How should the persistent in-process Python REPL session engine be structured (evaluating multi-line AST, capturing stdout/stderr/return values, managing global scope across turns) and integrate with the Python MCP SDK (`mcp`) over the `/tmp/chrome_bridge.sock` Unix Domain Socket?

## Findings

Detailed research completed in [01-python-repl-session-engine.md](../research/01-python-repl-session-engine.md).

