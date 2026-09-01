# Primary operator flow

Operator UI for **RETRANS** (code/repo: `retrans`). Live YouTube → X. Three beats. Localhost.

This file is the **only chrome** for the operator UI. Wave 1 five-block layout in [layout-v1.md](layout-v1.md) is superseded. Keep layout-v1 pill/token locks as the status-pill reference.

Frontend owns this UI. Implement these rules now.

## Product

RETRANS operator. Live YouTube → X. Three beats. Localhost.

1. Keys / Configuration
2. Drop link
3. Retrans

These are the three **pane menu** panes (Designer lock labels: **Keys** / **Drop link** / **Outbound**). Not a fourth beat.

**LIVE** first. Playlist on Drop link / Retrans may include **live or VOD** page URLs that roll (YouTube first). Not clip-post. Not file upload. Never Posted / Clip / Tweet / Upload.

Bind and proxy **127.0.0.1 only**. Never `0.0.0.0`, LAN, or hotspot.

**Operator URL:** `http://127.0.0.1:8788` **only** (same origin serves UI + `/api`). **One Docker compose** is the operator form factor: that compose binds **127.0.0.1:8788 only**. Operators open that URL. Not Vite `5173`. Not a second published port. Not `0.0.0.0` / LAN / hotspot. Vite `5173` is not the operator path (dev proxy may still exist for Frontend work; operators open 8788).

Beat 1 is **Keys / Configuration** — named Media Studio stream-key save (RTMP URL hidden by default). Not a Sign-in gate. Not X OAuth. No “Sign in with X”.

## Chrome

- Console: `min-height: 100vh`, max-width **480px** (narrow primary — not the old 720px five-block maze), **24px** pad.
- Do **not** clip helpers with `overflow: hidden` on `html`, `body`, `#app`, or the body. Allow scroll if needed.
- Top bar **48px** (`--bar`): **RETRANS** left, status pill right.
- Pill states from [layout-v1.md](layout-v1.md): Idle | Preview | Starting | LIVE | Stopped | Error — same copy and tokens.
- Backend `starting` → pill **Starting** (not Preview). Backend `live` → **LIVE**. Backend `stopped` → **Stopped**.
- Gap 12 (`--gap`) between stacked controls on the current beat.
- Type (from layout-v1): 13/18 body, 15/22 title, `font-family: ui-sans-serif, system-ui, sans-serif`. Buttons 32px tall, pad 12, radius `--radius`.
- Show **one beat at a time**. Always-visible compact **3-item pane menu** switches them (**Keys** / **Drop link** / **Outbound**). No five-block stack. No settings pages. Not a hamburger. Not a fourth beat.

### Status rules (from layout-v1 Error chrome)

- **Idle-on-poll-fail.** Boot `GET /api/live/status` failure and mid-session status poll / network failures MUST keep the current pill (fresh load = Idle). Never flip the pill to Error for a failed status poll. Never invent helper text like `status failed`.
- **Error pill** only after a real start failure (HTTP 400 or equivalent) or a usable status payload (`GET /api/live/status` HTTP 200) with nonempty `status.error` / `state === "error"` (or the same on a `sessions[]` entry). Idle + `error: null` (or empty) stays Idle / Preview. Never invent Error from a poll fail. **Not** from `GET /api/live/preview` 502 / probe fail (Drop-link helper only; see Beat 2).
- **Error sticks until Stop.** After the UI enters Error (start HTTP 400 / equivalent, or usable status with nonempty `status.error` / `state === "error"`, or a session row in that state), keep the pill Error and the error helper until the operator presses **Stop** for that session. Do **not** auto-flip Error → Idle / Preview / Stopped when a later successful status poll returns `idle` / empty error / no longer `error` (the ~5s auto-clear bug).
- **Stop clears Error.** `POST /api/live/stop` (or Stop click) is the dismiss path from Error. Body `{ session_id }` **or** `{ key_id }`. After Stop succeeds, normal status mapping resumes (Idle / Stopped per existing locks).
- **Stop enablement.** Exactly **one** Stop per session on Beat 3 (the existing per-session Danger Stop → `POST /api/live/stop`). Enabled while that session is Starting, LIVE, **or** Error (so Waiting is not a trap). Concurrent sessions: one Stop per session row — not two. Native video pause is not Stop. KISS FAIL if two Stops appear.
- **Pill lock.** Exact `data-status` / backend → copy + tokens. Do not invent other labels. Beat 3 list pills are **per** `sessions[]` entry. Top-bar pill: Error if any session is Error; else LIVE if any is live; else Starting if any is starting; else Idle / Stopped / Preview per existing mapping.
- **Natural playlist end is not Error.** When the current item ends (live ends or VOD finishes) and the playlist is empty / exhausted (no next URL), map to Idle / Stopped per existing status locks. Do **not** invent Error from that natural end. Mid-item start/status Error still sticks until Stop.

