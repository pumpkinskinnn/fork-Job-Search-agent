import re

from jobs.domain_filter import IRRELEVANT_TITLE, broad_stem_title_matches
from jobs.experience_filter import is_senior_title


def company_to_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = slug.replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    for suffix in ("-inc", "-ltd", "-limited", "-corp", "-pvt"):
        if slug.endswith(suffix):
            slug = slug[: -len(suffix)]
    return slug


def company_matches(job_company: str, target_company: str) -> bool:
    job = job_company.lower().strip()
    target = target_company.lower().strip()

    if not job or not target:
        return False
    if target in job or job in target:
        return True

    target_root = target.split()[0]
    job_root = job.split()[0]
    return len(target_root) >= 4 and target_root == job_root


def role_matches(job_title: str, target_roles: list[str]) -> bool:
    if not target_roles:
        return True

    title = job_title.lower()
    scientific_search = re.search(r"energy|materials|chemistry|chemist|scientist", " ".join(target_roles), re.I)
    if scientific_search and (is_senior_title(title) or IRRELEVANT_TITLE.search(title)):
        return False
    for role in target_roles:
        role_lower = role.lower().strip()
        if not role_lower:
            continue
        if role_lower in title:
            return True

        keywords = [w for w in re.split(r"[\s/,-]+", role_lower) if len(w) >= 4]
        if len(keywords) >= 2 and sum(1 for w in keywords if w in title) >= 2:
            return True
        if len(keywords) == 1 and keywords[0] in title:
            return True

    # Scientific graduate titles vary substantially across employers. Keep
    # related STEM variants for scoring rather than demanding one exact label.
    if scientific_search:
        return broad_stem_title_matches(title)
    return False
