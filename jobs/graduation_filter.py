"""Check explicit applicant graduation cohorts, not programme start dates."""

import re

from config import CANDIDATE_GRADUATION_YEAR
from jobs.requirements_text import is_optional, qualification_clauses

_YEARS = r"20\d{2}(?:\s*(?:,|/|or|and|to|-)\s*20\d{2})*"
_COHORT = re.compile(
    rf"\b(?:(?:graduating|graduated)\s+(?:in\s+)?|graduate\s+in\s+)(?P<after>{_YEARS})\b|"
    rf"\b(?P<before>{_YEARS})\s+graduates\b|"
    rf"\b(?:graduation\s+(?:year|date)|class\s+of)\s*[:=]?\s*(?P<label>{_YEARS})\b", re.I
)


def graduation_matches(job: dict) -> bool:
    for clause in qualification_clauses(f"{job.get('title') or ''}\n{job.get('description') or ''}"):
        if is_optional(clause):
            continue
        for match in _COHORT.finditer(clause):
            value = next(value for value in match.groups() if value)
            years = [int(year) for year in re.findall(r"20\d{2}", value)]
            accepted = set(years)
            if len(years) == 2 and re.search(r"\bto\b|-", value) and years[0] <= years[1]:
                accepted.update(range(years[0], years[1] + 1))
            if CANDIDATE_GRADUATION_YEAR not in accepted:
                return False
    return True
