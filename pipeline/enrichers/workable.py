"""Workable ATS enricher."""

from __future__ import annotations

import json
import logging
import re

import requests

from pipeline.config import SALARY_RANGE_PATTERN, HOURLY_PATTERN

logger = logging.getLogger(__name__)

# Workable URL pattern: https://apply.workable.com/j/{id}/ or https://apply.workable.com/{company}/j/{id}/
URL_PATTERN = re.compile(r"apply\.workable\.com/(?:([^/]+)/)?j/([^/]+)")


def enrich_workable(job: dict) -> dict | None:
    """Fetch job details from Workable widget API or HTML page."""
    match = URL_PATTERN.search(job["url"])
    if not match:
        return None

    company, shortcode = match.groups()

    # Try the widget API first
    if company:
        result = _try_widget_api(company, shortcode)
        if result:
            return result

    # Fall back to scraping the page for JSON-LD
    return _try_jsonld(job["url"])


def _try_widget_api(company: str, shortcode: str) -> dict | None:
    """Try the Workable widget API."""
    api_url = f"https://apply.workable.com/api/v1/widget/accounts/{company}?details=true"
    try:
        resp = requests.get(api_url, timeout=15)
        if resp.status_code != 200:
            return None
        data = resp.json()

        for posting in data.get("jobs", []):
            if posting.get("shortcode") == shortcode:
                return _parse_posting(posting)
    except Exception as e:
        logger.debug("Workable widget API error: %s", e)
    return None


def _parse_posting(posting: dict) -> dict:
    result = {}

    if posting.get("created_at"):
        result["posted_date"] = posting["created_at"]

    if posting.get("description"):
        result["description_html"] = posting["description"]
        plain = re.sub(r"<[^>]+>", " ", posting["description"])
        result["description_plain"] = re.sub(r"\s+", " ", plain).strip()

    salary = posting.get("salary")
    if salary:
        if salary.get("salary_from"):
            result["salary_min"] = int(float(salary["salary_from"]) * 100)
        if salary.get("salary_to"):
            result["salary_max"] = int(float(salary["salary_to"]) * 100)
        if salary.get("salary_currency"):
            result["salary_currency"] = salary["salary_currency"]

    if not result.get("salary_min") and result.get("description_plain"):
        text = result["description_plain"]
        salary_match = SALARY_RANGE_PATTERN.search(text)
        if salary_match:
            low = float(salary_match.group(1).replace(",", ""))
            high = float(salary_match.group(2).replace(",", ""))
            if HOURLY_PATTERN.search(text[salary_match.start():salary_match.end() + 20]):
                low *= 2080
                high *= 2080
            result["salary_min"] = int(low * 100)
            result["salary_max"] = int(high * 100)

    return result


def _try_jsonld(url: str) -> dict | None:
    """Scrape JSON-LD from the job page."""
    try:
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            return None

        ld_match = re.search(
            r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>',
            resp.text, re.DOTALL,
        )
        if not ld_match:
            return None

        ld = json.loads(ld_match.group(1))
        if isinstance(ld, list):
            ld = next((x for x in ld if x.get("@type") == "JobPosting"), None)
        if not ld or ld.get("@type") != "JobPosting":
            return None

        result = {}
        if ld.get("datePosted"):
            result["posted_date"] = ld["datePosted"]
        if ld.get("description"):
            result["description_html"] = ld["description"]
            plain = re.sub(r"<[^>]+>", " ", ld["description"])
            result["description_plain"] = re.sub(r"\s+", " ", plain).strip()

        salary = ld.get("baseSalary", {}).get("value", {})
        if salary:
            if salary.get("minValue"):
                result["salary_min"] = int(float(salary["minValue"]) * 100)
            if salary.get("maxValue"):
                result["salary_max"] = int(float(salary["maxValue"]) * 100)
            currency = ld.get("baseSalary", {}).get("currency")
            if currency:
                result["salary_currency"] = currency

        return result if result else None
    except Exception as e:
        logger.debug("Workable JSON-LD error for %s: %s", url, e)
        raise
