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
  <meta property="og:title" content="{escape(title)}">
  <meta property="og:description" content="{escape(meta_desc)}">
  <meta property="og:url" content="{canonical}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="NurseBoard">
  <meta name="twitter:card" content="summary">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>+</text></svg>">
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


def _build_job_jsonld(job: dict, desc_html: str, salary_display: str) -> str:
    """Build JSON-LD JobPosting structured data for Google rich results."""
    plain = re.sub(r"<[^>]+>", " ", desc_html or "")
    plain = re.sub(r"\s+", " ", plain).strip()[:5000]

    posted = job.get("posted_date") or job.get("first_seen_at") or ""
    # Normalize to YYYY-MM-DD
    date_posted = posted[:10] if posted else datetime.now(timezone.utc).strftime("%Y-%m-%d")

    ld = {
        "@context": "https://schema.org/",
        "@type": "JobPosting",
        "title": job["title"],
        "description": plain,
        "datePosted": date_posted,
        "hiringOrganization": {
            "@type": "Organization",
            "name": job["company_name"],
        },
        "jobLocationType": None,
        "applicantLocationRequirements": None,
        "directApply": True,
    }

    # Location
    location = job.get("location") or ""
    if any(kw in location.lower() for kw in ["remote", "virtual", "telehealth", "work from home"]):
        ld["jobLocationType"] = "TELECOMMUTE"
    elif location:
        loc_obj = {"@type": "Place", "address": {"@type": "PostalAddress"}}
        state = job.get("state")
        if state:
            loc_obj["address"]["addressRegion"] = state
            loc_obj["address"]["addressCountry"] = "US"
        loc_obj["address"]["streetAddress"] = location
        ld["jobLocation"] = loc_obj

    # Clean up None values
    ld = {k: v for k, v in ld.items() if v is not None}

    # Salary
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")
    if salary_min or salary_max:
        currency = job.get("salary_currency", "USD")
        base_salary = {
            "@type": "MonetaryAmount",
            "currency": currency,
            "value": {
                "@type": "QuantitativeValue",
                "unitText": "YEAR",
            },
        }
        if salary_min and salary_max:
            base_salary["value"]["minValue"] = salary_min / 100
            base_salary["value"]["maxValue"] = salary_max / 100
        elif salary_min:
            base_salary["value"]["value"] = salary_min / 100
        else:
            base_salary["value"]["value"] = salary_max / 100
        ld["baseSalary"] = base_salary

    # Valid through (30 days from posted)
    try:
        from datetime import timedelta as td
        dt = datetime.fromisoformat(date_posted)
        ld["validThrough"] = (dt + td(days=30)).strftime("%Y-%m-%d")
    except Exception:
        pass

    return f'<script type="application/ld+json">{json.dumps(ld, separators=(",", ":"))}</script>'


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

    # Build JSON-LD JobPosting schema
    jsonld = _build_job_jsonld(job, desc_html, salary)

    # Meta description from plain text
    plain = re.sub(r"<[^>]+>", " ", desc_html or "")
    plain = re.sub(r"\s+", " ", plain).strip()
    meta_desc = f"{job['title']} at {job['company_name']}"
    if job.get("location"):
        meta_desc += f" in {job['location']}"
    if salary:
        meta_desc += f". {salary}"
    meta_desc += ". Apply now on NurseBoard."

    job_title_full = f'{escape(job["title"])} at {escape(job["company_name"])}'
    job_canonical = f'{SITE_URL}/jobs/{job["slug"]}/'

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{job_title_full} | NurseBoard</title>
  <meta name="description" content="{escape(meta_desc)}">
  <link rel="canonical" href="{job_canonical}">
  <meta property="og:title" content="{job_title_full} | NurseBoard">
  <meta property="og:description" content="{escape(meta_desc)}">
  <meta property="og:url" content="{job_canonical}">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="NurseBoard">
  <meta name="twitter:card" content="summary">
  <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>+</text></svg>">
  <link rel="stylesheet" href="{css_path}">
  {jsonld}
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
          {f'<div class="sidebar-salary">{salary}</div>' if salary else ""}
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

def _build_related_links_html(label: str, links: list[tuple[str, str, int]]) -> str:
    """Build a related links section. links = [(url, display_name, count), ...]"""
    if not links:
        return ""
    items = "".join(
        f'<a class="hub-link" href="{url}">{escape(name)} <span class="count">{count}</span></a>'
        for url, name, count in links
    )
    return f'<div class="related-section"><h3>{escape(label)}</h3><div class="hub-links">{items}</div></div>'


