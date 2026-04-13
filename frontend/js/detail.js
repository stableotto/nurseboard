/**
 * Job detail page rendering.
 */
import { formatDate } from "./time.js";
import { formatSalary, companyColor } from "./filters.js";

export async function renderDetail(container) {
  // Parse slug from path: /listing/at/company/title-hash/
  // Last 12 chars of slug are the job ID for direct detail file lookup
  const path = window.location.pathname;
  const slug = path.replace(/^\/listing\//, "").replace(/\/$/, "");

  if (!slug) {
    container.innerHTML = '<div class="empty-state">Job not found.</div>';
    return;
  }

  // Extract job ID from end of slug (last 12 hex chars after final hyphen)
  const parts = slug.split("-");
  const id = parts[parts.length - 1];
  if (!id || id.length < 12) {
    container.innerHTML = '<div class="empty-state">Job not found.</div>';
    return;
  }

  const prefix = id.substring(0, 2);

  // Single request — go straight to the detail JSON file
  let job = null;
  try {
    const resp = await fetch(`/data/jobs/${prefix}/${id}.json`);
    if (resp.ok) job = await resp.json();
  } catch {}

  if (!job) {
    container.innerHTML = '<div class="empty-state">Job not found. <a href="/">Back to jobs</a></div>';
    return;
  }

  renderJobDetail(job, container);

  // Inject JSON-LD if present
  if (job.jsonld) {
    const existing = document.querySelector('script[type="application/ld+json"]');
    if (!existing) {
      document.head.insertAdjacentHTML("beforeend", job.jsonld);
    }
  }
}

function slugify(text) {
  return (text || "unknown").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 80);
}

function renderJobDetail(job, container) {
  const color = companyColor(job.company_name);
  const salary = formatSalary(job.salary_min, job.salary_max, job.salary_currency);
  const posted = formatDate(job.posted_date || job.first_seen_at);
  const hasDescription = job.description_html || job.description_plain;

  const metaParts = [
    (job.departments || []).join(", "),
    salary ? `<span class="salary">${salary}</span>` : null,
    job.location,
  ].filter(Boolean);

  const deptTags = (job.departments || [])
    .map((d) => `<span class="dept-tag">${escapeHtml(d)}</span>`)
    .join("");

  const descHtml = hasDescription
    ? sanitizeHtml(job.description_html || job.description_plain)
    : '<p class="no-description">Full description not yet available. Click "Apply" to view on the original posting.</p>';

  container.innerHTML = `
    <div class="breadcrumb">
      <a href="/">Home</a>
      <span class="sep">&rsaquo;</span>
      <span>${escapeHtml(job.company_name || "")}</span>
      <span class="sep">&rsaquo;</span>
      <span>${escapeHtml(job.title)}</span>
    </div>

    <div class="detail-layout">
      <div class="detail-main">
        <div class="detail-company">
          <div class="company-avatar" style="background:${color}">
            <img src="/logos/${slugify(job.company_name)}.png" alt="" class="company-logo"
              onload="this.nextElementSibling.style.display='none'"
              onerror="this.onerror=null;this.style.display='none'">
            <span class="avatar-fallback">${(job.company_name || "?")[0].toUpperCase()}</span>
          </div>
          <span class="detail-company-name">${escapeHtml(job.company_name || "")}</span>
        </div>
        <h1 class="detail-title">${escapeHtml(job.title)}</h1>
        <div class="detail-meta">${metaParts.join('<span style="color:var(--border)">|</span>')}</div>
        ${deptTags ? `<div class="dept-tags">${deptTags}</div>` : ""}
        <div class="description">${descHtml}</div>
      </div>

      <div class="detail-sidebar">
        <div class="sidebar-card">
          <a class="apply-btn" href="${escapeAttr(job.url)}" target="_blank" rel="noopener">Apply for this job</a>
          <dl class="sidebar-info">
            <dt>Company</dt>
            <dd>${escapeHtml(job.company_name || job.company_slug)}</dd>
            <dt>Posted</dt>
            <dd>${posted}</dd>
            ${job.location ? `<dt>Location</dt><dd>${escapeHtml(job.location)}</dd>` : ""}
          </dl>
        </div>
      </div>
    </div>
  `;
}

function sanitizeHtml(html) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  doc.querySelectorAll("script, style, iframe, object, embed").forEach((el) => el.remove());
  return doc.body.innerHTML;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str || "";
  return div.innerHTML;
}

function escapeAttr(str) {
  return (str || "").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}
