const GTAG = `<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-4X9CP554TV"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-4X9CP554TV');
</script>`;

function escapeHtml(str) {
  return (str || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function escapeAttr(str) {
  return (str || "").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function stripHtml(html) {
  return (html || "").replace(/<[^>]*>/g, " ").replace(/\s+/g, " ").trim();
}

// Strip active content from enriched description HTML before SSR.
function sanitizeHtml(html) {
  return (html || "").replace(/<(script|style|iframe|object|embed)[\s\S]*?<\/\1>/gi, "");
}

function slugify(text) {
  return (text || "unknown")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80);
}

// Salary stored in cents. Mirrors frontend/js/filters.js formatSalary().
function formatSalary(min, max) {
  if (min == null && max == null) return null;
  const fmt = (cents) => {
    const dollars = cents / 100;
    if (dollars >= 1000) return `$${Math.round(dollars / 1000)}k`;
    return `$${Math.round(dollars)}`;
  };
  if (min != null && max != null) {
    if (min === max) return fmt(min);
    return `${fmt(min)} - ${fmt(max)}`;
  }
  if (min != null) return `${fmt(min)}+`;
  return `Up to ${fmt(max)}`;
}

const AVATAR_COLORS = [
  "#6366f1", "#8b5cf6", "#ec4899", "#f43f5e",
  "#f97316", "#eab308", "#22c55e", "#14b8a6",
  "#06b6d4", "#3b82f6", "#a855f7", "#e11d48",
];

// Mirrors frontend/js/filters.js companyColor().
function companyColor(name) {
  let hash = 0;
  for (let i = 0; i < (name || "").length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  return AVATAR_COLORS[Math.abs(hash) % AVATAR_COLORS.length];
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// Manual format (avoids Workers ICU dependence). Mirrors frontend/js/time.js formatDate().
function formatDate(dateStr) {
  if (!dateStr) return "";
  const d = new Date(dateStr);
  if (isNaN(d.getTime())) return "";
  return `${MONTHS[d.getUTCMonth()]} ${d.getUTCDate()}, ${d.getUTCFullYear()}`;
}

// Server-render the job detail body so the page has real content at crawl
// time (Googlebot does not run our JS module before deciding to index).
// Mirrors renderJobDetail() in frontend/js/detail.js.
function buildBody(job) {
  if (!job) {
    return '<div class="empty-state">Job not found. <a href="/">Back to jobs</a></div>';
  }

  const company = job.company_name || job.company_slug || "";
  const color = companyColor(job.company_name);
  const salary = formatSalary(job.salary_min, job.salary_max);
  const posted = formatDate(job.posted_date || job.first_seen_at);
  const departments = job.departments || [];

  const metaParts = [
    departments.length ? escapeHtml(departments.join(", ")) : null,
    salary ? `<span class="salary">${escapeHtml(salary)}</span>` : null,
    job.location ? escapeHtml(job.location) : null,
  ].filter(Boolean);

  const deptTags = departments
    .map((d) => `<span class="dept-tag">${escapeHtml(d)}</span>`)
    .join("");

  const descHtml = (job.description_html || job.description_plain)
    ? sanitizeHtml(job.description_html || "")
    : '<p class="no-description">Full description not yet available. Click "Apply" to view on the original posting.</p>';

  const initial = (job.company_name || "?").charAt(0).toUpperCase();

  return `
    <div class="breadcrumb">
      <a href="/">Home</a>
      <span class="sep">&rsaquo;</span>
      <span>${escapeHtml(company)}</span>
      <span class="sep">&rsaquo;</span>
      <span>${escapeHtml(job.title)}</span>
    </div>
    <div class="detail-layout">
      <div class="detail-main">
        <div class="detail-company">
          <div class="company-avatar" style="background:${color}">
            <img src="/logos/${slugify(job.company_name)}.png" alt="" class="company-logo"
              onload="this.parentNode.style.background='none';this.nextElementSibling.style.display='none'"
              onerror="this.onerror=null;this.style.display='none'">
            <span class="avatar-fallback">${escapeHtml(initial)}</span>
          </div>
          <span class="detail-company-name">${escapeHtml(company)}</span>
        </div>
        <h1 class="detail-title">${escapeHtml(job.title)}</h1>
        <div class="detail-meta">${metaParts.join('<span style="color:var(--border)">|</span>')}</div>
        ${deptTags ? `<div class="dept-tags">${deptTags}</div>` : ""}
        <div class="description">${descHtml}</div>
      </div>
      <div class="detail-sidebar">
        <div class="sidebar-card">
          <a class="apply-btn" href="${escapeAttr(job.url)}" target="_blank" rel="noopener">Apply for this job</a>
          ${salary ? `<div class="sidebar-salary">${escapeHtml(salary)}</div>` : ""}
          <dl class="sidebar-info">
            <dt>Company</dt>
            <dd>${escapeHtml(company)}</dd>
            <dt>Posted</dt>
            <dd>${escapeHtml(posted)}</dd>
            ${job.location ? `<dt>Location</dt><dd>${escapeHtml(job.location)}</dd>` : ""}
          </dl>
        </div>
      </div>
    </div>`;
}

function buildPage(job, slug) {
  const title = job
    ? `${escapeHtml(job.title)} at ${escapeHtml(job.company_name)} – ScrubShifts`
    : "Job Not Found – ScrubShifts";

  const description = job
    ? escapeAttr(
        stripHtml(job.description_html || "").slice(0, 160) ||
          `${job.title} at ${job.company_name}${job.location ? ` in ${job.location}` : ""}`
      )
    : "This job is no longer available.";

  const canonical = job
    ? `https://scrubshifts.com/listing/${escapeAttr(job.slug || slug)}/`
    : "";

  const jsonld = job && job.jsonld ? job.jsonld : "";

  const robotsMeta = job
    ? ""
    : '<meta name="robots" content="noindex">';

  return `<!DOCTYPE html>
<html lang="en">
<head>
  ${GTAG}
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${title}</title>
  <meta name="description" content="${description}">
  ${canonical ? `<link rel="canonical" href="${canonical}">` : ""}
  ${robotsMeta}
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="/css/style.css">
  ${jsonld}
</head>
<body>
  <header class="header">
    <div class="container">
      <div class="header-left">
        <a href="/" class="logo">ScrubShifts</a>
        <nav class="header-nav">
          <a href="/jobs/rn/">RN Jobs</a>
          <a href="/jobs/nurse-practitioner/">NP Jobs</a>
          <a href="/jobs/cna/">CNA Jobs</a>
          <a href="/alerts.html">Alerts</a>
          <a href="/promote.html">For Employers</a>
        </nav>
      </div>
    </div>
  </header>
  <main class="container" id="app">${buildBody(job)}</main>
  <script type="module">
    import { renderDetail } from "/js/detail.js";
    renderDetail(document.getElementById("app"));
  </script>
</body>
</html>`;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Serve job detail page for /listing/* paths
    if (url.pathname.startsWith("/listing/")) {
      const slug = url.pathname.replace(/^\/listing\//, "").replace(/\/$/, "");

      // Extract job ID (last 12 hex chars after final hyphen)
      const parts = slug.split("-");
      const id = parts.length > 0 ? parts[parts.length - 1] : "";
      const validId = Boolean(id && id.length >= 12);

      let job = null;
      if (validId) {
        const prefix = id.substring(0, 2);
        try {
          const dataReq = new Request(new URL(`/data/jobs/${prefix}.json`, url.origin));
          const resp = await env.ASSETS.fetch(dataReq);
          if (resp.ok) {
            const chunk = await resp.json();
            job = chunk[id] || null;
          }
        } catch {}
      }

      // 200 when found. A well-formed listing URL whose job is gone returns
      // 410 Gone (expired) so Google de-indexes it quickly and stops
      // re-flagging it as a soft 404; malformed URLs return 404.
      const status = job ? 200 : validId ? 410 : 404;

      const html = buildPage(job, slug);
      return new Response(html, {
        status,
        headers: { "Content-Type": "text/html;charset=UTF-8" },
      });
    }

    // Everything else: pass through to static assets, inject gtag into HTML
    const resp = await env.ASSETS.fetch(request);
    const ct = resp.headers.get("content-type") || "";
    if (ct.includes("text/html")) {
      const html = await resp.text();
      const injected = html.replace("<head>", `<head>\n  ${GTAG}`);
      // Drop the upstream Content-Length: the injected body is longer than
      // the original asset, and a stale length truncates the response.
      const headers = new Headers(resp.headers);
      headers.delete("content-length");
      return new Response(injected, {
        status: resp.status,
        headers,
      });
    }
    return resp;
  },
};
