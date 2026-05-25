#!/bin/bash
# ProcessGuard Pro v2.0 — One-Click Runner
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d "$ROOT/venv" ]; then
    echo "First run — running installer..."
    bash "$ROOT/scripts/install.sh"
fi

source "$ROOT/venv/bin/activate"
echo ""
echo "  ⚙  Starting ProcessGuard Pro v2.0..."
echo "  Press Ctrl+C to quit."
echo ""
python3 "$ROOT/main.py"
