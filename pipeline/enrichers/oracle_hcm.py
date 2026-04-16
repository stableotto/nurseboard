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


# Flex field prompts that indicate salary (employer-configured, not standardized)
_SALARY_MIN_PROMPTS = re.compile(
    r"(?:minimum|min)\s*(?:salary|pay|wage|rate|compensation|hourly)",
    re.IGNORECASE,
)
_SALARY_MAX_PROMPTS = re.compile(
    r"(?:maximum|max)\s*(?:salary|pay|wage|rate|compensation|hourly)",
    re.IGNORECASE,
)
_SALARY_SINGLE_PROMPTS = re.compile(
    r"^(?:salary|pay\s*rate|hourly\s*rate|wage\s*rate|compensation)$",
    re.IGNORECASE,
)


def _extract_flex_salary(flex_fields: list[dict]) -> tuple[int | None, int | None]:
    """Extract salary from requisitionFlexFields.

    Flex fields are employer-configured with varying prompt names.
    Values are typically bare numbers (hourly rates or annual amounts).
    """
    sal_min_val = None
    sal_max_val = None

    for field in flex_fields:
        prompt = (field.get("Prompt") or "").strip()
        value = (field.get("Value") or "").strip()
        if not prompt or not value:
            continue

        try:
            num = float(value.replace(",", ""))
        except (ValueError, TypeError):
            continue

        if num <= 0:
            continue

        if _SALARY_MIN_PROMPTS.search(prompt):
            sal_min_val = num
        elif _SALARY_MAX_PROMPTS.search(prompt):
            sal_max_val = num
        elif _SALARY_SINGLE_PROMPTS.match(prompt):
            sal_min_val = sal_min_val or num
            sal_max_val = sal_max_val or num

    if not sal_min_val and not sal_max_val:
        return None, None

    # Use whichever we have
    if sal_min_val and not sal_max_val:
        sal_max_val = sal_min_val
    elif sal_max_val and not sal_min_val:
        sal_min_val = sal_max_val

    # Heuristic: values under 300 are hourly, over 10k are annual
    if sal_min_val < 300:
        # Hourly -> annual
        min_cents = int(sal_min_val * 2080 * 100)
        max_cents = int(sal_max_val * 2080 * 100)
    elif sal_min_val >= 10_000:
        # Already annual
        min_cents = int(sal_min_val * 100)
        max_cents = int(sal_max_val * 100)
    else:
        # Ambiguous — skip
        return None, None

    return min_cents, max_cents


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

    # Salary: try flex fields first (structured data), then description text
    flex_fields = detail.get("requisitionFlexFields", [])
    if flex_fields:
        sal_min, sal_max = _extract_flex_salary(flex_fields)
        if sal_min:
            result["salary_min"] = sal_min
            result["salary_max"] = sal_max

    # Fallback: parse salary from description text
    if not result.get("salary_min"):
        sal_min, sal_max = parse_salary(result.get("description_plain", ""))
        if sal_min:
            result["salary_min"] = sal_min
        if sal_max:
            result["salary_max"] = sal_max

    return result if result else None
