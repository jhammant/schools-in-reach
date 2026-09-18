"""Map ONS geography (LAD, LSOA) onto DfE LA codes, built from GIAS.

One DfE LA can span several ONS LADs (county councils, e.g. Kent DfE code 886 spans 12
LADs). We derive LAD -> DfE LA from GIAS's own `DistrictAdministrative (code)` (ONS LAD,
the school's physical location) vs `LA (code)` (DfE LA, the school's administering
authority) columns: for each English LAD, take the DfE LA code used by the majority of its
open schools. This is then checked against the *current* ONS LAD list (same service Hackney's
boundary step uses) so every English LAD is covered; any gap is resolved by matching the
LAD's ONS name against a DfE LA name (normalised), and reported either way.

Confirmed by running this against the live services on 2026-09-17:
- 296 English LADs (ONS 'Local_Authority_Districts_May_2026_Boundaries_UK_BFC').
- GIAS's majority-vote LAD -> LA mapping covers all 296 with zero gaps, and produces
  exactly 153 distinct DfE LA codes -- matching the 153 site/data/la/<code> folders other
  agents are already writing to. No name-based fallback was needed, but the code path
  exists and is exercised (and reported) if GIAS ever falls behind an LAD/LGR change.
- The ONS LSOA21->LAD25 lookup ('LSOA21_WD25_LAD25_EW_LU_v2') has 33,755 English LSOAs
  (2021 geography), matching IoD2025 File 7's LSOA count exactly. That is the authoritative
  total (the task brief's "33,642" estimate is superseded by this direct count).
"""

from __future__ import annotations

import json
import re

import pandas as pd

from areas import latest_lad_service, latest_lsoa_lookup
from common import CACHE, ROOT, log
from national_common import paginated_features

GIAS_CSV = ROOT / "pipeline" / ".cache" / "shared" / "gias_edubasealldata_20260916.csv"
MAPPING_CACHE = CACHE / "la_mapping.json"

OPEN_STATUSES = {"Open", "Open, but proposed to close"}


def _norm_name(s: str) -> str:
    s = s.lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]", "", s)


def _gias_open_english() -> pd.DataFrame:
    df = pd.read_csv(GIAS_CSV, encoding="cp1252", low_memory=False)
    df = df[df["EstablishmentStatus (name)"].isin(OPEN_STATUSES)]
    df = df[df["LA (code)"] != 0]
    df = df[df["DistrictAdministrative (code)"].astype(str).str.startswith("E")]
    return df


def _english_lads() -> dict[str, str]:
    """Current ONS English LAD codes -> names (same service as Hackney's boundary step)."""
    service, _year = latest_lad_service()
    try:
        cache_name = f"{service}_all_england.json"
        feats = paginated_features(service, "LAD26CD LIKE 'E%'", "LAD26CD,LAD26NM", cache_name.replace(".json", ""))
        code_field = next(k for k in feats[0]["attributes"] if re.fullmatch(r"LAD\d\dCD", k))
        name_field = code_field[:-2] + "NM"
        return {f["attributes"][code_field]: f["attributes"][name_field] for f in feats}
    except Exception as err:  # noqa: BLE001
        log(f"  could not list live ONS LAD codes ({err}); mapping will be GIAS-only")
        return {}


