"""NEOGOV ATS enricher.

Fetches the job detail page and extracts JSON-LD (schema.org/JobPosting)
for structured data including description, salary, posted date, and location.

Many NEOGOV jobs arrive pre-enriched from the scraper (which already fetches
JSON-LD during discovery). This enricher handles jobs found via upstream
sources that only have URLs.
"""

from __future__ import annotations

import json
import logging
import re

import requests

from pipeline.config import SALARY_RANGE_PATTERN, HOURLY_PATTERN

logger = logging.getLogger(__name__)

# NEOGOV URL patterns
URL_PATTERN = re.compile(
    r"https?://(?:www\.)?governmentjobs\.com/(?:careers/[^/]+/jobs/\d+|jobs/\d+)"
)

_JSONLD_RE = re.compile(
    r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
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

    unit = (value.get("unitText") or "").upper()
    if unit == "HOUR":
        if low:
            low *= 2080
        if high:
            high *= 2080

    min_cents = int(low * 100) if low else None
    max_cents = int(high * 100) if high else None
    return min_cents, max_cents


def enrich_neogov(job: dict) -> dict | None:
    """Fetch job details from NEOGOV via JSON-LD."""
    if not URL_PATTERN.search(job["url"]):
        return None

    try:
        resp = requests.get(
            job["url"],
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
            },
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except Exception as e:
        logger.debug("NEOGOV fetch error for %s: %s", job["url"], e)
        raise

    ld = _parse_jsonld(resp.text)
    if not ld:
        return None

    result = {}

    # Description
    desc = ld.get("description", "")
    if desc:
        result["description_html"] = desc
        plain = re.sub(r"<[^>]+>", " ", desc)
        result["description_plain"] = re.sub(r"\s+", " ", plain).strip()

    # Posted date
    posted = ld.get("datePosted", "")
    if posted:
        result["posted_date"] = posted[:10]

    # Company name
    org = ld.get("hiringOrganization", {})
    if org and org.get("name"):
        result["company_name"] = org["name"]

    # Salary from JSON-LD
    salary_min, salary_max = _extract_salary(ld)
    if salary_min or salary_max:
        result["salary_min"] = salary_min
        result["salary_max"] = salary_max
    else:
        # Fallback: parse salary from description text
        text = result.get("description_plain", "")
        salary_match = SALARY_RANGE_PATTERN.search(text)
        if salary_match:
            low = float(salary_match.group(1).replace(",", ""))
            high = float(salary_match.group(2).replace(",", ""))
            if HOURLY_PATTERN.search(text[salary_match.start():salary_match.end() + 20]):
                low *= 2080
                high *= 2080
            result["salary_min"] = int(low * 100)
            result["salary_max"] = int(high * 100)

    return result if result else None
