# RETRANS

Tool for restreaming a live YouTube (or similar) source to X as an X live, using the operator's Media Studio RTMP source.

## Components:

| Piece | Description |
| ------------------------- | ---------------------------------------------------------------------------- |
| `ghcr.io/branpurn/retrans` | Operator image: UI, `/api`, ffmpeg, yt-dlp, streamlink |
| `retrans serve` | Loopback UI + control API at http://127.0.0.1:8788 |
| `retrans live` | Headless restream (no UI, no published port) |
| `docker-compose.yml` | Optional loopback / live profiles for the same image |
| `docs/operator.md` | Developer and API notes |
| `docs/permission-fair-use.md` | Rights / fair-use expectations before go-live |

## Prerequisites:

- Docker (Docker Desktop is fine)
- X Premium / Premium+ with access to [Media Studio](https://studio.x.com)
- An RTMP source + stream key (Sources → Create Source → RTMP)
- Rights to restream the source (permission or a fair-use basis you are willing to stand behind)

## Usage:

- Pull the image, then start the operator UI. Publish is loopback only:

```
docker pull ghcr.io/branpurn/retrans:latest
docker rm -f retrans 2>/dev/null; docker run --rm --init -p 127.0.0.1:8788:8788 --name retrans ghcr.io/branpurn/retrans:latest retrans serve
```

- Open http://127.0.0.1:8788
- Do NOT `--network host`. On Docker Desktop that binds inside the LinuxKit VM, so this machine's http://127.0.0.1:8788 stays empty.
- Menu is **Keys**, **Drop link**, **Outbound**. One pane at a time.
- **Keys:** named stream keys only (the RTMP URL stays hidden). `?` points at Media Studio Sources.
- **Drop link:** paste a live page URL, then Retrans. Playlist is an ordered list of YouTube URLs on the same named key (live or VOD); when the current item ends, the next plays; Stop ends the whole playlist.
- **Outbound:** the encoded picture + sound (empty until the restream is actually sending).
- In Media Studio: Create Broadcast against that source, then Go Live. Sending RTMP is not enough on its own. There is no public X API to mint a key or start the broadcast.

## Headless:

No UI. No published port. Source URL + stream key. Default ingest is `rtmps://va.pscp.tv:443/x` (the RTMP URL stays hidden). Broadcast title is still set in Media Studio.

`retrans.env` (placeholder only):

```
RETRANS_X_RTMP_KEY=YOUR_STREAM_KEY
```

```
docker run --name retrans-live --env-file retrans.env ghcr.io/branpurn/retrans:latest retrans live "$SOURCE_URL"
```

Optional `--restart unless-stopped` if you want the container back after reboot.

## Primary Tools:

- `yt-dlp` / `streamlink` to pull the live source (YouTube first)
- `ffmpeg` to encode H.264+AAC/FLV to the operator RTMP destination
- Named keys in the UI (local 0600 store; never echoed in API responses)
- Same-origin HLS tee for the Outbound player

## What/Why?:

- Operators run the GHCR image. Checking out this repo is for development, not day-to-day use.
- Bind is `127.0.0.1:8788` only so the control UI never sits on a LAN or hotspot.
- `-p 127.0.0.1:8788:8788` is what actually puts that port on this machine under Docker Desktop and rootless Docker.
- No X OAuth. Media Studio is the key and go-live path.
- Not a clip cutter, VOD uploader, or tweet bot. Success is an on-air X live.

### Notes:

- You must have permission or a fair-use basis for the source. A public URL is not permission. See [docs/permission-fair-use.md](docs/permission-fair-use.md). This is not legal advice.
- Developers: [docs/operator.md](docs/operator.md)