def build_mapping(refresh: bool = False) -> dict:
    """Returns {"la_to_lads", "la_names", "lad_names", "lad_to_la", "gaps"}. Cached to
    pipeline/.cache/geo/la_mapping.json (network calls inside common.fetch are cached too,
    so a rebuild without --refresh is fast either way)."""
    if MAPPING_CACHE.exists() and not refresh:
        return json.loads(MAPPING_CACHE.read_text())

    gias = _gias_open_english()
    lad_to_la_gias = gias.groupby("DistrictAdministrative (code)")["LA (code)"].agg(
        lambda s: str(int(s.mode().iloc[0]))
    ).to_dict()
    la_names = {
        str(int(k)): v for k, v in
        gias.groupby("LA (code)")["LA (name)"].agg(lambda s: s.mode().iloc[0]).to_dict().items()
    }

    ons_lads = _english_lads()
    lad_names = dict(ons_lads) if ons_lads else {k: k for k in lad_to_la_gias}
    all_lad_codes = set(ons_lads) | set(lad_to_la_gias)

    la_name_by_norm = {_norm_name(v): k for k, v in la_names.items()}
    lad_to_la: dict[str, str] = {}
    gaps: list[dict] = []
    for lad_code in sorted(all_lad_codes):
        if lad_code in lad_to_la_gias:
            lad_to_la[lad_code] = lad_to_la_gias[lad_code]
            continue
        # Not in GIAS (e.g. a brand-new LAD from local government reorganisation with no
        # open schools recorded against it yet): resolve by matching its ONS name.
        name = lad_names.get(lad_code, "")
        la_code = la_name_by_norm.get(_norm_name(name))
        if la_code:
            lad_to_la[lad_code] = la_code
            gaps.append({"lad_code": lad_code, "lad_name": name, "resolved_by": "name match", "la_code": la_code})
        else:
            gaps.append({"lad_code": lad_code, "lad_name": name, "resolved_by": None, "la_code": None})

    la_to_lads: dict[str, list[str]] = {}
    for lad_code, la_code in lad_to_la.items():
        la_to_lads.setdefault(la_code, []).append(lad_code)
    for la_code in la_to_lads:
        la_to_lads[la_code].sort()

    # la_names (from GIAS's LA (name) column, grouped by LA (code)) can include codes that
    # never won an English LAD's majority vote -- e.g. a handful of schools recorded under a
    # Welsh LA code (664 Flintshire, 669 Carmarthenshire) or the "Fieldwork Overseas
    # Establishments" placeholder (704) despite sitting in an English LAD. Restrict to the
    # real 153 DfE LAs so downstream name-matching (national_la_geometry.py) doesn't see them.
    la_names = {k: v for k, v in la_names.items() if k in la_to_lads}

    result = {
        "la_to_lads": la_to_lads,
        "la_names": la_names,
        "lad_names": lad_names,
        "lad_to_la": lad_to_la,
        "gaps": gaps,
        "english_lad_count": len(all_lad_codes),
        "la_count": len(la_to_lads),
    }
    if gaps:
        unresolved = [g for g in gaps if not g["la_code"]]
        log(f"la_mapping: {len(gaps)} LAD(s) not in GIAS's majority vote "
            f"({len(gaps) - len(unresolved)} resolved by name, {len(unresolved)} UNRESOLVED)")
        for g in gaps:
            log(f"  gap: {g}")
    else:
        log(f"la_mapping: {len(lad_to_la)} LADs -> {len(la_to_lads)} DfE LAs, no gaps")
    MAPPING_CACHE.parent.mkdir(parents=True, exist_ok=True)
    MAPPING_CACHE.write_text(json.dumps(result, indent=None))
    return result


def lsoa_lad_lookup(refresh: bool = False) -> list[dict]:
    """Every England+Wales LSOA21 -> LAD25 row from the ONS lookup (33,755 English +
    Welsh rows). Cached as raw ArcGIS JSON pages under pipeline/.cache/geo/."""
    svc = latest_lsoa_lookup()
    cache_prefix = f"{svc}_all"
    if refresh:
        for p in CACHE.glob(f"{cache_prefix}_p*.json"):
            p.unlink()
    feats = paginated_features(svc, "1=1", "LSOA21CD,LSOA21NM,LAD25CD,LAD25NM", cache_prefix)
    return [f["attributes"] for f in feats]


def la_lsoas(mapping: dict | None = None, refresh: bool = False) -> dict[str, list[str]]:
    """DfE LA code -> sorted LSOA21 codes, via LAD membership. Also returns per-LSOA name."""
    mapping = mapping or build_mapping()
    rows = lsoa_lad_lookup(refresh=refresh)
    lad_to_la = mapping["lad_to_la"]
    out: dict[str, list[str]] = {}
    lsoa_names: dict[str, str] = {}
    unmapped_lads: set[str] = set()
    for r in rows:
        lad = r["LAD25CD"]
        if not lad.startswith("E"):
            continue
        la = lad_to_la.get(lad)
        if la is None:
            unmapped_lads.add(lad)
            continue
        out.setdefault(la, []).append(r["LSOA21CD"])
        lsoa_names[r["LSOA21CD"]] = r["LSOA21NM"]
    for la in out:
        out[la].sort()
    if unmapped_lads:
        log(f"la_lsoas: {len(unmapped_lads)} LAD(s) in the LSOA lookup have no DfE LA mapping: {sorted(unmapped_lads)}")
    total = sum(len(v) for v in out.values())
    log(f"la_lsoas: {total} English LSOAs assigned across {len(out)} DfE LAs")
    return out, lsoa_names


if __name__ == "__main__":  # pragma: no cover
    m = build_mapping(refresh=True)
    lsoas, _names = la_lsoas(m, refresh=True)
    print(f"{m['la_count']} DfE LAs, {m['english_lad_count']} English LADs, "
          f"{sum(len(v) for v in lsoas.values())} LSOAs, {len(m['gaps'])} gaps")
