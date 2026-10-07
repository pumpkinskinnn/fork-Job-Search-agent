"""Keep qualification statements separate so preferences cannot mask requirements."""

import re

from bs4 import BeautifulSoup

OPTIONAL = re.compile(
    r"\b(?:preferred|preferably|desirable|desired|advantageous|beneficial|optional|"
    r"nice\s+to\s+have|a\s+plus|bonus|ideally|not\s+essential|not\s+required)\b", re.I
)
REQUIRED = re.compile(
    r"\b(?:required|require[sd]?|requiring|must|essential|mandatory|need(?:ed|s)?|"
    r"minimum|at\s+least)\b", re.I
)
NEGATED = re.compile(
    r"\b(?:not\s+(?:required|essential|necessary|mandatory|needed)|"
    r"no\s+(?:(?:previous|prior|professional|industry|work|related|relevant|commercial)\s+)*experience\s+"
    r"(?:is\s+)?(?:required|needed|necessary))\b", re.I
)
REQUIRED_HEADINGS = {
    "essential", "essential criteria", "requirements", "qualifications", "required",
    "minimum requirements", "must have", "eligibility", "eligibility requirements",
    "skills and requirements", "what you'll need", "what you will need", "what you'll have",
    "what you will have", "what we're looking for", "what we are looking for",
    "we're looking for", "your qualifications", "required qualifications", "education requirements",
    "required skills", "required experience", "education", "what you'll bring", "what you will bring",
}
PREFERRED_HEADINGS = {
    "preferred", "desirable", "desirable criteria", "nice to have", "optional",
    "preferred qualifications", "preferred skills", "desirable qualifications", "desirable skills",
}
NEUTRAL_HEADINGS = {
    "responsibilities", "benefits", "about us", "about the role", "duties", "what you'll do",
    "what you will do", "the role", "additional information", "graduate development programme",
    "training", "what we offer",
}
_ABBREVIATION_END = re.compile(r"(?:\b[A-Za-z]|\b[BM]\.(?:Sc|S|Eng)|\bPh\.D)\.$", re.I)


def complete_sentences(text: str) -> list[str]:
    """Split sentence/semicolon boundaries without splitting degree abbreviations."""
    parts, start = [], 0
    for match in re.finditer(r";|\.(?=\s|$)", text):
        if match.group() == "." and _ABBREVIATION_END.search(text[:match.end()]):
            continue
        parts.append(text[start:match.start()])
        start = match.end()
    parts.append(text[start:])
    return [part.strip() for part in parts if part.strip()]


def plain_blocks(text: str) -> str:
    soup = BeautifulSoup(text or "", "lxml")
    for tag in soup.find_all(["p", "li", "div", "h1", "h2", "h3", "h4", "br"]):
        tag.insert_before("\n")
        tag.insert_after("\n")
    return re.sub(r"[‐‑‒–—]", "-", soup.get_text(separator=" ").replace("\u00a0", " "))


def qualification_clauses(text: str) -> list[str]:
    """Preserve list/section context, inline degree tags and dotted abbreviations."""
    clauses = []
    context = ""

    def append_clause(clause: str) -> None:
        clause = clause.strip()
        if clause:
            # A local preference overrides a generic Requirements heading;
            # a local requirement also overrides a Desirable heading.
            prefix = "" if REQUIRED.search(clause) or OPTIONAL.search(clause) else context
            clauses.append(prefix + clause)

    for line in plain_blocks(text).splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if not line:
            continue
        head, colon, rest = line.partition(":")
        heading = head.strip(" •-").lower().replace("’", "'")
        if heading in REQUIRED_HEADINGS:
            context = "Required: "
        elif heading in PREFERRED_HEADINGS:
            context = "Preferred: "
        elif heading in NEUTRAL_HEADINGS:
            context = ""
        else:
            heading = ""
        if heading:
            line = rest.strip() if colon else ""
            if not line:
                continue
        for sentence in complete_sentences(line):
            parts = re.split(r"(?:,\s*)?\b(?:but|however|whereas)\b\s+", sentence, flags=re.I)
            for part in parts:
                chunks = re.split(
                    r"(,|\s+and\s+(?=(?:(?:previous|prior|relevant)\s+)?"
                    r"(?:professional|industry|commercial|consultancy|master|MSc|PhD|bachelor|BSc)\b))",
                    part, flags=re.I,
                )
                current = chunks[0]
                for separator, chunk in zip(chunks[1::2], chunks[2::2]):
                    continuation = re.match(r"\s*(?:including|through|via|or|such\s+as)\b", chunk, re.I)
                    if (REQUIRED.search(current) or OPTIONAL.search(current)) and not continuation:
                        append_clause(current)
                        current = chunk
                    else:
                        current += separator + chunk
                if current.strip():
                    append_clause(current)
    return clauses


def is_optional(clause: str) -> bool:
    mandatory = REQUIRED.search(NEGATED.sub("", clause))
    return bool((OPTIONAL.search(clause) or NEGATED.search(clause)) and not mandatory)
