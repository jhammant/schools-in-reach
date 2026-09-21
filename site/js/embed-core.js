import { chanceModel, reachStatus, RULE_CAVEATS } from "./admissions.js";
import { classify, matchesPhase, isSelectiveSchool, isFaithSchool } from "./state.js";
import { milesBetween } from "./util.js";
import { ofstedHeadline } from "./ofsted.js";

export const normalisePhase = (value) => ["primary", "secondary"].includes(value) ? value : "all";

export function parentHostname(referrer = "", ancestor = "") {
  // The immediate ancestor is authoritative when the browser exposes it.
  try {
    const url = new URL(ancestor || referrer);
    return ["https:", "http:"].includes(url.protocol) ? url.hostname.toLowerCase().replace(/\.$/, "") : "";
  } catch { return ""; }
}

export function domainMatches(host, domain) {
  if (!host || typeof domain !== "string") return false;
  const allowed = domain.toLowerCase();
  return host === allowed || host.endsWith(`.${allowed}`);
}

export function accessTier(agents, id, host) {
  const agent = Array.isArray(agents) && agents.find((entry) => entry.id === id);
  return agent && ["active", "trial"].includes(agent.status) &&
    Array.isArray(agent.domains) && agent.domains.some((domain) => domainMatches(host, domain)) ? "full" : "preview";
}

export function schoolPath(urn, slugs) {
  const key = String(urn);
  const slug = Object.hasOwn(slugs || {}, key) ? slugs[key] : null;
  return /^\d+$/.test(key) && typeof slug === "string" && /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug)
    ? `/school/${key}-${slug}/` : null;
}

export function nearbySections(schools, home, phase, tier) {
  const phases = phase === "all" ? ["primary", "secondary"] : [phase];
  const sorted = schools.filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lon) && !/closed/i.test(s.status || ""))
    .map((s) => ({ ...s, _class: s._class || classify(s), _dist: milesBetween(home, s) }))
    .filter((s) => !s._class.hidden && phases.some((p) => matchesPhase(s, p)))
    .sort((a, b) => a._dist - b._dist || Number(a.urn) - Number(b.urn));
  // Preview is three schools total, not three per phase. All-through appears only once here.
  const preview = tier === "preview" ? sorted.slice(0, 3) : null;
  return phases.map((p, index) => ({ phase: p, schools: (preview || sorted)
    .filter((s) => matchesPhase(s, p) && (!preview || !phases.slice(0, index).some((earlier) => matchesPhase(s, earlier))))
    .slice(0, 5) }));
}

export function chanceLine(rec, distance, school) {
  if (isSelectiveSchool(school)) return { text: RULE_CAVEATS.selective.pill, note: RULE_CAVEATS.selective.note, caveat: true };
  const model = chanceModel(rec);
  if (model?.kind === "rule") return { text: model.rule.pill, note: model.rule.note, caveat: true };
  const status = reachStatus(rec, distance);
  if (!status) return null;
  if (model?.kind !== "distance") return { text: status.label };
  // Reuse the model's normalised samples, including open bands; never recompute cut-offs.
  const years = new Set(model.points.map((p) => p.yr));
  const hits = new Set(model.points.filter((p) => p.cutoff >= distance).map((p) => p.yr));
  const banded = model.points.length > years.size;
  const text = `Places reached this distance${banded ? " in at least one band" : ""} in ${hits.size} of ${years.size} published years (${model.from}–${model.to}).`;
  return { text: text + (isFaithSchool(school) || model.faith ? " Faith criteria usually come before distance." : ""), note: status.label };
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// 2023-02-28 -> "Feb 2023", matching the UK-style dates on the school pages.
export function ukMonth(value) {
  const m = /^(\d{4})-(\d{2})/.exec(String(value || ""));
  return m && +m[2] >= 1 && +m[2] <= 12 ? `${MONTHS[+m[2] - 1]} ${m[1]}` : value || "";
}

export function formatRow(school, ofsted, admissions, slugs, tier) {
  const headline = ofstedHeadline(ofsted);
  const date = ukMonth(ofsted?.latest?.date);
  return {
    name: school.name,
    href: schoolPath(school.urn, slugs),
    distance: `${school._dist.toFixed(1)} mi`,
    inspection: headline ? `${ofsted?.inspectorate === "ISI" ? "" : "Ofsted: "}${headline}${date ? ` · ${date}` : " · date not published"}` : "Ofsted data not available",
    chance: tier === "full" ? chanceLine(admissions, school._dist, school) : null,
  };
}

export function postcodeValue(raw) {
  const pc = String(raw || "").replace(/\s+/g, "").toUpperCase();
  return /^(?:GIR0AA|[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2})$/.test(pc) ? pc : null;
}
