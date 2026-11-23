// Offline checks for the "Your chances" report offer (report-offer.js), with a stubbed page.
import assert from "node:assert/strict";
import { CONFIG } from "./config.js";
import { EVENTS, EVENT_KEYS, createReportOffer, eventProps, isLikelyEmail, offerFor, offerHtml, sendSignup } from "./report-offer.js";

let count = 0;
async function test(name, run) { await run(); count++; console.log(`PASS ${name}`); }

const LIVE = { ...CONFIG.parentsReport, enabled: true, endsOn: "2027-01-15" };
const HACKNEY = { primary: { 100000: { years: {} } }, secondary: {} };
const ENFIELD = { primary: {}, secondary: { 100001: { years: {} } } };
const results = (overrides = {}) => ({ hasHome: true, awayFromHome: false, phase: "primary", councilCode: "204", admissions: HACKNEY, ...overrides });

/** Just enough of an element for report-offer.js. */
function element(name) {
  return {
    name, hidden: false, value: "", textContent: "", attributes: {}, events: {}, focused: 0,
    setAttribute(key, value) { this.attributes[key] = value; },
    addEventListener(type, fn) { this.events[type] = fn; },
    focus() { this.focused++; },
    querySelector(selector) { return this.children?.[selector] ?? null; },
  };
}

function page({ config = LIVE, fetchImpl, today = "2026-11-22" } = {}) {
  const root = element("root");
  root.hidden = true;
  let html = "";
  const parts = {};
  Object.defineProperty(root, "innerHTML", {
    get: () => html,
    set(value) {
      html = value;
      for (const selector of ["[data-report-open]", "#report-offer-panel", "[data-report-close]", "[data-report-status]", "#report-offer-title"]) parts[selector] = element(selector);
      parts["#report-offer-panel"].hidden = true;
      if (value.includes("data-report-form")) {
        const form = element("form");
        const email = element("email");
        const trap = element("trap");
        form.children = { "#report-offer-email": email, '[name="website"]': trap };
        Object.assign(parts, { "[data-report-form]": form, "#report-offer-email": email });
      }
    },
  });
  root.querySelector = (selector) => parts[selector] ?? null;
  const events = [];
  const track = (name, props) => events.push({ name, props });
  const offer = createReportOffer({ root, config, track, fetchImpl, today: () => today });
  return { root, parts, events, offer };
}

const submit = async (parts) => parts["[data-report-form]"].events.submit({ preventDefault() {} });

await test("the offer shows for a primary search in a council with Reception cut-offs", () => {
  // Arrange, Act
  const context = offerFor({ config: LIVE, today: "2026-11-22", ...results() });

  // Assert
  assert.deepEqual(context, { council_code: "204", phase: "primary" });
});

await test("the offer also shows with all phases listed, and says so", () => {
  // Arrange, Act
  const context = offerFor({ config: LIVE, today: "2026-11-22", ...results({ phase: "" }) });

  // Assert
  assert.deepEqual(context, { council_code: "204", phase: "all" });
});

await test("the offer stays hidden wherever it doesn't fit", () => {
  // Arrange
  const cases = {
    "secondary only": results({ phase: "secondary" }),
    "nursery": results({ phase: "nursery" }),
    "no home yet": results({ hasHome: false }),
    "map moved away from home": results({ awayFromHome: true }),
    "council with no cut-offs": results({ councilCode: "306", admissions: null }),
    "council with secondary cut-offs only": results({ councilCode: "308", admissions: ENFIELD }),
    "no council known": results({ councilCode: null }),
  };

  // Act
  const shown = Object.entries(cases).filter(([, input]) => offerFor({ config: LIVE, today: "2026-11-22", ...input }));

  // Assert
  assert.deepEqual(shown.map(([label]) => label), []);
});

await test("the offer is off when switched off, and from the 15 January 2027 deadline", () => {
  // Arrange, Act
  const off = offerFor({ config: { ...LIVE, enabled: false }, today: "2026-11-22", ...results() });
  const lastDay = offerFor({ config: LIVE, today: "2027-01-14", ...results() });
  const deadline = offerFor({ config: LIVE, today: "2027-01-15", ...results() });

  // Assert
  assert.equal(off, null);
  assert.ok(lastDay);
  assert.equal(deadline, null);
});

