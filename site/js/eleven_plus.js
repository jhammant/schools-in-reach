import { esc } from "./util.js";

/**
 * What a family needs to know about entrance tests (the "11+") at grammar and other
 * selective schools. Dates move every year, so this gives the shape of the year and
 * always sends people to their council for the actual deadlines.
 */

// Areas that run one shared test. Timings are the usual pattern, not this year's dates.
const AREA_TESTS = {
  886: { name: "the Kent Test", when: "Registration usually opens in early June and closes in the first week of July, in Year 5. The test is sat in September of Year 6." },
  887: { name: "the Medway Test", when: "Registration usually runs through June, in Year 5, with the test in September of Year 6." },
  825: { name: "the Buckinghamshire Secondary Transfer Test", when: "Children at Buckinghamshire schools are usually entered automatically; everyone else registers by mid-June of Year 5. The test is sat in September of Year 6." },
  881: { name: "the CSSE entrance exam used by Essex grammar schools", when: "Registration usually closes in the summer before Year 6, with the test that autumn." },
  919: { name: "the Hertfordshire consortium test", when: "Registration usually closes in the summer before Year 6, with tests in September." },
  916: { name: "the Gloucestershire grammar schools' test", when: "Registration usually runs in the spring and early summer of Year 5, with the test in September of Year 6." },
  330: { name: "the King Edward VI consortium test", when: "Registration usually closes in June, with the test in September of Year 6." },
  925: { name: "the Lincolnshire grammar schools' test", when: "Registration usually runs in the summer before Year 6, with the test that September." },
  358: { name: "the Trafford consortium test", when: "Registration usually closes in the summer before Year 6, with tests in September." },
};

const GENERIC = {
  name: "an entrance test set by the school or a group of local schools",
  when: "Registration usually happens in the late spring or summer of Year 5, with the test in September or October of Year 6.",
};

/** A callout for a selective school's page. Returns "" for schools that don't test. */
export function elevenPlusNote(school, laName) {
  const area = AREA_TESTS[String(school._la)] || GENERIC;
  return `<div class="callout callout-info">
    <p><strong>This school uses an entrance test (the 11+).</strong> Places go first to children who reach the required standard in ${esc(area.name)}, so how close you live matters less here than it does elsewhere.</p>
    <p>${esc(area.when)} Registering for the test is separate from applying for a school place, and the test deadline usually falls <em>before</em> the application deadline of 31 October. Missing it usually means missing the chance for that year.</p>
    <ul>
      <li>You still list the school on your council application form by 31 October, alongside your other choices.</li>
      <li>Passing does not guarantee a place. Schools that fill up then rank by distance, by catchment, or by test score.</li>
      <li>Ranking a grammar school first never harms your chances at your other choices, so most families list a mix.</li>
      <li>If your child doesn't reach the standard, there is usually a review or appeal route. Your council explains how.</li>
    </ul>
    <p class="note">Dates change every year. Check ${esc(laName || "your council")}'s admissions pages and the school's own website for this year's registration deadline, and see <a href="https://www.gov.uk/apply-for-secondary-school-place" target="_blank" rel="noopener">GOV.UK: apply for a secondary school place</a>.</p>
  </div>`;
}

/** A short line for the list and map tooltips. */
export const elevenPlusPill = "Grammar · entrance test";
