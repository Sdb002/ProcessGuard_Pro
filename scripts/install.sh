#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  ProcessGuard Pro v2.0 — Installer
#  Run once:  bash scripts/install.sh
#  Or let scripts/run.sh call it automatically on first run.
# ═══════════════════════════════════════════════════════════

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

banner() { echo -e "${CYAN}${BOLD}$1${NC}"; }
ok()     { echo -e "  ${GREEN}✓${NC}  $1"; }
warn()   { echo -e "  ${YELLOW}⚠${NC}  $1"; }
err()    { echo -e "  ${RED}✗${NC}  $1"; }
step()   { echo -e "\n${BOLD}[$1]${NC} $2"; }

echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║     ⚙  ProcessGuard Pro v2.0 — Installer    ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ── 1. OS check ──────────────────────────────────────────
step "1/8" "Checking OS and display server"
if [[ "$OSTYPE" != "linux"* ]]; then
    warn "This app targets Linux. You may encounter issues on $OSTYPE."
fi
if [ -z "$DISPLAY" ] && [ -z "$WAYLAND_DISPLAY" ]; then
    warn "No DISPLAY or WAYLAND_DISPLAY detected."
    warn "ProcessGuard Pro requires a graphical desktop environment."
    warn "(SSH sessions without X forwarding won't work for the GUI)"
fi
ok "OS check done"

# ── 2. Python 3.9+ ───────────────────────────────────────
step "2/8" "Checking Python 3.9+"
if ! command -v python3 &>/dev/null; then
    warn "Python3 not found — installing via apt..."
    sudo apt-get update -qq
    sudo apt-get install -y python3 python3-pip python3-venv
fi
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PY_MAJ=$(echo "$PY_VER" | cut -d. -f1)
PY_MIN=$(echo "$PY_VER" | cut -d. -f2)
if [ "$PY_MAJ" -lt 3 ] || ([ "$PY_MAJ" -eq 3 ] && [ "$PY_MIN" -lt 9 ]); then
    err "Python 3.9+ required (found $PY_VER)"
    exit 1
fi
ok "Python $PY_VER ✓"

# ── 3. System packages (Dear PyGui needs OpenGL + libGL) ─
step "3/8" "Installing system dependencies (OpenGL, libGL, libnotify)"
if command -v apt-get &>/dev/null; then
    sudo apt-get install -y --no-install-recommends \
        libgl1-mesa-glx libgl1 libglib2.0-0 \
        libnotify-bin python3-venv python3-pip \
        2>/dev/null || true
    ok "System packages installed"
else
    warn "apt-get not found — skipping system package install."
    warn "Make sure libGL.so.1 is available for Dear PyGui."
fi

# ── 4. Virtual environment ───────────────────────────────
step "4/8" "Setting up virtual environment"
if [ ! -d "$ROOT/venv" ]; then
    python3 -m venv "$ROOT/venv"
    ok "Created venv/"
else
    ok "venv/ already exists"
fi
source "$ROOT/venv/bin/activate"

# ── 5. pip upgrade ───────────────────────────────────────
step "5/8" "Upgrading pip"
pip install --quiet --upgrade pip
ok "pip upgraded"

# ── 6. Python packages ───────────────────────────────────
step "6/8" "Installing Python packages"
pip install --quiet -r "$ROOT/requirements.txt"
ok "psutil, dearpygui, plyer, pystray, Pillow installed"

# ── 7. Script permissions ────────────────────────────────
step "7/8" "Setting script permissions"
chmod +x "$ROOT/scripts/"*.sh
ok "All scripts made executable"

# ── 8. Directories ───────────────────────────────────────
step "8/8" "Creating required directories"
mkdir -p "$ROOT/logs" "$ROOT/reports" "$ROOT/assets"
ok "logs/ reports/ assets/ ready"

# ── Done ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   ✅  Installation complete!                 ║"
echo "  ║                                              ║"
echo "  ║   To run:                                    ║"
echo "  ║     bash scripts/run.sh                      ║"
echo "  ║                                              ║"
echo "  ║   In VSCode:                                 ║"
echo "  ║     Ctrl+Shift+B  →  Run ProcessGuard Pro    ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"
