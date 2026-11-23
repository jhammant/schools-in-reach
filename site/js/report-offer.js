// A demand test for a paid "Your chances" report, before the report is built.
//
// On the results list for a home in a council whose Reception cut-offs we hold, a button offers
// the full report at £9.99. Pressing it opens a short panel: the report is coming in early
// December, and an email box to be told when it is ready. Nothing is sold or charged.
//
// Three analytics events measure demand: the offer being shown, the button being pressed and an
// email being saved. Their properties are the council code and the phase filter, nothing more:
// never a postcode, coordinates, the email address or anything about a child.
//
// This module imports nothing; app.js hands it the config, the tracker and fetch, so it can be
// tested in Node with stand-ins.

export const EVENTS = {
  shown: "report_cta_shown",
  clicked: "report_cta_clicked",
  signedUp: "report_email_signup",
  failed: "report_email_signup_failed",
};

/** The only properties any report event may carry. */
export const EVENT_KEYS = ["council_code", "phase", "reason"];

/** A plausible email address: one @, a dot in the domain, no spaces or markup, at most 254 characters. */
export function isLikelyEmail(value) {
  const email = String(value ?? "").trim();
  if (!email || email.length > 254) return false;
  const match = /^([^\s@<>()[\]\\,;:"']+)@([^\s@<>()[\]\\,;:"']+\.[^\s@<>()[\]\\,;:"'.]{2,})$/.exec(email);
  return Boolean(match) && match[1].length <= 64 && !match[2].includes("..");
}

const PHASES = { primary: "primary", "": "all" };

/**
 * Whether the offer belongs on the results now, and for which council. Pure, so it can be tested.
 *
 * Shown only when: the test is switched on and before its end date; a home is set and the list
 * is showing schools around it (not a map dragged elsewhere); the list includes primary schools
 * (the Primary switch, or all phases); and the home's council has published Reception cut-offs.
 */
export function offerFor({ config, today, hasHome, awayFromHome, phase, councilCode, admissions }) {
  if (!config?.enabled) return null;
  if (config.endsOn && today >= config.endsOn) return null;
  if (!hasHome || awayFromHome) return null;
  if (!(String(phase ?? "") in PHASES)) return null;
  if (!councilCode || !admissions?.primary || !Object.keys(admissions.primary).length) return null;
  return { council_code: String(councilCode), phase: PHASES[String(phase ?? "")] };
}

/** Event properties, cut down to the allowed keys. Anything else passed in is dropped. */
export function eventProps(context, extra = {}) {
  const props = { council_code: context.council_code, phase: context.phase, ...extra };
  return Object.fromEntries(Object.entries(props).filter(([key, value]) => EVENT_KEYS.includes(key) && value != null));
}

/**
 * Send one sign-up to the endpoint. The body is text/plain JSON, so the browser sends it without a
 * CORS preflight. Resolves { ok } or { ok: false, reason }; never throws.
 */
export async function sendSignup({ url, email, honeypot = "", fetchImpl, timeoutMs = 10000 }) {
  try {
    const response = await fetchImpl(url, {
      method: "POST",
      mode: "cors",
      credentials: "omit",
      referrerPolicy: "no-referrer",
      headers: { "content-type": "text/plain;charset=UTF-8" },
      body: JSON.stringify({ email: String(email).trim(), website: honeypot }),
      signal: typeof AbortSignal !== "undefined" && AbortSignal.timeout ? AbortSignal.timeout(timeoutMs) : undefined,
    });
    if (response.ok) return { ok: true };
    const reasons = { 400: "invalid", 410: "closed", 429: "rate_limited" };
    return { ok: false, reason: reasons[response.status] || "rejected" };
  } catch {
    return { ok: false, reason: "network" };
  }
}

const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

