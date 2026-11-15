# Finding schools and parents’ associations

Search suggestions and `/search/` recognise phase-and-place queries such as
`primary schools in Hackney` and `secondary schools near E8`. A school name can
still be combined with its town or council. Fundraising terms such as `PTFA` and
`friends of` link to `/ptfa/#fundraising-finder`. Unmatched queries offer area
links, similar names elsewhere and council browsing.

The results page keeps `q`, `phase`, `status`, `pta` and `sort` in its URL. For
example, `/search/?q=hackney&phase=primary&pta=1&sort=pp` finds primary schools
with a registered association. `status=unknown` selects schools without a money
status. Sort values are `relevance`, `pp` and `total`. Filters run before the
50-result page limit; Show more results reveals the rest. A recognised URN
still opens its school directly when no filters are set.

The fundraising finder keeps `region`, `council` (council code), `phase`, `band`,
`postcode` and `sort` (`total` or `pp`) in its URL. It shows up to 25 results.
Postcode filtering means within 10 miles of the district centre from the
existing postcode files; it does not contact an external geocoder. School
pages link to this finder with their council selected. Static top lists and
council browsing remain available without JavaScript.

`search.json` gains only `ph`, a one-digit phase code (seven bytes per school).
The code order is defined by `fundraising.PHASES` and mirrored in `app.js`.
Fundraising figures load separately from `/data/fundraising.json` when a search
runs or the finder opens. Names and school links are joined from the search
index by URN. The compact file's `columns` describe its array rows; council
names, regions and medians are stored once. Its build budget is 1,200,000 bytes.
A failed load can be retried; ordinary school search and static browsing remain
available.

The new file includes currently registered associations, excluding matches
held for review. Latest income and per-pupil figures use the existing
`areas.school_years` and `areas.pta_record` rules. Shared charities retain the
equal split; lower-confidence matches are labelled. Missing or suspect pupil
counts, federation totals and a missing finance return for the charity's year
never become per-pupil figures. Zero income remains zero. No school donations
are added to association income.

England and council medians are the existing published figures for the latest
well-covered national year. They are labelled with that year and do not change
with filters. Results show each association's latest available year, which can
be different. Nearby school lists use up to eight same-phase schools with a
registered association within 30 miles, independently of the existing general
nearby comparison list. Missing locations are excluded. This list is rendered
in the school page, including when the school has no association itself.