| data-status / backend | Pill copy (exact) | Tokens |
| --- | --- | --- |
| idle | Idle | bg `var(--line)`, color `var(--ink)` |
| preview | Preview | bg `#243447`, color `var(--accent)` |
| starting | Starting | bg `var(--warn)`, color `#0f1419` |
| live | LIVE | bg `var(--live)`, color `#fff` |
| stopped | Stopped | bg `var(--line)`, color `var(--muted)` |
| error | Error | bg `var(--stop)`, color `#fff` |

`--warn` stays `#f59e0b`.

## Playlist chrome (KISS)

Chrome lock for Drop link / Retrans. Backend ingest owns roll. No extra routes. Do **not** restomp Keys / Configuration (Beat 1).

1. **Ordered source-URL list** on Beat 2 (Drop link). Operator can add / reorder / remove page URLs. Items may be **live or VOD** (YouTube first). Not clip UI. Not file upload. Not Sign-in.
2. **Selected named key stays** for the whole playlist run (same `key_id` across roll). Do not force re-Select on each item.
3. When the **current** item ends (live ends or VOD finishes), **roll to the next** URL in order automatically with that same named key. **Stop** still stops the session. Empty / exhausted playlist → Idle / Stopped per existing status locks. Do not invent Error from a natural end.
4. Keep 3-beat 480px. Beat 3 shows the current item + compact playlist position (e.g. `2/5`) without a settings maze. Preview / LIVE badge rules still apply per current item (LIVE badge iff `is_live === true` on 200 ok).
5. Product “True LIVE only / Not VOD” is softened only so the playlist may include VOD items that roll. Still **not** clip-post, not file upload, never Posted / Clip / Tweet / Upload UI.

Outbound monitor (picture + sound of the encoded outbound) is **Beat 3 only**. Do not put it on Drop link or Keys / Configuration. Do not restomp this playlist chrome.

## Pane menu

One compact **3-item** menu on the existing 3-beat 480px console at `http://127.0.0.1:8788`. Brain-dead. Always visible. Selected item marked. One pane visible at a time. The menu switches the three existing panes — not a fourth beat, not a hamburger settings page, not tabs-as-settings, not a settings maze. Same origin **8788** only. No second port. No Vite `5173` operator path. No new API routes. No clip UI. No OAuth. No Sign-in framing.

Copywriter is off. Designer owns chrome labels. Frontend owns exact UI strings. Product RETRANS.

Menu labels (Designer lock, three items only):

1. **Keys** — opens Beat 1 Keys / Configuration. Do not rename that panel. Do not restomp Open / Edit / Select / Delete, Advanced collapsed, or `?` help.
2. **Drop link** — opens Beat 2 Drop link / playlist. Do not restomp ordered live+VOD URLs, named key stays, roll next, or the preview card.
3. **Outbound** — opens Beat 3 Retrans including the Outbound encode player. Do not restomp the Outbound spec: waiting then HLS picture + sound of the encoded RTMP (tee of X RTMP), not a dead blank during Starting, not a YouTube embed, not clip, not preview metadata.

Switching panes does **not** Stop a running session. The Outbound player still hides on Idle / Stopped and shows on Starting / LIVE per the existing Outbound spec.

