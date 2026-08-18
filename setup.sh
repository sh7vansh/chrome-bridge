#!/usr/bin/env bash
set -e

# ANSI Color Codes
CYAN="\033[0;36m"
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BOLD="\033[1m"
DIM="\033[2m"
NC="\033[0m"

echo -e "${BOLD}${CYAN}================================================================${NC}"
echo -e "${BOLD}${CYAN}   🚀 Chrome Bridge 2.0 — Pure Python Setup Assistant           ${NC}"
echo -e "${BOLD}${CYAN}================================================================${NC}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo -e "\n${BOLD}📋 System Environment Check:${NC}"
echo -e "  • Working Directory: ${DIR}"
echo -e "  • Shell:             ${SHELL:-bash}"
echo -e "  • Platform:          $(uname -s) ($(uname -m))"

# Check Python / uv Package Manager
echo -e "\n${BOLD}${YELLOW}[1/2] Provisioning Python Virtual Environment...${NC}"
PYTHON_BIN=""

if command -v uv >/dev/null 2>&1; then
    UV_VER="$(uv --version)"
    echo -e "  ${GREEN}✓${NC} Fast installer detected: ${BOLD}${UV_VER}${NC}"
    if [ ! -d ".venv" ]; then
        echo -e "  ⚡ Creating virtualenv at ${BOLD}.venv${NC} using uv..."
        uv venv .venv
    else
        echo -e "  ${GREEN}✓${NC} Existing .venv directory found."
    fi
    echo -e "  📥 Syncing dependencies from requirements.txt and registering package..."
    source .venv/bin/activate
    uv pip install -r requirements.txt
    uv pip install -e .
    PYTHON_BIN=".venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PY_VER="$(python3 --version)"
    echo -e "  ${GREEN}✓${NC} Python 3 detected: ${BOLD}${PY_VER}${NC}"
    if [ ! -d ".venv" ]; then
        echo -e "  🐍 Creating virtualenv at ${BOLD}.venv${NC} using python3 -m venv..."
        python3 -m venv .venv || {
            echo -e "  ${RED}✗ Failed to create venv. You may need python3-venv installed.${NC}"
            echo -e "    👉 ${CYAN}sudo apt install python3-venv python3-pip${NC}"
            exit 1
        }
    fi
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        echo -e "  📥 Installing dependencies via pip and registering package..."
        pip install -r requirements.txt
        pip install -e .
        PYTHON_BIN=".venv/bin/python3"
    else
        PYTHON_BIN="python3"
    fi
else
    echo -e "  ${RED}✗ Error: Python 3.10+ is required for the REPL automation runtime.${NC}"
    echo -e "    👉 ${CYAN}sudo apt install python3 python3-venv python3-pip${NC} or install ${CYAN}uv${NC} (https://astral.sh/uv)"
    exit 1
fi

echo -e "\n${BOLD}${YELLOW}[2/2] Registering Chrome Native Host, Agent Skill & MCP Servers...${NC}"
"$PYTHON_BIN" setup_host.py "$@"
