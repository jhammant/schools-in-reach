"""School register (GIAS) -> schools.json rows."""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from pyproj import Transformer

from values import num

LA_CODE = "204"
EMPTY = {"", "Not applicable", "Not Applicable", "NULL", "None"}

_to_wgs84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return None if value in EMPTY else value


def _iso_date(value: str | None) -> str | None:
    value = _clean(value)
    if not value:
        return None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return value


def _flag(value: str | None, yes: str, no: str) -> bool | None:
    value = _clean(value)
    if value == yes:
        return True
    if value == no:
        return False
    return None


def load_register(path: Path, la_code: str = LA_CODE) -> list[dict]:
    with open(path, encoding="cp1252", newline="") as fh:
        rows = [
            row for row in csv.DictReader(fh)
            if row["LA (code)"] == la_code
            and row["EstablishmentStatus (name)"].startswith("Open")
        ]
    return rows


# GOR names that mark rows which are not real English local authorities
# (placeholders, Welsh pseudo-regions, offshore/overseas establishments).
NON_ENGLISH_GOR = {"Not Applicable", "Wales (pseudo)"}


def load_register_england(path: Path) -> tuple[dict[str, list[dict]], dict[str, dict], list[dict]]:
    """Group open establishments by LA code.

    Returns (rows_by_la, la_info, skipped) where la_info maps each kept LA code
    to {"name", "region"} and skipped lists {"code", "name", "reason"} for
    LA codes that are not real English local authorities.
    """
    rows_by_la: dict[str, list[dict]] = {}
    la_info: dict[str, dict] = {}
    skipped: dict[str, dict] = {}
    with open(path, encoding="cp1252", newline="") as fh:
        for row in csv.DictReader(fh):
            if not row["EstablishmentStatus (name)"].startswith("Open"):
                continue
            code = row["LA (code)"].strip()
            name = row["LA (name)"].strip()
            region = row["GOR (name)"].strip()
            if not code.isdigit() or region in NON_ENGLISH_GOR:
                skipped.setdefault(code, {"code": code, "name": name, "reason": f"GOR is {region!r}, not an English local authority"})
                continue
            rows_by_la.setdefault(code, []).append(row)
            la_info[code] = {"name": name, "region": region}
    return rows_by_la, la_info, sorted(skipped.values(), key=lambda s: s["code"])


def school_record(row: dict, la_code: str = LA_CODE) -> dict:
    easting = num(row.get("Easting"))
    northing = num(row.get("Northing"))
    lat = lon = None
    if easting and northing:
        lon, lat = _to_wgs84.transform(easting, northing)
        lat, lon = round(lat, 6), round(lon, 6)

    head_parts = [
        _clean(row.get("HeadTitle (name)")),
        _clean(row.get("HeadFirstName")),
        _clean(row.get("HeadLastName")),
    ]
    head = " ".join(p for p in head_parts if p) or None

    sen = [
        _clean(row.get(f"SEN{i} (name)"))
        for i in range(1, 14)
    ]
    sen = [s for s in sen if s]

    resourced = None
    rp_type = _clean(row.get("TypeOfResourcedProvision (name)"))
    if rp_type:
        resourced = {
            "type": rp_type,
            "on_roll": num(row.get("ResourcedProvisionOnRoll")),
            "capacity": num(row.get("ResourcedProvisionCapacity")),
            "sen_unit_on_roll": num(row.get("SenUnitOnRoll")),
            "sen_unit_capacity": num(row.get("SenUnitCapacity")),
        }
        resourced = {k: v for k, v in resourced.items() if v is not None}

    website = _clean(row.get("SchoolWebsite"))
    if website and not website.lower().startswith(("http://", "https://")):
        website = "https://" + website

    record = {
        "urn": int(row["URN"]),
        "name": row["EstablishmentName"].strip(),
        "lat": lat,
        "lon": lon,
        "easting": easting,
        "northing": northing,
        "phase": (row.get("PhaseOfEducation (name)") or "").strip() or None,
        "type": _clean(row.get("TypeOfEstablishment (name)")),
        "type_group": _clean(row.get("EstablishmentTypeGroup (name)")),
        "gender": _clean(row.get("Gender (name)")),
        "religious_character": _clean(row.get("ReligiousCharacter (name)")),
        "religious_ethos": _clean(row.get("ReligiousEthos (name)")),
        "diocese": _clean(row.get("Diocese (name)")),
        "admissions_policy": _clean(row.get("AdmissionsPolicy (name)")),
        "age_low": num(row.get("StatutoryLowAge")),
        "age_high": num(row.get("StatutoryHighAge")),
        "nursery_provision": _flag(row.get("NurseryProvision (name)"), "Has Nursery Classes", "No Nursery Classes"),
        "sixth_form": _flag(row.get("OfficialSixthForm (name)"), "Has a sixth form", "Does not have a sixth form"),
        "capacity": num(row.get("SchoolCapacity")),
        "pupils": num(row.get("NumberOfPupils")),
        "boys": num(row.get("NumberOfBoys")),
        "girls": num(row.get("NumberOfGirls")),
        "fsm_pct": num(row.get("PercentageFSM")),
        "census_date": _iso_date(row.get("CensusDate")),
        "street": _clean(row.get("Street")),
        "locality": _clean(row.get("Locality")),
        "address3": _clean(row.get("Address3")),
        "town": _clean(row.get("Town")),
        "postcode": _clean(row.get("Postcode")),
        "website": website,
        "phone": _clean(row.get("TelephoneNum")),
        "head": head,
        "head_job_title": _clean(row.get("HeadPreferredJobTitle")),
        "trust": _clean(row.get("Trusts (name)")),
        "trust_flag": _clean(row.get("TrustSchoolFlag (name)")),
        "sponsor": _clean(row.get("SchoolSponsors (name)")),
        "federation": _clean(row.get("Federations (name)")),
        "inspectorate": _clean(row.get("InspectorateName (name)")),
        "last_inspection_visit": _iso_date(row.get("DateOfLastInspectionVisit")),
        "sen_provision": sen or None,
        "resourced_provision": resourced or None,
        "boarders": _clean(row.get("Boarders (name)")),
        "lsoa": _clean(row.get("LSOA (code)")),
        "lsoa_name": _clean(row.get("LSOA (name)")),
        "msoa": _clean(row.get("MSOA (code)")),
        "msoa_name": _clean(row.get("MSOA (name)")),
        "ward": _clean(row.get("AdministrativeWard (name)")),
        "ward_code": _clean(row.get("AdministrativeWard (code)")),
        "constituency": _clean(row.get("ParliamentaryConstituency (name)")),
        "urban_rural": _clean(row.get("UrbanRural (name)")),
        "open_date": _iso_date(row.get("OpenDate")),
        "ukprn": _clean(row.get("UKPRN")),
        "laestab": f"{la_code}{row['EstablishmentNumber'].strip()}" if _clean(row.get("EstablishmentNumber")) else None,
    }
    return {k: v for k, v in record.items() if v is not None}
