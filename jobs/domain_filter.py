"""Broad STEM titles first; generic titles need domain evidence when available."""

import re

from bs4 import BeautifulSoup
from config import FILTER_BY_DOMAIN

DOMAIN = re.compile(
    r"\b(?:energy|renewables?|renewable|sustainab\w*|materials?|batter(?:y|ies)|"
    r"electrochem\w*|chemistry|chemist|chemical|cleantech|clean[ -](?:technology|tech)|"
    r"net[ -]zero|low[ -]carbon|decarbon\w*|climate|photocatal\w*|"
    r"solar|photovoltaic\w*|hydrogen|semiconductor\w*|functional materials|"
    r"environmental|polymer\w*|nano(?:materials?|science|technology)|optoelectronic\w*)\b", re.I
)
IRRELEVANT_TITLE = re.compile(
    r"\b(?:software|developer|full[ -]stack|marketing|sales|HR|human resources|"
    r"recruitment|recruiter|accountant|accounting|retail|hospitality|legal|"
    r"customer service|graphic designer)\b", re.I
)
EARLY_CAREER = re.compile(r"\b(?:graduate|junior|trainee|entry[ -]level|new[ -]grad)\b", re.I)
STEM_TITLE = re.compile(
    r"\b(?:scientist|analyst|consultant|engineer|researcher|chemist|technician)\b|"
    r"\b(?:research|laboratory|lab)\s+(?:assistant|associate)\b", re.I
)
SCHEME = re.compile(r"\b(?:programme|program|scheme)\b", re.I)


def broad_stem_title_matches(title: str) -> bool:
    if IRRELEVANT_TITLE.search(title):
        return False
    return bool(DOMAIN.search(title) or STEM_TITLE.search(title)
                or (EARLY_CAREER.search(title) and SCHEME.search(title)))


def description_available(job: dict) -> bool:
    description = (job.get("description") or "").strip()
    return bool(description and description != "Job description unavailable.")


def domain_matches(job: dict) -> bool:
    if not FILTER_BY_DOMAIN:
        return True
    title = job.get("title") or ""
    if IRRELEVANT_TITLE.search(title):
        return False
    if DOMAIN.search(title):
        return True
    # Unknown descriptions stay visible, with an explicit uncertainty indicator.
    if not description_available(job):
        return True
    text = BeautifulSoup(job["description"], "lxml").get_text(" ", strip=True)
    return bool(DOMAIN.search(text))
