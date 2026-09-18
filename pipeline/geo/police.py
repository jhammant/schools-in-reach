"""Check the data.police.uk street-level crime API the frontend calls client-side.

Writes a short summary (no raw crime records) into pipeline/geo/README.md between markers and
pipeline/.cache/geo/police_check.json.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

import shapely

from common import CACHE, boundary_shape, log, now_iso, session

API = "https://data.police.uk/api"
TEST_LAT, TEST_LNG = 51.5597, -0.0763  # Stoke Newington, Hackney
README = Path(__file__).resolve().parent / "README.md"
START, END = "<!-- police-check:start -->", "<!-- police-check:end -->"


def _get(path: str, **params):
    r = session().get(f"{API}/{path}", params=params, timeout=120)
    return r


def poly_param(geom, max_points: int = 60) -> str:
    """Leaflet-friendly 'lat,lng:lat,lng' string for a polygon, simplified to <= max_points."""
    tol = 0.0002
    ring = geom.exterior
    while len(ring.coords) > max_points:
        ring = shapely.simplify(geom, tol).exterior
        tol *= 1.5
    return ":".join(f"{lat:.5f},{lng:.5f}" for lng, lat in list(ring.coords)[:-1])


def check_police_api() -> dict:
    out: dict = {"checked_at": now_iso(), "point": {"lat": TEST_LAT, "lng": TEST_LNG}}

    r = _get("crimes-street-dates")
    r.raise_for_status()
    dates = [d["date"] for d in r.json()]
    latest = max(dates)
    out["available_months"] = {"count": len(dates), "earliest": min(dates), "latest": latest}
    out["cors_allow_origin"] = r.headers.get("access-control-allow-origin")

    cats = _get("crime-categories", date=latest).json()
    names = {c["url"]: c["name"] for c in cats}
    out["categories"] = len(cats)

    r = _get("crimes-street/all-crime", lat=TEST_LAT, lng=TEST_LNG, date=latest)
    r.raise_for_status()
    crimes = r.json()
    out["point_1_mile"] = {
        "status": r.status_code,
        "total": len(crimes),
        "by_category": dict(Counter(names.get(c["category"], c["category"]) for c in crimes).most_common()),
        "fields": sorted(crimes[0].keys()) if crimes else [],
        "cors_allow_origin": r.headers.get("access-control-allow-origin"),
    }

    # Custom area: whole borough, simplified polygon, sent as POST (long polys exceed the 4094-char GET limit).
    poly = poly_param(boundary_shape())
    r = session().post(f"{API}/crimes-street/all-crime", data={"poly": poly, "date": latest}, timeout=180)
    out["hackney_polygon_post"] = {"status": r.status_code, "points": poly.count(":") + 1,
                                   "total": len(r.json()) if r.ok else None}

    # A GET with a short polygon (square ~500 m around the test point).
    d = 0.0023
    sq = f"{TEST_LAT+d:.5f},{TEST_LNG-d*1.6:.5f}:{TEST_LAT+d:.5f},{TEST_LNG+d*1.6:.5f}:{TEST_LAT-d:.5f},{TEST_LNG+d*1.6:.5f}:{TEST_LAT-d:.5f},{TEST_LNG-d*1.6:.5f}"
    r = _get("crimes-street/all-crime", poly=sq, date=latest)
    out["square_polygon_get"] = {"status": r.status_code, "total": len(r.json()) if r.ok else None}

    # Demonstrate the 10,000-crime cap with a Greater-London-sized polygon.
    big = "51.70,-0.50:51.70,0.30:51.28,0.30:51.28,-0.50"
    r = _get("crimes-street/all-crime", poly=big, date=latest)
    out["london_polygon_get"] = {"status": r.status_code, "note": "503 expected: more than 10,000 crimes"}

    (CACHE / "police_check.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    log(f"police: latest month {latest}; {len(crimes)} crimes within 1 mile of test point; "
        f"Hackney polygon POST -> {out['hackney_polygon_post']}; London polygon -> HTTP {out['london_polygon_get']['status']}")
    update_readme(out)
    return out


def update_readme(out: dict) -> None:
    if not README.exists():
        return
    p = out["point_1_mile"]
    rows = "\n".join(f"| {k} | {v} |" for k, v in p["by_category"].items())
    block = f"""{START}
_Last checked {out['checked_at']} by `build.py --only police`._

- Months available: {out['available_months']['count']} ({out['available_months']['earliest']} to {out['available_months']['latest']}); latest = **{out['available_months']['latest']}**.
- `Access-Control-Allow-Origin: {p['cors_allow_origin']}` on crime responses, so browser `fetch()` works.
- 1-mile radius around lat {out['point']['lat']}, lng {out['point']['lng']} ({out['available_months']['latest']}): **{p['total']} crimes** (HTTP {p['status']}).
- Whole-borough polygon ({out['hackney_polygon_post']['points']} points) via POST: HTTP {out['hackney_polygon_post']['status']}, {out['hackney_polygon_post']['total']} crimes.
- ~500 m square polygon via GET: HTTP {out['square_polygon_get']['status']}, {out['square_polygon_get']['total']} crimes.
- Greater-London-sized polygon: HTTP {out['london_polygon_get']['status']} (over the 10,000-crime cap).

| Category ({out['available_months']['latest']}, 1 mile of test point) | Crimes |
|---|---|
{rows}
{END}"""
    text = README.read_text(encoding="utf-8")
    if START in text and END in text:
        text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
        README.write_text(text, encoding="utf-8")
