/**
 * Search and filter logic.
 */

const ROLE_PATTERNS = {
  // Nursing
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
  // Allied Health — Therapy
  "physical-therapist": /\bphysical\s+therap(?:ist|y)\b|\bDPT\b|\bPTA\b/i,
  "occupational-therapist": /\boccupational\s+therap(?:ist|y)\b|\bOTR\b|\bCOTA\b/i,
  "speech-language-pathologist": /\bSLP\b|\bspeech[\s\-]?language\s+patholog(?:ist|y)\b|\bspeech\s+therap(?:ist|y)\b/i,
  "respiratory-therapist": /\brespiratory\s+therap(?:ist|y)\b|\bRRT\b|\bCRT\b/i,
  // Allied Health — Diagnostic / Lab
  "radiology-technologist": /\brad(?:iologic(?:al)?|iology)\s+tech|\bx[\s\-]?ray\s+tech|\bCT\s+tech|\bMRI\s+tech|\bsonograph|\bultrasound\s+tech|\bdiagnostic\s+imaging/i,
  "lab-technician": /\bMLT\b|\bMLS\b|\bCLS\b|\bmedical\s+lab(?:oratory)?\s+(?:tech|scientist)|\blab(?:oratory)?\s+tech(?:nician|nologist)?/i,
  "phlebotomist": /\bphlebotom(?:ist|y)\b/i,
  // Allied Health — Pharmacy / Nutrition
  "pharmacist": /\bPharmD\b|\bRPh\b|\bpharmac(?:ist|y\s+tech)|\bpharmacy\s+tech(?:nician)?/i,
  "dietitian": /\bRDN\b|\bdietit(?:ian|ion)\b|\bnutritionist\b|\bclinical\s+nutrition\b/i,
  // Allied Health — Other
  "medical-assistant": /\bmedical\s+assistant\b|\bCMA\b|\bclinical\s+medical\s+assistant\b/i,
  "surgical-technologist": /\bsurg(?:ical)?\s+tech(?:nolog(?:ist|y))?\b|\bCST\b|\boperating\s+room\s+tech\b/i,
  "paramedic": /\bparamedic\b|\bEMT\b|\bemergency\s+medical\s+tech(?:nician)?/i,
  "dental-hygienist": /\bdental\s+hygien(?:ist|e)\b|\bRDH\b/i,
  "social-worker": /\bLCSW\b|\bLMSW\b|\bmedical\s+social\s+worker\b|\bclinical\s+social\s+worker\b/i,
  "athletic-trainer": /\bathletic\s+train(?:er|ing)\b|\bATC\b/i,
};

export function filterJobs(jobs, { query, role, state, metro, hasSalary }) {
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

  if (hasSalary) {
    filtered = filtered.filter((j) => j.salary_min != null);
  }

  return filtered;
}

export function interleaveByCompany(jobs) {
  // Group by company, keeping each group sorted by date (already sorted)
  const byCompany = {};
  for (const job of jobs) {
    const key = job.company_name || "unknown";
    if (!byCompany[key]) byCompany[key] = [];
    byCompany[key].push(job);
  }

  // Sort company groups by their newest job date
  const groups = Object.values(byCompany).sort((a, b) => {
    const da = a[0].posted_date || a[0].first_seen_at || "";
    const db = b[0].posted_date || b[0].first_seen_at || "";
    return db.localeCompare(da);
  });

  // Round-robin: deal one job from each company per round
  const result = [];
  let round = 0;
  let added = true;
  while (added) {
    added = false;
    for (const group of groups) {
      if (round < group.length) {
        result.push(group[round]);
        added = true;
      }
    }
    round++;
  }
  return result;
}

export function formatSalary(min, max, currency) {
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
