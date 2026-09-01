# RETRANS

Public product name: **RETRANS**. Code and package: `retrans`.

retransmit YouTube (and other) live streams to X.com as X live. Extensible input sources; YouTube first. Code paths: `retrans`.

Success is live retrans via Media Studio RTMP + retrans bridge: a live YouTube (or other live) source comes out as X live. Not VOD clips. Not INIT/APPEND/FINALIZE clip posts as the product.

Wave 1 operator UI: paste a YouTube live URL → preview → Media Studio RTMP destination → permission / fair-use ack → start/stop **LIVE** retrans to X.

Not clip-post. Not VOD. Not file upload. Status language is live only (Idle | Preview | LIVE | Stopped | Error). Never Posted / Clip / Tweet / Upload.

Layout: [design/layout-v1.md](design/layout-v1.md)

- [Permission / fair use](docs/permission-fair-use.md)
- [X API notes](docs/x-api-notes.md)
- [Wave 1 test plan](docs/test-plan-wave1.md) — operator plan for live YouTube → operator RTMP. Plan only; not a live PASS. Live clicks wait for a Backend live-path SHA.

Wave 1 path: **live source URL → continuous live restream** to the operator’s RTMP endpoint (X Media Studio). Success is an on-air live at that destination — not a clip or VOD post.

There is **no public X API** to create a live broadcast or mint an RTMP key. Sending RTMP alone is **not** enough — the operator must create a source, create a broadcast, and click **Go Live** in Media Studio ([Restream](https://restream.io/learn/platforms/how-to-find-x-stream-key/), [Castr](https://docs.castr.com/en/articles/5119218-how-to-stream-live-video-to-x-formerly-twitter-using-castr), [vMix](https://www.vmix.com/knowledgebase/article.aspx/373/stream-to-x-using-custom-rtmp)).

Operator dependencies: **ffmpeg** and **yt-dlp** (streamlink optional fallback). Operator-run image: `docker compose up --build` (ffmpeg + yt-dlp + streamlink). Secrets via `.env` / env vars only (copy `.env.example`; never commit `.env`).

## Operator loopback (one command)

UI + `retrans serve` together, both on `127.0.0.1` only (never `0.0.0.0` / LAN / hotspot).

Linux + Docker (host network so `retrans serve` can bind `127.0.0.1:8788` on the host; publishing `8788:8788` is forbidden because that would require listen `0.0.0.0` inside the container):

```bash
docker compose --profile loopback up --build
```

Without Docker (`pip install -e .` and `npm install` first):

```bash
./scripts/loopback.sh
```

CI checks that `HOST=0.0.0.0 ./scripts/loopback.sh` is refused (non-zero; no bind). Both paths fail-hard if `retrans serve` is not listening on `127.0.0.1:8788`; the UI is not started until that loopback probe succeeds.

Then open the Vite URL (typically `http://127.0.0.1:5173`). Control API: `http://127.0.0.1:8788`. Default `docker compose up` remains the live ffmpeg worker (no host port).

## Sign in → Drop link → Retrans (loopback, 127.0.0.1 only)

Operator run path on loopback `127.0.0.1` only — never `0.0.0.0` / LAN / hotspot. Live page URL only. No clip path. No VOD.

1. **Sign in:** operator supplies X Media Studio RTMP URL + stream key (env `RETRANS_X_RTMP_URL` / `RETRANS_X_RTMP_KEY` or the UI fields). Do not commit secrets.
2. **Drop link:** paste/drop a live YouTube (or other live) page URL. Not a VOD/clip file.
3. **Retrans:** fair-use ack, then Start LIVE. Still Create Broadcast + Go Live in Media Studio.

How to run that path locally:

- `docker compose --profile loopback up --build` (Linux host network) OR `./scripts/loopback.sh`
- Open http://127.0.0.1:5173 — never `0.0.0.0`
- Control API http://127.0.0.1:8788

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
| `POST` | `/api/live/start` | JSON `{"source_url":"…","rtmp_url":"…","rtmp_key":"…"}` → `200 {"ok":true,"state":"starting"}` (process up → later status `live`). `400` missing/invalid fields **or not a live stream** (VOD / clip / upcoming / ended — ffmpeg/RTMP are not started). `409` already running. |
| `POST` | `/api/live/stop` | `200 {"ok":true,"state":"stopped"}` (also `200`/`ok` if already idle) |
| `GET` | `/api/live/status` | `200 {"ok":true,"state":"idle"\|"starting"\|"live"\|"error"\|"stopped","source_url":"…" or null,"error":null or string}` |

Responses **never** echo `rtmp_key` or `rtmp_url`. If ffmpeg exits unexpectedly (non-zero **or** zero without an operator stop), `GET /api/live/status` becomes `state=error` with a redacted reason — not a stuck `live` or a clean `stopped`. Operator `POST /api/live/stop` is still `stopped`. After `error`, `stopped`, or `idle`, `POST /api/live/start` starts a new session on the same serve process (no restart required) and clears the previous error. `409` already-running is only when a session is actually `starting` or `live`.

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
