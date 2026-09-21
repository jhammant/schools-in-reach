import assert from "node:assert/strict";
import { parentHostname, domainMatches, accessTier, schoolPath, nearbySections, formatRow, chanceLine, postcodeValue, normalisePhase } from "./embed-core.js";

let count = 0;
function test(name, run) {
  try { run(); count++; }
  catch (error) { console.error(`FAIL: ${name}`); throw error; }
}
const agents = [{ id: "demo", status: "active", domains: ["example.com", "localhost"] }];
const school = { urn: 123, name: "St Ŵyn & Mary's <School>", phase: "Secondary", lat: 51.5, lon: -0.1, _dist: 0.4 };
const rec = { years: { 2024: { max_distance: 0.3 }, 2025: { max_distance: 0.6 }, 2026: { max_distance: 0.5 } } };
const slugs = { 123: "st-wyn-and-mary-s-school" };

test("referrer is parsed as a URL and normalised", () => assert.equal(parentHostname("https://WWW.Example.com:8443/listing"), "www.example.com"));
test("ancestor origin takes priority", () => assert.equal(parentHostname("https://example.com", "https://other.com"), "other.com"));
test("opaque or missing referrer fails closed", () => { for (const value of ["", "null", "garbage", "file:///example.com", "javascript:alert(1)"]) assert.equal(parentHostname(value), ""); });
test("malformed ancestor does not fall back to favourable referrer", () => assert.equal(parentHostname("https://example.com", "null"), ""));
test("exact hosts and real subdomains match", () => { assert.ok(domainMatches("example.com", "example.com")); assert.ok(domainMatches("branch.example.com", "example.com")); });
test("suffix tricks and empty hosts fail", () => { for (const host of ["evilexample.com", "example.com.evil.test", ""]) assert.equal(domainMatches(host, "example.com"), false); });
test("approved active and trial branches get full access", () => { assert.equal(accessTier(agents, "demo", "example.com"), "full"); assert.equal(accessTier([{ ...agents[0], status: "trial" }], "demo", "branch.example.com"), "full"); });
test("unknown cancelled and unapproved branches get preview", () => { assert.equal(accessTier(agents, "unknown", "example.com"), "preview"); assert.equal(accessTier(agents, "demo", ""), "preview"); assert.equal(accessTier([{ ...agents[0], status: "cancelled" }], "demo", "example.com"), "preview"); assert.equal(accessTier(null, "demo", "example.com"), "preview"); });
test("lookup uses the generated slug verbatim", () => assert.equal(schoolPath(123, slugs), "/school/123-st-wyn-and-mary-s-school/"));
test("missing and malicious slug paths fail closed", () => { assert.equal(schoolPath(456, slugs), null); assert.equal(schoolPath(123, { 123: "../../evil" }), null); assert.equal(schoolPath("<script>", slugs), null); assert.equal(schoolPath("toString", {}), null); });
test("row keeps text separate from URL", () => { const row = formatRow(school, { latest: { kind: "graded", date: "2025-02-01", judgements: { overall_effectiveness: "Good" } } }, rec, slugs, "full"); assert.equal(row.name, school.name); assert.equal(row.distance, "0.4 mi"); assert.equal(row.inspection, "Ofsted: Good · Feb 2025"); assert.match(row.chance.text, /2 of 3 published years/); });
test("preview contains no admissions lines", () => assert.equal(formatRow(school, null, rec, slugs, "preview").chance, null));
test("missing data is honest", () => { const row = formatRow(school, null, null, slugs, "full"); assert.equal(row.inspection, "Ofsted data not available"); assert.equal(row.chance, null); });
test("report cards do not invent an overall grade", () => assert.equal(formatRow(school, { latest: { kind: "report_card", date: "2026-01-10" } }, null, slugs, "full").inspection, "Ofsted: Report card 2026 · Jan 2026"));
test("every special allocation rule suppresses chances", () => { for (const allocation of ["selective", "nodal_point", "catchment_then_distance"]) { const line = chanceLine({ years: { 2026: { allocation, max_distance: 1 } } }, 0.4, school); assert.equal(line.caveat, true); assert.doesNotMatch(line.text, /published years/); } });
test("register selective flag works without admissions data", () => assert.equal(chanceLine(null, 0.4, { ...school, admissions_policy: "Selective" }).text, "Selective school (entrance test)"));
test("lottery remains a random draw", () => assert.equal(chanceLine({ years: { 2026: { allocation: "random_by_zone" } } }, 0.4, school).text, "Places by random draw (2026)"));
test("open bands reuse the model's unlimited reach", () => assert.match(chanceLine({ years: { 2026: { max_distance: 350 } } }, 400, school).text, /1 of 1 published years/));
test("all offered and spare places count without cutoffs", () => { for (const year of [{ all_offered: true }, { non_preference_offers: 2 }]) assert.match(chanceLine({ years: { 2026: year } }, 20, school).text, /1 of 1/); });
test("bands are not counted as separate years", () => assert.match(chanceLine({ years: { 2026: { max_distance: { A: 0.1, B: 0.5 } } } }, 0.4, school).text, /at least one band in 1 of 1 published years/));
test("faith priority remains visible", () => assert.match(chanceLine(rec, 0.4, { ...school, religious_character: "Church of England" }).text, /Faith criteria/));
test("postcode and phase validation", () => { assert.equal(postcodeValue("e8 1dy"), "E81DY"); for (const raw of [null, "E8", "<script>", "SW1A 1AA/junk"]) assert.equal(postcodeValue(raw), null); assert.equal(normalisePhase("secondary"), "secondary"); assert.equal(normalisePhase("bogus"), "all"); });
const schools = Array.from({ length: 16 }, (_, i) => ({ ...school, urn: 100 + i, lat: 51.5 + i * 0.001, phase: i % 2 ? "Primary" : "Secondary" }));
test("full tier sorts and limits each phase to five", () => { const sections = nearbySections([...schools].reverse(), school, "all", "full"); assert.deepEqual(sections.map((s) => s.schools.length), [5, 5]); assert.equal(sections[1].schools[0].urn, 100); });
test("preview is three total and phase filtering precedes limiting", () => { const sections = nearbySections(schools, school, "all", "preview"); assert.equal(sections.flatMap((s) => s.schools).length, 3); assert.equal(nearbySections(schools, school, "primary", "preview")[0].schools.length, 3); });
test("all-through schools appear in both full sections but once in preview", () => { const list = [{ ...school, phase: "All-through" }]; assert.deepEqual(nearbySections(list, school, "all", "full").map((s) => s.schools.length), [1, 1]); assert.deepEqual(nearbySections(list, school, "all", "preview").map((s) => s.schools.length), [1, 0]); });
test("closed and ungeocoded schools are excluded", () => assert.equal(nearbySections([{ ...school, lat: null }, { ...school, status: "Closed" }], school, "all", "full").flatMap((s) => s.schools).length, 0));
console.log(`${count} embed core tests passed`);
