"""Supplemental NEOGOV (governmentjobs.com) scraper.

Uses the XHR listing endpoint for job discovery, then fetches individual
job detail pages to extract JSON-LD (schema.org/JobPosting) for structured
data including title, description, salary, posted date, and location.

Two-pass approach:
  Pass 1 — Discovery via XHR listing endpoint. Gets job IDs and basic info.
  Pass 2 — Detail enrichment via JSON-LD on detail pages happens in the
           enrichment phase (see enrichers/neogov.py).
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from pipeline.config import SALARY_RANGE_PATTERN, HOURLY_PATTERN
from pipeline.filter import is_nursing_job

logger = logging.getLogger(__name__)

AGENCIES_FILE = os.path.join(os.path.dirname(__file__), "neogov_agencies.json")
MAX_WORKERS = 5  # Conservative — NEOGOV is stricter than Oracle
JOBS_PER_PAGE = 10  # NEOGOV XHR returns 10 per page
MAX_PAGES = 100  # Safety limit: 100 * 10 = 1000 per agency

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

# Regex to extract job links from NEOGOV XHR HTML fragments
_JOB_LINK_RE = re.compile(
    r'href="(/careers/[^/]+/jobs/(\d+)[^"]*)"[^>]*>',
    re.IGNORECASE,
)

# Regex to extract job title from the HTML fragments
_JOB_TITLE_RE = re.compile(
    r'class="item-title"[^>]*>\s*(?:<[^>]+>)*\s*([^<]+)',
    re.IGNORECASE,
)

# Regex for JSON-LD extraction from detail pages
_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)


def _load_agencies() -> list[str]:
    """Load NEOGOV agency slugs."""
    if not os.path.exists(AGENCIES_FILE):
        return []
    with open(AGENCIES_FILE) as f:
        return json.load(f)


def _parse_jsonld(html: str) -> dict | None:
    """Extract JobPosting JSON-LD from a detail page."""
    for match in _JSONLD_RE.finditer(html):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                for item in data:
                    if item.get("@type") == "JobPosting":
                        return item
            elif isinstance(data, dict) and data.get("@type") == "JobPosting":
                return data
        except (json.JSONDecodeError, KeyError):
            continue
    return None


def _extract_salary(ld: dict) -> tuple[int | None, int | None]:
    """Extract salary from JSON-LD baseSalary."""
    base = ld.get("baseSalary", {})
    if not base:
        return None, None
    value = base.get("value", {})
    if not value:
        return None, None

    low = value.get("minValue")
    high = value.get("maxValue")
    if not low and not high:
        return None, None

    try:
        low = float(low) if low else None
        high = float(high) if high else None
    except (ValueError, TypeError):
        return None, None

    # Convert hourly to annual
    unit = (value.get("unitText") or "").upper()
    if unit == "HOUR":
        if low:
            low *= 2080
        if high:
            high *= 2080

    min_cents = int(low * 100) if low else None
    max_cents = int(high * 100) if high else None
    return min_cents, max_cents


def _extract_location(ld: dict) -> str:
    """Extract location string from JSON-LD jobLocation."""
    loc = ld.get("jobLocation", {})
    if not loc:
        return ""
    addr = loc.get("address", {})
    if not addr:
        return ""
    parts = []
    city = addr.get("addressLocality", "")
    state = addr.get("addressRegion", "")
    if city:
        parts.append(city)
    if state:
        parts.append(state)
    return ", ".join(parts)


def _fetch_agency_jobs(agency: str) -> list[dict]:
    """Fetch all nursing jobs from a single NEOGOV agency."""
    base_url = f"https://www.governmentjobs.com/careers/home/index"
    headers = {
        "Accept": "text/html, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": f"https://www.governmentjobs.com/careers/{agency}",
    }

    all_jobs = []
    seen_ids = set()

    for page in range(1, MAX_PAGES + 1):
        params = {
            "agency": agency,
            "sort": "PositionTitle",
            "isDescendingSort": "false",
            "page": page,
        }

        try:
            resp = requests.get(base_url, params=params, headers=headers, timeout=20)
            if resp.status_code != 200:
                logger.debug("[neogov] %d for %s page %d, stopping", resp.status_code, agency, page)
                break
        except Exception as e:
            logger.debug("[neogov] Error fetching %s page %d: %s", agency, page, e)
            break

        html = resp.text
        if not html or "job-postings" not in html.lower() and page > 1:
            break

        # Extract job links from the HTML fragment
        links = _JOB_LINK_RE.findall(html)
        if not links:
            break

        for href, job_id in links:
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)

            job_url = f"https://www.governmentjobs.com{href}"

            # We'll get the full data from the detail page JSON-LD
            # For now, create a minimal job record for filtering
            # Extract title from the listing HTML near this link
            all_jobs.append({
                "job_id": job_id,
                "url": job_url,
                "agency": agency,
            })

        # If we got fewer links than expected, we're on the last page
        if len(links) < JOBS_PER_PAGE:
            break

        # Polite delay
        time.sleep(random.uniform(0.8, 1.5))

    # Now fetch detail pages to get JSON-LD
    enriched_jobs = []
    for job_stub in all_jobs:
        try:
            detail_resp = requests.get(
                job_stub["url"],
                headers={"User-Agent": random.choice(USER_AGENTS)},
                timeout=15,
            )
            if detail_resp.status_code != 200:
                continue

            ld = _parse_jsonld(detail_resp.text)
            if not ld:
                continue

            title = ld.get("title", "")
            if not title:
                continue

            location = _extract_location(ld)
            posted = ld.get("datePosted", "")
            salary_min, salary_max = _extract_salary(ld)

            # Get employer name
            org = ld.get("hiringOrganization", {})
            company = org.get("name", "") if org else ""
            if not company:
                company = agency.replace("-", " ").title()

            desc_html = ld.get("description", "")

            job = {
                "title": title,
                "company": company,
                "ats": "neogov",
                "url": job_stub["url"],
                "location": location[:80] if location else "",
                "skill_level": "",
                "is_recruiter": False,
                "departments": [],
                "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }

            if posted:
                job["posted_date"] = posted[:10]

            if salary_min and salary_max:
                job["salary_min"] = salary_min
                job["salary_max"] = salary_max

            # Store description for pre-enrichment (skip enricher for these)
            if desc_html:
                job["_description_html"] = desc_html

            if is_nursing_job(job):
                enriched_jobs.append(job)

        except Exception as e:
            logger.debug("[neogov] Error fetching detail for %s: %s", job_stub["url"], e)
            continue

        # Polite delay between detail fetches
        time.sleep(random.uniform(0.3, 0.8))

    return enriched_jobs


def scrape_neogov() -> list[dict]:
    """Scrape all NEOGOV agencies and return nursing jobs."""
    agencies = _load_agencies()
    if not agencies:
        logger.info("[neogov] No NEOGOV agencies configured")
        return []

    logger.info("[neogov] Scraping %d NEOGOV agencies", len(agencies))
    all_nursing_jobs = []
    success = 0
    failed = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_agency_jobs, agency): agency
            for agency in agencies
        }
        for future in as_completed(futures):
            agency = futures[future]
            try:
                jobs = future.result()
                if jobs:
                    all_nursing_jobs.extend(jobs)
                    logger.debug("[neogov] %s: %d nursing jobs", agency, len(jobs))
                success += 1
            except Exception as e:
                logger.debug("[neogov] %s failed: %s", agency, e)
                failed += 1

    logger.info(
        "[neogov] Done: %d agencies scraped, %d failed, %d nursing jobs found",
        success, failed, len(all_nursing_jobs),
    )
    return all_nursing_jobs
