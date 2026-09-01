import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  DEFAULT_INGEST,
  KEYS_HELPER,
  applyDeleteKey,
  applyKeysBoot,
  applyKeysPoll,
  applySaveSuccess,
  applySelectKey,
  applyStartEdit,
  defaultKeyName,
  findKeyByName,
  mergeOptimisticKey,
  putKeyBody,
  resolveSaveKeyId,
  unusedKeys,
} from "./keysFlow.js";

describe("first Save sticks on Beat 2", () => {
  it("first Save success → Beat 2 immediately with optimistic {id,name}", () => {
    let chrome = { beat: 1, keys: [], justSaved: false, adding: false };
    chrome = applySaveSuccess(chrome, { id: "key-a", name: "Studio A" }, { adding: false });
    assert.equal(chrome.beat, 2);
    assert.equal(chrome.justSaved, true);
    assert.equal(chrome.selectedKeyId, "key-a");
    assert.deepEqual(chrome.keys, [{ id: "key-a", name: "Studio A", in_use: false }]);
  });

  it("later empty GET keys / slow poll does not snap back to Keys panel", () => {
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

  it("boot with any named key stays Beat 1 so the list can Open/Edit/Select", () => {
    const chrome = applyKeysBoot({
      httpStatus: 200,
      keys: [{ id: "key-a", name: "Studio A" }],
    });
    assert.equal(chrome.beat, 1);
    assert.equal(chrome.keys[0].name, "Studio A");
  });

  it("Select sets key_id and goes to Beat 2; Open/Edit stays Beat 1", () => {
    const base = {
      beat: 1,
      keys: [{ id: "key-a", name: "Studio A", in_use: false }],
      justSaved: false,
    };
    const selected = applySelectKey(base, "key-a");
    assert.equal(selected.beat, 2);
    assert.equal(selected.selectedKeyId, "key-a");
    const editing = applyStartEdit(base, "key-a");
    assert.equal(editing.beat, 1);
    assert.equal(editing.editingId, "key-a");
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
    const edited = putKeyBody({
      id: "key-a",
      name: "Studio A2",
      rtmp_key: "placeholder-stream-key-bbb",
      rtmp_url: "",
      keys: [{ id: "key-a", name: "Studio A" }],
    });
    assert.equal(edited.id, "key-a");
    assert.equal(edited.name, "Studio A2");
    assert.equal(edited.rtmp_key, "placeholder-stream-key-bbb");
    assert.equal("rtmp_url" in edited, false);
  });

  it("Add with an existing name edits that id; same-id rename is kept", () => {
    const keys = [
      { id: "key-a", name: "Studio A", in_use: false },
      { id: "key-b", name: "Studio B", in_use: false },
    ];
    assert.equal(findKeyByName(keys, "Studio A")?.id, "key-a");
    assert.equal(resolveSaveKeyId({ keys, name: "Studio A" }), "key-a");
    assert.equal(resolveSaveKeyId({ keys, name: "Studio A", id: "key-b" }), "key-b");
    assert.equal(resolveSaveKeyId({ keys, name: "New" }), "");
    const reuse = putKeyBody({
      name: "Studio A",
      rtmp_key: "placeholder-stream-key-ccc",
      rtmp_url: "",
      keys,
    });
    assert.equal(reuse.id, "key-a");
    assert.equal(reuse.name, "Studio A");
    const clash = putKeyBody({
      id: "key-b",
      name: "Studio A",
      rtmp_key: "placeholder-stream-key-ccc",
      rtmp_url: "",
      keys,
    });
    assert.equal(clash.id, "key-b");
    assert.equal(clash.name, "Studio A");
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
    assert.match(html, /Save a named Media Studio stream key\./);
    assert.equal(KEYS_HELPER, "Save a named Media Studio stream key.");
    assert.doesNotMatch(html, /Sign in/);
    assert.match(main, /textContent = "Select"/);
    assert.match(main, /textContent = "Open\/Edit"/);
    assert.match(main, /textContent = "Delete"/);
    assert.match(main, /id: state\.editingId/);
    assert.match(api, /res\.status === 409 \? "name already exists"/);
    assert.doesNotMatch(main, /leave blank to keep/i);
  });
});
