"""Supplemental Phenom ATS scraper.

Uses the unauthenticated /widgets POST API to bulk-fetch jobs from Phenom
career sites listed in phenom_companies.json.

Two-pass approach:
  Pass 1 — Search: POST with ddoKey "refineSearch", size=500, paginate.
           Gets title, location, city/state, posted date, category, type.
  Pass 2 — Detail: POST with ddoKey "jobDetail" per job to get full HTML
           description. Parses salary from description text.

Jobs are inserted as already-enriched (description included from detail pass).
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from pipeline.filter import is_healthcare_job
from pipeline.salary import parse_salary, parse_bonus

logger = logging.getLogger(__name__)

COMPANIES_FILE = os.path.join(os.path.dirname(__file__), "phenom_companies.json")
SEARCH_SIZE = 500
MAX_DETAIL_WORKERS = 5
DETAIL_DELAY = 0.2  # seconds between detail calls per site

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
)


def _load_sites() -> list[dict]:
    """Load Phenom career sites from config."""
    if not os.path.exists(COMPANIES_FILE):
        return []
    with open(COMPANIES_FILE) as f:
        return json.load(f)


def _search_jobs(domain: str) -> list[dict]:
    """Fetch all jobs from a Phenom site using the refineSearch widget."""
    url = f"https://{domain}/widgets"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }

    all_jobs = []
    offset = 0

    while True:
        payload = {
            "lang": "en_us",
            "deviceType": "desktop",
            "country": "us",
            "pageName": "search-results",
            "ddoKey": "refineSearch",
            "sortBy": "",
            "from": offset,
            "size": SEARCH_SIZE,
            "jobs": True,
            "counts": False,
            "all_fields": ["category", "type"],
        }

        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            if resp.status_code != 200:
                logger.debug("[phenom] %d for %s, stopping", resp.status_code, domain)
                break
            data = resp.json()
        except Exception as e:
            logger.debug("[phenom] Error fetching %s offset %d: %s", domain, offset, e)
            break

        ref_data = data.get("refineSearch", {})
        hits = ref_data.get("data", {}).get("jobs", [])
        total = ref_data.get("totalHits", 0)

        if not hits:
            break

        all_jobs.extend(hits)
        offset += SEARCH_SIZE

        if offset >= total:
            break

        time.sleep(0.3)

    return all_jobs


def _fetch_detail(domain: str, job_seq_no: str) -> dict | None:
    """Fetch full job detail using the jobDetail widget."""
    url = f"https://{domain}/widgets"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    payload = {
        "lang": "en_us",
        "deviceType": "desktop",
        "country": "us",
        "pageName": "search-results",
        "ddoKey": "jobDetail",
        "jobSeqNo": job_seq_no,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        if resp.status_code != 200:
            return None
        return resp.json().get("jobDetail", {}).get("data", {}).get("job", {})
    except Exception:
        return None


def _scrape_site(site: dict) -> list[dict]:
    """Scrape a single Phenom site: search then enrich with details."""
    domain = site["domain"]
    logger.info("[phenom] Scraping %s", domain)

    # Pass 1: Search all jobs
    raw_jobs = _search_jobs(domain)
    if not raw_jobs:
        logger.debug("[phenom] No jobs found on %s", domain)
        return []

    # Pre-filter to healthcare before fetching details
    candidates = []
    for rj in raw_jobs:
        title = rj.get("title", "")
        if not title:
            continue

        city = rj.get("city", "")
        state = rj.get("state", "")
        location = f"{city}, {state}" if city and state else city or state or ""

        job_stub = {
            "title": title,
            "departments": [rj.get("category", "")] if rj.get("category") else [],
            "location": location,
        }

        if is_healthcare_job(job_stub):
            candidates.append(rj)

    if not candidates:
        logger.debug("[phenom] No healthcare jobs on %s (checked %d)", domain, len(raw_jobs))
        return []

    logger.info("[phenom] %s: %d healthcare jobs of %d total, fetching details", domain, len(candidates), len(raw_jobs))

    # Pass 2: Fetch details for healthcare jobs
    results = []
    for i, rj in enumerate(candidates):
        job_seq_no = rj.get("jobSeqNo", "")
        if not job_seq_no:
            continue

        detail = _fetch_detail(domain, job_seq_no)
        if detail is None:
            detail = {}

        title = rj.get("title", "")
        city = rj.get("city", "")
        state = rj.get("state", "")
        location = f"{city}, {state}" if city and state else city or state or ""
        company_name = rj.get("companyName", "") or domain.split(".")[0]
        posted = rj.get("postedDate", "")
        category = rj.get("category", "")
        job_type = rj.get("type", "")
        req_id = rj.get("reqId", "")

        # Build job URL
        title_slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
        job_url = f"https://{domain}/us/en/job/{job_seq_no}/{title_slug}"

        # Description from detail
        desc_html = detail.get("description", "")
        desc_plain = ""
        if desc_html:
            desc_plain = re.sub(r"<[^>]+>", " ", desc_html)
            desc_plain = re.sub(r"\s+", " ", desc_plain).strip()

        # Salary: parse from description
        salary_min = salary_max = None
        bonus = None
        if desc_plain:
            salary_min, salary_max = parse_salary(desc_plain)
            bonus = parse_bonus(desc_plain)

        # Departments
        departments = []
        if category:
            departments.append(category)
        if job_type:
            departments.append(job_type)

        job = {
            "title": title,
            "company": company_name,
            "company_name": company_name,
            "ats": "phenom",
            "url": job_url,
            "location": location[:80] if location else "",
            "skill_level": "",
            "is_recruiter": False,
            "departments": departments,
            "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        if posted:
            job["posted_date"] = posted[:10]

        # These fields are normally set during enrichment, but we have them now
        if desc_html:
            job["description_html"] = desc_html
            job["description_plain"] = desc_plain
        if salary_min:
            job["salary_min"] = salary_min
            job["salary_max"] = salary_max
        if bonus:
            job["bonus"] = bonus

        results.append(job)

        if (i + 1) % 100 == 0:
            logger.info("[phenom] %s: fetched %d/%d details", domain, i + 1, len(candidates))

        time.sleep(DETAIL_DELAY)

    return results


def scrape_phenom() -> list[dict]:
    """Scrape all Phenom career sites and return healthcare jobs with full details."""
    sites = _load_sites()
    if not sites:
        logger.info("[phenom] No Phenom sites configured")
        return []

    logger.info("[phenom] Scraping %d Phenom career sites", len(sites))
    all_jobs = []
    success = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=MAX_DETAIL_WORKERS) as executor:
        futures = {
            executor.submit(_scrape_site, site): site["domain"]
            for site in sites
        }
        for future in as_completed(futures):
            domain = futures[future]
            try:
                jobs = future.result()
                if jobs:
                    all_jobs.extend(jobs)
                    logger.info("[phenom] %s: %d healthcare jobs", domain, len(jobs))
                    success += 1
                else:
                    success += 1
            except Exception as e:
                logger.warning("[phenom] %s failed: %s", domain, e)
                failed += 1

    logger.info(
        "[phenom] Done: %d jobs from %d sites (%d failed)",
        len(all_jobs), success, failed,
    )
    return all_jobs