Prefer this menu as the switcher so we do not grow a button row. Existing in-beat links (**Change destination** / **Keys**, **Drop another**) may remain as shortcuts **or** defer to the menu. Do not add extra nav.

## Boot / routing

On load:

1. `GET /api/live/keys`
2. Empty `keys` list (or first visit / GET fail treated as empty) → **Beat 1 (Keys / Configuration)** — menu **Keys** — so the operator can **Add**. Do **not** frame empty-keys as Sign in.
3. Keys present → still **Beat 1** (named-key list with Open / Edit / Select / Delete). Do **not** skip Keys because keys exist (that was the Sign-in gate).

The **pane menu** is how the operator switches after that. Keys / Configuration is **not** a Sign-in gate. Empty keys never mean “Sign in”. Saved named keys are not Delete-only.

**Drop link** still requires a selected named key (existing **Select** / first-**Save**-that-selects). Menu item **Drop link** with no selected key stays on Keys or shows the existing helper — do not invent a maze.

**Outbound** menu item opens Beat 3 (start/stop/sessions + Outbound player). Switching panes does not Stop a running session.

Forward / switch (still three panes — no fourth page). The pane menu is the switcher:

- Menu **Keys** / **Drop link** / **Outbound** → Beat 1 / Beat 2 / Beat 3
- Beat 1 **Select** (or first **Save** that also selects the new key) still selects the named key (existing Keys rule) and may land on Beat 2 as today — or the operator uses the **Drop link** menu item
- Beat 2 Continue may land on Beat 3 as today — or the operator uses the **Outbound** menu item

Prefer the menu so we do not grow a button row.

Same-beat / back links, not a settings maze (shortcuts — may remain **or** defer to the menu):

- On Beat 1: **Add** another named key (Add + Save) stays on Beat 1
- On Beat 2: small **Change destination** / **Keys** link → Beat 1 (the Keys / Configuration panel; empty Add / Edit fields; never prefill secrets) — or use the **Keys** menu item
- On Beat 3: **Drop another** / back to Beat 2 with an unused named key. If no unused key, helper to add a key → Beat 1 (Keys / Configuration; empty Add fields) — or use the **Drop link** / **Keys** menu items

No other pages. No OAuth screens. No clip-post. No `/api/live/credentials` chrome.

## Beat 1 — Keys / Configuration (menu pane **Keys**)

Shown when `GET /api/live/keys` → empty `keys` (or first visit) so the operator can **Add**. Also shown when keys are present (list is not Delete-only). Also when the operator chooses **Change destination** / **Keys** from Beat 2 or Beat 3.

This panel is **not** a Sign-in gate. Do not title, helper, or boot-copy it as Sign in. Not X OAuth. No “Sign in with X”.

| Element | Rule |
| --- | --- |
| Title | `Keys` / `Configuration` — clickable `?` next to this title (same beat). Designer owns the visual title. |
| Helper (one short line) | `Save a named Media Studio stream key.` — default visible helper. Not Sign in. Not X OAuth. |
| Field | Optional short name — `type="text"` |
| Field | Stream key — `type="password"` (primary; **no** RTMP URL field by default). On **Open** / **Edit**, this field is empty and never shows the old key. Empty key field on Save of an existing row = keep the existing key unless a new key is typed — say that clearly. Do not invent API fields beyond `PUT /api/live/keys`. |
| Advanced | Collapsed disclosure **OFF** by default. When on: RTMP URL override (`type="text"`). Empty override = default ingest |
| List | Named key list — **names only**, never keys. Each saved row MUST support the actions below (labels for Frontend; Designer owns visual labels) |
| Open / Edit | **Open** / **Edit** — reopen the row to edit name + replace stream key (password field; never show the old key value). Empty key field = keep existing key unless a new key is typed. Save uses `PUT /api/live/keys` (same Add/update route). |
| Select | **Select** — choose this key for Drop link / Retrans destination |
| Delete | **Delete** — `DELETE /api/live/keys/<id>` (confirm is fine; not a settings page) |
| Add | **Add** another named key on this beat (Add + Save via `PUT /api/live/keys`) |
| Primary | **Save** |

