// Offline integration harness: runs the actual loader and widget against a minimal DOM.
// This checks behaviour, not CSS layout; visual checks still need a browser.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";

class Element {
  constructor(tag = "div") {
    this.tagName = tag;
    this.children = [];
    this.dataset = {};
    this.style = {};
    this.attributes = {};
    this.hidden = false;
    this.textContent = "";
    this.contentWindow = tag === "iframe" ? {} : undefined;
  }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.append(node); }
  setAttribute(name, value) { this.attributes[name] = value; }
  removeAttribute(name) { delete this[name]; delete this.attributes[name]; }
  getBoundingClientRect() { return { height: 720 }; }
  addEventListener(name, callback) { this[name] = callback; }
}
const loader = await readFile(new URL("../widget.js", import.meta.url), "utf8");
const containers = [new Element(), new Element()];
containers[0].dataset = { postcode: 'E8 1DY&agent=evil', agent: 'demo' };
containers[1].dataset = { postcode: 'E8 1DY', agent: 'demo', phase: 'secondary' };
const listeners = {};
const documentStub = {
  currentScript: { src: "https://schools.example/widget.js" }, readyState: "complete",
  querySelectorAll: () => containers,
  createElement: (tag) => new Element(tag),
};
const windowStub = { addEventListener: (name, fn) => { listeners[name] = fn; } };
const context = vm.createContext({ document: documentStub, window: windowStub, URL, Map });
vm.runInContext(loader, context);
vm.runInContext(loader, context);
let count = 0;
function test(name, run) { run(); count++; console.log(`PASS ${name}`); }
test("loader is safe twice and supports multiple instances", () => assert.deepEqual(containers.map((c) => c.children.length), [1, 1]));
const frame = containers[0].children[0];
test("loader uses script origin, safely encoded attributes and iframe settings", () => {
  const url = new URL(frame.src);
  assert.equal(url.origin, "https://schools.example");
  assert.equal(url.searchParams.get("postcode"), containers[0].dataset.postcode);
  assert.equal(url.searchParams.get("agent"), "demo");
  assert.equal(frame.referrerPolicy, "strict-origin-when-cross-origin");
  assert.equal(frame.loading, "lazy");
  assert.equal(frame.title, "Nearby schools");
  assert.equal(new URL(containers[1].children[0].src).searchParams.get("phase"), "secondary");
});
const send = (origin, source, height) => listeners.message({ origin, source, data: { type: "sir:height", height } });
test("only matching source and origin can resize", () => {
  send("https://schools.example", frame.contentWindow, 725);
  assert.equal(frame.style.height, "725px");
  send("https://evil.example", frame.contentWindow, 12);
  send("https://schools.example", {}, 12);
  for (const invalid of [NaN, Infinity, "100", -10, 20001]) send("https://schools.example", frame.contentWindow, invalid);
  assert.equal(frame.style.height, "725px");
  send("https://schools.example", frame.contentWindow, 350);
  assert.equal(frame.style.height, "350px");
});

