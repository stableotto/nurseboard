"""Export jobs to static HTML + JSON for programmatic SEO."""

from __future__ import annotations

import hashlib
import json
import os
import logging
import re
import shutil
from datetime import datetime, timezone
from html import escape

from pipeline.config import (
    DETAIL_DIR, EXPORT_DIR, JOBS_JSON, META_JSON,
    normalize_company_name, SEO_CATEGORIES, STATE_NAMES, STATE_SLUGS,
    MIN_JOBS_FOR_PAGE,
)

logger = logging.getLogger(__name__)

SITE_URL = "https://nurseboard.pages.dev"
FRONTEND_DIR = "frontend"

_US_STATES = set(STATE_NAMES.keys())
_STATE_RE = re.compile(r"\b([A-Z]{2})\b")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_state(location: str | None) -> str | None:
    if not location:
        return None
    for m in _STATE_RE.finditer(location):
        if m.group(1) in _US_STATES:
            return m.group(1)
    return None


def _slugify(text: str) -> str:
    """Convert text to a URL-safe slug."""
    s = text.lower().strip()
    s = _SLUG_RE.sub("-", s)
    return s.strip("-")[:80]


def _job_slug(company_name: str, title: str, location: str | None, url: str) -> str:
    """Generate a clean URL slug: at/company/title-location-hash."""
    company = _slugify(company_name or "unknown")
    parts = [title or ""]
    if location:
        parts.append(location)
    slug = _slugify(" ".join(parts))
    # Append short hash to avoid collisions
    h = hashlib.md5(url.encode()).hexdigest()[:6]
    return f"at/{company}/{slug}-{h}"


def _job_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _format_salary_html(salary_min, salary_max) -> str:
    if salary_min is None and salary_max is None:
        return ""
    def fmt(cents):
        d = cents / 100
        return f"${d:,.0f}" if d < 1000 else f"${d/1000:.0f}k"
    if salary_min and salary_max:
        return f"{fmt(salary_min)} - {fmt(salary_max)}"
    if salary_min:
        return f"{fmt(salary_min)}+"
    return f"Up to {fmt(salary_max)}"


def _relative_time(date_str: str | None) -> str:
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        days = (now - dt).days
        if days > 30:
            return f"{days // 30}mo ago"
        if days > 0:
            return f"{days}d ago"
        return "today"
    except Exception:
        return ""


def _company_color(name: str) -> str:
    h = 0
    for c in (name or ""):
        h = ord(c) + ((h << 5) - h)
    colors = [
        "#6366f1", "#8b5cf6", "#ec4899", "#f43f5e",
        "#f97316", "#eab308", "#22c55e", "#14b8a6",
        "#06b6d4", "#3b82f6", "#a855f7", "#e11d48",
    ]
    return colors[abs(h) % len(colors)]


# ---------------------------------------------------------------------------
# Build list entry from DB row
# ---------------------------------------------------------------------------

def _build_list_entry(job: dict) -> dict:
    company_display = normalize_company_name(
        job.get("company_name") or job.get("company_slug") or ""
    )
    location = job.get("location")
    state = _extract_state(location)
    jid = _job_id(job["url"])
    slug = _job_slug(company_display, job["title"], location, job["url"])

    return {
        "id": jid,
        "slug": slug,
        "url": job["url"],
        "title": job["title"],
        "company_slug": job["company_slug"],
        "company_name": company_display,
        "location": location,
        "state": state,
        "ats_platform": job["ats_platform"],
        "departments": json.loads(job["departments"]) if job.get("departments") else [],
        "is_recruiter": bool(job.get("is_recruiter")),
        "posted_date": job.get("posted_date"),
        "salary_min": job.get("salary_min"),
        "salary_max": job.get("salary_max"),
        "salary_currency": job.get("salary_currency", "USD"),
        "first_seen_at": job.get("first_seen_at"),
    }


# ---------------------------------------------------------------------------
# Pre-render job rows as static HTML
# ---------------------------------------------------------------------------

def _render_job_rows_html(jobs: list[dict], limit: int = 25) -> str:
    """Render job list rows as static HTML for SEO."""
    rows = []
    for job in jobs[:limit]:
        initial = (job["company_name"] or "?")[0].upper()
        color = _company_color(job["company_name"])
        salary = _format_salary_html(job.get("salary_min"), job.get("salary_max"))
        time_str = _relative_time(job.get("posted_date") or job.get("first_seen_at"))
        meta_parts = [escape(job["company_name"] or "")]
        if salary:
            meta_parts.append(f'<span class="salary">{salary}</span>')

        rows.append(f'''<a class="job-row" href="/jobs/{job["slug"]}/">
  <div class="company-avatar" style="background:{color}">{initial}</div>
  <div class="job-info">
    <div class="job-title">{escape(job["title"])}</div>
    <div class="job-meta">{" &middot; ".join(meta_parts)}</div>
  </div>
  <div class="job-right">
    <div class="job-location">{escape(job.get("location") or "")}</div>
    <div class="job-time">{time_str}</div>
  </div>
</a>''')
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Page templates
# ---------------------------------------------------------------------------

