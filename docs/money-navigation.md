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

## Sorting schools and fundraising

`/search/` and the finder on `/ptfa/` offer school name, association total income,
income per pupil, change in income in pounds or percent, and pupil count. Search
also offers relevance; the finder offers distance after a valid postcode or
district is entered. Distance uses the existing ten-mile radius from the district
centre, so schools without a location cannot be included in that radius.

The labelled **Direction** control uses **Ascending** and **Descending**, matching
the council table. Changing the sort defaults to ascending for name and distance,
descending otherwise. Missing values stay last in both directions. Search ranks
are highest first for descending relevance and reversed for ascending relevance.
The URL stores `sort` and `dir=asc|desc`, alongside all the existing filters.
An unknown search sort still falls back to relevance. For example:

```text
/search/?q=Hackney&phase=primary&sort=change&dir=desc
/ptfa/?postcode=E8&sort=distance&dir=asc#fundraising-finder
```

Change compares adjacent school years for the same set of charities at the same
school. It uses `series._pta`'s underlying unrounded sums, equal shared-charity
allocation and return deduplication, then rounds pounds and per-pupil changes to
whole pounds and percentages to one decimal place. Earlier income of zero or below has a
cash change but no percentage. Per-pupil change is the difference between the two
years' income per pupil, using each year's own reliable pupil count.

Gaps, changed contributors, missing income, explicitly unusual returns and years
newer than the existing national 60% coverage window get an explanation instead
of a change. The current source has no separate PTA filing flag in `series.py`;
the coverage window is the existing `areas.pta_window` rule. The comparison helper
also honours explicit `unusual`, income `suspect`, and `still_filing` return flags.
The original income figures, school donations and published medians are unchanged.

`fundraising.json` is now version 2. Its original ten row columns are followed by
`change`: either `[pounds, percentage, per_pupil]`, with null for an unavailable
percentage or per-pupil figure, or a reason code from `series.PTA_CHANGE_REASONS`.
The previous year is derived from the row's year, avoiding repeated labels. A
separate `pupils` object in the same file maps school URNs to their latest full
return's reliable own-school count, including schools without associations.
Unreliable latest counts are left out; older counts are not substituted. This
keeps the global `search.json` unchanged. The 1,200,000-byte fundraising ceiling
and 96,000-byte school-page ceiling are unchanged.

The school page's **Change** column uses the same helper for every displayed year.
It names Up, Down or No change in words and stacks across the phone row. Its money
figures have the standard keyboard-accessible explanation.
