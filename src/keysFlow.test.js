import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  DEFAULT_INGEST,
  SIGNIN_HELPER,
  applyDeleteKey,
  applyKeysBoot,
  applyKeysPoll,
  applySaveSuccess,
  defaultKeyName,
  mergeOptimisticKey,
  putKeyBody,
  unusedKeys,
} from "./keysFlow.js";

describe("first Save sticks on Beat 2", () => {
  it("first Save success → Beat 2 immediately with optimistic {id,name}", () => {
    let chrome = { beat: 1, keys: [], justSaved: false, adding: false };
    chrome = applySaveSuccess(chrome, { id: "key-a", name: "Studio A" }, { adding: false });
    assert.equal(chrome.beat, 2);
    assert.equal(chrome.justSaved, true);
    assert.deepEqual(chrome.keys, [{ id: "key-a", name: "Studio A", in_use: false }]);
  });

  it("later empty GET keys / slow poll does not snap back to Sign in", () => {
    let chrome = applySaveSuccess(
      { beat: 1, keys: [], justSaved: false, adding: false },
      { id: "key-a", name: "Studio A" },
    );
    assert.equal(chrome.beat, 2);
    chrome = applyKeysPoll(chrome, { httpStatus: 200, keys: [] });
    assert.equal(chrome.beat, 2);
    assert.equal(chrome.keys.length, 1);
    assert.equal(chrome.keys[0].id, "key-a");
    chrome = applyKeysPoll(chrome, { httpStatus: 0, keys: [] });
    assert.equal(chrome.beat, 2);
    assert.equal(chrome.keys[0].name, "Studio A");
  });

  it("second Save is not required — confirmed GET keys stays Beat 2", () => {
    let chrome = applySaveSuccess(
      { beat: 1, keys: [], justSaved: false },
      { id: "key-a", name: "Studio A" },
    );
    chrome = applyKeysPoll(chrome, {
      httpStatus: 200,
      keys: [{ id: "key-a", name: "Studio A" }],
    });
    assert.equal(chrome.beat, 2);
    assert.equal(chrome.justSaved, false);
    assert.equal(chrome.keys.length, 1);
  });

  it("Add+Save stays Beat 1", () => {
    const chrome = applySaveSuccess(
      { beat: 1, keys: [{ id: "key-a", name: "A", in_use: false }], justSaved: false },
      { id: "key-b", name: "B" },
      { adding: true },
    );
    assert.equal(chrome.beat, 1);
    assert.equal(chrome.keys.length, 2);
    assert.equal(chrome.justSaved, false);
  });

  it("only Beat 1 when keys actually empty AND we did not just save", () => {
    const empty = applyKeysBoot({ httpStatus: 200, keys: [] });
    assert.equal(empty.beat, 1);
    assert.equal(empty.keys.length, 0);
    const fail = applyKeysBoot({ httpStatus: 502, keys: [] });
    assert.equal(fail.beat, 1);
    const afterDelete = applyDeleteKey(
      { beat: 2, keys: [{ id: "key-a", name: "A", in_use: false }], justSaved: true },
      "key-a",
    );
    assert.equal(afterDelete.beat, 1);
    assert.equal(afterDelete.keys.length, 0);
    assert.equal(afterDelete.justSaved, false);
  });

  it("boot with any named key skips to Beat 2", () => {
    const chrome = applyKeysBoot({
      httpStatus: 200,
      keys: [{ id: "key-a", name: "Studio A" }],
    });
    assert.equal(chrome.beat, 2);
    assert.equal(chrome.keys[0].name, "Studio A");
  });
});

describe("named keys helpers", () => {
  it("unused keys omit starting/live / in_use", () => {
    const keys = [
      { id: "a", name: "A", in_use: false },
      { id: "b", name: "B", in_use: false },
      { id: "c", name: "C", in_use: true },
    ];
    const unused = unusedKeys(keys, [
      { key_id: "b", state: "live" },
      { key_id: "a", state: "stopped" },
    ]);
    assert.deepEqual(
      unused.map((key) => key.id),
      ["a"],
    );
  });

  it("PUT body omits rtmp_url unless Advanced override; default name when empty", () => {
    assert.equal(DEFAULT_INGEST, "rtmps://va.pscp.tv:443/x");
    assert.equal(defaultKeyName([]), "Key");
    const omitted = putKeyBody({
      name: "",
      rtmp_key: "placeholder-stream-key-aaa",
      rtmp_url: "",
      keys: [],
    });
    assert.equal(omitted.name, "Key");
    assert.equal(omitted.rtmp_key, "placeholder-stream-key-aaa");
    assert.equal("rtmp_url" in omitted, false);
    const override = putKeyBody({
      name: "Studio",
      rtmp_key: "placeholder-stream-key-aaa",
      rtmp_url: "rtmp://placeholder.example/live",
      keys: [],
    });
    assert.equal(override.rtmp_url, "rtmp://placeholder.example/live");
  });

  it("mergeOptimisticKey never stores a secret field", () => {
    const merged = mergeOptimisticKey([], {
      id: "key-a",
      name: "Studio A",
      rtmp_key: "placeholder-stream-key-aaa",
    });
    assert.equal("rtmp_key" in merged[0], false);
    assert.equal("rtmp_url" in merged[0], false);
  });
});

describe("first-save wiring lock", () => {
  it("main uses applySaveSuccess / applyKeysPoll; no credentials chrome", () => {
    const main = readFileSync(new URL("./main.js", import.meta.url), "utf8");
    const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
    const api = readFileSync(new URL("./retransApi.js", import.meta.url), "utf8");
    assert.match(main, /applySaveSuccess/);
    assert.match(main, /applyKeysPoll/);
    assert.match(main, /justSaved/);
    assert.match(main, /retransApi\.saveKey/);
    assert.match(main, /retransApi\.listKeys/);
    assert.match(main, /retransApi\.deleteKey/);
    assert.doesNotMatch(main, /saveCredentials/);
    assert.doesNotMatch(main, /retransApi\.credentials/);
    assert.doesNotMatch(main, /\/api\/live\/credentials/);
    assert.doesNotMatch(api, /\/api\/live\/credentials/);
    assert.doesNotMatch(html, /\/api\/live\/credentials/);
    assert.match(html, /Save Media Studio RTMP once\. Not X OAuth\./);
    assert.equal(SIGNIN_HELPER, "Save Media Studio RTMP once. Not X OAuth.");
  });
});