def _page_shell(title: str, meta_desc: str, canonical: str, css_path: str,
                js_path: str, data_path: str, body: str) -> str:
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(title)}</title>
  <meta name="description" content="{escape(meta_desc)}">
  <link rel="canonical" href="{canonical}">
  <link rel="stylesheet" href="{css_path}">
</head>
<body>
  <header class="header">
    <div class="container">
      <a href="/" class="logo">NurseBoard</a>
      <span class="tagline">Nursing jobs, aggregated daily</span>
    </div>
  </header>
  <main class="container">
{body}
  </main>
  <script type="module" src="{js_path}/app.js"></script>
</body>
</html>'''


def _job_detail_html(job: dict, desc_html: str, css_path: str) -> str:
    initial = (job["company_name"] or "?")[0].upper()
    color = _company_color(job["company_name"])
    salary = _format_salary_html(job.get("salary_min"), job.get("salary_max"))
    posted = job.get("posted_date") or job.get("first_seen_at") or ""
    meta_parts = [
        (", ".join(job.get("departments") or [])) or None,
        f'<span class="salary">{salary}</span>' if salary else None,
        escape(job.get("location") or "") or None,
    ]
    meta_parts = [p for p in meta_parts if p]

    dept_tags = "".join(
        f'<span class="dept-tag">{escape(d)}</span>'
        for d in (job.get("departments") or [])
    )

    # Meta description from plain text
    plain = re.sub(r"<[^>]+>", " ", desc_html or "")
    plain = re.sub(r"\s+", " ", plain).strip()
    meta_desc = f"{job['title']} at {job['company_name']}"
    if job.get("location"):
        meta_desc += f" in {job['location']}"
    if salary:
        meta_desc += f". {salary}"
    meta_desc += ". Apply now on NurseBoard."

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(job["title"])} at {escape(job["company_name"])} | NurseBoard</title>
  <meta name="description" content="{escape(meta_desc)}">
  <link rel="canonical" href="{SITE_URL}/jobs/{job["slug"]}/">
  <link rel="stylesheet" href="{css_path}">
</head>
<body>
  <header class="header">
    <div class="container">
      <a href="/" class="logo">NurseBoard</a>
      <span class="tagline">Nursing jobs, aggregated daily</span>
    </div>
  </header>
  <main class="container">
    <div class="breadcrumb">
      <a href="/">Home</a>
      <span class="sep">&rsaquo;</span>
      <span>{escape(job["company_name"])}</span>
      <span class="sep">&rsaquo;</span>
      <span>{escape(job["title"])}</span>
    </div>
    <div class="detail-layout">
      <div class="detail-main">
        <div class="detail-company">
          <div class="company-avatar" style="background:{color}">{initial}</div>
          <span class="detail-company-name">{escape(job["company_name"])}</span>
        </div>
        <h1 class="detail-title">{escape(job["title"])}</h1>
        <div class="detail-meta">{' <span style="color:var(--border)">|</span> '.join(meta_parts)}</div>
        {f'<div class="dept-tags">{dept_tags}</div>' if dept_tags else ""}
        <div class="description">{desc_html}</div>
      </div>
      <div class="detail-sidebar">
        <div class="sidebar-card">
          <a class="apply-btn" href="{escape(job["url"])}" target="_blank" rel="noopener">Apply for this job</a>
          <dl class="sidebar-info">
            <dt>Company</dt>
            <dd>{escape(job["company_name"])}</dd>
            <dt>Posted</dt>
            <dd>{posted[:10] if posted else ""}</dd>
            {f'<dt>Location</dt><dd>{escape(job["location"])}</dd>' if job.get("location") else ""}
          </dl>
        </div>
      </div>
    </div>
  </main>
</body>
</html>'''


