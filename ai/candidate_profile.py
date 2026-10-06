"""Deterministic, bounded CV evidence selection without AI calls or text slicing."""

from dataclasses import dataclass, field
import re

from ai.resume_sections import parse_experience_entries, split_resume_sections

PROFILE_CHAR_LIMIT = 4800

_MODULE_TOPICS = re.compile(
    r"energy|electrochem|materials|data science|sustainability|project management", re.I
)
_SKILL_TOPICS = re.compile(
    r"electrochem|XRD|SEM|NMR|FTIR|UV-Vis|GPC|SEC|glovebox|materials synthesis|"
    r"Excel|Origin|data analysis", re.I
)
_EVIDENCE_TOPICS = re.compile(
    r"\d[\d,]*|energy|electrochem\w*|materials?|synth\w*|surface|interfac\w*|"
    r"wettability|XRD|X-ray diffraction|photocatal\w*|electron.transfer|"
    r"sustainab\w*|polym\w*|RAFT|GPC|SEC|microscopy|data|report|present\w*|"
    r"technical|communicat\w*", re.I
)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lstrip("•-* ")


def _sentence(text: str) -> str:
    text = _clean(text)
    return text if text.endswith((".", "!", "?")) else text + "."


@dataclass
class _Block:
    label: str
    items: list[str]
    inline: bool = False
    required: bool = False
    selected: set[int] = field(default_factory=set)

    def render(self) -> str:
        items = [item for index, item in enumerate(self.items) if index in self.selected]
        if not items:
            return _sentence(self.label) if self.required else ""
        if self.inline:
            return _sentence(f"{self.label}: " + "; ".join(items))
        return f"{self.label}:\n" + "\n".join("- " + _sentence(item) for item in items)


def _skills(lines: list[str]) -> list[tuple[str, list[str]]]:
    """Keep named categories and whole skill names, including multiline lists."""
    groups = []
    for raw in lines:
        text = _clean(raw)
        if not text:
            continue
        if ":" in text:
            name, text = text.split(":", 1)
            groups.append((name.strip(), []))
        elif not groups:
            groups.append(("Other skills", []))
        groups[-1][1].extend(item.strip() for item in text.split(",") if item.strip())
    return groups


def build_candidate_profile(resume: str, candidate: dict, limit: int = PROFILE_CHAR_LIMIT) -> str:
    """Reserve all entry identities and core qualifications; fill with whole facts.

    Lower-priority complete bullets/modules/skills can be omitted to fit the
    budget. No project identity or role scope is silently cut. If mandatory
    identity/scope/qualification data cannot fit, fail clearly instead of sending
    a misleading partial profile. Selection is extractive, not generated prose.
    """
    sections = split_resume_sections(resume)
    blocks = []
    optional = []
    research = []

    def add(label, items, *, inline=False, required=False, mandatory=()):
        block = _Block(label, [_clean(item) for item in items if _clean(item)], inline, required)
        block.selected.update(mandatory)
        blocks.append(block)
        return block

    def render():
        return "\n".join(text for block in blocks if (text := block.render()))

    overview, areas = [], []
    in_areas = False
    for raw in sections.get("SUMMARY", []):
        text = _clean(raw)
        if re.match(r"^Target areas\s*:", text, re.I):
            in_areas = True
            text = text.split(":", 1)[1].strip()
        if text:
            (areas if in_areas else overview).append(text)
    intro = overview[:1] or [candidate.get("education") or "Graduate candidate"]
    add("Candidate", intro, inline=True, mandatory=range(len(intro)))
    background = (
        f"{candidate.get('location') or 'Location unspecified'}; "
        f"{candidate.get('experience_years', 0)} years of full-time professional experience; "
        "academic projects/internships are not professional industry employment"
    )
    add("Practical/background", [background], inline=True, mandatory=(0,))
    if areas:
        add("Target areas", areas, inline=True, mandatory=range(len(areas)))
    roles = candidate.get("target_roles") or []
    if roles:
        add("Target roles", roles, inline=True, mandatory=range(len(roles)))

    education, modules = [], []
    in_modules = False
    for raw in sections.get("EDUCATION", []):
        text = _clean(raw)
        if re.match(r"^(?:Relevant )?modules\s*:", text, re.I):
            in_modules = True
            text = text.split(":", 1)[1].strip()
        if text:
            (modules if in_modules else education).append(text)
    if education:
        add("Education", education, inline=True, mandatory=range(len(education)))
    if modules:
        core = [i for i, text in enumerate(modules) if _MODULE_TOPICS.search(text)]
        block = add("Modules", modules, inline=True, mandatory=core)
        optional.extend((40, block, i) for i in range(len(modules)) if i not in core)

    for name, items in _skills(sections.get("SKILLS", [])):
        if not items:
            continue
        core = [i for i, text in enumerate(items) if _SKILL_TOPICS.search(text)] or [0]
        block = add(f"Skills / {name}", items, inline=True, mandatory=core)
        optional.extend((50, block, i) for i in range(len(items)) if i not in core)

    entries = parse_experience_entries(sections.get("EXPERIENCE", []))
    entries += parse_experience_entries(sections.get("PROJECTS", []))
    if entries:
        add("Research/project/internship evidence (retain the stated academic/work context)", [], required=True)
    for entry in entries:
        identity = " | ".join(filter(None, (entry["header"], entry["subheader"])))
        # Normalise scientific notation, without rewriting or inventing facts.
        evidence = [re.sub(r"X-ray diffraction", "XRD", text, flags=re.I) for text in entry["bullets"]]
        block = add(identity or "Untitled research/project entry", evidence, required=True)
        research.append(block)
        for i, text in enumerate(evidence):
            score = len(_EVIDENCE_TOPICS.findall(text))
            if score:
                optional.append((100 + score, block, i))

    # Leadership and languages remain useful transferable evidence, but never
    # enter the research/professional experience list.
    for entry in parse_experience_entries(sections.get("LEADERSHIP", [])):
        identity = " | ".join(filter(None, (entry["header"], entry["subheader"])))
        block = add(f"Leadership/activities (separate): {identity}", entry["bullets"])
        optional.extend((20, block, i) for i in range(len(block.items)))
    languages = [_clean(line) for line in sections.get("LANGUAGES", []) if _clean(line)]
    if languages:
        block = add("Languages (separate)", languages, inline=True)
        optional.extend((10, block, i) for i in range(len(languages)))

    if len(render()) > limit:
        raise ValueError(f"Mandatory candidate qualifications/role scope exceed the {limit}-character profile budget")

    # Give every research entry a turn before any entry receives more evidence.
    for position, block in enumerate(research):
        if not block.items:
            continue
        fair_share = (limit - len(render())) // (len(research) - position)
        ranked = sorted(range(len(block.items)), key=lambda i: -len(_EVIDENCE_TOPICS.findall(block.items[i])))
        for i in ranked:
            before = len(render())
            block.selected.add(i)
            if len(render()) - before <= fair_share and len(render()) <= limit:
                break
            block.selected.remove(i)
        else:
            raise ValueError(f"No complete evidence for '{block.label}' fits the {limit}-character profile budget")

    # Highest-value scientific facts first; render in original section/item
    # order. Oversized bullets are skipped whole, not truncated into fragments.
    for _, block, i in sorted(optional, key=lambda unit: -unit[0]):
        if i in block.selected:
            continue
        block.selected.add(i)
        if len(render()) > limit:
            block.selected.remove(i)
    return render()
