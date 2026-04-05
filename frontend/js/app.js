/**
 * Entry point for the job list page.
 * Works on homepage and category pages.
 * Category pages set window.__CATEGORY_FILTER to pre-filter jobs.
 */
import { filterJobs } from "./filters.js";
import { renderJobList, renderPagination } from "./list.js";
import { filterByRadius } from "./radius.js";

initListPage();

async function initListPage() {
  const container = document.getElementById("job-list");
  if (!container) return;
  const paginationEl = document.getElementById("pagination");
  const countEl = document.getElementById("result-count");
  const searchInput = document.getElementById("search");
  const roleSelect = document.getElementById("filter-role");
  const stateSelect = document.getElementById("filter-state");
  const metroSelect = document.getElementById("filter-metro");
  const zipInput = document.getElementById("filter-zip");
  const radiusSelect = document.getElementById("filter-radius");
  const salaryToggle = document.getElementById("filter-salary");
  const recruiterToggle = document.getElementById("filter-recruiter");

  // Determine data path — category pages may be nested deeper
  const scripts = document.querySelectorAll("script[src*='app.js']");
  let dataPath = "data/jobs.json";
  if (scripts.length) {
    const src = scripts[0].getAttribute("src");
    const jsIdx = src.indexOf("js/app.js");
    if (jsIdx > 0) {
      dataPath = src.substring(0, jsIdx) + "data/jobs.json";
    }
  }

  let allJobs = [];
  let currentPage = 1;
  const catFilter = window.__CATEGORY_FILTER || {};

  try {
    const resp = await fetch(dataPath);
    if (!resp.ok) throw new Error("Failed to load jobs");
    let jobs = await resp.json();

    // Apply category pre-filter
    if (catFilter.regex) {
      const re = new RegExp(catFilter.regex, "i");
      jobs = jobs.filter((j) => re.test(j.title));
    }
    if (catFilter.state) {
      jobs = jobs.filter((j) => j.state === catFilter.state);
    }
    if (catFilter.company) {
      const cs = catFilter.company;
      jobs = jobs.filter((j) => j.slug && j.slug.split("/")[1] === cs);
    }
    if (catFilter.metro) {
      jobs = jobs.filter((j) => j.metro === catFilter.metro);
    }
    if (catFilter.hasSalary) {
      jobs = jobs.filter((j) => j.salary_min != null);
    }
    allJobs = jobs;
  } catch {
    container.innerHTML =
      '<div class="empty-state">Could not load jobs. Run the pipeline first.</div>';
    return;
  }

  // Populate state filter (only if not already locked by category)
  if (stateSelect && !catFilter.state) {
    const states = [...new Set(allJobs.map((j) => j.state).filter(Boolean))].sort();
    states.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = s;
      opt.textContent = s;
      stateSelect.appendChild(opt);
    });
  } else if (stateSelect && catFilter.state) {
    stateSelect.style.display = "none";
  }

  // Populate metro filter
  if (metroSelect && !catFilter.metro) {
    const metros = [...new Set(allJobs.map((j) => j.metro).filter(Boolean))].sort();
    metros.forEach((m) => {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m.replace(/-/g, " ").replace(/\b\w/g, c => c.toUpperCase());
      metroSelect.appendChild(opt);
    });
  } else if (metroSelect && catFilter.metro) {
    metroSelect.style.display = "none";
  }

  async function render() {
    let filtered = filterJobs(allJobs, {
      query: searchInput ? searchInput.value : "",
      role: roleSelect ? roleSelect.value : "",
      state: stateSelect ? stateSelect.value : "",
      metro: metroSelect ? metroSelect.value : "",
      hasSalary: salaryToggle ? salaryToggle.checked : false,
      hideRecruiters: recruiterToggle ? recruiterToggle.checked : false,
    });

    // Apply radius filter if zip + radius are set
    const zip = zipInput ? zipInput.value.trim() : "";
    const radius = radiusSelect ? parseInt(radiusSelect.value) : 0;
    if (zip.length === 5 && radius > 0) {
      filtered = await filterByRadius(filtered, zip, radius);
      // Sort by distance
      filtered.sort((a, b) => (a._distance || 999) - (b._distance || 999));
    }

    if (countEl) {
      countEl.textContent = `${filtered.length} nursing job${filtered.length !== 1 ? "s" : ""}`;
    }
    renderJobList(filtered, currentPage, container);
    if (paginationEl) {
      renderPagination(filtered.length, currentPage, paginationEl, (p) => {
        currentPage = p;
        render();
        window.scrollTo({ top: 0, behavior: "smooth" });
      });
    }
  }

  let debounceTimer;
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => {
        currentPage = 1;
        render();
      }, 200);
    });
  }

  // Location filters: radius, metro, state are mutually exclusive
  if (zipInput) {
    let zipTimer;
    const onZipChange = () => {
      clearTimeout(zipTimer);
      zipTimer = setTimeout(() => {
        if (zipInput.value.trim().length === 5 && radiusSelect && radiusSelect.value) {
          if (stateSelect) stateSelect.value = "";
          if (metroSelect) metroSelect.value = "";
          currentPage = 1;
          render();
        }
      }, 300);
    };
    zipInput.addEventListener("input", onZipChange);
  }
  if (radiusSelect) {
    radiusSelect.addEventListener("change", () => {
      if (zipInput && zipInput.value.trim().length === 5) {
        if (stateSelect) stateSelect.value = "";
        if (metroSelect) metroSelect.value = "";
        currentPage = 1;
        render();
      }
    });
  }
  if (metroSelect) {
    metroSelect.addEventListener("change", () => {
      if (metroSelect.value) {
        if (stateSelect) stateSelect.value = "";
        if (zipInput) zipInput.value = "";
        if (radiusSelect) radiusSelect.value = "";
      }
      currentPage = 1;
      render();
    });
  }
  if (stateSelect) {
    stateSelect.addEventListener("change", () => {
      if (stateSelect.value) {
        if (metroSelect) metroSelect.value = "";
        if (zipInput) zipInput.value = "";
        if (radiusSelect) radiusSelect.value = "";
      }
      currentPage = 1;
      render();
    });
  }

  [roleSelect].forEach((el) => {
    if (el) el.addEventListener("change", () => { currentPage = 1; render(); });
  });

  [salaryToggle, recruiterToggle].forEach((el) => {
    if (el) el.addEventListener("change", () => { currentPage = 1; render(); });
  });

  render();
}
