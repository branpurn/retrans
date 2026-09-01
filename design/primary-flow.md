# Primary operator flow

Operator UI for **RETRANS** (code/repo: `retrans`). Live YouTube → X. Three beats. Localhost.

This file is the **only chrome** for the operator UI. Wave 1 five-block layout in [layout-v1.md](layout-v1.md) is superseded. Keep layout-v1 pill/token locks as the status-pill reference.

Frontend owns this UI. Implement these rules now.

## Product

RETRANS operator. Live YouTube → X. Three beats. Localhost.

1. Sign in
2. Drop link
3. Retrans

True **LIVE** only. Not clip-post. Not VOD. Not file upload. Never Posted / Clip / Tweet / Upload.

Bind and proxy **127.0.0.1 only**. Never `0.0.0.0`, LAN, or hotspot.

Sign-in is **not** X OAuth. Sign-in is a one-time Media Studio RTMP save.

## Chrome

- Console: `min-height: 100vh`, max-width **480px** (narrow primary — not the old 720px five-block maze), **24px** pad.
- Do **not** clip helpers with `overflow: hidden` on `html`, `body`, `#app`, or the body. Allow scroll if needed.
- Top bar **48px** (`--bar`): **RETRANS** left, status pill right.
- Pill states from [layout-v1.md](layout-v1.md): Idle | Preview | Starting | LIVE | Stopped | Error — same copy and tokens.
- Backend `starting` → pill **Starting** (not Preview). Backend `live` → **LIVE**. Backend `stopped` → **Stopped**.
- Gap 12 (`--gap`) between stacked controls on the current beat.
- Type (from layout-v1): 13/18 body, 15/22 title, `font-family: ui-sans-serif, system-ui, sans-serif`. Buttons 32px tall, pad 12, radius `--radius`.
- Show **one beat at a time**. No five-block stack. No settings pages.

### Status rules (from layout-v1 Error chrome)

- **Idle-on-poll-fail.** Boot `GET /api/live/status` failure and mid-session status poll / network failures MUST keep the current pill (fresh load = Idle). Never flip the pill to Error for a failed status poll. Never invent helper text like `status failed`.
- **Error pill** only after a real start failure (HTTP 400 or equivalent) or a usable status payload (`GET /api/live/status` HTTP 200) with nonempty `status.error` / `state === "error"`. Idle + `error: null` (or empty) stays Idle / Preview. Never invent Error from a poll fail.
- **Error sticks until Stop.** After the UI enters Error (start HTTP 400 / equivalent, or usable status with nonempty `status.error` / `state === "error"`), keep the pill Error and the error helper until the operator presses **Stop**. Do **not** auto-flip Error → Idle / Preview / Stopped when a later successful status poll returns `idle` / empty error / no longer `error` (the ~5s auto-clear bug).
- **Stop clears Error.** `POST /api/live/stop` (or Stop click) is the dismiss path from Error. After Stop succeeds, normal status mapping resumes (Idle / Stopped per existing locks).
- **Stop enablement.** Stop is enabled while LIVE **or** while Error (so Error can be cleared).
- **Pill lock.** Exact `data-status` / backend → copy + tokens. Do not invent other labels.

| data-status / backend | Pill copy (exact) | Tokens |
| --- | --- | --- |
| idle | Idle | bg `var(--line)`, color `var(--ink)` |
| preview | Preview | bg `#243447`, color `var(--accent)` |
| starting | Starting | bg `var(--warn)`, color `#0f1419` |
| live | LIVE | bg `var(--live)`, color `#fff` |
| stopped | Stopped | bg `var(--line)`, color `var(--muted)` |
| error | Error | bg `var(--stop)`, color `#fff` |

`--warn` stays `#f59e0b`.

## Boot / routing

On load:

1. `GET /api/live/credentials`
2. `configured: false` (or first visit / GET fail treated as not configured) → **Beat 1**
3. `configured: true` → skip to **Beat 2**

