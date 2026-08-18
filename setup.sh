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
echo -e "${BOLD}${CYAN}   🚀 Chrome Bridge 2.0 — Linux / macOS Setup Assistant         ${NC}"
echo -e "${BOLD}${CYAN}================================================================${NC}"

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo -e "\n${BOLD}📋 System Environment Check:${NC}"
echo -e "  • Working Directory: ${DIR}"
echo -e "  • Shell:             ${SHELL:-bash}"
echo -e "  • Platform:          $(uname -s) ($(uname -m))"

# Check Node.js
echo -e "\n${BOLD}${YELLOW}[1/3] Validating Node.js Runtime...${NC}"
if command -v node >/dev/null 2>&1; then
    NODE_VER="$(node --version)"
    echo -e "  ${GREEN}✓${NC} Node.js detected: ${BOLD}${NODE_VER}${NC} (${DIM}$(which node)${NC})"
else
    echo -e "  ${RED}✗ Error: Node.js is required for Native Messaging IPC.${NC}"
    echo -e "    Please install Node.js (v18+ recommended):"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo -e "    👉 ${CYAN}brew install node${NC}"
    else
        echo -e "    👉 ${CYAN}sudo apt install nodejs npm${NC} or ${CYAN}curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -${NC}"
    fi
    exit 1
fi

# Check Python / Package Manager
echo -e "\n${BOLD}${YELLOW}[2/3] Provisioning Python Virtual Environment...${NC}"
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
    fi
else
    echo -e "  ${RED}✗ Error: Python 3.10+ is required for the REPL automation runtime.${NC}"
    exit 1
fi

echo -e "\n${BOLD}${YELLOW}[3/3] Registering Chrome Native Host, Agent Skill & MCP Servers...${NC}"
node setup-host.mjs "$@"

