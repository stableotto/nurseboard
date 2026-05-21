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
  <main class="container" id="app"></main>
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

      let job = null;
      if (id && id.length >= 12) {
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

      const html = buildPage(job, slug);
      return new Response(html, {
        status: job ? 200 : 404,
        headers: { "Content-Type": "text/html;charset=UTF-8" },
      });
    }

    // Everything else: pass through to static assets, inject gtag into HTML
    const resp = await env.ASSETS.fetch(request);
    const ct = resp.headers.get("content-type") || "";
    if (ct.includes("text/html")) {
      const html = await resp.text();
      const injected = html.replace("<head>", `<head>\n  ${GTAG}`);
      return new Response(injected, {
        status: resp.status,
        headers: resp.headers,
      });
    }
    return resp;
  },
};
