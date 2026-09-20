import { $, $$, esc, fmt } from "./util.js";
import { state, on, matchesPhase, admissionsFor, laForDistrict, isFaithSchool, laName , isSelectiveSchool } from "./state.js";
import { chanceModel, chanceAt, RULE_CAVEATS } from "./admissions.js";
import { addToPlan, isInPlan, planFull } from "./planner.js";

const CSS = "css/welcome.css";

function injectCss() {
  if (!document.querySelector(`link[href="${CSS}"]`)) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = CSS;
    document.head.appendChild(link);
  }
}

const fmtDate = (d) => d.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
const fmtDateShort = (d) => d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

function nextWorkingDay(d) {
  const x = new Date(d);
  while (x.getDay() === 0 || x.getDay() === 6) x.setDate(x.getDate() + 1);
  return x;
}

export function initHelpMe({ selectSchool, applyPostcode }) {
  injectCss();

  const thisYear = new Date().getFullYear();
  let step = 0;
  let entry = null; // { phase, entryYear, applyFrom, deadline, offerDay }

  /* ---------- DOM ---------- */

  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "helpme-btn";
  btn.textContent = "Help me!";
  btn.setAttribute("aria-haspopup", "dialog");

  const backdrop = document.createElement("div");
  backdrop.className = "helpme-backdrop";
  backdrop.hidden = true;

  const sheet = document.createElement("div");
  sheet.className = "helpme-sheet";
  sheet.setAttribute("role", "dialog");
  sheet.setAttribute("aria-modal", "true");
  sheet.setAttribute("aria-label", "Help me find a school");
  sheet.innerHTML = `
    <div class="helpme-head">
      <button type="button" class="helpme-x" aria-label="Close guide">✕</button>
      <h2 class="helpme-title">Help me find a school</h2>
      <div class="helpme-progress" aria-hidden="true"><div class="helpme-progress-bar"></div></div>
      <p class="helpme-step-label"></p>
    </div>
    <div class="helpme-body"></div>
    <div class="helpme-foot">
      <button type="button" class="btn secondary" id="helpme-back">Back</button>
      <span class="helpme-foot-right">
        <button type="button" class="btn secondary" id="helpme-plan" hidden>Open My plan</button>
        <button type="button" class="btn" id="helpme-next">Next</button>
      </span>
    </div>`;

  document.body.appendChild(btn);
  document.body.appendChild(backdrop);
  document.body.appendChild(sheet);

  const body = $(".helpme-body", sheet);
  const bar = $(".helpme-progress-bar", sheet);
  const label = $(".helpme-step-label", sheet);
  const backBtn = $("#helpme-back", sheet);
  const nextBtn = $("#helpme-next", sheet);
  const planBtn = $("#helpme-plan", sheet);

  /* ---------- shared helpers ---------- */

  const phase = () => entry?.phase || "primary";

  // Schools from other councils may still be loaded in the map view, so keep suggestions local:
  // 6 miles is a normal school run; widen only when a rural area has too few.
  const NEAR_MILES = [6, 15, 30];

  function phaseSchools() {
    // "Other types" in the DfE register covers secure units and similar: not schools a family applies to.
    const all = state.schools.filter((s) => s.lat != null && matchesPhase(s, phase()) && !s._class.independent && !/other types/i.test(s.type_group || ""));
    if (!state.home) return all;
    for (const miles of NEAR_MILES) {
      const near = all.filter((s) => s._dist != null && s._dist <= miles);
      if (near.length >= 6) return near;
    }
    return all.filter((s) => s._dist != null && s._dist <= NEAR_MILES[NEAR_MILES.length - 1]);
  }

  function chanceFor(s) {
    const rec = admissionsFor(s.urn);
    const model = rec && chanceModel(rec);
    return model?.kind === "distance" && s._dist != null ? chanceAt(model, s._dist) : null;
  }

  function schoolRow(s, chance) {
    const inPlan = isInPlan(s.urn);
    const disabled = inPlan || planFull();
    return `<div class="helpme-school">
      <div class="helpme-school-main">
        <strong>${esc(s.name)}</strong>
        <span>${esc(laName(s._la))}${s._dist != null ? ` · ${fmt.mi(s._dist)}` : ""}${chance != null ? ` · ${Math.round(chance * 100)}% chance` : ""}</span>
      </div>
      <div class="helpme-school-actions">
        <button type="button" data-select="${s.urn}">View</button>
        <button type="button" data-add="${s.urn}" ${disabled ? "disabled" : ""}>${inPlan ? "In plan" : "Add to my plan"}</button>
      </div>
    </div>`;
  }

  /* ---------- step renderers ---------- */

  function stepOneHtml() {
    const h = state.home;
    const la = h?.districtCode ? laForDistrict(h.districtCode) : null;
    const council = la?.name || h?.district || "";
    return `
      <h3>Where do you live?</h3>
      <p>Tell us your postcode so we can show schools near you and work out which council you'll apply through.</p>
      ${h ? `<div class="helpme-card"><b>Your home</b><p>You've already set a pin${council ? ` in ${esc(council)}` : ""}. Everything is measured from there.</p></div>` : ""}
      <form class="helpme-inline" id="helpme-form">
        <input id="helpme-postcode" placeholder="Postcode, e.g. E8 1DY" autocapitalize="characters" inputmode="text" aria-label="Postcode">
        <button type="submit">Find schools</button>
      </form>
      <p class="helpme-msg" id="helpme-msg" role="status" hidden></p>
      ${h ? `<p><button type="button" class="btn secondary" id="helpme-use-pin">Use the pin I already set</button></p>` : ""}`;
  }

  function computeEntry(month, year, ph) {
    const receptionYear = month >= 8 ? year + 5 : year + 4; // September (0-indexed 8) after the 4th birthday
    const secondaryYear = receptionYear + 7;
    if (ph === "primary") {
      const entryYear = receptionYear;
      return { phase: "primary", entryYear, applyFrom: new Date(entryYear - 1, 8, 1), deadline: new Date(entryYear, 0, 15), offerDay: nextWorkingDay(new Date(entryYear, 3, 16)) };
    }
    const entryYear = secondaryYear;
    return { phase: "secondary", entryYear, applyFrom: new Date(entryYear - 1, 8, 1), deadline: new Date(entryYear - 1, 9, 31), offerDay: nextWorkingDay(new Date(entryYear, 2, 1)) };
  }

  function stepTwoHtml() {
    const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
    const years = [];
    for (let y = thisYear - 16; y <= thisYear; y++) years.push(y);
    return `
      <h3>When was your child born?</h3>
      <p>We'll use their month and year of birth to work out when they start school and when to apply.</p>
      <div class="helpme-inline">
        <select id="helpme-month" aria-label="Birth month"><option value="" selected>Month</option>${months.map((m, i) => `<option value="${i}">${m}</option>`).join("")}</select>
        <select id="helpme-year" aria-label="Birth year"><option value="" selected>Year</option>${years.reverse().map((y) => `<option value="${y}">${y}</option>`).join("")}</select>
      </div>
      <div class="helpme-phase" role="radiogroup" aria-label="School phase">
        <label><input type="radio" name="helpme-phase" value="primary" checked> Primary (Reception)</label>
        <label><input type="radio" name="helpme-phase" value="secondary"> Secondary (Year 7)</label>
      </div>
      <div id="helpme-entry"></div>`;
  }

  function stepThreeHtml() {
    const ph = phase();
    const govLink = ph === "secondary" ? "https://www.gov.uk/apply-for-secondary-school-place" : "https://www.gov.uk/apply-for-primary-school-place";
    const london = state.home?.districtCode && laForDistrict(state.home.districtCode)?.region === "London";
    return `
      <h3>How to apply</h3>
      <p>You apply through your home council, even for schools in another borough. The council co-ordinates everything with you.</p>
      <ul class="helpme-list">
        <li>Start on GOV.UK — <a href="${govLink}" target="_blank" rel="noopener">${govLink}</a> — it routes you to your council's form.</li>
        ${london ? `<li>London families apply through <a href="https://www.eadmissions.org.uk" target="_blank" rel="noopener">eAdmissions</a>.</li>` : ""}
        <li>You can usually list up to 6 schools in London, and 3 to 6 elsewhere — check your council.</li>
        <li>List schools in the order you truly want them. Ranking a school lower never hurts your chances at it: every school treats your application as if it were your first choice.</li>
      </ul>`;
  }

  function stepFourHtml() {
    const ph = phase();
    if (!state.schools.length) {
      return `<h3>Schools where you have a good chance</h3><p>Search a postcode first, then come back — we'll list schools you have a real chance at.</p>`;
    }
    const cands = phaseSchools();
    if (!cands.length) {
      return `<h3>Schools where you have a good chance</h3><p>We haven't found ${ph === "primary" ? "primary" : "secondary"} schools near you yet. Search a postcode or zoom the map.</p>`;
    }
    const scored = cands.map((s) => ({ s, chance: chanceFor(s) })).sort((a, b) => (b.chance ?? -1) - (a.chance ?? -1));
    const hasChance = scored.some((x) => x.chance != null);
    if (!hasChance) {
      const nearest = cands.slice().sort((a, b) => (a._dist ?? Infinity) - (b._dist ?? Infinity)).slice(0, 6);
      return `<h3>Schools where you have a good chance</h3>
        <p>We don't have past cut-off figures for your council yet, so we can't estimate chances. These are your nearest ${ph === "primary" ? "primary" : "secondary"} schools instead.</p>
        ${nearest.map((s) => schoolRow(s, null)).join("")}`;
    }
    const byDist = (a, b) => (a.s._dist ?? Infinity) - (b.s._dist ?? Infinity);
    const likely = scored.filter((x) => x.chance >= 0.8).sort(byDist).slice(0, 4);
    const good = scored.filter((x) => x.chance >= 0.6 && x.chance < 0.8).sort(byDist).slice(0, 4);
    const worth = scored.filter((x) => x.chance >= 0.2 && x.chance < 0.6).sort(byDist).slice(0, 4);
    const longer = scored.filter((x) => x.chance != null && x.chance < 0.2).sort(byDist).slice(0, 4);
    const unknown = scored.filter((x) => x.chance == null).sort(byDist).slice(0, 3);
    const group = (list, title, note) => (list.length ? `<p class="helpme-msg"><b>${title}</b> — ${note}</p>` + list.map((x) => schoolRow(x.s, x.chance)).join("") : "");
    return `<h3>Schools you could put on your list</h3>
      <p>Based on past offer days${state.home ? ", measured from your home" : ""}. Chances are estimates, not promises. You can usually name six schools, and ranking one higher never hurts your chances at the others, so it's worth mixing likely ones with those you'd love.</p>
      ${group(likely, "Very likely", "almost everyone at your distance was offered a place. One of these is a good safety net.")}
      ${group(good, "Good chance", "places usually reached families like yours.")}
      ${group(worth, "Worth a try", "places sometimes reached families like yours.")}
      ${group(longer, "A long shot, but you can still list them", "places haven't reached this far lately. Waiting lists do move over the summer.")}
      ${group(unknown, "We don't have figures for these yet", "nearby schools we can't estimate. Their own pages still show results, Ofsted and more.")}
      ${!likely.length && !good.length && !worth.length && !longer.length && !unknown.length ? `<p>We couldn't find schools to suggest near you. Try the map, and see the next step for what else can help.</p>` : ""}`;
  }

  function stepFiveHtml() {
    const cands = phaseSchools();
    const models = cands.map((s) => chanceModel(admissionsFor(s.urn))).filter(Boolean);
    const hasSelective = models.some((m) => m.kind === "rule" && m.rule === RULE_CAVEATS.selective) || phaseSchools().some(isSelectiveSchool);
    const hasCatchment = models.some((m) => m.kind === "rule" && (m.rule === RULE_CAVEATS.catchment_then_distance || m.rule === RULE_CAVEATS.nodal_point));
    const hasFaith = cands.some(isFaithSchool);
    const chips = [
      `<div class="helpme-chip"><b>Siblings</b>If an older brother or sister already goes to a school, your child usually gets priority there. It's the single biggest boost to your chances.</div>`,
      `<div class="helpme-chip"><b>Looked-after children</b>Children who are looked after (or were) get top priority at most schools. If this applies to you, the school and council will tell you what to provide.</div>`,
    ];
    if (hasFaith) chips.push(`<div class="helpme-chip"><b>Faith schools</b>Some schools give priority to families of a particular faith. Check the school's admissions policy for what evidence they need, and note the deadline for faith forms.</div>`);
    if (hasSelective) {
      chips.push(`<div class="helpme-chip"><b>Banding tests</b>Some areas test all children in the autumn of Year 6 and spread places across ability bands. You don't need to prepare — the band, not the score, decides which group you're in.</div>`);
      chips.push(`<div class="helpme-chip"><b>Selective school tests</b>Grammar and other selective schools set their own test. Registration is usually May to July of Year 5, with the test that September of Year 6. Register on time — late entries often can't sit it.</div>`);
    }
    if (hasCatchment) chips.push(`<div class="helpme-chip"><b>Catchment areas and nodal points</b>Some schools give priority to homes inside a catchment area, or measure distance from a fixed point instead of the school gate. Check the council's catchment map to see which side of the line you're on.</div>`);
    return `<h3>Things that can change your chances</h3>
      <p>These are the ones that could matter near you. Every school also explains its own rules in its admissions policy.</p>
      ${chips.join("")}`;
  }

  function stepSixHtml() {
    const e = entry;
    const items = [];
    const today = new Date();
    if (e && new Date(e.entryYear, 8, 1) < today) {
      items.push(`<li><b>Contact your council's admissions team</b> to ask which schools near you have space right now.</li>`);
      items.push(`<li><b>Make an in-year application</b>. You can do this at any time of year.</li>`);
      items.push(`<li><b>Ask to join waiting lists</b> for the schools you'd love. Places often come up during the year.</li>`);
    } else if (e && e.deadline < today) {
      items.push(`<li><b>Apply as soon as you can</b> through your council. Late applications are still considered.</li>`);
      items.push(`<li><b>National Offer Day, ${fmtDate(e.offerDay)}</b>: on-time applications hear first, and late ones follow.</li>`);
    } else if (e) {
      items.push(`<li><b>Visit open days</b> — usually September and October before you apply.</li>`);
      items.push(`<li><b>Register for any tests</b> the schools near you need (see the previous step).</li>`);
      items.push(`<li><b>Apply by ${fmtDate(e.deadline)}</b> through your council.</li>`);
      items.push(`<li><b>National Offer Day, ${fmtDate(e.offerDay)}</b> — you'll hear which school offered a place.</li>`);
    } else {
      items.push(`<li><b>Visit open days</b> — usually September and October before you apply.</li>`);
      items.push(`<li><b>Apply by the deadline</b> — 31 October for secondary, 15 January for Reception.</li>`);
      items.push(`<li><b>National Offer Day</b> — 1 March for secondary, 16 April for Reception.</li>`);
    }
    items.push(`<li><b>Accept your place</b> by the date in your offer.</li>`);
    items.push(`<li><b>Join waiting lists</b> for any school you'd prefer — accepting your offer doesn't hurt your place on them.</li>`);
    items.push(`<li><b>Appeal</b> if you're unhappy — the council will tell you how.</li>`);
    return `<h3>Your next steps</h3>
      <p>A short list, in order. We'll keep the dates handy.</p>
      <ul class="helpme-list">${items.join("")}</ul>
      <p>Ready to rank schools? Open My plan and add the ones you like.</p>`;
  }

  const RENDERERS = [stepOneHtml, stepTwoHtml, stepThreeHtml, stepFourHtml, stepFiveHtml, stepSixHtml];

  function bindStep(i) {
    if (i === 0) {
      const msg = $("#helpme-msg", body);
      const form = $("#helpme-form", body);
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const value = $("#helpme-postcode", body).value.trim();
        if (!value) { msg.textContent = "Type a postcode first."; msg.hidden = false; return; }
        msg.hidden = false;
        msg.textContent = "Looking it up…";
        const ok = await applyPostcode(value);
        if (ok) { msg.hidden = true; step = 1; render(); }
        else { msg.textContent = "We couldn't find that postcode. Check it and try again."; }
      });
      const usePin = $("#helpme-use-pin", body);
      if (usePin) usePin.addEventListener("click", () => { step = 1; render(); });
    }
    if (i === 1) {
      const month = $("#helpme-month", body);
      const year = $("#helpme-year", body);
      const radios = $$('input[name="helpme-phase"]', body);
      let phaseChosenByHand = false;
      radios.forEach((r) => r.addEventListener("change", () => { phaseChosenByHand = true; }));
      const update = (e) => {
        const box = $("#helpme-entry", body);
        if (month.value === "" || year.value === "") {
          entry = null;
          box.innerHTML = `<p class="helpme-msg">Choose your child's birth month and year and we'll work out your dates.</p>`;
          return;
        }
        const today = new Date();
        // Guess the move the family is most likely planning, unless they chose one themselves:
        // Reception while its deadline is ahead, secondary from about Year 4, otherwise a move within their current phase.
        if (!phaseChosenByHand) {
          const primary = computeEntry(Number(month.value), Number(year.value), "primary");
          const secondaryStart = new Date(computeEntry(Number(month.value), Number(year.value), "secondary").entryYear, 8, 1);
          const threeYears = 3 * 365 * 864e5;
          const pick = primary.deadline >= today ? "primary" : secondaryStart - today < threeYears ? "secondary" : "primary";
          radios.forEach((r) => { r.checked = r.value === pick; });
        }
        entry = computeEntry(Number(month.value), Number(year.value), [...radios].find((r) => r.checked)?.value || "primary");
        const starts = new Date(entry.entryYear, 8, 1);
        let note = "";
        if (starts < today) note = `<p>That start date has already passed. If your child is already at school and you'd like them to move, you can make an <strong>in-year application</strong> to your council at any time. Schools with space can offer a place straight away.</p>`;
        else if (entry.deadline < today) note = `<p>The on-time deadline has passed, but you can still apply. Your council will explain how late applications are handled, and it's worth applying as soon as you can.</p>`;
        box.innerHTML = `<div class="helpme-card">
          <b>Your child ${starts < today ? "started" : "starts"} ${entry.phase === "primary" ? "Reception" : "secondary school"} in September ${entry.entryYear}.</b>
          ${note || `<p>Applications open around ${fmtDateShort(entry.applyFrom)} and close on <strong>${fmtDate(entry.deadline)}</strong>.</p>
          <p>National Offer Day, when you hear which school offered a place, is <strong>${fmtDate(entry.offerDay)}</strong>.</p>`}
        </div>`;
      };
      [month, year, ...radios].forEach((el) => el.addEventListener("change", update));
      update();
    }
    if (i === 3) {
      $$("[data-select]", body).forEach((b) => b.addEventListener("click", () => { closeGuide({ keepHistory: true }); selectSchool(Number(b.dataset.select)); }));
      $$("[data-add]", body).forEach((b) => b.addEventListener("click", () => { addToPlan(Number(b.dataset.add)); render(); }));
    }
  }

  function render() {
    body.innerHTML = RENDERERS[step]();
    bar.style.width = `${((step + 1) / 6) * 100}%`;
    label.textContent = `Step ${step + 1} of 6`;
    backBtn.disabled = step === 0;
    nextBtn.textContent = step === 5 ? "Close" : "Next";
    planBtn.hidden = step !== 5;
    bindStep(step);
    body.scrollTop = 0;
  }

  /* ---------- open / close ---------- */

  // A history entry per opening, so Back closes the guide instead of leaving the site.
  let pushed = false;

  function openGuide() {
    if (sheet.classList.contains("open")) return;
    if (!pushed) { history.pushState({ overlay: "helpme" }, "", location.href); pushed = true; }
    document.body.classList.add("helpme-open");
    sheet.classList.add("open");
    backdrop.hidden = false;
    render();
    requestAnimationFrame(() => nextBtn.focus());
  }

  function closeGuide({ fromPop = false, keepHistory = false } = {}) {
    if (!sheet.classList.contains("open")) return;
    sheet.classList.remove("open");
    backdrop.hidden = true;
    document.body.classList.remove("helpme-open");
    btn.focus();
    const hadEntry = pushed;
    pushed = false;
    if (hadEntry && !fromPop && !keepHistory) history.back();
  }

  window.addEventListener("popstate", () => { if (sheet.classList.contains("open")) closeGuide({ fromPop: true }); });

  btn.addEventListener("click", openGuide);
  // The same guide, offered at the top of the schools list.
  document.querySelector("#plan-cta")?.addEventListener("click", openGuide);
  $(".helpme-x", sheet).addEventListener("click", () => closeGuide());
  backdrop.addEventListener("click", () => closeGuide());

  nextBtn.addEventListener("click", () => {
    if (step === 5) { closeGuide(); return; }
    step += 1;
    render();
  });
  backBtn.addEventListener("click", () => { step -= 1; render(); });

  planBtn.addEventListener("click", () => {
    closeGuide({ keepHistory: true });
    document.querySelector('.tabs [data-view="plan"]')?.click();
  });

  sheet.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { closeGuide(); return; }
    if (e.key !== "Tab") return;
    const focusables = [...sheet.querySelectorAll('button, input, select, a[href]')].filter((el) => !el.disabled && !el.hidden && el.offsetParent !== null);
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  // Keep the guide current as schools and home load or change.
  on("schools", () => { if (sheet.classList.contains("open") && (step === 3 || step === 4)) render(); });
  on("home", () => { if (sheet.classList.contains("open") && step === 0) render(); });
}
