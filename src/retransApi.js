/**
 * Locked live API. Operator URL: http://127.0.0.1:8788 only — same-origin fetch("/api/...").
 * Vite 5173 is not the operator path (`npm run dev` may proxy /api → 8788; never 0.0.0.0).
 * Never fetch an absolute :5173 or :8788 API URL.
 *
 * GET    /api/live/keys → 200 { keys: [{id,name}] }  never secrets
 * PUT    /api/live/keys {id?, name, rtmp_key, rtmp_url?} → 200 {id,name}
 *        id present = edit; name + rtmp_key required every time (no keep-blank)
 *        omit rtmp_url → default ingest rtmps://va.pscp.tv:443/x
 * DELETE /api/live/keys/<id> → 200
 * GET    /api/live/preview?source_url= → 200 { ok, source_url, title, is_live }
 *        probe fail → 502 { ok:false, error } (not 200 empty/false)
 * POST   /api/live/start  { source_url, key_id } live-only (unchanged)
 * POST   /api/live/start  { source_urls: [url, ...], key_id } VOD+live playlist
 * POST   /api/live/stop   { session_id } | { key_id } → 200 { ok, state:"stopped" }
 * GET    /api/live/status → 200 { sessions:[{session_id,key_id,name,source_url,source_index,state,error}] }
 *
 * Never log or return rtmp_url / rtmp_key. No clip routes. Keys panel uses named keys only.
 */

import { startBody } from "./playlist.js";

const START = "/api/live/start";
const STOP = "/api/live/stop";
const STATUS = "/api/live/status";
const KEYS = "/api/live/keys";
const PREVIEW = "/api/live/preview";

/** Redact rtmp_url / rtmp_key substrings only; leave NotLiveError text otherwise unchanged. */
export function redactSecrets(text, secrets = []) {
  let out = String(text ?? "");
  for (const secret of secrets) {
    const value = String(secret ?? "");
    if (value.length >= 3) out = out.split(value).join("[redacted]");
  }
  return out.replace(/rtmps?:\/\/\S+/gi, "[redacted-rtmp]");
}

async function readBody(res) {
  const text = await res.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { error: "bad-response" };
  }
}

function publicSession(raw = {}) {
  const session = {
    session_id: typeof raw.session_id === "string" ? raw.session_id : "",
    key_id: typeof raw.key_id === "string" ? raw.key_id : "",
    name: typeof raw.name === "string" ? raw.name : "",
    source_url: typeof raw.source_url === "string" ? raw.source_url : "",
    state: typeof raw.state === "string" ? raw.state : "",
    error: typeof raw.error === "string" ? raw.error : "",
  };
  if (Number.isInteger(raw.source_index) && raw.source_index >= 0) {
    session.source_index = raw.source_index;
  }
  if (typeof raw.outbound_url === "string" && raw.outbound_url) {
    session.outbound_url = raw.outbound_url;
  }
  return session;
}

function publicStatus(data = {}, httpStatus) {
  const state = typeof data.state === "string" ? data.state : "error";
  const sessions = Array.isArray(data.sessions) ? data.sessions.map(publicSession) : [];
  const result = {
    ok: Boolean(data.ok),
    state,
    source_url: typeof data.source_url === "string" ? data.source_url : "",
    error: typeof data.error === "string" ? data.error : "",
    sessions,
    httpStatus,
  };
  if (Number.isInteger(data.source_index) && data.source_index >= 0) {
    result.source_index = data.source_index;
  }
  return result;
}

function publicKey(data = {}, httpStatus, error = "") {
  const keys = Array.isArray(data.keys)
    ? data.keys.map((key) => ({
        id: typeof key.id === "string" ? key.id : "",
        name: typeof key.name === "string" ? key.name : "",
        in_use: key.in_use === true,
      }))
    : [];
  return {
    ok: Boolean(data.ok),
    id: typeof data.id === "string" ? data.id : "",
    name: typeof data.name === "string" ? data.name : "",
    keys,
    error: typeof error === "string" ? error : "",
    httpStatus,
  };
}

// status.source_url / error may be null from retrans serve; never leak dest fields.

export async function start({ source_url, source_urls, key_id } = {}) {
  const body = startBody({ source_url, source_urls, key_id });
  const res = await fetch(START, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(body),
  });
  const data = await readBody(res);
  const result = publicStatus(data, res.status);
  if (typeof data.key_id === "string") result.key_id = data.key_id;
  if (typeof data.session_id === "string") result.session_id = data.session_id;
  if (result.error) result.error = redactSecrets(result.error);
  if (!res.ok && !result.error) {
    result.error = res.status === 409 ? "live session already running" : "start failed";
  }
  return result;
}

export async function stop({ session_id, key_id } = {}) {
  const body = {};
  if (session_id) body.session_id = session_id;
  else if (key_id) body.key_id = key_id;
  const res = await fetch(STOP, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(body),
  });
  const data = await readBody(res);
  const result = publicStatus(data, res.status);
  if (!res.ok && !result.error) result.error = "stop failed";
  return result;
}

export async function status() {
  const res = await fetch(STATUS, { cache: "no-store" });
  const data = await readBody(res);
  // Do not invent a synthetic status error — poll/boot ignore non-OK and keep Idle.
  return publicStatus(data, res.status);
}

export async function preview(source_url) {
  const qs = new URLSearchParams({ source_url: String(source_url ?? "") });
  const res = await fetch(`${PREVIEW}?${qs}`, { cache: "no-store" });
  const data = await readBody(res);
  let error = typeof data.error === "string" ? data.error : "";
  if (error) error = redactSecrets(error);
  // 502: keep API error as-is (possibly empty). Do not invent helper copy here.
  if (!res.ok && res.status !== 502 && !error) error = "preview failed";
  const probeFail = res.status === 502;
  return {
    ok: res.ok && Boolean(data.ok) && !probeFail,
    source_url: typeof data.source_url === "string" ? data.source_url : "",
    title: typeof data.title === "string" ? data.title : "",
    is_live: data.is_live === true,
    error,
    httpStatus: res.status,
  };
}

export async function listKeys() {
  const res = await fetch(KEYS, { cache: "no-store" });
  const data = await readBody(res);
  return publicKey(data, res.status);
}

export async function saveKey({ id, name, rtmp_key, rtmp_url }) {
  const payload = { name, rtmp_key };
  if (id) payload.id = id;
  if (rtmp_url) payload.rtmp_url = rtmp_url;
  const res = await fetch(KEYS, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify(payload),
  });
  const data = await readBody(res);
  let error = typeof data.error === "string" ? data.error : "";
  if (error) error = redactSecrets(error, [rtmp_key, rtmp_url]);
  if (!res.ok && !error) error = "save failed";
  return publicKey(data, res.status, error);
}

export async function deleteKey(id) {
  const res = await fetch(`${KEYS}/${encodeURIComponent(id)}`, {
    method: "DELETE",
    cache: "no-store",
  });
  const data = await readBody(res);
  return publicKey(data, res.status);
}

export const retransApi = {
  start,
  stop,
  status,
  preview,
  listKeys,
  saveKey,
  deleteKey,
};
