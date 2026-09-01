/**
 * Named-key beat routing. First Save sticks on Beat 2.
 * Optimistic keys from PUT 200 {id,name}. Empty GET keys/status must not
 * snap back to the Keys panel after a successful Save.
 *
 * Boot with saved keys stays on Beat 1 so the operator can select / edit.
 * Select is UI-only (sets key_id for POST /api/live/start).
 */

const BUSY = new Set(["starting", "live"]);

export const DEFAULT_INGEST = "rtmps://va.pscp.tv:443/x";
export const KEYS_HELPER = "Save a named Media Studio stream key.";

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

/** Exact name match. Backend 409 is case-sensitive on a different id. */
export function findKeyByName(keys, name) {
  const wanted = typeof name === "string" ? name.trim() : "";
  if (!wanted) return null;
  return (Array.isArray(keys) ? keys : []).find((key) => key.name === wanted) || null;
}

/**
 * Same-id edit keeps that id (200 even if the name is unchanged).
 * Add with a name already used → that row's id (edit, not a silent duplicate).
 */
export function resolveSaveKeyId({ keys, name, id } = {}) {
  const given = typeof id === "string" && id.trim() ? id.trim() : "";
  if (given) return given;
  return findKeyByName(keys, name)?.id || "";
}

export function mergeOptimisticKey(keys, saved) {
  const next = publicNamedKey(saved);
  if (!next) return Array.isArray(keys) ? keys.slice() : [];
  const list = (Array.isArray(keys) ? keys : []).filter((key) => key.id !== next.id);
  list.push(next);
  return list;
}

/**
 * First Save (no keys yet, not Add/Edit) → Beat 2 + justSaved.
 * Add+Save / Edit+Save stays on Beat 1 (list stays visible).
 */
export function applySaveSuccess(chrome, saved, { adding = false, editing = false } = {}) {
  const prior = Array.isArray(chrome.keys) ? chrome.keys : [];
  const first = prior.length === 0;
  const keys = mergeOptimisticKey(prior, saved);
  if (editing || (adding && !first)) {
    return {
      ...chrome,
      keys,
      justSaved: false,
      adding: Boolean(adding && !first),
      editingId: "",
      beat: 1,
    };
  }
  return {
    ...chrome,
    keys,
    justSaved: true,
    adding: false,
    editingId: "",
    selectedKeyId: saved?.id || chrome.selectedKeyId || "",
    beat: 2,
  };
}

/** Boot: empty / GET fail / any named key → Beat 1 (list visible when keys exist). */
export function applyKeysBoot(result) {
  const keys = keysFromResult(result);
  return { keys, justSaved: false, adding: false, editingId: "", beat: 1 };
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
    return { ...chrome, keys: [], justSaved: false, beat: 1, adding: false, editingId: "" };
  }
  return {
    ...chrome,
    keys: incoming,
    justSaved: false,
    beat: chrome.adding || chrome.editingId || chrome.beat === 1 ? 1 : chrome.beat || 2,
  };
}

export function applyDeleteKey(chrome, id) {
  const keys = (Array.isArray(chrome.keys) ? chrome.keys : []).filter((key) => key.id !== id);
  const selectedKeyId = chrome.selectedKeyId === id ? "" : chrome.selectedKeyId;
  const editingId = chrome.editingId === id ? "" : chrome.editingId;
  if (keys.length === 0) {
    return {
      ...chrome,
      keys,
      selectedKeyId,
      editingId,
      justSaved: false,
      adding: false,
      beat: 1,
    };
  }
  return { ...chrome, keys, selectedKeyId, editingId };
}

/** Select is UI-only: sets key_id for Drop/Retrans start. */
export function applySelectKey(chrome, id) {
  const keys = Array.isArray(chrome.keys) ? chrome.keys : [];
  if (!keys.some((key) => key.id === id)) return chrome;
  return { ...chrome, selectedKeyId: id, editingId: "", adding: false, beat: 2 };
}

/** Reopen a named key for edit. Secret is never returned — field stays empty. */
export function applyStartEdit(chrome, id) {
  const keys = Array.isArray(chrome.keys) ? chrome.keys : [];
  if (!keys.some((key) => key.id === id)) return chrome;
  return { ...chrome, editingId: id, adding: false, beat: 1 };
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

/**
 * PUT /api/live/keys body. Backend requires name + rtmp_key every time.
 * id present = edit. Omit rtmp_url unless Advanced override is on.
 * Never send a blank key (caller must require a typed value).
 */
export function putKeyBody({ name, rtmp_key, rtmp_url, keys, id }) {
  const trimmed = typeof name === "string" ? name.trim() : "";
  let resolved = trimmed;
  if (!resolved && id) {
    const existing = (Array.isArray(keys) ? keys : []).find((key) => key.id === id);
    resolved = existing?.name || defaultKeyName(keys);
  } else if (!resolved) {
    resolved = defaultKeyName(keys);
  }
  const body = { rtmp_key, name: resolved };
  const resolvedId = resolveSaveKeyId({ keys, name: resolved, id });
  if (resolvedId) body.id = resolvedId;
  if (rtmp_url && rtmp_url.trim()) body.rtmp_url = rtmp_url.trim();
  return body;
}
