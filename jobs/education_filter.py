import re

from config import FILTER_BY_EDUCATION, MAX_EDUCATION
from jobs.requirements_text import REQUIRED, is_optional, qualification_clauses

_BACHELORS = re.compile(r"\b(?:bachelor['’]?s?|b\.?\s*sc\.?|b\.?\s*s\.?|beng|btech|undergraduate|STEM\s+degree)\b", re.I)
_MASTERS = re.compile(r"\b(?:master['’]?s?|m\.?\s*sc\.?|m\.?\s*s\.?|mres|meng|mtech|mba|postgraduate\s+degree)\b", re.I)
_PHD = re.compile(r"\b(?:ph\.?\s*d\.?|dphil|doctorate|doctoral|post[ -]?doc(?:toral)?)\b", re.I)
_LEVELS = {"bachelors": 1, "bachelor": 1, "bsc": 1, "masters": 2, "master": 2, "msc": 2, "phd": 3, "doctorate": 3}


def education_matches(job: dict) -> bool:
    """Reject mandatory qualifications above the configured degree, not preferences."""
    if not FILTER_BY_EDUCATION:
        return True
    ceiling = _LEVELS.get(MAX_EDUCATION, 1)
    text = f"{job.get('title') or ''}\n{job.get('description') or ''}"
    for clause in qualification_clauses(text):
        if is_optional(clause):
            continue
        if re.search(r"\bno\s+(?:master['’]?s?|m\.?sc\.?|ph\.?d\.?|postgraduate\s+degree)"
                     r"(?:\s+\w+){0,3}\s+(?:required|needed|necessary)\b", clause, re.I):
            continue
        higher = (_MASTERS.search(clause) if ceiling < 2 else None) or (_PHD.search(clause) if ceiling < 3 else None)
        if not higher:
            continue
        lower = _BACHELORS.search(clause) or (_MASTERS.search(clause) if ceiling >= 2 else None)
        between = ""
        if lower:
            first, second = sorted((lower, higher), key=lambda match: match.start())
            between = clause[first.end():second.start()]
        alternative = bool(lower and re.search(r"\b(?:or|and/or)\b|/", between, re.I)
                           and not re.search(r"\b(?:with|plus)\b", between, re.I))
        if alternative:
            continue
        if REQUIRED.search(clause) or re.search(r"\b(?:post[ -]?doc(?:toral)?|phd\s+studentship)\b", clause, re.I):
            return False
    return True
