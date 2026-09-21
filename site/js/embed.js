import { SITE, getJSON } from "./util.js";
import { state, loadLaIndex, lasNear, ensureLas, setHome, admissionsFor } from "./state.js";
import { normalisePhase, parentHostname, accessTier, nearbySections, formatRow, postcodeValue } from "./embed-core.js";

// state.js also serves nested pages; its default data path is relative to the app root.
SITE.dataBase = "/data/";
const params = new URLSearchParams(location.search);
const agent = params.get("agent") || "preview";
const phase = normalisePhase(params.get("phase"));
const status = document.querySelector("#status");
const root = document.querySelector("#widget");
const credit = new URL(document.querySelector("#credit").href);
credit.searchParams.set("utm_campaign", agent);
document.querySelector("#credit").href = credit.href;

let lastHeight = 0;
function sendHeight() {
  // Measure content, not the iframe viewport, so it can shrink as well as grow.
  const height = Math.ceil(root.getBoundingClientRect().height);
  if (height !== lastHeight) {
    lastHeight = height;
    parent.postMessage({ type: "sir:height", height }, "*");
  }
}
if (typeof ResizeObserver !== "undefined") new ResizeObserver(sendHeight).observe(root);
window.addEventListener("resize", sendHeight);
window.addEventListener("load", sendHeight);
sendHeight();

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text) node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function showSchools() {
  try {
    const agents = await getJSON("/agents.json").catch(() => []);
    const host = parentHostname(document.referrer, location.ancestorOrigins?.[0]);
    const tier = accessTier(agents, agent, host);
    document.querySelector("#preview").hidden = tier === "full";
    root.dataset.tier = tier;
    const pc = postcodeValue(params.get("postcode"));
    if (!pc) {
      status.textContent = "Add a full UK postcode to see schools near this property.";
      return;
    }
    const response = await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(pc)}`, { signal: AbortSignal.timeout(10000) });
    if (response.status === 404 || response.status === 400) {
      status.textContent = "We couldn't find that postcode. Please check the property's full UK postcode.";
      return;
    }
    if (!response.ok) throw new Error("Postcode lookup unavailable");
    const { result } = await response.json();
    if (!Number.isFinite(result?.latitude) || !Number.isFinite(result?.longitude)) throw new Error("Missing coordinates");
    const home = { lat: result.latitude, lon: result.longitude, postcode: result.postcode };
    await loadLaIndex();
    const slugs = {};
    const slugCouncils = new Set();
    // Fetch only the slug maps for councils actually loaded near this postcode.
    const ensureSlugs = async () => {
      const wanted = [...new Set(state.schools.map((s) => s._la))].filter((la) => la && !slugCouncils.has(la));
      wanted.forEach((la) => slugCouncils.add(la));
      const maps = await Promise.all(wanted.map((la) => getJSON(`/embed/slugs/${encodeURIComponent(la)}.json`)));
      for (const map of maps) Object.assign(slugs, map);
    };
    setHome(home);
    // Expand in rural areas while keeping the common London request small.
    let sections;
    for (const radius of [3, 10, 30]) {
      await ensureLas(lasNear(home, radius));
      await ensureSlugs();
      const schools = state.schools.filter((s) => Object.hasOwn(slugs, String(s.urn)));
      sections = nearbySections(schools, home, phase, tier);
      const enough = tier === "preview" ? sections.reduce((n, s) => n + s.schools.length, 0) >= 3 : sections.every((s) => s.schools.length >= 5);
      const furthest = Math.max(0, ...sections.flatMap((s) => s.schools.map((school) => school._dist)));
      if (enough && furthest <= radius) break;
    }
    const count = sections.reduce((n, section) => n + section.schools.length, 0);
    status.textContent = count ? `Nearest schools to ${home.postcode || pc}${tier === "preview" ? " · Preview" : ""}` : "We don't have nearby school data for this postcode yet. Please try again later.";
    for (const section of sections) {
      const container = element("section");
      container.append(element("h2", section.phase === "primary" ? "Primary" : "Secondary"));
      const list = element("ul");
      for (const school of section.schools) {
        const row = formatRow(school, state.laData.get(school._la)?.ofsted?.schools?.[school.urn], admissionsFor(school.urn), slugs, tier);
        const item = element("li");
        const heading = element("div", "", "school-heading");
        const link = element("a", row.name);
        link.href = row.href;
        link.target = "_blank";
        link.rel = "noopener";
        heading.append(link, element("span", row.distance, "distance"));
        item.append(heading, element("p", row.inspection, "inspection"));
        if (row.chance) {
          const chance = element("p", row.chance.text, row.chance.caveat ? "chance pill" : "chance");
          if (row.chance.note) chance.title = row.chance.note;
          item.append(chance);
        }
        list.append(item);
      }
      container.append(list);
      if (!section.schools.length) container.append(element("p", "No schools of this phase found nearby."));
      document.querySelector("#schools").append(container);
    }
  } catch {
    status.textContent = "Nearby schools are temporarily unavailable. Please try again later, or visit Schools in Reach below.";
  } finally { sendHeight(); }
}
showSchools();
