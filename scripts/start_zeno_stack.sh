#!/usr/bin/env bash
# Full Zeno stack startup: download datasets → validate → update .env → rebuild → start API + frontend
set -e
LOG=/tmp/zeno_startup.log
exec > >(tee -a "$LOG") 2>&1

echo "========================================"
echo "ZENO STACK STARTUP — $(date)"
echo "========================================"

ZENO=/mnt/e/agentdev/projects/project-zeno
ZENO_NEXT=/mnt/e/agentdev/projects/project-zeno-next

# ── Step 1: Download zarr datasets ───────────────────────────────────────────
echo ""
echo "Step 1: Downloading GFW Pro zarr datasets..."
cd "$ZENO"
uv run python3 /mnt/e/agentdev/projects/project-zeno/scripts/download_gfwpro.py
echo "Step 1 DONE"

# ── Step 2: Update .env — set GFW_PRO_DATA_PATH ──────────────────────────────
echo ""
echo "Step 2: Setting GFW_PRO_DATA_PATH in .env..."
if grep -q "^# GFW_PRO_DATA_PATH" "$ZENO/.env"; then
    sed -i 's|^# GFW_PRO_DATA_PATH=.*|GFW_PRO_DATA_PATH=/mnt/e/datasets/gfwpro|' "$ZENO/.env"
    echo "  Uncommented GFW_PRO_DATA_PATH=/mnt/e/datasets/gfwpro"
elif grep -q "^GFW_PRO_DATA_PATH" "$ZENO/.env"; then
    sed -i 's|^GFW_PRO_DATA_PATH=.*|GFW_PRO_DATA_PATH=/mnt/e/datasets/gfwpro|' "$ZENO/.env"
    echo "  Updated GFW_PRO_DATA_PATH=/mnt/e/datasets/gfwpro"
else
    echo "GFW_PRO_DATA_PATH=/mnt/e/datasets/gfwpro" >> "$ZENO/.env"
    echo "  Added GFW_PRO_DATA_PATH=/mnt/e/datasets/gfwpro"
fi
echo "Step 2 DONE"

# ── Step 3: Rebuild Docker API image ─────────────────────────────────────────
echo ""
echo "Step 3: Rebuilding API Docker image (picks up new deps + libgdal-dev)..."
cd "$ZENO"
docker compose -f docker-compose.dev.yaml build api
echo "Step 3 DONE"

# ── Step 4: Kill any existing API session and restart ────────────────────────
echo ""
echo "Step 4: Starting API (port 8000)..."
tmux kill-session -t zeno-api 2>/dev/null || true
tmux new-session -d -s zeno-api -c "$ZENO" \
    "bash -lc 'make api 2>&1 | tee /tmp/zeno-api.log'"

# Wait up to 30s for API to come up
echo "  Waiting for API health check..."
for i in $(seq 1 30); do
    sleep 2
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "  API is UP (after ${i}x2s)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  WARNING: API health check timed out — check /tmp/zeno-api.log"
    fi
done
echo "Step 4 DONE"

# ── Step 5: Start Next.js frontend ───────────────────────────────────────────
echo ""
echo "Step 5: Starting Next.js frontend (port 3000)..."
tmux kill-session -t zeno-next 2>/dev/null || true
tmux new-session -d -s zeno-next -c "$ZENO_NEXT" \
    "bash -lc 'pnpm dev 2>&1 | tee /tmp/zeno-next.log'"

# Wait up to 30s for Next.js to come up
echo "  Waiting for Next.js..."
for i in $(seq 1 30); do
    sleep 2
    if curl -sf http://localhost:3000 > /dev/null 2>&1; then
        echo "  Next.js is UP (after ${i}x2s)"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "  WARNING: Next.js health check timed out — check /tmp/zeno-next.log"
    fi
done
echo "Step 5 DONE"

echo ""
echo "========================================"
echo "STACK READY"
echo "  Frontend : http://localhost:3000"
echo "  API      : http://localhost:8000"
echo "  Log      : /tmp/zeno_startup.log"
echo "  API log  : /tmp/zeno-api.log"
echo "  FE log   : /tmp/zeno-next.log"
echo "========================================"
