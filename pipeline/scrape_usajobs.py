"""Supplemental USAJobs scraper for federal healthcare positions.

Uses the official USAJobs Search API to fetch nursing and allied health
jobs from federal agencies (VA hospitals, DoD, IHS, etc.).

Jobs come fully enriched — description, salary, location, and posted date
are all available from the API response, so no separate enrichment step
is needed.

Requires a free API key from https://developer.usajobs.gov/
Set USAJOBS_API_KEY and USAJOBS_EMAIL environment variables.
"""

from __future__ import annotations

import logging
import os
import re
import time

import requests

from pipeline.filter import is_healthcare_job
from pipeline.salary import parse_bonus

logger = logging.getLogger(__name__)

API_BASE = "https://data.usajobs.gov/api/Search"
RESULTS_PER_PAGE = 500

# Federal healthcare occupational series codes
JOB_CATEGORY_CODES = [
    "0610",  # Nurse
    "0620",  # Practical Nurse
    "0621",  # Nursing Assistant
    "0630",  # Dietitian / Nutritionist
    "0631",  # Occupational Therapist
    "0633",  # Physical Therapist
    "0635",  # Corrective Therapist
    "0636",  # Rehabilitation Therapy Assistant
    "0640",  # Health Aid and Technician
    "0642",  # Nuclear Medicine Technician
    "0644",  # Medical Technologist
    "0645",  # Medical Technician
    "0646",  # Pathology Technician
    "0647",  # Diagnostic Radiologic Technologist
    "0648",  # Therapeutic Radiologic Technologist
    "0649",  # Medical Instrument Technician
    "0660",  # Pharmacist
    "0661",  # Pharmacy Technician
    "0665",  # Speech Pathology and Audiology
    "0680",  # Dental Officer
    "0681",  # Dental Hygienist
    "0682",  # Dental Assistant
    "0683",  # Dental Lab Aid / Technician
    "0601",  # General Health Science
    "0602",  # Medical Officer
    "0603",  # Physician Assistant
]


def _get_credentials() -> tuple[str, str] | None:
    """Get API key and email from environment."""
    api_key = os.environ.get("USAJOBS_API_KEY")
    email = os.environ.get("USAJOBS_EMAIL")
    if not api_key or not email:
        return None
    return api_key, email


def _fetch_page(headers: dict, params: dict, page: int) -> dict | None:
    """Fetch a single page of results."""
    params = {**params, "Page": page}
    try:
        resp = requests.get(API_BASE, headers=headers, params=params, timeout=30)
        if resp.status_code != 200:
            logger.warning("[usajobs] API returned %d on page %d", resp.status_code, page)
            return None
        return resp.json()
    except Exception as e:
        logger.warning("[usajobs] Error fetching page %d: %s", page, e)
        return None


def _parse_salary(remuneration: list[dict]) -> tuple[int | None, int | None]:
    """Extract annual salary from remuneration data."""
    if not remuneration:
        return None, None

    for rem in remuneration:
        interval = rem.get("RateIntervalCode", "")
        try:
            raw_min = rem.get("MinimumRange", "0")
            raw_max = rem.get("MaximumRange", "0")
            sal_min = int(float(raw_min))
            sal_max = int(float(raw_max))
        except (ValueError, TypeError):
            continue

        if sal_min <= 0:
            continue

        # Convert hourly to annual estimate
        if interval == "PH":
            sal_min = sal_min * 2080
            sal_max = sal_max * 2080

        # Sanity check — skip per-diem or weird values
        if sal_min < 15000 or sal_min > 500000:
            continue

        return sal_min, sal_max

    return None, None


def _parse_location(position_locations: list[dict]) -> str:
    """Extract 'City, ST' from the first US location."""
    if not position_locations:
        return ""

    loc = position_locations[0]
    city = loc.get("CityName", "")
    state = loc.get("CountrySubDivisionCode", "")

    # CountrySubDivisionCode comes as full state name (e.g., "California")
    # or sometimes as "State-Abbr" — normalize to abbreviation
    if state and len(state) == 2:
        return f"{city}, {state}" if city else state

    # Full state name — the export normalizer will convert it
    if city and state:
        return f"{city}, {state}"
    return city or state or ""


