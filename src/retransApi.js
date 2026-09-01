/**
 * Locked live API. Vite proxies /api → http://127.0.0.1:8788 (never 0.0.0.0).
 *
 * POST /api/live/start  { source_url, rtmp_url, rtmp_key } → 200 { ok, state:"starting" } | 400 | 409
 * POST /api/live/stop   → 200 { ok, state:"stopped" }
 * GET  /api/live/status → 200 { ok, state, source_url, error }
 *
 * Never log or return rtmp_url / rtmp_key. No clip routes.
 */

const START = "/api/live/start";
const STOP = "/api/live/stop";
const STATUS = "/api/live/status";

function redactSecrets(text, secrets) {
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

function publicStatus(data = {}, httpStatus) {
  const state = typeof data.state === "string" ? data.state : "error";
  return {
    ok: Boolean(data.ok),
    state,
    source_url: typeof data.source_url === "string" ? data.source_url : "",
    error: typeof data.error === "string" ? data.error : "",
    httpStatus,
  };
}

// status.source_url / error may be null from retrans serve; never leak dest fields.

export async function start({ source_url, rtmp_url, rtmp_key }) {
  const res = await fetch(START, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
    body: JSON.stringify({ source_url, rtmp_url, rtmp_key }),
  });
  const data = await readBody(res);
  const result = publicStatus(data, res.status);
  if (result.error) {
    result.error = redactSecrets(result.error, [rtmp_url, rtmp_key]);
  }
  if (!res.ok && !result.error) {
    result.error = res.status === 409 ? "live session already running" : "start failed";
  }
  return result;
}

export async function stop() {
  const res = await fetch(STOP, {
    method: "POST",
    cache: "no-store",
  });
  const data = await readBody(res);
  const result = publicStatus(data, res.status);
  if (!res.ok && !result.error) result.error = "stop failed";
  return result;
}

export async function status() {
  const res = await fetch(STATUS, { cache: "no-store" });
  const data = await readBody(res);
  const result = publicStatus(data, res.status);
  if (!res.ok && !result.error) result.error = "status failed";
  return result;
}

export const retransApi = { start, stop, status };
