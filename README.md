# RETRANS

Live YouTube → X. Product **RETRANS**. Code/repo `retrans`. No clip. No OAuth.

## Run

```bash
docker pull ghcr.io/branpurn/retrans:latest
docker rm -f retrans; docker run --rm --init -p 127.0.0.1:8788:8788 --name retrans ghcr.io/branpurn/retrans:latest retrans serve
```

Open http://127.0.0.1:8788

## Use

**Sign in** = named stream keys only (RTMP URL hidden). `?` for Media Studio Sources.

Drop a live URL → Retrans. You must have permission or fair use.

Developers: [docs/operator.md](docs/operator.md)
