/**
 * Entry point for the job list page.
 */
import { filterJobs } from "./filters.js";
import { renderJobList, renderPagination } from "./list.js";

initListPage();

async function initListPage() {
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

  try {
    const resp = await fetch("data/jobs.json");
    if (!resp.ok) throw new Error("Failed to load jobs");
    allJobs = await resp.json();
  } catch {
    container.innerHTML =
      '<div class="empty-state">Could not load jobs. Run the pipeline first.</div>';
    return;
  }

  // Populate ATS filter options
  const platforms = [...new Set(allJobs.map((j) => j.ats_platform).filter(Boolean))].sort();
  platforms.forEach((p) => {
    const opt = document.createElement("option");
    opt.value = p;
    opt.textContent = p;
    atsSelect.appendChild(opt);
  });

  // Populate state filter options
  const states = [...new Set(allJobs.map((j) => j.state).filter(Boolean))].sort();
  states.forEach((s) => {
    const opt = document.createElement("option");
    opt.value = s;
    opt.textContent = s;
    stateSelect.appendChild(opt);
  });

  function render() {
    const filtered = filterJobs(allJobs, {
      query: searchInput.value,
      state: stateSelect.value,
      ats: atsSelect.value,
      hasSalary: salaryToggle.checked,
      hideRecruiters: recruiterToggle.checked,
    });

    countEl.textContent = `${filtered.length} nursing job${filtered.length !== 1 ? "s" : ""}`;
    renderJobList(filtered, currentPage, container);
    renderPagination(filtered.length, currentPage, paginationEl, (p) => {
      currentPage = p;
      render();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  let debounceTimer;
  searchInput.addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      currentPage = 1;
      render();
    }, 200);
  });

  [stateSelect, atsSelect].forEach((el) =>
    el.addEventListener("change", () => {
      currentPage = 1;
      render();
    })
  );

  [salaryToggle, recruiterToggle].forEach((el) =>
    el.addEventListener("change", () => {
      currentPage = 1;
      render();
    })
  );

  render();
}
