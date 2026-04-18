"""iCIMS ATS enricher.

Fetches job detail pages with ?in_iframe=1 to get the raw job content
(without the employer's custom wrapper site).
"""

from __future__ import annotations

import logging
import re

import requests

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html",
}

# Extract all description blocks (Overview, Responsibilities, Qualifications, etc.)
_DESC_BLOCK_RE = re.compile(
    r'<div\s+class="iCIMS_Expandable_Text">(.*?)</div>\s*</div>\s*</div>',
    re.DOTALL | re.IGNORECASE,
)

# Extract posted date from header fields
_DATE_RE = re.compile(
    r'Posted\s+Date.*?(\d{1,2}/\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}|\w+\s+\d{1,2},?\s+\d{4})',
    re.DOTALL | re.IGNORECASE,
)


def enrich_icims(job: dict) -> dict | None:
    """Fetch job details from an iCIMS career page."""
    url = job["url"]

    # Add in_iframe=1 to get the actual job content
    sep = "&" if "?" in url else "?"
    fetch_url = f"{url}{sep}in_iframe=1"

    try:
        resp = requests.get(fetch_url, headers=_HEADERS, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
    except Exception as e:
        logger.debug("iCIMS fetch error for %s: %s", url, e)
        raise

    html = resp.text

    # Extract all expandable text blocks (description sections)
    blocks = _DESC_BLOCK_RE.findall(html)
    if not blocks:
        return None

    desc_html = "\n".join(blocks)
    plain = re.sub(r"<[^>]+>", " ", desc_html)
    plain = re.sub(r"\s+", " ", plain).strip()

    if len(plain) < 50:
        return None

    result = {
        "description_html": desc_html,
        "description_plain": plain,
    }

    # Extract posted date
    date_match = _DATE_RE.search(html)
    if date_match:
        raw_date = date_match.group(1)
        # Convert MM/DD/YYYY to YYYY-MM-DD
        m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", raw_date)
        if m:
            result["posted_date"] = f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"
        else:
            result["posted_date"] = raw_date

    # Parse salary and bonus from description
    from pipeline.salary import parse_salary, parse_bonus
    sal_min, sal_max = parse_salary(plain)
    if sal_min:
        result["salary_min"] = sal_min
        result["salary_max"] = sal_max

    bonus = parse_bonus(plain)
    if bonus:
        result["bonus"] = bonus

    return result
