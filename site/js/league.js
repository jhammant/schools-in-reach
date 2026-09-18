import { $, $$, esc, fmt, humanize } from "./util.js";
import { state, laFile, laName, nearestLoadedLa, laForDistrict } from "./state.js";
import { getMap } from "./map.js";

const ui = { phase: "secondary", sort: null, dir: -1, la: null };

/** The council to rank: the one picked, else the one at your pin, else the one at the map centre. */
function currentLa() {
  if (ui.la && state.laData.has(ui.la)) return ui.la;
  const home = state.home;
  const fromHome = home?.districtCode && laForDistrict(home.districtCode);
  if (fromHome && state.laData.has(String(fromHome.la_code))) return String(fromHome.la_code);
  const c = getMap()?.getCenter();
  const near = c ? nearestLoadedLa({ lat: c.lat, lon: c.lng }) : null;
  return near || [...state.laData.keys()][0] || null;
}

function cell(k, v) {
  if (v == null) return "–";
  if (typeof v !== "number") return esc(v);
  if (/p8|progress/i.test(k)) return fmt.signed(v);
  return Number.isInteger(v) ? String(v) : v.toFixed(1);
}

function phaseOf(row) {
  const p = String(row.phase || "").toLowerCase();
  if (p.includes("16") || p.includes("post")) return "post16";
  if (p.includes("second") || p.includes("all")) return "secondary";
  return "primary";
}

export async function renderLeague(onSelect) {
  const root = $("#view-league");
  const la = currentLa();
  if (!la) {
    root.innerHTML = `<p class="empty">Zoom in on the map or search a postcode to load a council's schools.</p>`;
    return;
  }
  const data = await laFile(la, "league_tables.json");
  const rows = Array.isArray(data) ? data : data?.rows || data?.schools || [];
  if (!rows.length) {
    root.innerHTML = `<p class="empty">We don't have league table data for ${esc(laName(la))} yet.</p>`;
    return;
  }
  const labels = data?.columns || data?.labels || {};
  const prefix = { primary: "ks2_", secondary: "ks4_", post16: "ks5_" }[ui.phase];
  const phaseRows = rows.filter((r) => Object.keys(r).some((k) => k.startsWith(prefix) && typeof r[k] === "number"));
  const measureKeys = [...new Set(phaseRows.flatMap((r) => Object.keys(r).filter((k) => k.startsWith(prefix) && (typeof r[k] === "number" || /grade$/.test(k)))))];
  if (!ui.sort || (ui.sort !== "_dist" && !measureKeys.includes(ui.sort))) ui.sort = measureKeys.find((k) => /rwm_exp|a8|aps/.test(k)) || measureKeys[0] || null;

  const withDist = phaseRows.map((r) => ({ ...r, _dist: state.byUrn.get(Number(r.urn))?._dist ?? null }));
  const sortKey = ui.sort;
  withDist.sort((a, b) => {
    const av = sortKey === "_dist" ? a._dist : a[sortKey];
    const bv = sortKey === "_dist" ? b._dist : b[sortKey];
    if (av == null || typeof av !== "number") return 1;
    if (bv == null || typeof bv !== "number") return -1;
    return (av - bv) * ui.dir;
  });

  const councils = [...state.laData.keys()].sort((a, b) => laName(a).localeCompare(laName(b)));
  root.innerHTML = `
    <label class="small muted" for="league-la">Council</label>
    <select id="league-la" style="width:100%;margin:2px 0 8px">${councils.map((code) => `<option value="${code}" ${code === la ? "selected" : ""}>${esc(laName(code))}</option>`).join("")}</select>
    <div class="chips" role="group" aria-label="Phase">
      ${[["primary", "Primary"], ["secondary", "Secondary"], ["post16", "Sixth form"]].map(([id, l]) => `<button class="chip" data-phase="${id}" aria-pressed="${ui.phase === id}">${l}</button>`).join("")}
    </div>
    <p class="note">${esc(laName(la))} ${ui.phase === "primary" ? "primary" : ui.phase === "secondary" ? "secondary" : "16–18"} schools, showing the latest published results. Click a column heading to sort, or tap a school to open it. Any measure you're unsure about is explained on the About page.</p>
    <div style="overflow-x:auto">
      <table>
        <thead><tr>
          <th>School</th>
          ${state.home ? `<th class="num sortable" data-sort="_dist" aria-sort="${ui.sort === "_dist" ? (ui.dir > 0 ? "ascending" : "descending") : "none"}">Distance</th>` : ""}
          ${measureKeys.map((k) => `<th class="num sortable" data-sort="${esc(k)}" aria-sort="${ui.sort === k ? (ui.dir > 0 ? "ascending" : "descending") : "none"}">${esc(k === "ks4_p8" && data?.years?.ks4_p8 ? `Progress 8 (${data.years.ks4_p8})` : labels[k] || humanize(k))}</th>`).join("")}
        </tr></thead>
        <tbody>
          ${[["local", data?.benchmarks?.la?.[la] || data?.benchmarks?.la || data?.benchmarks?.hackney, `${laName(la)} average`], ["england", data?.benchmarks?.england, "England average"]].filter(([, b]) => b && typeof b === "object").map(([, b, label]) => `<tr><td><em>${esc(label)}</em></td>${state.home ? "<td></td>" : ""}${measureKeys.map((k) => `<td class="num"><em>${cell(k, b[k])}</em></td>`).join("")}</tr>`).join("")}
          ${withDist.map((r) => `<tr class="clickable" data-urn="${r.urn}"><td>${esc(r.name)}</td>${state.home ? `<td class="num">${fmt.mi(r._dist)}</td>` : ""}${measureKeys.map((k) => `<td class="num">${cell(k, r[k])}</td>`).join("")}</tr>`).join("")}
        </tbody>
      </table>
    </div>
    <p class="note">${data?.years ? `Results: ${esc(data.years[prefix.slice(0, 3)] || "")}${prefix === "ks4_" && data.years.ks4_p8 ? `; Progress 8 is ${esc(data.years.ks4_p8)}, the latest year it was published` : ""}. ` : ""}Source: the Department for Education's school performance tables. Independent schools are included where they publish results.</p>`;

  $("#league-la", root).addEventListener("change", (e) => { ui.la = e.target.value; ui.sort = null; renderLeague(onSelect); });
  $$("[data-phase]", root).forEach((b) => b.addEventListener("click", () => { ui.phase = b.dataset.phase; ui.sort = null; renderLeague(onSelect); }));
  $$("[data-sort]", root).forEach((th) => th.addEventListener("click", () => {
    const k = th.dataset.sort;
    if (ui.sort === k) ui.dir *= -1;
    else { ui.sort = k; ui.dir = k === "_dist" ? 1 : -1; }
    renderLeague(onSelect);
  }));
  $$("tr[data-urn]", root).forEach((tr) => tr.addEventListener("click", () => onSelect(Number(tr.dataset.urn))));
}
