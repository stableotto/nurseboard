"""Supplemental Workday scraper for companies not in the upstream aggregator.

Hits the Workday CXS jobs list API for each company in workday_extra.json,
filters for nursing jobs, and returns them in the same format as upstream.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from pipeline.config import TITLE_PATTERN, DEPARTMENT_KEYWORDS
from pipeline.filter import is_healthcare_job

logger = logging.getLogger(__name__)

EXTRA_COMPANIES_FILE = os.path.join(os.path.dirname(__file__), "workday_extra.json")
MAX_WORKERS = 15
JOBS_PER_PAGE = 20
MAX_PAGES = 50  # Safety limit: 50 * 20 = 1000 jobs per company

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]


def _load_extra_companies() -> list[tuple[str, str, str]]:
    """Load company list. Returns list of (tenant, wd_num, site_id)."""
    if not os.path.exists(EXTRA_COMPANIES_FILE):
        return []
    with open(EXTRA_COMPANIES_FILE) as f:
        entries = json.load(f)

    result = []
    for entry in entries:
        parts = entry.split("|")
        if len(parts) == 3:
            tenant, wd_num, site_id = parts
            result.append((tenant, wd_num, site_id))
    return result


def _fetch_company_jobs(tenant: str, wd_num: str, site_id: str) -> list[dict]:
    """Fetch all jobs from a single Workday company, return nursing matches."""
    base = f"https://{tenant}.wd{wd_num}.myworkdayjobs.com"
    api_url = f"{base}/wday/cxs/{tenant}/{site_id}/jobs"
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": random.choice(USER_AGENTS),
    }

    all_jobs = []
    offset = 0
    company_name = tenant  # fallback to slug

    for page in range(MAX_PAGES):
        payload = {"appliedFacets": {}, "limit": JOBS_PER_PAGE, "offset": offset, "searchText": ""}

        try:
            resp = requests.post(api_url, json=payload, headers=headers, timeout=20)
            if resp.status_code == 403:
                logger.debug("[workday-extra] 403 for %s/%s, skipping", tenant, site_id)
                break
            if resp.status_code != 200:
                break
            data = resp.json()
        except Exception as e:
            logger.debug("[workday-extra] Error fetching %s/%s page %d: %s", tenant, site_id, page, e)
            break

        postings = data.get("jobPostings", [])
        if not postings:
            break

        total = data.get("total", 0)

        # On first page, fetch one detail to get the real company name
        if page == 0 and company_name == tenant and postings:
            first_path = postings[0].get("externalPath", "")
            if first_path:
                try:
                    detail_url = f"{base}/wday/cxs/{tenant}/{site_id}{first_path}"
                    dr = requests.get(detail_url, headers={"Accept": "application/json"}, timeout=10)
                    if dr.status_code == 200:
                        hiring_org = dr.json().get("hiringOrganization", {})
                        if hiring_org.get("name"):
                            company_name = hiring_org["name"]
                except Exception:
                    pass

        for posting in postings:
            title = posting.get("title", "")
            external_path = posting.get("externalPath", "")
            location = posting.get("locationsText", "") or ""
            posted_on = posting.get("postedOn", "")

            job_url = f"{base}/{site_id}{external_path}" if external_path else ""
            if not job_url or not title:
                continue

            # Build in upstream-compatible format
            job = {
                "title": title,
                "company": company_name,
                "ats": "workday",
                "url": job_url,
                "location": location[:50],
                "skill_level": "",
                "is_recruiter": False,
                "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

            # Filter for healthcare (nursing + allied health)
            if is_healthcare_job(job):
                all_jobs.append(job)

        offset += JOBS_PER_PAGE
        if offset >= total:
            break

        # Polite delay between pages
        time.sleep(random.uniform(0.5, 1.2))

    return all_jobs


def scrape_extra_workday() -> list[dict]:
    """Scrape all extra Workday companies and return nursing jobs."""
    companies = _load_extra_companies()
    if not companies:
        logger.info("[workday-extra] No extra companies configured")
        return []

    logger.info("[workday-extra] Scraping %d extra Workday companies", len(companies))
    all_nursing_jobs = []
    success = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_company_jobs, t, w, s): f"{t}/{s}"
            for t, w, s in companies
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                jobs = future.result()
                if jobs:
                    all_nursing_jobs.extend(jobs)
                    logger.debug("[workday-extra] %s: %d nursing jobs", key, len(jobs))
                success += 1
            except Exception as e:
                logger.debug("[workday-extra] %s failed: %s", key, e)
                failed += 1

    logger.info(
        "[workday-extra] Done: %d companies scraped, %d failed, %d nursing jobs found",
        success, failed, len(all_nursing_jobs),
    )
    return all_nursing_jobs
