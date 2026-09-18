"""characteristics.json: pupil characteristics and class sizes for every English
school, split into one file per local authority.

Source: Explore Education Statistics, "Schools, pupils and their
characteristics" latest release - the two school-level supporting files
("School level underlying data" and "School level underlying data - class
sizes"), January school census, OGL v3.0. Both files already cover all of
England and carry the school's LA directly (old_la_code), the same DfE LA
code scheme as GIAS.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from util import CACHE, OGL, fetch, is_english_la_code, log, read_csv, to_float, to_int

PUBLICATION = "school-pupils-and-their-characteristics"
EES_SITE = "https://explore-education-statistics.service.gov.uk"
EES_CONTENT = "https://content.explore-education-statistics.service.gov.uk/api"

ETHNIC_FINE = [
    # (key, source label fragment, major group)
    ("white_british", "white British", "white_british"),
    ("white_irish", "Irish", "white_other"),
    ("traveller_of_irish_heritage", "traveller of Irish heritage", "white_other"),
    ("gypsy_roma", "Gypsy/Roma", "white_other"),
    ("any_other_white", "any other white background", "white_other"),
    ("mixed_white_black_caribbean", "white and black Caribbean", "mixed"),
    ("mixed_white_black_african", "white and black African", "mixed"),
    ("mixed_white_asian", "white and Asian", "mixed"),
    ("any_other_mixed", "any other mixed background", "mixed"),
    ("indian", "Indian", "asian"),
    ("pakistani", "Pakistani", "asian"),
    ("bangladeshi", "Bangladeshi", "asian"),
    ("any_other_asian", "any other Asian background", "asian"),
    ("black_caribbean", "Caribbean", "black"),
    ("black_african", "African", "black"),
    ("any_other_black", "any other black background", "black"),
    ("chinese", "Chinese", "chinese"),
    ("any_other_ethnic_group", "any other ethnic group", "other"),
]
MAJOR = ["white_british", "white_other", "mixed", "asian", "black", "chinese", "other", "unclassified"]

STAGES = {
    "early_years_e1_e2": "Number of early year pupils (years E1 and E2)",
    "nursery_n1_n2": "Number of nursery pupils (years N1 and N2)",
    "reception": "Number of reception pupils (year R)",
    "ks1": "Number of key stage 1 pupils (years 1 and 2)",
    "ks2": "Number of key stage 2 pupils (years 3 to 6)",
    "ks3": "Number of key stage 3 pupils (years 7 to 9)",
    "ks4": "Number of key stage 4 pupils (years 10 and 11)",
    "ks5": "Number of key stage 5 pupils (years 12 to 14)",
}


def next_data(url: str, name: str, refresh: bool) -> dict:
    page = fetch(url, CACHE / "ees" / f"{PUBLICATION}_{name}.html", refresh).read_text(encoding="utf-8")
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page, re.S)
    if not m:
        raise RuntimeError(f"EES page data not found: {url}")
    return json.loads(m.group(1))["props"]["pageProps"]


def release_files(refresh: bool = False) -> dict:
    """Latest release meta + the school-level supporting files (from the EES page data)."""
    landing = next_data(f"{EES_SITE}/find-statistics/{PUBLICATION}", "landing", refresh)
    slug = landing["publicationSummary"]["latestRelease"]["slug"]
    props = next_data(f"{EES_SITE}/find-statistics/{PUBLICATION}/{slug}/explore", f"{slug}_explore", refresh)
    rel = props["releaseVersionSummary"]
    dc = props["dataContent"]
    files = {f["filename"]: f for f in dc.get("supportingFiles", [])}
    main = next(f for n, f in files.items() if re.match(r"spc_school_level_underlying_data_\d{4}\.csv$", n))
    cls = next(f for n, f in files.items() if re.match(r"spc_school_level_class_size_underlying_data_\d{4}\.csv$", n))
    return {
        "release_title": rel["title"], "release_slug": rel["slug"], "published": rel["published"][:10],
        "release_version_id": dc["releaseVersionId"], "main": main, "class_size": cls,
        "release_url": f"{EES_SITE}/find-statistics/{PUBLICATION}/{rel['slug']}",
    }


def download_file(meta: dict, f: dict, refresh: bool) -> Path:
    url = f"{EES_CONTENT}/releases/{meta['release_version_id']}/files/{f['fileId']}"
    return fetch(url, CACHE / f["filename"], refresh)


def pct(n: int | None, d: int | None) -> float | None:
    if n is None or not d:
        return None
    return round(100 * n / d, 1)


def nz(v: float | int | None):
    """Class-size figures are 0 when a school has no such classes: treat as not applicable."""
    return None if not v else v


def build_all(refresh: bool = False) -> dict[str, dict]:
    """Build characteristics.json content for every English LA. Returns {la_code: data}."""
    log("characteristics.json: school census characteristics + class sizes (all England)")
    meta = release_files(refresh)
    main_rows = read_csv(download_file(meta, meta["main"], refresh))
    cls_rows = read_csv(download_file(meta, meta["class_size"], refresh))

    classes = {r["urn"]: r for r in cls_rows}
    period = None
    schools_by_la: dict[str, dict[str, dict]] = defaultdict(dict)
    unassigned = 0
    for r in main_rows:
        la_code = r.get("old_la_code") or r.get("old_LA_code")
        if not is_english_la_code(la_code):
            unassigned += 1
            continue
        urn = r["urn"]
        tp = r.get("time_period", "")
        period = period or (f"{tp[:4]}/{tp[4:]}" if len(tp) == 6 else tp)
        headcount = to_int(r.get("headcount of pupils"))
        female = to_int(r.get("headcount total female"))
        male = to_int(r.get("headcount total male"))
        eth_base = headcount  # DfE ethnicity counts cover all pupils on roll (checked: % = count / headcount)

        fine, fine_n, major_n = {}, {}, {k: None for k in MAJOR}
        for key, label, group in ETHNIC_FINE:
            n = to_int(r.get(f"number of pupils classified as {label} ethnic origin"))
            fine[key] = to_float(r.get(f"% of pupils classified as {label} ethnic origin"), 1)
            fine_n[key] = n
            if n is not None:
                major_n[group] = (major_n[group] or 0) + n
        unclassified_n = to_int(r.get("number of pupils unclassified"))
        major_n["unclassified"] = unclassified_n
        fine["unclassified"] = to_float(r.get("% of pupils unclassified"), 1)
        has_eth = any(v is not None for v in fine_n.values())
        ethnicity = {k: pct(v, eth_base) for k, v in major_n.items()} if has_eth else None

        c = classes.get(urn, {})
        avg_all = nz(to_float(c.get("average size of one teacher classes"), 1))
        class_sizes = {
            "average_all_classes": avg_all,
            "average_infant_reception_ks1": nz(to_float(c.get("average size of key stage 1 classes taught by one teacher"), 1)),
            "average_ks2": nz(to_float(c.get("average size of key stage 2 classes taught by one teacher"), 1)),
            "classes": nz(to_int(c.get("total number of classes taught by one teacher"))),
            "pupils_in_classes": nz(to_int(c.get("total number of pupils in classes taught by one teacher"))),
            "classes_31_35": to_int(c.get("number of classes of size 31-35 taught by one teacher")) if avg_all else None,
            "classes_36_plus": to_int(c.get("number of classes of size 36+ taught by one teacher")) if avg_all else None,
        } if c else None

        schools_by_la[la_code][urn] = {
            "name": r.get("school_name"),
            "phase": r.get("phase_type_grouping"),
            "establishment_type": r.get("typeofestablishment_name"),
            "sex_of_school": r.get("sex_of_school_description"),
            "headcount": headcount,
            "fte": to_float(r.get("fte pupils"), 1),
            "sex": {"female": female, "male": male, "female_pct": pct(female, headcount), "male_pct": pct(male, headcount)},
            "pupils_by_stage": {k: to_int(r.get(col)) for k, col in STAGES.items() if to_int(r.get(col))},
            "fsm": {
                "eligible": to_int(r.get("number of pupils known to be eligible for free school meals")),
                "eligible_pct": to_float(r.get("% of pupils known to be eligible for free school meals"), 1),
            },
            "language": {
                "eal": to_int(r.get("number of pupils whose first language is known or believed to be other than English")),
                "eal_pct": to_float(r.get("% of pupils whose first language is known or believed to be other than English"), 1),
                "english_pct": to_float(r.get("% of pupils whose first language is known or believed to be English"), 1),
                "unclassified_pct": to_float(r.get("% of pupils whose first language is unclassified"), 1),
            },
            "ethnicity_base": eth_base if has_eth else None,
            "ethnicity_pct": ethnicity,
            "ethnicity_detail_pct": fine if has_eth else None,
            "young_carers_pct": to_float(r.get("% of pupils who are a young carer"), 1),
            "class_sizes": class_sizes,
        }

    if unassigned:
        log(f"  {unassigned} census rows could not be matched to an English LA (skipped)")

    sources = [
        {"title": f"Schools, pupils and their characteristics: {meta['release_title']} - "
                  f"{meta['main']['title']} ({meta['main']['filename']})",
         "url": meta["release_url"], "licence": OGL},
        {"title": f"Schools, pupils and their characteristics: {meta['release_title']} - "
                  f"{meta['class_size']['title']} ({meta['class_size']['filename']})",
         "url": meta["release_url"], "licence": OGL},
    ]
    census = "January school census" + (f" {period[:2]}{period[-2:]}" if period and len(period) == 7 else "")
    notes = [
        "Keyed by URN. Figures are from the January school census for the academic year in time_period.",
        "ethnicity_pct groups: white_british; white_other = Irish, Traveller of Irish heritage, Gypsy/Roma and any "
        "other White background; mixed; asian = Indian, Pakistani, Bangladeshi, any other Asian; black = Caribbean, "
        "African, any other Black; chinese; other = any other ethnic group; unclassified (refused / not obtained). "
        "Computed from DfE pupil counts over ethnicity_base (headcount of pupils); "
        "ethnicity_detail_pct holds DfE's published percentages.",
        "eal_pct = first language known or believed to be other than English. fsm.eligible_pct = pupils known to be "
        "eligible for free school meals.",
        "class_sizes are for classes taught by one teacher. average_infant_reception_ks1 is DfE's 'key stage 1 "
        "classes' (infant classes: reception, year 1 and year 2); DfE publishes no separate key stage 3/4 averages, "
        "so secondary schools only have average_all_classes. Independent schools do not return class size or "
        "ethnicity data.",
        "DfE applied no suppression to these files; values not collected (e.g. ethnicity, FSM and class sizes for "
        "independent schools) are null.",
    ]
    return {
        la_code: {
            "sources": sources,
            "time_period": period,
            "census": census,
            "release_published": meta["published"],
            "notes": notes,
            "schools": dict(sorted(schools.items(), key=lambda kv: int(kv[0]))),
        }
        for la_code, schools in schools_by_la.items()
    }
