"""Reject explicit twelve-month employment contracts, not training or experience."""

import re

from config import REJECT_12_MONTH_CONTRACT
from jobs.requirements_text import qualification_clauses

_DURATION = r"(?:(?:12|twelve)[ -]+months?|(?:one|1)[ -]+year)"
_CONTRACT = r"(?:fixed[ -]+term(?:\s+contract)?|ftc|temporary(?:\s+contract)?|contract)"
_TWELVE_MONTH_CONTRACT = re.compile(
    rf"\b(?:{_DURATION}\s+(?:(?:full[ -]time|temporary|paid)\s+)?{_CONTRACT}|"
    rf"{_CONTRACT}\s*(?:(?:for|of|lasting|duration(?:\s+of)?|length(?:\s+of)?|is)\s*)?"
    rf"[:(-]?\s*(?:a\s+)?{_DURATION})\b", re.I
)


def contract_matches(job: dict) -> bool:
    if not REJECT_12_MONTH_CONTRACT:
        return True
    text = f"{job.get('title') or ''}\n{job.get('description') or ''}"
    return not any(_TWELVE_MONTH_CONTRACT.search(clause) for clause in qualification_clauses(text))