await test("the shipped config runs the test until the deadline, at £9.99, with an HTTPS endpoint", () => {
  // Arrange
  const config = CONFIG.parentsReport;

  // Act
  const url = new URL(config.notifyUrl);

  // Assert
  assert.equal(config.enabled, true);
  assert.equal(config.price, "£9.99");
  assert.equal(config.endsOn, "2027-01-15");
  assert.equal(url.protocol, "https:");
  assert.match(url.pathname, /\/api\/notify$/);
});

await test("event properties keep only the council code, phase and failure reason", () => {
  // Arrange
  const context = { council_code: "204", phase: "primary", postcode: "E8 1DY", lat: 51.5, lon: -0.05 };

  // Act
  const props = eventProps(context, { reason: "network", email: "a@b.org", child: "Sam" });

  // Assert
  assert.deepEqual(props, { council_code: "204", phase: "primary", reason: "network" });
});

await test("the button, its panel and the first view are counted, with no postcode, place or address", async () => {
  // Arrange
  const { root, parts, events, offer } = page({ fetchImpl: async () => ({ ok: true, status: 200 }) });

  // Act
  offer.update(results());
  offer.update(results()); // the list redraws often; one impression per council and phase
  parts["[data-report-open]"].events.click();

  // Assert
  assert.equal(root.hidden, false);
  assert.match(root.innerHTML, /Get the full report, £9\.99/);
  assert.match(root.innerHTML, /coming in early December/);
  assert.equal(parts["#report-offer-panel"].hidden, false);
  assert.equal(parts["[data-report-open]"].attributes["aria-expanded"], "true");
  assert.equal(parts["#report-offer-email"].focused, 1);
  assert.deepEqual(events.map((e) => e.name), [EVENTS.shown, EVENTS.clicked]);
  for (const { props } of events) assert.deepEqual(props, { council_code: "204", phase: "primary" });
});

await test("closing the panel isn't counted as a click", () => {
  // Arrange
  const { parts, events, offer } = page();
  offer.update(results());
  parts["[data-report-open]"].events.click();

  // Act
  parts["[data-report-open]"].events.click();
  parts["[data-report-close]"].events.click();

  // Assert
  assert.equal(parts["#report-offer-panel"].hidden, true);
  assert.deepEqual(events.map((e) => e.name), [EVENTS.shown, EVENTS.clicked]);
});

await test("a sign-up posts only the address, as text/plain JSON without credentials, then counts it", async () => {
  // Arrange
  const calls = [];
  const fetchImpl = async (url, init) => { calls.push({ url, init }); return { ok: true, status: 200 }; };
  const { parts, events, offer } = page({ fetchImpl });
  offer.update(results());
  parts["[data-report-open]"].events.click();
  parts["#report-offer-email"].value = " parent@example.com ";

  // Act
  await submit(parts);

  // Assert
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, LIVE.notifyUrl);
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.credentials, "omit");
  assert.equal(calls[0].init.headers["content-type"], "text/plain;charset=UTF-8");
  assert.deepEqual(JSON.parse(calls[0].init.body), { email: "parent@example.com", website: "" });
  assert.equal(parts["[data-report-form]"].hidden, true);
  assert.match(parts["[data-report-status]"].textContent, /Thanks/);
  assert.deepEqual(events.map((e) => e.name), [EVENTS.shown, EVENTS.clicked, EVENTS.signedUp]);
  const sent = JSON.stringify(events);
  assert.doesNotMatch(sent, /parent@example\.com|E8|postcode|lat|lon/i);
  for (const { props } of events) assert.ok(Object.keys(props).every((key) => EVENT_KEYS.includes(key)));
});

