"""Supplemental Oracle HCM scraper.

Hits the unauthenticated recruitingCEJobRequisitions REST API for each
Oracle HCM career site in oracle_hcm_extra.json, filters for nursing jobs,
and returns them in the same format as upstream.

Two-pass approach:
  Pass 1 — List-only scrape (~2 min). Grabs title, location, posted date,
           short description, schedule, shift from the list endpoint.
           Parses salary from short description when available.
  Pass 2 — Detail calls for jobs missing salary happen later in the
           enrichment phase (see enrichers/oracle_hcm.py).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

import requests

from pipeline.config import SALARY_RANGE_PATTERN, HOURLY_PATTERN
from pipeline.filter import is_nursing_job

logger = logging.getLogger(__name__)

EXTRA_FILE = os.path.join(os.path.dirname(__file__), "oracle_hcm_extra.json")
MAX_WORKERS = 10
JOBS_PER_PAGE = 200
MAX_PAGES = 100  # Safety limit: 100 * 200 = 20,000 per site

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"


def _load_sites() -> list[tuple[str, str]]:
    """Load Oracle HCM sites. Returns list of (host, site_number)."""
    if not os.path.exists(EXTRA_FILE):
        return []
    with open(EXTRA_FILE) as f:
        entries = json.load(f)

    seen = set()
    result = []
    for entry in entries:
        parts = entry.split("|")
        if len(parts) == 2:
            host, site = parts
            key = f"{host}|{site}"
            if key not in seen:
                seen.add(key)
                result.append((host, site))
    return result


def _parse_salary_from_text(text: str) -> tuple[int | None, int | None]:
    """Extract salary from description text. Returns (min_cents, max_cents)."""
    if not text:
        return None, None
    match = SALARY_RANGE_PATTERN.search(text)
    if not match:
        return None, None
    low = float(match.group(1).replace(",", ""))
    high = float(match.group(2).replace(",", ""))
    if HOURLY_PATTERN.search(text[match.start():match.end() + 20]):
        low *= 2080
        high *= 2080
    return int(low * 100), int(high * 100)


def _fetch_site_jobs(host: str, site_number: str) -> list[dict]:
    """Fetch all jobs from a single Oracle HCM site, return nursing matches."""
    base = f"https://{host}"
    api_base = f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"

    headers = {
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }

    all_jobs = []
    offset = 0
    total = None

    for page in range(MAX_PAGES):
        finder = (
            f"findReqs;siteNumber={site_number},"
            f"limit={JOBS_PER_PAGE},offset={offset},"
            f"sortBy=POSTING_DATES_DESC"
        )
        url = f"{api_base}?onlyData=true&expand=requisitionList&finder={finder}"

        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code != 200:
                logger.debug("[oracle-hcm] %d for %s/%s, skipping", resp.status_code, host, site_number)
                break
            data = resp.json()
        except Exception as e:
            logger.debug("[oracle-hcm] Error fetching %s/%s page %d: %s", host, site_number, page, e)
            break

        items_wrapper = data.get("items", [{}])
        if not items_wrapper:
            break

        # The API nests jobs under items[0].requisitionList
        req_list = items_wrapper[0].get("requisitionList", []) if items_wrapper else []
        if not req_list:
            break

        if total is None:
            total = items_wrapper[0].get("TotalJobsCount", 0)

        for req in req_list:
            title = req.get("Title", "")
            job_id = req.get("Id", "")
            location = req.get("PrimaryLocation", "")
            posted = req.get("PostedDate", "")
            short_desc = req.get("ShortDescriptionStr", "")
            schedule = req.get("JobSchedule", "")
            shift = req.get("JobShift", "")
            job_family = req.get("JobFamily", "")

            if not title or not job_id:
                continue

            job_url = f"{base}/hcmUI/CandidateExperience/en/sites/{site_number}/job/{job_id}"

            # Parse salary from short description
            salary_min, salary_max = _parse_salary_from_text(short_desc)

            # Build departments from job family + schedule
            departments = []
            if job_family:
                departments.append(job_family)
            if schedule:
                departments.append(schedule)

            job = {
                "title": title,
                "company": host.split(".")[0],  # fallback slug
                "ats": "oracle_hcm",
                "url": job_url,
                "location": location[:80] if location else "",
                "skill_level": "",
                "is_recruiter": False,
                "departments": departments,
                "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

            if posted:
                job["posted_date"] = posted[:10]  # YYYY-MM-DD

            if salary_min and salary_max:
                job["salary_min"] = salary_min
                job["salary_max"] = salary_max

            if shift:
                job["shift"] = shift

            if is_nursing_job(job):
                all_jobs.append(job)

        offset += JOBS_PER_PAGE
        if total and offset >= total:
            break

        # Polite delay between pages
        time.sleep(0.3)

    return all_jobs


def scrape_oracle_hcm() -> list[dict]:
    """Scrape all Oracle HCM career sites and return nursing jobs."""
    sites = _load_sites()
    if not sites:
        logger.info("[oracle-hcm] No Oracle HCM sites configured")
        return []

    logger.info("[oracle-hcm] Scraping %d Oracle HCM career sites", len(sites))
    all_nursing_jobs = []
    seen_urls = set()
    success = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_site_jobs, host, site): f"{host}/{site}"
            for host, site in sites
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                jobs = future.result()
                if jobs:
                    # Dedup across sites (same host with different site numbers)
                    for job in jobs:
                        if job["url"] not in seen_urls:
                            seen_urls.add(job["url"])
                            all_nursing_jobs.append(job)
                    logger.debug("[oracle-hcm] %s: %d nursing jobs", key, len(jobs))
                success += 1
            except Exception as e:
                logger.debug("[oracle-hcm] %s failed: %s", key, e)
                failed += 1

    logger.info(
        "[oracle-hcm] Done: %d sites scraped, %d failed, %d nursing jobs found",
        success, failed, len(all_nursing_jobs),
    )
    return all_nursing_jobs
