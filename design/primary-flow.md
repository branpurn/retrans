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

**Operator URL:** `http://127.0.0.1:8788` **only** (same origin serves UI + `/api`). **One Docker compose** is the operator form factor: that compose binds **127.0.0.1:8788 only**. Operators open that URL. Not Vite `5173`. Not a second published port. Not `0.0.0.0` / LAN / hotspot. Vite `5173` is not the operator path (dev proxy may still exist for Frontend work; operators open 8788).

Sign-in is **not** X OAuth. Sign-in is a Media Studio stream-key save (named keys; RTMP URL hidden by default).

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
- **Error pill** only after a real start failure (HTTP 400 or equivalent) or a usable status payload (`GET /api/live/status` HTTP 200) with nonempty `status.error` / `state === "error"` (or the same on a `sessions[]` entry). Idle + `error: null` (or empty) stays Idle / Preview. Never invent Error from a poll fail. **Not** from `GET /api/live/preview` 502 / probe fail (Drop-link helper only; see Beat 2).
- **Error sticks until Stop.** After the UI enters Error (start HTTP 400 / equivalent, or usable status with nonempty `status.error` / `state === "error"`, or a session row in that state), keep the pill Error and the error helper until the operator presses **Stop** for that session. Do **not** auto-flip Error → Idle / Preview / Stopped when a later successful status poll returns `idle` / empty error / no longer `error` (the ~5s auto-clear bug).
- **Stop clears Error.** `POST /api/live/stop` (or Stop click) is the dismiss path from Error. Body `{ session_id }` **or** `{ key_id }`. After Stop succeeds, normal status mapping resumes (Idle / Stopped per existing locks).
- **Stop enablement.** Stop is enabled while that session is LIVE **or** Error (so Error can be cleared). Concurrent sessions: each Beat 3 row has its own Stop.
- **Pill lock.** Exact `data-status` / backend → copy + tokens. Do not invent other labels. Beat 3 list pills are **per** `sessions[]` entry. Top-bar pill: Error if any session is Error; else LIVE if any is live; else Starting if any is starting; else Idle / Stopped / Preview per existing mapping.

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

1. `GET /api/live/keys`
2. Empty `keys` list (or first visit / GET fail treated as empty) → **Beat 1**
3. Any saved named key → skip to **Beat 2**

Forward only (still three beats — no fourth page):

- Beat 1 first Save success → Beat 2
- Beat 2 Continue → Beat 3

Same-beat / back links, not a settings maze:

- On Beat 1: **Add** another named key (Add + Save) stays on Beat 1
- On Beat 2: small **Change destination** / **Add key** link → Beat 1 (empty fields; never prefill secrets)
- On Beat 3: **Drop another** / back to Beat 2 with an unused named key. If no unused key, helper to add a key → Beat 1 (empty fields)

No other pages. No OAuth screens. No clip-post. No `/api/live/credentials` chrome.

## Beat 1 — Sign in

Shown when `GET /api/live/keys` → empty `keys` (or first visit). Also when the operator chooses Add key / Change destination from Beat 2 or Beat 3.

| Element | Rule |
| --- | --- |
| Title | `Sign in` — clickable `?` next to this title (same beat) |
| Helper (one short line) | `Save Media Studio RTMP once. Not X OAuth.` — default visible helper |
| Field | Optional short name — `type="text"` |
| Field | Stream key — `type="password"` (primary; **no** RTMP URL field by default) |
| Advanced | Collapsed disclosure **OFF** by default. When on: RTMP URL override (`type="text"`). Empty override = default ingest |
| List | Named key list — **names only**, never keys |
| Add | **Add** another named key on this beat (Add + Save via `PUT /api/live/keys`) |
| Delete | `DELETE /api/live/keys/<id>` (confirm is fine; not a settings page) |
| Primary | **Save** |

