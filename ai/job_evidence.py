"""Select whole job facts by scoring value, retaining hard eligibility evidence."""

import re
from dataclasses import dataclass

from jobs.requirements_text import (
    NEUTRAL_HEADINGS, PREFERRED_HEADINGS, REQUIRED_HEADINGS, REQUIRED,
    complete_sentences, is_optional, plain_blocks,
)

JOB_EVIDENCE_CHAR_LIMIT = 2400

_HEADINGS = {
    **dict.fromkeys(REQUIRED_HEADINGS, "required"),
    **dict.fromkeys(PREFERRED_HEADINGS, "preferred"),
    **dict.fromkeys(NEUTRAL_HEADINGS, ""),
    "eligibility": "eligibility", "eligibility requirements": "eligibility",
    "responsibilities": "responsibilities", "duties": "responsibilities",
    "what you'll do": "responsibilities", "what you will do": "responsibilities",
    "about the role": "responsibilities", "the role": "responsibilities",
    "additional information": "", "contract type": "contract",
    "benefits": "boilerplate", "about us": "boilerplate", "what we offer": "boilerplate",
    "equal opportunity": "boilerplate", "how to apply": "boilerplate",
}
_DEGREE = re.compile(
    r"\b(?:degree|qualifications?|bachelor['’]?s?|b\.?\s*(?:sc|s|eng)|master['’]?s?|"
    r"m\.?\s*(?:sc|s|eng)|mres|ph\.?\s*d|dphil|doctorate|postgraduate|STEM|discipline)\b", re.I
)
_EXPERIENCE = re.compile(r"\bexperience\b|\b\d+[+-]?\s*years?\b", re.I)
_ELIGIBILITY = re.compile(
    r"\b(?:graduating|graduates?\s+(?:in|only)|graduation|class\s+of|"
    r"right\s+to\s+work|work\s+(?:permission|authori[sz]ation)|visa|sponsorship|"
    r"nationality|citizenship|residen[ct]|security\s+clearance|UK[- ]based|programme\s+starts?)\b", re.I
)
_CONTRACT = re.compile(r"\b(?:contract|fixed[- ]term|FTC|temporary|permanent|full[- ]time|part[- ]time)\b", re.I)
_DUTIES = re.compile(r"\b(?:responsib|analyse|analyze|develop|research|model|synthesi[sz]e|support|deliver|investigate|assess)\w*\b", re.I)


class EvidenceBudgetError(ValueError):
    """Hard eligibility facts cannot safely fit; do not score an incomplete prompt."""


@dataclass(frozen=True)
class _Fact:
    priority: int
    order: int
    text: str
    critical: bool


def _facts(description: str) -> list[_Fact]:
    facts = []
    seen = set()
    context = ""
    for line in plain_blocks(description).splitlines():
        line = re.sub(r"\s+", " ", line).strip(" \t•-")
        if not line:
            continue
        heading, colon, remainder = line.partition(":")
        key = heading.strip().lower().replace("’", "'")
        if key in _HEADINGS:
            context = _HEADINGS[key]
            line = remainder.strip() if colon else ""
            if not line:
                continue
        for sentence in complete_sentences(line):
            sentence = sentence.strip()
            if not sentence:
                continue
            # Local wording wins over a section-wide preferred/required label.
            checked = sentence
            if not REQUIRED.search(sentence) and not is_optional(sentence) and context in {"required", "preferred"}:
                checked = context.title() + ": " + sentence
            optional = is_optional(checked)
            if optional:
                priority, label = 6, "Preferred"
            elif context == "eligibility" or _ELIGIBILITY.search(sentence):
                priority, label = 0, "Eligibility"
            elif _DEGREE.search(sentence):
                priority, label = 1, "Qualifications"
            elif _EXPERIENCE.search(sentence):
                priority, label = 2, "Experience"
            elif context == "contract" or _CONTRACT.search(sentence):
                priority, label = 3, "Contract"
            elif context == "required" or REQUIRED.search(sentence):
                priority, label = 4, "Required skills"
            elif context == "responsibilities" or _DUTIES.search(sentence):
                priority, label = 5, "Responsibilities"
            elif context == "boilerplate":
                continue
            else:
                priority, label = 7, "Role"
            text = f"{label}: {checked.rstrip('.')}."
            canonical = checked.casefold()
            if canonical not in seen:
                facts.append(_Fact(priority, len(facts), text, priority <= 3))
                seen.add(canonical)
    return facts


def select_job_evidence(description: str, limit: int = JOB_EVIDENCE_CHAR_LIMIT) -> str:
    """Bound the excerpt without cutting facts or silently losing eligibility.

    Mandatory eligibility/qualification/experience/contract facts are selected
    first across the complete JD. Duties and preferences fill the remaining
    budget as complete sentences/list items. Oversized critical facts fail
    before an API request, rather than producing an unsupported high score.
    """
    ranked = sorted(_facts(description), key=lambda fact: (fact.priority, fact.order))
    selected = [fact for fact in ranked if fact.critical]

    def render():
        return "\n".join(fact.text for fact in sorted(selected, key=lambda fact: (fact.priority, fact.order)))

    if len(render()) > limit:
        raise EvidenceBudgetError(f"Complete eligibility facts exceed the {limit}-character job evidence budget")
    for fact in ranked:
        if fact.critical:
            continue
        selected.append(fact)
        if len(render()) > limit:
            selected.pop()
    return render()
