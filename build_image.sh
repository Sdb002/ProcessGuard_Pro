#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  ProcessGuard Pro v2.0 — Docker Image Builder & Launcher
#  Usage:
#    bash build_image.sh            # build only
#    bash build_image.sh --run      # build + run
#    bash build_image.sh --push     # build + push to registry
# ═══════════════════════════════════════════════════════════

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
IMAGE_NAME="processguard-pro"
IMAGE_TAG="latest"
FULL_TAG="${IMAGE_NAME}:${IMAGE_TAG}"

BOLD='\033[1m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'

banner() { echo -e "\n${CYAN}${BOLD}$1${NC}"; }
ok()     { echo -e "  ${GREEN}✓${NC}  $1"; }
warn()   { echo -e "  ${YELLOW}⚠${NC}  $1"; }

echo ""
echo -e "${GREEN}${BOLD}"
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   🐳  ProcessGuard Pro — Docker Builder     ║"
echo "  ╚══════════════════════════════════════════════╝"
echo -e "${NC}"

# ── Check Docker ─────────────────────────────────────────
if ! command -v docker &>/dev/null; then
    echo -e "${RED}Docker not found. Install from https://docs.docker.com/get-docker/${NC}"
    exit 1
fi
ok "Docker found: $(docker --version | head -1)"

# ── Build ────────────────────────────────────────────────
banner "Building Docker image: ${FULL_TAG}"
cd "$ROOT"
docker build \
    --tag "${FULL_TAG}" \
    --file Dockerfile \
    --progress=plain \
    .

ok "Image built successfully: ${FULL_TAG}"
echo ""
echo "  Image size:"
docker images "${IMAGE_NAME}" --format "    {{.Repository}}:{{.Tag}}  {{.Size}}"

# ── Run (if --run flag) ───────────────────────────────────
if [[ "$1" == "--run" ]] || [[ "$2" == "--run" ]]; then
    banner "Launching ProcessGuard Pro container"

    # Allow X connections from Docker
    if command -v xhost &>/dev/null; then
        xhost +local:docker 2>/dev/null && ok "X11 access granted (xhost +local:docker)"
    else
        warn "xhost not found — X11 forwarding may not work"
    fi

    mkdir -p "$ROOT/logs" "$ROOT/reports"
    [ -f "$ROOT/config.json" ] || echo '{}' > "$ROOT/config.json"

    docker run --rm -it \
        --name processguard-pro \
        --pid=host \
        --network=host \
        -e DISPLAY="${DISPLAY:-:0}" \
        -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
        -v "$ROOT/logs:/app/logs" \
        -v "$ROOT/reports:/app/reports" \
        -v "$ROOT/config.json:/app/config.json" \
        "${FULL_TAG}"
fi

# ── Push (if --push flag) ─────────────────────────────────
if [[ "$1" == "--push" ]] || [[ "$2" == "--push" ]]; then
    if [ -z "$REGISTRY" ]; then
        warn "Set REGISTRY env var to push (e.g. REGISTRY=myuser docker build --push)"
    else
        banner "Pushing to registry: ${REGISTRY}/${FULL_TAG}"
        docker tag "${FULL_TAG}" "${REGISTRY}/${FULL_TAG}"
        docker push "${REGISTRY}/${FULL_TAG}"
        ok "Pushed to ${REGISTRY}/${FULL_TAG}"
    fi
fi

echo ""
echo -e "${GREEN}${BOLD}  Done.${NC}"
echo ""
echo "  To run manually:"
echo "    xhost +local:docker"
echo "    docker run --rm -it --pid=host --network=host \\"
echo "      -e DISPLAY=\$DISPLAY \\"
echo "      -v /tmp/.X11-unix:/tmp/.X11-unix \\"
echo "      -v \$(pwd)/logs:/app/logs \\"
echo "      -v \$(pwd)/reports:/app/reports \\"
echo "      ${FULL_TAG}"
echo ""
