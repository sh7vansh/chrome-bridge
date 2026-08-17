#!/usr/bin/env bash
set -e

# ANSI Color Codes
GREEN="\033[0;32m"
CYAN="\033[0;36m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BOLD="\033[1m"
NC="\033[0m"

echo -e "${BOLD}${CYAN}======================================================${NC}"
echo -e "${BOLD}${CYAN}   Chrome Bridge 2.0 - Comprehensive Test Suite       ${NC}"
echo -e "${BOLD}${CYAN}======================================================${NC}"

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

# 1. Check Python Virtual Environment
if [ -f ".venv/bin/pytest" ]; then
    PYTEST_BIN=".venv/bin/pytest"
elif command -v pytest &> /dev/null; then
    PYTEST_BIN="pytest"
else
    echo -e "${RED}[ERROR] pytest not found in .venv or PATH.${NC}"
    exit 1
fi

echo -e "\n${BOLD}${YELLOW}[1/3] Running Python REPL & Zero-Leakage Test Suites...${NC}"
$PYTEST_BIN -v

echo -e "\n${BOLD}${YELLOW}[2/3] Checking Domain Terminology & Skill Encapsulation...${NC}"
# Assert no forbidden internal tokens leaked into agent skills
FORBIDDEN_LEAK=( "socket.sock" "native-host.mjs" "Manifest V3 worker" )
VIOLATIONS=0

for term in "${FORBIDDEN_LEAK[@]}"; do
    if grep -q "$term" skills/chrome-bridge/SKILL.md 2>/dev/null; then
        echo -e "${RED}[FAIL] Forbidden leak '$term' found in skills/chrome-bridge/SKILL.md${NC}"
        VIOLATIONS=$((VIOLATIONS + 1))
    fi
done

if [ $VIOLATIONS -eq 0 ]; then
    echo -e "${GREEN}✓ Skill documentation is 100% encapsulated and clean.${NC}"
else
    echo -e "${RED}✗ Skill documentation has abstraction leakage.${NC}"
    exit 1
fi

echo -e "\n${BOLD}${YELLOW}[3/3] Verifying MCP Canonical Entrypoint...${NC}"
if [ -f "mcp_server.py" ]; then
    .venv/bin/python -c "import mcp_server; print('✓ mcp_server.py imported successfully with tool:', mcp_server.execute_python.__name__)"
fi

echo -e "\n${BOLD}${GREEN}======================================================${NC}"
echo -e "${BOLD}${GREEN}   ✓ ALL TESTS & ZERO-LEAKAGE CHECKS PASSED!          ${NC}"
echo -e "${BOLD}${GREEN}======================================================${NC}"
