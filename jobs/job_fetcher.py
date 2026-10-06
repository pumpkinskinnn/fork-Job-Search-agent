import logging
import re
from itertools import zip_longest
from urllib.parse import quote

from bs4 import BeautifulSoup

from config import (
    BROAD_SEARCH_QUERIES, BROAD_SEARCH_QUERIES_PER_CYCLE, ENABLE_BROAD_LINKEDIN_SEARCH,
    LINKEDIN_MAX_SEARCHES_PER_CYCLE, LINKEDIN_MIN_DELAY_SECONDS, USER_PROFILE,
)
from jobs.linkedin_utils import normalize_linkedin_job_url
from jobs.ats.base import make_dedup_hash, normalize_job_id
from jobs.career_fetcher import fetch_all_career_jobs
from jobs.company_utils import company_matches, role_matches
from jobs.job_description import attach_description
from jobs.linkedin_client import begin_linkedin_cycle, linkedin_get, linkedin_is_limited
from jobs.profile_filter import pre_description_matches, profile_matches

logger = logging.getLogger(__name__)

GUEST_API = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings"
_company_offset = 0
_broad_offset = 0
_role_offset = 0
_known_job_ids: set[str] = set()
_known_descriptions: dict[str, str] = {}


def _extract_job_id(href: str, card) -> str | None:
    if href:
        match = re.search(r"(\d{8,})", href)
        if match:
            return match.group(1)

    urn = card.get("data-entity-urn", "")
    match = re.search(r"jobPosting:(\d+)", urn)
    if match:
        return match.group(1)

    return None


def _parse_job_cards(html: str, source_company: str = "") -> list[dict]:
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for card in soup.select("div.base-search-card"):
        link = card.select_one("a.base-card__full-link")
        title_el = card.select_one("h3.base-search-card__title")
        company_el = card.select_one("h4.base-search-card__subtitle")
        location_el = card.select_one("span.job-search-card__location")
        time_el = card.select_one("time")

        href = link.get("href", "") if link else ""
        job_id = _extract_job_id(href, card)
        if not job_id:
            continue

        title = title_el.get_text(strip=True) if title_el else "Unknown Title"
        company = company_el.get_text(strip=True) if company_el else source_company or "Unknown Company"
        location = location_el.get_text(strip=True) if location_el else USER_PROFILE.get("location", "")
        posted_date = time_el.get("datetime", "") if time_el else ""
        if not posted_date and time_el:
            posted_date = time_el.get_text(strip=True)

        job_url = normalize_linkedin_job_url(
            href.split("?")[0] if href else f"https://www.linkedin.com/jobs/view/{job_id}",
            normalize_job_id("li", job_id),
        )
        li_job_id = normalize_job_id("li", job_id)

        jobs.append(
            {
                "job_id": li_job_id,
                "title": title,
                "company": company,
                "location": location,
                "posted_date": posted_date,
                "job_url": job_url,
                "source": "linkedin",
                "source_company": source_company,
                "dedup_hash": make_dedup_hash(company, title, location),
            }
        )

    return jobs


def _fetch_html(path_and_query: str) -> str:
    if linkedin_is_limited():
        return ""
    response = linkedin_get(f"{GUEST_API}/{path_and_query}", timeout=20)
    return response.text if response is not None else ""


def _search_params(keywords: str, location: str, lookback: str, start: int = 0, count: int = 25) -> str:
    return "&".join(
        [
            f"keywords={quote(keywords)}",
            f"location={quote(location)}",
            f"f_TPR={lookback}",
            "sortBy=DD",
            f"start={start}",
            f"count={count}",
        ]
    )


def _fetch_search(keywords: str, location: str, lookback: str) -> list[dict]:
    query = _search_params(keywords, location, lookback)
    html = _fetch_html(f"search?{query}")
    return _parse_job_cards(html) if html else []


def _is_relevant(job: dict, company_name: str, roles: list[str]) -> bool:
    if company_name and not company_matches(job.get("company", ""), company_name):
        return False
    if USER_PROFILE.get("filter_by_role", True) and roles and not role_matches(job.get("title", ""), roles):
        return False
    if not job.get("description"):
        job["description"] = _known_descriptions.get(job.get("job_id"), "")
    if not pre_description_matches(job):
        return False
    already_stored = job.get("job_id") in _known_job_ids
    if (not already_stored or not job.get("description")) and not linkedin_is_limited():
        attach_description(job)
    return profile_matches(job)


def fetch_jobs_for_company(company_name: str, roles: list[str], location: str, lookback: str) -> list[dict]:
    jobs: list[dict] = []
    seen_ids: set[str] = set()

    for job in _fetch_search(company_name, location, lookback):
        if job["job_id"] in seen_ids:
            continue
        if not _is_relevant(job, company_name, roles):
            continue
        seen_ids.add(job["job_id"])
        jobs.append(job)

    logger.info("Fetched %d jobs for company %s", len(jobs), company_name)
    return jobs


