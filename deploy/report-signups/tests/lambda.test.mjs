// The sign-up endpoint, run against an in-memory store: no AWS needed.
import assert from "node:assert/strict";
import { test } from "node:test";
import { CLOSES_AT, DELETE_AT, cleanEmail, createHandler, createLimiter } from "../lambda.mjs";

const SITE = "https://www.schoolsinreach.com";
const NOV_22 = Date.UTC(2026, 10, 22, 12);

function memoryStore() {
  const rows = new Map();
  return {
    rows,
    async save(email, record) {
      if (rows.has(email)) return "exists";
      rows.set(email, record);
      return "created";
    },
  };
}

function post(body, { origin = SITE, ip = "203.0.113.5", path = "/api/notify", method = "POST", base64 = false } = {}) {
  const text = typeof body === "string" ? body : JSON.stringify(body);
  return {
    rawPath: path,
    headers: origin ? { Origin: origin, "content-type": "text/plain;charset=UTF-8" } : {},
    requestContext: { http: { method, sourceIp: ip } },
    body: base64 ? Buffer.from(text).toString("base64") : text,
    isBase64Encoded: base64,
  };
}

function setup(options = {}) {
  const store = memoryStore();
  const handler = createHandler({ save: store.save, now: () => NOV_22, ...options });
  return { store, handler };
}

test("a sign-up from the site stores the address, tidied, with only a time and a deletion date", async () => {
  // Arrange
  const { store, handler } = setup();

  // Act
  const res = await handler(post({ email: "  Parent@Example.co.uk ", website: "" }));

  // Assert
  assert.equal(res.statusCode, 200);
  assert.deepEqual(JSON.parse(res.body), { ok: true });
  assert.equal(res.headers["access-control-allow-origin"], SITE);
  assert.deepEqual([...store.rows.keys()], ["parent@example.co.uk"]);
  assert.deepEqual(store.rows.get("parent@example.co.uk"), { created: "2026-11-22T12:00:00.000Z", ttl: DELETE_AT });
});

test("rows are set to be deleted before the end of January 2027", () => {
  // Arrange
  const deleteAt = new Date(DELETE_AT * 1000);

  // Act
  const daysBeforeEndOfJanuary = (Date.UTC(2027, 0, 31) - deleteAt.getTime()) / 86400000;

  // Assert: DynamoDB removes expired rows within a few days, so leave at least a week.
  assert.ok(daysBeforeEndOfJanuary >= 7, `only ${daysBeforeEndOfJanuary} days of slack`);
  assert.ok(DELETE_AT > CLOSES_AT);
});

test("the same address twice is one row, and the answer doesn't reveal it was already there", async () => {
  // Arrange
  const { store, handler } = setup();
  await handler(post({ email: "parent@example.com" }));

  // Act
  const again = await handler(post({ email: "PARENT@example.com" }));

  // Assert
  assert.equal(again.statusCode, 200);
  assert.deepEqual(JSON.parse(again.body), { ok: true });
  assert.equal(store.rows.size, 1);
});

test("a base64-encoded body is read too", async () => {
  // Arrange
  const { store, handler } = setup();

  // Act
  const res = await handler(post({ email: "a@b.org" }, { base64: true }));

  // Assert
  assert.equal(res.statusCode, 200);
  assert.ok(store.rows.has("a@b.org"));
});

test("posts from other sites, or with no Origin, are refused and store nothing", async () => {
  // Arrange
  const { store, handler } = setup();

  // Act
  const elsewhere = await handler(post({ email: "a@b.org" }, { origin: "https://evil.example" }));
  const noOrigin = await handler(post({ email: "a@b.org" }, { origin: null }));

  // Assert
  assert.equal(elsewhere.statusCode, 403);
  assert.equal(elsewhere.headers["access-control-allow-origin"], undefined);
  assert.equal(noOrigin.statusCode, 403);
  assert.equal(store.rows.size, 0);
});

test("the CORS preflight is answered for the site only", async () => {
  // Arrange
  const { handler } = setup();

  // Act
  const ok = await handler(post("", { method: "OPTIONS" }));
  const other = await handler(post("", { method: "OPTIONS", origin: "https://evil.example" }));

  // Assert
  assert.equal(ok.statusCode, 204);
  assert.equal(ok.headers["access-control-allow-origin"], SITE);
  assert.match(ok.headers["access-control-allow-methods"], /POST/);
  assert.equal(other.statusCode, 403);
});