def _build_hub_section_html(label: str, links: list[tuple[str, str, int]]) -> str:
    """Build a hub link section for homepage."""
    if not links:
        return ""
    items = "".join(
        f'<a class="hub-link" href="{url}">{escape(name)} <span class="count">{count}</span></a>'
        for url, name, count in links
    )
    return f'<section class="hub-section"><h2>{escape(label)}</h2><div class="hub-links">{items}</div></section>'


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

    # Generate category pages (role, state, role×state, company)
    _generate_all_category_pages(list_jobs)

    # Generate homepage
    _generate_homepage(list_jobs)

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

        # Build state sub-links for this role
        role_state_links = []
        for abbr, sjobs in by_state.items():
            cnt = sum(1 for j in sjobs if matcher(j))
            if cnt >= MIN_JOBS_FOR_PAGE:
                state_name = STATE_NAMES.get(abbr, abbr)
                state_sl = STATE_SLUGS.get(abbr, abbr.lower())
                role_state_links.append((f"/jobs/{slug}/{state_sl}/", f"{display} in {state_name}", cnt))
        role_state_links.sort(key=lambda x: -x[2])

        # Related roles
        related_roles = [
            (f"/jobs/{s}/", d, sum(1 for j in list_jobs if m(j)))
            for s, d, _, _, m in cat_matchers
            if s != slug and sum(1 for j in list_jobs if m(j)) >= MIN_JOBS_FOR_PAGE
        ][:10]

        seo_extra = _build_related_links_html(f"{display} Jobs by State", role_state_links[:15])
        seo_extra += _build_related_links_html("Related Roles", related_roles)

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
            extra_seo=seo_extra,
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

        # Role links within this state
        state_role_links = []
        for s, d, rx, _, m in cat_matchers:
            if rx:
                cnt = sum(1 for j in state_jobs if m(j))
                if cnt >= MIN_JOBS_FOR_PAGE:
                    state_role_links.append((f"/jobs/{s}/{state_slug}/", d, cnt))
        state_role_links.sort(key=lambda x: -x[2])

        state_seo = f"<p>We track nursing positions in {state_name} from {companies} healthcare employers. Roles include RN, LPN, CNA, nurse practitioner, and more.</p>"
        state_seo += _build_related_links_html(f"Roles in {state_name}", state_role_links[:12])

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
            extra_seo=state_seo,
        )
        with open(os.path.join(page_dir, "index.html"), "w") as f:
            f.write(html)
        total += 1

    # 4. Company pages: /jobs/at/{company}/
    by_company: dict[str, list] = {}
    for j in list_jobs:
        slug_parts = j["slug"].split("/")  # at/company/title-hash
        if len(slug_parts) >= 2:
            company_slug = slug_parts[1]
            by_company.setdefault(company_slug, []).append(j)

    for company_slug, company_jobs in by_company.items():
        if len(company_jobs) < MIN_JOBS_FOR_PAGE:
            continue

        company_name = company_jobs[0]["company_name"]
        states_with_jobs = sorted(set(j.get("state") for j in company_jobs if j.get("state")))

        # Related: other top companies
        related_companies = sorted(
            [(cs, cj) for cs, cj in by_company.items() if cs != company_slug and len(cj) >= MIN_JOBS_FOR_PAGE],
            key=lambda x: -len(x[1]),
        )[:12]
        related_html = _build_related_links_html(
            "More Healthcare Employers",
            [(f"/jobs/at/{cs}/", cj[0]["company_name"], len(cj)) for cs, cj in related_companies],
        )

        page_dir = os.path.join(FRONTEND_DIR, "jobs", "at", company_slug)
        os.makedirs(page_dir, exist_ok=True)

        heading = f"{company_name} Nursing Jobs"
        meta_desc = f"Browse {len(company_jobs)} nursing jobs at {company_name}. Updated daily with salary data and direct application links."

        seo_block = f"""<section class="seo-content">
      <h2>About {escape(heading)}</h2>
      <p>NurseBoard tracks <strong>{len(company_jobs)}</strong> nursing positions at {escape(company_name)}, updated daily with salary data, full descriptions, and direct application links.</p>
    </section>
    {related_html}"""

        html = _category_page_html(
            heading=heading,
            description=meta_desc,
            meta_desc=meta_desc,
            canonical=f"{SITE_URL}/jobs/at/{company_slug}/",
            css_path="../../../css/style.css",
            js_path="../../../js",
            data_path="../../../data",
            jobs=company_jobs,
            category_filter_json=json.dumps({"company": company_slug}),
            extra_seo=seo_block,
        )
        with open(os.path.join(page_dir, "index.html"), "w") as f:
            f.write(html)
        total += 1

    logger.info("Generated %d pSEO pages (categories + companies)", total)