def fetch_jobs_for_role(role: str, location: str, lookback: str) -> list[dict]:
    jobs = _fetch_search(role, location, lookback)
    # Broad query wording need not appear verbatim in a suitable result title.
    return [job for job in jobs if _is_relevant(job, "", USER_PROFILE.get("target_roles", []))]


def _rotation(items: list[str], offset: int, count: int) -> list[str]:
    return [items[(offset + i) % len(items)] for i in range(min(count, len(items)))] if items else []


def linkedin_search_plan(companies: list[str], roles: list[str]) -> list[tuple[str, str]]:
    """Preview this cycle without advancing cursors or making any requests."""
    cap = LINKEDIN_MAX_SEARCHES_PER_CYCLE
    broad_count = min(BROAD_SEARCH_QUERIES_PER_CYCLE, len(BROAD_SEARCH_QUERIES), cap)
    if not ENABLE_BROAD_LINKEDIN_SEARCH:
        broad_count = 0
    if companies:
        broad_count = min(broad_count, max(0, cap - 1))  # reserve shortlist capacity
        company_queries = _rotation(companies, _company_offset, cap - broad_count)
        return ([('company', query) for query in company_queries]
                + [('broad', query) for query in _rotation(BROAD_SEARCH_QUERIES, _broad_offset, broad_count)])
    if broad_count:
        return [('broad', query) for query in _rotation(BROAD_SEARCH_QUERIES, _broad_offset, broad_count)]
    return [('role', query) for query in _rotation(roles, _role_offset, cap)]


def _fetch_linkedin_jobs(
    companies: list[str],
    roles: list[str],
    location: str,
    lookback: str,
) -> list[dict]:
    global _known_job_ids, _known_descriptions, _company_offset, _broad_offset, _role_offset

    begin_linkedin_cycle()
    try:
        from jobs.job_store import get_existing_job_ids, get_existing_job_descriptions

        _known_job_ids = get_existing_job_ids()
        _known_descriptions = get_existing_job_descriptions()
    except Exception:
        _known_job_ids = set()
        _known_descriptions = {}

    plan = linkedin_search_plan(companies, roles)
    logger.info(
        "LinkedIn: %d planned searches, including %d company-independent queries (%.0fs between requests)",
        len(plan),
        sum(kind != 'company' for kind, _ in plan),
        LINKEDIN_MIN_DELAY_SECONDS,
    )

    candidate_batches: list[list[tuple[dict, str]]] = []
    seen_ids: set[str] = set()
    # Search first: all detail requests still share the unchanged LinkedIn budget.
    for kind, query in plan:
        if linkedin_is_limited():
            logger.warning("LinkedIn: stopping remaining searches this cycle (rate limited)")
            break
        try:
            results = _fetch_search(query, location, lookback)
            batch = []
            for job in results:
                company = query if kind == 'company' else ''
                if company and not company_matches(job.get('company', ''), company):
                    continue
                if job.get('job_id') and job['job_id'] not in seen_ids:
                    batch.append((job, company))
                    seen_ids.add(job.get('job_id'))
            candidate_batches.append(batch)
        except Exception:
            logger.exception("LinkedIn fetch failed for %s", query)
        finally:
            # Advance only attempted queries; a blocked cycle resumes unattempted ones.
            if kind == 'company':
                _company_offset += 1
            elif kind == 'broad':
                _broad_offset += 1
            else:
                _role_offset += 1

    # Give each search path a turn at description enrichment, so a busy first
    # company cannot consume all remaining detail requests before broad results.
    kept = []
    for row in zip_longest(*candidate_batches):
        for candidate in row:
            if candidate is not None:
                job, company = candidate
                if _is_relevant(job, company, roles):
                    kept.append(job)
    return kept


def fetch_all_jobs() -> list[dict]:
    location = USER_PROFILE.get("location", "")
    roles = USER_PROFILE.get("target_roles", [])
    companies = USER_PROFILE.get("target_companies", [])
    lookback = USER_PROFILE.get("job_lookback", "r604800")

    all_jobs: list[dict] = []
    seen_ids: set[str] = set()
    seen_dedup: set[str] = set()

    def add_job(job: dict) -> None:
        job_id = job.get("job_id")
        dedup = job.get("dedup_hash", "")
        if not job_id or job_id in seen_ids:
            return
        if dedup and dedup in seen_dedup:
            return
        seen_ids.add(job_id)
        if dedup:
            seen_dedup.add(dedup)
        all_jobs.append(job)

    for job in fetch_all_career_jobs():
        add_job(job)

    for job in _fetch_linkedin_jobs(companies, roles, location, lookback):
        add_job(job)

    career_count = sum(1 for j in all_jobs if j.get("source") != "linkedin")
    logger.info(
        "Total jobs fetched: %d (%d from career sites, %d from LinkedIn)",
        len(all_jobs),
        career_count,
        len(all_jobs) - career_count,
    )
    return all_jobs
