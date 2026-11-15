# AGENTS.md

Notes for coding agents (Codex, Kimi, Claude) working in this repository.

## What lives here

- **Schools in Reach** (www.schoolsinreach.com): school-choice site. Static site in `site/`, data pipelines in
  `pipeline/` (admissions, catchments, Ofsted and so on).
- **School Money** (money.schoolsinreach.com): school finances for parents, governors, PTFA committees and school
  leaders. Generated, never hand-edited:
  - Generator: `pipeline/money/build_money.py` (pages, data files, search index), with the page shell in
    `pipeline/money/site.py`, school pages in `pipeline/money/school_page.py`, area pages in
    `pipeline/money/area_pages.py` and `areas.py`, guides in `pipeline/money/guides.py` (Markdown in
    `pipeline/money/data/guides/`), parents' associations in `pipeline/money/pta.py`.
  - Front-end source: `pipeline/money/assets/` (vanilla JS in an IIFE, no framework, no build step, plus CSS).
    The build copies it to `site_money/assets/`.
  - Output: `site_money/` (about 2.4 GB, 24,800 school pages). It is gitignored. **Never edit files in
    `site_money/`; change the generator or `pipeline/money/assets/` and rebuild.**
  - Inputs: `pipeline/.cache/` (gitignored, about 6.5 GB of DfE, GIAS and Charity Commission data). Read it, never
    write to it.

## Commands

```bash
# Money tests (Python + the node suites run through pipeline/money/test_js.py). About 3 minutes; 765 pass on 15 Nov 2026.
python3 -m pytest -q -p no:cacheprovider pipeline/money tests -k "money or areas or a1_ or a4_ or a5_ or b1_ or b3_ or shell or search"

# One node suite directly
node --test pipeline/money/test_app_js.mjs

# Full build of site_money/ from pipeline/.cache (slow; writes only site_money/)
python3 -m pipeline.money.build_money

# Serve the build locally
python3 -m http.server 8090 --directory site_money
```

`deploy/money/deploy.sh` builds and deploys to production on Railway. **Agents never run it.**

## Rules

- British English, plain words, short sentences. Readers are parents and volunteers, not accountants.
- Honesty rules the tests enforce: figures are a starting point for a conversation, not a verdict; a parents'
  association's income and a school's donations are never added together (they can overlap); suspect pupil counts
  are kept out of every per-pupil figure; a federation lead's PTFA is never divided by the whole federation's pupils.
  Keep these intact.
- Page size budgets are tested (`SCHOOL_PAGE_BUDGET`, `PAGE_BUDGET`, `SX_BUDGET` in `build_money.py`) and the
  global search index `site_money/data/search.json` is already about 4.5 MB: do not grow it much. Put extra data
  in separate files that only the page needing them loads.
- Accessibility: every control keyboard-usable with a visible focus, labelled inputs, ARIA only where native HTML
  cannot do it, works at 360 px wide, respects `prefers-reduced-motion`.
- No new dependencies (Python stdlib plus what is already imported; no npm packages in the front end).
- Tests in AAA style with `# Arrange`, `# Act`, `# Assert` comments, next to the code they test
  (`pipeline/money/test_*.py`, `pipeline/money/test_*.mjs`).
- Conventional Commits. Agents do not commit or push unless told to.

## Final summary must list

Files changed, decisions made, assumptions, the exact test commands run with pass/fail counts, and anything you
could not verify (production, network, a full build).
