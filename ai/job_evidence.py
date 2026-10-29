"""Select whole job facts by scoring value, retaining hard eligibility evidence."""

import re
from dataclasses import dataclass

from jobs.requirements_text import (
    NEUTRAL_HEADINGS, PREFERRED_HEADINGS, REQUIRED_HEADINGS, REQUIRED,
    complete_sentences, is_optional,
)
from jobs.student_filter import requires_current_student
from jobs.education_filter import _required_degree
from jobs.experience_filter import _extract_year_requirements
from jobs.availability_filter import has_start_evidence, normalise_start_lines

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
    "what we offer you": "boilerplate", "next steps": "boilerplate",
    "different people, shared values": "boilerplate",
    "is this role right for you?": "required", "about you": "required",
    "the opportunity": "responsibilities", "recent projects include": "responsibilities",
    "typical project engagements include": "responsibilities",
}
_DEGREE = re.compile(
    r"\b(?:degree|qualifications?|bachelor['’]?s?|b\.?\s*(?:sc|s|eng)|master['’]?s?|"
    r"m(?!\.?\s*s\.?\s*office\b)\.?\s*(?:sc|s|eng)|mres|ph\.?\s*d|dphil|doctorate|postgraduate|STEM|discipline)\b", re.I
)
_EXPERIENCE = re.compile(r"\bexperience\b|\b\d+[+-]?\s*years?\b", re.I)
_ELIGIBILITY = re.compile(
    r"\b(?:graduating|graduated|graduates?\s+(?:in|only)|graduation|class\s+of|"
    r"right\s+to\s+work|working\s+rights|work\s+(?:permission|authori[sz]ation)|visa|sponsorship|"
    r"nationality|citizenship|residen[ct]|security\s+clearance|UK[- ]based|programme\s+starts?)\b", re.I
)
_CONTRACT = re.compile(r"\b(?:contract|placements?|fixed[- ]term|FTC|temporary|permanent|full[- ]time|part[- ]time)\b", re.I)
_DUTIES = re.compile(r"\b(?:responsib|analyse|analyze|develop|research|model|synthesi[sz]e|support|deliver|investigate|assess)\w*\b", re.I)
_BOILERPLATE = re.compile(
    r"\b(?:equal opportunity|do not discriminate|regardless of|degree of flexibility|"
    r"match your experience with the correct salary)\b", re.I
)
_EXPERIENCE_SCOPE = re.compile(
    r"\b(?:previous|prior|professional|industry|commercial|work)\s+experience\b|"
    r"\b(?:no more than|up to|at most|maximum(?: of)?)\s+\d+\s+months?\b", re.I
)


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
    for line in normalise_start_lines(description).splitlines():
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
            student = requires_current_student(checked)
            degree = bool(_DEGREE.search(sentence))
            experience = bool(_EXPERIENCE.search(sentence) and (
                context in {"required", "eligibility"} or REQUIRED.search(sentence)
                or _EXPERIENCE_SCOPE.search(sentence)
                or _extract_year_requirements(sentence)[0] is not None))
            start_evidence = has_start_evidence(sentence)
            eligibility = bool(_ELIGIBILITY.search(sentence) or start_evidence)
            contract = bool(_CONTRACT.search(sentence))
            # Benefits and EEO text can contain "degree", "experience",
            # "nationality" and "permanent" without imposing eligibility.
            # Preserve explicit requirements even under a misplaced heading.
            explicit = bool(student or start_evidence or (degree and _required_degree(sentence))
                            or ((experience or eligibility or contract) and REQUIRED.search(sentence)))
            if (context == "boilerplate" or _BOILERPLATE.search(sentence)) and not explicit:
                continue
            if optional:
                priority, label = 6, "Preferred"
            elif student or eligibility:
                priority, label = 0, "Eligibility"
            elif degree:
                priority, label = 1, "Qualifications"
            elif experience:
                priority, label = 2, "Experience"
            elif context == "contract" or contract:
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
