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

# Healthcare keyword patterns (case-insensitive, word-boundary)
# Nursing
NURSING_TITLE_KEYWORDS = [
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

# Allied health professionals
ALLIED_HEALTH_TITLE_KEYWORDS = [
    # Physical Therapy
    r"\bPT\b(?=.*(?:therap|rehab|physical|clinic|hospital|health|outpatient|inpatient))",
    r"\bDPT\b",
    r"\bPTA\b",
    r"\bphysical\s+therap(?:ist|y)\b",
    # Occupational Therapy
    r"\bOT\b(?=.*(?:therap|rehab|occupational|clinic|hospital|health))",
    r"\bOTR\b",
    r"\bCOTA\b",
    r"\boccupational\s+therap(?:ist|y)\b",
    # Speech-Language Pathology
    r"\bSLP\b",
    r"\bCCC[\-\s]?SLP\b",
    r"\bspeech[\s\-]?language\s+patholog(?:ist|y)\b",
    r"\bspeech\s+therap(?:ist|y)\b",
    # Respiratory Therapy
    r"\bRRT\b",
    r"\bCRT\b",
    r"\brespiratory\s+therap(?:ist|y)\b",
    # Radiology / Imaging
    r"\brad(?:iologic(?:al)?|iology)\s+tech(?:nolog(?:ist|y))?",
    r"\bRT\s*\(R\)",
    r"\bx[\-\s]?ray\s+tech\b",
    r"\bCT\s+tech(?:nolog(?:ist|y))?\b",
    r"\bMRI\s+tech(?:nolog(?:ist|y))?\b",
    r"\bsonograph(?:er|y)\b",
    r"\bultrasound\s+tech\b",
    r"\bmammograph(?:er|y)\s+tech\b",
    r"\bdiagnostic\s+imaging\b",
    # Medical Laboratory
    r"\bMLT\b",
    r"\bMLS\b",
    r"\bCLS\b",
    r"\bmedical\s+lab(?:oratory)?\s+(?:tech|scientist)\b",
    r"\bclinical\s+lab(?:oratory)?\s+scientist\b",
    r"\blab(?:oratory)?\s+tech(?:nician|nologist)?\b",
    # Pharmacy
    r"\bPharmD\b",
    r"\bRPh\b",
    r"\bpharmac(?:ist|y\s+tech)\b",
    r"\bpharmacy\s+tech(?:nician)?\b",
    # Dietetics / Nutrition
    r"\bRD\b(?=.*(?:diet|nutri|food|clinical|health))",
    r"\bRDN\b",
    r"\bdietit(?:ian|ion)\b",
    r"\bnutritionist\b",
    r"\bclinical\s+nutrition\b",
    # Social Work (clinical/medical)
    r"\bLCSW\b",
    r"\bLMSW\b",
    r"\bmedical\s+social\s+worker\b",
    r"\bclinical\s+social\s+worker\b",
    r"\bhealthcare\s+social\s+worker\b",
    # Paramedic / EMT
    r"\bparamedic\b",
    r"\bEMT\b",
    r"\bemergency\s+medical\s+tech(?:nician)?\b",
    # Surgical Technology
    r"\bsurg(?:ical)?\s+tech(?:nolog(?:ist|y))?\b",
    r"\bCST\b",
    r"\boperating\s+room\s+tech\b",
    # Dental Hygiene
    r"\bdental\s+hygien(?:ist|e)\b",
    r"\bRDH\b",
    # Phlebotomy
    r"\bphlebotom(?:ist|y)\b",
    # Medical Assistant
    r"\bCMA\b",
    r"\bmedical\s+assistant\b",
    r"\bclinical\s+medical\s+assistant\b",
    # Athletic Training
    r"\bathletic\s+train(?:er|ing)\b",
    r"\bATC\b",
]

TITLE_KEYWORDS = NURSING_TITLE_KEYWORDS + ALLIED_HEALTH_TITLE_KEYWORDS

TITLE_PATTERN = re.compile("|".join(TITLE_KEYWORDS), re.IGNORECASE)

DEPARTMENT_KEYWORDS = re.compile(
    r"\b(?:nursing|clinical|patient\s+care|medical|health\s*care"
    r"|therapy|therapies|rehabilitation|rehab|radiology|imaging"
    r"|laboratory|pharmacy|nutrition|dietetics|social\s+work"
    r"|respiratory|surgical\s+services|emergency\s+medical"
    r"|dental|allied\s+health)\b",
    re.IGNORECASE,
)

# Salary parsing from description text
# Matches: "$50,000 - $75,000", "$28.00 to $42.00/hr", "$32/hr - $48/hr"
SALARY_RANGE_PATTERN = re.compile(
    r"\$([\d,]+(?:\.\d{2})?)\s*(?:/\w+\s*)?(?:[-\u2013]+|to)\s*\$([\d,]+(?:\.\d{2})?)"
)
# Matches single salary: "$75,000", "$45.00/hr", "Starting at $50,000"
SALARY_SINGLE_PATTERN = re.compile(
    r"(?:(?:starting|up to|from|base|minimum|at least|approximately|~)\s+)?"
    r"\$([\d,]+(?:\.\d{2})?)"
    r"(?:\s*[-\u2013]\s*\$([\d,]+(?:\.\d{2})?))?",  # optional upper bound
    re.IGNORECASE,
)
# Detects hourly pay — broader than before
HOURLY_PATTERN = re.compile(
    r"(?:/\s*(?:hr|hour)|per\s+hour|hourly|/hr\b|\bhr\b.*rate|\ban\s+hour)",
    re.IGNORECASE,
)
# Detects annual pay
ANNUAL_PATTERN = re.compile(
    r"(?:per\s+year|per\s+annum|annually|annual|/\s*(?:yr|year)|\bsalary\b)",
    re.IGNORECASE,
)

# Sign-on bonus parsing from description text
# Matches: "$5,000 sign-on bonus", "signing bonus of $10,000", "$15k sign on bonus"
BONUS_PATTERN = re.compile(
    r"(?:"
    # Pattern 1: dollar amount followed by bonus phrase
    r"\$([\d,]+(?:\.\d{2})?)\s*(?:k\b)?\s*(?:sign[\-\s]?on|signing|recruitment|retention|welcome|hiring)\s*bonus"
    r"|"
    # Pattern 2: bonus phrase followed by dollar amount
    r"(?:sign[\-\s]?on|signing|recruitment|retention|welcome|hiring)\s*bonus\s*(?:of\s*|up\s+to\s*|:\s*)?\$([\d,]+(?:\.\d{2})?)\s*(?:k\b)?"
    r")",
    re.IGNORECASE,
)

# Rate limiting (requests per second per ATS)
RATE_LIMITS = {
    "greenhouse": 5,
    "lever": 5,
    "ashby": 3,
    "workday": 3,
    "workable": 3,
    "bamboohr": 2,
    "oracle_hcm": 3,
    # "icims": 3,  # Disabled: upstream has no location data
    "neogov": 2,
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

# Minimum jobs required to generate a pSEO page (avoids thin content)
MIN_JOBS_FOR_PAGE = 3

# SEO category pages: (slug, display_name, title_regex, meta_description)
SEO_CATEGORIES = [
    # Core roles
    ("rn", "Registered Nurse", r"\bRN\b|\bregistered\s+nurse\b", "Find registered nurse (RN) jobs. Browse {count} open RN positions updated daily."),
    ("lpn", "Licensed Practical Nurse", r"\bLPN\b|\blicensed\s+practical\s+nurse\b", "Browse {count} LPN jobs. Licensed practical nurse positions updated daily."),
    ("lvn", "Licensed Vocational Nurse", r"\bLVN\b|\blicensed\s+vocational\s+nurse\b", "Browse {count} LVN jobs. Licensed vocational nurse positions updated daily."),
    ("cna", "Certified Nursing Assistant", r"\bCNA\b|\bcertified\s+nurs(?:e|ing)\s+assistant\b|\bnurse\s+aide\b", "Browse {count} CNA jobs. Certified nursing assistant positions updated daily."),
    ("nurse-practitioner", "Nurse Practitioner", r"\bNP\b|\bnurse\s+practitioner\b|\bAPRN\b|\badvanced\s+practice\b", "Browse {count} nurse practitioner (NP/APRN) jobs updated daily."),
    ("case-manager", "Case Manager", r"\bcase\s+manag(?:er|ement)\b", "Browse {count} nurse case manager jobs updated daily."),
    # Specialty
    ("icu-nurse", "ICU Nurse", r"\bICU\b|\bintensive\s+care\b|\bcritical\s+care\b", "Browse {count} ICU nurse jobs. Intensive care nursing positions updated daily."),
    ("er-nurse", "ER Nurse", r"\bER\s+nurs|\bemergency\b.*nurs|\bnurs.*\bemergency\b|\bemergency\s+(?:room|department)\b", "Browse {count} ER nurse jobs. Emergency room nursing positions updated daily."),
    ("or-nurse", "OR Nurse", r"\bOR\s+nurs|\bsurg(?:ical|ery)\b.*nurs|\bnurs.*\bsurg(?:ical|ery)\b|\boperating\s+room\b", "Browse {count} OR and surgical nurse jobs updated daily."),
    ("nicu-nurse", "NICU Nurse", r"\bNICU\b|\bneonatal\b", "Browse {count} NICU nurse jobs. Neonatal ICU nursing positions updated daily."),
    ("pacu-nurse", "PACU Nurse", r"\bPACU\b", "Browse {count} PACU nurse jobs. Post-anesthesia care nursing positions."),
    ("med-surg", "Med-Surg Nurse", r"\bmed[\s\-]?surg\b|\bmedical[\s\-]?surgical\b", "Browse {count} med-surg nurse jobs. Medical-surgical nursing positions updated daily."),
    ("oncology-nurse", "Oncology Nurse", r"\boncology\b.*nurs|\bnurs.*\boncology\b|\bcancer\b.*nurs", "Browse {count} oncology nurse jobs. Cancer care nursing positions updated daily."),
    ("pediatric-nurse", "Pediatric Nurse", r"\bpediatric\b.*nurs|\bnurs.*\bpediatric\b|\bPICU\b", "Browse {count} pediatric nurse jobs updated daily."),
    ("psychiatric-nurse", "Psychiatric Nurse", r"\bpsych\b.*nurs|\bnurs.*\bpsych\b|\bmental\s+health\b|\bbehavioral\s+health\b", "Browse {count} psychiatric nurse jobs. Mental health nursing positions."),
    ("labor-delivery", "Labor & Delivery Nurse", r"\blabor\b.*\bdelivery\b|\bL&D\b|\bOB\b.*nurs|\bobstetric\b", "Browse {count} labor and delivery nurse jobs updated daily."),
    # Settings
    ("home-health", "Home Health Nurse", r"\bhome\s+health\b|\bhome\s+care\b|\bhospice\b", "Browse {count} home health nurse jobs. Home care nursing positions updated daily."),
    ("travel-nurse", "Travel Nurse", r"\btravel\s+nurs(?:e|ing)\b", "Browse {count} travel nurse jobs. Travel nursing positions across all states."),
    ("remote-nurse", "Remote Nursing", r"\bremote\b|\btelehealth\b|\btelemedicine\b|\bvirtual\s+(?:care|nurse|nursing)\b", "Browse {count} remote nursing jobs. Telehealth and work-from-home nursing positions."),
    # Leadership
    ("charge-nurse", "Charge Nurse", r"\bcharge\s+nurse\b", "Browse {count} charge nurse jobs updated daily."),
    ("nurse-manager", "Nurse Manager", r"\bnurse\s+manager\b|\bnursing\s+manager\b|\bdirector.*nurs|\bnurs.*director\b", "Browse {count} nurse manager jobs. Nursing management positions updated daily."),
    ("clinical-nurse", "Clinical Nurse", r"\bclinical\s+nurse\b", "Browse {count} clinical nurse jobs. Clinical nursing positions updated daily."),
    # Advanced practice
    ("crna", "Nurse Anesthetist", r"\bCRNA\b|\bnurse\s+anesthetist\b|\banesthesia\b.*nurs", "Browse {count} CRNA jobs. Certified registered nurse anesthetist positions."),
    ("midwife", "Midwife", r"\bmidwi(?:fe|very|ves)\b", "Browse {count} midwife jobs. Certified nurse-midwife positions updated daily."),
    ("nurse-educator", "Nurse Educator", r"\bnurse\s+educator\b|\bnursing\s+(?:instructor|faculty|professor|educat)\b|\bclinical\s+educator\b", "Browse {count} nurse educator jobs. Nursing education positions updated daily."),
    # Shift / employment type
    ("night-shift", "Night Shift Nurse", r"\bnight\s*shift\b|\bnoc(?:turnal)?\s+shift\b|\bovernight\b|\b3rd\s+shift\b|\bthird\s+shift\b", "Browse {count} night shift nursing jobs updated daily."),
    ("per-diem", "Per Diem Nurse", r"\bper\s*[\-\s]?diem\b|\bPRN\b", "Browse {count} per diem and PRN nursing jobs updated daily."),
    ("part-time-nurse", "Part-Time Nurse", r"\bpart[\s\-]?time\b", "Browse {count} part-time nursing jobs updated daily."),
    # Pay
    ("nursing-with-salary", "Jobs with Salary", None, "Browse {count} healthcare jobs with published salary ranges. Know your pay upfront."),
    # Allied Health — Therapy
    ("physical-therapist", "Physical Therapist", r"\bphysical\s+therap(?:ist|y)\b|\bPT\b(?=.*(?:therap|rehab|physical|clinic|hospital|health))|\bDPT\b|\bPTA\b", "Browse {count} physical therapist jobs. PT and PTA positions updated daily."),
    ("occupational-therapist", "Occupational Therapist", r"\boccupational\s+therap(?:ist|y)\b|\bOTR\b|\bCOTA\b", "Browse {count} occupational therapist jobs. OT and COTA positions updated daily."),
    ("speech-language-pathologist", "Speech-Language Pathologist", r"\bSLP\b|\bspeech[\s\-]?language\s+patholog(?:ist|y)\b|\bspeech\s+therap(?:ist|y)\b|\bCCC[\-\s]?SLP\b", "Browse {count} speech-language pathologist jobs. SLP positions updated daily."),
    ("respiratory-therapist", "Respiratory Therapist", r"\brespiratory\s+therap(?:ist|y)\b|\bRRT\b|\bCRT\b", "Browse {count} respiratory therapist jobs. RT positions updated daily."),
    # Allied Health — Diagnostic / Lab
    ("radiology-technologist", "Radiology Technologist", r"\brad(?:iologic(?:al)?|iology)\s+tech|\bRT\s*\(R\)|\bx[\-\s]?ray\s+tech|\bCT\s+tech|\bMRI\s+tech|\bsonograph|\bultrasound\s+tech|\bmammograph|\bdiagnostic\s+imaging", "Browse {count} radiology and imaging technologist jobs updated daily."),
    ("lab-technician", "Lab Technician", r"\bMLT\b|\bMLS\b|\bCLS\b|\bmedical\s+lab(?:oratory)?\s+(?:tech|scientist)|\bclinical\s+lab(?:oratory)?\s+scientist|\blab(?:oratory)?\s+tech(?:nician|nologist)?", "Browse {count} medical laboratory technician and scientist jobs updated daily."),
    ("phlebotomist", "Phlebotomist", r"\bphlebotom(?:ist|y)\b", "Browse {count} phlebotomist jobs updated daily."),
    # Allied Health — Pharmacy / Nutrition
    ("pharmacist", "Pharmacist", r"\bPharmD\b|\bRPh\b|\bpharmac(?:ist|y\s+tech)|\bpharmacy\s+tech(?:nician)?", "Browse {count} pharmacist and pharmacy technician jobs updated daily."),
    ("dietitian", "Dietitian", r"\bRDN?\b(?=.*(?:diet|nutri|food|clinical|health))|\bdietit(?:ian|ion)\b|\bnutritionist\b|\bclinical\s+nutrition\b", "Browse {count} dietitian and nutritionist jobs updated daily."),
    # Allied Health — Other
    ("medical-assistant", "Medical Assistant", r"\bmedical\s+assistant\b|\bCMA\b|\bclinical\s+medical\s+assistant\b", "Browse {count} medical assistant jobs updated daily."),
    ("surgical-technologist", "Surgical Technologist", r"\bsurg(?:ical)?\s+tech(?:nolog(?:ist|y))?\b|\bCST\b|\boperating\s+room\s+tech\b", "Browse {count} surgical technologist jobs updated daily."),
    ("paramedic", "Paramedic / EMT", r"\bparamedic\b|\bEMT\b|\bemergency\s+medical\s+tech(?:nician)?", "Browse {count} paramedic and EMT jobs updated daily."),
    ("dental-hygienist", "Dental Hygienist", r"\bdental\s+hygien(?:ist|e)\b|\bRDH\b", "Browse {count} dental hygienist jobs updated daily."),
    ("social-worker", "Healthcare Social Worker", r"\bLCSW\b|\bLMSW\b|\bmedical\s+social\s+worker\b|\bclinical\s+social\s+worker\b|\bhealthcare\s+social\s+worker\b", "Browse {count} healthcare social worker jobs updated daily."),
    ("athletic-trainer", "Athletic Trainer", r"\bathletic\s+train(?:er|ing)\b|\bATC\b", "Browse {count} athletic trainer jobs updated daily."),
]

# State abbreviation to URL slug (lowercase full name)
STATE_SLUGS = {abbr: name.lower().replace(" ", "-") for abbr, name in {
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
}.items()}

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
    "ummh": "UMass Memorial Health",
    "veterinaryemergencygroupst": "Veterinary Emergency Group",
    "vumc": "Vanderbilt University Medical Center",
    "talkspacepsychiatry": "Talkspace",
    "wellstar": "Wellstar Health System",
    "valleyhealthlink": "Valley Health",
    "heyrowan": "Rowan",
    "vca": "VCA Animal Hospitals",
    "wustl": "Washington University in St. Louis",
    "vailclinicincdbavailhealth": "Vail Health",
    "sonobello": "Sono Bello",
    "animaltrust": "Animal Trust",
    "thegialliancemanagementllccompany": "GI Alliance",
    "skinlaundry": "Skin Laundry",
    "twochairs": "Two Chairs",
    "upenn": "University of Pennsylvania",
    "ascensionrecovery": "Ascension Recovery",
    "tia": "Tia Health",
    "cabinetpeaks": "Cabinet Peaks Medical Center",
    "cmciks": "CMC",
    "healthvisionteam": "Health Vision Team",
    "mchwc": "MCHWC",
    "utaustin": "UT Austin",
    "lighthousebehavioralhealthsolutions": "Lighthouse Behavioral Health Solutions",
    "communicarehealth": "CommuniCare Health",
    "cookchildrens": "Cook Children's",
    "denverhealth": "Denver Health",
    "massgeneralbrigham": "Mass General Brigham",
    "memorialhermann": "Memorial Hermann",
    "montefiore": "Montefiore Medical Center",
    "ohiohealth": "OhioHealth",
    "prismahealth": "Prisma Health",
    "stormontvail": "Stormont Vail Health",
    "lcmchealth": "LCMC Health",
    "methodisthealth": "Methodist Le Bonheur Healthcare",
    "albanymed": "Albany Medical Center",
    "seattlechildrens": "Seattle Children's",
    "cincinnatichildrens": "Cincinnati Children's",
    "nebraskamedical": "Nebraska Medicine",
    "stanfordhealthcare": "Stanford Health Care",
    "bannerhealth": "Banner Health",
    "christianacare": "ChristianaCare",
    "multicare": "MultiCare Health System",
    "nshs": "Northwell Health",
    "roswellpark": "Roswell Park",
    "gundersenhealth": "Gundersen Health",
    "exactcare": "ExactCare Pharmacy",
    "onedigital": "OneDigital",
    "oneoncology": "OneOncology",
    "primetherapeutics": "Prime Therapeutics",
    "cardinalhealth": "Cardinal Health",
    "bristolmyerssquibb": "Bristol-Myers Squibb",
    "geaerospace": "GE Aerospace",
    "guardianpharmacy": "Guardian Pharmacy",
    "easyservice": "Bon Secours",
    "flcancer": "Florida Cancer Specialists",
    "southshorehealth": "South Shore Health",
    "annieaesthetic": "Annie Aesthetic",
    "cabrillohospice": "Cabrillo Hospice",
    "catholiccharitiesli": "Catholic Charities LI",
    "clinicaromero": "Clinica Romero",
    "doveschoolsoklahoma": "Dove Schools of Oklahoma",
    "fikamidwifery": "Fika Midwifery",
    "fraservalleycataractandlaser": "Fraser Valley Cataract & Laser",
    "givinghhc": "Giving Home Health Care",
    "healthemployersassociationofbc": "Health Employers Association of BC",
    "heritagehealthservices": "Heritage Health Services",
    "paulrobeson": "Paul Robeson",
    "scgreencharter": "SC Green Charter",
    "southeastdermatology": "Southeast Dermatology",
    "southshoreskin": "South Shore Skin",
    "springfertility": "Spring Fertility",
    "thematherevanston": "The Mather Evanston",
    "theoncologyinstitute": "The Oncology Institute",
    "spokanetribe": "Spokane Tribe",
    "primehomedds": "Prime Home DDS",
    "katalystsystemsimpact": "Katalyst Systems Impact",
    "sonderaustralia": "Sonder Australia",
    "ngaiteranginz": "Ngai Terangi NZ",
    "maamwesying": "Maamwesying",
    "gilbertcentre": "Gilbert Centre",
    "charleslea": "Charles Lea",
    "glowacademy": "Glow Academy",
    "evergreenoutdoorcenter": "Evergreen Outdoor Center",
    "caringnetwork": "Caring Network",
    "healthcaringkw": "Health Caring KW",
    "baptistjax": "Baptist Health Jacksonville",
    "ashealthnet": "AS Health Net",
    "altamed": "AltaMed",
    "archildrens": "Arkansas Children's",
    "ameripharma": "AmeriPharma",
    "adaptadg": "Adapt ADG",
    "akidolabs": "Akido Labs",
    "akumincorp": "Akumin Corp",
    "agiliti": "Agiliti",
    "allcarehha": "AllCare Home Health",
    "alphahousecalgary": "Alpha House Calgary",
    "anewwell": "Anew Well",
    "aoncology": "AOncology",
    "arcetyp": "Arcetyp",
    "aspirehealthalliance": "Aspire Health Alliance",
    "clearskyhealthcare": "Clear Sky Healthcare",
    "5starcares": "5 Star Cares",
    "4seasonstransport": "4 Seasons Transport",
    "acecaremgmt": "ACE Care Management",
    "alivation": "Alivation",
    "allcareers": "All Careers",
    "agibank": "Agibank",
    "analogdevices": "Analog Devices",
    "geisinger": "Geisinger",
    "pulse": "Pulse",
    "bayada": "BAYADA",
    # Oracle HCM site names
    "mayo": "Mayo Clinic",
    "chs": "Community Health Systems",
    "osu medical center": "Ohio State University Medical Center",
}

# Suffixes to split on when the slug is all-lowercase with no obvious word
# boundaries.  Ordered longest-first so "medical" matches before "care", etc.
_SLUG_SUFFIXES = [
    "healthcare",
    "solutions",
    "services",
    "midwifery",
    "institute",
    "aesthetic",
    "fertility",
    "hospice",
    "medical",
    "hospital",
    "academy",
    "network",
    "outdoor",
    "charter",
    "centre",
    "school",
    "health",
    "clinic",
    "tribe",
    "group",
    "laser",
    "care",
    "skin",
    "home",
    "llc",
    "inc",
    "nz",
    "bc",
    "li",
]

_CAMEL_SPLIT_RE = re.compile(r"(?<=[a-z])(?=[A-Z])")
_SUFFIX_SPLIT_RE = re.compile(
    r"(" + "|".join(_SLUG_SUFFIXES) + r")$", re.IGNORECASE
)

# Patterns for cleaning Workday legal entity names
_LEADING_NUMBERS_RE = re.compile(r"^\d+\s+")
_CORPORATE_SUFFIX_RE = re.compile(
    r",?\s*\b(Inc\.?|LLC\.?|L\.?L\.?C\.?|Corporation|Incorporated|Corp\.?|Co\.?|Ltd\.?|Limited|Association|P\.?C\.?)\s*\.?\s*$",
    re.IGNORECASE,
)
_POSSESSIVE_FIX_RE = re.compile(r"'S\b")


def _clean_legal_name(name: str) -> str:
    """Clean a legal entity name from Workday API.
    '9000 Bon Secours Mercy Health Inc' -> 'Bon Secours Mercy Health'
    '223 Aurora Medical Group, Inc.' -> 'Aurora Medical Group'
    """
    # Strip leading numeric codes
    name = _LEADING_NUMBERS_RE.sub("", name)
    # Strip corporate suffixes
    name = _CORPORATE_SUFFIX_RE.sub("", name).strip().rstrip(",").strip()
    # Fix possessives: 'S -> 's
    name = _POSSESSIVE_FIX_RE.sub("'s", name)
    return name


def normalize_company_name(slug: str) -> str:
    """Convert a company slug or legal name to a human-readable display name."""
    if not slug:
        return slug

    key = slug.lower().strip()
    if key in _COMPANY_NAME_MAP:
        return _COMPANY_NAME_MAP[key]

    name = slug.strip()

    # If it already has spaces, it's likely from an API (e.g. Workday hiringOrganization)
    if " " in name:
        cleaned = _clean_legal_name(name)
        if cleaned:
            return cleaned

    # camelCase splitting
    if name != name.lower() and name != name.upper():
        name = _CAMEL_SPLIT_RE.sub(" ", name)
        return name.strip()

    # All lowercase — try to split on known words anywhere in the string
    lower = name.lower()
    # Build list of all known words to split on (suffixes work as infixes too)
    split_words = sorted(_SLUG_SUFFIXES, key=len, reverse=True)
    # Add common prefixes
    split_words += [
        "community", "children", "baptist", "memorial", "regional",
        "alpine", "american", "national", "central", "western",
        "eastern", "northern", "southern", "pacific", "atlantic",
        "physicians", "associates", "partners", "alliance", "center",
        "county", "valley", "river", "lake", "cross", "star",
        "premier", "primary", "urgent", "rehab", "senior",
        "pediatric", "dental", "pharma", "transport", "staffing",
    ]

    result = lower
    for word in split_words:
        idx = result.find(word)
        if idx > 0 and result[idx - 1] != " ":
            result = result[:idx] + " " + result[idx:]

    if result != lower:
        return result.title()

    return name.title()
