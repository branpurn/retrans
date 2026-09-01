/**
 * Beat 3 outbound player. HTML5 <video> + audio on same-origin 8788.
 * Src is GET /api/live/status sessions[].outbound_url — path-only
 * `/live/<session_id>/index.m3u8`. Empty until starting/live.
 * No YouTube embed. No preview thumbnail. No invented /api routes.
 */

import Hls from "hls.js";

const LIVEISH = new Set(["starting", "live"]);
const SESSION_ID_RE = /^[0-9a-f]{12}$/;
const OUTBOUND_PLAYLIST = /^\/live\/[0-9a-f]{12}\/index\.m3u8$/;

/** Locked JSON / control routes — never a media src. Preview stays title/is_live only. */
const NOT_MEDIA = new Set([
  "/api/live/preview",
  "/api/live/status",
  "/api/live/keys",
  "/api/live/start",
  "/api/live/stop",
  "/api/live/credentials",
]);

/** Same-origin tee path. Empty until Backend names one. Never YouTube. */
export const NAMED_TEE = "";

/** Designer lock — visual label on Beat 3. Not Preview, Monitor, or Clip. */
export const OUTBOUND_LABEL = "Outbound";

export function playerShouldAttach({ backend, sessions = [] } = {}) {
  if (LIVEISH.has(backend)) return true;
  return sessions.some((sess) => LIVEISH.has(sess.state));
}

/** Path-only playlist for a session id. Never a host or secret. */
export function outboundMediaPath(session_id) {
  const id = typeof session_id === "string" ? session_id.trim() : "";
  if (!SESSION_ID_RE.test(id)) return "";
  return `/live/${id}/index.m3u8`;
}

/**
 * Media src for <video>. Same-origin `/live/<session_id>/index.m3u8` only.
 * Never YouTube page/embed URLs. Never preview thumbnails. Never 0.0.0.0.
 */
export function outboundSrc(namedTee = NAMED_TEE) {
  const raw = typeof namedTee === "string" ? namedTee.trim() : "";
  if (!raw) return "";
  if (/youtube\.com|youtu\.be|ytimg\.com/i.test(raw)) return "";
  let path = raw;
  if (/^https?:\/\//i.test(raw)) {
    try {
      const url = new URL(raw);
      if (url.hostname !== "127.0.0.1") return "";
      if (url.port && url.port !== "8788") return "";
      path = url.pathname;
    } catch {
      return "";
    }
  } else if (!raw.startsWith("/") || raw.startsWith("//")) {
    return "";
  } else {
    path = raw.split("?")[0];
  }
  if (NOT_MEDIA.has(path) || path.startsWith("/api/live/")) return "";
  return OUTBOUND_PLAYLIST.test(path) ? path : "";
}

/** Prefer status outbound_url; else `/live/<session_id>/index.m3u8`. Empty if idle. */
export function sessionOutboundSrc(session) {
  if (!session || !LIVEISH.has(session.state)) return "";
  return outboundSrc(session.outbound_url) || outboundMediaPath(session.session_id);
}

function destroyHls(video) {
  const hls = video?._retransHls;
  if (!hls) return;
  if (typeof hls.destroy === "function") hls.destroy();
  video._retransHls = null;
  video._retransHlsSrc = "";
}

function bindHls(video, media) {
  const native =
    typeof video.canPlayType === "function" &&
    Boolean(video.canPlayType("application/vnd.apple.mpegurl"));
  if (native) {
    destroyHls(video);
    if (video.getAttribute("src") !== media) video.setAttribute("src", media);
    return;
  }
  if (Hls.isSupported()) {
    if (video._retransHls && video._retransHlsSrc === media) return;
    destroyHls(video);
    const hls = new Hls({ enableWorker: false });
    hls.loadSource(media);
    hls.attachMedia(video);
    video._retransHls = hls;
    video._retransHlsSrc = media;
    return;
  }
  if (video.getAttribute("src") !== media) video.setAttribute("src", media);
}

export function attachPlayer(video, { attach, src } = {}) {
  if (!video) return { attached: false, src: "" };
  const media = attach ? outboundSrc(src) : "";
  if (!attach) {
    destroyHls(video);
    if (typeof video.pause === "function") video.pause();
    video.removeAttribute("src");
    video.removeAttribute("poster");
    if (typeof video.load === "function") video.load();
    video.classList.add("hidden");
    return { attached: false, src: "" };
  }
  video.classList.remove("hidden");
  if (media) {
    bindHls(video, media);
  } else {
    destroyHls(video);
    video.removeAttribute("src");
  }
  video.removeAttribute("poster");
  return { attached: true, src: media };
}
