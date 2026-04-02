"""Greenhouse ATS enricher."""

from __future__ import annotations

import logging
import re

import requests

logger = logging.getLogger(__name__)

# Standard: https://job-boards.greenhouse.io/{slug}/jobs/{id}
# or: https://boards.greenhouse.io/{slug}/jobs/{id}
BOARD_PATTERN = re.compile(r"(?:job-)?boards\.greenhouse\.io/([^/]+)/jobs/(\d+)")

# Custom domain with gh_jid param: https://example.com/careers?gh_jid=12345
GH_JID_PATTERN = re.compile(r"[?&]gh_jid=(\d+)")


def _fetch_job(slug: str, job_id: str) -> dict | None:
    """Fetch from Greenhouse boards API."""
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}?pay_transparency=true"
    resp = requests.get(api_url, timeout=15)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()


def enrich_greenhouse(job: dict) -> dict | None:
    """Fetch job details from Greenhouse API."""
    url = job["url"]
    slug = None
    job_id = None

    match = BOARD_PATTERN.search(url)
    if match:
        slug, job_id = match.groups()
    else:
        jid_match = GH_JID_PATTERN.search(url)
        if jid_match:
            job_id = jid_match.group(1)
            slug = job.get("company_slug", "")
        else:
            return None

    if not slug or not job_id:
        return None

    try:
        data = _fetch_job(slug, job_id)
        if not data:
            return None
    except Exception as e:
        logger.debug("Greenhouse API error for %s: %s", url, e)
        raise

    content = data.get("content") or ""
    # Greenhouse sometimes returns double-escaped HTML entities
    if "&lt;" in content and "<p>" not in content:
        import html
        content = html.unescape(content)

    result = {
        "posted_date": data.get("updated_at"),
        "description_html": content or None,
        "company_name": data.get("company_name"),
    }

    if result["description_html"]:
        plain = re.sub(r"<[^>]+>", " ", result["description_html"])
        result["description_plain"] = re.sub(r"\s+", " ", plain).strip()

    pay_ranges = data.get("pay_input_ranges") or []
    if pay_ranges:
        pr = pay_ranges[0]
        min_val = pr.get("min_cents")
        max_val = pr.get("max_cents")
        currency = pr.get("currency_type", "USD")

        if min_val is not None:
            result["salary_min"] = int(min_val)
        if max_val is not None:
            result["salary_max"] = int(max_val)
        result["salary_currency"] = currency

    return result
