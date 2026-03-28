"""Pipeline entry point."""

import logging
import sys

from pipeline.config import DB_PATH
from pipeline.db import get_connection, get_exportable_jobs, get_stats, mark_removed, upsert_job
from pipeline.download import download_upstream_jobs
from pipeline.enrich import enrich_all
from pipeline.export import export_for_frontend
from pipeline.filter import filter_nursing_jobs

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
        logger.warning("No nursing jobs found! Exiting.")
        sys.exit(1)

    # 3. Upsert into SQLite
    conn = get_connection(DB_PATH)
    new_count = 0
    current_urls = set()
    for job in nursing_jobs:
        current_urls.add(job["url"])
        if upsert_job(conn, job):
            new_count += 1
    conn.commit()
    logger.info("Upserted %d jobs (%d new)", len(nursing_jobs), new_count)

    # 4. Mark removed jobs
    removed = mark_removed(conn, current_urls)
    conn.commit()
    logger.info("Marked %d jobs as removed", removed)

    # 5. Enrich new/failed jobs
    logger.info("Starting enrichment...")
    results = enrich_all(DB_PATH)
    for r in results:
        logger.info(
            "  [%s] %d/%d enriched%s",
            r["ats"], r["success"], r["total"],
            " (SKIPPED)" if r["skipped"] else "",
        )

    # 6. Export for frontend
    exportable = get_exportable_jobs(conn)
    stats = get_stats(conn)
    export_for_frontend(exportable, stats)
    logger.info("Exported %d jobs for frontend", len(exportable))

    # Print summary
    logger.info("=== Pipeline Summary ===")
    logger.info("Total active jobs: %d", stats["total"])
    logger.info("Enriched: %d", stats["enriched"])
    logger.info("By platform: %s", stats["by_ats"])
    logger.info("Exported: %d", len(exportable))

    conn.close()


if __name__ == "__main__":
    main()
