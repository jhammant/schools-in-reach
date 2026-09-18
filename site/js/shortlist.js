import { $, $$, esc, fmt } from "./util.js";
import { state, admissionsFor, GROUP_META, toggleShortlist, ensureLas, laName } from "./state.js";
import { reachPill } from "./admissions.js";
import { addToPlan, isInPlan, planFull } from "./planner.js";

export function renderShortlist(onSelect) {
  const root = $("#view-shortlist");
  $("#shortlist-count").textContent = state.shortlist.size || "";
  const missingLas = [...state.shortlist].filter((u) => !state.byUrn.has(u)).map((u) => state.shortlistLa[u]).filter(Boolean);
  if (missingLas.length) ensureLas(missingLas); // re-renders via the "schools" event once loaded
  const schools = [...state.shortlist].map((u) => state.byUrn.get(u)).filter(Boolean);
  if (!schools.length) {
    root.innerHTML = `<p class="empty">Add schools with “☆ Add to shortlist” to compare them side by side. Your shortlist is saved in this browser only.</p>`;
    return;
  }
  if (state.home) schools.sort((a, b) => (a._dist ?? 99) - (b._dist ?? 99));
  const rows = [
    ["Phase", (s) => esc(GROUP_META[s._class.group]?.label)],
    ["Council", (s) => esc(laName(s._la))],
    ["Type", (s) => esc(s._class.independent ? "Independent" : s.type_group)],
    ["Distance", (s) => (s._dist != null ? fmt.mi(s._dist) : "–")],
    ["Your chances", (s) => reachPill(admissionsFor(s.urn), s._dist, s) || "–"],
    ["Ofsted", (s) => esc(s._ofsted || "–")],
    ["Pupils", (s) => fmt.num(s.pupils)],
    ["Gender", (s) => esc(s.gender || "–")],
    ["Faith", (s) => esc(s.religious_character || "–")],
    ["Free school meals (lower income)", (s) => fmt.pct(s.fsm_pct, 1)],
  ];
  const planButton = (s) =>
    isInPlan(s.urn) ? `<button class="back small" disabled>In plan</button>`
    : planFull() ? `<button class="back small" disabled>Plan full</button>`
    : `<button class="back small" data-add-plan="${s.urn}">Add to my plan</button>`;
  root.innerHTML = `
    <div style="overflow-x:auto">
      <table>
        <thead><tr><th></th>${schools.map((s) => `<th><a href="#school=${s.urn}" data-urn="${s.urn}">${esc(s.name)}</a><br><button class="back small" data-remove="${s.urn}">Remove</button> ${planButton(s)}</th>`).join("")}</tr></thead>
        <tbody>${rows.map(([label, f]) => `<tr><th>${label}</th>${schools.map((s) => `<td>${f(s)}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>
    </div>
    <p class="note">Saved in this browser only.</p>`;
  $$("[data-urn]", root).forEach((a) => a.addEventListener("click", (e) => { e.preventDefault(); onSelect(Number(a.dataset.urn)); }));
  $$("[data-remove]", root).forEach((b) => b.addEventListener("click", () => toggleShortlist(b.dataset.remove)));
  $$("[data-add-plan]", root).forEach((b) => b.addEventListener("click", () => { addToPlan(Number(b.dataset.addPlan)); renderShortlist(onSelect); }));
}
