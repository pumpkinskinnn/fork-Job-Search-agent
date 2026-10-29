import re

from config import (
    FILTER_BY_EDUCATION, MAX_EDUCATION, USER_PROFILE,
    CURRENT_EDUCATION, CURRENT_EDUCATION_STATUS, CURRENT_EDUCATION_DISCIPLINE,
)
from jobs.availability_filter import assess_start, add_eligibility_warning, clear_eligibility_warnings
from jobs.requirements_text import REQUIRED, is_optional, qualification_clauses

_BACHELORS = re.compile(r"\b(?:bachelor['’]?s?|b\.?\s*sc\.?|b\.?\s*s\.?|beng|btech|undergraduate|STEM\s+degree)\b", re.I)
_MASTERS = re.compile(r"\b(?:master['’]?s?|m\.?\s*sc\.?|m(?!\.?\s*s\.?\s*office\b)\.?\s*s\.?|mres|meng|mtech|mba|postgraduate\s+degree)\b", re.I)
_PHD = re.compile(r"\b(?:ph\.?\s*d\.?|dphil|doctorate|doctoral|post[ -]?doc(?:toral)?)\b", re.I)
_LEVELS = {"bachelors": 1, "bachelor": 1, "bsc": 1, "masters": 2, "master": 2, "msc": 2, "phd": 3, "doctorate": 3}
_DEGREE = re.compile(r"\b(?:degree|qualification|bachelor['’]?s?|b\.?sc\.?|beng|master['’]?s?|msc|meng|ph\.?d\.?)\b", re.I)
_ENGINEERING = re.compile(
    r"\b(?:(?:electrical|electronic|power|mechanical|civil|structural|chemical|aerospace|"
    r"automotive|computer|software)\s+)?engineering\b", re.I
)
_SCIENCE_ALTERNATIVE = re.compile(
    r"\b(?:chemistry|materials(?:\s+science)?|STEM|natural\s+sciences?|"
    r"(?:relevant\s+)?scientific\s+discipline|related\s+(?:discipline|field|subject))\b|"
    r"(?<!computer )(?<!data )\bsciences?\b", re.I
)
_DEGREE_FACT = re.compile(
    r"^(?:Required:\s*)?(?:(?:along\s+with|at\s+least|minimum(?:\s+of)?|"
    r"you\s+(?:(?:will|must|should)\s+)?(?:have|hold|possess)|"
    r"have|hold|holding|possess|(?:we\s+seek\s+)?candidates?\s+"
    r"(?:(?:(?:will|must|should)\s+)?(?:have|hold|possess)|with))\s+)?(?:an?\s+)?"
    r"(?:bachelor['’]?s?|b\.?sc|beng|master['’]?s?|m\.?sc|meng|ph\.?d|dphil|doctor|"
    r"degree\s+in|(?:2[:.]1|2[:.]2|first[- ]class)\s+(?:degree\s+)?in)\b", re.I
)
_COMPLETED_AT_APPLICATION = re.compile(
    r"\b(?:(?:already|currently)\s+(?:hold|have|possess)|"
    r"(?:hold|have|possess)\s+(?:an?\s+)?completed|"
    r"(?:completed|awarded|obtained)\b.{0,80}\b(?:at|before|when|by)\s+(?:the\s+)?application|"
    r"(?:at|before|when|by)\s+(?:the\s+)?application\b.{0,80}\b(?:completed|awarded|obtained))\b", re.I
)
_INCOMPATIBLE_MASTERS = re.compile(
    r"\b(?:finance|accounting|economics|business administration|computer science|data science|"
    r"law|medicine|nursing|psychology|architecture|geotechnical engineering|history|"
    r"literature|linguistics|sociology|social work|fine arts|music|marketing)\b", re.I
)


def _required_degree(clause: str) -> bool:
    # A standalone qualification fact (also outside a labelled Requirements
    # section) is eligibility evidence; narrative degree mentions are not.
    return bool(REQUIRED.search(clause) or _DEGREE_FACT.search(clause))


