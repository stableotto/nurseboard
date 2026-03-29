"""Export jobs to JSON for the frontend + generate SEO category pages."""

from __future__ import annotations

import hashlib
import json
import os
import logging
import re
from datetime import datetime, timezone

from pipeline.config import (
    DETAIL_DIR, EXPORT_DIR, JOBS_JSON, META_JSON,
    normalize_company_name, SEO_CATEGORIES, STATE_NAMES,
)

logger = logging.getLogger(__name__)

SITE_URL = "https://nurseboard.pages.dev"
FRONTEND_DIR = "frontend"

_US_STATES = set(STATE_NAMES.keys())
_STATE_RE = re.compile(r"\b([A-Z]{2})\b")


def _extract_state(location: str | None) -> str | None:
    if not location:
        return None
    for m in _STATE_RE.finditer(location):
        if m.group(1) in _US_STATES:
            return m.group(1)
    return None


def _job_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


def _prefix(job_id: str) -> str:
    return job_id[:2]


def _build_list_entry(job: dict) -> dict:
    company_display = normalize_company_name(
        job.get("company_name") or job.get("company_slug") or ""
    )
    location = job.get("location")
    state = _extract_state(location)
    jid = _job_id(job["url"])

    return {
        "id": jid,
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
# Category page HTML template
# ---------------------------------------------------------------------------

CATEGORY_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} | NurseBoard</title>
  <meta name="description" content="{meta_description}">
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
    <div class="category-hero">
      <h1>{heading}</h1>
      <p class="category-desc">{description}</p>
    </div>

    <section class="search-section">
      <input type="text" id="search" class="search-input" placeholder="Search {heading_lower} jobs...">
    </section>

    <div class="filter-row">
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

    <div id="result-count" class="result-count"></div>
    <div id="job-list" class="job-list"></div>
    <div id="pagination" class="pagination"></div>

    <section class="seo-content">
      <h2>About {heading} Jobs</h2>
      <p>NurseBoard aggregates <strong>{heading_lower}</strong> positions from {source_count} healthcare employers. Jobs are updated daily with salary data, full descriptions, and direct application links.</p>
      {extra_seo}
    </section>
  </main>

  <script type="module">
    import {{ filterJobs }} from "{js_path}/filters.js";
    import {{ renderJobList, renderPagination }} from "{js_path}/list.js";

    const DATA_URL = "{data_path}/jobs.json";
    const CATEGORY_FILTER = {category_filter_json};

    init();

    async function init() {{
      const container = document.getElementById("job-list");
      const paginationEl = document.getElementById("pagination");
      const countEl = document.getElementById("result-count");
      const searchInput = document.getElementById("search");
      const stateSelect = document.getElementById("filter-state");
      const atsSelect = document.getElementById("filter-ats");
      const salaryToggle = document.getElementById("filter-salary");
      const recruiterToggle = document.getElementById("filter-recruiter");

      container.innerHTML = '<div class="loading">Loading jobs...</div>';

      let allJobs = [];
      let currentPage = 1;

      try {{
        const resp = await fetch(DATA_URL);
        if (!resp.ok) throw new Error("Failed");
        let jobs = await resp.json();
        // Pre-filter for this category
        if (CATEGORY_FILTER.regex) {{
          const re = new RegExp(CATEGORY_FILTER.regex, "i");
          jobs = jobs.filter(j => re.test(j.title) || re.test((j.departments||[]).join(" ")));
        }}
        if (CATEGORY_FILTER.state) {{
          jobs = jobs.filter(j => j.state === CATEGORY_FILTER.state);
        }}
        if (CATEGORY_FILTER.hasSalary) {{
          jobs = jobs.filter(j => j.salary_min != null);
        }}
        allJobs = jobs;
      }} catch {{
        container.innerHTML = '<div class="empty-state">Could not load jobs.</div>';
        return;
      }}

      const states = [...new Set(allJobs.map(j => j.state).filter(Boolean))].sort();
      states.forEach(s => {{
        const opt = document.createElement("option");
        opt.value = s; opt.textContent = s;
        stateSelect.appendChild(opt);
      }});

      function render() {{
        const filtered = filterJobs(allJobs, {{
          query: searchInput.value,
          state: stateSelect.value,
          hasSalary: salaryToggle.checked,
          hideRecruiters: recruiterToggle.checked,
        }});
        countEl.textContent = `${{filtered.length}} ${{filtered.length !== 1 ? "jobs" : "job"}}`;
        renderJobList(filtered, currentPage, container);
        renderPagination(filtered.length, currentPage, paginationEl, p => {{
          currentPage = p;
          render();
          window.scrollTo({{ top: 0, behavior: "smooth" }});
        }});
      }}

      let t;
      searchInput.addEventListener("input", () => {{ clearTimeout(t); t = setTimeout(() => {{ currentPage = 1; render(); }}, 200); }});
      stateSelect.addEventListener("change", () => {{ currentPage = 1; render(); }});
      [salaryToggle, recruiterToggle].forEach(el => el.addEventListener("change", () => {{ currentPage = 1; render(); }}));
      render();
    }}
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# Main export
# ---------------------------------------------------------------------------

