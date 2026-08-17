#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "📦 Initializing Chrome Bridge Python REPL Runtime environment..."

if command -v uv >/dev/null 2>&1; then
    echo "⚡ Setting up virtualenv with uv..."
    if [ ! -d ".venv" ]; then
        uv venv .venv
    fi
    source .venv/bin/activate
    uv pip install -r requirements.txt
elif command -v python3 >/dev/null 2>&1; then
    echo "🐍 Setting up virtualenv with python3 -m venv..."
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv || true
    fi
    if [ -f ".venv/bin/activate" ]; then
        source .venv/bin/activate
        pip install -r requirements.txt
    fi
fi

if command -v node >/dev/null 2>&1; then
    node setup-host.mjs
else
    echo "⚠️ Node.js not found. Please install Node.js to register Chrome Native Messaging Host."
fi
