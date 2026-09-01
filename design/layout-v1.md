# Wave 1 layout

> Wave 1 five-block chrome is superseded by [design/primary-flow.md](primary-flow.md) for the operator UI (pill/token locks below remain the status-pill reference).

Operator UI for RETRANS. Live retrans YouTube → X. LIVE status language only. Not clip-post.

Product string: **RETRANS**. Code/repo: `retrans`. Frontend owns the operator UI.

## Chrome

`min-height: 100vh` operator console. Do **not** clip helpers with `overflow: hidden` on the console body (`html`, `body`, `#app`, `.body`). Prefer min-height 100vh; allow the body to scroll if needed so Media Studio helpers (including Create Broadcast / no public API) and the Transport helper are never truncated.

1. Top bar 48px (`--bar`) — left `RETRANS`, right status pill: Idle | Preview | Starting | LIVE | Stopped | Error. Never say Posted, Clip, Tweet, or Upload.
2. Body max-width 720px, 24px pad. Five stacked blocks, gap 12 (`--gap`), in this locked order:

### Status rules

- **Idle-on-poll-fail.** Boot `GET /api/live/status` failure and mid-session status poll / network failures MUST keep the current pill (fresh load = Idle). Never flip the pill to Error for a failed status poll. Never invent helper text like `status failed`.
- **Error pill** only after a real start failure (HTTP 400 or equivalent start failure) or a usable status payload (`GET /api/live/status` HTTP 200) with nonempty `status.error` / `state === "error"`. Not on status poll fail. Idle + `error: null` (or empty) stays Idle / Preview. Never invent Error from a poll fail.
- **Error sticks until Stop.** After the UI enters Error (start HTTP 400 / equivalent, or usable status with nonempty `status.error` / `state === "error"`), keep the pill Error and the error helper until the operator presses **Stop**. Do **not** auto-flip Error → Idle / Preview / Stopped when a later successful status poll returns `idle` / empty error / no longer `error`.
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

- **Mapping.** Backend `starting` → pill Starting (not Preview). Backend `live` → LIVE. Backend `stopped` → Stopped. `--warn` stays `#f59e0b` in Tokens.

### 1. Paste

- Label: Source URL
- Input + Preview
- Placeholder: Paste YouTube URL (live first)
- YouTube first; other URLs can sit disabled with helper “YouTube first”

### 2. Preview card

- Thumbnail, title, host
- LIVE badge on the card if the source is a live stream
- Empty: Paste a YouTube URL to preview

### 3. Destination

From X Media Studio. Required for Start.

- RTMP URL — text input
- Stream key — password input; never echo in logs or UI after blur
- Helper: `From X Media Studio`
- Helper (Create Broadcast / no public API): After Start, still Create Broadcast + Go Live in Media Studio. RETRANS sends the live restream; there is no public API to start the broadcast.
- Both Media Studio helpers must be fully readable (never clipped).

### 4. Gate

Required checkbox: `I have permission or fair use to retransmit this live.`

Unchecked = Start disabled.

### 5. Transport

- Start live retrans (primary)
- Stop (danger, enabled while LIVE or Error)
- Helper (exact; fully readable, never clipped):
  - Default / non-LIVE non-Error: `Idle until preview + destination + ack`
  - While LIVE: `Retransmitting live to X`
  - On Error with a nonempty `status.error` / start error string: show that API error string as-is (redact rtmp secrets only). Do not rewrite it.

## Enablement

- Start enabled only when: preview ok + RTMP URL + stream key + ack checked + status not LIVE
- Stop enabled when LIVE or Error
- Error sticks until Stop. Do not auto-flip Error → Idle / Preview / Stopped on a later successful status poll that returns `idle` / empty error / no longer `error`.
- Stop (`POST /api/live/stop`) clears Error; after Stop succeeds, normal status mapping resumes (Idle / Stopped).
- Status poll / network / non-OK `GET /api/live/status` does not change the pill and does not invent `status failed`
- Start HTTP 400 (or equivalent start failure) or usable status with nonempty `status.error` / state error → Error pill + API error string as-is (rtmp secrets redacted only)

## Tokens

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

Type: 13/18 body, 15/22 title, font-family ui-sans-serif, system-ui, sans-serif. Buttons 32px tall, pad 12, radius 8.

## Out of v1

No clip download, schedule, multi-dest, or comments. No clip-post chrome. YouTube first; other URLs can sit disabled with YouTube first.
