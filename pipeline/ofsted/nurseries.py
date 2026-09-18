"""nurseries.json: Ofsted-registered early years and childcare providers for every
English local authority, split into one file per LA.

Source: gov.uk "Childcare providers and inspections: management information"
(latest 'childcare provider data as at' CSV, OGL v3.0), which already covers all
of England. Postcodes of providers whose address Ofsted publishes (non-domestic
premises) are geocoded offline from the National Statistics Postcode Lookup
(NSPL), ONS Open Geography Portal, OGL - not via a live per-postcode API.

Each provider is assigned to a DfE LA using the MI's own 'Local authority' name
column where it matches a GIAS LA name; the handful of rows with no usable LA
name (Ofsted MI: 'Not Recorded') fall back to the postcode's local authority
district (from the NSPL), mapped to a DfE LA via GIAS (DistrictAdministrative
(code) -> LA (code)). Providers with neither are dropped (extremely rare: a
handful of records nationally with both an unrecorded LA and a redacted address).

Ofsted redacts the name and address of childminders, home childcarers and
childcare on domestic premises; those providers are kept without a name or
coordinates and summarised by parliamentary constituency.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from util import (CACHE, OGL, REPORTS, cached_attachment, clean, district_name_index, district_to_la,
                  fetch, gias_open_all, govuk_attachments, iso, la_code_for_name,
                  log, pick_attachment, prune, read_csv, to_int)

SLUG = "childcare-providers-and-inspections-management-information"

# ONS Open Geography Portal hosted tables (OGL). Re-issued quarterly/periodically;
# the item ids below are the latest at the time of writing (Feb 2026 NSPL, May
# 2025 ward names) - pass --refresh after ONS publishes a newer release to re-fetch.
NSPL_ITEM = "419355d8a54741f19025ba97e35da55a"  # National Statistics Postcode Lookup (February 2026) for the UK
NSPL_URL = f"https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/{NSPL_ITEM}/csv?layers=0"
NSPL_RAW = CACHE / "nspl" / "nspl_latest.csv"
WARD_NAMES_ITEM = "db1e8af0f59f4aaf8ec5d21afe8f26b0"  # Wards (May 2025) Names and Codes in the UK
WARD_NAMES_URL = f"https://open-geography-portalx-ons.hub.arcgis.com/api/download/v1/items/{WARD_NAMES_ITEM}/csv?layers=0"
WARD_NAMES_RAW = CACHE / "nspl" / "ward_names.csv"
GEO_CACHE = CACHE / "nspl" / "postcode_index.json"

# reports.ofsted.gov.uk provider categories (checked with the site search for each type)
PROVIDER_CATEGORY = {
    "Childcare on domestic premises": "15",
    "Childcare on non-domestic premises": "16",
    "Childminder": "17",
    "Home childcarer": "18",
}

GRADE_WORDS = {"1": "Outstanding", "2": "Good", "3": "Requires improvement", "4": "Inadequate"}


def val(v: str | None) -> str | None:
    v = clean(v)
    return None if v in (None, "-") else v


def grade(v: str | None) -> str | None:
    v = val(v)
    if v is None:
        return None
    return GRADE_WORDS.get(v, v if not v[0].isdigit() else None)


def yn(v: str | None) -> bool | None:
    return {"Yes": True, "No": False, "Y": True, "N": False}.get(val(v) or "")


def norm_pc(pc: str) -> str:
    pc = "".join(pc.upper().split())
    return f"{pc[:-3]} {pc[-3:]}" if len(pc) > 3 else pc


def ward_names(refresh: bool = False) -> dict[str, str]:
    """ONS ward code (e.g. E05009375) -> ward name (Wards (May 2025) Names and Codes in the UK)."""
    path = fetch(WARD_NAMES_URL, WARD_NAMES_RAW, refresh)
    return {r["WD25CD"]: r["WD25NM"] for r in read_csv(path) if r.get("WD25CD") and r.get("WD25NM")}


def geocode(postcodes: set[str], refresh: bool = False) -> dict[str, dict | None]:
    """postcode -> {lat, lon, ward, district, lad, terminated}, from the NSPL (offline, cached)."""
    cache: dict[str, dict | None] = {}
    if GEO_CACHE.exists() and not refresh:
        cache = json.loads(GEO_CACHE.read_text())
    todo = sorted(pc for pc in postcodes if pc not in cache)
    if todo:
        import pandas as pd  # local import: only needed the first time new postcodes must be resolved

        path = fetch(NSPL_URL, NSPL_RAW, refresh)
        log(f"  looking up {len(todo)} postcodes in the NSPL ({path.stat().st_size / 1e6:.0f} MB source, offline)")
        wards = ward_names(refresh)
        districts = district_name_index()
        wanted = set(todo)
        df = pd.read_csv(path, usecols=["pcds", "lat", "long", "lad25cd", "wd25cd", "doterm"],
                         dtype=str, low_memory=False)
        df = df[df["pcds"].isin(wanted)]
        found: dict[str, dict] = {}
        for pcds, lat, lon, lad, wd, doterm in zip(df["pcds"], df["lat"], df["long"], df["lad25cd"],
                                                    df["wd25cd"], df["doterm"]):
            if not lat or not lon or lat != lat:  # lat != lat catches NaN
                continue
            found[pcds] = {
                "lat": round(float(lat), 6), "lon": round(float(lon), 6),
                "ward": wards.get(wd or "") if wd and wd == wd else None,
                "district": districts.get(lad or "") if lad and lad == lad else None,
                "lad": lad if lad and lad == lad else None,
                "terminated": bool(doterm and doterm == doterm and doterm.strip()),
            }
        for pc in todo:
            cache[pc] = found.get(pc)
    GEO_CACHE.parent.mkdir(parents=True, exist_ok=True)
    GEO_CACHE.write_text(json.dumps(cache, indent=0, sort_keys=True))
    return {pc: cache.get(pc) for pc in postcodes}


def provider_record(r: dict) -> dict:
    urn = r["Provider URN"].strip()
    ptype = val(r.get("Provider type"))
    name = val(r.get("Provider name"))
    postcode = val(r.get("Provider postcode"))
    address = [val(r.get(c)) for c in ("Provider address line 1", "Provider address line 2",
                                        "Provider address line 3", "Provider town")]

    reif = None
    if val(r.get("EYR REIF: Most recent: Inspection date")):
        reif = {
            "date": iso(r.get("EYR REIF: Most recent: Inspection date")),
            "type": val(r.get("EYR REIF: Most recent: Inspection visit type")),
            "inspection_number": val(r.get("EYR REIF: Most recent: Inspection number")),
            "safeguarding_standards": val(r.get("EYR REIF: Most recent: Safeguarding standards met?")),
            "inclusion": val(r.get("EYR REIF: Most recent: Inclusion")),
            "curriculum_and_teaching": val(r.get("EYR REIF: Most recent: Curriculum and teaching")),
            "achievement": val(r.get("EYR REIF: Most recent: Achievement")),
            "behaviour_attitudes_and_routines": val(r.get("EYR REIF: Most recent: Behaviour, attitudes and establishing routines")),
            "childrens_welfare_and_wellbeing": val(r.get("EYR REIF: Most recent: Children's welfare and wellbeing")),
            "leadership_and_governance": val(r.get("EYR REIF: Most recent: Leadership and governance")),
        }
    graded = None
    oe = grade(r.get("EYR OEIF/CIF: Most recent: Overall effectiveness"))
    gdate = iso(r.get("EYR OEIF: Most recent: Full inspection date"))
    if oe or gdate:
        graded = {
            "date": gdate,
            "inspection_number": val(r.get("EYR OEIF: Most recent: Full inspection number")),
            "overall_effectiveness": oe,
            "quality_of_education": grade(r.get("EYR OEIF: Most recent: Quality of education")),
            "behaviour_and_attitudes": grade(r.get("EYR OEIF: Most recent: Behaviour and attitudes")),
            "personal_development": grade(r.get("EYR OEIF: Most recent: Personal development")),
            "leadership_and_management": grade(r.get("EYR OEIF/CIF: Most recent: Effectiveness of leadership and management")),
            "safeguarding_effective": yn(r.get("EYR OEIF: Most recent: Safeguarding is effective?")),
        }
    ncor = oosc = cr = None
    if val(r.get("EYR OEIF NCOR: Most recent: Inspection date")):
        ncor = {"date": iso(r.get("EYR OEIF NCOR: Most recent: Inspection date")),
                "outcome": val(r.get("EYR OEIF NCOR: Most recent: Overall effectiveness"))}
    if val(r.get("EYR OEIF OOSC: Most recent: Inspection date")):
        oosc = {"date": iso(r.get("EYR OEIF OOSC: Most recent: Inspection date")),
                "outcome": val(r.get("EYR OEIF OOSC: Most recent: Overall effectiveness")),
                "safeguarding_effective": yn(r.get("EYR OEIF OOSC: Most recent: Safeguarding is effective?"))}
    if val(r.get("CR: Most recent: Inspection date")):
        cr = {"date": iso(r.get("CR: Most recent: Inspection date")),
              "compliance": val(r.get("CR: Compliance"))}

    dated = [(e["date"], label, e) for label, e in
             (("eyr_report_card", reif), ("eyr_graded", graded), ("eyr_no_children_on_roll", ncor),
              ("eyr_out_of_school", oosc), ("childcare_register", cr)) if e and e.get("date")]
    dated.sort(key=lambda x: x[0], reverse=True)
    latest = dated[0] if dated else None
    if latest:
        e = latest[2]
        # report cards have no single headline grade: see eyr_report_card
        latest_grade = None if latest[1] == "eyr_report_card" else (
            e.get("overall_effectiveness") or e.get("outcome") or e.get("compliance"))
    else:
        latest_grade = None

    addressed = ptype == "Childcare on non-domestic premises" and postcode is not None
    rec = {
        "urn": urn,
        "provider_type": ptype,
        "provider_subtype": val(r.get("Provider subtype")),
        "name": name if addressed or ptype == "Childcare on non-domestic premises" else None,
        "registration_date": iso(r.get("Registration date")),
        "registers": {
            "eyr": val(r.get("Provider Early Years Register flag")) == "Y",
            "ccr": val(r.get("Provider Compulsory Childcare Register flag")) == "Y",
            "vcr": val(r.get("Provider Voluntary Childcare Register flag")) == "Y",
        },
        "places": to_int(r.get("Places")),
        "latest_inspection_date": latest[0] if latest else None,
        "latest_inspection": latest[1] if latest else None,
        "latest_grade": latest_grade,
        "overall_effectiveness": oe,
        "eyr_report_card": reif,
        "eyr_graded": graded,
        "eyr_no_children_on_roll": ncor,
        "eyr_out_of_school": oosc,
        "childcare_register": cr,
        "ccr_suitability": val(r.get("CCR requirements suitability")),
        "vcr_suitability": val(r.get("VCR requirements suitability")),
        "constituency": val(r.get("Parliamentary constituency")),
        "deprivation_band": val(r.get("Deprivation band")),
    }
    if addressed:
        rec["address"] = ", ".join(a for a in address if a)
        rec["postcode"] = norm_pc(postcode)
    category = PROVIDER_CATEGORY.get(ptype or "")
    if category:
        # Ofsted's own page withholds names/addresses of childminders etc.
        rec["report_url"] = f"{REPORTS}/{category}/{urn}"
    return rec


def build_all(refresh: bool = False) -> dict[str, dict]:
    """Build nurseries.json content for every English LA. Returns {la_code: data}."""
    log("nurseries.json: childcare providers (all England)")
    _, atts = govuk_attachments(SLUG, refresh)
    att = pick_attachment(atts, r"childcare provider(s)? data as at|most recent inspections data as at", ".csv")
    rows = read_csv(cached_attachment(att, "childcare_providers", refresh), header_first_cell="Web link")
    active = [r for r in rows if (r.get("Provider status") or "Active") == "Active"]

    gias = gias_open_all()
    d2la = district_to_la()

    # LA assignment: primarily the MI's own 'Local authority' name; the few rows Ofsted
    # marks 'Not Recorded' fall back to postcode -> district (NSPL) -> LA (GIAS).
    la_by_row: list[str | None] = []
    fallback_postcodes: set[str] = set()
    for r in active:
        la_code = la_code_for_name(r.get("Local authority"))
        la_by_row.append(la_code)
        if la_code is None:
            pc = val(r.get("Provider postcode"))
            if pc:
                fallback_postcodes.add(norm_pc(pc))

    providers = [provider_record(r) for r in active]
    publish_postcodes = {p["postcode"] for p in providers if p.get("postcode")}
    geo = geocode(publish_postcodes | fallback_postcodes, refresh)

    for i, la_code in enumerate(la_by_row):
        if la_code is not None:
            continue
        pc = val(active[i].get("Provider postcode"))
        g = geo.get(norm_pc(pc)) if pc else None
        if g and g.get("lad"):
            la_by_row[i] = d2la.get(g["lad"])

    by_la: dict[str, list[dict]] = defaultdict(list)
    unassigned = 0
    for i, p in enumerate(providers):
        la_code = la_by_row[i]
        if not la_code:
            unassigned += 1
            continue
        if p.get("postcode"):
            g = geo.get(p["postcode"])
            if g:
                p["lat"], p["lon"] = g["lat"], g["lon"]
                if g.get("ward"):
                    p["ward"] = g["ward"]
        by_la[la_code].append(p)
    if unassigned:
        log(f"  {unassigned} providers could not be matched to an English LA (skipped, e.g. redacted address + "
            f"'Not Recorded' LA)")

    la_names = {r.get("LA (code)"): r.get("LA (name)") for r in gias.values()}
    sources = [
        {"title": f"Childcare providers and inspections: management information - {att['title']}",
         "url": att["url"], "licence": OGL},
        {"title": "National Statistics Postcode Lookup (NSPL), ONS Open Geography Portal - coordinates, ward "
                  "and local authority district",
         "url": "https://geoportal.statistics.gov.uk/", "licence": OGL},
    ]
    data_as_at = att["as_at"].isoformat()

    outputs: dict[str, dict] = {}
    for la_code, la_providers in by_la.items():
        la_name = la_names.get(la_code, la_code)
        la_providers.sort(key=lambda p: (p.get("provider_type") or "", p.get("name") or "~", p["urn"]))

        by_type = Counter(p["provider_type"] for p in la_providers)
        unaddressed = [p for p in la_providers if not p.get("postcode")]
        by_constituency: dict[str, Counter] = defaultdict(Counter)
        for p in unaddressed:
            by_constituency[p.get("constituency") or "Unknown"][p["provider_type"]] += 1
        by_ward: dict[str, Counter] = defaultdict(Counter)
        outside = 0
        for p in la_providers:
            if p.get("ward"):
                by_ward[p["ward"]][p["provider_type"]] += 1
            if p.get("postcode"):
                g = geo.get(p["postcode"])
                if g and g.get("lad") and d2la.get(g["lad"]) != la_code:
                    outside += 1
        places_by_type = Counter()
        for p in la_providers:
            places_by_type[p["provider_type"]] += p.get("places") or 0

        la_gias = {u: g for u, g in gias.items() if g.get("LA (code)") == la_code}
        nursery_schools = sum(1 for g in la_gias.values()
                              if g.get("TypeOfEstablishment (name)") == "Local authority nursery school")
        nursery_classes = sum(1 for g in la_gias.values() if g.get("NurseryProvision (name)") == "Has Nursery Classes")
        nursery_classes_state = sum(1 for g in la_gias.values() if g.get("NurseryProvision (name)") == "Has Nursery Classes"
                                    and "independent" not in (g.get("TypeOfEstablishment (name)") or "").lower())

        outputs[la_code] = {
            "sources": sources,
            "data_as_at": data_as_at,
            "la": {"code": int(la_code), "name": la_name},
            "notes": [
                f"Active Ofsted-registered early years and childcare providers whose local authority is {la_name}.",
                "Ofsted withholds the name and address of childminders, home childcarers and childcare on domestic "
                "premises: those records have no name, address or coordinates and are counted by parliamentary "
                "constituency in counts.unaddressed_by_constituency (the MI gives no ward for them).",
                "registers: eyr = Early Years Register, ccr = Compulsory Childcare Register, vcr = Voluntary Childcare "
                "Register. Providers only on the childcare registers (e.g. nannies/home childcarers) are not graded.",
                "overall_effectiveness is the most recent graded Early Years Register inspection (EIF/CIF). "
                "eyr_report_card holds renewed-framework report card grades (from 10 November 2025) exactly as "
                "published. latest_inspection names the most recent of the inspection blocks and latest_grade gives "
                "its headline outcome.",
                "lat/lon/ward come from the provider postcode (NSPL centroid, offline - not a live geocoding API), "
                "so several providers can share a point.",
                f"Not duplicated here: {la_name}'s {nursery_schools} maintained nursery schools and the "
                f"{nursery_classes} schools with nursery classes ({nursery_classes_state} state-funded) listed in "
                "schools.json / ofsted.json (GIAS) - school-run nursery classes are inspected as part of the school.",
            ],
            "counts": {
                "providers": len(la_providers),
                "by_type": dict(sorted(by_type.items())),
                "places_by_type": dict(sorted(places_by_type.items())),
                "with_address": len(la_providers) - len(unaddressed),
                "geocoded": sum(1 for p in la_providers if "lat" in p),
                "addressed_outside_hackney_boundary": outside,
                "unaddressed_by_constituency": {k: dict(sorted(v.items())) for k, v in sorted(by_constituency.items())},
                "addressed_by_ward": {k: dict(sorted(v.items())) for k, v in sorted(by_ward.items())},
            },
            "providers": [prune(p) for p in la_providers],
        }
    return outputs
