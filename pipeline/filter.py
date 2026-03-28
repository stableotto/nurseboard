"""Filter jobs for nursing-related positions."""

import json
import logging

from pipeline.config import DEPARTMENT_KEYWORDS, TITLE_PATTERN

logger = logging.getLogger(__name__)


def is_nursing_job(job: dict) -> bool:
    """Check if a job matches nursing criteria."""
    title = job.get("title", "")
    if TITLE_PATTERN.search(title):
        return True

    departments = job.get("departments", [])
    if isinstance(departments, str):
        try:
            departments = json.loads(departments)
        except (json.JSONDecodeError, TypeError):
            departments = [departments]

    for dept in departments:
        if isinstance(dept, str) and DEPARTMENT_KEYWORDS.search(dept):
            return True

    return False


def filter_nursing_jobs(jobs: list[dict]) -> list[dict]:
    """Filter a list of jobs to only nursing-related positions."""
    nursing = [j for j in jobs if is_nursing_job(j)]
    logger.info("Filtered %d -> %d nursing jobs", len(jobs), len(nursing))
    return nursing
