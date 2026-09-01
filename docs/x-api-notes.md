# X API notes

## Gap: no public X Live ingest API

No public X Live ingest API was found. There is no documented REST ingest endpoint to start or push an X live stream.

## Live path we will build

The operator creates an RTMP source in X Media Studio at https://studio.x.com, copies the RTMP URL and stream key, and gives those to retrans. retrans pulls YouTube live and pushes to that ingest (the retrans bridge).

That is the product: Media Studio RTMP source + retrans bridge only. Wave 1 does not ship other go-live options (including signed-in operator go-live). We do not invent an undocumented X Live REST ingest API.

## Non-goal / fallback (not success)

Chunked media upload for clip segments is INIT / APPEND / FINALIZE, then attach the media id on the post.

Pay-per-use post costs (published): **$0.015** plain text post, **$0.20** post with a URL.

INIT/APPEND/FINALIZE clip posts and those post costs are a documented non-goal / fallback note only. They are not Wave 1 success.
