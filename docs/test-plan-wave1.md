# Wave 1 test plan — live YouTube → operator RTMP (X)

Operator-facing plan for the **live** restream path. This document is the plan only. It is **not** a PASS of a live run.

**Idle on live operator clicks** until Backend names a runnable **live-path SHA**. Do not execute GUI or on-air steps against an unnamed build.

---

## Success lock

**Success = continuous live restream.** The operator provides a live source URL; RETRANS restreams that live feed to the operator’s RTMP endpoint (X Media Studio / operator RTMP). Pass means the destination is **on-air** as a live.

**Not success.** Clip download, VOD upload, or posting recorded segments are **FAIL** if treated as the happy path.

---

## Scope

**In scope (Wave 1)**

- Live YouTube source URL → continuous live restream to the operator RTMP (X Media Studio).
- Operator start / stop of that live path.
- Permission / fair-use acknowledgment before go-live (see [permission-fair-use.md](permission-fair-use.md)).

**Out of scope**

- Non-YouTube sources (later waves).
- Clip download, VOD ingest, or scheduled posts of recorded segments.
- Treating a posted video, clip, or VOD on X as the Wave 1 success path.

---

## Preconditions

Before any live attempt:

1. Operator YouTube access to a **live** source the operator has rights to restream (see [permission-fair-use.md](permission-fair-use.md)).
2. Operator X account with Media Studio (or equivalent) **live RTMP** ingest: destination URL + stream key held by the operator.
3. Backend has named a runnable **live-path SHA**. Frontend/operator UI, if used, is that SHA — not an ad-hoc build.
4. Operator confirms permission / fair-use **before** start. No go-live without that confirmation.
5. Secrets (X/RTMP keys, account tokens) stay on the operator box except as required to open the RTMP session to the operator’s own destination.

---

## Happy path (operator)

Do not run these clicks until Backend names the live-path SHA.

1. Confirm the source is a **live** YouTube URL (on-air or about to be), not a VOD or clip.
2. Confirm you have rights to restream it; complete the permission / fair-use acknowledgment.
3. Enter the live source URL (Wave 1 UI lock: paste URL → preview).
4. Confirm preview is the intended **live** source — not a VOD or clip page.
5. Enter / confirm the operator RTMP destination (X Media Studio ingest URL + stream key).
6. Start restream.
7. In X Media Studio (or the operator RTMP monitor), confirm a **continuous live** is on-air — the destination is live, not a posted video.
8. Watch for a short hold (source stays live; RTMP stays connected; destination stays on-air).
9. Stop restream. Destination goes off-air cleanly. No clip or VOD is published as the result of this path.

---

## Network / privacy locks

**Must not leave the box**

- Operator account passwords, OAuth tokens, and unused API keys.
- RTMP stream keys except to the operator’s own ingest host.
- Local config, logs with secrets, or source URLs of content you do not have rights to restream.
- Any download of the source as a file for later upload.

**May reach X**

- The live audiovisual restream, over RTMP, to the operator’s Media Studio / RTMP endpoint.
- Whatever X requires to keep that live session up (connection to the operator ingest).

Nothing else is in the Wave 1 allow-out set.

---

## Failure paths

| Condition | Expected |
| --- | --- |
| No permission / fair-use acknowledgment | Start is blocked. No RTMP session. |
| Private / unlisted / login-walled source without rights | Restream does not start (or stops). Nothing goes on-air at the operator RTMP. |
| Source is VOD or a clip, not live | Path refuses or fails. Do **not** fall back to download + post. |
| X / RTMP auth fail (bad ingest URL or stream key) | Restream does not go on-air. Error is visible to the operator. No clip/VOD post as fallback. |
| Source drop or RTMP drop mid-live | Live destination goes off-air or shows the drop. No automatic VOD/clip publish as the “success” recovery. |

---

## Pass / fail criteria

**PASS** (when a named live-path SHA is run — not claimed by this doc)

- Operator started from a **live** YouTube URL.
- RETRANS restreamed continuously to the operator RTMP (X Media Studio).
- **X live (or the RTMP destination) is on-air** — a live session, not “a video was posted.”
- Stop ends the live; no clip/VOD artifact is the success output.

**FAIL**

- Happy path is implemented or documented as clip download, VOD upload, or posting recorded segments.
- Pass is scored because a video appeared on X (clip/VOD/post) rather than a live being on-air.
- Go-live without permission / fair-use confirmation.
- Live operator clicks were run before Backend named a live-path SHA.

---

## Status of this document

This is the Wave 1 **plan**. It does **not** record a live QA PASS.

Live GUI / operator clicks wait until Backend names a runnable **live-path SHA**.
