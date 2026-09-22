// Offline behaviour checks using the actual analytics and agents modules.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { CONFIG } from "./config.js";

const source = async (name) => (await readFile(new URL(name, import.meta.url), "utf8"))
  .replace(/^import .*;\n/gm, "").replace(/^export /gm, "");
const analytics = await source("analytics.js");
const page = await source("page-analytics.js");
const agents = await source("agents.js");
let count = 0;
async function test(name, run) { await run(); count++; console.log(`PASS ${name}`); }

function setup(key = CONFIG.posthog.key, checkoutUrl = CONFIG.agents.checkoutUrl) {
  const scripts = [];
  const element = () => ({
    textContent: "", hidden: true, events: {},
    addEventListener(name, fn) { this.events[name] = fn; },
    setAttribute() {}, removeAttribute(name) { delete this[name]; },
  });
  const links = [element(), element()];
  const nodes = Object.fromEntries(["#copy-code", "#copy-status", "#checkout-status", "#embed-code"].map(id => [id, element()]));
  nodes["#embed-code"].textContent = '<div data-postcode="E8 1DY"></div>';
  const copied = [];
  const context = vm.createContext({
    CONFIG: { ...CONFIG, posthog: { ...CONFIG.posthog, key }, agents: { checkoutUrl } },
    URL, window: {},
    navigator: { clipboard: { async writeText(text) { copied.push(text); } } },
    document: {
      createElement: () => ({}),
      getElementsByTagName: () => [{ parentNode: { insertBefore(script) { scripts.push(script); } } }],
      querySelectorAll: () => links,
      querySelector: id => nodes[id],
    },
  });
  vm.runInContext(analytics, context);
  vm.runInContext(page, context);
  return { context, scripts, links, nodes, copied };
}

await test("static entry initialises cookieless pageviews once with site registration", () => {
  const { context, scripts } = setup();
  vm.runInContext(page, context);
  assert.equal(scripts.length, 1);
  const ph = context.window.posthog;
  assert.equal(ph._i.length, 1);
  const options = ph._i[0][1];
  assert.equal(options.capture_pageview, true);
  assert.equal(options.persistence, "memory");
  assert.equal(options.autocapture, false);
  assert.equal(options.disable_session_recording, true);
  assert.equal(options.ip, false);
  assert.equal(options.respect_dnt, true);
  assert.equal(ph.find(call => call[0] === "register")[1].site, "schoolsinreach");
});
await test("empty analytics key creates no scripts", () => {
  const { scripts, context } = setup("");
  assert.equal(scripts.length, 0);
  assert.equal(context.window.posthog, undefined);
});
await test("both trial CTAs capture clicks and preserve checkout navigation", () => {
  const { context, links } = setup();
  vm.runInContext(agents, context);
  for (const link of links) {
    assert.equal(link.href, CONFIG.agents.checkoutUrl);
    link.events.click();
  }
  const events = context.window.posthog.filter(call => call[0] === "capture");
  assert.equal(events.length, 2);
  assert.ok(events.every(call => call[1] === "agents_cta_click" && Object.keys(call[2]).length === 0));
});
await test("copy button captures click without snippet data and copies the snippet", async () => {
  const { context, nodes, copied } = setup();
  vm.runInContext(agents, context);
  await nodes["#copy-code"].events.click();
  assert.equal(copied[0], nodes["#embed-code"].textContent);
  assert.equal(nodes["#copy-status"].textContent, "Code copied");
  const event = context.window.posthog.find(call => call[1] === "agents_copy_snippet");
  assert.ok(event);
  assert.equal(Object.keys(event[2]).length, 0);
});
await test("analytics failure leaves CTA and clipboard behaviour working", async () => {
  const { context, nodes, links } = setup();
  context.window.posthog.capture = () => { throw new Error("Analytics unavailable"); };
  vm.runInContext(agents, context);
  links[0].events.click();
  await nodes["#copy-code"].events.click();
  assert.equal(nodes["#copy-status"].textContent, "Code copied");
});
console.log(`${count} page analytics tests passed`);
