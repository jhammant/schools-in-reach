"""Newham (LA 316): parse the "Outcomes for On-Time Applicants" table inside
Newham's published Reception and Year 7 application/offer-statistics PDFs
(pdftotext -layout). This table gives, per school, the criterion under which
the last (final) offer was made, the distance of that final offer, and the
tie-break method used for that school ("Shortest Walking Distance in Miles",
"Straight Line Distance in Miles", or (one school) "...in Kilometres").

The column set of numeric admission-criteria counts between the school name
and this tail varies between years and between phases (Newham's own template
changed over time), so those per-criterion counts are not parsed here -- only
the school name, the distance-of-final-offer, its criterion, and the
tie-break method, which is this borough's equivalent of a "last distance
offered". PAN/applications/total-offers are published in separate tables
elsewhere in the same PDFs but are not reliably machine-parseable across all
years within the time available, so are left null (recorded in notes).
The 2026 Year 7 ("Primary to Secondary Transition") document only publishes
the preference/offer tables, not yet the outcomes-with-distance table used in
2023-2025 (that table for 2026 was marked "coming soon" on the council's
statistics page at the time of writing).
"""

from __future__ import annotations

import re

import common

LA_CODE = "316"
LA_NAME = "Newham"
# Newham's PDFs print possessive school names without the apostrophe (e.g. "St Antonys" for "St Antony's"),
# which the shared GIAS tokeniser's `'s` normalisation doesn't catch since there is no apostrophe to strip.
MANUAL_ALIASES: dict[str, tuple[str, str]] = {
    "antonys catholic st": ("148025", "possessive apostrophe dropped in source: St Antony's"),
    "catholic edwards st": ("147335", "possessive apostrophe dropped in source: St Edward's"),
    "catholic helens st": ("141925", "possessive apostrophe dropped in source: St Helen's"),
    "catholic joachims st": ("141927", "possessive apostrophe dropped in source: St Joachim's"),
    "lukes st": ("102766", "possessive apostrophe dropped in source: St Luke's"),
    "catholic michaels st": ("150664", "possessive apostrophe dropped in source: St Michael's"),
    "st stephens": ("102748", "possessive apostrophe dropped in source: St Stephen's (primary, not the "
                    "separate St Stephen's Nursery School)"),
    "catholic st winefrides": ("148972", "possessive apostrophe dropped in source: St Winefride's"),
    "angelas st ursuline": ("102786", "possessive apostrophe dropped in source: St Angela's"),
    "bonaventures catholic st": ("102787", "possessive apostrophe dropped in source: St Bonaventure's"),
}

SECONDARY_DOCS = {
    2023: {"cache": "secondary-2023.pdf",
          "url": "https://www.newham.gov.uk/downloads/file/5805/web-6-7-application-and-offer-figures"},
    2024: {"cache": "secondary-2024.pdf",
          "url": "https://www.newham.gov.uk/downloads/file/8036/"
                 "primary-to-secondary-school-transition-september-2024"},
    2025: {"cache": "secondary-2025.pdf",
          "url": "https://www.newham.gov.uk/downloads/file/9034/primary-to-secondary-figures-for-web"},
}
PRIMARY_DOCS = {
    2023: {"cache": "reception-2023.pdf", "url": "https://www.newham.gov.uk/downloads/file/6042/"
                                                  "reception-class-september-2023"},
    2024: {"cache": "reception-2024.pdf",
          "url": "https://www.newham.gov.uk/downloads/file/8037/reception-2024-application-offer-statistics-pdf"},
    2025: {"cache": "reception-2025.pdf", "url": "https://www.newham.gov.uk/downloads/file/9035/"
                                                  "reception-figures-for-web"},
    2026: {"cache": "reception-2026.pdf", "url": "https://www.newham.gov.uk/downloads/file/10890/"
                                                  "reception-application-and-offer-statistics-for-web"},
}
DISTANCE_METHOD = "mixed"
DISTANCE_NOTES = ('Published per-school in the "Tie-break Procedure" column: most schools use "Shortest Walking '
                  'Distance in Miles", a few use "Straight Line Distance in Miles", and Harris Science Academy '
                  'East London is published in "Straight Line Distance in Kilometres" (converted to miles here).')

METHOD_RE = r"(?:Shortest Walking|Straight Line) Distance in (?:Miles|Kilometres)"
TAIL_RE = re.compile(
    # crit is a short published label (e.g. "N/A", "All Other", "FAITH PG 8", "Voluntary Aided - 9"); its length
    # is capped so a non-greedy `head` can't be short-circuited by crit swallowing the rest of the row
    # (including the school name) when the row happens to also satisfy dist+method after a shorter head.
    rf"^(?P<head>.*?)\s+(?P<crit>N/A|All Other|Foundation|Feeder|[A-Z][A-Za-z0-9][A-Za-z0-9 \-]{{0,18}})\s+"
    rf"(?P<dist>N/A|TBC|[\d.]+)\s+(?:Tie-break:\s*)?(?P<method>{METHOD_RE})\s*$")
