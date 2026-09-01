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
