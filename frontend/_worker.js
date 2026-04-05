const JOB_PAGE_HTML = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ScrubShifts - Job Details</title>
  <link rel="stylesheet" href="/css/style.css">
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

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    // Serve job detail page for /listing/* paths
    if (url.pathname.startsWith("/listing/")) {
      return new Response(JOB_PAGE_HTML, {
        headers: { "Content-Type": "text/html;charset=UTF-8" },
      });
    }

    // Everything else: pass through to static assets
    return env.ASSETS.fetch(request);
  },
};
