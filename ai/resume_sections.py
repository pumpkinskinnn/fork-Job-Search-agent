"""Shared CV headings for scoring and document generation."""

import re

HEADING = re.compile(
    r"^(SUMMARY|PROFILE|PERSONAL PROFILE|CANDIDATE PROFILE|SKILLS|TECHNICAL SKILLS|EXPERIENCE|"
    r"WORK EXPERIENCE|PROFESSIONAL EXPERIENCE|RESEARCH EXPERIENCE|"
    r"(?:PROJECTS?\s*(?:&|AND)\s*RESEARCH|RESEARCH\s*(?:&|AND)\s*PROJECTS?)\s+EXPERIENCE|"
    r"PROJECT EXPERIENCE|ACADEMIC EXPERIENCE|INTERNSHIP EXPERIENCE|INTERNSHIPS?|"
    r"PERSONAL PROJECTS?|RESEARCH PROJECTS?|ACADEMIC PROJECTS?|PROJECTS?|"
    r"LEADERSHIP AND ACTIVITIES|LEADERSHIP\s*&\s*ACTIVITIES|LEADERSHIP|ACTIVITIES|LANGUAGES|"
    r"EDUCATION|CERTIFICATIONS|PUBLICATIONS|AWARDS|INTERESTS|REFERENCES)\s*:?$", re.I
)


def split_resume_sections(text: str) -> dict[str, list[str]]:
    sections = {"_header": []}
    current = "_header"
    for raw in text.splitlines():
        line = raw.rstrip()
        match = HEADING.fullmatch(line.strip())
        if match:
            heading = match.group(1).upper()
            if "EXPERIENCE" in heading or heading in {"INTERNSHIP", "INTERNSHIPS"}:
                current = "EXPERIENCE"
            elif "LEADERSHIP" in heading or heading == "ACTIVITIES":
                current = "LEADERSHIP"
            elif "PROJECT" in heading:
                current = "PROJECTS"
            elif "SKILLS" in heading:
                current = "SKILLS"
            elif "PROFILE" in heading:
                current = "SUMMARY"
            else:
                current = heading
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return sections


def parse_experience_entries(lines: list[str]) -> list[dict]:
    """Parse whole entries, retaining institution/date metadata before the bullets."""
    entries = []
    current = None
    for line in lines:
        text = line.strip()
        if not text:
            continue
        bullet = re.match(r"^[•\-*]\s+", text)
        if bullet:
            if current is None:
                current = {"header": "", "subheader": "", "bullets": []}
                entries.append(current)
            current["bullets"].append(text[bullet.end():])
        elif current is None or current["bullets"]:
            current = {"header": text, "subheader": "", "bullets": []}
            entries.append(current)
        else:
            current["subheader"] = " | ".join(filter(None, (current["subheader"], text)))
    return entries
