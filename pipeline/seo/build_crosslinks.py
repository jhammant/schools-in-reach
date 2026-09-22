"""Build cross-site link maps between Schools in Reach and TermMinder.

Input: a TermMinder export (`{"jurisdictions": [{..., "is_live"}], "schools": [[official_reference, id, jurisdiction_id], ...]}`)
from its production database, plus this repo's generated slug maps (site/embed/slugs/*.json).
Output:
  pipeline/seo/crosslinks.json                 -> used by build_pages.py (links to TermMinder)
  <out_dir>/schoolsinreach.json                -> copied into TermMinder (links to Schools in Reach)
Councils match on official GSS code, then on a normalised name. Schools match on URN / official reference.
"""
import json, re, sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline.seo.build_pages import slug  # same slugs as the generated council pages

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "site" / "data"


def norm(name):
    name = name.lower().replace("&", "and")
    name = re.sub(r"\b(city of|county of|the|council|borough|royal borough of|london borough of)\b", " ", name)
    return re.sub(r"[^a-z0-9]+", "", name)


def load_las():
    las = json.loads((DATA / "england" / "las.json").read_text())
    las = las.get("las", las) if isinstance(las, dict) else las
    for f in ("scotland_las.json", "wales_las.json", "northern_ireland_las.json"):
        d = json.loads((DATA / "uk" / f).read_text())
        las += d.get("las", d) if isinstance(d, dict) else d
    return las


def main(export_path, out_dir):
    tm = json.loads(Path(export_path).read_text())
    # TermMinder only serves pages for live jurisdictions; linking any other would 404.
    live = [j for j in tm["jurisdictions"] if j.get("is_live", True)]
    juris = [j for j in live if j.get("level") == "authority"]
    # Northern Ireland has one Education Authority calendar, so every NI council links to it.
    ni = next((j for j in live if j["id"] == "uk-nir"), None)
    by_code = {j["official_code"]: j for j in juris if j.get("official_code")}
    by_name = {norm(j["name"]): j for j in juris}
    to_tm_councils, to_sir_councils, unmatched = {}, {}, []
    for la in load_las():
        j = next((by_code[c] for c in [la["la_code"], *la.get("lad_codes", [])] if c in by_code), None) or by_name.get(norm(la["name"]))
        if not j and ni and (la.get("nation") == "Northern Ireland" or str(la["la_code"]).startswith("N09")):
            j = ni
        if not j:
            unmatched.append(la["name"]); continue
        to_tm_councils[la["la_code"]] = f"/uk/term-dates/{j['slug']}/"
        to_sir_councils.setdefault(j["id"], f"/council/{slug(la['name'])}/")
    sir_paths = {}
    for f in (ROOT / "site" / "embed" / "slugs").glob("*.json"):
        for urn, s in json.loads(f.read_text()).items():
            sir_paths[str(urn)] = f"/school/{urn}-{s}/"
    to_tm_schools, to_sir_schools = {}, {}
    for ref, tm_id, _ in tm["schools"]:
        if str(ref) in sir_paths:
            to_tm_schools[str(ref)] = f"/uk/schools/{tm_id}/"
            to_sir_schools[tm_id] = sir_paths[str(ref)]
    today = date.today().isoformat()
    (ROOT / "pipeline" / "seo" / "crosslinks.json").write_text(json.dumps(
        {"generated": today, "termminder": {"base": "https://www.termminder.com", "councils": to_tm_councils, "schools": to_tm_schools}},
        separators=(",", ":"), sort_keys=True))
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "schoolsinreach.json").write_text(json.dumps(
        {"generated": today, "base": "https://www.schoolsinreach.com", "councils": to_sir_councils, "schools": to_sir_schools},
        separators=(",", ":"), sort_keys=True))
    print(f"councils matched {len(to_tm_councils)}/{len(to_tm_councils) + len(unmatched)}; unmatched: {unmatched}")
    print(f"schools matched {len(to_tm_schools)} of {len(sir_paths)} SiR / {len(tm['schools'])} TermMinder")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