Forward only:

- Beat 1 Save success → Beat 2
- Beat 2 Continue → Beat 3

Optional, not a settings maze:

- On Beat 2 only: small **Change destination** link → Beat 1 (empty fields; never prefill secrets)

No other pages. No OAuth screens. No multi-dest. No clip-post.

## Beat 1 — Sign in

Shown when `GET /api/live/credentials` → `{ configured: false }` (or first visit).

| Element | Rule |
| --- | --- |
| Title | `Sign in` |
| Helper (one short line) | `Save Media Studio RTMP once. Not X OAuth.` |
| Field | RTMP URL — `type="text"` |
| Field | Stream key — `type="password"` |
| Primary | **Save** |

- Save calls `PUT /api/live/credentials` with `{ rtmp_url, rtmp_key }` only.
- On success → Beat 2. Clear the fields from the DOM. **Never show secrets again after save.**
- If `configured: true` at boot, skip this beat.
- No Media Studio walkthrough, no Create Broadcast maze, no extra helpers beyond that one line.
- Not X OAuth. No “Sign in with X” button.

## Beat 2 — Drop link

| Element | Rule |
| --- | --- |
| Title | `Drop link` |
| Field | Single large URL field. Placeholder: `Paste YouTube live URL` |
| Preview | On blur / Enter, or a Preview control — preview card (fields below) |
| Gate | Checkbox, exact copy: `I have permission or fair use to retransmit this live.` |
| Primary | **Continue** (or **Next**) |

### Preview card chrome (Beat 2 + Beat 3 compact)

Consume `GET /api/live/preview` for `title` + `is_live`. Same LIVE badge + real title rules on the Beat 3 compact preview.

Preview card fields:

| Field | Rule |
| --- | --- |
| Thumbnail | Show when available |
| Title | Real `title` from `GET /api/live/preview` when present. Never invent a synthetic `YouTube source <id>` placeholder. Never invent clip/VOD marketing copy. If `title` is empty, leave empty or show host-only. |
| Host | Host from the source URL when available |
| LIVE badge | Existing `.live-badge` chrome / `--live` token. Show **iff** `is_live === true`. |

When the source is **actually live** (`is_live === true`):

- Show the **LIVE** badge on the preview card.
- Show the **real source title** from the preview payload (`title`). Not a synthetic `YouTube source <id>` placeholder.

When the source is **VOD / not live** (`is_live` is not `true`):

- **No LIVE badge** (QA expected that).
- Still show the preview card with thumbnail + title/host when available.
- Continue/Start stay gated by preview-ok rules already in this file (live-first product: non-live may fail Start with API error — do not add clip UI).

Enable Continue only when **all** are true:

- preview ok
- ack checked
- credentials configured (`GET /api/live/credentials` → `configured: true`)

YouTube first. Non-YouTube: helper `YouTube first` (exact). Other URLs stay not-ok for preview.

Optional: small **Change destination** link (not a button row, not a settings page) that returns to Beat 1 with empty fields.

No RTMP fields on this beat. No start/stop. Preview payload has no RTMP fields — never display rtmp secrets from preview.

## Beat 3 — Retrans

| Element | Rule |
| --- | --- |
| Source | Compact source preview — same card fields as Beat 2 (thumbnail, real `title` when available, host, **LIVE** badge iff `is_live === true`) + the top-bar status pill |
| Primary | **Start live retrans** — enabled when ready |
| Danger | **Stop** — enabled while LIVE **or** Error |
| Helper | see below |

Ready for Start (does **not** disable Stop on Error):

- preview ok
- ack already checked (from Beat 2)
- credentials configured
- status is not `starting` and not `live`

Stop stays enabled on Error even when Start is not ready. Stop is the only dismiss path from Error.

Start calls `POST /api/live/start` with `{ source_url }` **only**. Do not send `rtmp_url` or `rtmp_key`. Credentials were already saved on Beat 1.

