import { store } from "./util.js";

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

/** The next application deadline from today: secondary (31 Oct) or Reception (15 Jan), whichever comes first. */
function nextDeadline(today) {
  const y = today.getFullYear();
  const sec = today <= new Date(y, 9, 31)
    ? { phase: "secondary", entryYear: y + 1, date: new Date(y, 9, 31) }
    : { phase: "secondary", entryYear: y + 2, date: new Date(y + 1, 9, 31) };
  const rec = today <= new Date(y, 0, 15)
    ? { phase: "reception", entryYear: y, date: new Date(y, 0, 15) }
    : { phase: "reception", entryYear: y + 1, date: new Date(y + 1, 0, 15) };
  return sec.date <= rec.date ? sec : rec;
}

const ART = `<svg class="welcome-art" viewBox="0 0 420 120" role="img" aria-label="A winding path leads from a house to a school under a sunny sky">
  <circle cx="382" cy="26" r="14" style="fill:var(--s4)"/>
  <circle cx="382" cy="26" r="22" style="fill:var(--s4)" opacity="0.18"/>
  <path d="M0 94 C 90 78, 150 106, 210 98 S 350 82, 420 94" fill="none" stroke="currentColor" stroke-width="2" opacity="0.5"/>
  <rect x="52" y="70" width="58" height="40" rx="4" style="fill:var(--s2)" stroke="currentColor" stroke-width="2"/>
  <path d="M42 72 L81 44 L120 72 Z" style="fill:var(--s1)" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
  <rect x="72" y="86" width="16" height="24" rx="2" style="fill:var(--surface-1)" stroke="currentColor" stroke-width="2"/>
  <circle cx="60" cy="84" r="4" style="fill:var(--surface-1)"/>
  <path d="M80 110 C 132 88, 172 128, 216 108 S 302 82, 342 110" fill="none" style="stroke:var(--s3)" stroke-width="3" stroke-linecap="round"/>
  <rect x="178" y="88" width="4" height="12" style="fill:var(--surface-1)" stroke="currentColor" stroke-width="2"/>
  <circle cx="180" cy="84" r="9" style="fill:var(--s3)" stroke="currentColor" stroke-width="2"/>
  <rect x="300" y="62" width="84" height="48" rx="4" style="fill:var(--s1)" stroke="currentColor" stroke-width="2"/>
  <path d="M292 64 L342 40 L392 64 Z" style="fill:var(--s2)" stroke="currentColor" stroke-width="2" stroke-linejoin="round"/>
  <line x1="342" y1="40" x2="342" y2="28" stroke="currentColor" stroke-width="2"/>
  <path d="M342 28 L354 32 L342 36 Z" style="fill:var(--s4)"/>
  <rect x="334" y="82" width="16" height="28" rx="2" style="fill:var(--surface-1)" stroke="currentColor" stroke-width="2"/>
  <rect x="306" y="70" width="16" height="12" rx="1.5" style="fill:var(--surface-1)"/>
  <rect x="362" y="70" width="16" height="12" rx="1.5" style="fill:var(--surface-1)"/>
  <rect x="306" y="88" width="16" height="12" rx="1.5" style="fill:var(--surface-1)"/>
  <rect x="362" y="88" width="16" height="12" rx="1.5" style="fill:var(--surface-1)"/>
</svg>`;

const ICON_PIN = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-7-5.3-7-11a7 7 0 0 1 14 0c0 5.7-7 11-7 11z"/><circle cx="12" cy="10" r="2.6"/></svg>`;
const ICON_CHANCE = `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="3.2"/><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="10" stroke-dasharray="2 3"/></svg>`;
const ICON_PLAN = `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="3" width="16" height="18" rx="2"/><path d="M8 9l2 2 3-3M8 15l2 2 3-3"/></svg>`;

