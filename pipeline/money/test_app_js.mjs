// Pure-helper tests for assets/app.js under node (no DOM, no network). Run: node --test pipeline/money/test_app_js.mjs
import { test } from "node:test";
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// Arrange (shared): a localStorage stub before the script runs; node's own localStorage needs a flag.
const memory = new Map();
Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: (k) => (memory.has(k) ? memory.get(k) : null),
    setItem: (k, v) => memory.set(k, String(v)),
    removeItem: (k) => memory.delete(k),
  },
});
const here = dirname(fileURLToPath(import.meta.url));
await import(pathToFileURL(join(here, "assets", "app.js")).href);
const M = globalThis.MoneyApp;

test("MoneyApp exports the helpers", () => {
  for (const k of ["fmtMoney", "perPupil", "parsePostcode", "rankSearch", "pinLimits", "togglePin", "importShortlist", "postcodeLookup"]) {
    assert.ok(M[k], k);
  }
});

test("fmtMoney formats like charts.money", () => {
  assert.equal(M.fmtMoney(-1_234_567), "-£1.2m");
  assert.equal(M.fmtMoney(543_210), "£543k");
  assert.equal(M.fmtMoney(950), "£950");
  assert.equal(M.fmtMoney(1_250_000_000), "£1.25bn");
  assert.equal(M.fmtMoney(25_000, true), "+£25k");
  assert.equal(M.fmtMoney(0), "£0");
  assert.equal(M.fmtMoney(null), "—");
  assert.equal(M.fmtMoney("x"), "—");
});

test("perPupil divides by the same row's pupils and is null without pupils", () => {
  assert.equal(M.perPupil(1_234_567, 300), 4115);
  assert.equal(M.perPupil(1000, null), null);
  assert.equal(M.perPupil(1000, 0), null);
  assert.equal(M.perPupil(null, 300), null);
  assert.equal(M.perPupil(-3000, 300), -10);
});

test("parsePostcode finds the outward district", () => {
  assert.deepEqual(M.parsePostcode("E8 1AA"), { district: "E8", inward: "1AA", full: "E8 1AA" });
  assert.equal(M.parsePostcode("n16 0ab").district, "N16");
  assert.equal(M.parsePostcode("  sw1a1aa ").district, "SW1A");
  assert.equal(M.parsePostcode("EC1A").district, "EC1A");
  assert.equal(M.parsePostcode("hello"), null);
  assert.equal(M.parsePostcode("William Patten"), null);
  assert.equal(M.parsePostcode(""), null);
  assert.equal(M.parsePostcode(null), null);
});

const ROWS = [
  { t: "trust", id: "hackney-learning-trust", name: "Hackney Learning Trust", sub: "", status: null, p: "/trust/hackney-learning-trust/" },
  { t: "school", id: "100001", name: "Stoke Newington School", sub: "Hackney", status: "healthy", p: "/school/100001-stoke-newington-school/" },
  { t: "council", id: "204", name: "Hackney", sub: "London", status: null, p: "/council/hackney/" },
  { t: "school", id: "100002", name: "Hackney New School", sub: "Hackney", status: "tight", p: "/school/100002-hackney-new-school/" },
  { t: "constituency", id: "hackney-north", name: "Hackney North and Stoke Newington", sub: "", status: null, p: "/constituency/hackney-north/" },
  { t: "school", id: "100003", name: "William Patten Primary School", sub: "Stoke Newington, Hackney", status: "in_deficit", p: "/school/100003-william-patten-primary-school/" },
  { t: "school", id: "100004", name: "Thomas Fairchild Community School", sub: "Hoxton, Hackney", status: "healthy", p: "/school/100004-thomas-fairchild/" },
];

test("rankSearch: prefix > word match > substring, type order school, council, constituency, trust", () => {
  const names = M.rankSearch(ROWS, "hackney").map((r) => r.id);
  // Prefix hits first (school before council before constituency before trust), then word/substring hits.
  assert.deepEqual(names.slice(0, 4), ["100002", "204", "hackney-north", "hackney-learning-trust"]);
  assert.ok(names.indexOf("100001") > 3, "Stoke Newington School matches only via its sub text");
  assert.ok(names.indexOf("100003") > 3);
  assert.equal(M.rankSearch(ROWS, "patten")[0].id, "100003", "word prefix beats substring");
  assert.equal(M.rankSearch(ROWS, "new sch")[0].id, "100002", "every word a word-prefix in the name");
  assert.equal(M.rankSearch(ROWS, "ewing")[0].name, "Stoke Newington School", "substring still matches");
  assert.deepEqual(M.rankSearch(ROWS, "zzz"), []);
  assert.deepEqual(M.rankSearch(ROWS, "   "), []);
  assert.equal(M.rankSearch(ROWS, "hackney", 2).length, 2, "limit respected");
  assert.equal(M.rankSearch(ROWS, "hackney").length, Math.min(8, 7));
});

