"""Assess explicit employment starts, independently of posting/graduation dates."""

import calendar
from dataclasses import dataclass
from datetime import date
import re

from config import CANDIDATE_AVAILABLE_FROM
from jobs.requirements_text import is_optional, plain_blocks, qualification_clauses

_MONTHS = {name.lower(): index for index in range(1, 13)
           for name in (calendar.month_name[index], calendar.month_abbr[index])}
_MONTH = "(?:" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?"
_DATE = (rf"(?:20\d{{2}}-\d{{2}}-\d{{2}}|\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH}\s+20\d{{2}}|"
         rf"{_MONTH}\s+\d{{1,2}}(?:st|nd|rd|th)?[,]?\s+20\d{{2}}|{_MONTH}\s+20\d{{2}}|"
         r"(?:autumn|fall|spring|summer|winter)\s+20\d{2})")
_START = r"(?:start(?:s|ing)?(?:\s+dates?)?|commenc(?:e|es|ing|ement)(?:\s+date)?|begins?|beginning)"
_START_DATE = re.compile(
    rf"\b{_START}\s*(?:this\s+(?:opportunity|role|position)\s+)?(?:[:=-]\s*)?"
    rf"(?:(?:will\s+be|is|on|in|from|of)\s+)*"
    rf"(?P<after>{_DATE})\b|\b(?P<before>{_DATE})\s+(?:fixed\s+)?{_START}\b", re.I)
_IMMEDIATE = re.compile(r"\b(?:immediate\s+start|start\s+immediately|start\s+ASAP|"
                        r"(?:start|starting)\s+as\s+soon\s+as\s+possible)\b", re.I)
_FLEXIBLE = re.compile(r"\b(?:flexible|negotiable|by arrangement|to be agreed)\b", re.I)


@dataclass(frozen=True)
class StartAssessment:
    status: str  # eligible, unavailable, confirmation_needed, unknown
    reason: str = ""


def add_eligibility_warning(job: dict, warning: str) -> None:
    warnings = job.setdefault("eligibility_warnings", [])
    if warning not in warnings:
        warnings.append(warning)


def clear_eligibility_warnings(job: dict, prefix: str) -> None:
    if "eligibility_warnings" in job:
        job["eligibility_warnings"] = [text for text in job["eligibility_warnings"] if not text.startswith(prefix)]


def has_start_evidence(text: str) -> bool:
    return bool(_START_DATE.search(text) or _IMMEDIATE.search(text))


def normalise_start_lines(text: str) -> str:
    """Keep a labelled start and its next-line date together as one fact."""
    return re.sub(rf"(\b{_START}[^\n.?!]{{0,65}})\n\s*(?={_DATE}\b)", r"\1 ", plain_blocks(text), flags=re.I)


def _window(value: str) -> tuple[date, date]:
    value = re.sub(r"(\d)(?:st|nd|rd|th)\b", r"\1", value.lower()).replace(",", "").replace(".", "")
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
        exact = date.fromisoformat(value)
        return exact, exact
    parts = value.split()
    year = int(parts[-1])
    seasons = {"autumn": (9, 11), "fall": (9, 11), "spring": (3, 5), "summer": (6, 8), "winter": (12, 2)}
    if parts[0] in seasons:
        first, last = seasons[parts[0]]
        end_year = year + (last < first)
        return date(year, first, 1), date(end_year, last, calendar.monthrange(end_year, last)[1])
    if len(parts) == 3:
        month = _MONTHS[parts[1] if parts[0].isdigit() else parts[0]]
        day = int(parts[0] if parts[0].isdigit() else parts[1])
        exact = date(year, month, day)
        return exact, exact
    month = _MONTHS[parts[0]]
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def assess_start(job: dict) -> StartAssessment:
    if not CANDIDATE_AVAILABLE_FROM:
        return StartAssessment("unknown")
    available = date.fromisoformat(CANDIDATE_AVAILABLE_FROM)
    text = f"{job.get('title') or ''}\n{job.get('description') or ''}"
    if job.get("start_date"):
        text += f"\nStart date: {job['start_date']}"
    assessments = []
    for clause in qualification_clauses(normalise_start_lines(text)):
        flexible = bool(_FLEXIBLE.search(clause) or is_optional(clause))
        if _IMMEDIATE.search(clause) and date.today() < available:
            assessments.append(StartAssessment("confirmation_needed" if flexible else "unavailable",
                                              "Immediate start is before full-time availability " + available.isoformat()))
        for match in _START_DATE.finditer(clause):
            value = match.group("after") or match.group("before")
            try:
                earliest, latest = _window(value)
            except (ValueError, KeyError):
                assessments.append(StartAssessment("confirmation_needed", "Confirm invalid or unclear start date: " + value))
                continue
            if flexible or earliest < available <= latest:
                result = StartAssessment("confirmation_needed", f"Confirm start date '{value}' against availability {available.isoformat()}")
            elif latest < available:
                result = StartAssessment("unavailable", f"Start date '{value}' is before availability {available.isoformat()}")
            else:
                result = StartAssessment("eligible")
            assessments.append(result)
    for status in ("unavailable", "confirmation_needed", "eligible"):
        for result in assessments:
            if result.status == status:
                return result
    return StartAssessment("unknown")


def availability_matches(job: dict) -> bool:
    clear_eligibility_warnings(job, "Availability: ")
    result = assess_start(job)
    if result.status == "confirmation_needed":
        add_eligibility_warning(job, "Availability: " + result.reason)
    return result.status != "unavailable"