Default ingest (not a secret; document it): `rtmps://va.pscp.tv:443/x`. Hide the RTMP URL field unless Advanced is on.

- **Add** + **Save** calls `PUT /api/live/keys` with the stream key + optional name + optional `rtmp_url` override. Omit `rtmp_url` to use the default ingest.
- **Open** / **Edit** Save of an existing named key also uses `PUT /api/live/keys` (the existing Add/update route). Empty stream-key field on that update = keep the stored key; a typed value replaces it. Do not invent extra API fields or routes.
- First Save that also **Select**s the new key → Beat 2. Add + Save stays on Beat 1. **Select** on a saved row → Beat 2 (that key is the Drop link / Retrans destination).
- Clear the key field from the DOM after Save. **Never show secrets again after save.**
- Stream key stays `type="password"`. After Save, the key is **never shown again** (fields cleared from the DOM). `GET /api/live/keys` returns id + name (+ `in_use` if status does not already say so) **only** — never echo `rtmp_key`, `rtmp_url`, or the key value.
- Do **not** skip this beat because keys exist. Keys / Configuration is not a Sign-in gate.
- Not X OAuth. No “Sign in with X”.

### Keys / Configuration `?` help (same beat)

Clickable `?` next to the **Keys / Configuration** panel title. Show/hide short help on this beat (disclosure / inline panel). Stays inside the 480px one-beat console. No new route. No modal maze. No OAuth screen. Not a settings maze. Not a fifth block.

Default visible helper stays the one line: `Save a named Media Studio stream key.` The `?` does not replace that line.

Help copy — short steps only (exact path names):

1. Media Studio **Sources** → **Create Source** (RTMP)
2. Copy the stream key into the key field (not a two-field URL + key form)

Also one short line in that help (not a Broadcast UI): **Broadcasts → Create Broadcast** + **Go Live** still happen on X after Retrans starts. That is not this beat. Do not add Broadcast UI here.

No extra Media Studio maze beyond this `?` disclosure. No settings page. No “Sign in with X”. No Sign-in framing.

## Beat 2 — Drop link (menu pane **Drop link**)

Ordered **source-URL list** on this beat. Operator can add / reorder / remove page URLs. Items may be **live or VOD** (YouTube first). Not clip UI. Not file upload. Not Sign-in. Not a playlist editor maze — compact list inside the 480px beat.

| Element | Rule |
| --- | --- |
| Title | `Drop link` |
| Playlist | Ordered list of page URLs. Add / reorder / remove. Live or VOD. Compact — stays in 480px. No clip picker. No file upload. |
| Field | Add a page URL to the list. Placeholder: `Paste YouTube URL` (live or VOD). Large field. |
| Preview | Per item: on blur / Enter, or a Preview control — preview card (fields below). LIVE badge iff `is_live === true` on 200 ok for **that** item. |
| Destination | Compact named-key picker — unused keys only (names from `GET /api/live/keys`; in-use from `status.sessions[]`). The **selected** named key from Keys / Configuration **stays** for the whole playlist run (same `key_id` across roll). Do not force re-Select on each item. |
| Gate | Checkbox, exact copy: `I have permission or fair use to retransmit this live.` |
| Primary | **Continue** (or **Next**) |

### Preview card chrome (Beat 2 + Beat 3 compact)

Consume `GET /api/live/preview` for `title` + `is_live`. Same LIVE badge + real title rules on the Beat 3 compact preview. This card is **source preview** metadata. The Beat 3 **Outbound** player is the encoded outbound — not this card, not a YouTube embed.

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
- Continue/Start stay gated by preview-ok rules already in this file. VOD (`is_live === false` on 200 ok) is a valid playlist item (rolls; no LIVE badge). Do not add clip UI. Do not fail Start solely because an item is VOD.

When `GET /api/live/preview` returns **502** `{ ok: false, error: "…" }` (yt-dlp fail / probe fail / off-air — same route as the Live API table; not a second preview path) or an equivalent non-OK probe fail from that endpoint:

