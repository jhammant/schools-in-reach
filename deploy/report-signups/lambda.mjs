// Sign-ups for the Schools in Reach "Your chances" report: "email me when it's ready".
//
// Deployed with hammantlabs-sites (`hlsite deploy deploy/report-signups --slug sir-report --kind pages`),
// so it runs as its own Lambda with its own DynamoDB table in eu-west-2 (London). The browser posts
// to https://pages.hammantlabs.com/sir-report/api/notify and the handler sees rawPath /api/notify.
//
// It stores the email address and the time it arrived, nothing else: no IP address, no council,
// no postcode. Each row carries a DynamoDB TTL so it is deleted automatically by the end of
// January 2027, as the privacy page promises. Nothing is logged that contains an address.

export const PARTITION = "chances-report";
// DynamoDB removes expired rows within a few days of their TTL, so 20 January leaves room to be
// gone by 31 January 2027, the date on the privacy page.
export const DELETE_AT = Date.UTC(2027, 0, 20) / 1000;
// Reception applications close on 15 January 2027; the offer and sign-ups stop with them.
export const CLOSES_AT = Date.UTC(2027, 0, 16) / 1000;
export const DEFAULT_ORIGINS = ["https://www.schoolsinreach.com"];
const MAX_BODY = 2048;

/** A plausible email address, the same rule as site/js/report-offer.js. Returns it tidied, or null. */
export function cleanEmail(value) {
  const email = String(value ?? "").trim().toLowerCase();
  if (!email || email.length > 254) return null;
  const match = /^([^\s@<>()[\]\\,;:"']+)@([^\s@<>()[\]\\,;:"']+\.[^\s@<>()[\]\\,;:"'.]{2,})$/.exec(email);
  return match && match[1].length <= 64 && !match[2].includes("..") ? email : null;
}

/** At most `max` sign-ups per address per window, per warm Lambda instance. Kept in memory only. */
export function createLimiter({ max = 5, windowMs = 10 * 60 * 1000 } = {}) {
  const hits = new Map();
  return (key, nowMs) => {
    if (!key) return true;
    const recent = (hits.get(key) || []).filter((t) => nowMs - t < windowMs);
    if (hits.size > 5000) hits.clear();
    if (recent.length >= max) {
      hits.set(key, recent);
      return false;
    }
    recent.push(nowMs);
    hits.set(key, recent);
    return true;
  };
}

function reply(status, body, origin) {
  const headers = { "content-type": "application/json", "cache-control": "no-store", vary: "origin" };
  if (origin) {
    headers["access-control-allow-origin"] = origin;
    headers["access-control-allow-methods"] = "POST, OPTIONS";
    headers["access-control-allow-headers"] = "content-type";
    headers["access-control-max-age"] = "86400";
  }
  return { statusCode: status, headers, body: status === 204 ? "" : JSON.stringify(body) };
}

function readBody(event) {
  const raw = event.body || "";
  return event.isBase64Encoded ? Buffer.from(raw, "base64").toString("utf8") : raw;
}

/**
 * The request handler, with its storage passed in so it can be tested without AWS.
 * `save(email, record)` stores one sign-up and resolves "created" or "exists".
 */
export function createHandler({ save, allowedOrigins = DEFAULT_ORIGINS, now = () => Date.now(), allow = createLimiter() }) {
  return async (event) => {
    const method = String(event?.requestContext?.http?.method || "GET").toUpperCase();
    const path = event?.rawPath || "/";
    const headers = Object.fromEntries(Object.entries(event?.headers || {}).map(([k, v]) => [k.toLowerCase(), v]));
    const origin = allowedOrigins.includes(headers.origin) ? headers.origin : null;

    if (path === "/api/health") return reply(200, { ok: true });
    if (path !== "/api/notify") return reply(404, { ok: false, error: "not_found" });
    if (method === "OPTIONS") return origin ? reply(204, null, origin) : reply(403, { ok: false, error: "origin" });
    if (method !== "POST") return reply(405, { ok: false, error: "method" }, origin);
    if (!origin) return reply(403, { ok: false, error: "origin" });

    const nowMs = now();
    if (nowMs / 1000 >= CLOSES_AT) return reply(410, { ok: false, error: "closed" }, origin);
    const raw = readBody(event);
    if (raw.length > MAX_BODY) return reply(413, { ok: false, error: "too_large" }, origin);
    let input;
    try {
      input = JSON.parse(raw);
    } catch {
      return reply(400, { ok: false, error: "email" }, origin);
    }
    if (!input || typeof input !== "object") return reply(400, { ok: false, error: "email" }, origin);
    // The form has a hidden field people never see; anything typed there is a bot. Look successful, store nothing.
    if (input.website) return reply(200, { ok: true }, origin);
    const email = cleanEmail(input.email);
    if (!email) return reply(400, { ok: false, error: "email" }, origin);
    if (!allow(event?.requestContext?.http?.sourceIp || "", nowMs)) return reply(429, { ok: false, error: "slow_down" }, origin);

    try {
      await save(email, { created: new Date(nowMs).toISOString(), ttl: DELETE_AT });
    } catch (err) {
      console.error(JSON.stringify({ error: "save_failed", name: err?.name || "Error" }));
      return reply(503, { ok: false, error: "unavailable" }, origin);
    }
    // The same answer whether the address is new or already there, so the form can't be used to
    // find out who has signed up.
    return reply(200, { ok: true }, origin);
  };
}

/** Storage in this site's DynamoDB table (TABLE_NAME, set by hlsite). One row per address. */
async function dynamoSave() {
  const { DynamoDBClient } = await import("@aws-sdk/client-dynamodb");
  const { DynamoDBDocumentClient, PutCommand } = await import("@aws-sdk/lib-dynamodb");
  const client = DynamoDBDocumentClient.from(new DynamoDBClient({}));
  return async (email, record) => {
    try {
      await client.send(new PutCommand({
        TableName: process.env.TABLE_NAME,
        Item: { pk: PARTITION, sk: email, ...record },
        ConditionExpression: "attribute_not_exists(sk)",
      }));
      return "created";
    } catch (err) {
      if (err?.name === "ConditionalCheckFailedException") return "exists";
      throw err;
    }
  };
}

let live = null;

export async function handler(event) {
  if (!live) {
    const origins = (process.env.ALLOWED_ORIGINS || "").split(",").map((o) => o.trim()).filter(Boolean);
    live = createHandler({ save: await dynamoSave(), allowedOrigins: origins.length ? origins : DEFAULT_ORIGINS });
  }
  return live(event);
}
