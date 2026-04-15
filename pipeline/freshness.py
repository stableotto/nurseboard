"""Freshness checker: verify enriched job URLs are still live.

Checks a batch of the oldest enriched jobs each run using ATS-specific
methods. Removes any that are confirmed gone (404/410).
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from pipeline.db import get_connection

logger = logging.getLogger(__name__)

# Check the oldest N enriched jobs per run
BATCH_SIZE = 500
MAX_WORKERS = 10
TIMEOUT = 10

USER_AGENT = "Mozilla/5.0 (compatible; ScrubShifts/1.0)"

# BambooHR page URLs 404 even for live jobs; use the API instead
_BAMBOO_RE = re.compile(r"(https?://[^/]+\.bamboohr\.com)/careers/(?:view/)?(\d+)")
# Oracle HCM: use the REST API detail endpoint
_ORACLE_RE = re.compile(
    r"https?://([^/]+)/hcmUI/CandidateExperience/\w+/sites/([^/]+)/(?:job|requisitions?)/(\d+)"
)


def _check_url(url: str, ats: str) -> tuple[str, bool]:
    """Check if a job URL is still live. Returns (url, is_alive)."""
    try:
        # BambooHR: check the JSON API, not the HTML page
        m = _BAMBOO_RE.search(url)
        if m:
            base, job_id = m.groups()
            api_url = f"{base}/careers/{job_id}/detail"
            resp = requests.get(
                api_url,
                headers={"Accept": "application/json", "User-Agent": USER_AGENT},
                timeout=TIMEOUT,
            )
            if resp.status_code in (404, 410):
                return url, False
            if resp.status_code == 200:
                data = resp.json()
                if not data.get("result", {}).get("jobOpening"):
                    return url, False
            return url, True

        # Oracle HCM: check the REST API
        m = _ORACLE_RE.search(url)
        if m:
            host, site, job_id = m.groups()
            from urllib.parse import quote
            api_url = (
                f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails"
                f"?onlyData=true&finder=ById;Id={quote(chr(34) + job_id + chr(34))},siteNumber={site}"
            )
            resp = requests.get(
                api_url,
                headers={"Accept": "application/json"},
                timeout=TIMEOUT,
            )
            if resp.status_code in (404, 410):
                return url, False
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                if not items:
                    return url, False
            return url, True

        # Default: HEAD request
        resp = requests.head(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=TIMEOUT,
            allow_redirects=True,
        )
        if resp.status_code in (404, 410):
            return url, False
        return url, True

    except requests.exceptions.ConnectionError:
        return url, True  # Host unreachable — keep, might be temporary
    except Exception:
        return url, True  # Timeout, SSL, etc — keep


def check_freshness(db_path: str) -> dict:
    """Check a batch of the oldest enriched jobs for freshness.

    Returns {"checked": N, "removed": N}.
    """
    conn = get_connection(db_path)

    # Get the oldest enriched jobs (by enriched_at) that haven't been removed
    rows = conn.execute(
        """SELECT url, ats_platform FROM jobs
        WHERE enriched_at IS NOT NULL
          AND removed_at IS NULL
        ORDER BY enriched_at ASC
        LIMIT ?""",
        (BATCH_SIZE,),
    ).fetchall()

    jobs = [(r["url"], r["ats_platform"]) for r in rows]
    if not jobs:
        return {"checked": 0, "removed": 0}

    logger.info("[freshness] Checking %d oldest enriched jobs", len(jobs))

    dead_urls = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(_check_url, url, ats): url for url, ats in jobs}
        for future in as_completed(futures):
            url, alive = future.result()
            if not alive:
                dead_urls.append(url)

    if dead_urls:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn.executemany(
            "UPDATE jobs SET removed_at = ?, updated_at = ? WHERE url = ?",
            [(now, now, url) for url in dead_urls],
        )
        conn.commit()
        logger.info("[freshness] Removed %d stale jobs (404/410)", len(dead_urls))
    else:
        logger.info("[freshness] All %d jobs still live", len(urls))

    conn.close()
    return {"checked": len(urls), "removed": len(dead_urls)}
