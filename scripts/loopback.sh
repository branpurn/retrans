#!/usr/bin/env bash
# Operator loopback: retrans serve on 127.0.0.1:8788 (dist/ + /api, same-origin).
# Never binds 0.0.0.0 / LAN / hotspot. No Vite operator. No prompts. Fail-hard.
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

if [[ ! -f "${ROOT}/dist/index.html" ]]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "dist/ missing and npm not on PATH. Run: npm ci && npm run build" >&2
    exit 1
  fi
  npm ci
  npm run build
fi

serve_pid=""

cleanup() {
  trap - EXIT INT TERM HUP
  if [[ -n "${serve_pid}" ]]; then
    if command -v pkill >/dev/null 2>&1; then
      pkill -P "${serve_pid}" 2>/dev/null || true
    fi
    kill "${serve_pid}" 2>/dev/null || true
  fi
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM HUP

retrans serve &
serve_pid=$!

# Fail-hard unless serve is on 127.0.0.1:8788.
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
  echo "fail-hard: retrans serve is not listening on 127.0.0.1:8788" >&2
  exit 1
fi

wait "${serve_pid}"
status=$?
exit "${status}"
