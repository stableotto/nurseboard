"""Oracle HCM ATS enricher.

Fetches the full job detail from the recruitingCEJobRequisitionDetails
endpoint to get full HTML description and parse salary from it.
"""

from __future__ import annotations

import logging
import re
from urllib.parse import quote

import requests

from pipeline.salary import parse_salary

logger = logging.getLogger(__name__)

# Oracle HCM URL: https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{id}
URL_PATTERN = re.compile(
    r"https?://([^/]+)/hcmUI/CandidateExperience/\w+/sites/([^/]+)/(?:job|requisitions?)/(\d+)"
)


def enrich_oracle_hcm(job: dict) -> dict | None:
    """Fetch job details from Oracle HCM CE API."""
    match = URL_PATTERN.search(job["url"])
    if not match:
        return None

    host, site_number, job_id = match.groups()
    base = f"https://{host}"

    # The detail endpoint requires the ID to be double-quoted and URL-encoded
    encoded_id = quote(f'"{job_id}"')
    detail_url = (
        f"{base}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
        f"?expand=all&onlyData=true"
        f"&finder=ById;Id={encoded_id},siteNumber={site_number}"
    )

    try:
        resp = requests.get(
            detail_url,
            headers={"Accept": "application/json"},
            timeout=15,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        logger.debug("Oracle HCM API error for %s: %s", job["url"], e)
        raise

    items = data.get("items", [])
    if not items:
        return None

    detail = items[0]
    result = {}

    # Full HTML description
    desc = detail.get("ExternalDescriptionStr", "")
    quals = detail.get("ExternalQualificationsStr", "")
    resps = detail.get("ExternalResponsibilitiesStr", "")

    # Combine all description parts
    full_html = desc
    if resps:
        full_html += f"\n<h3>Responsibilities</h3>\n{resps}"
    if quals:
        full_html += f"\n<h3>Qualifications</h3>\n{quals}"

    if full_html:
        result["description_html"] = full_html
        plain = re.sub(r"<[^>]+>", " ", full_html)
        result["description_plain"] = re.sub(r"\s+", " ", plain).strip()

    # Posted date
    posted = detail.get("ExternalPostedStartDate") or detail.get("PostedDate", "")
    if posted:
        result["posted_date"] = posted[:10]

    # Company name from LegalEmployer or Organization
    company = detail.get("Organization") or detail.get("LegalEmployer") or ""
    if company:
        result["company_name"] = company

    # Parse salary from full description text
    sal_min, sal_max = parse_salary(result.get("description_plain", ""))
    if sal_min:
        result["salary_min"] = sal_min
    if sal_max:
        result["salary_max"] = sal_max

    return result if result else None