Default ingest (not a secret; document it): `rtmps://va.pscp.tv:443/x`. Hide the RTMP URL field unless Advanced is on.

- Save calls `PUT /api/live/keys` with the stream key + optional name + optional `rtmp_url` override. Omit `rtmp_url` to use the default ingest.
- On first Save success → Beat 2. Add + Save stays on Beat 1. Clear the key field from the DOM. **Never show secrets again after save.**
- Stream key stays `type="password"`. After Save, the key is **never shown again** (fields cleared from the DOM). `GET /api/live/keys` returns id + name (+ `in_use` if status does not already say so) **only** — never echo `rtmp_key`, `rtmp_url`, or the key value.
- If any named key exists at boot, skip this beat.
- Sign-in is a Media Studio stream-key save. Not X OAuth. No “Sign in with X” button.

### Sign in `?` help (same beat)

Clickable `?` next to the **Sign in** title. Show/hide short help on this beat (disclosure / inline panel). Stays inside the 480px one-beat console. No new route. No modal maze. No OAuth screen. Not a settings maze. Not a fifth block.

Default visible helper stays the one line: `Save Media Studio RTMP once. Not X OAuth.` The `?` does not replace that line.

Help copy — short steps only (exact path names):

1. Open studio.x.com (Creator / Media Studio Producer)
2. Sources → Create Source (RTMP)
3. Copy the stream key into the Sign in field (not a two-field URL + key form)

Also one short line in that help (not a Broadcast UI): **Broadcasts → Create Broadcast** + **Go Live** still happen on X after Retrans starts. That is not this beat. Do not add Broadcast UI here.

No extra Media Studio maze beyond this `?` disclosure. No settings page. No “Sign in with X”.

## Beat 2 — Drop link

| Element | Rule |
| --- | --- |
| Title | `Drop link` |
| Field | Single large URL field. Placeholder: `Paste YouTube live URL` |
| Preview | On blur / Enter, or a Preview control — preview card (fields below) |
| Destination | Compact named-key picker — unused keys only (names from `GET /api/live/keys`; in-use from `status.sessions[]`) |
| Gate | Checkbox, exact copy: `I have permission or fair use to retransmit this live.` |
| Primary | **Continue** (or **Next**) |

### Preview card chrome (Beat 2 + Beat 3 compact)

Consume `GET /api/live/preview` for `title` + `is_live`. Same LIVE badge + real title rules on the Beat 3 compact preview.

Preview card fields:

| Field | Rule |
| --- | --- |
| Thumbnail | Show when available |
| Title | Real `title` from `GET /api/live/preview` when present on **200 ok**. Never invent a synthetic `YouTube source <id>` placeholder. Never invent clip/VOD marketing copy. If `title` is empty **on 200 ok**, leave empty or show host-only. Do not use this empty-title rule for 502 / probe fail. |
| Host | Host from the source URL when available |
| LIVE badge | Existing `.live-badge` chrome / `--live` token. Show **iff** `is_live === true` on **200 ok**. Never from a failed preview. |

When the source is **actually live** (`GET /api/live/preview` **200 ok** and `is_live === true`):

- Show the **LIVE** badge on the preview card.
- Show the **real source title** from the preview payload (`title`). Not a synthetic `YouTube source <id>` placeholder.

When the source is **VOD / not live** (`GET /api/live/preview` **200 ok** and `is_live` is `false`):

- **No LIVE badge** (QA expected that).
- Still show the preview card with thumbnail + title/host when available (card ok; preview ok for Continue gating).
- Continue/Start stay gated by preview-ok rules already in this file (live-first product: non-live may fail Start with API error — do not add clip UI).

When `GET /api/live/preview` returns **502** `{ ok: false, error: "…" }` (yt-dlp fail / probe fail / off-air — same route as the Live API table; not a second preview path) or an equivalent non-OK probe fail from that endpoint:

- **Error helper** on Drop link: show the API `error` string **as-is** (redact rtmp secrets only). Do not invent copy like `status failed` or clip/VOD marketing.
- **No empty title card.** Do **not** show the preview card with blank title / empty chrome. Hide the preview card (preview not-ok). This is not the 200-ok empty-`title` case above.
- **No fake LIVE badge.** Never show LIVE from a failed preview.
- **Continue stays disabled** (preview not-ok).
- **Top-bar pill:** do **not** flip the status pill to Error solely from preview 502. Stay Idle (or the prior non-Error Drop-link pill). Transport Error pill / Error-sticks-until-Stop remains for start/status Error only — do not conflate preview probe fail with that.

Enable Continue only when **all** are true:

- preview ok
- ack checked
- a named key that is **not** already in a live/starting session is selected (names from `GET /api/live/keys`; in-use from `status.sessions[]`)

YouTube first. Non-YouTube: helper `YouTube first` (exact). Other URLs stay not-ok for preview.

Optional: small **Change destination** / **Add key** link (not a button row, not a settings page) that returns to Beat 1 with empty fields.

No RTMP fields on this beat. No start/stop. Preview payload has no RTMP fields — never display rtmp secrets from preview. Named-key picker shows **names only**.

## Beat 3 — Retrans

Keep three beats and 480px. Concurrent restreams live on this beat (not a fourth page). One named key per restream. Operator can run multiple live sources at once.

| Element | Rule |
| --- | --- |
| Sessions | Compact list from `status.sessions[]`: source + **named** key + per-session pill/status + **Stop** |
| Source | Compact source preview for the current start — same card fields as Beat 2 (thumbnail, real `title` when available, host, **LIVE** badge iff `is_live === true`) + the top-bar status pill |
| Primary | **Start live retrans** — enabled when ready |
| Another | **Drop another** / back to Beat 2 using an unused named key. If none unused, helper to add a key → Beat 1 |
| Danger | **Stop** — per session, enabled while that session is LIVE **or** Error |
| Helper | see below |

Ready for Start (does **not** disable Stop on Error / other live sessions):

- preview ok
- ack already checked (from Beat 2)
- selected unused named key (`key_id`)
- that key is not already `starting` or `live` in `sessions[]`

Stop stays enabled on a session in Error even when Start is not ready. Stop is the only dismiss path from that session’s Error.

Start calls `POST /api/live/start` with `{ source_url, key_id }` **only**. Do not send `rtmp_url` or `rtmp_key`. The named key was already saved on Beat 1.

Stop calls `POST /api/live/stop` with `{ session_id }` **or** `{ key_id }`.

Helper (exact; fully readable, never clipped):

- Default / non-LIVE non-Error: `Idle until ready`
- While LIVE: `Retransmitting live to X`
- On Error with a nonempty `status.error` / session `error` / start error string: show that API error string **as-is** (redact rtmp secrets only). Do not rewrite it.

**Not on this beat:** RTMP URL field, stream key field, destination form, clip, download, schedule, OAuth, settings. Sessions list shows **names only**, never keys.

After Start, `GET /api/live/status` (`sessions[]`) drives per-session pills (`starting` → Starting, then `live` → LIVE) except Error, which sticks until Stop. Poll fail stays the current pill (Idle on fresh load). Never invent Error from a poll fail.

## Live API (Frontend contract)

Operator path is **one Docker compose** → `http://127.0.0.1:8788` (same origin UI + `/api`). Vite may still proxy `/api` → `http://127.0.0.1:8788` for Frontend work; operators open 8788. Never `0.0.0.0`. No `/api/clip` route. No clip UI. No `/api/live/credentials` chrome — Sign-in consumes `/api/live/keys`.

These routes are the lock. Do not invent extra routes beyond keys list/add/delete + start/stop/status/preview.