- **Error helper** on Drop link: show the API `error` string **as-is** (redact rtmp secrets only). Do not invent copy like `status failed` or clip/VOD marketing.
- **No empty title card.** Do **not** show the preview card with blank title / empty chrome. Hide the preview card (preview not-ok). This is not the 200-ok empty-`title` case above.
- **No fake LIVE badge.** Never show LIVE from a failed preview.
- **Continue stays disabled** (preview not-ok).
- **Top-bar pill:** do **not** flip the status pill to Error solely from preview 502. Stay Idle (or the prior non-Error Drop-link pill). Transport Error pill / Error-sticks-until-Stop remains for start/status Error only — do not conflate preview probe fail with that.

Enable Continue only when **all** are true:

- playlist has at least one page URL
- every listed URL is preview ok (200 ok; live or VOD)
- ack checked
- a named key that is **not** already in a live/starting session is selected (names from `GET /api/live/keys`; in-use from `status.sessions[]`). That same `key_id` stays for the whole playlist run.

YouTube first. Non-YouTube: helper `YouTube first` (exact). Other URLs stay not-ok for preview.

Optional: small **Change destination** / **Keys** link (not a button row, not a settings page) that returns to Beat 1 (Keys / Configuration panel; empty Add / Edit fields; never prefill secrets).

No RTMP fields on this beat. No start/stop. Preview payload has no RTMP fields — never display rtmp secrets from preview. Named-key picker shows **names only**.

## Beat 3 — Retrans (menu pane **Outbound**)

Keep three beats and 480px. Concurrent restreams live on this beat (not a fourth page). One named key per restream / playlist run. The selected named key **stays** for the whole playlist run (same `key_id` across roll). Do not force re-Select on each item. Operator can run multiple playlist sessions at once (unused keys).

| Element | Rule |
| --- | --- |
| Sessions | Compact list from `status.sessions[]`: current source + compact playlist position (e.g. `2/5`) + **named** key + per-session pill/status + **Stop** |
| Source | Compact source preview for the **current** item — same card fields as Beat 2 (thumbnail, real `title` when available, host, **LIVE** badge iff `is_live === true` on 200 ok for the current item) + playlist position (`2/5`) + the top-bar status pill. No playlist editor maze on this beat. This card is **not** the Outbound player. |
| Outbound | Compact native HTML `video` (or equivalent same-origin media element) on this existing 480px console. Visual label **Outbound** (Designer lock — not Preview, not YouTube, not Monitor maze, not Clip). During Starting, MUST NOT be a dead blank: waiting status **Waiting** (Designer lock) in the player area, paired with the existing Starting pill — not a second pill. When same-origin HLS segments exist (`/api/live/…` or `/live/…`), the same player plays picture + sound of the encoded outbound (tee of X RTMP). Not a YouTube embed. Not `GET /api/live/preview` metadata/thumbnail as a fake. Not clip. Not the Source preview card. One player per session row. See below. |
| Primary | **Start live retrans** — enabled when ready |
| Another | **Drop another** / back to Beat 2 using an unused named key (a new playlist run). If none unused, helper to add a key → Beat 1 |
| Danger | **Stop** — exactly **one** Stop per session (this existing Danger Stop → `POST /api/live/stop`). Stops the playlist run (not skip-current-only). Enabled while that session is Starting, LIVE, **or** Error (Waiting is not a trap). Native video pause is not Stop. KISS FAIL if two Stops appear (player Stop + session Stop, top-bar Stop + row Stop, duplicate buttons). Concurrent: one Stop per row — not two. |
| Helper | see below |

Ready for Start (does **not** disable Stop on Starting / Error / other live sessions):

- playlist preview ok (at least one URL; every listed URL 200 ok — live or VOD)
- ack already checked (from Beat 2)
- selected unused named key (`key_id`) — same key for the whole run
- that key is not already `starting` or `live` in `sessions[]`

Stop stays enabled on a session that is Starting, LIVE, or Error even when Start is not ready. Waiting is not a trap. Stop is the only dismiss path from that session’s Error.

