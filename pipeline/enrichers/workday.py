"""Workday ATS enricher."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

import requests

from pipeline.config import SALARY_RANGE_PATTERN, HOURLY_PATTERN

logger = logging.getLogger(__name__)

# Workday URL: https://{tenant}.wd{N}.myworkdayjobs.com/{site}/job/{location}/{slug}
URL_PATTERN = re.compile(
    r"https?://([^.]+)\.wd\d+\.myworkdayjobs\.com/(?:[^/]+/)?([^/]+)/job/[^/]+/([^/?]+)"
)

# "Posted Today", "Posted Yesterday", "Posted 30+ Days Ago", "Posted 3 Days Ago"
POSTED_PATTERN = re.compile(r"Posted\s+(.+)", re.IGNORECASE)


def _parse_posted_on(posted_on: str, start_date: str | None) -> str | None:
    """Parse Workday's 'postedOn' string into ISO date."""
    if start_date:
        return start_date

    if not posted_on:
        return None

    match = POSTED_PATTERN.match(posted_on)
    if not match:
        return None

    text = match.group(1).strip().lower()
    now = datetime.now(timezone.utc)

    if text == "today":
        return now.strftime("%Y-%m-%d")
    elif text == "yesterday":
        return (now - timedelta(days=1)).strftime("%Y-%m-%d")
    elif "30+" in text:
        return (now - timedelta(days=31)).strftime("%Y-%m-%d")
    else:
        # "3 Days Ago" etc
        days_match = re.search(r"(\d+)\s*days?\s*ago", text)
        if days_match:
            days = int(days_match.group(1))
            return (now - timedelta(days=days)).strftime("%Y-%m-%d")

    return None


def enrich_workday(job: dict) -> dict | None:
    """Fetch job details from Workday CXS API."""
    match = URL_PATTERN.search(job["url"])
    if not match:
        return None

    tenant, site, slug = match.groups()
    # Reconstruct the base domain from the original URL
    domain_match = re.match(r"(https?://[^/]+)", job["url"])
    if not domain_match:
        return None

    base = domain_match.group(1)
    api_url = f"{base}/wday/cxs/{tenant}/{site}/job/{slug}"

    try:
        resp = requests.get(api_url, headers={"Accept": "application/json"}, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.debug("Workday API error for %s: %s", job["url"], e)
        raise

    jpi = data.get("jobPostingInfo", {})
    if not jpi:
        return None

    result = {}

    posted_date = _parse_posted_on(jpi.get("postedOn", ""), jpi.get("startDate"))
    if posted_date:
        result["posted_date"] = posted_date

    desc = jpi.get("jobDescription", "")
    if desc:
        result["description_html"] = desc
        plain = re.sub(r"<[^>]+>", " ", desc)
        result["description_plain"] = re.sub(r"\s+", " ", plain).strip()

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