NAME_RE = re.compile(r"^\s*(?:\d{3,5}\s+\d{5,6}\s+)?([A-Z][A-Za-z0-9'&,.\- ]*?)\s{2,}")


SPARSE_NOTE = ("Detailed admission-criteria counts (EHCP, sibling, etc.) are published for this school and year "
              "but are not parsed here; PAN and total applications are published in a separate table in the "
              "same document and are also not parsed here. Only the distance and criterion of the final offer, "
              "and the tie-break method, are recorded.")


def _rows(text: str, skipped: list[str]) -> list[dict]:
    lines = re.findall(rf"^.*{METHOD_RE}.*$", text, re.M)
    out = []
    for line in lines:
        if re.match(rf"^\s*Tie-break:\s*{METHOD_RE}\s*$", line):
            continue  # a wrapped tie-break label whose row data was captured on the previous line
        m = TAIL_RE.match(line)
        if not m:
            # A small number of rows wrap across a page/column break in a way that loses the leading numeric
            # columns; rather than lose the whole document, these are skipped and reported.
            skipped.append(line.strip())
            continue
        head, crit, dist, method = m.group("head"), m.group("crit"), m.group("dist"), m.group("method")
        nm = NAME_RE.match(head)
        name = nm.group(1).strip() if nm else head.strip()
        if not name or name in ("Tie-break",):
            continue  # a continuation line ("Tie-break: ...") for a row whose data was on the previous line
        unit = "km" if "Kilometres" in method else "miles"
        max_distance = None if dist in ("N/A", "TBC") else common.miles(float(dist), from_unit=unit)
        notes = [SPARSE_NOTE, f"Tie-break method for this school: \"{method}\"."]
        if dist == "TBC":
            notes.append("Distance of final offer published as \"TBC\" (to be confirmed) for this school.")
        if unit == "km":
            notes.append(f"Published in kilometres ({dist} km); converted to miles here.")
        if crit == "N/A":
            notes.append("No offers were made under the distance criterion (places filled by higher criteria, "
                         "or the school had spare capacity).")
        else:
            notes.append(f"Distance criterion of final offer: {crit}.")
        all_offered = dist == "N/A" and crit == "N/A"
        out.append({"name": name, "max_distance": max_distance, "all_offered": all_offered, "notes": notes})
    return out


SITE_SUFFIX_RE = re.compile(r"\s+-\s+.+ Site$", re.I)


def parse(phase: str, paths: dict[int, "Path"], skipped: list[str] | None = None) -> list[dict]:  # noqa: F821
    if skipped is None:
        skipped = []
    out = []
    seen: dict[tuple[str, int], dict] = {}
    for year, path in paths.items():
        text = common.pdftotext(path)
        for row in _rows(text, skipped):
            # A school with more than one admission site (e.g. "Upton Cross Primary School - Kirton Road
            # Site") is published as a separate row per site, but GIAS has only one URN for the school; merge
            # onto the base name, keeping the first site's figures and noting the other site's separately.
            site_m = SITE_SUFFIX_RE.search(row["name"])
            base_name = SITE_SUFFIX_RE.sub("", row["name"]) if site_m else row["name"]
            key = (base_name, year)
            if phase == "secondary":
                rec = {"name": base_name, "year": year, "pan": None, "applications": None, "groups": ["All"],
                      "criteria": [], "max_distance": {"All": row["max_distance"]},
                      "all_offered": ["All"] if row["all_offered"] else [], "non_preference_offers": None,
                      "total_offers": None, "allocation": "distance", "notes": list(row["notes"])}
            else:
                rec = {"name": base_name, "year": year, "pan": None, "applications": None, "total_offers": None,
                      "criteria": [], "max_distance": row["max_distance"], "all_offered": row["all_offered"],
                      "non_preference_offers": None, "allocation": "distance", "notes": list(row["notes"])}
            if key in seen:
                dist_txt = f"{row['max_distance']} miles" if row["max_distance"] is not None else "n/a"
                seen[key]["notes"].append(
                    f"This school has more than one admission site; \"{row['name']}\" is published as a "
                    f"separate row with its own figures (distance of final offer: {dist_txt}), not reproduced "
                    "in full here.")
                continue
            seen[key] = rec
            out.append(rec)
    return out