await test("a mistyped address is caught before anything is sent", async () => {
  // Arrange
  let sent = 0;
  const { parts, events, offer } = page({ fetchImpl: async () => { sent++; return { ok: true }; } });
  offer.update(results());
  parts["#report-offer-email"].value = "E8 1DY";

  // Act
  await submit(parts);

  // Assert
  assert.equal(sent, 0);
  assert.match(parts["[data-report-status]"].textContent, /doesn't look like an email address/);
  assert.deepEqual(events.map((e) => e.name), [EVENTS.shown]);
});

await test("a failed save says so, keeps the form and counts the failure with its reason only", async () => {
  // Arrange
  const { parts, events, offer } = page({ fetchImpl: async () => { throw new TypeError("Failed to fetch"); } });
  offer.update(results());
  parts["#report-offer-email"].value = "parent@example.com";

  // Act
  await submit(parts);

  // Assert
  assert.equal(parts["[data-report-form]"].hidden, false);
  assert.match(parts["[data-report-status]"].textContent, /didn't save/);
  assert.deepEqual(events.at(-1), { name: EVENTS.failed, props: { council_code: "204", phase: "primary", reason: "network" } });
});

await test("endpoint refusals map to reasons", async () => {
  // Arrange
  const statuses = [400, 410, 429, 503];

  // Act
  const reasons = await Promise.all(statuses.map((status) => sendSignup({ url: "https://x/api/notify", email: "a@b.org", fetchImpl: async () => ({ ok: false, status }) })));

  // Assert
  assert.deepEqual(reasons.map((r) => r.reason), ["invalid", "closed", "rate_limited", "rejected"]);
});

await test("with no endpoint configured the offer still counts clicks but asks for no email", () => {
  // Arrange
  const { root, parts, events, offer } = page({ config: { ...LIVE, notifyUrl: "" } });

  // Act
  offer.update(results());
  parts["[data-report-open]"].events.click();

  // Assert
  assert.doesNotMatch(root.innerHTML, /type="email"/);
  assert.equal(parts["[data-report-form]"], undefined);
  assert.deepEqual(events.map((e) => e.name), [EVENTS.shown, EVENTS.clicked]);
});

await test("leaving a qualifying area hides the offer; a new council is a new impression", () => {
  // Arrange
  const { root, events, offer } = page();
  offer.update(results());

  // Act
  offer.update(results({ councilCode: "306", admissions: null }));
  const hiddenOutside = root.hidden;
  offer.update(results({ councilCode: "208" }));

  // Assert
  assert.equal(hiddenOutside, true);
  assert.equal(root.hidden, false);
  assert.deepEqual(events.map((e) => e.props.council_code), ["204", "208"]);
});

await test("while another view covers the list, the impression waits until the list is back", () => {
  // Arrange
  const { root, events, offer } = page();

  // Act
  offer.update({ ...results(), inView: false });
  const whileCovered = events.length;
  offer.update({ ...results(), inView: true });

  // Assert
  assert.equal(root.hidden, false);
  assert.equal(whileCovered, 0);
  assert.deepEqual(events.map((e) => e.name), [EVENTS.shown]);
});

await test("a sign-up still counts for the council it was made in if the list moves on meanwhile", async () => {
  // Arrange
  let answer;
  const { parts, events, offer } = page({ fetchImpl: () => new Promise((resolve) => { answer = resolve; }) });
  offer.update(results());
  parts["#report-offer-email"].value = "parent@example.com";

  // Act
  const pending = submit(parts);
  offer.update(results({ awayFromHome: true }));
  answer({ ok: true, status: 200 });
  await pending;

  // Assert
  assert.deepEqual(events.at(-1), { name: EVENTS.signedUp, props: { council_code: "204", phase: "primary" } });
});

await test("a tracker that throws never breaks the offer", () => {
  // Arrange
  const root = page().root;
  const offer = createReportOffer({ root, config: LIVE, track: () => { throw new Error("blocked"); }, fetchImpl: async () => ({ ok: true }), today: () => "2026-11-22" });

  // Act, Assert
  assert.doesNotThrow(() => offer.update(results()));
  assert.equal(root.hidden, false);
});

await test("the markup escapes the configured price and links the privacy page", () => {
  // Arrange, Act
  const html = offerHtml({ ...LIVE, price: "<b>£9.99</b>" });

  // Assert
  assert.match(html, /&lt;b&gt;£9\.99&lt;\/b&gt;/);
  assert.match(html, /href="privacy.html#report-email"/);
  assert.match(html, /delete it by the end of January 2027/);
});

await test("isLikelyEmail accepts ordinary addresses and refuses postcodes", () => {
  // Arrange, Act, Assert
  assert.equal(isLikelyEmail("parent@example.co.uk"), true);
  assert.equal(isLikelyEmail("E8 1DY"), false);
});

console.log(`${count} report offer checks passed`);
