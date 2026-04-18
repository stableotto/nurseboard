"""Supplemental NEOGOV (governmentjobs.com) scraper.

Uses the global /jobs endpoint with healthcare keywords for discovery across
ALL agencies, then fetches individual job detail pages to extract JSON-LD
(schema.org/JobPosting) for structured data.

Two-pass approach:
  Pass 1 — Global keyword search for nursing and allied health jobs. Gets
           job URLs, titles, locations, salaries, and agency names from
           listing HTML.
  Pass 2 — Detail pages fetched for JSON-LD to get full descriptions.
           Jobs are pre-enriched at scrape time.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from pipeline.filter import is_healthcare_job

logger = logging.getLogger(__name__)

MAX_PAGES_PER_KEYWORD = 150  # Safety limit: 150 * 10 = 1500 per keyword
DETAIL_WORKERS = 3  # Conservative — NEOGOV rate-limits aggressively
JOBS_PER_PAGE = 10
DETAIL_DELAY = (1.0, 2.0)  # Delay between detail fetches per worker
PAGE_DELAY = (1.0, 2.0)  # Delay between listing pages

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
]

# Healthcare keywords to search globally — aligned with TITLE_KEYWORDS and SEO_CATEGORIES
SEARCH_KEYWORDS = [
    # Nursing — Core roles
    "registered nurse",
    "nurse practitioner",
    "LPN",
    "LVN",
    "CNA",
    "nursing",
    "CRNA",
    "APRN",
    # Nursing — Specialty
    "ICU nurse",
    "NICU",
    "med surg",
    "psychiatric nurse",
    "behavioral health nurse",
    "oncology nurse",
    "pediatric nurse",
    "labor delivery nurse",
    # Nursing — Settings
    "home health nurse",
    "hospice nurse",
    "public health nurse",
    # Nursing — Leadership
    "charge nurse",
    "nurse manager",
    "nurse educator",
    "clinical nurse",
    "director of nursing",
    # Nursing — Other
    "nurse midwife",
    "nurse navigator",
    "staff nurse",
    "case manager nurse",
    # Allied Health — Therapy
    "physical therapist",
    "physical therapy assistant",
    "occupational therapist",
    "occupational therapy assistant",
    "speech language pathologist",
    "speech therapist",
    "respiratory therapist",
    # Allied Health — Diagnostic / Lab
    "radiology technologist",
    "x-ray technologist",
    "MRI technologist",
    "CT technologist",
    "sonographer",
    "ultrasound technician",
    "medical laboratory technician",
    "lab technologist",
    "phlebotomist",
    # Allied Health — Pharmacy / Nutrition
    "pharmacist",
    "pharmacy technician",
    "dietitian",
    "nutritionist",
    # Allied Health — Other
    "medical assistant",
    "surgical technologist",
    "paramedic",
    "EMT",
    "dental hygienist",
    "clinical social worker",
    "athletic trainer",
]

# Regex to extract job links from the global /jobs HTML fragments
_JOB_LINK_RE = re.compile(
    r'href="(/jobs/(\d+-?\d*)/[^"]*)"',
    re.IGNORECASE,
)

# Extract job title from listing HTML
_JOB_TITLE_RE = re.compile(
    r'class="job-details-link"[^>]*>\s*([^<]+)',
    re.IGNORECASE,
)

# Extract organization/agency from listing HTML
_JOB_ORG_RE = re.compile(
    r'class="[^"]*job-organization[^"]*"[^>]*>\s*([^<]+)',
    re.IGNORECASE,
)

# Extract location from listing HTML
_JOB_LOC_RE = re.compile(
    r'class="[^"]*job-location[^"]*"[^>]*>\s*([^<]+)',
    re.IGNORECASE,
)

# Extract salary from listing HTML
_JOB_SALARY_RE = re.compile(
    r'class="[^"]*job-salary[^"]*"[^>]*>\s*([^<]+)',
    re.IGNORECASE,
)

# Regex for JSON-LD extraction from detail pages
_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)

# Split listing HTML into individual job blocks
_JOB_BLOCK_RE = re.compile(
    r'data-job-id="[^"]*".*?(?=data-job-id="|$)',
    re.DOTALL,
)


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


def _extract_salary_from_ld(ld: dict) -> tuple[int | None, int | None]:
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

    unit = (value.get("unitText") or "").upper()
    if unit == "HOUR":
        if low:
            low *= 2080
        if high:
            high *= 2080

    min_cents = int(low * 100) if low else None
    max_cents = int(high * 100) if high else None
    return min_cents, max_cents


def _extract_location_from_ld(ld: dict) -> str:
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


def _discover_jobs_for_keyword(keyword: str) -> list[dict]:
    """Search the global /jobs endpoint for a keyword, return job stubs."""
    base_url = "https://www.governmentjobs.com/jobs"
    headers = {
        "Accept": "text/html, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": random.choice(USER_AGENTS),
        "Referer": "https://www.governmentjobs.com/jobs",
    }

    stubs = []
    seen_ids = set()

    for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
        params = {
            "keyword": keyword,
            "sort": "date",
            "isDescendingSort": "true",
            "page": page,
        }

        try:
            resp = requests.get(base_url, params=params, headers=headers, timeout=20)
            if resp.status_code != 200:
                logger.debug("[neogov] %d for keyword '%s' page %d", resp.status_code, keyword, page)
                break
        except Exception as e:
            logger.debug("[neogov] Error searching '%s' page %d: %s", keyword, page, e)
            break

        html = resp.text
        if not html:
            break

        # Extract job links
        links = _JOB_LINK_RE.findall(html)
        if not links:
            break

        for href, job_id in links:
            if job_id in seen_ids:
                continue
            seen_ids.add(job_id)
            stubs.append({
                "job_id": job_id,
                "url": f"https://www.governmentjobs.com{href}",
            })

        if len(links) < JOBS_PER_PAGE:
            break

        # Polite delay between pages — NEOGOV rate-limits aggressively
        time.sleep(random.uniform(*PAGE_DELAY))

    return stubs


def _fetch_detail(job_stub: dict) -> dict | None:
    """Fetch a single job detail page and extract JSON-LD."""
    try:
        resp = requests.get(
            job_stub["url"],
            headers={"User-Agent": random.choice(USER_AGENTS)},
            timeout=15,
        )
        if resp.status_code != 200:
            return None

        ld = _parse_jsonld(resp.text)
        if not ld:
            return None

        title = ld.get("title", "")
        if not title:
            return None

        location = _extract_location_from_ld(ld)
        posted = ld.get("datePosted", "")
        salary_min, salary_max = _extract_salary_from_ld(ld)

        org = ld.get("hiringOrganization", {})
        company = org.get("name", "") if org else ""
        if not company:
            company = "Government Agency"

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

        if desc_html:
            job["_description_html"] = desc_html

        return job

    except Exception as e:
        logger.debug("[neogov] Error fetching detail for %s: %s", job_stub["url"], e)
        return None


def scrape_neogov() -> list[dict]:
    """Scrape NEOGOV globally for healthcare jobs across all agencies."""
    logger.info("[neogov] Searching governmentjobs.com globally with %d keywords", len(SEARCH_KEYWORDS))

    # Phase 1: Discover jobs across all keywords
    all_stubs = {}  # job_id -> stub (dedup across keywords)
    for keyword in SEARCH_KEYWORDS:
        stubs = _discover_jobs_for_keyword(keyword)
        new = 0
        for stub in stubs:
            if stub["job_id"] not in all_stubs:
                all_stubs[stub["job_id"]] = stub
                new += 1
        logger.info("[neogov] Keyword '%s': %d found, %d new (total: %d)", keyword, len(stubs), new, len(all_stubs))

    if not all_stubs:
        logger.info("[neogov] No jobs discovered")
        return []

    logger.info("[neogov] Discovered %d unique jobs, fetching details", len(all_stubs))

    # Phase 2: Fetch detail pages in parallel
    all_healthcare_jobs = []
    fetched = 0
    failed = 0

    stub_list = list(all_stubs.values())
    with ThreadPoolExecutor(max_workers=DETAIL_WORKERS) as executor:
        futures = {
            executor.submit(_fetch_detail, stub): stub["job_id"]
            for stub in stub_list
        }
        for future in as_completed(futures):
            job = future.result()
            if job and is_healthcare_job(job):
                all_healthcare_jobs.append(job)
                fetched += 1
            elif job:
                fetched += 1  # Got detail but not healthcare match
            else:
                failed += 1

    logger.info(
        "[neogov] Done: %d details fetched, %d failed, %d healthcare jobs found",
        fetched, failed, len(all_healthcare_jobs),
    )
    return all_healthcare_jobs