def export_for_frontend(jobs: list[dict], stats: dict):
    """Export jobs to frontend data files + generate SEO pages."""
    os.makedirs(EXPORT_DIR, exist_ok=True)

    list_jobs = []
    detail_count = 0

    for job in jobs:
        entry = _build_list_entry(job)
        list_jobs.append(entry)

        jid = entry["id"]
        prefix = _prefix(jid)
        if job.get("description_html") or job.get("description_plain"):
            detail = {
                **entry,
                "description_html": job.get("description_html"),
                "description_plain": job.get("description_plain"),
            }
            detail_dir = os.path.join(DETAIL_DIR, prefix)
            os.makedirs(detail_dir, exist_ok=True)
            with open(os.path.join(detail_dir, f"{jid}.json"), "w") as f:
                json.dump(detail, f, separators=(",", ":"))
            detail_count += 1

    with open(JOBS_JSON, "w") as f:
        json.dump(list_jobs, f, separators=(",", ":"))

    meta = {
        "total": len(list_jobs),
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "by_platform": stats.get("by_ats", {}),
        "enriched": stats.get("enriched", 0),
    }
    with open(META_JSON, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Exported %d list jobs, %d detail files", len(list_jobs), detail_count)

    # Generate SEO category pages
    _generate_category_pages(list_jobs)
    _generate_state_pages(list_jobs)
    _generate_sitemap(list_jobs)


def _generate_category_pages(list_jobs: list[dict]):
    """Generate /jobs/{slug}/index.html for each SEO category."""
    cat_dir = os.path.join(FRONTEND_DIR, "jobs")
    os.makedirs(cat_dir, exist_ok=True)
    generated = 0

    for slug, display, regex, meta_desc_tmpl in SEO_CATEGORIES:
        if regex:
            pat = re.compile(regex, re.IGNORECASE)
            matched = [j for j in list_jobs if pat.search(j["title"]) or pat.search(" ".join(j.get("departments", [])))]
        elif slug == "nursing-with-salary":
            matched = [j for j in list_jobs if j.get("salary_min")]
        else:
            matched = list_jobs

        if not matched:
            continue

        companies = set(j["company_name"] for j in matched)
        meta_desc = meta_desc_tmpl.format(count=len(matched))

        category_filter = {}
        if regex:
            category_filter["regex"] = regex
        if slug == "nursing-with-salary":
            category_filter["hasSalary"] = True

        page_dir = os.path.join(cat_dir, slug)
        os.makedirs(page_dir, exist_ok=True)

        html = CATEGORY_TEMPLATE.format(
            title=f"{display} Jobs",
            meta_description=meta_desc,
            canonical=f"{SITE_URL}/jobs/{slug}/",
            css_path="../../css/style.css",
            heading=f"{display} Jobs",
            heading_lower=display.lower(),
            description=meta_desc,
            source_count=len(companies),
            extra_seo="",
            js_path="../../js",
            data_path="../../data",
            category_filter_json=json.dumps(category_filter),
        )

        with open(os.path.join(page_dir, "index.html"), "w") as f:
            f.write(html)
        generated += 1

    logger.info("Generated %d category pages", generated)


def _generate_state_pages(list_jobs: list[dict]):
    """Generate /jobs/state/{abbr}/index.html for each state with jobs."""
    state_dir = os.path.join(FRONTEND_DIR, "jobs", "state")
    os.makedirs(state_dir, exist_ok=True)
    generated = 0

    # Group by state
    by_state: dict[str, list] = {}
    for j in list_jobs:
        st = j.get("state")
        if st:
            by_state.setdefault(st, []).append(j)

    for abbr, state_jobs in by_state.items():
        full_name = STATE_NAMES.get(abbr, abbr)
        companies = set(j["company_name"] for j in state_jobs)

        page_dir = os.path.join(state_dir, abbr.lower())
        os.makedirs(page_dir, exist_ok=True)

        html = CATEGORY_TEMPLATE.format(
            title=f"Nursing Jobs in {full_name}",
            meta_description=f"Browse {len(state_jobs)} nursing jobs in {full_name} ({abbr}). Updated daily with salary data and direct application links.",
            canonical=f"{SITE_URL}/jobs/state/{abbr.lower()}/",
            css_path="../../../css/style.css",
            heading=f"Nursing Jobs in {full_name}",
            heading_lower=f"nursing in {full_name}",
            description=f"Browse {len(state_jobs)} nursing jobs in {full_name}. Updated daily with salary data and direct application links.",
            source_count=len(companies),
            extra_seo=f"<p>We track nursing positions in {full_name} from {len(companies)} healthcare employers. Roles include RN, LPN, CNA, nurse practitioner, and more.</p>",
            js_path="../../../js",
            data_path="../../../data",
            category_filter_json=json.dumps({"state": abbr}),
        )

        with open(os.path.join(page_dir, "index.html"), "w") as f:
            f.write(html)
        generated += 1

    logger.info("Generated %d state pages", generated)


def _generate_sitemap(list_jobs: list[dict]):
    """Generate sitemap.xml for search engines."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urls = [
        f'  <url><loc>{SITE_URL}/</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>',
    ]

    # Category pages
    for slug, display, regex, _ in SEO_CATEGORIES:
        if regex:
            pat = re.compile(regex, re.IGNORECASE)
            count = sum(1 for j in list_jobs if pat.search(j["title"]))
        elif slug == "nursing-with-salary":
            count = sum(1 for j in list_jobs if j.get("salary_min"))
        else:
            count = len(list_jobs)
        if count > 0:
            urls.append(f'  <url><loc>{SITE_URL}/jobs/{slug}/</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>0.8</priority></url>')

    # State pages
    states_with_jobs = set(j.get("state") for j in list_jobs if j.get("state"))
    for abbr in sorted(states_with_jobs):
        urls.append(f'  <url><loc>{SITE_URL}/jobs/state/{abbr.lower()}/</loc><lastmod>{now}</lastmod><changefreq>daily</changefreq><priority>0.7</priority></url>')

    # Job detail pages
    for j in list_jobs:
        urls.append(f'  <url><loc>{SITE_URL}/job.html?id={j["id"]}</loc><lastmod>{now}</lastmod><changefreq>weekly</changefreq><priority>0.5</priority></url>')

    sitemap = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "\n".join(urls) + "\n</urlset>"

    with open(os.path.join(FRONTEND_DIR, "sitemap.xml"), "w") as f:
        f.write(sitemap)

    # robots.txt
    with open(os.path.join(FRONTEND_DIR, "robots.txt"), "w") as f:
        f.write(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}/sitemap.xml\n")

    logger.info("Generated sitemap with %d URLs", len(urls))
