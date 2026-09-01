import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  addUrl,
  moveUrl,
  nowPlayingCopy,
  parsePlaylistUrl,
  playlistUrls,
  removeAt,
  sessionIndex,
  startBody,
} from "./playlist.js";

const LIVE = "https://www.youtube.com/watch?v=jfKfPfyJRdk";
const VOD = "https://www.youtube.com/watch?v=dQw4w9wgGcQ";
const LIVE_PATH = "https://www.youtube.com/live/abcdefghijk";

describe("playlist", () => {
  it("parses YouTube live and VOD; rejects non-YouTube", () => {
    assert.equal(parsePlaylistUrl(LIVE), LIVE);
    assert.equal(parsePlaylistUrl(VOD), VOD);
    assert.equal(parsePlaylistUrl(LIVE_PATH), LIVE_PATH);
    assert.equal(parsePlaylistUrl("https://example.com/watch"), "");
    assert.equal(parsePlaylistUrl(""), "");
  });

  it("add / remove / reorder keep order and skip duplicates", () => {
    let list = [];
    list = addUrl(list, LIVE);
    list = addUrl(list, VOD);
    list = addUrl(list, LIVE);
    assert.deepEqual(list, [LIVE, VOD]);
    list = moveUrl(list, 1, -1);
    assert.deepEqual(list, [VOD, LIVE]);
    list = removeAt(list, 0);
    assert.deepEqual(list, [LIVE]);
    assert.deepEqual(moveUrl(list, 0, -1), [LIVE]);
    assert.deepEqual(removeAt(list, 9), [LIVE]);
  });

  it("playlistUrls prefers the list; typed field fills a one-item list", () => {
    assert.deepEqual(playlistUrls([LIVE, VOD], LIVE_PATH), [LIVE, VOD]);
    assert.deepEqual(playlistUrls([], VOD), [VOD]);
    assert.deepEqual(playlistUrls([], "https://example.com/nope"), []);
    assert.deepEqual(playlistUrls([]), []);
  });

  it("start payload is source_urls[] + key_id when the playlist has items", () => {
    const body = startBody({
      source_urls: playlistUrls([LIVE, VOD]),
      source_url: LIVE,
      key_id: "key-a",
    });
    assert.deepEqual(body, { source_urls: [LIVE, VOD], key_id: "key-a" });
    assert.equal("source_url" in body, false);
    assert.equal("rtmp_key" in body, false);
    assert.equal("rtmp_url" in body, false);
  });

  it("single live source_url path is unchanged when source_urls is empty", () => {
    const body = startBody({ source_url: LIVE, key_id: "key-a" });
    assert.deepEqual(body, { source_url: LIVE, key_id: "key-a" });
    assert.equal("source_urls" in body, false);
    assert.deepEqual(startBody({ source_urls: [], source_url: LIVE, key_id: "key-a" }), {
      source_url: LIVE,
      key_id: "key-a",
    });
  });

  it("now-playing uses status source_url + source_index; never secrets", () => {
    assert.equal(sessionIndex({ source_index: 1 }), 1);
    assert.equal(sessionIndex({}), 0);
    assert.match(
      nowPlayingCopy({ source_url: VOD, source_index: 0 }, 2),
      /Item 1 of 2\. Next starts when this ends\./,
    );
    assert.match(
      nowPlayingCopy({ source_url: LIVE, source_index: 1 }, 2),
      /Item 2 of 2\. Last in the playlist/,
    );
    assert.match(nowPlayingCopy({ source_url: VOD }, 1), /One source/);
    const src = readFileSync(new URL("./playlist.js", import.meta.url), "utf8");
    assert.doesNotMatch(src, /rtmp_key/);
    assert.doesNotMatch(src, /rtmp_url/);
    assert.doesNotMatch(src, /YOUR_STREAM_KEY/);
  });

  it("README has one playlist block and keeps Run + Headless", () => {
    const readme = readFileSync(new URL("../README.md", import.meta.url), "utf8");
    assert.match(readme, /## Playlist\n\nOrdered YouTube URLs on the same named key/);
    assert.match(readme, /When the current item ends, the next plays/);
    assert.match(readme, /## Run\n\n```bash\ndocker pull ghcr.io\/branpurn\/retrans:latest/);
    assert.match(readme, /## Headless/);
    assert.match(readme, /Open http:\/\/127\.0\.0\.1:8788/);
    assert.match(readme, /NOT `--network host`\. Not 0\.0\.0\.0\. Not Vite 5173\. Not a git clone\./);
    const playlistBlock = readme.slice(readme.indexOf("## Playlist"), readme.indexOf("## Headless"));
    assert.doesNotMatch(playlistBlock, /--network host/);
    assert.doesNotMatch(playlistBlock, /0\.0\.0\.0/);
    assert.doesNotMatch(playlistBlock, /5173/);
    assert.doesNotMatch(playlistBlock, /git clone/);
    assert.equal((readme.match(/## Playlist/g) || []).length, 1);
  });
});