def _generate_homepage(list_jobs: list[dict]):
    """Generate the homepage with hub links to categories, states, and companies."""
    # Build role links
    role_links = []
    for slug, display, regex, _ in SEO_CATEGORIES:
        if regex:
            pat = re.compile(regex, re.IGNORECASE)
            count = sum(1 for j in list_jobs if pat.search(j["title"]))
        elif slug == "nursing-with-salary":
            count = sum(1 for j in list_jobs if j.get("salary_min"))
        else:
            count = len(list_jobs)
        if count >= MIN_JOBS_FOR_PAGE:
            role_links.append((f"/jobs/{slug}/", display, count))

    # Build state links
    by_state: dict[str, int] = {}
    for j in list_jobs:
        st = j.get("state")
        if st:
            by_state[st] = by_state.get(st, 0) + 1
    state_links = sorted(
        [(f"/jobs/{STATE_SLUGS[abbr]}/", STATE_NAMES[abbr], cnt) for abbr, cnt in by_state.items() if cnt >= MIN_JOBS_FOR_PAGE],
        key=lambda x: -x[2],
    )

    # Build company links (top 20)
    by_company: dict[str, tuple[str, int]] = {}
    for j in list_jobs:
        slug_parts = j["slug"].split("/")
        if len(slug_parts) >= 2:
            cs = slug_parts[1]
            if cs not in by_company:
                by_company[cs] = (j["company_name"], 0)
            by_company[cs] = (by_company[cs][0], by_company[cs][1] + 1)
    company_links = sorted(
        [(f"/jobs/at/{cs}/", name, cnt) for cs, (name, cnt) in by_company.items() if cnt >= MIN_JOBS_FOR_PAGE],
        key=lambda x: -x[2],
    )[:24]

    pre_rendered = _render_job_rows_html(list_jobs)
    hub_roles = _build_hub_section_html("Browse by Role", role_links)
    hub_states = _build_hub_section_html("Browse by State", state_links[:20])
    hub_companies = _build_hub_section_html("Top Employers", company_links)
    homepage = _page_shell(
        title="NurseBoard - Nursing Jobs Aggregated Daily from 500+ Employers",
        meta_desc=f"Browse {len(list_jobs)} nursing jobs aggregated daily from top healthcare employers. RN, LPN, CNA, NP, travel nurse, and more. Salary data and direct application links.",
        canonical=f"{SITE_URL}/",
        css_path="css/style.css",
        js_path="js",
        data_path="data",
        body=f'''    <section class="hero">
      <p class="hero-eyebrow">Updated daily from 600+ companies.</p>
      <div class="hero-content">
        <h1>Nursing jobs.<br>Direct from the employer.</h1>
        <p class="hero-blurb">Every job here links straight to the employer's career page. No recruiters, no staffing agencies, no middlemen. We scan thousands of company career pages daily so you can skip the noise and apply directly.</p>
      </div>
    </section>

    <section class="search-section">
      <input type="text" id="search" class="search-input" placeholder="Search by title, company, or location...">
    </section>

    <div class="filter-row">
      <select id="filter-role" class="filter-select">
        <option value="">All Roles</option>
        <option value="rn">RN - Registered Nurse</option>
        <option value="lpn-lvn">LPN / LVN</option>
        <option value="cna">CNA</option>
        <option value="np">Nurse Practitioner / APRN</option>
        <option value="case-manager">Case Manager</option>
        <option value="travel-nurse">Travel Nurse</option>
        <option value="charge-nurse">Charge Nurse</option>
        <option value="nurse-manager">Nurse Manager</option>
        <option value="icu">ICU / Critical Care</option>
        <option value="er">ER / Emergency</option>
        <option value="or-nurse">OR / Surgical Nurse</option>
        <option value="home-health">Home Health</option>
        <option value="med-surg">Med-Surg</option>
        <option value="pediatric">Pediatric / NICU / PICU</option>
        <option value="psych">Psychiatric / Behavioral</option>
        <option value="oncology">Oncology</option>
        <option value="crna">CRNA</option>
        <option value="midwife">Midwife</option>
        <option value="educator">Nurse Educator</option>
        <option value="telehealth">Telehealth / Remote</option>
      </select>
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

    <div id="result-count" class="result-count">{len(list_jobs)} nursing jobs</div>

    <div id="job-list" class="job-list">
{pre_rendered}
    </div>
    <div id="pagination" class="pagination"></div>

    {hub_roles}
    {hub_states}
    {hub_companies}''',
    )

    with open(os.path.join(FRONTEND_DIR, "index.html"), "w") as f:
        f.write(homepage)

    logger.info("Generated homepage with hub links")


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
