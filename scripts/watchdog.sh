#!/usr/bin/env bash
# watchdog.sh — monitors the Zeno API server and restarts it if non-responsive.
#
# Usage: ./scripts/watchdog.sh [--port 8000] [--interval 30] [--failures 3]
# Run in a dedicated tmux pane; Ctrl+C to stop.

set -euo pipefail

PORT="${PORT:-8000}"
INTERVAL="${INTERVAL:-30}"        # seconds between checks
FAILURE_THRESHOLD="${THRESHOLD:-3}" # consecutive failures before restart
CHECK_URL="http://localhost:${PORT}/api/metadata"
CHECK_TIMEOUT=8                   # seconds for health check request
RESTART_CMD="uv run uvicorn src.api.app:app --reload --reload-dir src --host 0.0.0.0 --port ${PORT}"
LOG_PREFIX="[watchdog]"

# Parse flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --port)      PORT="$2";               CHECK_URL="http://localhost:${PORT}/api/metadata"; shift 2 ;;
    --interval)  INTERVAL="$2";           shift 2 ;;
    --failures)  FAILURE_THRESHOLD="$2";  shift 2 ;;
    *) echo "Unknown option: $1"; exit 1 ;;
  esac
done

log() { echo "$(date '+%Y-%m-%dT%H:%M:%S') ${LOG_PREFIX} $*"; }

kill_server() {
  log "Stopping existing uvicorn processes..."
  # Kill any uvicorn process on our port
  pkill -f "uvicorn src.api.app:app" 2>/dev/null || true
  sleep 2
  # Force-kill if still running
  pkill -9 -f "uvicorn src.api.app:app" 2>/dev/null || true
  sleep 1
}

start_server() {
  log "Starting server: ${RESTART_CMD}"
  # Start in background; stdout/stderr go to a log file
  nohup bash -c "cd /mnt/e/agentdev/projects/project-zeno && ${RESTART_CMD}" \
    >> /tmp/zeno-api.log 2>&1 &
  SERVER_PID=$!
  log "Server started (PID ${SERVER_PID})"
  # Give it time to bind the port
  sleep 10
}

check_health() {
  # Returns 0 if healthy, non-zero if not
  http_code=$(curl -s -o /dev/null -w "%{http_code}" \
    --max-time "${CHECK_TIMEOUT}" "${CHECK_URL}" 2>/dev/null) || return 1
  [[ "${http_code}" -ge 200 && "${http_code}" -lt 500 ]] && return 0 || return 1
}

# ─── main loop ────────────────────────────────────────────────────────────────
log "Watchdog started. Checking ${CHECK_URL} every ${INTERVAL}s (restart after ${FAILURE_THRESHOLD} consecutive failures)"

consecutive_failures=0

while true; do
  if check_health; then
    if [[ "${consecutive_failures}" -gt 0 ]]; then
      log "Server recovered after ${consecutive_failures} failure(s)"
    fi
    consecutive_failures=0
    log "Health OK (${CHECK_URL})"
  else
    consecutive_failures=$(( consecutive_failures + 1 ))
    log "Health FAIL #${consecutive_failures}/${FAILURE_THRESHOLD} — server did not respond in ${CHECK_TIMEOUT}s"

    if [[ "${consecutive_failures}" -ge "${FAILURE_THRESHOLD}" ]]; then
      log "Threshold reached — restarting server"
      kill_server
      start_server
      consecutive_failures=0

      # Verify restart succeeded
      log "Waiting for server to come up..."
      for i in $(seq 1 6); do
        sleep 5
        if check_health; then
          log "Server is healthy after restart"
          break
        fi
        log "Still waiting... (${i}/6)"
      done

      # Pre-warm Next.js route compilation so first user request is fast
      NEXT_WARMUP="/home/agentdev/Projects/factory/project-zeno-next/scripts/warmup.sh"
      if [[ -x "${NEXT_WARMUP}" ]]; then
        log "Running Next.js route warmup..."
        bash "${NEXT_WARMUP}" --wait 5 &
      fi
    fi
  fi

  sleep "${INTERVAL}"
done