def _category_page_html(heading: str, description: str, meta_desc: str,
                        canonical: str, css_path: str, js_path: str,
                        data_path: str, jobs: list[dict],
                        category_filter_json: str, extra_seo: str = "") -> str:
    count = len(jobs)
    pre_rendered = _render_job_rows_html(jobs)
    companies = len(set(j["company_name"] for j in jobs))

    return _page_shell(
        title=f"{heading} | NurseBoard",
        meta_desc=meta_desc,
        canonical=canonical,
        css_path=css_path,
        js_path=js_path,
        data_path=data_path,
        body=f'''    <div class="category-hero">
      <h1>{escape(heading)}</h1>
      <p class="category-desc">{escape(description)}</p>
    </div>

    <section class="search-section">
      <input type="text" id="search" class="search-input" placeholder="Search {escape(heading.lower())}...">
    </section>

    <div class="filter-row">
      <select id="filter-role" class="filter-select" style="display:none"></select>
      <select id="filter-state" class="filter-select">
        <option value="">All States</option>
      </select>
      <label class="filter-toggle">
        <input type="checkbox" id="filter-salary"> Has Salary
      </label>
      <label class="filter-toggle">
        <input type="checkbox" id="filter-recruiter"> Hide Recruiters
      </label>
    </div>

    <div id="result-count" class="result-count">{count} job{"s" if count != 1 else ""}</div>

    <div id="job-list" class="job-list">
{pre_rendered}
    </div>
    <div id="pagination" class="pagination"></div>

    <section class="seo-content">
      <h2>About {escape(heading)}</h2>
      <p>NurseBoard aggregates <strong>{escape(heading.lower())}</strong> positions from {companies} healthcare employers. Jobs are updated daily with salary data, full descriptions, and direct application links.</p>
      {extra_seo}
    </section>

    <script>window.__CATEGORY_FILTER = {category_filter_json};</script>''',
    )


# ---------------------------------------------------------------------------
# Main export
# ---------------------------------------------------------------------------

