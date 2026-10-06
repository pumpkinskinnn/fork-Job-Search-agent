import re

from config import EXPERIENCE_MAX, FILTER_BY_EXPERIENCE
from jobs.requirements_text import NEGATED, REQUIRED, is_optional, qualification_clauses

_TOO_SENIOR = re.compile(
    r"\b(?:senior|sr\.?|lead|principal|staff|manager|director|head\s+of|"
    r"vice\s+president|vp|chief|distinguished|architect)\b|"
    r"\b(?:engineer|sde)[\s-]*(?:iii|iv|v|[3-9])\b|\bl[5-9]\b", re.I
)
_EXPERIENCE = re.compile(r"\bexperience\b", re.I)
_PROFESSIONAL = re.compile(
    r"\b(?:professional|industry|industrial|commercial|consultancy|consulting|"
    r"full[ -]time|employment|work\s+experience)\b|"
    r"\bexperience\s+(?:in|within|of)\s+(?:the\s+)?energy\s+(?:industry|sector)\b", re.I
)
_ACADEMIC = re.compile(r"\b(?:academic|university|research|projects?|placements?|internships?)\b", re.I)
_ACADEMIC_ALTERNATIVE = re.compile(
    r"\b(?:or|including|includes?|through|via|from)\b.{0,60}\b"
    r"(?:academic|university|research|projects?|placements?|internships?)\b|"
    r"\b(?:academic|university|research|projects?|placements?|internships?)\b.{0,70}"
    r"\b(?:count|counts|accepted|acceptable|welcomed|qualify|qualifies|equivalent)\b", re.I
)
_YEAR = re.compile(
    r"\b(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|fifteen)"
    r"\s*(?:(?:-|to|–|—)\s*(\d+)\s*)?(?:\+|plus\s*)?\s*(?:years?|yrs?)\b", re.I
)
_WORD_YEARS = dict(zip(
    ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "fifteen"),
    (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15),
))


def _extract_year_requirements(text: str) -> tuple[int | None, int | None]:
    """Extract experience years, including zero-minimum ranges; ignore preferences."""
    mins, maxs = [], []
    for clause in qualification_clauses(text):
        if not _EXPERIENCE.search(clause) or is_optional(clause) or NEGATED.search(clause):
            continue
        for match in _YEAR.finditer(clause):
            window = clause[max(0, match.start() - 35):match.end() + 65]
            if not _EXPERIENCE.search(window):
                continue
            token = match.group(1).lower()
            low = int(token) if token.isdigit() else _WORD_YEARS[token]
            high = int(match.group(2)) if match.group(2) else None
            if 0 <= low <= 40 and (high is None or low <= high <= 40):
                mins.append(low)
                if high is not None:
                    maxs.append(high)
    return (max(mins) if mins else None, max(maxs) if maxs else None)


def requires_professional_experience(job: dict, max_years: int = 0) -> bool:
    """Reject clear unmet requirements, keeping preferences and academic alternatives.

    Unqualified/ambiguous experience is retained for AI assessment. A quantitative
    industry requirement is explicit even if it omits the word 'required'.
    """
    text = f"{job.get('title') or ''}\n{job.get('description') or ''}"
    for clause in qualification_clauses(text):
        if not _EXPERIENCE.search(clause) or is_optional(clause) or NEGATED.search(clause):
            continue
        professional = bool(_PROFESSIONAL.search(clause))
        if _ACADEMIC.search(clause) and (not professional or _ACADEMIC_ALTERNATIVE.search(clause)):
            continue
        minimum, _ = _extract_year_requirements(clause)
        if minimum is not None:
            if minimum > max_years and (professional or REQUIRED.search(clause)):
                return True
            continue  # A range starting at zero does not require prior experience.
        if professional and REQUIRED.search(clause) and max_years == 0:
            return True
    return False


def is_senior_title(title: str) -> bool:
    return bool(_TOO_SENIOR.search(re.sub(r"[_|/]+", " ", title or "")))


def experience_matches(job: dict) -> bool:
    if not FILTER_BY_EXPERIENCE:
        return True
    if is_senior_title(job.get("title") or ""):
        return False
    return not requires_professional_experience(job, EXPERIENCE_MAX)