Start calls `POST /api/live/start` with `{ source_urls, key_id }` (ordered list + named key). A single URL is a one-item `source_urls` list. Bare `source_url` + `key_id` may remain as a one-item playlist (Backend ingest owns that path). Do not send `rtmp_url` or `rtmp_key`. The named key was already saved / selected on Beat 1. Same `key_id` for the whole run.

**Roll next.** When the **current** item ends (live ends or VOD finishes), Backend ingest rolls to the **next** URL in order automatically with that same named key. Chrome consumes status: current `source_url` / `source_index` updates. Do not re-Select. Do not invent a next-item route.

**Stop** still stops the session (the playlist run). `POST /api/live/stop` with `{ session_id }` **or** `{ key_id }`.

**Empty / exhausted playlist** (current item ends and there is no next URL): Idle / Stopped per existing status locks. Do **not** invent Error from a natural live end or VOD finish.

Helper (exact; fully readable, never clipped):

- Default / non-LIVE non-Error: `Idle until ready`
- While LIVE: `Retransmitting live to X`
- On Error with a nonempty `status.error` / session `error` / start error string: show that API error string **as-is** (redact rtmp secrets only). Do not rewrite it.

**Not on this beat:** RTMP URL field, stream key field, destination form, clip, download, schedule, OAuth, settings. No YouTube embed / iframe / youtube.com player. No clip download from the Outbound player. Sessions list shows **names only**, never keys.

### Outbound (Beat 3 only)

While Retrans is running, the operator watches and hears the actual encoded outbound (the same bytes going to X RTMP) on `http://127.0.0.1:8788`. KISS player on this existing 3-beat 480px console. Designer owns the visual label **Outbound**. Frontend may use that word. Do not invent a settings heading. Copywriter is off — Frontend owns exact UI strings.

- **Where.** Beat 3 only. One compact player per session row (same named key / session). Keep 480px. No fourth page. Playlist roll: the player follows the **current** item’s outbound (same `key_id`). Do not restomp playlist `2/5` chrome.
- **Not a dead blank.** During session Starting, the Outbound pane MUST NOT be an empty/dead blank (no black void, no empty video with nothing to read).
- **Waiting then HLS.** While Starting and HLS segments do not yet exist: show a waiting status in the Outbound player area. Designer label lock: **Waiting**. Not Preview. Not YouTube. Not a settings heading. Pair with the existing Starting pill — do not invent a second pill. When same-origin HLS segments exist (outbound media under `/api/live/…` or `/live/…` — the one already-locked outbound media path), the **same** Outbound player plays picture + sound of the encoded outbound (tee of X RTMP). Not a YouTube embed. Not `GET /api/live/preview` metadata/thumbnail as a fake. Not clip. No new API maze.
- **Show / hide.** Hide Outbound player chrome on Idle / Stopped (unchanged). Show the player area on Starting (Waiting, then HLS) and LIVE. Error: do not replace with clip UI; the one Stop still clears Error.
- **Sound.** On by default once HLS has segments (localhost operator). Native play/pause + volume are **not** Stop. Native controls are enough. No extra toolbar. No `download` attribute. No PiP settings page. No quality picker maze.
- **One Stop.** Exactly **one** Stop control per session on Beat 3: the existing per-session Danger Stop → `POST /api/live/stop`. KISS FAIL if two Stops appear (player Stop + session Stop, top-bar Stop + row Stop, duplicate buttons). Native video pause is not Stop. Enable that one Stop while the session is Starting, LIVE, or Error (so Waiting is not a trap with no way out). Concurrent sessions: still one Stop per session row — not two per row.
- **Bytes.** Same origin `http://127.0.0.1:8788` only. Bind **127.0.0.1 only**. No second port. No Vite `5173` operator path. The bytes in the player MUST be the encoded outbound (tee of what is pushed to X RTMP), not the YouTube ingest URL and not `GET /api/live/preview` JSON. HLS path already locked as the one same-origin outbound media path.
- **Not.** Not a YouTube embed / iframe / youtube.com player. Not clip download, not file save, not Posted / Clip / Tweet / Upload UI. Not the Drop-link `GET /api/live/preview` metadata card (title / `is_live` / thumbnail is source preview; this is the outbound encode).

