#!/usr/bin/env bash
# Operator loopback: retrans serve + Vite UI on 127.0.0.1 only.
# Never binds 0.0.0.0 / LAN / hotspot. No prompts. Fail-hard.
# Cleans up child processes on exit.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

if [[ -n "${HOST:-}" && "${HOST}" != "127.0.0.1" && "${HOST}" != "localhost" ]]; then
  echo "refusing HOST=${HOST}; operator loopback is 127.0.0.1 only" >&2
  exit 1
fi
export HOST=127.0.0.1
export PORT="${PORT:-8788}"

if ! command -v retrans >/dev/null 2>&1; then
  echo "retrans not on PATH. Install with: pip install -e ." >&2
  exit 1
fi
if ! command -v npm >/dev/null 2>&1; then
  echo "npm not on PATH." >&2
  exit 1
fi

serve_pid=""
ui_pid=""

cleanup() {
  trap - EXIT INT TERM HUP
  if [[ -n "${serve_pid}" ]]; then
    if command -v pkill >/dev/null 2>&1; then
      pkill -P "${serve_pid}" 2>/dev/null || true
    fi
    kill "${serve_pid}" 2>/dev/null || true
  fi
  if [[ -n "${ui_pid}" ]]; then
    kill "${ui_pid}" 2>/dev/null || true
    if command -v pkill >/dev/null 2>&1; then
      pkill -P "${ui_pid}" 2>/dev/null || true
    fi
  fi
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM HUP

retrans serve &
serve_pid=$!

# Fail-hard unless serve is on 127.0.0.1:8788. Do not start the UI first.
serve_up=0
for ((i = 0; i < 16; i++)); do
  if ! kill -0 "${serve_pid}" 2>/dev/null; then
    echo "retrans serve exited before listening on 127.0.0.1:8788" >&2
    exit 1
  fi
  if command -v curl >/dev/null 2>&1 \
      && curl -sf --max-time 1 "http://127.0.0.1:8788/api/live/status" >/dev/null 2>&1; then
    serve_up=1
    break
  fi
  if (echo >/dev/tcp/127.0.0.1/8788) >/dev/null 2>&1; then
    serve_up=1
    break
  fi
  sleep 0.5
done
if [[ "${serve_up}" -ne 1 ]]; then
  echo "fail-hard: retrans serve is not listening on 127.0.0.1:8788; UI not started" >&2
  exit 1
fi

npm run dev &
ui_pid=$!

# Fail-hard when the first child exits (portable: no wait -n).
while kill -0 "${serve_pid}" 2>/dev/null && kill -0 "${ui_pid}" 2>/dev/null; do
  sleep 1
done

status=1
if ! kill -0 "${serve_pid}" 2>/dev/null; then
  wait "${serve_pid}" || status=$?
else
  wait "${ui_pid}" || status=$?
fi
exit "${status}"