/** The offer's markup. The email form appears only when an endpoint is configured. */
export function offerHtml(config) {
  const price = esc(config.price || "£9.99");
  const form = config.notifyUrl
    ? `<form class="report-offer-form" data-report-form novalidate>
        <label for="report-offer-email">Email me when it's ready</label>
        <div class="report-offer-row">
          <input id="report-offer-email" name="email" type="email" autocomplete="email" inputmode="email" maxlength="254" required placeholder="you@example.com">
          <button type="submit">Tell me</button>
        </div>
        <div class="report-offer-trap" aria-hidden="true"><label>Leave this empty <input name="website" tabindex="-1" autocomplete="off"></label></div>
        <p class="report-offer-small">We'll use your email only to tell you once, when the report is ready, and delete it by the end of January 2027. <a href="privacy.html#report-email">Privacy</a></p>
      </form>`
    : "";
  return `
    <p class="report-offer-lead">Your chances at every Reception school near you, side by side, in one report.</p>
    <button type="button" class="report-offer-btn" data-report-open aria-expanded="false" aria-controls="report-offer-panel">Get the full report, ${price}</button>
    <div id="report-offer-panel" class="report-offer-panel" role="region" aria-labelledby="report-offer-title" hidden>
      <h3 id="report-offer-title" tabindex="-1">The “Your chances” report is coming in early December</h3>
      <p>It will show your chance of a Reception place at each school near your home, side by side, with the past cut-offs behind each estimate, as a PDF you can keep. There is nothing to pay today.</p>
      ${form}
      <p class="report-offer-status" data-report-status role="status" aria-live="polite"></p>
      <button type="button" class="link-btn report-offer-close" data-report-close>No thanks</button>
    </div>`;
}

const FAILURE_TEXT = {
  invalid: "That doesn't look like an email address. Please check it and try again.",
  rate_limited: "We've had a few tries from here just now. Please try again in a few minutes.",
  closed: "Sign-ups for this report have closed.",
  rejected: "Sorry, that didn't save. Please try again in a minute.",
  network: "Sorry, that didn't save. Please check your connection and try again.",
};

/**
 * Wire the offer into its container. Returns { update(input) }, which app.js calls whenever the
 * results list is redrawn. Every analytics call goes through `track`, which never throws.
 */
export function createReportOffer({ root, config, track, fetchImpl, today = () => new Date().toISOString().slice(0, 10) }) {
  const safeTrack = (name, props) => { try { track(name, props); } catch { /* analytics must never break the site */ } };
  const shown = new Set();
  let context = null;
  let built = false;
  let busy = false;
  let done = false;

  function build() {
    built = true;
    root.innerHTML = offerHtml(config);
    const open = root.querySelector("[data-report-open]");
    const panel = root.querySelector("#report-offer-panel");
    const close = root.querySelector("[data-report-close]");
    const form = root.querySelector("[data-report-form]");
    const status = root.querySelector("[data-report-status]");
    const setOpen = (isOpen) => {
      panel.hidden = !isOpen;
      open.setAttribute("aria-expanded", String(isOpen));
    };
    open.addEventListener("click", () => {
      const opening = panel.hidden;
      setOpen(opening);
      if (!opening) return;
      if (context) safeTrack(EVENTS.clicked, eventProps(context));
      const email = root.querySelector("#report-offer-email");
      (email && !done ? email : root.querySelector("#report-offer-title"))?.focus?.();
    });
    close.addEventListener("click", () => {
      setOpen(false);
      open.focus?.();
    });
    form?.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (busy || done) return;
      const asked = context; // the list may redraw while the request is out
      const email = form.querySelector("#report-offer-email");
      const honeypot = form.querySelector('[name="website"]')?.value || "";
      if (!isLikelyEmail(email.value)) {
        status.textContent = FAILURE_TEXT.invalid;
        email.focus?.();
        return;
      }
      busy = true;
      status.textContent = "Saving…";
      const result = await sendSignup({ url: config.notifyUrl, email: email.value, honeypot, fetchImpl });
      busy = false;
      if (result.ok) {
        done = true;
        form.hidden = true;
        status.textContent = "Thanks. We'll email you once, when the report is ready.";
        if (asked) safeTrack(EVENTS.signedUp, eventProps(asked));
      } else {
        status.textContent = FAILURE_TEXT[result.reason] || FAILURE_TEXT.rejected;
        if (asked) safeTrack(EVENTS.failed, eventProps(asked, { reason: result.reason }));
      }
    });
  }

  /**
   * Show or hide the offer for the current results. `inView` is false while another view covers
   * the list (a school page, the league tables): the offer is kept up to date but its impression
   * waits until the list is on screen, so the count of views stays honest.
   */
  function update({ inView = true, ...input }) {
    context = offerFor({ config, today: today(), ...input });
    if (!context) {
      root.hidden = true;
      return;
    }
    if (!built) build();
    root.hidden = false;
    const key = `${context.council_code}|${context.phase}`;
    if (inView && !shown.has(key)) {
      shown.add(key);
      safeTrack(EVENTS.shown, eventProps(context));
    }
  }

  return { update };
}
