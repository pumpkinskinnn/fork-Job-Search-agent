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
    r"\s*(?:(?:-|to|–|—)\s*(\d+)\s*)?(?:\+|plus\s*)?\s*[- ]?\s*(?:years?|yrs?)\b", re.I
)
_WORD_YEARS = dict(zip(
    ("one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "fifteen"),
    (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 15),
))
_UPPER_BOUND = re.compile(r"\b(?:no\s+more\s+than|not\s+more\s+than|up\s+to|at\s+most|maximum(?:\s+of)?)\s*$", re.I)
_PROGRAMME = r"(?:(?:graduate|development|training|rotational|rotation|induction)\s+)*(?:program(?:me)?|scheme)|training\b"
_PROFESSIONAL_EXPERIENCE = re.compile(
    r"\b(?:professional|industry|industrial|commercial|consultancy|consulting|work)"
    r"(?:\s+[\w'-]+){0,3}\s+experience\b|"
    r"\bexperience\s+(?:in|within|of)\s+(?:the\s+)?(?:industry|energy\s+(?:industry|sector))\b", re.I
)


def _programme_duration(clause: str, match: re.Match) -> bool:
    """Associate a duration with its programme, never with nearby career benefits."""
    before, after = clause[:match.start()], clause[match.end():]
    return bool(re.match(rf"\s*[- ]?\s*(?:{_PROGRAMME})\b", after, re.I)
                or re.search(rf"\b(?:{_PROGRAMME})\s+(?:lasting|lasts?|runs?\s+for|duration(?:\s+of)?|of|for)\s*$", before, re.I))


def _experience_years(clause: str):
    for match in _YEAR.finditer(clause):
        if _programme_duration(clause, match):
            continue
        window = clause[max(0, match.start() - 35):match.end() + 65]
        if not _EXPERIENCE.search(window) and not (
            _PROFESSIONAL.search(window) and re.search(r"\b(?:role|working|in|within)\b", window, re.I)
        ):
            continue
        token = match.group(1).lower()
        low = int(token) if token.isdigit() else _WORD_YEARS[token]
        high = int(match.group(2)) if match.group(2) else None
        if not (0 <= low <= 40 and (high is None or low <= high <= 40)):
            continue
        if _UPPER_BOUND.search(clause[:match.start()]):
            yield 0, high if high is not None else low
        else:
            yield low, high


def _extract_year_requirements(text: str) -> tuple[int | None, int | None]:
    """Extract experience years, including zero-minimum ranges; ignore preferences."""
    mins, maxs = [], []
    for clause in qualification_clauses(text):
        if is_optional(clause) or NEGATED.search(clause):
            continue
        for low, high in _experience_years(clause):
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
        if is_optional(clause) or NEGATED.search(clause):
            continue
        professional = bool(_PROFESSIONAL.search(clause))
        if _ACADEMIC.search(clause) and (not professional or _ACADEMIC_ALTERNATIVE.search(clause)):
            continue
        minimum, _ = _extract_year_requirements(clause)
        if minimum is not None:
            if minimum > max_years and (professional or REQUIRED.search(clause)):
                return True
            continue  # A range starting at zero does not require prior experience.
        # A programme duration next to "experience and professional network
        # needed" is a future benefit, not a candidate experience requirement.
        duration = any(_programme_duration(clause, match) for match in _YEAR.finditer(clause))
        if duration and not _PROFESSIONAL_EXPERIENCE.search(clause):
            continue
        if (duration and re.search(r"\b(?:build|develop|gain|provide|offer|acquire)\b.{0,80}\bexperience\b", clause, re.I)
                and not re.search(r"\b(?:must|requires?|required|essential|mandatory|previous|prior|proven)\b",
                                  clause.removeprefix("Required: "), re.I)):
            continue  # Experience the programme will teach, rather than prior employment.
        if _EXPERIENCE.search(clause) and professional and REQUIRED.search(clause) and max_years == 0:
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
