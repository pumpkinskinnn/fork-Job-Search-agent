import logging

import requests

from jobs.ats.base import make_dedup_hash, normalize_job_id
from jobs.location_filter import location_matches

logger = logging.getLogger(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"}


def fetch_smartrecruiters_jobs(company: str, slug: str, location_filter: str = "") -> list[dict]:
    jobs = []
    offset = 0
    limit = 100

    while True:
        url = (
            f"https://api.smartrecruiters.com/v1/companies/{slug}/postings"
            f"?offset={offset}&limit={limit}"
        )
        try:
            response = requests.get(url, headers=HEADERS, timeout=20)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            logger.warning("SmartRecruiters fetch failed for %s (%s): %s", company, slug, exc)
            break

        content = data.get("content", [])
        if not content:
            break

        for item in content:
            loc = item.get("location", {})
            location = loc.get("fullLocation", loc.get("city", "")) if isinstance(loc, dict) else str(loc)
            country = loc.get("country", "") if isinstance(loc, dict) else ""
            if country:
                location = f"{location}, {country}"

            jobs.append(
                {
                    "job_id": normalize_job_id("sr", f"{slug}_{item['id']}"),
                    "title": item.get("name", ""),
                    "company": company,
                    "location": location,
                    "posted_date": item.get("releasedDate", "")[:10],
                    "job_url": item.get("ref") or f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{item['id']}",
                    "detail_url": f"https://api.smartrecruiters.com/v1/companies/{slug}/postings/{item['id']}",
                    "description": item.get("description", "") or "",
                    "source": "smartrecruiters",
                    "source_company": company,
                    "dedup_hash": make_dedup_hash(company, item.get("name", ""), location),
                }
            )

        offset += limit
        if offset >= data.get("totalFound", 0):
            break

    if location_filter:
        # Generic remote locations need detail text before UK eligibility can be checked.
        from jobs.location_filter import location_needs_description
        jobs = [j for j in jobs if location_matches(j) or location_needs_description(j)]

    return jobs