const schools = Array.from({ length: 14 }, (_, i) => ({ urn: 100001 + i, name: i === 0 ? '<script>school</script>' : `School ${i}`, phase: i % 2 ? "Primary" : "Secondary", lat: 51.55 + i * 0.001, lon: -0.06 }));
const fixtures = {
  "/agents.json": [{ id: "demo", status: "active", domains: ["listing.example"] }],
  "/embed/slugs/999.json": Object.fromEntries(schools.map((s) => [s.urn, `school-${s.urn}`])),
  "/data/england/las.json": { las: [{ la_code: "999", bbox: [-0.1, 51.5, 0, 51.6], centroid: [51.55, -0.06] }] },
  "/data/la/999/schools.json": { schools },
  "/data/la/999/ofsted.json": { schools: Object.fromEntries(schools.map((s) => [s.urn, { latest: { kind: "graded", date: "2025-01-01", overall_effectiveness: "Good" } }])) },
  "/data/la/999/admissions.json": { primary: Object.fromEntries(schools.map((s) => [s.urn, { years: { 2026: { max_distance: 0.8 } } }])) },
};
const requests = [];
let mode = "ok", elements, messages, finished;
globalThis.fetch = async (input) => {
  const url = String(input);
  requests.push(url);
  if (url.startsWith("https://api.postcodes.io/")) {
    if (mode === "offline") throw new Error("Offline fixture");
    return { ok: mode !== "404", status: mode === "404" ? 404 : 200, json: async () => ({ result: { latitude: 51.55, longitude: -0.06, postcode: "E8 1DY" } }) };
  }
  if (mode === "registry-error" && url === "/agents.json") throw new Error("Registry unavailable");
  if (mode === "slugs-error" && url.startsWith("/embed/slugs/")) throw new Error("Slugs unavailable");
  return { ok: true, json: async () => fixtures[url] || {} };
};
let run = 0;
async function render(search, referrer = "https://listing.example/property") {
  elements = Object.fromEntries(["#status", "#widget", "#credit", "#preview", "#schools"].map((id) => [id, new Element()]));
  elements["#credit"].href = "https://www.schoolsinreach.com/?utm_source=widget&utm_medium=embed&utm_campaign=preview";
  messages = [];
  const complete = new Promise((resolve) => { finished = resolve; });
  // The actual module marks its final content measurement in its finally block.
  let measurements = 0;
  elements["#widget"].getBoundingClientRect = () => { if (++measurements === 2) finished(); return { height: measurements * 300 }; };
  globalThis.document = { referrer, querySelector: (id) => elements[id], createElement: (tag) => new Element(tag) };
  globalThis.location = { search };
  globalThis.parent = { postMessage: (message) => messages.push(message) };
  globalThis.window = { addEventListener() {} };
  globalThis.ResizeObserver = class { observe() {} };
  await import(`./embed.js?integration=${++run}`);
  await complete;
}
const rows = () => elements["#schools"].children.flatMap((section) => section.children.find((c) => c.tagName === "ul").children);
await render("?postcode=E8%201DY&agent=demo");
test("actual widget loads fixtures from absolute paths and renders ten full rows", () => {
  assert.equal(elements["#widget"].dataset.tier, "full");
  assert.equal(rows().length, 10);
  assert.equal(elements["#preview"].hidden, true);
  assert.ok(requests.includes("/data/la/999/admissions.json"));
  assert.ok(requests.includes("https://api.postcodes.io/postcodes/E81DY"));
  assert.ok(rows().every((r) => r.children[2].textContent.includes("published years")));
});
test("rows create safe text, generated links and visible dated inspections", () => {
  const row = rows().find((r) => r.children[0].children[0].textContent.startsWith("<script>"));
  assert.equal(row.children[0].children[0].href, "/school/100001-school-100001/");
  assert.equal(row.children[0].children[0].children.length, 0);
  assert.match(row.children[1].textContent, /Good · Jan 2025/);
});
test("widget sends content height and campaign credit", () => {
  assert.equal(messages.at(-1).type, "sir:height");
  assert.equal(messages.at(-1).height, 600);
  assert.equal(new URL(elements["#credit"].href).searchParams.get("utm_campaign"), "demo");
});
await render("?postcode=E81DY&agent=demo", "https://evil-listing.example/");
test("unapproved host renders three preview rows without chances", () => {
  assert.equal(rows().length, 3);
  assert.ok(rows().every((r) => r.children.length === 2));
  assert.equal(elements["#preview"].hidden, false);
});
await render("?postcode=E81DY&agent=demo&phase=secondary");
test("phase restriction renders one section of five", () => {
  assert.equal(elements["#schools"].children.length, 1);
  assert.equal(elements["#schools"].children[0].children[0].textContent, "Secondary");
  assert.equal(rows().length, 5);
});
await render("?agent=demo");
test("missing postcode has friendly message", () => assert.match(elements["#status"].textContent, /Add a full UK postcode/));
mode = "404";
await render("?postcode=E81DY");
test("unknown postcode has friendly message", () => assert.match(elements["#status"].textContent, /couldn't find that postcode/));
mode = "offline";
await render("?postcode=E81DY");
test("network failure retains fallback and credit", () => {
  assert.match(elements["#status"].textContent, /temporarily unavailable/);
  assert.ok(elements["#credit"].href.startsWith("https://www.schoolsinreach.com/"));
});
mode = "registry-error";
await render("?postcode=E81DY&agent=demo");
test("registry failure fails to preview", () => assert.equal(rows().length, 3));
mode = "slugs-error";
await render("?postcode=E81DY&agent=demo");
test("missing generated map fails gracefully without broken school links", () => {
  assert.match(elements["#status"].textContent, /temporarily unavailable/);
  assert.equal(rows().length, 0);
});
const { CONFIG } = await import("./config.js");
const ctas = [new Element("a"), new Element("a")];
const sales = Object.fromEntries(["#checkout-status", "#copy-code", "#copy-status", "#embed-code"].map((id) => [id, new Element()]));
sales["#embed-code"].textContent = '<div data-schools-in-reach data-postcode="E8 1DY"></div>';
globalThis.document = { querySelectorAll: () => ctas, querySelector: (id) => sales[id] };
// Test both states regardless of what the committed config ships with.
const shippedCheckoutUrl = CONFIG.agents.checkoutUrl;
CONFIG.agents.checkoutUrl = "";
await import("./agents.js?empty");
test("empty checkout disables every sales CTA", () => {
  assert.ok(ctas.every((link) => link.textContent === "Coming soon" && link.attributes["aria-disabled"] === "true" && !link.href));
});
CONFIG.agents.checkoutUrl = "https://checkout.example/trial";
await import("./agents.js?configured");
test("configured checkout replaces pricing anchors", () => assert.ok(ctas.every((link) => link.href === "https://checkout.example/trial")));
CONFIG.agents.checkoutUrl = shippedCheckoutUrl;
let copied;
Object.defineProperty(globalThis, "navigator", { configurable: true, value: { clipboard: { writeText: async (text) => { copied = text; } } } });
await sales["#copy-code"].click();
test("copy button copies the real snippet", () => {
  assert.equal(copied, sales["#embed-code"].textContent);
  assert.equal(sales["#copy-status"].textContent, "Code copied");
});
console.log(`${count} offline integration tests passed`);
