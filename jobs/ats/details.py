"""Bounded enrichment using supported ATS JSON endpoints, never website scraping."""

import logging
import re
import threading
from urllib.parse import urlparse

import requests

from config import ATS_DETAIL_REQUESTS_PER_BOARD
from jobs.domain_filter import description_available
from jobs.http_client import get_session

logger = logging.getLogger(__name__)
_offsets: dict[tuple[str, str], int] = {}
_lock = threading.Lock()


def official_detail_url(job: dict) -> str:
    """Derive endpoints from trusted board URLs, also after database round trips."""
    try:
        parsed = urlparse(job.get("detail_url") or job.get("job_url") or "")
        port = parsed.port
    except ValueError:
        return ""
    if parsed.scheme != "https" or parsed.username or parsed.password or port:
        return ""
    if job.get("source") == "smartrecruiters":
        if parsed.hostname == "api.smartrecruiters.com" and re.fullmatch(
            r"/v1/companies/[\w-]+/postings/[\w-]+", parsed.path
        ):
            return f"https://{parsed.hostname}{parsed.path}"
    if job.get("source") == "workday" and re.fullmatch(
        r"[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com", parsed.hostname or "", re.I
    ):
        match = re.fullmatch(r"/([\w-]+)(/job/.+)", parsed.path)
        if match and not any(part in {".", ".."} for part in parsed.path.split("/")):
            tenant = parsed.hostname.split(".")[0]
            return f"https://{parsed.hostname}/wday/cxs/{tenant}/{match[1]}{match[2]}"
    return ""


def fetch_official_description(job: dict) -> str:
    url = official_detail_url(job)
    if not url:
        return ""
    try:
        response = get_session().get(url, timeout=20, allow_redirects=False, headers={"Accept": "application/json"})
        response.raise_for_status()
        data = response.json()
        if job.get("source") == "workday":
            info = data.get("jobPostingInfo") or {}
            return info.get("jobDescription") or ""
        sections = (data.get("jobAd") or {}).get("sections") or {}
        parts = []
        for key, label in (("jobDescription", "Responsibilities"), ("qualifications", "Qualifications"),
                           ("additionalInformation", "Additional information")):
            text = (sections.get(key) or {}).get("text") or ""
            if text:
                parts.append(f"<h3>{label}</h3>\n{text}")
        return "\n".join(parts)
    except (requests.RequestException, ValueError, TypeError, AttributeError) as exc:
        logger.debug("Official ATS detail unavailable for %s: %s", job.get("job_id"), exc)
        return ""


def enrich_ats_descriptions(jobs: list[dict], limit: int = ATS_DETAIL_REQUESTS_PER_BOARD) -> None:
    pending = [job for job in jobs if job.get("source") in {"workday", "smartrecruiters"}
               and not description_available(job)]
    if not pending:
        return
    from jobs.job_store import get_existing_job_descriptions
    cached = get_existing_job_descriptions()
    for job in pending:
        if cached.get(job.get("job_id")):
            job["description"] = cached[job["job_id"]]
    pending = [job for job in pending if not description_available(job) and official_detail_url(job)]
    if not pending or limit <= 0:
        return
    # Each invocation handles one company board; skip cached descriptions and
    # rotate the remaining bounded detail attempts so later jobs get coverage.
    key = (pending[0]["source"], pending[0].get("source_company") or pending[0].get("company", ""))
    with _lock:
        offset = _offsets.get(key, 0)
        count = min(limit, len(pending))
        _offsets[key] = offset + count
    for i in range(count):
        job = pending[(offset + i) % len(pending)]
        description = fetch_official_description(job)
        if description:
            job["description"] = description
