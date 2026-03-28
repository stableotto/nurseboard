"""Lever ATS enricher."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

import requests

from pipeline.config import SALARY_RANGE_PATTERN, HOURLY_PATTERN

logger = logging.getLogger(__name__)

# Lever URL pattern: https://jobs.lever.co/{company}/{id}
URL_PATTERN = re.compile(r"jobs\.lever\.co/([^/]+)/([a-f0-9-]+)")


def enrich_lever(job: dict) -> dict | None:
    """Fetch job details from Lever API."""
    match = URL_PATTERN.search(job["url"])
    if not match:
        return None

    company, posting_id = match.groups()
    api_url = f"https://api.lever.co/v0/postings/{company}/{posting_id}"

    try:
        resp = requests.get(api_url, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.debug("Lever API error for %s: %s", job["url"], e)
        raise

    result = {}

    created_at = data.get("createdAt")
    if created_at:
        result["posted_date"] = datetime.fromtimestamp(
            created_at / 1000, tz=timezone.utc
        ).isoformat()

    desc_parts = []
    if data.get("description"):
        desc_parts.append(data["description"])
    for lst in data.get("lists", []):
        if lst.get("text"):
            desc_parts.append(f"<h3>{lst['text']}</h3>")
        if lst.get("content"):
            desc_parts.append(lst["content"])

    if desc_parts:
        result["description_html"] = "\n".join(desc_parts)
        plain = re.sub(r"<[^>]+>", " ", result["description_html"])
        result["description_plain"] = re.sub(r"\s+", " ", plain).strip()

    additional = data.get("additionalPlain") or ""
    full_text = (result.get("description_plain") or "") + " " + additional
    salary_match = SALARY_RANGE_PATTERN.search(full_text)
    if salary_match:
        low = float(salary_match.group(1).replace(",", ""))
        high = float(salary_match.group(2).replace(",", ""))
        if HOURLY_PATTERN.search(full_text[salary_match.start():salary_match.end() + 20]):
            low *= 2080
            high *= 2080
        result["salary_min"] = int(low * 100)
        result["salary_max"] = int(high * 100)

    return result
