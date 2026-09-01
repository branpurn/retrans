/**
 * Named-key beat routing. First Save sticks on Beat 2.
 * Optimistic keys from PUT 200 {id,name}. Empty GET keys/status must not
 * snap back to Sign in after a successful Save.
 */

const BUSY = new Set(["starting", "live"]);

export const DEFAULT_INGEST = "rtmps://va.pscp.tv:443/x";
export const SIGNIN_HELPER = "Save Media Studio RTMP once. Not X OAuth.";

export function publicNamedKey(raw) {
  if (!raw || typeof raw !== "object") return null;
  const id = typeof raw.id === "string" ? raw.id.trim() : "";
  if (!id) return null;
  return {
    id,
    name: typeof raw.name === "string" && raw.name.trim() ? raw.name.trim() : "Key",
    in_use: raw.in_use === true,
  };
}

export function keysFromResult(result) {
  if (!result || result.httpStatus !== 200 || !Array.isArray(result.keys)) return [];
  return result.keys.map(publicNamedKey).filter(Boolean);
}

export function defaultKeyName(keys) {
  const n = Array.isArray(keys) ? keys.length + 1 : 1;
  return n === 1 ? "Key" : `Key ${n}`;
}

export function mergeOptimisticKey(keys, saved) {
  const next = publicNamedKey(saved);
  if (!next) return Array.isArray(keys) ? keys.slice() : [];
  const list = (Array.isArray(keys) ? keys : []).filter((key) => key.id !== next.id);
  list.push(next);
  return list;
}

/**
 * First Save (no keys yet, not Add) → Beat 2 + justSaved.
 * Add+Save (already had keys, or operator clicked Add with keys) → Beat 1.
 */
export function applySaveSuccess(chrome, saved, { adding = false } = {}) {
  const prior = Array.isArray(chrome.keys) ? chrome.keys : [];
  const first = prior.length === 0;
  const keys = mergeOptimisticKey(prior, saved);
  if (adding && !first) {
    return { ...chrome, keys, justSaved: false, adding: true, beat: 1 };
  }
  return { ...chrome, keys, justSaved: true, adding: false, beat: 2 };
}

/** Boot: empty / GET fail → Beat 1. Any named key → Beat 2. */
export function applyKeysBoot(result) {
  const keys = keysFromResult(result);
  if (keys.length === 0) {
    return { keys: [], justSaved: false, adding: false, beat: 1 };
  }
  return { keys, justSaved: false, adding: false, beat: 2 };
}

/**
 * Later GET keys. Empty/slow poll must not wipe a just-saved optimistic list.
 * Only Beat 1 when keys are actually empty AND we did not just save
 * (or after deleting the last key — caller clears justSaved).
 */
export function applyKeysPoll(chrome, result) {
  const optimistic = Array.isArray(chrome.keys) ? chrome.keys : [];
  const usable = Boolean(result && result.httpStatus === 200);
  if (!usable) {
    if (chrome.justSaved && optimistic.length > 0) {
      const beat = chrome.adding ? 1 : chrome.beat === 1 ? 2 : chrome.beat || 2;
      return { ...chrome, keys: optimistic, justSaved: true, beat };
    }
    return chrome;
  }
  const incoming = keysFromResult(result);
  if (incoming.length === 0) {
    if (chrome.justSaved && optimistic.length > 0) {
      const beat = chrome.adding ? 1 : chrome.beat === 1 ? 2 : chrome.beat || 2;
      return { ...chrome, keys: optimistic, justSaved: true, beat };
    }
    return { ...chrome, keys: [], justSaved: false, beat: 1, adding: false };
  }
  return {
    ...chrome,
    keys: incoming,
    justSaved: false,
    beat: chrome.adding ? 1 : chrome.beat || 2,
  };
}

export function applyDeleteKey(chrome, id) {
  const keys = (Array.isArray(chrome.keys) ? chrome.keys : []).filter((key) => key.id !== id);
  if (keys.length === 0) {
    return { ...chrome, keys, justSaved: false, adding: false, beat: 1 };
  }
  return { ...chrome, keys };
}

export function unusedKeys(keys, sessions) {
  const list = Array.isArray(keys) ? keys : [];
  const busy = new Set();
  for (const sess of Array.isArray(sessions) ? sessions : []) {
    if (BUSY.has(sess.state) || sess.in_use === true) busy.add(sess.key_id);
  }
  return list.filter((key) => !key.in_use && !busy.has(key.id));
}

export function sessionIsError(sess) {
  if (!sess) return false;
  return sess.state === "error" || (typeof sess.error === "string" && sess.error.trim() !== "");
}

export function aggregateSessions(sessions, fallback = "idle") {
  const list = Array.isArray(sessions) ? sessions : [];
  let anyError = false;
  let anyLive = false;
  let anyStarting = false;
  let anyStopped = false;
  for (const sess of list) {
    if (sessionIsError(sess)) anyError = true;
    else if (sess.state === "live") anyLive = true;
    else if (sess.state === "starting") anyStarting = true;
    else if (sess.state === "stopped") anyStopped = true;
  }
  if (anyError) return "error";
  if (anyLive) return "live";
  if (anyStarting) return "starting";
  if (anyStopped && list.length > 0 && list.every((sess) => sess.state === "stopped")) {
    return "stopped";
  }
  return fallback;
}

/** Per-session Error sticks until Stop. Status idle must not auto-clear. */
export function stickSessions(prevSessions, incoming, stuckErrors) {
  const prev = Array.isArray(prevSessions) ? prevSessions : [];
  const next = Array.isArray(incoming) ? incoming.map((sess) => ({ ...sess })) : [];
  const stuck = { ...(stuckErrors || {}) };
  const byId = new Map(prev.map((sess) => [sess.session_id || sess.key_id, sess]));
  for (const sess of next) {
    const id = sess.session_id || sess.key_id;
    const prior = byId.get(id);
    if (sessionIsError(sess)) {
      stuck[id] = sess.error || stuck[id] || "";
      sess.state = "error";
      if (!sess.error && stuck[id]) sess.error = stuck[id];
    } else if (prior && (prior.state === "error" || stuck[id] != null) && sess.state !== "error") {
      sess.state = "error";
      sess.error = stuck[id] || prior.error || sess.error || "";
    }
  }
  for (const [id, error] of Object.entries(stuck)) {
    if (next.some((sess) => (sess.session_id || sess.key_id) === id)) continue;
    const prior = byId.get(id);
    if (prior && prior.state === "error") {
      next.push({ ...prior, state: "error", error: error || prior.error || "" });
    }
  }
  return { sessions: next, stuckErrors: stuck };
}

export function clearStuck(stuckErrors, session) {
  const next = { ...(stuckErrors || {}) };
  if (session?.session_id) delete next[session.session_id];
  if (session?.key_id) delete next[session.key_id];
  return next;
}

export function putKeyBody({ name, rtmp_key, rtmp_url, keys }) {
  const body = { rtmp_key, name: name && name.trim() ? name.trim() : defaultKeyName(keys) };
  if (rtmp_url && rtmp_url.trim()) body.rtmp_url = rtmp_url.trim();
  return body;
}