def _parse_job(item: dict) -> dict | None:
    """Parse a single search result item into our job format."""
    mo = item.get("MatchedObjectDescriptor", {})
    if not mo:
        return None

    title = mo.get("PositionTitle", "")
    if not title:
        return None

    # Build location from first position location
    locations = mo.get("PositionLocation", [])
    location = _parse_location(locations)

    # Organization / agency name
    org_name = mo.get("OrganizationName", "")
    dept_name = mo.get("DepartmentName", "")
    # Use org name as company, fall back to department
    company_name = org_name or dept_name or "U.S. Federal Government"

    # Company slug from org name
    company_slug = re.sub(r"[^a-z0-9]+", "", org_name.lower())[:40] or "usgov"

    # Job URL
    job_url = mo.get("PositionURI", "")
    if not job_url:
        return None

    # Posted date
    pub_date = mo.get("PublicationStartDate", "")
    posted_date = pub_date[:10] if pub_date else None

    # Salary
    remuneration = mo.get("PositionRemuneration", [])
    salary_min, salary_max = _parse_salary(remuneration)

    # Description — combine available text fields
    details = mo.get("UserArea", {}).get("Details", {})
    major_duties = details.get("MajorDuties", "")
    job_summary = details.get("JobSummary", "")
    qualifications = mo.get("QualificationSummary", "")

    # Build HTML description from available sections
    desc_parts = []
    if job_summary:
        desc_parts.append(f"<h3>Summary</h3>{job_summary}")
    if major_duties:
        desc_parts.append(f"<h3>Duties</h3>{major_duties}")
    if qualifications:
        desc_parts.append(f"<h3>Qualifications</h3>{qualifications}")

    desc_html = "\n".join(desc_parts)
    desc_plain = ""
    if desc_html:
        desc_plain = re.sub(r"<[^>]+>", " ", desc_html)
        desc_plain = re.sub(r"\s+", " ", desc_plain).strip()

    # Parse bonus from description
    bonus = parse_bonus(desc_plain) if desc_plain else None

    # Departments / categories
    categories = mo.get("JobCategory", [])
    departments = [c.get("Name", "") for c in categories if c.get("Name")]

    job = {
        "title": title,
        "company": company_slug,
        "company_name": company_name,
        "ats": "usajobs",
        "url": job_url,
        "location": location,
        "skill_level": "",
        "is_recruiter": False,
        "departments": departments,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    if posted_date:
        job["posted_date"] = posted_date
    if desc_html:
        job["description_html"] = desc_html
        job["description_plain"] = desc_plain
    if salary_min:
        job["salary_min"] = salary_min
        job["salary_max"] = salary_max
    if bonus:
        job["bonus"] = bonus

    return job


def scrape_usajobs() -> list[dict]:
    """Fetch healthcare jobs from USAJobs API. Returns pre-enriched job dicts."""
    creds = _get_credentials()
    if not creds:
        logger.info("[usajobs] No API credentials set (USAJOBS_API_KEY, USAJOBS_EMAIL), skipping")
        return []

    api_key, email = creds

    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": email,
        "Authorization-Key": api_key,
    }

    # Search using healthcare occupation codes
    params = {
        "JobCategoryCode": ";".join(JOB_CATEGORY_CODES),
        "ResultsPerPage": RESULTS_PER_PAGE,
        "Fields": "full",
        "WhoMayApply": "public",
        "Country": "United States",
    }

    logger.info("[usajobs] Fetching healthcare jobs (codes: %d categories)", len(JOB_CATEGORY_CODES))

    # Fetch first page to get total count
    data = _fetch_page(headers, params, page=1)
    if not data:
        logger.warning("[usajobs] Failed to fetch first page")
        return []

    search_result = data.get("SearchResult", {})
    total = search_result.get("SearchResultCountAll", 0)
    num_pages = int(search_result.get("UserArea", {}).get("NumberOfPages", "1"))

    logger.info("[usajobs] %d total jobs across %d pages", total, num_pages)

    # Parse first page
    all_jobs = []
    items = search_result.get("SearchResultItems", [])
    for item in items:
        job = _parse_job(item)
        if job:
            all_jobs.append(job)

    # Fetch remaining pages
    for page in range(2, num_pages + 1):
        time.sleep(0.5)  # Be polite
        data = _fetch_page(headers, params, page)
        if not data:
            continue

        items = data.get("SearchResult", {}).get("SearchResultItems", [])
        for item in items:
            job = _parse_job(item)
            if job:
                all_jobs.append(job)

        if page % 5 == 0:
            logger.info("[usajobs] Fetched page %d/%d (%d jobs so far)", page, num_pages, len(all_jobs))

    # Additional filter through our healthcare keyword matcher for safety
    filtered = [j for j in all_jobs if is_healthcare_job(j)]

    logger.info(
        "[usajobs] Done: %d jobs fetched, %d matched healthcare filter",
        len(all_jobs), len(filtered),
    )
    return filtered