def export_for_frontend(jobs: list[dict], stats: dict):
    """Export jobs to frontend data files + generate pre-rendered SEO pages."""
    os.makedirs(EXPORT_DIR, exist_ok=True)

    list_jobs = []
    detail_jobs = []

    for job in jobs:
        entry = _build_list_entry(job)
        list_jobs.append(entry)
        if job.get("description_html") or job.get("description_plain"):
            detail_jobs.append((entry, job.get("description_html") or job.get("description_plain")))

    # Write jobs.json for JS interactivity
    with open(JOBS_JSON, "w") as f:
        json.dump(list_jobs, f, separators=(",", ":"))

    # Write meta.json
    meta = {
        "total": len(list_jobs),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "by_platform": stats.get("by_ats", {}),
        "enriched": stats.get("enriched", 0),
    }
    with open(META_JSON, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Exported %d jobs to JSON", len(list_jobs))

    # Generate job detail pages at clean URLs
    _generate_job_detail_pages(detail_jobs)

    # Generate category pages (role, state, role×state)
    _generate_all_category_pages(list_jobs)

    # Generate sitemap
    _generate_sitemap(list_jobs)


def _generate_job_detail_pages(detail_jobs: list[tuple[dict, str]]):
    """Generate /jobs/{company}/{title-hash}/index.html for each job."""
    # Clean old detail files
    jobs_dir = os.path.join(FRONTEND_DIR, "jobs")

    count = 0
    for entry, desc_html in detail_jobs:
        slug = entry["slug"]
        page_dir = os.path.join(FRONTEND_DIR, "jobs", slug)
        os.makedirs(page_dir, exist_ok=True)

        # Calculate relative CSS path based on depth
        depth = slug.count("/") + 2  # jobs/ + at/ + company/ + slug/
        css_path = "../" * depth + "css/style.css"

        html = _job_detail_html(entry, desc_html, css_path)
        with open(os.path.join(page_dir, "index.html"), "w") as f:
            f.write(html)
        count += 1

    # Also write detail JSON files for JS fallback
    os.makedirs(DETAIL_DIR, exist_ok=True)
    for entry, desc_html in detail_jobs:
        jid = entry["id"]
        prefix = jid[:2]
        detail_dir = os.path.join(DETAIL_DIR, prefix)
        os.makedirs(detail_dir, exist_ok=True)
        detail = {**entry, "description_html": desc_html}
        with open(os.path.join(detail_dir, f"{jid}.json"), "w") as f:
            json.dump(detail, f, separators=(",", ":"))

    logger.info("Generated %d job detail pages", count)


def _generate_all_category_pages(list_jobs: list[dict]):
    """Generate all pSEO pages: role, state, role×state."""
    total = 0

    # Pre-compile category matchers
    cat_matchers = []
    for slug, display, regex, meta_tmpl in SEO_CATEGORIES:
        if regex:
            pat = re.compile(regex, re.IGNORECASE)
            matcher = lambda j, p=pat: p.search(j["title"])
        elif slug == "nursing-with-salary":
            matcher = lambda j: j.get("salary_min") is not None
        else:
            matcher = lambda j: True
        cat_matchers.append((slug, display, regex, meta_tmpl, matcher))

    # Group jobs by state
    by_state: dict[str, list] = {}
    for j in list_jobs:
        st = j.get("state")
        if st:
            by_state.setdefault(st, []).append(j)

    # 1. Role-only pages: /jobs/{role}/
    for slug, display, regex, meta_tmpl, matcher in cat_matchers:
        matched = [j for j in list_jobs if matcher(j)]
        if len(matched) < MIN_JOBS_FOR_PAGE:
            continue

        cat_filter = {}
        if regex:
            cat_filter["regex"] = regex
        if slug == "nursing-with-salary":
            cat_filter["hasSalary"] = True

        page_dir = os.path.join(FRONTEND_DIR, "jobs", slug)
        os.makedirs(page_dir, exist_ok=True)
        html = _category_page_html(
            heading=f"{display} Jobs",
            description=meta_tmpl.format(count=len(matched)),
            meta_desc=meta_tmpl.format(count=len(matched)),
            canonical=f"{SITE_URL}/jobs/{slug}/",
            css_path="../../css/style.css",
            js_path="../../js",
            data_path="../../data",
            jobs=matched,
            category_filter_json=json.dumps(cat_filter),
        )
        with open(os.path.join(page_dir, "index.html"), "w") as f:
            f.write(html)
        total += 1

        # 2. Role × State pages: /jobs/{role}/{state-name}/
        for abbr, state_jobs in by_state.items():
            state_name = STATE_NAMES.get(abbr, abbr)
            state_slug = STATE_SLUGS.get(abbr, abbr.lower())
            state_matched = [j for j in state_jobs if matcher(j)]

            if len(state_matched) < MIN_JOBS_FOR_PAGE:
                continue

            state_filter = {**cat_filter, "state": abbr}
            cross_dir = os.path.join(FRONTEND_DIR, "jobs", slug, state_slug)
            os.makedirs(cross_dir, exist_ok=True)

            heading = f"{display} Jobs in {state_name}"
            meta_desc = f"Browse {len(state_matched)} {display.lower()} jobs in {state_name}. Updated daily with salary data and direct application links."

            html = _category_page_html(
                heading=heading,
                description=meta_desc,
                meta_desc=meta_desc,
                canonical=f"{SITE_URL}/jobs/{slug}/{state_slug}/",
                css_path="../../../css/style.css",
                js_path="../../../js",
                data_path="../../../data",
                jobs=state_matched,
                category_filter_json=json.dumps(state_filter),
                extra_seo=f"<p>We track {display.lower()} positions in {state_name} from {len(set(j['company_name'] for j in state_matched))} healthcare employers.</p>",
            )
            with open(os.path.join(cross_dir, "index.html"), "w") as f:
                f.write(html)
            total += 1

    # 3. State-only pages: /jobs/{state-name}/
    for abbr, state_jobs in by_state.items():
        if len(state_jobs) < MIN_JOBS_FOR_PAGE:
            continue

        state_name = STATE_NAMES.get(abbr, abbr)
        state_slug = STATE_SLUGS.get(abbr, abbr.lower())
        companies = len(set(j["company_name"] for j in state_jobs))

        page_dir = os.path.join(FRONTEND_DIR, "jobs", state_slug)
        os.makedirs(page_dir, exist_ok=True)

        heading = f"Nursing Jobs in {state_name}"
        meta_desc = f"Browse {len(state_jobs)} nursing jobs in {state_name}. Updated daily with salary data and direct application links."

        html = _category_page_html(
            heading=heading,
            description=meta_desc,
            meta_desc=meta_desc,
            canonical=f"{SITE_URL}/jobs/{state_slug}/",
            css_path="../../css/style.css",
            js_path="../../js",
            data_path="../../data",
            jobs=state_jobs,
            category_filter_json=json.dumps({"state": abbr}),
            extra_seo=f"<p>We track nursing positions in {state_name} from {companies} healthcare employers. Roles include RN, LPN, CNA, nurse practitioner, and more.</p>",
        )
        with open(os.path.join(page_dir, "index.html"), "w") as f:
            f.write(html)
        total += 1

    logger.info("Generated %d pSEO category pages", total)


def _generate_sitemap(list_jobs: list[dict]):
    """Generate sitemap.xml."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    urls = [f'  <url><loc>{SITE_URL}/</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>']

    # Collect all generated pages by scanning the jobs/ directory
    jobs_dir = os.path.join(FRONTEND_DIR, "jobs")
    if os.path.isdir(jobs_dir):
        for root, dirs, files in os.walk(jobs_dir):
            if "index.html" in files:
                rel = os.path.relpath(root, FRONTEND_DIR)
                urls.append(f'  <url><loc>{SITE_URL}/{rel}/</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>0.7</priority></url>')

    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"
    with open(os.path.join(FRONTEND_DIR, "sitemap.xml"), "w") as f:
        f.write(sitemap)

    with open(os.path.join(FRONTEND_DIR, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")

    logger.info("Generated sitemap with %d URLs", len(urls))
