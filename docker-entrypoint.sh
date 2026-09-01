#!/bin/bash
# Long-running operator live pipeline.
# Prefer the Backend `retrans` CLI when installed; otherwise use image tools.
# Path: live source → yt-dlp/streamlink + ffmpeg → RTMP(S) (X Media Studio URL + key).
# Not a clip-only batch job.
set -euo pipefail

if [[ $# -gt 0 ]]; then
  exec "$@"
fi

if command -v retrans >/dev/null 2>&1; then
  exec retrans
fi

: "${SOURCE_URL:?set SOURCE_URL to the live source (YouTube first)}"
: "${X_RTMP_URL:?set X_RTMP_URL to the X Media Studio RTMP(S) ingest URL}"
: "${X_STREAM_KEY:?set X_STREAM_KEY to the X Media Studio stream key}"

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
