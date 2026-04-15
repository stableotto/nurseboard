"""Ashby ATS enricher. Uses batch endpoint per company."""

from __future__ import annotations

import logging
import re

import requests

from pipeline.salary import parse_salary

logger = logging.getLogger(__name__)

# Ashby URL pattern: https://jobs.ashbyhq.com/{slug}/{id} or similar
URL_PATTERN = re.compile(r"jobs\.ashbyhq\.com/([^/]+)/([a-f0-9-]+)")

# Cache batch results per slug within a single run
_cache: dict[str, dict] = {}


def _fetch_board(slug: str) -> dict:
    """Fetch all jobs for a company board (cached)."""
    if slug in _cache:
        return _cache[slug]

    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
    try:
        resp = requests.get(api_url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        jobs_by_id = {}
        for job in data.get("jobs", []):
            jid = job.get("id")
            if jid:
                jobs_by_id[jid] = job
        _cache[slug] = jobs_by_id
        return jobs_by_id
    except Exception as e:
        logger.debug("Ashby board fetch error for %s: %s", slug, e)
        _cache[slug] = {}
        raise


def enrich_ashby(job: dict) -> dict | None:
    """Fetch job details from Ashby batch API."""
    match = URL_PATTERN.search(job["url"])
    if not match:
        return None

    slug, job_id = match.groups()

    try:
        board = _fetch_board(slug)
    except Exception:
        raise

    posting = board.get(job_id)
    if not posting:
        return None

    result = {}

    if posting.get("publishedAt"):
        result["posted_date"] = posting["publishedAt"]

    desc = posting.get("descriptionHtml") or posting.get("descriptionPlain")
    if desc:
        result["description_html"] = desc
        plain = re.sub(r"<[^>]+>", " ", desc)
        result["description_plain"] = re.sub(r"\s+", " ", plain).strip()

    sal_min, sal_max = parse_salary(result.get("description_plain", ""))
    if sal_min:
        result["salary_min"] = sal_min
    if sal_max:
        result["salary_max"] = sal_max

    return result