After Start, `GET /api/live/status` (`sessions[]`) drives per-session pills (`starting` → Starting, then `live` → LIVE) except Error, which sticks until Stop. Poll fail stays the current pill (Idle on fresh load). Never invent Error from a poll fail.

## Live API (Frontend contract)

Operator path is **one Docker compose** → `http://127.0.0.1:8788` (same origin UI + `/api`). Vite may still proxy `/api` → `http://127.0.0.1:8788` for Frontend work; operators open 8788. Never `0.0.0.0`. No `/api/clip` route. No clip UI. No `/api/live/credentials` chrome — Keys / Configuration consumes `/api/live/keys`.

These routes are the lock. Do not invent extra routes beyond keys list/add/delete + start/stop/status/preview + **one** same-origin outbound media path per running session. Playlist chrome is start/status fields only (no playlist editor route). Do not add clip, download, or VOD export routes. Outbound monitor is Beat 3 only — **not** `GET /api/live/preview`.

| Method | Path | Body / response |
| --- | --- | --- |
| `GET` | `/api/live/keys` | List named keys. `200` with `keys[]` of `{ id, name }` plus `in_use` if `status.sessions[]` does not already say so. **Never** echo `rtmp_key`, `rtmp_url`, or the key value. Empty `keys` → Keys / Configuration so the operator can **Add** (not Sign in). |
| `PUT` | `/api/live/keys` | Add/update a named key (Add + Save, and Open / Edit Save). Body: stream key + optional `name` + optional `rtmp_url` override. Omit `rtmp_url` to use default ingest `rtmps://va.pscp.tv:443/x`. On update of an existing named key, an empty / omitted stream-key field means keep the stored key unless a new key is typed. `200` success (id + name only). **Never** echo the key. |
| `DELETE` | `/api/live/keys/<id>` | Remove a named key. `200` success. **Never** echo secrets. |
| `GET` | `/api/live/preview` | Query `source_url`. `200 { "ok": true, "source_url": "…", "title": "…", "is_live": true \| false }`. Title from yt-dlp `-J` `title` (may be `""` if unknown). `is_live` true when `live_status` is `is_live` or JSON `is_live` is true. Confirmed `not_live` / `was_live` stay `200` + title + `is_live:false`. YouTube first. `400 { "ok": false, "error": "…" }` missing/invalid URL. `502 { "ok": false, "error": "…" }` when yt-dlp fails (not `200` empty/false). Drop-link chrome for that 502: Beat 2 Preview (hide card; `error` as-is; Continue disabled; pill stays Idle — not Transport Error). No ffmpeg / restream. Never `rtmp_url` / `rtmp_key` / `destination`. |
| `POST` | `/api/live/start` | Chrome lock: `{ "source_urls":["…", "…"], "key_id":"…" }` — ordered page URLs (live or VOD) + the selected named key. One URL = one-item `source_urls` list. Bare `{ "source_url":"…", "key_id":"…" }` may remain as a one-item playlist (Backend ingest owns that path). → `200 { "ok": true, "state": "starting" }` (process up → later status `live`; roll updates current `source_url` / `source_index`). Never `rtmp_url` / `rtmp_key`. `400` missing/invalid / empty `source_urls`. Do **not** `400` `source_urls` solely because an item is VOD. `409` key already in a live/starting session. Same `key_id` for the whole run — do not re-Select per item. |
| `POST` | `/api/live/stop` | `{ "session_id":"…" }` **or** `{ "key_id":"…" }` → `200 { "ok": true, "state": "stopped" }` (also `200`/`ok` if that session already idle) |
| `GET` | `/api/live/preview` | Query `source_url`. `127.0.0.1:8788`. Response `{ "ok", "source_url", "title", "is_live" }` **only**. No `rtmp_url` / `rtmp_key`. Never echo secrets. **LIVE** badge iff `is_live === true` on 200 ok. Show real `title` (not a synthetic `YouTube source <id>` placeholder). Same-route **502** `{ ok: false, error }` chrome: Beat 2 Preview (hide card; no LIVE badge; `error` as-is; Continue disabled; pill stays Idle). |
| `GET` | `/api/live/status` | `200` includes `sessions[]` (concurrent restreams / playlist runs): `{ session_id, key_id, name, source_url, source_index, state, error }` — names only, never keys. `source_url` is the **current** item. `source_index` is the chrome lock (0-based current item). Beat 3 compact position is `{source_index + 1}/{n}` (e.g. `2/5`) using the ordered list chrome already sent. `state` is `idle`\|`starting`\|`live`\|`error`\|`stopped`. Exhausted playlist → `idle` / `stopped`, not Error. Pill / Error-stick apply **per session** where chrome shows them. Never echo `rtmp_key` or `rtmp_url`. Never echo secrets. Optional same-origin `outbound_url` (path only, `127.0.0.1:8788`) for the Beat 3 Outbound player is ok — still names only, never keys. Not `GET /api/live/preview`. |
| `GET` | outbound media for a running session | Same-origin media for the Beat 3 **Outbound** player (`session_id` or `key_id`). Path under `/api/live/…` or `/live/…` (HLS / fMP4 or equivalent). **Not** `GET /api/live/preview`. Backend/Infra own the tap — do not invent a maze. Chrome consumes the path. Never echo secrets. Never return `rtmp_url` / `rtmp_key`. No clip / download / VOD export. |

