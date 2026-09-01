# RETRANS

Public product name: **RETRANS**. Code and package: `retrans`.

retransmit YouTube (and other) live streams to X.com as X live. Extensible input sources; YouTube first. Code paths: `retrans`.

Success is live retrans via Media Studio RTMP + retrans bridge: a live YouTube (or other live) source comes out as X live. Not VOD clips. Not INIT/APPEND/FINALIZE clip posts as the product.

Wave 1 operator UI: paste a YouTube live URL → preview → Media Studio RTMP destination → permission / fair-use ack → start/stop **LIVE** retrans to X.

Not clip-post. Not VOD. Not file upload. Status language is live only (Idle | Preview | LIVE | Stopped | Error). Never Posted / Clip / Tweet / Upload.

Layout: [design/layout-v1.md](design/layout-v1.md)

- [Permission / fair use](docs/permission-fair-use.md)
- [X API notes](docs/x-api-notes.md)

There is **no public X API** to create a live broadcast or mint an RTMP key. Sending RTMP alone is **not** enough — the operator must create a source, create a broadcast, and click **Go Live** in Media Studio ([Restream](https://restream.io/learn/platforms/how-to-find-x-stream-key/), [Castr](https://docs.castr.com/en/articles/5119218-how-to-stream-live-video-to-x-formerly-twitter-using-castr), [vMix](https://www.vmix.com/knowledgebase/article.aspx/373/stream-to-x-using-custom-rtmp)).

Operator dependencies: **ffmpeg** and **yt-dlp** (streamlink optional fallback). Operator-run image: `docker compose up --build` (ffmpeg + yt-dlp + streamlink). Secrets via `.env` / env vars only (copy `.env.example`; never commit `.env`).

## Permission / fair use

This restreams a live source to the **operator’s** X account. The operator must have rights to the source. Restreaming someone else’s YouTube live without permission can violate YouTube’s Terms of Service and copyright. This is not legal advice. RETRANS is not a hidden bot.

## Operator setup (studio.x.com)

Requires X Premium / Premium+.

1. Open [https://studio.x.com](https://studio.x.com) (Media Studio **Producer**).
2. **Sources → Create Source** → type **RTMP**, pick a region close to you → copy the **RTMP(S) URL** and **stream key**. Do not commit these.
3. **Broadcasts → Create Broadcast** → select that source.
4. Start `retrans live` (or `retrans serve` + the operator UI) so ffmpeg is sending to that URL+key.
5. In Media Studio, **Go Live**.

```bash
export RETRANS_X_RTMP_URL='rtmps://…'
export RETRANS_X_RTMP_KEY='…'
```

## Install

```bash
pip install -e .
```

Package name: `retrans`. Console script: `retrans`.

## Product command

```bash
retrans live 'https://www.youtube.com/watch?v=…'
retrans resolve 'https://www.youtube.com/watch?v=…'
```

`retrans live` resolves the page URL (YouTube first, yt-dlp then streamlink) and restreams H.264 + AAC in FLV to the operator RTMP URL+key.

## Local HTTP control API (`retrans serve`)

`retrans serve` **must** listen on `127.0.0.1:8788`. `HOST=0.0.0.0` (and any LAN / hotspot / wildcard bind) is refused with a non-zero exit. There is no `/api/clip` route.

```bash
retrans serve
```

| Method | Path | Body / response |
| --- | --- | --- |
| `POST` | `/api/live/start` | JSON `{"source_url":"…","rtmp_url":"…","rtmp_key":"…"}` → `200 {"ok":true,"state":"starting"}` (process up → later status `live`). `400` missing/invalid fields. `409` already running. |
| `POST` | `/api/live/stop` | `200 {"ok":true,"state":"stopped"}` (also `200`/`ok` if already idle) |
| `GET` | `/api/live/status` | `200 {"ok":true,"state":"idle"\|"starting"\|"live"\|"error"\|"stopped","source_url":"…" or null,"error":null or string}` |

Responses **never** echo `rtmp_key` or `rtmp_url`.

## Operator UI (this PR)

Product string **RETRANS**. Code, files, and package: `retrans`. Chrome matches [design/layout-v1.md](design/layout-v1.md).

```bash
npm install
npm run dev      # Vite on 127.0.0.1; proxies /api → http://127.0.0.1:8788
npm run build    # static dist/ for Infra to serve
npm test
```

Do not bind or proxy `0.0.0.0`. Vite `server.host` is `127.0.0.1` only.

| Field | Env | Meaning |
| --- | --- | --- |
| `source_url` | — | Page URL to restream (YouTube first) |
| `rtmp_url` | `RETRANS_X_RTMP_URL` | RTMP(S) URL from studio.x.com → Sources → Create Source |
| `rtmp_key` | `RETRANS_X_RTMP_KEY` | Stream key (password). Never logged, never shown after submit. |

- **Start live retrans** only when: preview ok + `rtmp_url` + `rtmp_key` + fair-use ack + status not LIVE
- **Stop** only when LIVE
- Ack copy: `I have permission or fair use to retransmit this live.` (not legal advice)
- After Start, still Create Broadcast + Go Live in Media Studio
- No clip routes and no clip UI

## Debug aid (not the product)

```bash
retrans clip 'https://…' --start 00:00:00 --end 00:00:30 -o /tmp/debug.mp4
```

Clip cutter is a debug aid, not the product. Clip upload is fail / not default. Not in the operator GUI.