test("pinLimits and togglePin: toggle, limits per type counted separately, input not mutated", () => {
  assert.deepEqual(M.pinLimits, { school: 6, area: 4 });
  const start = [];
  let r = M.togglePin(start, { type: "school", id: 1, name: "A", p: "/school/1-a/" });
  assert.equal(r.action, "added");
  assert.deepEqual(r.list, [{ type: "school", id: "1", name: "A", p: "/school/1-a/" }]);
  assert.deepEqual(start, [], "input list untouched");
  r = M.togglePin(r.list, { type: "school", id: "1", name: "A", p: "/school/1-a/" });
  assert.equal(r.action, "removed");
  assert.deepEqual(r.list, []);

  let list = [];
  for (let i = 1; i <= 6; i++) list = M.togglePin(list, { type: "school", id: i, name: "S" + i, p: "/s/" + i }).list;
  assert.equal(list.length, 6);
  r = M.togglePin(list, { type: "school", id: 7, name: "S7", p: "/s/7" });
  assert.equal(r.action, "full");
  assert.equal(r.limit, 6);
  assert.equal(r.list.length, 6, "7th school rejected");
  // Areas are counted separately from schools.
  for (let i = 1; i <= 4; i++) {
    r = M.togglePin(list, { type: "area", id: "council-" + i, name: "C" + i, p: "/council/c" + i + "/" });
    assert.equal(r.action, "added", "area " + i + " fits beside 6 schools");
    list = r.list;
  }
  assert.equal(list.length, 10);
  r = M.togglePin(list, { type: "area", id: "england", name: "England", p: "/" });
  assert.equal(r.action, "full");
  assert.equal(r.limit, 4, "5th area rejected");
  // Removing one school frees a slot.
  list = M.togglePin(list, { type: "school", id: "3" }).list;
  assert.equal(M.togglePin(list, { type: "school", id: 7, name: "S7", p: "/s/7" }).action, "added");
});

test("importShortlist: strings and numbers, de-duplicated, unknown skipped, limit respected", () => {
  const lookup = (urn) => (Number(urn) >= 100001 && Number(urn) <= 100009 ? { name: "School " + urn, p: "/school/" + urn + "-x/" } : null);
  const existing = [{ type: "school", id: "100001", name: "School 100001", p: "/school/100001-x/" }, { type: "area", id: "england", name: "England", p: "/" }];
  const r = M.importShortlist(existing, ["100001", 100002, "100002", 100003, " 100004 ", "999999", "abc", null], lookup);
  assert.equal(r.added, 3, "100002, 100003, 100004");
  assert.equal(r.skipped, 1, "100001 already pinned");
  assert.equal(r.unknown, 1, "999999 has no money page");
  assert.deepEqual(r.list.filter((p) => p.type === "school").map((p) => p.id), ["100001", "100002", "100003", "100004"]);
  assert.equal(r.list.filter((p) => p.type === "area").length, 1, "areas kept");
  assert.equal(existing.length, 2, "input not mutated");

  const big = M.importShortlist([], [100001, 100002, 100003, 100004, 100005, 100006, 100007, 100008], lookup);
  assert.equal(big.list.length, 6, "limit of 6 schools");
  assert.equal(big.added, 6);
  assert.equal(big.skipped, 2);

  // A map works as the lookup too.
  const viaMap = M.importShortlist([], [100001], { "100001": { name: "Mapped", p: "/school/100001-mapped/" } });
  assert.equal(viaMap.list[0].name, "Mapped");
});

test("postcodeLookup resolves null without a fetch implementation or network", async () => {
  const saved = globalThis.fetch;
  globalThis.fetch = () => Promise.reject(new Error("offline"));
  try {
    assert.equal(await M.postcodeLookup("E8"), null);
    assert.equal(await M.postcodeLookup(""), null);
  } finally {
    globalThis.fetch = saved;
  }
});
