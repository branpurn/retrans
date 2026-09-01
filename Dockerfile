# Operator-run live worker: yt-dlp/streamlink + ffmpeg → RTMP(S).
# Same image ships Vite dist/ so `retrans serve` hosts UI + /api on 127.0.0.1:8788.
# Not a clip-only batch image. Backend package layout (do not invent here):
#   retrans/sources/  retrans/ingest.py  retrans/segment.py  retrans/outputs/x.py
FROM node:22-bookworm AS ui

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html vite.config.js ./
COPY src ./src
RUN npm run build \
    && test -f /app/dist/index.html

FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 retrans

# Live pullers are image requirements (also expected as package deps once pyproject exists).
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir yt-dlp streamlink

WORKDIR /app
COPY . .
COPY --from=ui /app/dist ./dist

RUN if [ -f pyproject.toml ]; then pip install --no-cache-dir .; fi \
    && chmod +x /app/docker-entrypoint.sh \
    && test -f /app/dist/index.html

USER retrans
ENTRYPOINT ["/app/docker-entrypoint.sh"]
