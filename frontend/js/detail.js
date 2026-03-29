/**
 * Job detail page rendering.
 */
import { formatDate } from "./time.js";
import { formatSalary, companyColor } from "./filters.js";

export async function renderDetail(container) {
  const params = new URLSearchParams(window.location.search);
  const id = params.get("id");
  if (!id) {
    container.innerHTML = '<div class="empty-state">Job not found.</div>';
    return;
  }

  const prefix = id.substring(0, 2);
  container.innerHTML = '<div class="loading">Loading job details...</div>';

  // Try detail file first, fall back to finding the job in the list data
  let job = null;
  try {
    const resp = await fetch(`data/jobs/${prefix}/${id}.json`);
    if (resp.ok) {
      job = await resp.json();
    }
  } catch {}

  if (!job) {
    // Fall back to list data
    try {
      const listResp = await fetch("data/jobs.json");
      if (listResp.ok) {
        const allJobs = await listResp.json();
        job = allJobs.find((j) => j.id === id);
      }
    } catch {}
  }

  if (!job) {
    container.innerHTML = '<div class="empty-state">Job not found. <a href="/">Back to jobs</a></div>';
    return;
  }

  renderJobDetail(job, container);
}

function renderJobDetail(job, container) {
  const initial = (job.company_name || "?")[0].toUpperCase();
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
          <div class="company-avatar" style="background:${color}">${initial}</div>
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
