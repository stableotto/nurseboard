"""Filter jobs for nursing and allied health positions."""

import json
import logging

from pipeline.config import DEPARTMENT_KEYWORDS, TITLE_PATTERN

logger = logging.getLogger(__name__)


def is_healthcare_job(job: dict) -> bool:
    """Check if a job matches nursing or allied health criteria."""
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


# Backward-compatible alias
is_nursing_job = is_healthcare_job


def filter_healthcare_jobs(jobs: list[dict]) -> list[dict]:
    """Filter a list of jobs to nursing and allied health positions."""
    matched = [j for j in jobs if is_healthcare_job(j)]
    logger.info("Filtered %d -> %d healthcare jobs", len(jobs), len(matched))
    return matched


# Backward-compatible alias
filter_nursing_jobs = filter_healthcare_jobs
