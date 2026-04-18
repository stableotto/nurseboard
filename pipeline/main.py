"""Pipeline entry point."""

import logging
import sys

from pipeline.config import DB_PATH
from pipeline.db import (
    get_connection, get_exportable_jobs, get_stats,
    mark_removed, upsert_job, delete_unenriched,
)
from pipeline.download import download_upstream_jobs
from pipeline.enrich import enrich_all
from pipeline.export import export_for_frontend
from pipeline.freshness import check_freshness
from pipeline.filter import filter_healthcare_jobs
from pipeline.scrape_workday import scrape_extra_workday
from pipeline.scrape_oracle_hcm import scrape_oracle_hcm
# from pipeline.scrape_neogov import scrape_neogov  # Disabled: HTML scraping, rate-limited

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("Starting healthcare job pipeline")

    # 1. Download upstream jobs
    all_jobs = download_upstream_jobs()

    # 2. Filter for healthcare jobs (nursing + allied health)
    healthcare_jobs = filter_healthcare_jobs(all_jobs)
    if not healthcare_jobs:
        logger.warning("No healthcare jobs found from upstream!")

    # 2b. Scrape extra Workday companies
    extra_jobs = scrape_extra_workday()
    if extra_jobs:
        healthcare_jobs.extend(extra_jobs)
        logger.info("Added %d extra Workday jobs", len(extra_jobs))

    # 2c. Scrape Oracle HCM career sites
    oracle_jobs = scrape_oracle_hcm()
    if oracle_jobs:
        healthcare_jobs.extend(oracle_jobs)
        logger.info("Added %d Oracle HCM jobs", len(oracle_jobs))

    if extra_jobs or oracle_jobs:
        logger.info("Total healthcare jobs (upstream + extra): %d", len(healthcare_jobs))

    if not healthcare_jobs:
        logger.warning("No healthcare jobs found at all! Exiting.")
        sys.exit(1)

    # 3. Upsert into SQLite — track which are new this run
    conn = get_connection(DB_PATH)

    # One-time migration: fix BambooHR /careers/view/ -> /careers/ URLs
    fixed = conn.execute(
        "UPDATE jobs SET url = REPLACE(url, '/careers/view/', '/careers/') "
        "WHERE url LIKE '%bamboohr.com/careers/view/%'"
    ).rowcount
    if fixed:
        conn.commit()
        logger.info("Migrated %d BambooHR URLs to new format", fixed)
    existing_before = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    new_count = 0
    new_by_ats = {}
    updated_count = 0
    current_urls = set()
    for job in healthcare_jobs:
        current_urls.add(job["url"])
        if upsert_job(conn, job):
            new_count += 1
            ats = (job.get("ats") or "").lower()
            new_by_ats[ats] = new_by_ats.get(ats, 0) + 1
        else:
            updated_count += 1
    conn.commit()
    logger.info("=== Upsert Breakdown ===")
    logger.info("  Upstream healthcare jobs: %d", len(healthcare_jobs))
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

    # 5b. Re-parse salary for enriched jobs missing salary data
    logger.info("=== Salary Re-parse ===")
    conn = get_connection(DB_PATH)
    from pipeline.salary import parse_salary, parse_bonus
    no_salary = conn.execute(
        """SELECT url, description_plain FROM jobs
        WHERE enriched_at IS NOT NULL AND removed_at IS NULL
          AND salary_min IS NULL AND description_plain IS NOT NULL
          AND description_plain != ''"""
    ).fetchall()
    reparsed = 0
    for row in no_salary:
        sal_min, sal_max = parse_salary(row["description_plain"])
        if sal_min:
            conn.execute(
                "UPDATE jobs SET salary_min = ?, salary_max = ?, updated_at = datetime('now') WHERE url = ?",
                (sal_min, sal_max, row["url"]),
            )
            reparsed += 1
    if reparsed:
        conn.commit()
    logger.info("  Re-parsed salary for %d/%d jobs missing salary", reparsed, len(no_salary))

    # 5c. Parse sign-on bonuses from descriptions
    logger.info("=== Bonus Parse ===")
    no_bonus = conn.execute(
        """SELECT url, description_plain FROM jobs
        WHERE enriched_at IS NOT NULL AND removed_at IS NULL
          AND bonus IS NULL AND description_plain IS NOT NULL
          AND description_plain != ''"""
    ).fetchall()
    bonus_found = 0
    for row in no_bonus:
        bonus = parse_bonus(row["description_plain"])
        if bonus:
            conn.execute(
                "UPDATE jobs SET bonus = ?, updated_at = datetime('now') WHERE url = ?",
                (bonus, row["url"]),
            )
            bonus_found += 1
    if bonus_found:
        conn.commit()
    logger.info("  Found sign-on bonus in %d/%d jobs", bonus_found, len(no_bonus))

    # 6. Clean up: delete jobs that failed enrichment (stale/gone from ATS)
    cleaned = delete_unenriched(conn)
    conn.commit()
    if cleaned:
        logger.info("  Cleaned up %d unenrichable jobs (404/gone)", cleaned)

    # 6b. Freshness check: verify oldest enriched jobs are still live
    logger.info("=== Freshness Check ===")
    freshness = check_freshness(DB_PATH)
    logger.info("  Checked %d, removed %d stale jobs", freshness["checked"], freshness["removed"])

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
