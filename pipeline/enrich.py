"""Enrichment orchestrator with rate limiting and threading."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from pipeline.config import (
    CONSECUTIVE_FAIL_BACKOFF,
    CONSECUTIVE_FAIL_SKIP,
    RATE_LIMITS,
)
from pipeline.db import get_connection, get_unenriched, increment_failure, save_enrichment, mark_job_gone
from pipeline.enrichers.greenhouse import enrich_greenhouse
from pipeline.enrichers.lever import enrich_lever
from pipeline.enrichers.ashby import enrich_ashby
from pipeline.enrichers.workday import enrich_workday
from pipeline.enrichers.bamboohr import enrich_bamboohr
from pipeline.enrichers.oracle_hcm import enrich_oracle_hcm
from pipeline.enrichers.neogov import enrich_neogov

logger = logging.getLogger(__name__)

# Workable is not in the upstream data source
ENRICHERS = {
    "greenhouse": enrich_greenhouse,
    "lever": enrich_lever,
    "ashby": enrich_ashby,
    "workday": enrich_workday,
    "bamboohr": enrich_bamboohr,
    "oracle_hcm": enrich_oracle_hcm,
    "neogov": enrich_neogov,
}


class RateLimiter:
    """Simple per-ATS rate limiter."""

    def __init__(self, rps: float):
        self.min_interval = 1.0 / rps
        self.last_call = 0.0

    def wait(self):
        now = time.monotonic()
        elapsed = now - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.monotonic()


def enrich_ats(db_path: str, ats: str, enrich_fn, limit: int = 5000) -> dict:
    """Enrich jobs for a single ATS platform. Creates its own DB connection."""
    conn = get_connection(db_path)
    try:
        jobs = get_unenriched(conn, ats, limit=limit)
        if not jobs:
            return {"ats": ats, "total": 0, "success": 0, "failed": 0, "skipped": False}

        logger.info("[%s] Enriching %d jobs", ats, len(jobs))
        limiter = RateLimiter(RATE_LIMITS.get(ats, 3))
        consecutive_failures = 0
        success = 0
        failed = 0

        for job in jobs:
            if consecutive_failures >= CONSECUTIVE_FAIL_SKIP:
                logger.warning("[%s] %d consecutive failures, skipping remaining", ats, consecutive_failures)
                return {"ats": ats, "total": len(jobs), "success": success, "failed": failed, "skipped": True}

            if consecutive_failures >= CONSECUTIVE_FAIL_BACKOFF:
                backoff = min(2 ** (consecutive_failures - CONSECUTIVE_FAIL_BACKOFF), 30)
                logger.info("[%s] Backing off %ds after %d failures", ats, backoff, consecutive_failures)
                time.sleep(backoff)

            limiter.wait()

            try:
                data = enrich_fn(job)
                if data:
                    save_enrichment(conn, job["url"], data)
                    conn.commit()
                    consecutive_failures = 0
                    success += 1
                else:
                    # enricher returned None = job not found / URL didn't match
                    # Don't count as consecutive failure (likely stale listing)
                    mark_job_gone(conn, job["url"])
                    conn.commit()
                    failed += 1
            except requests.exceptions.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    # Job removed from ATS — not a real failure
                    mark_job_gone(conn, job["url"])
                    conn.commit()
                    failed += 1
                elif e.response is not None and e.response.status_code == 403:
                    # Forbidden — likely geo-block or bot detection, skip job but don't panic
                    increment_failure(conn, job["url"])
                    conn.commit()
                    failed += 1
                else:
                    logger.warning("[%s] Error enriching %s: %s", ats, job["url"], e)
                    increment_failure(conn, job["url"])
                    conn.commit()
                    consecutive_failures += 1
                    failed += 1
            except Exception as e:
                logger.warning("[%s] Error enriching %s: %s", ats, job["url"], e)
                increment_failure(conn, job["url"])
                conn.commit()
                consecutive_failures += 1
                failed += 1

        return {"ats": ats, "total": len(jobs), "success": success, "failed": failed, "skipped": False}
    finally:
        conn.close()


def enrich_all(db_path: str):
    """Run enrichment across all ATS platforms concurrently."""
    results = []
    with ThreadPoolExecutor(max_workers=len(ENRICHERS)) as executor:
        futures = {
            executor.submit(enrich_ats, db_path, ats, fn): ats
            for ats, fn in ENRICHERS.items()
        }
        for future in as_completed(futures):
            ats = futures[future]
            try:
                result = future.result()
                results.append(result)
                logger.info(
                    "[%s] Done: %d/%d success, skipped=%s",
                    ats, result["success"], result["total"], result["skipped"],
                )
            except Exception as e:
                logger.error("[%s] Enrichment failed: %s", ats, e)
                results.append({"ats": ats, "total": 0, "success": 0, "failed": 0, "skipped": True})

    return results
