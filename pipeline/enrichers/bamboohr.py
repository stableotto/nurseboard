"""BambooHR ATS enricher via JSON API."""

from __future__ import annotations

import logging
import re

import requests

from pipeline.salary import parse_salary

logger = logging.getLogger(__name__)

# BambooHR URL: https://{company}.bamboohr.com/careers/view/{id}
URL_PATTERN = re.compile(r"(https?://[^/]+\.bamboohr\.com)/careers/(?:view/)?(\d+)")


def enrich_bamboohr(job: dict) -> dict | None:
    """Fetch job details from BambooHR JSON API."""
    match = URL_PATTERN.search(job["url"])
    if not match:
        return None

    base, job_id = match.groups()
    api_url = f"{base}/careers/{job_id}/detail"

    try:
        resp = requests.get(
            api_url,
            headers={"Accept": "application/json", "User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.debug("BambooHR API error for %s: %s", job["url"], e)
        raise

    opening = data.get("result", {}).get("jobOpening", {})
    if not opening:
        return None

    result = {}

    # BambooHR doesn't expose reliable posted dates

    desc = opening.get("description", "")
    if desc:
        result["description_html"] = desc
        plain = re.sub(r"<[^>]+>", " ", desc)
        result["description_plain"] = re.sub(r"\s+", " ", plain).strip()

    # Parse salary from compensation field or description
    comp = opening.get("compensation", "")
    text = f"{comp} {result.get('description_plain', '')}"
    sal_min, sal_max = parse_salary(text)
    if sal_min:
        result["salary_min"] = sal_min
    if sal_max:
        result["salary_max"] = sal_max

    return result if result else None
