#!/bin/bash
# Long-running operator live pipeline.
# Args (e.g. `retrans serve`) are exec'd as-is. No-args default: image tools.
# Path: live source → yt-dlp/streamlink + ffmpeg → RTMP(S) (X Media Studio URL + key).
# Missing .env credentials: fail-soft (message + idle). Pipeline death: fail-hard.
# Not a clip-only batch job.
set -euo pipefail

if [[ $# -gt 0 ]]; then
  exec "$@"
fi

if [[ -z "${SOURCE_URL:-}" || -z "${X_RTMP_URL:-}" || -z "${X_STREAM_KEY:-}" ]]; then
  echo "Live worker needs .env (SOURCE_URL, X_RTMP_URL, X_STREAM_KEY; copy .env.example)." >&2
  echo "Idling. Set those variables and recreate the container to start the pipeline." >&2
  exec sleep infinity
fi

case "${X_RTMP_URL}" in
  rtmp://*|rtmps://*) ;;
  *)
    echo "X_RTMP_URL must be rtmp:// or rtmps:// (operator ingest from X Media Studio)" >&2
    exit 1
    ;;
esac

dest="${X_RTMP_URL%/}/${X_STREAM_KEY}"

echo "RETRANS live pipeline: source → yt-dlp/streamlink + ffmpeg → ${X_RTMP_URL%/}/<key>" >&2

if streamlink --can-handle-url "${SOURCE_URL}"; then
  streamlink \
    --stdout \
    --retry-streams 5 \
    --retry-max 0 \
    "${SOURCE_URL}" \
    best \
    | ffmpeg -hide_banner -fflags +genpts -i pipe:0 \
        -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p \
        -c:a aac -b:a 128k -ar 44100 -ac 2 \
        -f flv \
        "${dest}"
  exit $?
fi

yt-dlp --no-playlist -o - -f "best/bestvideo+bestaudio" "${SOURCE_URL}" \
  | ffmpeg -hide_banner -fflags +genpts -i pipe:0 \
      -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p \
      -c:a aac -b:a 128k -ar 44100 -ac 2 \
      -f flv \
      "${dest}"
