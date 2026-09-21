# Schools in Reach — state as of 20 September 2026

## What this is
A free, ad-supported school-choice site for the UK: schools near a postcode, an estimate of
your chances from published admissions figures, Ofsted/results/neighbourhood data, a
step-by-step guide and a plan you can rank. Live at **www.schoolsinreach.com** (Railway),
open source at **github.com/jhammant/schools-in-reach**, tiles on S3/CloudFront at
tiles.schoolsinreach.com. Started as personal research into a Hackney secondary place.

## Where it stands
**Live and working**
- All four UK nations: England (~23,600 schools, 153 councils), Wales (1,543 / 22),
  Scotland (2,427 / 32), Northern Ireland (1,098 / 11). Council boundaries for all 218.
- Admissions cut-offs for 24 London boroughs + Greenwich refreshed today (see below).
- Chance heat map, cut-off rings (now only the schools that reach you), Help me guide,
  My plan, shortlist, FAQ page (29 questions), How-to-apply walkthrough.
- 11+ handling: grammar schools flagged, a filter, and a local-test explainer (Kent Test,
  Bucks STT, CSSE, Herts, Gloucestershire, Lincolnshire, Trafford, King Edward VI).
- Cross-council note on school pages: "run by Islington, you live in Hackney" plus the
  eAdmissions Local Authority dropdown tip. This was the most-asked question.
- Analytics live (PostHog, cookieless), dashboard at
  eu.posthog.com/project/168391/dashboard/962460, every event tagged `site=schoolsinreach`.
- AdSense: site added to pub-5764635530350909, verified by meta tag, **review requested**,
  ads.txt live. Ad code stays off until approval (`site/js/config.js` client is empty).

**Greenwich fix (today, from a LinkedIn bug report)**
Royal Greenwich rebuilt their site and moved both booklets from PDFs (now HTTP 500) into a
PageSuite reader. `pipeline/admissions_london/greenwich_booklet_pages.mjs` +
`b3_greenwich_booklet.py` read the reader's page list in a headless browser, download each
page PDF from pages.pagesuite.com and parse the tables. Primary now has entry 2026 for 57
schools; secondary entry 2026 for 12 of 14, bands included.

**Known gaps**
- Greenwich: 6 primary pages the council hasn't refreshed keep older figures; St Mary
  Magdalene and St Paul's have blank cells in the booklet.
- London batch 4 never done: Croydon, Bromley, Bexley, Sutton, Hounslow, Barking &
  Dagenham, Havering, Redbridge have no cut-off data.
- No admissions figures anywhere outside London (Kent etc. publish them; not parsed).
- NI can't have chance estimates — post-primary is not distance-based and SEAG publishes
  no cut-off scores. Scotland/Wales use catchment areas, not distances.
- Chance model treats all bands equally and uses one waiting-list freeing rate for every
  band; partly selective schools aren't modelled as two queues.
- Heat map and "space for everyone" ignore a school's single-sex status.

**Crawlable pages, estate-agent widget and billing (21 Sep 2026)**
- SEO: `pipeline/seo/build_pages.py` writes static pages for 30,227 schools and 218
  councils plus a sitemap index (23,385 indexable; Scotland/Wales/NI noindexed until
  they have a second data source). `deploy.sh` regenerates them and refuses to ship
  without them. Search Console domain property verified by a Route53 apex TXT record
  (don't delete it); sitemap submitted.
- Widget: `widget.js` + `/embed/` (full tier for agents in `site/agents.json` whose
  site matches the referrer, 3-school preview otherwise). `/agents/` sells it at £29 (founding code FOUNDING: £19 for 12 months, first 20)
  per branch per month after a 30-day trial via Stripe Payment Link
  https://buy.stripe.com/00w7sN8Of3e3dnfgS6bQY01 (Hammant Labs account). Customers
  manage or cancel at https://billing.stripe.com/p/login/6oU28t3tVdSH4QJgS6bQY00.
- Onboarding an agent is manual: when Stripe emails a new trial, add
  `{id, name, domains, status: "trial"}` to `site/agents.json`, deploy, and email
  them the snippet with their id.
- Follow-up: first widget render makes ~88 small requests (~3 s); a compact
  per-council widget bundle would cut that to a handful.

## Next steps
1. **Scotland catchments.** A national dataset exists (Improvement Service, Spatial Hub:
   data.spatialhub.scot/dataset/school_catchments-is) — real legal boundaries, all councils,
   GeoJSON/WFS. Needs a free account, which is why it stopped. Reminder set for Jon
   (Hermes job `2ce1480553ad`, Saturday 09:00). Once he has the AuthKey, wire it in.
2. **Kent and the other 11+ counties' allocation data** — routed earlier as batch:extract
   (router chose local-batch; my recommendation was DeepSeek with me writing the parser
   contract, or do Kent by hand first as the reference). Jon hasn't chosen.
3. **London batch 4** (8 boroughs), same shape as batches 1–3.
4. Watch for other councils moving to PageSuite; `b3_greenwich_booklet.py` generalises.

## Open questions (Jon's to decide)
- Which pool parses the non-London admissions PDFs (local-batch / DeepSeek / by hand).
- Whether to pay for a dedicated PostHog project: the RecOS org is at its plan's project
  limit, so Schools in Reach data currently shares "Default project" with another product.
- Whether the old loom host (schoolsinreach.hammantlabs.com) should redirect to the domain.
  It currently serves the same build, and drifted once already.
- AdSense payments account shows an "Action required" banner; may block approval.

## Ideas worth keeping
- **Show good news as a colour, not an absence.** The heat map left areas blank where
  nearby schools admit everyone, which read as "no chance". Painting "a school with space
  for everyone is nearby" in its own colour turned a scary gap into the best news on the map.
- **Answer the question where it's asked.** The cross-council note lives on the school page
  a family is looking at, not only in an FAQ, and names both councils and the exact dropdown.
- **Label the data's vintage from the document, then sanity-check it.** Greenwich's primary
  tables are headed "for entry 2027" in a booklet whose own offer day is April 2027, so the
  figures must be the 2026 round. The secondary booklet confirmed the convention.
- **Deploy tooling must not silently skip content.** `railway up` honours .gitignore, so
  ignoring generated data shipped an empty site three times while reporting "not live yet".
  Any deploy that can't find its payload should fail loudly.

---
_Updated by `forkcode close` on 2026-09-20T21:48+01:00_
