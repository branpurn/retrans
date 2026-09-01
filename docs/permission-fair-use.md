# Permission / fair use

The operator must have permission or a fair-use basis for the **live** source being retransmitted to X live.

Do not build RETRANS around stealing content. Wave 1 assumes the operator supplies a live source they are allowed to retransmit.

## How to create the RTMP source

Create the RTMP live source at https://studio.x.com (Media Studio). Copy the RTMP URL and stream key. Give those two values to retrans.

Do not invent a public Live ingest REST API. If a studio.x.com click-path is not verifiable, stop at: create the RTMP live source in Media Studio at studio.x.com; the two values retrans needs are RTMP URL and stream key. Do not invent extra menus.

This lock is live-to-live via Media Studio RTMP + retrans bridge. It is not a clip-archive or VOD-republish product.

This document is an operator lock only. It is not legal advice.
