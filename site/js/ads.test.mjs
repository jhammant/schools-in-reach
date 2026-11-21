// Offline behaviour checks for the ad placeholders on generated school pages,
// using the actual ads module with a stubbed document.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import vm from "node:vm";
import { CONFIG } from "./config.js";

const source = (await readFile(new URL("ads.js", import.meta.url), "utf8"))
  .replace(/^import .*;\n/gm, "").replace(/^export /gm, "")
  .replaceAll("import.meta.url", JSON.stringify("https://www.schoolsinreach.com/js/ads.js"));
const blankSlots = Object.fromEntries(Object.keys(CONFIG.adsense.slots).map((name) => [name, ""]));
let count = 0;
function test(name, run) { run(); count++; console.log(`PASS ${name}`); }

function element(tag = "div") {
  return {
    tag, children: [], attributes: {}, style: {}, dataset: {}, hidden: false,
    setAttribute(name, value) { this.attributes[name] = value; },
    append(...nodes) { this.children.push(...nodes); },
    appendChild(node) { this.children.push(node); return node; },
  };
}

function setup({ client = "", slots = {}, hosts = ["schoolAfterAdmissions", "schoolFooter"], path = "/school/100001-test/" } = {}) {
  const placeholders = hosts.map((name) => Object.assign(element(), { hidden: true, dataset: { adSlot: name } }));
  const head = element("head");
  const window = {};
  const context = vm.createContext({
    // Slot IDs start blank whatever config.js ships with, so these tests still hold once ads are switched on.
    CONFIG: { ...CONFIG, adsense: { client, slots: { ...blankSlots, ...slots }, nonPersonalised: true } },
    URL, Set, Object, encodeURIComponent, window, location: { pathname: path },
    document: {
      head,
      createElement: element,
      getElementById: (id) => head.children.find((node) => node.id === id) || null,
      querySelector: () => null,
      querySelectorAll: (selector) => (selector === ".ad-host[data-ad-slot]" ? placeholders : []),
    },
  });
  vm.runInContext(source, context);
  return { placeholders, head, window };
}

test("the shipped config names both school-page slots", () => {
  // Arrange / Act
  const { slots } = CONFIG.adsense;
  // Assert
  assert.ok(Object.hasOwn(slots, "schoolAfterAdmissions"));
  assert.ok(Object.hasOwn(slots, "schoolFooter"));
});

test("with no publisher ID nothing loads and placeholders stay hidden", () => {
  // Arrange / Act
  const { placeholders, head, window } = setup({ slots: { schoolAfterAdmissions: "111", schoolFooter: "222" } });
  // Assert
  assert.equal(head.children.length, 0);
  assert.equal(window.adsbygoogle, undefined);
  assert.ok(placeholders.every((host) => host.hidden && host.children.length === 0));
});

test("with a publisher ID but no slot IDs nothing loads and placeholders stay hidden", () => {
  // Arrange / Act
  const { placeholders, head, window } = setup({ client: "ca-pub-test" });
  // Assert
  assert.equal(head.children.length, 0);
  assert.equal(window.adsbygoogle, undefined);
  assert.ok(placeholders.every((host) => host.hidden));
});

test("configured slots are shown, labelled and requested once as non-personalised", () => {
  // Arrange / Act
  const { placeholders, head, window } = setup({ client: "ca-pub-test", slots: { schoolAfterAdmissions: "111", schoolFooter: "222" } });
  // Assert
  const scripts = head.children.filter((node) => node.tag === "script");
  assert.equal(scripts.length, 1);
  assert.equal(scripts[0].src, "https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-test");
  const styles = head.children.filter((node) => node.tag === "link");
  assert.equal(styles.length, 1);
  assert.equal(styles[0].href, "https://www.schoolsinreach.com/css/ads.css");
  assert.equal(window.adsbygoogle.requestNonPersonalizedAds, 1);
  assert.equal(window.adsbygoogle[0].enable_page_level_ads, false);
  // One config push, then one render push per slot.
  assert.equal(window.adsbygoogle.length, 3);
  for (const [index, slotId] of ["111", "222"].entries()) {
    const host = placeholders[index];
    assert.equal(host.hidden, false);
    const [wrap] = host.children;
    const [label, ins] = wrap.children;
    assert.equal(label.textContent, "Advertisement");
    assert.equal(ins.attributes["data-ad-client"], "ca-pub-test");
    assert.equal(ins.attributes["data-ad-slot"], slotId);
  }
});

test("only the slot with an ID is shown; unknown placeholder names are ignored", () => {
  // Arrange / Act
  const { placeholders } = setup({ client: "ca-pub-test", slots: { schoolFooter: "222" }, hosts: ["schoolAfterAdmissions", "schoolFooter", "constructor"] });
  // Assert
  assert.deepEqual(placeholders.map((host) => host.hidden), [true, false, true]);
  assert.deepEqual(placeholders.map((host) => host.children.length), [0, 1, 0]);
});

console.log(`${count} ad placeholder tests passed`);