Responses **never** echo `rtmp_key` or `rtmp_url` (or the key value). Redact those substrings in any error string shown in the UI. `GET` never returns `rtmp_key` / `rtmp_url`.

`POST /api/live/start` does **not** accept raw destination fields. Destination is the selected named `key_id` (same `key_id` for the whole playlist run).

Consume `GET /api/live/preview` for `title` + `is_live` (source preview metadata only — not outbound media). Status poll fail stays Idle (Error chrome locks above). Error sticks until Stop. Beat 3 Outbound consumes the same-origin outbound media path (tee of X RTMP), never preview JSON and never a YouTube embed.

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

No settings pages. No settings maze. No Sign-in. No extra panes beyond these three. No hamburger settings page. No fourth beat. No tabs-as-settings. No clip-post. No clip download. No clip download from the Outbound player. No schedule. No OAuth screens. No Sign-in framing. No “Sign in with X”. No showing keys after save. No `/api/live/credentials` chrome. No Media Studio maze beyond the Beat 1 `?` disclosure (same-beat inline help; default helper stays the one short line). No playlist editor maze (Beat 2 is an ordered URL list; Beat 3 is current item + `2/5` only). No five-block 720px chrome. No Vite `5173` operator path. No second published port. No YouTube embed / iframe / youtube.com player. No treating outbound as preview metadata (`GET /api/live/preview` title / `is_live` / thumbnail is source preview). No dead-blank Starting Outbound. No second Stop. Playlist may include VOD items that roll; still not clip-post, not file upload, never Posted / Clip / Tweet / Upload UI.

## Done when

Frontend can ship a brain-dead 3-item menu (**Keys** / **Drop link** / **Outbound**) against this file without inventing chrome. Frontend can ship the three beats against this file without inventing chrome, OAuth, Sign-in framing, or clip UI. Beat 1 is **Keys / Configuration** (default ingest, Advanced off, named key list with Open / Edit / Select / Delete, clickable `?`). Not a Sign-in gate. Do not restomp that panel. Beat 2 is an ordered source-URL list (live or VOD; add / reorder / remove). The selected named key stays across roll. Beat 3 shows the current item + compact position (`2/5`); roll next when the current item ends; Stop stops the session; exhausted playlist is Idle / Stopped, not Error. Frontend can ship waiting-then-HLS **Outbound** + exactly one Stop against this file (Waiting in the player area during Starting — not a dead blank — then picture + sound from same-origin HLS when segments exist; the one Danger Stop enabled on Starting / LIVE / Error; native pause is not Stop; KISS FAIL if two Stops). Operator form factor is one Docker compose on `http://127.0.0.1:8788`.
