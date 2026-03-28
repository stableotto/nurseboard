/**
 * Search and filter logic.
 */
export function filterJobs(jobs, { query, state, ats, hasSalary, hideRecruiters }) {
  let filtered = jobs;

  if (query) {
    const q = query.toLowerCase();
    filtered = filtered.filter(
      (j) =>
        j.title.toLowerCase().includes(q) ||
        (j.company_name || "").toLowerCase().includes(q) ||
        (j.location || "").toLowerCase().includes(q)
    );
  }

  if (state) {
    filtered = filtered.filter((j) => j.state === state);
  }

  if (ats) {
    filtered = filtered.filter((j) => j.ats_platform === ats);
  }

  if (hasSalary) {
    filtered = filtered.filter((j) => j.salary_min != null);
  }

  if (hideRecruiters) {
    filtered = filtered.filter((j) => !j.is_recruiter);
  }

  return filtered;
}

export function formatSalary(min, max, currency) {
  if (min == null && max == null) return null;
  const fmt = (cents) => {
    const dollars = cents / 100;
    if (dollars >= 1000) return `$${Math.round(dollars / 1000)}k`;
    return `$${Math.round(dollars)}`;
  };
  if (min != null && max != null) return `${fmt(min)} - ${fmt(max)}`;
  if (min != null) return `${fmt(min)}+`;
  return `Up to ${fmt(max)}`;
}

export function companyColor(name) {
  let hash = 0;
  for (let i = 0; i < (name || "").length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }
  const colors = [
    "#6366f1", "#8b5cf6", "#ec4899", "#f43f5e",
    "#f97316", "#eab308", "#22c55e", "#14b8a6",
    "#06b6d4", "#3b82f6", "#a855f7", "#e11d48",
  ];
  return colors[Math.abs(hash) % colors.length];
}
