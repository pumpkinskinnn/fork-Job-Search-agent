"""Keep graduate-open opportunities; reject eligibility limited to enrolled students."""

import re

from jobs.requirements_text import REQUIRED, is_optional, qualification_clauses

_ENROLMENT = re.compile(
    r"\b(?:currently\s+(?:studying|enrolled|enroled|registered)|"
    r"current\s+(?:(?:university|college|undergraduate)\s+)?students?|"
    r"penultimate[ -]year\s+(?:(?:university|undergraduate)\s+)?students?|"
    r"(?:must\s+)?(?:remain|stay)\s+(?:enrolled|enroled|registered)|"
    r"(?:return|returning)\s+to\s+(?:university|college)\s+"
    r"(?:after|following)\s+(?:the\s+)?placement)\b", re.I
)
_PLACEMENT = re.compile(
    r"\b(?:industrial\s+placements?|student\s+placements?|"
    r"placement[ -]year(?:\s+students?)?|sandwich[ -]year|year\s+in\s+industry)\b", re.I
)
_GRADUATE_ALTERNATIVE = re.compile(
    r"\b(?:students?\s*(?:and\s*/\s*or|and|or|/|&)\s*(?:(?:recent|new)\s+)?graduates?|"
    r"graduates?\s*(?:and\s*/\s*or|and|or|/|&)\s*(?:(?:current|university)\s+)*students?|"
    r"(?:open|available)\s+to\s+(?:(?:recent|new)\s+)?graduates?|"
    r"graduates?\s+(?:are\s+)?(?:welcome|eligible|accepted))\b", re.I
)


def requires_current_student(clause: str) -> bool:
    """Recognise role eligibility, preserving local preferences and alternatives."""
    return bool(not is_optional(clause) and not _GRADUATE_ALTERNATIVE.search(clause)
                and (_ENROLMENT.search(clause) or _PLACEMENT.search(clause)))


def student_matches(job: dict) -> bool:
    text = f"{job.get('title') or ''}\n{job.get('description') or ''}"
    clauses = qualification_clauses(text)
    graduates_welcome = any(not is_optional(clause) and _GRADUATE_ALTERNATIVE.search(clause)
                            for clause in clauses)
    for clause in clauses:
        if not requires_current_student(clause):
            continue
        # A placement title alone does not override an explicit invitation to
        # graduates. An independent enrolment requirement still does.
        if graduates_welcome and not _ENROLMENT.search(clause) and not REQUIRED.search(clause):
            continue
        return False
    return True
