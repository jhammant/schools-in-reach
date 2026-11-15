# School Money navigation

The home page starts with one school search and three routes: look up a school,
explore parents' association fundraising, or compare schools. Videos, England's
figures and audience guides follow below. Other pages retain the header search.
Both search inputs keep their existing IDs and submit to `/search/`.

The main navigation has five links: Find a school, PTFA fundraising, Compare,
Areas and Guides. Map, Trusts, Debts, Videos and Tools remain available under the
native **More** disclosure. On phones, **Menu** opens the navigation; Escape closes
More first, then Menu, returning keyboard focus to the relevant control. Without
JavaScript the navigation remains visible and More still works.

Audience choices live on home. The existing `moneyAudience` local-storage key
and values (`parent`, `governor`, `ptfa`, `leader`, `pupil`) are unchanged. No choice
means no quick-links strip. A saved choice restores the appropriate links on other
pages in one horizontally scrolling strip. **Close** clears the choice, including
the section tags, and returns focus to search (or the home audience picker).

School pages with finance returns start with **At a glance**, linking to status,
spending, reserves and parents' association fundraising. It uses the existing
status and series helpers: suspect figures are not compared, a federation's pupil
count is not used for its lead school's association, and shared or uncertain
charity matches retain their caveats. No association found on the register does
not mean no fundraising. **On this page** stays at the top while scrolling and
scrolls horizontally to keep all section links reachable on a phone.

The implementation is in `site.py`, `build_money.render_home`, the top-of-page
helpers in `school_page.py`, and the `header, home and page top` block in
`assets/app.css`. `assets/app.js` handles the menu and saved choice;
`assets/audience.css` handles section tags. All paths are under `pipeline/money/`.
Generated files in `site_money/` must only change through a build.
