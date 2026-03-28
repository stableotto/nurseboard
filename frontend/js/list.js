/**
 * Job list rendering and pagination.
 */
import { relativeTime } from "./time.js";
import { formatSalary, companyColor } from "./filters.js";

const JOBS_PER_PAGE = 25;

export function renderJobList(jobs, page, container) {
  const start = (page - 1) * JOBS_PER_PAGE;
  const pageJobs = jobs.slice(start, start + JOBS_PER_PAGE);

  if (pageJobs.length === 0) {
    container.innerHTML = '<div class="empty-state">No jobs match your filters.</div>';
    return;
  }

  container.innerHTML = pageJobs
    .map((job) => {
      const initial = (job.company_name || "?")[0].toUpperCase();
      const color = companyColor(job.company_name);
      const salary = formatSalary(job.salary_min, job.salary_max, job.salary_currency);
      const time = relativeTime(job.posted_date || job.first_seen_at);
      const depts = (job.departments || []).join(", ");
      const metaParts = [
        job.company_name,
        depts,
        salary ? `<span class="salary">${salary}</span>` : null,
      ].filter(Boolean);

      return `<a class="job-row" href="job.html?id=${job.id}">
        <div class="company-avatar" style="background:${color}">${initial}</div>
        <div class="job-info">
          <div class="job-title">${escapeHtml(job.title)}</div>
          <div class="job-meta">${metaParts.join(" &middot; ")}</div>
        </div>
        <div class="job-right">
          <div class="job-location">${escapeHtml(job.location || "")}</div>
          <div class="job-time">${time}</div>
        </div>
      </a>`;
    })
    .join("");
}

export function renderPagination(totalJobs, page, container, onPageChange) {
  const totalPages = Math.ceil(totalJobs / JOBS_PER_PAGE);
  if (totalPages <= 1) {
    container.innerHTML = "";
    return;
  }

  container.innerHTML = `
    <button id="prev-btn" ${page <= 1 ? "disabled" : ""}>Previous</button>
    <span class="page-info">Page ${page} of ${totalPages}</span>
    <button id="next-btn" ${page >= totalPages ? "disabled" : ""}>Next</button>
  `;

  container.querySelector("#prev-btn").addEventListener("click", () => {
    if (page > 1) onPageChange(page - 1);
  });
  container.querySelector("#next-btn").addEventListener("click", () => {
    if (page < totalPages) onPageChange(page + 1);
  });
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}
