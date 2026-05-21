# ScrubShifts — Project Instructions

## What This Is
Healthcare job aggregator (scrubshifts.com). ~8K nursing + allied health jobs from 500+ employers, updated daily via automated pipeline.

## Stack
- **Pipeline**: Python (`pipeline/`) → SQLite (`data/nursing_jobs.db`)
- **Frontend**: Static HTML + vanilla JS on Cloudflare Pages
- **Worker**: `frontend/_worker.js` — SSR for `/listing/*` job detail pages + injects Google Analytics into all HTML
- **Deploy**: GitHub Actions → `wrangler pages deploy frontend --project-name=scrubshifts`

## Critical Rules

### Never break production
- This is a **live site**. Changes to committed files deploy automatically within hours (5 deploys/day).
- Always read existing code before modifying. Understand what it does first.

### Gitignored = generated
These directories are **gitignored and regenerated every pipeline run** by `pipeline/export.py`:
- `frontend/data/` (jobs.json, detail chunks, zips, cities)
- `frontend/jobs/` (pre-rendered category pages)
- `frontend/logos/` (company logos)
- `frontend/sitemap.xml`, `frontend/robots.txt`

To change these, edit `pipeline/export.py` templates — not the generated files.

### Template locations (keep in sync)
Page header/nav/footer exists in **5 places**:
1. `frontend/_worker.js` (job detail SSR template)
2. `pipeline/export.py` (~line 500, category page template)
3. `pipeline/export.py` (~line 750, homepage template)
4. `frontend/index.html`
5. `frontend/alerts.html` and `frontend/promote.html`

When changing nav links or site-wide elements, update ALL locations.

### Worker is the single source of truth for:
- Google Analytics (gtag G-4X9CP554TV) — injected into all HTML responses
- Job detail SEO metadata (title, description, canonical, JSON-LD)
- 404 handling for expired jobs (HTTP 404 + noindex)

Don't add gtag to individual HTML files — the worker handles it.

### Domain
Production domain is `scrubshifts.com`. Old domain `nurseboard.pages.dev` still resolves but should never be used in code. All canonical tags must point to scrubshifts.com.

## Key Constants
- Salary stored in **cents** (INTEGER). $50K/yr = 5000000
- Job IDs = MD5 of URL, first 12 hex chars
- Detail chunks keyed by 2-char hex prefix (`/data/jobs/{prefix}.json`) due to Cloudflare's 20K file limit
- MAX_JOB_AGE_DAYS = 30, MIN_JOBS_FOR_PAGE = 3, MAX_URLS_PER_SITEMAP = 25000

## ATS Platforms
Greenhouse, Lever, Ashby, Workday, BambooHR, Oracle HCM (active)
Workable, NeoGov (exist but disabled)

## GitHub Actions
- `nursing-pipeline.yml` — daily full pipeline @ 2:30 UTC
- `enrich.yml` — enrichment-only 4x/day (3:00, 9:00, 15:00, 21:00 UTC)
- `rollback.yml` — manual rollback to previous Cloudflare deployment

## Secrets (GitHub Actions)
CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID, USAJOBS_API_KEY, USAJOBS_EMAIL