| Method | Path | Body / response |
| --- | --- | --- |
| `GET` | `/api/live/keys` | List named keys. `200` with `keys[]` of `{ id, name }` plus `in_use` if `status.sessions[]` does not already say so. **Never** echo `rtmp_key`, `rtmp_url`, or the key value. Empty `keys` = not configured (Beat 1). |
| `PUT` | `/api/live/keys` | Add/update a named key. Body: stream key + optional `name` + optional `rtmp_url` override. Omit `rtmp_url` to use default ingest `rtmps://va.pscp.tv:443/x`. `200` success (id + name only). **Never** echo the key. |
| `DELETE` | `/api/live/keys/<id>` | Remove a named key. `200` success. **Never** echo secrets. |
| `GET` | `/api/live/preview` | Query `source_url`. `200 { "ok": true, "source_url": "…", "title": "…", "is_live": true \| false }`. Title from yt-dlp `-J` `title` (may be `""` if unknown). `is_live` true when `live_status` is `is_live` or JSON `is_live` is true. Confirmed `not_live` / `was_live` stay `200` + title + `is_live:false`. YouTube first. `400 { "ok": false, "error": "…" }` missing/invalid URL. `502 { "ok": false, "error": "…" }` when yt-dlp fails (not `200` empty/false). Drop-link chrome for that 502: Beat 2 Preview (hide card; `error` as-is; Continue disabled; pill stays Idle — not Transport Error). No ffmpeg / restream. Never `rtmp_url` / `rtmp_key` / `destination`. |
| `POST` | `/api/live/start` | `{ "source_url":"…", "key_id":"…" }` **only** → `200 { "ok": true, "state": "starting" }` (process up → later status `live`). Never `rtmp_url` / `rtmp_key`. `400` missing/invalid / not a live stream. `409` key already in a live/starting session. |
| `POST` | `/api/live/stop` | `{ "session_id":"…" }` **or** `{ "key_id":"…" }` → `200 { "ok": true, "state": "stopped" }` (also `200`/`ok` if that session already idle) |
| `GET` | `/api/live/preview` | Query `source_url`. `127.0.0.1:8788`. Response `{ "ok", "source_url", "title", "is_live" }` **only**. No `rtmp_url` / `rtmp_key`. Never echo secrets. **LIVE** badge iff `is_live === true` on 200 ok. Show real `title` (not a synthetic `YouTube source <id>` placeholder). Same-route **502** `{ ok: false, error }` chrome: Beat 2 Preview (hide card; no LIVE badge; `error` as-is; Continue disabled; pill stays Idle). |
| `GET` | `/api/live/status` | `200` includes `sessions[]` (concurrent restreams): `{ session_id, key_id, name, source_url, state, error }` — names only, never keys. `state` is `idle`\|`starting`\|`live`\|`error`\|`stopped`. Pill / Error-stick apply **per session** where chrome shows them. Never echo `rtmp_key` or `rtmp_url`. |

Responses **never** echo `rtmp_key` or `rtmp_url` (or the key value). Redact those substrings in any error string shown in the UI. `GET` never returns `rtmp_key` / `rtmp_url`.

`POST /api/live/start` does **not** accept raw destination fields. Destination is the selected named `key_id`.

Consume `GET /api/live/preview` for `title` + `is_live`. Status poll fail stays Idle (Error chrome locks above). Error sticks until Stop.

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

No settings pages. No clip-post. No clip download. No schedule. No OAuth screens. No showing keys after save. No `/api/live/credentials` chrome. No Media Studio maze beyond the Beat 1 `?` disclosure (same-beat inline help; default helper stays the one short line). No five-block 720px chrome. No Vite `5173` operator path. No second published port.

## Done when

Frontend can ship the three beats against this file without inventing chrome, OAuth, or clip UI. Beat 1 is keys-only Sign in (default ingest, Advanced off, named key list, clickable `?`). Beat 3 is concurrent `sessions[]` (one named key each). Operator form factor is one Docker compose on `http://127.0.0.1:8788`.
