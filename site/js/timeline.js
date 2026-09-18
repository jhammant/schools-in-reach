import { esc } from "./util.js";

const d = (y, m, day) => new Date(y, m - 1, day);

/**
 * The application journey for a school place starting in September `entryYear`,
 * as dated steps for secondary and reception entry. Every date is generated
 * from the year, so the timeline rolls forward on its own. Each step has a
 * `start` Date; its "current" window runs until the next step starts.
 */
export function buildTimeline(entryYear) {
  const y = entryYear;
  const secondary = [
    { key: "open", start: d(y - 1, 9, 1), label: "Applications open", when: `1 September ${y - 1}`, todo: "You can start your council application online. List schools in your true order of preference — your plan above is the working draft." },
    { key: "tests", start: d(y - 1, 9, 15), label: "Banding or entrance tests", when: `September–October ${y - 1}`, todo: "Some schools ask children to sit a banding or entrance test. Your primary school or the council confirms the dates; put them in the calendar now." },
    { key: "closing", start: d(y - 1, 10, 31), label: "Closing date", when: `31 October ${y - 1}`, todo: "The big one: submit your application by tonight. Six preferences is the usual number for London secondaries. After this date changes are harder." },
    { key: "offer", start: d(y, 3, 1), label: "National Offer Day", when: `1 March ${y}`, todo: "Offers arrive, usually by email in the evening. You'll get the highest school on your list that can offer your child a place." },
    { key: "accept", start: d(y, 3, 15), label: "Accept or decline", when: `by about 15 March ${y}`, todo: "Accept the offer (check your council's exact date). Accepting doesn't hurt your waiting-list chances at schools you ranked higher." },
    { key: "waiting", start: d(y, 3, 29), label: "Waiting lists move", when: `late March – about 21 July ${y}`, todo: "Places families turn down go to the waiting list in the same priority order. Ask the council for your child's position and check in now and then." },
    { key: "appeals", start: d(y, 3, 30), label: "Appeals", when: `lodge by about 29 March ${y}; hearings usually by June ${y}`, todo: "You can appeal for any school you were refused. Lodging an appeal is free and doesn't affect waiting lists." },
    { key: "start", start: d(y, 9, 1), label: "Starting secondary school", when: `early September ${y}`, todo: "First day. Whatever happened along the way, your child walks in with a fresh start." },
  ];
  const reception = [
    { key: "open", start: d(y - 1, 9, 1), label: "Applications open", when: `around 1 September ${y - 1} (some councils differ)`, todo: "Primary applications open. The number of preferences varies by council, so check yours." },
    { key: "closing", start: d(y, 1, 15), label: "Closing date", when: `15 January ${y}`, todo: "Submit your reception application by tonight. List schools in your true order of preference." },
    { key: "offer", start: d(y, 4, 16), label: "National Offer Day", when: `16 April ${y}`, todo: "Offers arrive. You'll get the highest school on your list that can offer your child a place." },
    { key: "start", start: d(y, 9, 1), label: "Starting reception", when: `early September ${y}`, todo: "First day of school — a big step, and it comes round faster than you think." },
  ];
  // Windows: each step is "current" until the next one starts.
  [secondary, reception].forEach((steps) => {
    steps.forEach((s, i) => { s.end = i + 1 < steps.length ? steps[i + 1].start : null; });
  });
  return { secondary, reception };
}

const fmtDay = (date) => date.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });

/** The step happening now: the one whose window contains `today`, else the next upcoming step. */
function nowIndex(steps, today) {
  const i = steps.findIndex((s) => today >= s.start && (!s.end || today < s.end));
  if (i >= 0) return i;
  return steps.findIndex((s) => s.start > today);
}

/**
 * Render a calm vertical timeline per phase into `root`.
 * `planNote` maps a step key (e.g. "offer") to one short sentence about what the plan means there.
 */
export function renderTimeline(root, { today = new Date(), planNote = {} } = {}) {
  const entryYear = (() => {
    const y = today.getFullYear();
    // Once the secondary closing date (31 Oct) has passed, the next intake is the cycle to show.
    return today > d(y, 10, 31) ? y + 2 : y + 1;
  })();
  const { secondary, reception } = buildTimeline(entryYear);
  const phase = (title, steps) => {
    const now = nowIndex(steps, today);
    return `
      <h4 class="tl-phase">${esc(title)}</h4>
      <ol class="tl">
        ${steps.map((s, i) => `
          <li class="tl-step${i === now ? " tl-now" : ""}${s.end && today >= s.end ? " tl-past" : ""}">
            <span class="tl-dot" aria-hidden="true"></span>
            <div class="tl-body">
              <strong>${esc(s.label)}</strong> <span class="tl-when">${esc(s.when)}</span>
              ${i === now ? `<span class="tl-here">You are here</span>` : ""}
              <p>${esc(s.todo)}${planNote[s.key] ? ` <em>${esc(planNote[s.key])}</em>` : ""}</p>
            </div>
          </li>`).join("")}
      </ol>`;
  };
  root.innerHTML = `
    ${phase(`Secondary entry, September ${entryYear}`, secondary)}
    ${phase(`Reception entry, September ${entryYear}`, reception)}`;
}