Helper (exact; fully readable, never clipped):

- Default / non-LIVE non-Error: `Idle until ready`
- While LIVE: `Retransmitting live to X`
- On Error with a nonempty `status.error` / start error string: show that API error string **as-is** (redact rtmp secrets only). Do not rewrite it.

**Not on this beat:** RTMP URL, stream key, destination form, clip, download, schedule, OAuth, settings.

After Start, `GET /api/live/status` drives the pill (`starting` → Starting, then `live` → LIVE) except Error, which sticks until Stop. Poll fail stays the current pill (Idle on fresh load). Never invent Error from a poll fail.

## Live API (Frontend contract)

Localhost only. Vite proxies `/api` → `http://127.0.0.1:8788`. Never `0.0.0.0`. No `/api/clip` route. No clip UI.

| Method | Path | Body / response |
| --- | --- | --- |
| `PUT` | `/api/live/credentials` | `{ "rtmp_url":"…", "rtmp_key":"…" }` → `200` success. Never echo secrets. |
| `GET` | `/api/live/credentials` | `200 { "configured": true \| false }` **only**. Never echo `rtmp_url` or `rtmp_key`. |
| `GET` | `/api/live/preview` | Query `source_url`. `200 { "ok": true, "source_url": "…", "title": "…", "is_live": true \| false }`. Title from yt-dlp `-J` `title` (may be `""` if unknown). `is_live` true when `live_status` is `is_live` or JSON `is_live` is true. Confirmed `not_live` / `was_live` stay `200` + title + `is_live:false`. YouTube first. `400 { "ok": false, "error": "…" }` missing/invalid URL. `502 { "ok": false, "error": "…" }` when yt-dlp fails (not `200` empty/false). No ffmpeg / restream. Never `rtmp_url` / `rtmp_key` / `destination`. |
| `POST` | `/api/live/start` | `{ "source_url":"…" }` **only** → `200 { "ok": true, "state": "starting" }` (process up → later status `live`). `400` missing/invalid / not a live stream. `409` already running. |
| `POST` | `/api/live/stop` | existing live API — `200 { "ok": true, "state": "stopped" }` (also `200`/`ok` if already idle) |
| `GET` | `/api/live/preview` | Query `source_url`. `127.0.0.1:8788`. Response `{ "ok", "source_url", "title", "is_live" }` **only**. No `rtmp_url` / `rtmp_key`. Never echo secrets. **LIVE** badge iff `is_live === true`. Show real `title` (not a synthetic `YouTube source <id>` placeholder). |
| `GET` | `/api/live/status` | existing live API — `200 { "ok": true, "state": "idle"\|"starting"\|"live"\|"error"\|"stopped", "source_url": "…" or null, "error": null or string }` |

Responses **never** echo `rtmp_key` or `rtmp_url`. Redact those substrings in any error string shown in the UI.

`POST /api/live/start` does **not** accept destination fields in the operator UI. Destination is the saved credentials.

Keep stop/status as the existing live API. Consume `GET /api/live/preview` for `title` + `is_live`. Status poll fail stays Idle (Error chrome locks above). Error sticks until Stop.

## Tokens

Reuse [layout-v1.md](layout-v1.md) `:root` tokens:

```css
:root {
  --bg: #0f1419;
  --panel: #1a2129;
  --ink: #e7ecf1;
  --muted: #8b98a5;
  --line: #2c3640;
  --accent: #1d9bf0;
  --live: #16a34a;
  --stop: #dc2626;
  --warn: #f59e0b;
  --radius: 8px;
  --gap: 12px;
  --bar: 48px;
}
```

## Out of primary

No settings pages. No multi-dest. No clip-post. No clip download. No schedule. No OAuth screens. No maze of Media Studio helpers beyond the one short line on Beat 1. No five-block 720px chrome.

## Done when

Frontend can ship the three beats against this file without inventing chrome, OAuth, or clip UI.
