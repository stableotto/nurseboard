"""Pipeline entry point."""

import logging
import sys

from pipeline.config import DB_PATH
from pipeline.db import (
    get_connection, get_exportable_jobs, get_stats,
    mark_removed, upsert_job, delete_unenriched, save_enrichment,
)
from pipeline.download import download_upstream_jobs
from pipeline.enrich import enrich_all
from pipeline.export import export_for_frontend
from pipeline.filter import filter_nursing_jobs
from pipeline.scrape_workday import scrape_extra_workday
from pipeline.scrape_oracle_hcm import scrape_oracle_hcm
from pipeline.scrape_neogov import scrape_neogov

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting nursing job pipeline")

    # 1. Download upstream jobs
    all_jobs = download_upstream_jobs()

    # 2. Filter for nursing jobs
    nursing_jobs = filter_nursing_jobs(all_jobs)
    if not nursing_jobs:
        logger.warning("No nursing jobs found from upstream!")

    # 2b. Scrape extra Workday companies
    extra_jobs = scrape_extra_workday()
    if extra_jobs:
        nursing_jobs.extend(extra_jobs)
        logger.info("Added %d extra Workday jobs", len(extra_jobs))

    # 2c. Scrape Oracle HCM career sites
    oracle_jobs = scrape_oracle_hcm()
    if oracle_jobs:
        nursing_jobs.extend(oracle_jobs)
        logger.info("Added %d Oracle HCM jobs", len(oracle_jobs))

    # 2d. Scrape NEOGOV agencies
    neogov_jobs = scrape_neogov()
    if neogov_jobs:
        nursing_jobs.extend(neogov_jobs)
        logger.info("Added %d NEOGOV jobs", len(neogov_jobs))

    if extra_jobs or oracle_jobs or neogov_jobs:
        logger.info("Total nursing jobs (upstream + extra): %d", len(nursing_jobs))

    if not nursing_jobs:
        logger.warning("No nursing jobs found at all! Exiting.")
        sys.exit(1)

    # 3. Upsert into SQLite — track which are new this run
    conn = get_connection(DB_PATH)
    existing_before = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    new_count = 0
    new_by_ats = {}
    updated_count = 0
    current_urls = set()
    pre_enriched = []
    for job in nursing_jobs:
        current_urls.add(job["url"])
        is_new = upsert_job(conn, job)
        if is_new:
            new_count += 1
            ats = (job.get("ats") or "").lower()
            new_by_ats[ats] = new_by_ats.get(ats, 0) + 1
            # NEOGOV scraper provides description via JSON-LD at scrape time
            if job.get("_description_html"):
                pre_enriched.append(job)
        else:
            updated_count += 1
    conn.commit()

    # Save pre-enriched data (NEOGOV jobs with descriptions from scraper)
    if pre_enriched:
        import re as _re
        for job in pre_enriched:
            html = job["_description_html"]
            plain = _re.sub(r"<[^>]+>", " ", html)
            plain = _re.sub(r"\s+", " ", plain).strip()
            enrich_data = {
                "description_html": html,
                "description_plain": plain,
                "company_name": job.get("company"),
            }
            if job.get("posted_date"):
                enrich_data["posted_date"] = job["posted_date"]
            if job.get("salary_min"):
                enrich_data["salary_min"] = job["salary_min"]
            if job.get("salary_max"):
                enrich_data["salary_max"] = job["salary_max"]
            save_enrichment(conn, job["url"], enrich_data)
        conn.commit()
        logger.info("  Pre-enriched %d NEOGOV jobs from scraper", len(pre_enriched))
    logger.info("=== Upsert Breakdown ===")
    logger.info("  Upstream nursing jobs: %d", len(nursing_jobs))
    logger.info("  Already in DB (updated): %d", updated_count)
    logger.info("  New jobs inserted: %d", new_count)
    for ats, count in sorted(new_by_ats.items(), key=lambda x: -x[1]):
        logger.info("    %s: %d new", ats, count)

    # 4. Mark removed jobs
    removed = mark_removed(conn, current_urls)
    conn.commit()
    logger.info("  Removed from upstream: %d", removed)

    # 5. Enrich only new/unenriched jobs
    logger.info("=== Enrichment ===")
    logger.info("  Jobs to enrich: %d", new_count)
    results = enrich_all(DB_PATH)
    total_enriched = 0
    total_failed = 0
    for r in results:
        if r["total"] > 0:
            logger.info(
                "  %s: %d/%d enriched, %d failed%s",
                r["ats"], r["success"], r["total"], r["failed"],
                " (SKIPPED — too many errors)" if r["skipped"] else "",
            )
        total_enriched += r["success"]
        total_failed += r["failed"]

    # 6. Clean up: delete jobs that failed enrichment (stale/gone from ATS)
    cleaned = delete_unenriched(conn)
    conn.commit()
    if cleaned:
        logger.info("  Cleaned up %d unenrichable jobs (404/gone)", cleaned)

    # 7. Export for frontend
    conn = get_connection(DB_PATH)
    exportable = get_exportable_jobs(conn)
    stats = get_stats(conn)
    export_for_frontend(exportable, stats)

    # Summary
    logger.info("=== Daily Summary ===")
    logger.info("  New jobs found: %d", new_count)
    logger.info("  Successfully enriched: %d", total_enriched)
    logger.info("  Failed/stale (deleted): %d", total_failed)
    logger.info("  Removed from upstream: %d", removed)
    logger.info("  Total jobs on site: %d", len(exportable))
    logger.info("  By platform: %s", stats["by_ats"])

    conn.close()


if __name__ == "__main__":
    main()
