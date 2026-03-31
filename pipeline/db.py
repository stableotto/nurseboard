"""SQLite schema and database operations."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timedelta, timezone

from pipeline.config import MAX_ENRICH_FAILURES, MAX_JOB_AGE_DAYS, UNENRICHED_GRACE_DAYS

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    url TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company_slug TEXT NOT NULL,
    company_name TEXT,
    location TEXT,
    ats_platform TEXT NOT NULL,
    skill_level TEXT,
    departments TEXT,
    is_recruiter INTEGER DEFAULT 0,

    posted_date TEXT,
    salary_min INTEGER,
    salary_max INTEGER,
    salary_currency TEXT DEFAULT 'USD',
    description_html TEXT,
    description_plain TEXT,

    first_seen_at TEXT NOT NULL,
    enriched_at TEXT,
    enrich_failures INTEGER DEFAULT 0,
    removed_at TEXT,
    upstream_scraped_at TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_jobs_ats ON jobs(ats_platform);
CREATE INDEX IF NOT EXISTS idx_jobs_enriched ON jobs(enriched_at);
CREATE INDEX IF NOT EXISTS idx_jobs_posted ON jobs(posted_date);
CREATE INDEX IF NOT EXISTS idx_jobs_removed ON jobs(removed_at);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    return conn


def upsert_job(conn: sqlite3.Connection, job: dict) -> bool:
    """Insert or update a job. Returns True if newly inserted."""
    now = datetime.now(timezone.utc).isoformat()
    departments = json.dumps(job.get("departments", []))

    cursor = conn.execute("SELECT url FROM jobs WHERE url = ?", (job["url"],))
    exists = cursor.fetchone() is not None

    # Map upstream field names: company->company_slug/name, ats->ats_platform, scraped_at->upstream
    company = job.get("company") or job.get("company_slug") or ""
    company_name = job.get("company_name") or company
    ats_platform = (job.get("ats") or job.get("ats_platform") or "").lower()
    scraped_at = job.get("scraped_at") or job.get("timestamp")

    if exists:
        conn.execute(
            """UPDATE jobs SET
                title = ?, company_name = ?, location = ?, skill_level = ?,
                departments = ?, is_recruiter = ?, removed_at = NULL,
                upstream_scraped_at = ?, updated_at = ?
            WHERE url = ?""",
            (
                job["title"],
                company_name,
                job.get("location"),
                job.get("skill_level"),
                departments,
                1 if job.get("is_recruiter") else 0,
                scraped_at,
                now,
                job["url"],
            ),
        )
        return False
    else:
        conn.execute(
            """INSERT INTO jobs (url, title, company_slug, company_name, location,
                ats_platform, skill_level, departments, is_recruiter,
                first_seen_at, upstream_scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                job["url"],
                job["title"],
                company,
                company_name,
                job.get("location"),
                ats_platform,
                job.get("skill_level"),
                departments,
                1 if job.get("is_recruiter") else 0,
                now,
                scraped_at,
            ),
        )
        return True


def get_unenriched(conn: sqlite3.Connection, ats: str, limit: int = 200) -> list[dict]:
    """Get jobs that need enrichment for a given ATS platform."""
    rows = conn.execute(
        """SELECT url, title, company_slug, company_name, ats_platform
        FROM jobs
        WHERE ats_platform = ?
          AND enriched_at IS NULL
          AND enrich_failures < ?
          AND removed_at IS NULL
        ORDER BY first_seen_at DESC
        LIMIT ?""",
        (ats, MAX_ENRICH_FAILURES, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def save_enrichment(conn: sqlite3.Connection, url: str, data: dict):
    """Save enrichment data for a job."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """UPDATE jobs SET
            posted_date = ?,
            salary_min = ?,
            salary_max = ?,
            salary_currency = ?,
            description_html = ?,
            description_plain = ?,
            enriched_at = ?,
            updated_at = ?
        WHERE url = ?""",
        (
            data.get("posted_date"),
            data.get("salary_min"),
            data.get("salary_max"),
            data.get("salary_currency", "USD"),
            data.get("description_html"),
            data.get("description_plain"),
            now,
            now,
            url,
        ),
    )


def increment_failure(conn: sqlite3.Connection, url: str):
    conn.execute(
        "UPDATE jobs SET enrich_failures = enrich_failures + 1, updated_at = datetime('now') WHERE url = ?",
        (url,),
    )


def mark_job_gone(conn: sqlite3.Connection, url: str):
    """Mark a job as gone from ATS (404). Sets max failures so we don't retry."""
    conn.execute(
        "UPDATE jobs SET enrich_failures = ?, updated_at = datetime('now') WHERE url = ?",
        (MAX_ENRICH_FAILURES, url),
    )


def delete_unenriched(conn: sqlite3.Connection) -> int:
    """Delete jobs that failed enrichment (maxed out retries — 404/gone from ATS)."""
    conn.execute(
        "DELETE FROM jobs WHERE enriched_at IS NULL AND enrich_failures >= ?",
        (MAX_ENRICH_FAILURES,),
    )
    deleted = conn.execute("SELECT changes()").fetchone()[0]
    return deleted


def mark_removed(conn: sqlite3.Connection, current_urls: set[str]):
    """Mark jobs not in current_urls as removed."""
    now = datetime.now(timezone.utc).isoformat()
    all_urls = {r["url"] for r in conn.execute("SELECT url FROM jobs WHERE removed_at IS NULL").fetchall()}
    removed = all_urls - current_urls
    if removed:
        conn.executemany(
            "UPDATE jobs SET removed_at = ?, updated_at = ? WHERE url = ?",
            [(now, now, url) for url in removed],
        )
    return len(removed)


def get_exportable_jobs(conn: sqlite3.Connection) -> list[dict]:
    """Get enriched jobs with descriptions, posted within 30 days."""
    cutoff_posted = (datetime.now(timezone.utc) - timedelta(days=MAX_JOB_AGE_DAYS)).isoformat()

    rows = conn.execute(
        """SELECT url, title, company_slug, company_name, location,
            ats_platform, skill_level, departments, is_recruiter,
            posted_date, salary_min, salary_max, salary_currency,
            description_html, description_plain, first_seen_at,
            enriched_at, upstream_scraped_at
        FROM jobs
        WHERE removed_at IS NULL
          AND enriched_at IS NOT NULL
          AND description_html IS NOT NULL
          AND COALESCE(posted_date, first_seen_at) >= ?
        ORDER BY posted_date IS NULL ASC, COALESCE(posted_date, first_seen_at) DESC""",
        (cutoff_posted,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_stats(conn: sqlite3.Connection) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM jobs WHERE removed_at IS NULL").fetchone()[0]
    enriched = conn.execute(
        "SELECT COUNT(*) FROM jobs WHERE removed_at IS NULL AND enriched_at IS NOT NULL"
    ).fetchone()[0]
    by_ats = {}
    for row in conn.execute(
        "SELECT ats_platform, COUNT(*) as cnt FROM jobs WHERE removed_at IS NULL GROUP BY ats_platform"
    ).fetchall():
        by_ats[row["ats_platform"]] = row["cnt"]
    return {"total": total, "enriched": enriched, "by_ats": by_ats}