def _discipline_matches(clause: str) -> bool:
    required = _ENGINEERING.search(clause)
    if not required or not (_DEGREE.search(clause) or re.search(r"\b2[:.]1\s+in\b", clause, re.I)):
        return True
    for alternative in _SCIENCE_ALTERNATIVE.finditer(clause):
        first, second = sorted((required, alternative), key=lambda match: match.start())
        between = clause[first.end():second.start()]
        if (re.search(r"\bor\b|[,/]|\bsuch\s+as\b|\bincluding\b", between, re.I)
                and not re.search(r"\b(?:with|plus|experience|knowledge|background|skills)\b", between, re.I)):
            return True
    candidate = USER_PROFILE.get("education", "")
    if _MASTERS.search(clause) and _pursuing_masters():
        candidate += " " + CURRENT_EDUCATION_DISCIPLINE
    # Compare the named family, rather than treating a Chemistry degree as an
    # engineering qualification. Broad science/related alternatives stay open.
    return bool(re.search(r"\b" + re.escape(required.group()) + r"\b", candidate, re.I))


def _pursuing_masters() -> bool:
    return _LEVELS.get(CURRENT_EDUCATION, 0) == 2 and CURRENT_EDUCATION_STATUS == "in_progress"


def _masters_by_start(job: dict, clause: str) -> bool:
    if not _pursuing_masters() or _COMPLETED_AT_APPLICATION.search(clause):
        return False
    # An ongoing materials MSc does not qualify the candidate for an unrelated
    # named Master's. An explicit relevant scientific alternative stays open.
    discipline = re.search(rf"{_MASTERS.pattern}(?:\s+(?:degree|qualification|level))?\s+(?:in|of)\s+(.+)", clause, re.I)
    field = re.split(r"\b(?:required|expected|essential|mandatory|with|plus|alongside)\b",
                     discipline.group(1), maxsplit=1, flags=re.I)[0] if discipline else ""
    if _INCOMPATIBLE_MASTERS.search(field):
        alternative = re.search(r"\bor\b|/", field, re.I)
        if not (alternative and _SCIENCE_ALTERNATIVE.search(field[alternative.end():])):
            return False
    start = assess_start(job)
    if start.status == "unavailable":
        return False
    if start.status in {"unknown", "confirmation_needed"}:
        add_eligibility_warning(job, "Education: MSc is in progress; confirm completion before the required start date.")
    return True


def education_matches(job: dict) -> bool:
    """Check required degree level and discipline, preserving alternatives/preferences."""
    clear_eligibility_warnings(job, "Education: ")
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
        if _required_degree(clause) and not _discipline_matches(clause):
            return False
        higher_degrees = ([*_MASTERS.finditer(clause)] if ceiling < 2 else [])
        higher_degrees += ([*_PHD.finditer(clause)] if ceiling < 3 else [])
        lower_degrees = [*_BACHELORS.finditer(clause)]
        if ceiling >= 2:
            lower_degrees += [*_MASTERS.finditer(clause)]
        for higher in higher_degrees:
            alternative = False
            alternatives = lower_degrees
            if _PHD.fullmatch(higher.group()) and _MASTERS.search(clause) and _masters_by_start(job, clause):
                alternatives = lower_degrees + list(_MASTERS.finditer(clause))
            for lower in alternatives:
                first, second = sorted((lower, higher), key=lambda match: match.start())
                between = clause[first.end():second.start()].replace("and/or", "or")
                if (re.search(r"\bor\b|/", between, re.I)
                        and not re.search(r"\b(?:with|plus|and)\b", between, re.I)):
                    alternative = True
                    break
            if not alternative and (_required_degree(clause) or re.search(r"\b(?:post[ -]?doc(?:toral)?|phd\s+studentship)\b", clause, re.I)):
                if _MASTERS.fullmatch(higher.group()) and _masters_by_start(job, clause):
                    continue
                return False
    return True