test("bad input is refused: not an address, not JSON, too long, wrong method", async () => {
  // Arrange
  const { store, handler } = setup();

  // Act
  const notEmail = await handler(post({ email: "E8 1DY" }));
  const notJson = await handler(post("email=a@b.org"));
  const tooLong = await handler(post({ email: "a@b.org", pad: "x".repeat(3000) }));
  const get = await handler(post("", { method: "GET" }));
  const elsewhere = await handler(post({ email: "a@b.org" }, { path: "/api/other" }));

  // Assert
  assert.equal(notEmail.statusCode, 400);
  assert.equal(notJson.statusCode, 400);
  assert.equal(tooLong.statusCode, 413);
  assert.equal(get.statusCode, 405);
  assert.equal(elsewhere.statusCode, 404);
  assert.equal(store.rows.size, 0);
});

test("a filled-in hidden field (a bot) looks successful but stores nothing", async () => {
  // Arrange
  const { store, handler } = setup();

  // Act
  const res = await handler(post({ email: "bot@spam.example", website: "http://spam.example" }));

  // Assert
  assert.equal(res.statusCode, 200);
  assert.equal(store.rows.size, 0);
});

test("one connection gets five sign-ups in ten minutes, then has to wait", async () => {
  // Arrange
  const { store, handler } = setup();
  for (let i = 0; i < 5; i++) await handler(post({ email: `p${i}@example.com` }));

  // Act
  const sixth = await handler(post({ email: "p5@example.com" }));
  const otherIp = await handler(post({ email: "p6@example.com" }, { ip: "198.51.100.7" }));

  // Assert
  assert.equal(sixth.statusCode, 429);
  assert.equal(otherIp.statusCode, 200);
  assert.equal(store.rows.size, 6);
});

test("the limiter forgets a connection after its window", () => {
  // Arrange
  const allow = createLimiter({ max: 1, windowMs: 1000 });
  allow("ip", 0);

  // Act
  const tooSoon = allow("ip", 500);
  const later = allow("ip", 1500);

  // Assert
  assert.equal(tooSoon, false);
  assert.equal(later, true);
});

test("after 15 January 2027 sign-ups are closed", async () => {
  // Arrange
  const { store, handler } = setup({ now: () => CLOSES_AT * 1000 });

  // Act
  const res = await handler(post({ email: "late@example.com" }));

  // Assert
  assert.equal(res.statusCode, 410);
  assert.equal(store.rows.size, 0);
});

test("a storage failure is a 503 and the log line holds no address", async () => {
  // Arrange
  const logged = [];
  const original = console.error;
  console.error = (...args) => logged.push(args.join(" "));
  const handler = createHandler({ save: async () => { throw Object.assign(new Error("boom parent@example.com"), { name: "ProvisionedThroughputExceededException" }); }, now: () => NOV_22 });

  // Act
  let res;
  try {
    res = await handler(post({ email: "parent@example.com" }));
  } finally {
    console.error = original;
  }

  // Assert
  assert.equal(res.statusCode, 503);
  assert.equal(logged.length, 1);
  assert.doesNotMatch(logged[0], /parent@example\.com/);
});

test("the health check answers without an Origin", async () => {
  // Arrange
  const { handler } = setup();

  // Act
  const res = await handler(post("", { path: "/api/health", method: "GET", origin: null }));

  // Assert
  assert.equal(res.statusCode, 200);
  assert.deepEqual(JSON.parse(res.body), { ok: true });
});

test("the address rule matches the browser's", async () => {
  // Arrange
  const { isLikelyEmail } = await import("../../../site/js/report-offer.js");
  const samples = ["a@b.co", "first.last+tag@sub.example.org", "E8 1DY", "a@b", "a@@b.com", "<a>@b.com", "a@b..com", `${"x".repeat(65)}@b.com`, ""];

  // Act
  const server = samples.map((s) => Boolean(cleanEmail(s)));
  const browser = samples.map((s) => isLikelyEmail(s));

  // Assert
  assert.deepEqual(server, browser);
  assert.deepEqual(server, [true, true, false, false, false, false, false, false, false]);
});
