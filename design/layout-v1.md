# Wave 1 layout

Operator UI for RETRANS. Live retrans YouTube → X. LIVE status language only. Not clip-post.

Product string: **RETRANS**. Code/repo: `retrans`. Frontend owns the operator UI.

## Chrome

100vh, no page scroll. Operator console.

1. Top bar 48px (`--bar`) — left `RETRANS`, right status pill: Idle | Preview | LIVE | Stopped | Error. LIVE uses `--live`. Never say Posted, Clip, Tweet, or Upload.
2. Body max-width 720px, 24px pad. Five stacked blocks, gap 12 (`--gap`), in this locked order:

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
- Helper: From X Media Studio

### 4. Gate

Required checkbox: `I have permission or fair use to retransmit this live.`

Unchecked = Start disabled.

### 5. Transport

- Start live retrans (primary)
- Stop (danger, enabled only while LIVE)
- Helper: `Retransmitting live to X` when LIVE; else Idle until preview + destination + ack

## Enablement

- Start enabled only when: preview ok + RTMP URL + stream key + ack checked + status not LIVE
- Stop enabled only when LIVE

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