export function initWelcome({ applyPostcode, useMyLocation, explore }) {
  injectCss();

  const d = nextDeadline(new Date());
  const deadlineText = d.phase === "secondary"
    ? `Applying for September ${d.entryYear}? Secondary deadline: ${fmtDate(d.date)}`
    : `Applying for September ${d.entryYear}? Reception deadline: ${fmtDate(d.date)}`;

  const wrap = document.createElement("div");
  wrap.className = "welcome";
  wrap.id = "welcome";
  wrap.setAttribute("role", "dialog");
  wrap.setAttribute("aria-modal", "true");
  wrap.setAttribute("aria-labelledby", "welcome-title");
  wrap.hidden = true;
  wrap.innerHTML = `
    <div class="welcome-backdrop" data-close></div>
    <div class="welcome-card" role="document">
      <button type="button" class="welcome-close" aria-label="Close welcome" data-close>✕</button>
      ${ART}
      <h1 class="welcome-title" id="welcome-title">Finding the right school, together</h1>
      <p class="welcome-sub">See which schools could work for your family, how places were given out in past years, and what happens when — all in plain English.</p>
      <fieldset class="welcome-phase">
        <legend>Which school are you looking for?</legend>
        <div class="welcome-phase-opts">
          <label class="welcome-phase-opt"><input type="radio" name="welcome-phase" value="primary">
            <span class="welcome-phase-main">Primary school</span>
            <span class="welcome-phase-note">Starting Reception, ages 4 to 11</span></label>
          <label class="welcome-phase-opt"><input type="radio" name="welcome-phase" value="secondary">
            <span class="welcome-phase-main">Secondary school</span>
            <span class="welcome-phase-note">Starting Year 7, ages 11 and up</span></label>
        </div>
      </fieldset>
      <form class="welcome-search" autocomplete="off">
        <label class="sr-only" for="welcome-postcode">Postcode</label>
        <input id="welcome-postcode" inputmode="text" placeholder="Enter a postcode, for example E8 1DY" autocapitalize="characters">
        <button type="submit" class="welcome-primary">Show schools near me</button>
      </form>
      <p class="welcome-error" data-role="error" role="alert" hidden></p>
      <div class="welcome-alt">
        <button type="button" class="btn secondary" data-action="locate">📍 Use my location</button>
        <button type="button" class="btn secondary" data-action="explore">Just explore the map</button>
      </div>
      <div class="welcome-steps">
        <div class="welcome-step"><span class="welcome-step-icon">${ICON_PIN}</span><b>1 · Tell us where you live</b><span>Type a postcode or drop a pin — everything is measured from home.</span></div>
        <div class="welcome-step"><span class="welcome-step-icon">${ICON_CHANCE}</span><b>2 · See your chances</b><span>The map turns green where places are likely.</span></div>
        <div class="welcome-step"><span class="welcome-step-icon">${ICON_PLAN}</span><b>3 · Make a plan</b><span>Rank schools, try what-ifs and see the dates.</span></div>
      </div>
      <div class="welcome-reassure">
        <p><span class="welcome-tick">✓</span><span>Every child who applies gets offered a school place: we'll help you choose the ones you'd love.</span></p>
        <p><span class="welcome-tick">✓</span><span>Free, and no sign-up.</span></p>
        <p><span class="welcome-tick">✓</span><span>Everything is an estimate from council data, not a promise.</span></p>
      </div>
      <div class="welcome-deadline"><span class="welcome-deadline-pill">${deadlineText}</span></div>
      <p class="welcome-kids">Starting a new school soon? This is for you too.</p>
    </div>`;

  document.body.appendChild(wrap);

  const postcode = wrap.querySelector("#welcome-postcode");
  const phaseRadios = [...wrap.querySelectorAll('input[name="welcome-phase"]')];

  /** Point the whole site at primary or secondary: the list filter drives the map too. */
  function applyPhase(value) {
    store.set("phase", value);
    const select = document.querySelector("#filter-phase");
    if (select && select.value !== value) {
      select.value = value;
      select.dispatchEvent(new Event("input", { bubbles: true }));
    }
  }

  /** True when a phase is chosen; otherwise ask for one, kindly. */
  function phaseChosen() {
    const picked = phaseRadios.find((r) => r.checked);
    if (!picked) {
      showError("First, tell us whether you're looking for a primary or a secondary school.");
      wrap.querySelector(".welcome-phase").classList.add("needs-answer");
      phaseRadios[0].focus();
      return false;
    }
    applyPhase(picked.value);
    return true;
  }

  phaseRadios.forEach((r) => r.addEventListener("change", () => {
    errorEl.hidden = true;
    wrap.querySelector(".welcome-phase").classList.remove("needs-answer");
    applyPhase(r.value);
  }));
  const errorEl = wrap.querySelector('[data-role="error"]');
  const form = wrap.querySelector(".welcome-search");

  let lastFocus = null;

  function showError(msg) {
    errorEl.textContent = msg;
    errorEl.hidden = false;
  }

  // A history entry per overlay, so the Back button (or a phone's back gesture) closes it.
  let pushed = false;

  function open() {
    if (!wrap.hidden) return;
    if (!pushed) { history.pushState({ overlay: "welcome" }, "", location.href); pushed = true; }
    const saved = store.get("phase", "");
    phaseRadios.forEach((r) => { r.checked = r.value === saved; });
    lastFocus = document.activeElement;
    wrap.hidden = false;
    document.body.classList.add("welcome-open");
    requestAnimationFrame(() => postcode.focus());
  }

  function close({ fromPop = false, keepHistory = false } = {}) {
    if (wrap.hidden) return;
    wrap.hidden = true;
    document.body.classList.remove("welcome-open");
    store.set("welcomed", true);
    if (lastFocus && lastFocus.focus) lastFocus.focus();
    const hadEntry = pushed;
    pushed = false;
    if (hadEntry && !fromPop && !keepHistory) history.back();
  }

  window.addEventListener("popstate", () => { if (!wrap.hidden) close({ fromPop: true }); });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!phaseChosen()) return;
    const value = postcode.value.trim();
    if (!value) { showError("Type a postcode first."); return; }
    errorEl.hidden = true;
    const ok = await applyPostcode(value);
    if (ok) close();
    else showError("We couldn't find that postcode. Check it and try again.");
  });

  wrap.querySelector('[data-action="locate"]').addEventListener("click", async () => {
    if (!phaseChosen()) return;
    errorEl.hidden = true;
    const ok = await useMyLocation();
    if (ok) close();
    else showError("That's fine — you can type a postcode or explore the map instead.");
  });

  wrap.querySelector('[data-action="explore"]').addEventListener("click", async () => {
    if (!phaseChosen()) return;
    errorEl.hidden = true;
    await explore();
    close();
  });

  wrap.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", () => close()));

  wrap.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { close(); return; }
    if (e.key !== "Tab") return;
    const focusables = [...wrap.querySelectorAll('button, input, a[href], [tabindex]:not([tabindex="-1"])')].filter((el) => el.offsetParent !== null);
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  // Reopen from the site logo or the "Start here" button, instead of navigating away.
  const brand = document.querySelector(".brand");
  if (brand) brand.addEventListener("click", (e) => { e.preventDefault(); open(); });
  const startBtn = document.querySelector("#open-welcome");
  if (startBtn) startBtn.addEventListener("click", open);

  return open;
}
