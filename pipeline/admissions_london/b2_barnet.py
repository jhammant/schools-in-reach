"""Barnet (LA 302): parse Barnet Education and Learning Service's "How places
were allocated at Barnet secondary schools" tables (national offer day 2021,
2022, 2024, and a combined 2023-2025 edition) and "How primary school places
were allocated" tables (2021, 2023, 2024, 2025).

barnet.gov.uk answers automated requests with a bot-protection page ("Pardon
Our Interruption"), so every document here is the Internet Archive's copy of
the council's own PDF (web.archive.org "id_" raw snapshot of the same URL).

Secondary: per school, places available and the places offered under each
criterion, with the furthest distance offered (miles) printed against the
distance-based criteria, or "(All offered)". Where a school prints distances
for several criteria (Archer Academy's three priority postcodes, St Mary's and
St John's four open bands, Wren's faith and community places) each becomes a
group. The Henrietta Barnett School, Queen Elizabeth's School (boys) and St
Michael's Catholic Grammar School admit by academic ability ("selective").

Primary: community schools give places, applications, siblings and the
furthest distance offered to children living inside and outside the school's
defined (catchment) area; voluntary-aided, foundation, free schools and
academies give places, applications and the criterion under which the final
place was offered, with its furthest distance where one applies. Schools whose
demand was met are listed (2021/2023/2024 as a sentence under the table, 2025
as "Demand met" rows).

Table cells are read with pdfplumber's table extraction. School names in the
secondary tables are vertically centred over several rows and their text can
spill into a neighbouring cell, so each name is read from the words lying
within its own block of rows. Names are resolved against GIAS by distinctive
tokens, and duplicate-named church schools by the postcode district printed
after the name, e.g. "St John's CE (N11)".
"""

from __future__ import annotations

import re

import b2_common as bc

LA_CODE = "302"
LA_NAME = "Barnet"
MANUAL_ALIASES: dict[str, tuple[str, str]] = {}  # filled in by parse() from GIAS resolution

WB = "https://web.archive.org/web/{ts}id_/https://www.barnet.gov.uk/sites/default/files/{path}"
SECONDARY_DOCS = [
    {"cache": "wb-allocation-table-2021.pdf", "year": 2021,
     "url": WB.format(ts="20211204232532", path="allocation_table_2021.pdf"),
     "title": "Barnet Council: How places were allocated at Barnet Secondary Schools on 1 March 2021"},
    {"cache": "wb-allocation-table-2022.pdf", "year": 2022,
     "url": WB.format(ts="20230126132620", path="Allocation%20Table%202022.pdf"),
     "title": "Barnet Council: How places were allocated at Barnet Secondary Schools on 1 March 2022"},
    {"cache": "wb-allocation-table-2024.pdf", "year": 2024,
     "url": WB.format(ts="20260106095403", path="allocation_table_2024_2.pdf"),
     "title": "Barnet Council: How places were allocated at Barnet Secondary Schools on 1 March 2024"},
    {"cache": "wb-secondary-2023-2025.pdf", "year": None,
     "url": WB.format(ts="20251108181221", path="secondary_transfer_-_how_places_were_allocated_updated_3_18.pdf"),
     "title": "Barnet Council: How places were allocated at Barnet secondary schools, 2023, 2024 and 2025"},
]
PRIMARY_DOCS = [
    {"cache": "wb-primary-2021.pdf", "year": 2021,
     "url": WB.format(ts="20211103022011", path="primary_allocation_table_2021.pdf"),
     "title": "Barnet Council: How primary school places were allocated on 16 April 2021"},
    {"cache": "wb-primary-2023.pdf", "year": 2023,
     "url": WB.format(ts="20240706114200", path="How%20primary%20school%20places%20were%20allocated%20on%2017%20April"
                                                "%202023%20at%20Voluntary%20aided%20schools.pdf"),
     "title": "Barnet Council: How primary school places were allocated on 17 April 2023"},
    {"cache": "wb-primary-2024.pdf", "year": 2024,
     "url": WB.format(ts="20240527140429", path="how_primary_school_places_were_allocated_on_16_april_2024_at_"
                                                "voluntary_aided_schools_0.pdf"),
     "title": "Barnet Council: How primary school places were allocated on 16 April 2024"},
    {"cache": "wb-primary-2025.pdf", "year": 2025,
     "url": WB.format(ts="20251030111841", path="how_primary_school_places_were_allocated_on_16_april_2025_v2_15.pdf"),
     "title": "Barnet Council: How primary school places were allocated on 16 April 2025"},
]
DISTANCE_METHOD = "straight_line"
DISTANCE_NOTES = ("Barnet prints the \"furthest distance offered (miles)\" for each distance-based criterion; the "
                  "primary tables describe it as the \"furthest straight-line distance in miles\".")

