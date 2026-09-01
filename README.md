# RETRANS

Live YouTube → X. Product **RETRANS**. Code/repo `retrans`. No clip. No OAuth.

## Run

```bash
docker pull ghcr.io/branpurn/retrans:latest
docker rm -f retrans; docker run --rm --init -p 127.0.0.1:8788:8788 --name retrans ghcr.io/branpurn/retrans:latest retrans serve
```

Open http://127.0.0.1:8788

NOT `--network host`. Not 0.0.0.0. Not Vite 5173. Not a git clone.

## Use

Menu: **Keys** · **Drop link** · **Outbound**. One pane at a time.

**Keys / Configuration** = named stream keys only (RTMP URL hidden). `?` for Media Studio Sources.

Drop a live URL → Retrans. You must have permission or fair use. Outbound is the encoded player (empty until Backend names the tee).

## Playlist

Ordered YouTube URLs on the same named key (live or VOD). When the current item ends, the next plays. Stop ends the whole playlist.

## Headless

No UI. No published port. Source URL + stream key. Default ingest `rtmps://va.pscp.tv:443/x` (RTMP URL hidden). Broadcast title is still Media Studio.

`retrans.env` (placeholder only):

```
RETRANS_X_RTMP_KEY=YOUR_STREAM_KEY
```

```bash
docker run --name retrans-live --env-file retrans.env ghcr.io/branpurn/retrans:latest retrans live "$SOURCE_URL"
```

Optional `--restart unless-stopped` if you want the container to come back after reboot.

You must have permission or fair use.

Developers: [docs/operator.md](docs/operator.md)
