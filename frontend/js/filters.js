/**
 * Search and filter logic.
 */

const ROLE_PATTERNS = {
  "rn": /\bRN\b|\bregistered\s+nurse\b/i,
  "lpn-lvn": /\bLPN\b|\bLVN\b|\blicensed\s+(?:practical|vocational)\s+nurse\b/i,
  "cna": /\bCNA\b|\bcertified\s+nurs(?:e|ing)\s+assistant\b|\bnurse\s+aide\b/i,
  "np": /\bNP\b|\bnurse\s+practitioner\b|\bAPRN\b|\badvanced\s+practice\b/i,
  "case-manager": /\bcase\s+manag(?:er|ement)\b/i,
  "travel-nurse": /\btravel\s+nurs(?:e|ing)\b/i,
  "charge-nurse": /\bcharge\s+nurse\b/i,
  "nurse-manager": /\bnurse\s+manager\b|\bnursing\s+manager\b|\bdirector.*nurs/i,
  "icu": /\bICU\b|\bintensive\s+care\b|\bcritical\s+care\b/i,
  "er": /\bER\b.*nurs|\bemergency\b.*nurs|\bnurs.*\bemergency\b|\bemergency\s+(?:room|department)\b/i,
  "or-nurse": /\bOR\s+nurs|\bsurg(?:ical|ery)\b.*nurs|\bnurs.*\bsurg(?:ical|ery)\b|\boperating\s+room\b/i,
  "home-health": /\bhome\s+health\b|\bhome\s+care\b|\bhospice\b/i,
  "med-surg": /\bmed[\s\-]?surg\b|\bmedical[\s\-]?surgical\b/i,
  "pediatric": /\bpediatric\b|\bNICU\b|\bPICU\b|\bneonatal\b/i,
  "psych": /\bpsych(?:iatric)?\b.*nurs|\bnurs.*\bpsych|\bmental\s+health\b|\bbehavioral\s+health\b/i,
  "oncology": /\boncology\b|\bcancer\b.*nurs|\bnurs.*\bcancer\b/i,
  "crna": /\bCRNA\b|\bnurse\s+anesthetist\b|\banesthesia\b.*nurs/i,
  "midwife": /\bmidwi(?:fe|very|ves)\b/i,
  "educator": /\bnurse\s+educator\b|\bnursing\s+(?:instructor|faculty|professor)\b|\bclinical\s+educator\b/i,
  "telehealth": /\bremote\b|\btelehealth\b|\btelemedicine\b|\bvirtual\s+(?:care|nurse|nursing)\b/i,
};

export function filterJobs(jobs, { query, role, state, metro, shift, hasSalary, hideRecruiters }) {
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

  if (role && ROLE_PATTERNS[role]) {
    const re = ROLE_PATTERNS[role];
    filtered = filtered.filter((j) => re.test(j.title));
  }

  if (metro) {
    filtered = filtered.filter((j) => j.metro === metro);
  } else if (state) {
    filtered = filtered.filter((j) => j.state === state);
  }

  if (shift) {
    filtered = filtered.filter((j) => j.shift === shift);
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
