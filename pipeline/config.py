"""Pipeline configuration: keywords, rate limits, constants."""

import re

# Upstream data source
UPSTREAM_MANIFEST_URL = (
    "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/jobs_manifest.json"
)

# Database
DB_PATH = "data/nursing_jobs.db"

# Export paths
EXPORT_DIR = "frontend/data"
JOBS_JSON = f"{EXPORT_DIR}/jobs.json"
META_JSON = f"{EXPORT_DIR}/meta.json"
DETAIL_DIR = f"{EXPORT_DIR}/jobs"

# Nursing keyword patterns (case-insensitive, word-boundary)
TITLE_KEYWORDS = [
    r"\bRN\b",
    r"\bLPN\b",
    r"\bLVN\b",
    r"\bCNA\b",
    r"\bNP\b",
    r"\bBSN\b",
    r"\bMSN\b",
    r"\bDNP\b",
    r"\bAPRN\b",
    r"\bCRNA\b",
    r"\bCNO\b",
    r"\bnurs(?:e|ing)\b",
    r"\bmidwi(?:fe|very)\b",
    r"\bcharge\s+nurse\b",
    r"\bstaff\s+nurse\b",
    r"\btravel\s+nurse\b",
    r"\bmed[\s\-]?surg\b",
    r"\bICU\s+nurse\b",
    r"\bNICU\b",
    r"\bPICU\b",
    r"\bPACU\b",
    r"\bclinical\s+nurse\b",
    r"\bnurse\s+(?:manager|educator|navigator)\b",
]

TITLE_PATTERN = re.compile("|".join(TITLE_KEYWORDS), re.IGNORECASE)

DEPARTMENT_KEYWORDS = re.compile(
    r"\b(?:nursing|clinical|patient\s+care|medical|health\s*care)\b",
    re.IGNORECASE,
)

# Salary parsing from description text
SALARY_RANGE_PATTERN = re.compile(
    r"\$([\d,]+(?:\.\d{2})?)\s*[-\u2013/]+(?: ?to ?)?\s*\$([\d,]+(?:\.\d{2})?)"
)
HOURLY_PATTERN = re.compile(r"/\s*(?:hr|hour)", re.IGNORECASE)

# Rate limiting (requests per second per ATS)
RATE_LIMITS = {
    "greenhouse": 5,
    "lever": 5,
    "ashby": 3,
    "workday": 3,
    "workable": 3,
    "bamboohr": 2,
}

# Enrichment settings
MAX_WORKERS_PER_ATS = 3
MAX_ENRICH_FAILURES = 5
CONSECUTIVE_FAIL_BACKOFF = 3
CONSECUTIVE_FAIL_SKIP = 10

# Freshness
MAX_JOB_AGE_DAYS = 30
UNENRICHED_GRACE_DAYS = 14

# Pagination
JOBS_PER_PAGE = 25

# SEO category pages: (slug, display_name, title_regex, meta_description)
SEO_CATEGORIES = [
    ("rn", "Registered Nurse", r"\bRN\b|\bregistered\s+nurse\b", "Find registered nurse (RN) jobs. Browse {count} open RN positions updated daily."),
    ("lpn", "Licensed Practical Nurse", r"\bLPN\b|\blicensed\s+practical\s+nurse\b", "Browse {count} LPN jobs. Licensed practical nurse positions updated daily."),
    ("lvn", "Licensed Vocational Nurse", r"\bLVN\b|\blicensed\s+vocational\s+nurse\b", "Browse {count} LVN jobs. Licensed vocational nurse positions updated daily."),
    ("cna", "Certified Nursing Assistant", r"\bCNA\b|\bcertified\s+nurs(?:e|ing)\s+assistant\b", "Browse {count} CNA jobs. Certified nursing assistant positions updated daily."),
    ("nurse-practitioner", "Nurse Practitioner", r"\bNP\b|\bnurse\s+practitioner\b|\bAPRN\b", "Browse {count} nurse practitioner (NP/APRN) jobs updated daily."),
    ("travel-nurse", "Travel Nurse", r"\btravel\s+nurs(?:e|ing)\b", "Browse {count} travel nurse jobs. Travel nursing positions across all states."),
    ("icu-nurse", "ICU Nurse", r"\bICU\s+nurs(?:e|ing)\b|\bintensive\s+care\b", "Browse {count} ICU nurse jobs. Intensive care nursing positions updated daily."),
    ("nicu-nurse", "NICU Nurse", r"\bNICU\b", "Browse {count} NICU nurse jobs. Neonatal ICU nursing positions updated daily."),
    ("pacu-nurse", "PACU Nurse", r"\bPACU\b", "Browse {count} PACU nurse jobs. Post-anesthesia care nursing positions."),
    ("med-surg", "Med-Surg Nurse", r"\bmed[\s\-]?surg\b", "Browse {count} med-surg nurse jobs. Medical-surgical nursing positions updated daily."),
    ("charge-nurse", "Charge Nurse", r"\bcharge\s+nurse\b", "Browse {count} charge nurse jobs updated daily."),
    ("clinical-nurse", "Clinical Nurse", r"\bclinical\s+nurse\b", "Browse {count} clinical nurse jobs. Clinical nursing positions updated daily."),
    ("nurse-manager", "Nurse Manager", r"\bnurse\s+manager\b|\bnursing\s+manager\b|\bmanager.*nurs\b", "Browse {count} nurse manager jobs. Nursing management positions updated daily."),
    ("nurse-educator", "Nurse Educator", r"\bnurse\s+educator\b|\bnursing\s+educat\b", "Browse {count} nurse educator jobs. Nursing education positions updated daily."),
    ("home-health-nurse", "Home Health Nurse", r"\bhome\s+health\b.*nurs|\bnurs.*\bhome\s+health\b", "Browse {count} home health nurse jobs. Home care nursing positions updated daily."),
    ("crna", "Nurse Anesthetist", r"\bCRNA\b|\bnurse\s+anesthetist\b", "Browse {count} CRNA jobs. Certified registered nurse anesthetist positions."),
    ("oncology-nurse", "Oncology Nurse", r"\boncology\b.*nurs|\bnurs.*\boncology\b", "Browse {count} oncology nurse jobs. Cancer care nursing positions updated daily."),
    ("er-nurse", "ER Nurse", r"\bER\s+nurs|\bemergency\b.*nurs|\bnurs.*\bemergency\b", "Browse {count} ER nurse jobs. Emergency room nursing positions updated daily."),
    ("pediatric-nurse", "Pediatric Nurse", r"\bpediatric\b.*nurs|\bnurs.*\bpediatric\b|\bPICU\b", "Browse {count} pediatric nurse jobs updated daily."),
    ("psychiatric-nurse", "Psychiatric Nurse", r"\bpsych\b.*nurs|\bnurs.*\bpsych\b|\bmental\s+health\b.*nurs", "Browse {count} psychiatric nurse jobs. Mental health nursing positions."),
    ("midwife", "Midwife", r"\bmidwi(?:fe|very|ves)\b", "Browse {count} midwife jobs. Certified nurse-midwife positions updated daily."),
    ("nursing-with-salary", "Nursing Jobs with Salary", None, "Browse {count} nursing jobs with published salary ranges. Know your pay upfront."),
    ("remote-nurse", "Remote Nursing", r"\bremote\b|\btelehealth\b|\btelemedicine\b", "Browse {count} remote nursing jobs. Telehealth and work-from-home nursing positions."),
]