# Names garbled in the PDF itself (two text runs printed over each other), fixed by hand after checking the
# criteria rows beneath them (Orthodox Jewish girls' school, 75 places).
GARBLED = {"AHracshmero nAecaand eHmigyh ( TShceh)ool for Girls": ("Hasmonean High School for Girls", 75)}
# Renamed schools not linked by GIAS succession: Whitefield School (URN 101347, NW2 1TR, closed 31-08-2011)
# reopened as an academy at the same postcode, now "Clarion" (URN 137361).
RENAMED = {"whitefield": "137361"}
# Before Menorah Primary School split into boys' and girls' schools (the boys' school opened 01-01-2024 as URN
# 150274 at the same NW11 9SP site), the single school was URN 101341, now "Menorah Primary School for Girls".
RENAMED_EXACT = {bc.alias_key("Menorah Primary Jewish"): "101341"}

YEAR_RE = re.compile(r"allocated at Barnet secondary schools on \d+ \w+ (20\d\d)", re.I)
DIST_RE = re.compile(r"\((\d+(?:\.\d+)?)(?:\s*miles)?\)")


def _clean(cell) -> str:
    return re.sub(r"\s+", " ", (cell or "").replace("\n", " ")).strip()


def _tables(path) -> list[tuple[int, list[str]]]:
    rows = []
    with bc.open_pdf(path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    rows.append((page.page_number, [_clean(c) for c in row]))
    return rows


# --------------------------------------------------------------------------- secondary

def _secondary_blocks(doc: dict, path) -> list[dict]:
    """One block per school. The name is read from the words inside the name column whose vertical centre lies
    within the school's own criterion rows (the name cell text itself can spill into neighbouring rows)."""
    year = doc["year"]
    blocks: list[dict] = []
    with bc.open_pdf(path) as pdf:
        for page in pdf.pages:
            words = bc.pdftools.page_words(page)
            for table in page.find_tables():
                page_blocks: list[dict] = []
                for row, cells in zip(table.rows, table.extract()):
                    cells = [_clean(c) for c in cells]
                    m = YEAR_RE.search(" ".join(cells))
                    if m:
                        year = int(m.group(1))
                        continue
                    if len(cells) < 5 or cells[0].startswith("Name of School"):
                        continue
                    name, pan, crit, offered, dist = cells[:5]
                    if not crit:
                        continue
                    top, bottom = row.bbox[1], row.bbox[3]
                    if name or pan:
                        name_cell = row.cells[0]
                        page_blocks.append({"year": year, "pan": int(pan) if re.fullmatch(r"\d+", pan) else None,
                                            "criteria": [], "top": top, "bottom": bottom, "cell_name": name,
                                            "x0": name_cell[0] if name_cell else table.bbox[0],
                                            "x1": name_cell[2] if name_cell else table.bbox[0] + 100})
                    if not page_blocks:
                        if blocks:  # a continuation row at the top of a page; its school started on the previous page
                            blocks[-1]["criteria"].append({"label": crit, "dist": dist,
                                                           "offered": int(offered) if offered.isdigit() else None})
                        continue
                    blk = page_blocks[-1]
                    blk["bottom"] = bottom
                    blk["criteria"].append({"label": crit, "offered": int(offered) if offered.isdigit() else None,
                                            "dist": dist})
                for blk in page_blocks:
                    inside = sorted((w for w in words if blk["x0"] <= w.cx <= blk["x1"]
                                     and blk["top"] <= w.cy <= blk["bottom"]), key=lambda w: (round(w.top), w.x0))
                    blk["raw_name"] = " ".join(w.text for w in inside) or blk["cell_name"]
                    if blk["cell_name"] in GARBLED:
                        blk["raw_name"], blk["pan"] = GARBLED[blk["cell_name"]]
                blocks.extend(page_blocks)
    return blocks


def _secondary_record(block: dict, school: dict, index: bc.GiasIndex) -> dict:
    crits = block["criteria"]
    dist_rows = [c for c in crits if c["dist"]]
    selective = index.selective(school["urn"]) or any(c["label"].startswith("Academic Ability") for c in crits)
    notes = []
    groups = ["All"] if len(dist_rows) <= 1 else [c["label"] for c in dist_rows]
    max_distance, all_offered = {}, []
    for g, c in zip(groups, dist_rows or [None]):
        if c is None:
            max_distance[g] = None
        elif c["dist"].lower().startswith("(all"):
            max_distance[g] = None
            all_offered.append(g)
        else:
            max_distance[g] = float(c["dist"])
    if len(dist_rows) == 1:
        notes.append(f"Furthest distance is printed against the \"{dist_rows[0]['label']}\" criterion.")
    elif not dist_rows:
        notes.append("No furthest distance is printed for this school in this year.")
    labels = " ".join(c["label"] for c in crits)
    if selective:
        allocation = "selective"
        notes.append("Selective (grammar) school: places are offered by rank in the entrance test (academic "
                     "ability); distance only separates applicants with equal scores, so no distance cut-off "
                     "applies.")
    elif "Priority Postcode" in labels:
        allocation = "catchment_then_distance"
        notes.append("Places are split between priority postcode areas (N2, N3, NW11), each with its own furthest "
                     "distance; applicants compete only within their own postcode group.")
    elif len(groups) > 1 or re.search(r"Random|Band [A-D1-4]", labels):
        allocation = "mixed"
        if re.search(r"Random", labels):
            notes.append("Some places are allocated by random allocation (lottery), not distance.")
        if len(groups) > 1:
            notes.append("Distances are published separately for each band / route of admission, shown as groups.")
    elif school["religion"] not in ("", "None", "Does not apply"):
        allocation = "faith_then_distance"
    else:
        allocation = "distance"
    criteria = [{"label": c["label"], "total": c["offered"]} for c in crits if c["offered"] is not None]
    total = sum(c["total"] for c in criteria) if criteria else None
    return bc.secondary_record(block["raw_name"], block["year"], pan=block["pan"], groups=groups, criteria=criteria,
                               max_distance=max_distance, all_offered=all_offered, total_offers=total,
                               allocation=allocation, notes=notes)


# --------------------------------------------------------------------------- primary

BAND_WORDS = {"Faith", "Open", "Community", "Foundation", "Proximity", "Jewish"}
COMMUNITY_RE = re.compile(r"^(All|None|\d+(?:\.\d+)?)$")


def _demand_met(text: str) -> list[str]:
    m = re.search(r"possible to meet the demand for applicants who applied on time for a place at the following "
                  r"schools:\s*(.+?)(?:\n\s*\n|How places were allocated|$)", text, re.S)
    if not m:
        return []
    return [n.strip() for n in re.sub(r"\s+", " ", m.group(1)).split(",") if n.strip()]


def _primary_rows(path) -> tuple[list[dict], list[dict]]:
    va, community = [], []
    for _, cells in _tables(path):
        vals = [c for c in cells if c]
        if not vals or vals[0].startswith(("Name of School", "How ")):
            continue
        if len(vals) == 6 and all(re.fullmatch(r"\d+", v) for v in vals[1:4]) and COMMUNITY_RE.match(vals[4]) \
                and COMMUNITY_RE.match(vals[5]):
            community.append({"name": vals[0], "pan": int(vals[1]), "apps": int(vals[2]), "siblings": int(vals[3]),
                              "inside": vals[4], "outside": vals[5]})
            continue
        if len(vals) >= 3 and re.fullmatch(r"\d+", vals[1]) and re.fullmatch(r"\d+", vals[2]):
            rest = vals[3:]
            band = rest.pop(0) if len(rest) > 1 and rest[0] in BAND_WORDS else None
            va.append({"name": vals[0], "pan": int(vals[1]), "apps": int(vals[2]),
                       "lines": [(band, " ".join(rest))] if rest else []})
            continue
        if va and not cells[0] and len(vals) <= 2:
            band = vals[0] if len(vals) == 2 and vals[0] in BAND_WORDS else None
            va[-1]["lines"].append((band, vals[-1]))
    return va, community


def _community_record(year: int, row: dict) -> dict:
    inside, outside = row["inside"], row["outside"]
    notes = ["Community school with a defined (catchment) area: after looked-after children, EHCPs, exceptional "
             "need and siblings, children living in the defined area are offered places before children living "
             "outside it, each by straight-line distance."]
    all_offered, max_distance = False, None
    if inside == "All" and outside == "All":
        all_offered = True
        notes.append("All applicants inside and outside the defined area were offered a place.")
    elif inside == "All":
        max_distance = float(outside) if outside != "None" else None
        notes.append(f"Every child living in the defined area was offered a place; children outside it were "
                     f"offered up to {outside} miles.")
    else:
        max_distance = float(inside) if inside != "None" else None
        notes.append(f"Not every child living in the defined area was offered a place: offers reached {inside} "
                     f"miles within the area, and {'none' if outside == 'None' else outside} outside it.")
    return bc.primary_record(row["name"], year, pan=row["pan"], applications=row["apps"],
                             criteria=[{"label": "Siblings", "total": row["siblings"]}], max_distance=max_distance,
                             all_offered=all_offered, allocation="catchment_then_distance", notes=notes)


def _va_record(year: int, row: dict, school: dict | None) -> dict:
    lines = row["lines"]
    text = " | ".join(f"{b}: {c}" if b else c for b, c in lines)
    notes = [f"Criterion under which the final place was offered, as published: \"{text}\"."]
    demand_met = any(c.lower().startswith("demand met") for _, c in lines)
    chosen = None
    with_dist = [(b, c) for b, c in lines if DIST_RE.search(c)]
    if len(with_dist) == 1:
        chosen = with_dist[0]
    elif with_dist:
        open_route = [(b, c) for b, c in with_dist if (b or "") in ("Open", "Community", "Proximity")
                      or c.startswith("Community Band")]
        chosen = open_route[-1] if open_route else with_dist[-1]
        notes.append("Several routes of admission are printed; the distance recorded is the one for the "
                     f"{'open/community' if open_route else 'last listed'} route.")
    max_distance = float(DIST_RE.findall(chosen[1])[-1]) if chosen else None
    lottery = any(re.search(r"lottery", c, re.I) for _, c in lines)
    religion = (school or {}).get("religion", "")
    if lottery and chosen is None:
        allocation = "mixed"
        notes.append("The final places were allocated by lottery, so no distance cut-off applies.")
    elif religion not in ("", "None", "Does not apply"):
        allocation = "faith_then_distance"
    else:
        allocation = "distance"
    return bc.primary_record(row["name"], year, pan=row["pan"], applications=row["apps"], max_distance=max_distance,
                             all_offered=demand_met, allocation=allocation, notes=notes)


# --------------------------------------------------------------------------- resolution

def _resolve(index: bc.GiasIndex, raw: str, phase: str, previous: str | None, log: list[str],
             seen: set[str] | None = None) -> dict | None:
    key = bc.alias_key(raw)
    if key in RENAMED_EXACT:
        return index.by_urn[RENAMED_EXACT[key]]
    for token, urn in RENAMED.items():
        if token in key.split():
            return index.by_urn[urn]
    exclude = {previous} if previous else set()
    school = index.resolve(raw, phase, exclude=exclude)
    if school is None and " / " in raw:
        for part in reversed(raw.split(" / ")):
            school = index.resolve(part, phase, exclude=exclude, min_overlap=1)
            if school:
                break
    if school is None and seen is not None:
        # a name cell holding two schools' names (text spilling across a page break): take the one school named
        # in full that has not already appeared in this year's table
        toks = bc._gias.tokens(raw)
        weak = {"high", "primary", "college", "catholic", "ce", "church", "st"}
        named = [r for r in index.rows if r["phase"] in bc._PHASES[phase] and r["urn"] not in seen
                 and (r["toks"] - weak) and (r["toks"] - weak) <= toks]
        school = named[0] if len(named) == 1 else None
    if school is None:
        log.append(f"barnet {phase}: could not resolve {raw!r}")
    return school


def _register(rec: dict, school: dict, log: list[str]) -> None:
    # alias_key strips phase-generic words ("Academy", "Primary", "School"), so a secondary and a primary
    # school that otherwise share a name (e.g. Ashmole Academy / Ashmole Primary School) can collide here;
    # plain GIAS token matching (phase-filtered) already resolves those correctly without an alias, so on a
    # cross-phase collision this just skips registering rather than treating it as an error.
    key = bc.alias_key(rec["name"])
    known = MANUAL_ALIASES.get(key)
    if known and known[0] != school["urn"]:
        log.append(f"barnet: name {rec['name']!r} resolves to two schools ({known[0]}, {school['urn']}); "
                   "not registering an alias for it, relying on phase-filtered GIAS matching instead.")
        return
    MANUAL_ALIASES[key] = (school["urn"], f"resolved against GIAS: {school['name']}")


def parse_secondary(paths: dict[str, "Path"], log: list[str]) -> list[dict]:  # noqa: F821
    index = bc.GiasIndex(LA_CODE)
    out: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for doc in SECONDARY_DOCS:
        previous = None
        for block in _secondary_blocks(doc, paths[doc["cache"]]):
            seen_year = {u for u, y in seen if y == block["year"]}
            school = _resolve(index, block["raw_name"], "secondary", previous, [], seen_year)
            if school is None and any(c["label"].startswith("Academic Ability") for c in block["criteria"]):
                # e.g. "Queen Elizabeth's" whose "Boys'" line fell outside its rows: only one selective match
                school = index.resolve(block["raw_name"], "secondary", policy="Selective")
            if school is None:
                log.append(f"barnet secondary: could not resolve {block['raw_name']!r}")
            if school is None:
                previous = None
                out.append(_secondary_record(block, {"urn": "", "religion": ""}, index))
                continue
            previous = school["urn"]
            if (school["urn"], block["year"]) in seen:
                continue  # 2024 appears in both the 2024 table and the 2023-2025 edition; keep the first
            seen.add((school["urn"], block["year"]))
            block["raw_name"] = school["name"]
            rec = _secondary_record(block, school, index)
            _register(rec, school, log)
            out.append(rec)
    return out


def parse_primary(paths: dict[str, "Path"], log: list[str]) -> list[dict]:  # noqa: F821
    index = bc.GiasIndex(LA_CODE)
    out: list[dict] = []
    for doc in PRIMARY_DOCS:
        year, path = doc["year"], paths[doc["cache"]]
        va, community = _primary_rows(path)
        if len(community) < 30:
            raise SystemExit(f"barnet primary {year}: only {len(community)} community rows")
        named = set()
        for row in community:
            school = _resolve(index, row["name"], "primary", None, log)
            rec = _community_record(year, row)
            if school:
                rec["name"] = school["name"]
                _register(rec, school, log)
                named.add(school["urn"])
            out.append(rec)
        for row in va:
            school = _resolve(index, row["name"], "primary", None, log)
            rec = _va_record(year, row, school)
            if school:
                rec["name"] = school["name"]
                _register(rec, school, log)
                named.add(school["urn"])
            out.append(rec)
        for name in _demand_met(bc.text_of(path)):
            school = _resolve(index, name, "primary", None, log)
            if school and school["urn"] in named:
                continue
            rec = bc.primary_record(school["name"] if school else name, year, all_offered=True,
                                    allocation="faith_then_distance" if school and school["religion"] not in
                                    ("", "None", "Does not apply") else "distance",
                                    notes=["Listed by Barnet as a school where \"it was possible to meet the demand "
                                           "for applicants who applied on time\"."])
            if school:
                _register(rec, school, log)
            out.append(rec)
    return out
