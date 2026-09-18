"""Map school names printed in council admissions sources to DfE URNs using GIAS.

Adapted from pipeline/admissions/gias.py (the Hackney pipeline), parameterised
by LA code and an optional per-borough manual-alias table so it can be reused
across boroughs. See that module's docstring for the matching approach: names
are reduced to a set of distinctive tokens before comparing, and a matched
school that has since converted to an academy (or been re-brokered / fresh-
started) is followed to its current open URN via GIAS.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

GENERIC = {"primary", "school", "schools", "community", "academy", "the", "and", "a", "of", "secondary", "voluntary",
           "aided", "with"}
SUCCESSION_REASONS = {"Academy Converter", "For Academy", "Fresh Start"}
PHASES = {
    "secondary": {"Secondary", "All-through", "Middle deemed secondary"},
    "primary": {"Primary", "All-through", "Middle deemed primary"},
}
STATE_GROUPS = {"Local authority maintained schools", "Academies", "Free Schools"}
DATA_START = date(2019, 9, 1)  # earliest admissions round covered by these sources is September 2020


def tokens(name: str) -> frozenset[str]:
    s = name.lower().replace("&", " and ").replace("’", "'")
    s = re.sub(r"\bchurch of england\b|\bcofe\b|\bc of e\b", " ce ", s)
    s = re.sub(r"\broman catholic\b|\brc\b", " catholic ", s)
    s = re.sub(r"\bsaint\b|\bst\.", " st ", s)
    s = re.sub(r"'s\b", "", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return frozenset(t for t in s.split() if t not in GENERIC)


def _key(toks: frozenset[str]) -> str:
    return " ".join(sorted(toks))


def _date(value: str) -> date | None:
    return datetime.strptime(value, "%d-%m-%Y").date() if value else None


@dataclass
class Establishment:
    urn: str
    name: str
    phase: str
    status: str
    postcode: str
    open_date: date | None
    close_date: date | None
    close_reason: str
    toks: frozenset[str] = field(default=frozenset())

    @property
    def is_open(self) -> bool:
        return self.status.startswith("Open")


@dataclass
class Match:
    urn: str
    name: str
    status: str
    via: str
    former_urns: list[str]
    former_names: list[str]


class Gias:
    def __init__(self, csv_path: Path, la_code: str, manual_aliases: dict[str, tuple[str, str]] | None = None):
        self.la_code = la_code
        self.manual_aliases = manual_aliases or {}
        self.by_urn: dict[str, Establishment] = {}
        with open(csv_path, encoding="cp1252", newline="") as fh:
            for row in csv.DictReader(fh):
                if row["LA (code)"] != la_code or row["EstablishmentTypeGroup (name)"] not in STATE_GROUPS:
                    continue
                est = Establishment(row["URN"], row["EstablishmentName"], row["PhaseOfEducation (name)"],
                                    row["EstablishmentStatus (name)"], row["Postcode"], _date(row["OpenDate"]),
                                    _date(row["CloseDate"]), row["ReasonEstablishmentClosed (name)"])
                est.toks = tokens(est.name)
                self.by_urn[est.urn] = est

    def _candidates(self, phase: str) -> list[Establishment]:
        return [e for e in self.by_urn.values() if e.phase in PHASES[phase]]

    def _successor(self, est: Establishment) -> Establishment | None:
        if est.is_open or est.close_reason not in SUCCESSION_REASONS or est.close_date is None:
            return None
        nxt = [e for e in self.by_urn.values() if e.postcode == est.postcode and e.phase == est.phase
               and e.open_date and 0 <= (e.open_date - est.close_date).days <= 400]
        if len(nxt) > 1:
            nxt = [e for e in nxt if e.toks == est.toks] or nxt
        return nxt[0] if len(nxt) == 1 else None

    def _predecessors(self, est: Establishment) -> list[Establishment]:
        if est.open_date is None:
            return []
        return [e for e in self.by_urn.values()
                if e.urn != est.urn and e.postcode == est.postcode and e.phase == est.phase
                and e.close_reason in SUCCESSION_REASONS
                and e.close_date and e.close_date >= DATA_START and 0 <= (est.open_date - e.close_date).days <= 400]

    def match(self, name: str, phase: str) -> Match | None:
        toks = tokens(name)
        via = "name"
        if _key(toks) in self.manual_aliases:
            urn, why = self.manual_aliases[_key(toks)]
            est, via = self.by_urn[urn], f"manual alias ({why})"
        else:
            pool = self._candidates(phase)
            exact = [e for e in pool if e.toks == toks]
            if not exact:
                exact = [e for e in pool if toks and (toks < e.toks or e.toks < toks)]
                via = "name (token subset)"
            if len(exact) > 1:
                opened = [e for e in exact if e.is_open]
                exact = opened if len(opened) == 1 else exact
            if len(exact) != 1:
                return None
            est = exact[0]
        chain = [est]
        while (nxt := self._successor(chain[-1])) is not None and nxt not in chain:
            chain.append(nxt)
        current = chain[-1]
        former = {e.urn: e for e in chain[:-1]}
        for pred in self._predecessors(current):
            former.setdefault(pred.urn, pred)
        former_names = []
        if tokens(name) != current.toks and not (tokens(name) < current.toks or current.toks < tokens(name)):
            former_names.append(name)
        for e in former.values():
            if e.toks != current.toks and e.name not in former_names:
                former_names.append(e.name)
        return Match(current.urn, current.name, "open" if current.is_open else "closed", via,
                     sorted(former, key=int), former_names)