# State full names for SEO pages
STATE_NAMES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
}


# ---------------------------------------------------------------------------
# Company name normalization
# ---------------------------------------------------------------------------

_COMPANY_NAME_MAP: dict[str, str] = {
    "davita": "DaVita",
    "ccf": "Cleveland Clinic",
    "cvshealth": "CVS Health",
    "bhs": "Baptist Health System",
    "jeffersonhealth": "Jefferson Health",
    "otterbein": "Otterbein",
    "carilionclinic": "Carilion Clinic",
    "bmc": "Boston Medical Center",
    "usc": "USC",
    "extendicare": "Extendicare",
    "medelitellc": "Med Elite LLC",
    "lifestance": "LifeStance Health",
    "ghc": "Group Health Cooperative",
    "ensign": "Ensign Group",
    "luminishealth": "Luminis Health",
    "humana": "Humana",
    "elevancehealth": "Elevance Health",
    "onemedical": "One Medical",
    "nationwidechildrens": "Nationwide Children's",
    "spectrumhealth": "Spectrum Health",
    "freseniusmedicalcare": "Fresenius Medical Care",
    "ennoblecare": "Ennoble Care",
    "aah": "Advocate Aurora Health",
    "avera": "Avera",
    "allina": "Allina Health",
    "wvumedicine": "WVU Medicine",
    "mercy": "Mercy",
    "sanford": "Sanford Health",
    "abbluecross": "Arkansas Blue Cross",
    "accelschools": "Accel Schools",
    "adventisthealthcare": "Adventist Healthcare",
    "agilonhealth": "Agilon Health",
    "airsculpt": "AirSculpt",
    "bravehealth": "Brave Health",
    "rivhs": "Riverside Health System",
    "sasllc": "SAS LLC",
}

# Suffixes to split on when the slug is all-lowercase with no obvious word
# boundaries.  Ordered longest-first so "medical" matches before "care", etc.
_SLUG_SUFFIXES = [
    "healthcare",
    "medical",
    "hospital",
    "health",
    "clinic",
    "group",
    "care",
    "llc",
    "inc",
]

_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_SUFFIX_SPLIT_RE = re.compile(
    r"(" + "|".join(_SLUG_SUFFIXES) + r")$", re.IGNORECASE
)


def normalize_company_name(slug: str) -> str:
    """Convert a company slug to a human-readable display name.

    Checks a hardcoded lookup table first, then applies heuristics:
    * Insert spaces at camelCase boundaries.
    * For all-lowercase slugs, split before known suffixes like
      "health", "medical", "clinic", etc.
    * Title-case the final result.
    """
    if not slug:
        return slug

    key = slug.lower().strip()
    if key in _COMPANY_NAME_MAP:
        return _COMPANY_NAME_MAP[key]

    name = slug

    # If there are camelCase transitions, split on them.
    if name != name.lower() and name != name.upper():
        name = _CAMEL_SPLIT_RE.sub(" ", name)
    else:
        # All lowercase (or all caps) — try suffix splitting.
        match = _SUFFIX_SPLIT_RE.search(name)
        if match and match.start() > 0:
            name = name[: match.start()] + " " + name[match.start() :]

    return name.title()
