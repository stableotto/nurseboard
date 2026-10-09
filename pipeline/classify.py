"""Structured healthcare facets extracted from a job's title and description.

These are the fields a personal AI agent needs to answer a real question like
"night shift ICU RN near Denver, $55+/hr, compact license, 1 year experience":
role, specialty, care setting, employment type, schedule, requirements and
normalized pay. Everything here is rule-based and deterministic, so a job
classifies the same way on every run and the output can be unit tested.

Role comes from the title only (descriptions mention many roles in passing).
Specialty also reads departments. Requirements and employment type read the
description, where ATS boilerplate usually states them.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Roles: (slug, label, SOC 2018 code, full-name regex, abbreviation regex).
#
# Matching runs in three passes over the title so ambiguous short tokens can't
# win over an explicit job name: (1) full role names, case-insensitive, in list
# order — specific before generic ("Physical Therapist Assistant" before
# "Physical Therapist"); (2) credential abbreviations, case-sensitive, so "PT"
# (part-time), "MA" (Massachusetts) and "MD" (Maryland) never decide a role;
# (3) a bare "nurse"/"nursing" falls back to RN ("Nurse Manager", "Director of
# Nursing").
# ---------------------------------------------------------------------------

ROLES: list[tuple[str, str, str | None, str | None, str | None]] = [
    ("crna", "Certified Registered Nurse Anesthetist", "29-1151",
     r"\bnurse\s+anesthetist", r"\bCRNA\b"),
    ("cnm", "Certified Nurse Midwife", "29-1161",
     r"\bnurse[\s\-]+midwi|\bmidwi(?:fe|ves|fery)\b", r"\bCNM\b"),
    ("nurse_practitioner", "Nurse Practitioner", "29-1171",
     r"\bnurse\s+practitioner|\badvanced\s+practice\s+(?:registered\s+)?nurse",
     r"\b(?:NP|ANP|ARNP|APRN|APN|FNP|PMHNP|AGNP|AGACNP|AGPCNP|ACNP|PNP|WHNP|NNP)(?:-(?:BC|C|PC|AC))?\b"),
    ("clinical_nurse_specialist", "Clinical Nurse Specialist", "29-1141",
     r"\bclinical\s+nurse\s+specialist", r"\bCNS\b"),
    ("physician_assistant", "Physician Assistant", "29-1071",
     r"\bphysician\s+(?:assistant|associate)", r"\bPA-C\b"),
    ("lpn", "Licensed Practical / Vocational Nurse", "29-2061",
     r"\blicensed\s+(?:practical|vocational)\s+nurse", r"\bLPN\b|\bLVN\b"),
    ("rn", "Registered Nurse", "29-1141",
     r"\bregistered\s+nurs", r"\bRN\b|\bR\.N\.|\bBSN\b|\bCNO\b|\bDON\b|\bADON\b"),
    ("physician", "Physician", "29-1229",
     r"\bphysician\b(?!\s+(?:office|practice|group|services|network|partners|clinic|liaison|relations|recruit|enterprise|billing|credential))"
     r"|\bhospitalist\b|\bpsychiatrist\b|\banesthesiologist\b|\bcardiologist\b|\bradiologist\b|\bintensivist\b"
     r"|\bneurologist\b|\boncologist\b|\bpediatrician\b|\bsurgeon\b",
     None),
    ("pharmacy_technician", "Pharmacy Technician", "29-2052",
     r"\bpharmacy\s+tech|\bpharm\s*tech", r"\bCPhT\b"),
    ("cna", "Certified Nursing Assistant", "31-1131",
     r"\bnurs(?:e|ing)\s+(?:aide|assistant)|\bcertified\s+nurs(?:e|ing)\s+(?:aide|assistant)",
     r"\bC?NA\b|\bSTNA\b|\bGNA\b|\bLNA\b|\bCNA\b"),
    ("patient_care_tech", "Patient Care Technician", "31-1131",
     r"\bpatient\s+care\s+(?:tech|assistant|associate|partner)|\bnurse\s+tech(?:nician)?\b|\bclinical\s+(?:tech|technician|care\s+assistant)\b",
     r"\bPCT\b|\bPCA\b"),
    ("medical_assistant", "Medical Assistant", "31-9092",
     r"\bmedical\s+assistant", r"\bCMA\b|\bRMA\b"),
    ("home_health_aide", "Home Health / Personal Care Aide", "31-1121",
     r"\bhome\s+health\s+aide|\bcaregiver\b|\bpersonal\s+care\s+(?:aide|attendant)|\bdirect\s+care\s+(?:worker|staff|professional)",
     r"\bHHA\b"),
    ("physical_therapist_assistant", "Physical Therapist Assistant", "31-2021",
     r"\bphysical\s+therap(?:ist|y)\s+assistant", r"\bPTA\b"),
    ("physical_therapist", "Physical Therapist", "29-1123",
     r"\bphysical\s+therap(?:ist|y)", r"\bDPT\b"),
    ("occupational_therapy_assistant", "Occupational Therapy Assistant", "31-2011",
     r"\boccupational\s+therap(?:ist|y)\s+assistant", r"\bCOTA\b"),
    ("occupational_therapist", "Occupational Therapist", "29-1122",
     r"\boccupational\s+therap(?:ist|y)|\btherapist,?\s+occupational", r"\bOTR(?:/L)?\b|\bOT\b"),
    ("speech_language_pathologist", "Speech-Language Pathologist", "29-1127",
     r"\bspeech[\s\-]+(?:language[\s\-]+)?(?:path|therap)", r"\bSLP\b|\bCCC[\-\s]?SLP\b"),
    ("respiratory_therapist", "Respiratory Therapist", "29-1126",
     r"\brespiratory\s+(?:therap|care\s+practitioner)", r"\bRRT\b|\bCRT\b"),
    ("radiation_therapist", "Radiation Therapist", "29-1124", r"\bradiation\s+therap", None),
    ("dentist", "Dentist", "29-1021", r"\bdentist\b", r"\bDDS\b|\bDMD\b"),
    ("pharmacist", "Pharmacist", "29-1051", r"\bpharmacist", r"\bPharmD\b|\bRPh\b"),
    ("sonographer", "Diagnostic Medical Sonographer", "29-2032",
     r"\bsonograph|\bultrasound|\bvascular\s+(?:tech|technolog)|\becho(?:cardiograph)?\w*\s+tech", r"\bRDMS\b|\bRDCS\b|\bRVT\b"),
    ("imaging_technologist", "Radiologic / Imaging Technologist", "29-2034",
     r"\brad(?:iologic(?:al)?|iology)?\s+tech|\bx[\-\s]?ray|\bmammograph|\bnuclear\s+medicine|\bdiagnostic\s+imaging|\bimaging\s+tech|\bradiograph|\bmulti[\s\-]?modality|\bx\s*-\s*ray|\bCT\s+(?:tech|scan)|\bMRI\b",
     r"\bCT\b|\bMRI\b|\bRT\s*\(R\)"),
    ("lab_technologist", "Medical Laboratory Scientist / Technician", "29-2011",
     r"\bmedical\s+lab(?:oratory)?\s+(?:tech|scientist)|\bclinical\s+lab(?:oratory)?\s+scientist|\blab(?:oratory)?\s+(?:tech|scientist|assistant)|\bhistotech|\bcytotech",
     r"\bMLT\b|\bMLS\b|\bCLS\b"),
    ("phlebotomist", "Phlebotomist", "31-9097", r"\bphlebotom", None),
    ("surgical_technologist", "Surgical Technologist", "29-2055",
     r"\bsurg(?:ical)?\s+tech|\boperating\s+room\s+tech|\bscrub\s+tech", r"\bCST\b"),
    ("paramedic", "Paramedic / EMT", "29-2043",
     r"\bparamedic|\bemergency\s+medical\s+tech", r"\bEMT\b"),
    ("dietitian", "Dietitian", "29-1031",
     r"\bdietit(?:ian|ion)|\bnutritionist|\bclinical\s+nutrition", r"\bRDN?\b"),
    ("social_worker", "Social Worker", "21-1022",
     r"\bsocial\s+work", r"\bLCSW\b|\bLMSW\b|\bMSW\b"),
    ("dental_hygienist", "Dental Hygienist", "29-1292", r"\bdental\s+hygien", r"\bRDH\b"),
    ("dental_assistant", "Dental Assistant", "31-9091", r"\bdental\s+assist", None),
    ("athletic_trainer", "Athletic Trainer", "29-9091", r"\bathletic\s+train", r"\bATC\b"),
    ("behavioral_health_tech", "Behavioral / Mental Health Technician", "29-2053",
     r"\b(?:behavioral|mental)\s+health\s+(?:tech|associate|specialist|worker|counselor)|\bpsych(?:iatric)?\s+tech",
     None),
]

_ROLE_WORD_RES = [(slug, re.compile(w, re.IGNORECASE)) for slug, _, _, w, _ in ROLES if w]
_ROLE_ABBR_RES = [(slug, re.compile(a)) for slug, _, _, _, a in ROLES if a]
_GENERIC_NURSE_RE = re.compile(r"\bnurs(?:e|es|ing)\b", re.IGNORECASE)
ROLE_LABELS = {slug: label for slug, label, _, _, _ in ROLES}
ROLE_SOC = {slug: soc for slug, _, soc, _, _ in ROLES}
ROLE_LABELS["other"] = "Other healthcare role"


def classify_role(title: str | None) -> str:
    t = title or ""
    for passes in (_ROLE_WORD_RES, _ROLE_ABBR_RES):
        for slug, rx in passes:
            if rx.search(t):
                return slug
    if _GENERIC_NURSE_RE.search(t):
        return "rn"
    return "other"


# ---------------------------------------------------------------------------
# Level
# ---------------------------------------------------------------------------

_NEW_GRAD_RE = re.compile(
    r"\bnew[\s\-]+grad|\bgraduate\s+nurse|\bGN\b|\bresidency\b|\bnurse\s+resident|\bfellowship\b|\btransition\s+to\s+practice|\bentry[\s\-]+level",
    re.IGNORECASE,
)
_LEADERSHIP_RE = re.compile(
    r"\bdirector\b|\bmanager\b|\bsupervisor\b|\bchief\b|\bCNO\b|\bDON\b|\bADON\b|\badministrator\b|\bvice\s+president\b|\bVP\b|\bhead\s+nurse|\bcoordinator\s+of\b",
    re.IGNORECASE,
)
_CASE_MANAGER_RE = re.compile(r"\bcase\s+manag|\bcare\s+manag", re.IGNORECASE)
_CHARGE_RE = re.compile(r"\bcharge\b|\blead\b|\bteam\s+lead", re.IGNORECASE)
_EDUCATOR_RE = re.compile(r"\beducat(?:or|ion)\b|\binstructor\b|\bfaculty\b|\bprofessor\b|\bpreceptor\b", re.IGNORECASE)


def classify_level(title: str | None) -> str:
    t = title or ""
    if _NEW_GRAD_RE.search(t):
        return "new_grad"
    if _LEADERSHIP_RE.search(t) and not _CASE_MANAGER_RE.search(t):
        return "leadership"
    if _EDUCATOR_RE.search(t):
        return "educator"
    if _CHARGE_RE.search(t):
        return "charge"
    return "staff"


# ---------------------------------------------------------------------------
# Specialties (multi-valued). Matched against title + departments.
# ---------------------------------------------------------------------------

SPECIALTIES: list[tuple[str, str, str]] = [
    ("icu", "ICU / Critical Care",
     r"\bICU\b|\bintensive\s+care|\bcritical\s+care|\bMICU\b|\bSICU\b|\bCVICU\b|\bCCU\b|\bNeuro\s*ICU|\bTICU\b|\bCVOR\b"),
    ("nicu", "NICU", r"\bNICU\b|\bneonatal|\bspecial\s+care\s+nursery"),
    ("picu", "PICU", r"\bPICU\b|\bpediatric\s+intensive|\bpediatric\s+critical"),
    ("emergency", "Emergency / ER",
     r"(?-i:\bER\b|\bED\b|\bEMS\b)|\bemergency\b|\btrauma\b"),
    ("labor_delivery", "Labor & Delivery",
     r"\bL\s*&\s*D\b|\bL\s*and\s*D\b|\blabor\s+(?:and|&)\s+delivery|\bbirth(?:ing)?\b|\bobstetric|(?-i:\bOB\b)|\bperinatal|\bantepartum|\bLDRP\b"),
    ("mother_baby", "Mother-Baby / Postpartum",
     r"\bpostpartum|\bmother[\s/\-]*baby|\bnewborn|\bwomen'?s\s+(?:and\s+)?(?:infant|health|services)|\bmaternal|\bnursery\b"),
    ("operating_room", "Operating Room / Perioperative",
     r"(?-i:\bOR\b)|\boperating\s+room|\bperi[\s\-]?op|\bsurgical\s+services|\bsurgery\s+cent|\bcirculat|\bCVOR\b"),
    ("pacu_preop", "PACU / Pre-Op",
     r"\bPACU\b|\bpost[\s\-]?anesthesia|\bpre[\s\-]?op\b|\bpre[\s\-]?operative|\bpre[\s\-]?procedure|\brecovery\s+room|\bphase\s+(?:I|II|1|2)\b"),
    ("cath_lab", "Cath Lab / Interventional",
     r"\bcath(?:eterization)?\s+lab|\binterventional|\belectrophysiology|(?-i:\bEP\s+lab|\bIR\b)"),
    ("med_surg", "Med-Surg",
     r"\bmed(?:ical)?[\s/\-]*surg|\bM/S\b|\bmedical[\s/\-]+surgical|\bmedical\s+unit|\bsurgical\s+unit"),
    ("telemetry", "Telemetry / Step-Down / PCU",
     r"\btele\b|\btelemetry|\bstep[\s\-]?down|\bprogressive\s+care|\bPCU\b|\bIMCU?\b|\bintermediate\s+care"),
    ("oncology", "Oncology / Hematology",
     r"\boncolog|\bcancer\b|\bhematolog|\bBMT\b|\bbone\s+marrow|\bradiation\s+therap|\bchemo"),
    ("infusion", "Infusion", r"\binfusion"),
    ("psych", "Psych / Behavioral Health",
     r"\bpsych|\bbehavioral|\bmental\s+health|\bsubstance|\baddiction|\bdetox"),
    ("pediatrics", "Pediatrics", r"\bpediatric|\bpeds\b|\bpaediatric|\bchildren'?s\b"),
    ("dialysis", "Dialysis / Nephrology",
     r"\bdialysis|\bnephrolog|\bhemodialysis|\brenal\b|\bkidney"),
    ("home_health", "Home Health",
     r"\bhome\s+health|\bhome\s+care|\bvisiting\s+nurse|\bin[\s\-]home|\bhome\s+infusion"),
    ("hospice", "Hospice / Palliative", r"\bhospice|\bpalliative|\bend[\s\-]of[\s\-]life"),
    ("rehab", "Rehabilitation",
     r"\brehab(?:ilitation)?\b|\bIRF\b|\bacute\s+rehab|\bphysical\s+medicine"),
    ("long_term_care", "Long-Term Care / Skilled Nursing",
     r"\blong[\s\-]term\s+care|\bLTC\b|\bskilled\s+nursing|\bSNF\b|\bnursing\s+home|\bpost[\s\-]acute|\bsub[\s\-]?acute|\bassisted\s+living|\bmemory\s+care|\bsenior\s+living|\bgeriatric"),
    ("ambulatory", "Ambulatory / Clinic",
     r"\bclinic\b|\bambulatory|\boutpatient|\bprimary\s+care|\bfamily\s+medicine|\binternal\s+medicine|\bphysician\s+(?:office|practice)|\bmedical\s+(?:office|group)"),
    ("urgent_care", "Urgent Care", r"\burgent\s+care|\bwalk[\s\-]in"),
    ("cardiology", "Cardiology / Cardiac",
     r"\bcardi(?:ac|olog\w*|ovascular|o)\b|\bheart\b|\bCVU\b|\bCVICU\b"),
    ("neuro", "Neurology / Stroke", r"\bneuro|\bstroke\b"),
    ("ortho", "Orthopedics", r"\borthop|\bortho\b|\bspine\b|\bjoint\s+replacement"),
    ("gi_endoscopy", "GI / Endoscopy", r"\bendoscop|(?-i:\bGI\b)|\bgastro"),
    ("wound_care", "Wound Care", r"\bwound|\bostomy|(?-i:\bWOCN?\b)"),
    ("case_management", "Case Management / Utilization Review",
     r"\bcase\s+manag|\bcare\s+manag|\butilization\s+(?:review|management)|\bcare\s+coordinat|\bdischarge\s+plan|\btransitions?\s+of\s+care"),
    ("infection_prevention", "Infection Prevention", r"\binfection\s+(?:prevention|control)"),
    ("occupational_health", "Occupational / Employee Health", r"\boccupational\s+health|\bemployee\s+health"),
    ("school", "School Nursing", r"\bschool\b|\bstudent\s+health"),
    ("correctional", "Correctional", r"\bcorrection|\bjail\b|\bprison\b|\bdetention\b|\binmate"),
    ("float_pool", "Float Pool", r"\bfloat\b|\bresource\s+(?:pool|team)|\bstaffing\s+pool"),
    ("telehealth", "Telehealth / Remote",
     r"\btele(?:health|medicine|phonic|triage)|\bvirtual\b|\bremote\b|\bwork\s+from\s+home"),
    ("informatics", "Informatics / Quality",
     r"\binformatic|\bquality\b|\bpatient\s+safety|\bclinical\s+document|\bCDI\b|\bEHR\b|\bEpic\b"),
    ("transplant", "Transplant", r"\btransplant"),
    ("burn", "Burn", r"\bburn\s+(?:unit|center|ICU)"),
]

_SPECIALTY_RES = [(slug, re.compile(rx, re.IGNORECASE)) for slug, _, rx in SPECIALTIES]
SPECIALTY_LABELS = {slug: label for slug, label, _ in SPECIALTIES}

# Short unit abbreviations (OR, ER, ED, OB, GI, IR) are matched case-sensitively
# so the words "or"/"ed" in a title never tag a specialty.


def classify_specialties(title: str | None, departments: list[str] | None = None) -> list[str]:
    depts = [d for d in (departments or []) if isinstance(d, str)]
    text = " ".join([title or ""] + depts)
    out = []
    for slug, rx in _SPECIALTY_RES:
        if rx.search(text):
            out.append(slug)
    return out


# ---------------------------------------------------------------------------
# Care setting (single primary value)
# ---------------------------------------------------------------------------

SETTING_LABELS = {
    "telehealth": "Telehealth / Remote",
    "home_health": "Home Health",
    "hospice": "Hospice",
    "dialysis_center": "Dialysis Center",
    "skilled_nursing": "Skilled Nursing / Long-Term Care",
    "behavioral_health": "Behavioral Health Facility",
    "school": "School",
    "correctional": "Correctional Facility",
    "ambulatory_surgery": "Ambulatory Surgery Center",
    "urgent_care": "Urgent Care",
    "clinic": "Clinic / Outpatient",
    "hospital": "Hospital",
    "ems": "EMS / Ambulance",
}

_SETTING_RULES: list[tuple[str, re.Pattern]] = [
    ("home_health", re.compile(r"\bhome\s+health|\bhome\s+care|\bvisiting\s+nurse|\bin[\s\-]home\b", re.I)),
    ("hospice", re.compile(r"\bhospice", re.I)),
    ("dialysis_center", re.compile(r"\bdialysis|\bDaVita\b|\bFresenius\b|\bAmerican\s+Renal|\bU\.?S\.?\s+Renal", re.I)),
    ("skilled_nursing", re.compile(
        r"\bskilled\s+nursing|\bnursing\s+(?:home|center|facility)|\bSNF\b|\blong[\s\-]term\s+care|\bLTC\b|\bpost[\s\-]acute"
        r"|\b(?:health|healthcare|nursing)\s+(?:and|&)\s+rehab|\brehab(?:ilitation)?\s+(?:and|&)\s+(?:nursing|healthcare)"
        r"|\bsenior\s+living|\bassisted\s+living|\bmemory\s+care|\bretirement\s+(?:community|home)|\bliving\s+center|\bcare\s+center\b",
        re.I)),
    ("behavioral_health", re.compile(r"\bbehavioral\s+health\s+(?:hospital|center|facility)|\bpsychiatric\s+(?:hospital|center|facility)|\bbehav\s+health\s+hosp", re.I)),
    ("school", re.compile(r"\bschool\b|\bschool\s+district|\bISD\b|\bunified\b", re.I)),
    ("correctional", re.compile(r"\bcorrection|\bjail\b|\bprison\b|\bdetention\b|\bsheriff", re.I)),
    ("ambulatory_surgery", re.compile(r"\bsurgery\s+center|\bsurgical\s+center|\bambulatory\s+surg|\bASC\b|\bendoscopy\s+center", re.I)),
    ("urgent_care", re.compile(r"\burgent\s+care", re.I)),
    ("ems", re.compile(r"\bambulance|\bEMS\b|\bground\s+transport|\bair\s+medical|\bfire\s+(?:department|rescue)", re.I)),
    ("clinic", re.compile(
        r"\bclinic\b|\boutpatient|\bambulatory|\bprimary\s+care|\bmedical\s+group|\bphysicians?\s+(?:group|practice|office)"
        r"|\bfamily\s+(?:medicine|practice)|\bpractice\b|\bmedical\s+office|\bcommunity\s+health\s+center|\bFQHC\b",
        re.I)),
    ("hospital", re.compile(
        r"\bhospital|\bmedical\s+center|\bmed\s+ctr\b|\bhealth\s+system|\binpatient|\bacute\s+care|\bregional\s+medical"
        r"|\bhealthcare\s+system|\bmedical\s+campus|\bmain\s+campus|\btrauma\s+center|\bunit\b",
        re.I)),
]

_SPECIALTY_TO_SETTING = {
    "telehealth": "telehealth",
    "home_health": "home_health",
    "hospice": "hospice",
    "dialysis": "dialysis_center",
    "long_term_care": "skilled_nursing",
    "school": "school",
    "correctional": "correctional",
    "urgent_care": "urgent_care",
    "ambulatory": "clinic",
}
_INPATIENT_SPECIALTIES = {
    "icu", "nicu", "picu", "emergency", "labor_delivery", "mother_baby", "operating_room",
    "pacu_preop", "cath_lab", "med_surg", "telemetry", "float_pool", "burn", "transplant",
}


def classify_setting(
    title: str | None,
    company: str | None,
    location: str | None,
    specialties: list[str],
    description: str | None = None,
    remote: bool = False,
) -> str | None:
    if remote or "telehealth" in specialties:
        return "telehealth"
    # Title-level specialty is the strongest signal (a home health RN posted by
    # a hospital system works in patients' homes, not the hospital).
    for spec in specialties:
        if spec in _SPECIALTY_TO_SETTING:
            return _SPECIALTY_TO_SETTING[spec]
    if any(s in _INPATIENT_SPECIALTIES for s in specialties):
        return "hospital"
    # Then the employer and worksite names.
    where = " ".join([title or "", company or "", location or ""])
    for setting, rx in _SETTING_RULES:
        if rx.search(where):
            return setting
    # Finally the opening of the description, where ATS boilerplate names the
    # facility. Only the strongest facility-type phrases count here.
    head = (description or "")[:1500]
    for setting in ("home_health", "hospice", "dialysis_center", "skilled_nursing", "ambulatory_surgery", "hospital"):
        rx = dict(_SETTING_RULES)[setting]
        if rx.search(head):
            return setting
    return None


# ---------------------------------------------------------------------------
# Employment type
# ---------------------------------------------------------------------------

EMPLOYMENT_TYPES = ["full_time", "part_time", "prn", "contract", "travel", "temporary", "internship"]

_EMP_TITLE_RULES = [
    ("travel", re.compile(r"\btravel(?:er|ing)?\b", re.I)),
    ("prn", re.compile(r"\bPRN\b|\bper[\s\-]?diem\b|\bcasual\b|\bcontingent\b|\bon[\s\-]call\b|\bas[\s\-]needed\b|\bpool\b", re.I)),
    ("internship", re.compile(r"\bintern(?:ship)?\b|\bextern(?:ship)?\b", re.I)),
    ("contract", re.compile(r"\bcontract(?:or)?\b|\blocum", re.I)),
    ("temporary", re.compile(r"\btemp(?:orary)?\b|\bseasonal\b", re.I)),
    ("part_time", re.compile(r"\bpart[\s\-]?time\b|\bPT\b(?=.*(?:days|nights|evenings|weekends|\d))", re.I)),
    ("full_time", re.compile(r"\bfull[\s\-]?time\b|\bFT\b", re.I)),
]

# ATS boilerplate: "Time Type: Full time", "Employment Type: PRN", "Status: Part-Time"
_EMP_LABEL_RE = re.compile(
    r"(?:time\s+type|employment\s+(?:type|status)|job\s+(?:type|status)|position\s+(?:type|status)|work\s+type|schedule|status|FTE\s+status)"
    r"\s*[:\-–]?\s*(full[\s\-]?time|part[\s\-]?time|PRN|per[\s\-]?diem|temporary|temp\b|contract|casual|seasonal)",
    re.I,
)


def _emp_from_word(word: str) -> str:
    w = word.lower().replace("-", " ").replace("  ", " ")
    if w.startswith("full"):
        return "full_time"
    if w.startswith("part"):
        return "part_time"
    if w in ("prn", "per diem", "perdiem", "casual"):
        return "prn"
    if w.startswith("temp") or w == "seasonal":
        return "temporary"
    if w == "contract":
        return "contract"
    return "full_time"


def classify_employment_type(title: str | None, description: str | None, shift: str | None = None) -> str | None:
    t = title or ""
    for kind, rx in _EMP_TITLE_RULES:
        if rx.search(t):
            # "Float Pool" is a unit, not PRN status.
            if kind == "prn" and re.search(r"\bfloat\s+pool|\bresource\s+pool", t, re.I) and not re.search(
                r"\bPRN\b|\bper[\s\-]?diem", t, re.I
            ):
                continue
            return kind
    if shift == "prn":
        return "prn"
    m = _EMP_LABEL_RE.search((description or "")[:4000])
    if m:
        return _emp_from_word(m.group(1))
    head = (description or "")[:1500]
    if re.search(r"\bfull[\s\-]time\b", head, re.I):
        return "full_time"
    if re.search(r"\bpart[\s\-]time\b", head, re.I):
        return "part_time"
    return None


# ---------------------------------------------------------------------------
# Schedule
# ---------------------------------------------------------------------------

_SHIFT_12_RE = re.compile(
    r"\b12[\s\-]*(?:hr|hour)s?\b|\b12'?s\b|\b3\s*x\s*12|\b(?:7|6|7:00|6:30|7:30)\s*[ap]m?\s*(?:-|–|to)\s*(?:7|6|7:00|6:30|7:30)\s*[ap]m?\b|\b7a\s*-\s*7p|\b7p\s*-\s*7a",
    re.I,
)
_SHIFT_10_RE = re.compile(r"\b10[\s\-]*(?:hr|hour)s?\b|\b10'?s\b|\b4\s*x\s*10", re.I)
_SHIFT_8_RE = re.compile(r"\b8[\s\-]*(?:hr|hour)s?\b|\b8'?s\b|\b5\s*x\s*8", re.I)
_WEEKEND_RE = re.compile(r"\bweekend(?:s)?\s+(?:only|option|program|warrior|plan)\b|\bbaylor\b", re.I)
_HOURS_PER_WEEK_RE = re.compile(r"\b(\d{2})(?:\.\d+)?\s*(?:hours|hrs)\s*(?:per|/|a)\s*week", re.I)
_FTE_RE = re.compile(r"\b(?:FTE|full[\s\-]time\s+equivalent)\s*[:\-]?\s*(0?\.\d+|1\.0|1)\b|\b(0?\.\d+|1\.0)\s*FTE\b", re.I)


def classify_schedule(title: str | None, description: str | None) -> dict:
    t = title or ""
    head = (description or "")[:3000]
    out: dict = {}
    for hours, rx in ((12, _SHIFT_12_RE), (10, _SHIFT_10_RE), (8, _SHIFT_8_RE)):
        if rx.search(t):
            out["shift_hours"] = hours
            break
    else:
        for hours, rx in ((12, _SHIFT_12_RE), (10, _SHIFT_10_RE), (8, _SHIFT_8_RE)):
            if rx.search(head):
                out["shift_hours"] = hours
                break
    if _WEEKEND_RE.search(t) or re.search(r"\bweekends?\b", t, re.I):
        out["weekend"] = True
    m = _HOURS_PER_WEEK_RE.search(head)
    if m and 8 <= int(m.group(1)) <= 60:
        out["hours_per_week"] = int(m.group(1))
    m = _FTE_RE.search(head)
    if m:
        try:
            fte = float(m.group(1) or m.group(2))
            if 0 < fte <= 1:
                out["fte"] = round(fte, 2)
        except (TypeError, ValueError):
            pass
    return out


# ---------------------------------------------------------------------------
# Requirements
# ---------------------------------------------------------------------------

CERTIFICATIONS = [
    "BLS", "ACLS", "PALS", "NRP", "TNCC", "ENPC", "CCRN", "CEN", "CNOR", "PCCN",
    "RNC-OB", "RNC-NIC", "CPN", "OCN", "NIHSS", "STABLE", "CPI", "CMSRN",
    "CPR", "CRRN", "CWOCN", "CHPN", "CNN", "CDN", "ARRT", "RRT", "RDMS",
]
_CERT_RE = re.compile(
    r"\b(BLS|ACLS|PALS|NRP|TNCC|ENPC|CCRN|CEN|CNOR|PCCN|RNC[\-\s]?OB|RNC[\-\s]?NIC|CPN|OCN|NIHSS|S\.?T\.?A\.?B\.?L\.?E\.?|CPI|CMSRN|CPR|CRRN|CWOCN|CHPN|CNN|CDN|ARRT|RRT|RDMS)\b"
)
_COMPACT_RE = re.compile(
    r"\bcompact\s+(?:state\s+)?(?:nursing\s+)?licen|\bmulti[\s\-]?state\s+(?:nursing\s+)?licen|\bNLC\b|\bnurse\s+licensure\s+compact|\bcompact\s+(?:RN|LPN)\b",
    re.I,
)
_NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_YEARS_RE = re.compile(
    r"\b(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:\(\d+\)\s*)?\+?\s*(?:(?:-|–|to)\s*\d+\s*)?(?:years?|yrs?)\b"
    r"(?:\s+of)?(?:\s+[\w/&\-]+){0,5}?\s+experience",
    re.I,
)
_NEW_GRAD_OK_RE = re.compile(
    r"\bnew\s+grad(?:uate)?s?\s+(?:are\s+)?(?:welcome|encouraged|considered|accepted|may\s+apply|eligible)"
    r"|\bno\s+(?:prior\s+)?experience\s+(?:is\s+)?(?:required|necessary|needed)"
    r"|\bwill\s+train\b|\bnew\s+graduate\s+(?:nurse|RN)s?\b|\bentry[\s\-]level\b",
    re.I,
)
_BSN_REQ_RE = re.compile(
    r"(?:BSN|bachelor'?s?(?:\s+degree)?\s+(?:of|in)\s+(?:science\s+in\s+)?nursing)[^.\n]{0,60}\brequired"
    r"|\brequired[^.\n]{0,40}(?:BSN|bachelor'?s?(?:\s+degree)?\s+(?:of|in)\s+(?:science\s+in\s+)?nursing)",
    re.I,
)
_BSN_PREF_RE = re.compile(
    r"(?:BSN|bachelor'?s?(?:\s+degree)?\s+(?:of|in)\s+(?:science\s+in\s+)?nursing)[^.\n]{0,60}\bpreferred"
    r"|\bpreferred[^.\n]{0,40}(?:BSN|bachelor'?s?(?:\s+degree)?\s+(?:of|in)\s+(?:science\s+in\s+)?nursing)",
    re.I,
)


def _norm_cert(c: str) -> str:
    c = c.upper().replace(" ", "-").replace(".", "")
    if c.startswith("RNC") and "-" not in c:
        c = "RNC-" + c[3:]
    return c


def classify_requirements(title: str | None, description: str | None, level: str) -> dict:
    desc = description or ""
    out: dict = {}
    certs = sorted({_norm_cert(m.group(1)) for m in _CERT_RE.finditer(desc)})
    # CPR on its own is BLS for healthcare purposes; keep BLS as the canonical name.
    if "CPR" in certs:
        certs.remove("CPR")
        if "BLS" not in certs:
            certs.append("BLS")
            certs.sort()
    if certs:
        out["certifications"] = certs
    if _COMPACT_RE.search(desc) or _COMPACT_RE.search(title or ""):
        out["compact_license"] = True
    years = []
    for m in _YEARS_RE.finditer(desc):
        raw = m.group(1).lower()
        n = _NUM_WORDS.get(raw) if not raw.isdigit() else int(raw)
        if n is not None and 0 <= n <= 15:
            years.append(n)
    if years:
        out["min_years_experience"] = min(years)
    if level == "new_grad" or _NEW_GRAD_OK_RE.search(desc) or (years and min(years) == 0):
        out["new_grad_ok"] = True
    elif years and min(years) >= 1:
        out["new_grad_ok"] = False
    if _BSN_REQ_RE.search(desc):
        out["bsn"] = "required"
    elif _BSN_PREF_RE.search(desc):
        out["bsn"] = "preferred"
    return out


# ---------------------------------------------------------------------------
# Pay
# ---------------------------------------------------------------------------

HOURS_PER_YEAR = 2080


def _to_int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def normalize_pay(salary_min, salary_max, source: str | None) -> dict:
    """Salary is stored as annualized cents (hourly × 2080). Return both hourly
    and annual dollar figures so an agent can answer either kind of question."""
    lo, hi = _to_int(salary_min), _to_int(salary_max)
    if lo is None and hi is None:
        return {}
    lo = lo if lo is not None else hi
    hi = hi if hi is not None else lo
    if lo > hi:
        lo, hi = hi, lo
    annual_lo, annual_hi = lo / 100, hi / 100
    if annual_lo < 15000 or annual_hi > 1_000_000:
        return {}
    return {
        "annual_min": round(annual_lo),
        "annual_max": round(annual_hi),
        "hourly_min": round(annual_lo / HOURS_PER_YEAR, 2),
        "hourly_max": round(annual_hi / HOURS_PER_YEAR, 2),
        "currency": "USD",
        "source": source or "posted",
    }


# ---------------------------------------------------------------------------
# Remote
# ---------------------------------------------------------------------------

_REMOTE_RE = re.compile(r"\bremote\b|\bvirtual\b|\btelehealth\b|\bwork\s+from\s+home\b|\bWFH\b|\btelecommute", re.I)


def is_remote(title: str | None, location: str | None) -> bool:
    return bool(_REMOTE_RE.search(location or "") or re.search(r"\bremote\b|\bwork\s+from\s+home\b|\bWFH\b", title or "", re.I))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def classify(
    title: str | None,
    description: str | None = None,
    departments: list[str] | None = None,
    company: str | None = None,
    location: str | None = None,
    shift: str | None = None,
) -> dict:
    """Return the structured facets for one job. Keys with no signal are omitted."""
    role = classify_role(title)
    level = classify_level(title)
    specialties = classify_specialties(title, departments)
    remote = is_remote(title, location)
    setting = classify_setting(title, company, location, specialties, description, remote)
    out: dict = {"role": role, "level": level}
    if ROLE_SOC.get(role):
        out["soc"] = ROLE_SOC[role]
    if specialties:
        out["specialties"] = specialties
    if setting:
        out["setting"] = setting
    if remote:
        out["remote"] = True
    emp = classify_employment_type(title, description, shift)
    if emp:
        out["employment_type"] = emp
    sched = classify_schedule(title, description)
    if sched:
        out["schedule"] = sched
    req = classify_requirements(title, description, level)
    if req:
        out["requirements"] = req
    return out


# ---------------------------------------------------------------------------
# Taxonomy published to agents (index.json, /api/v1/taxonomy). Aliases are the
# words people actually type; the API maps them back to slugs.
# ---------------------------------------------------------------------------

ROLE_ALIASES: dict[str, list[str]] = {
    "rn": ["rn", "registered nurse", "nurse", "staff nurse", "bsn"],
    "nurse_practitioner": ["np", "nurse practitioner", "aprn", "arnp", "fnp", "pmhnp", "agacnp", "family nurse practitioner"],
    "crna": ["crna", "nurse anesthetist"],
    "cnm": ["cnm", "midwife", "nurse midwife"],
    "clinical_nurse_specialist": ["cns", "clinical nurse specialist"],
    "lpn": ["lpn", "lvn", "licensed practical nurse", "licensed vocational nurse"],
    "cna": ["cna", "nursing assistant", "nurse aide", "stna", "gna"],
    "patient_care_tech": ["pct", "patient care tech", "patient care technician", "nurse tech"],
    "medical_assistant": ["ma", "cma", "medical assistant"],
    "home_health_aide": ["hha", "home health aide", "caregiver"],
    "physician": ["physician", "doctor", "md", "do", "hospitalist"],
    "physician_assistant": ["pa", "pa-c", "physician assistant", "physician associate"],
    "physical_therapist": ["pt", "dpt", "physical therapist"],
    "physical_therapist_assistant": ["pta", "physical therapist assistant"],
    "occupational_therapist": ["ot", "otr", "occupational therapist"],
    "occupational_therapy_assistant": ["cota", "occupational therapy assistant"],
    "speech_language_pathologist": ["slp", "speech therapist", "speech language pathologist"],
    "respiratory_therapist": ["rt", "rrt", "respiratory therapist"],
    "pharmacist": ["pharmacist", "pharmd", "rph"],
    "pharmacy_technician": ["pharmacy tech", "pharmacy technician", "cpht"],
    "imaging_technologist": ["rad tech", "radiologic technologist", "x-ray tech", "ct tech", "mri tech", "mammographer"],
    "sonographer": ["sonographer", "ultrasound tech", "echo tech", "vascular tech"],
    "radiation_therapist": ["radiation therapist"],
    "lab_technologist": ["mls", "mlt", "cls", "lab tech", "medical lab scientist", "medical technologist"],
    "phlebotomist": ["phlebotomist", "phlebotomy"],
    "surgical_technologist": ["surg tech", "surgical tech", "scrub tech", "cst"],
    "paramedic": ["paramedic", "emt"],
    "dietitian": ["dietitian", "rd", "rdn", "nutritionist"],
    "social_worker": ["social worker", "lcsw", "msw", "lmsw"],
    "dentist": ["dentist", "dds", "dmd"],
    "dental_hygienist": ["dental hygienist", "rdh", "hygienist"],
    "dental_assistant": ["dental assistant"],
    "athletic_trainer": ["athletic trainer", "atc"],
    "behavioral_health_tech": ["behavioral health tech", "mental health tech", "psych tech"],
}

SPECIALTY_ALIASES: dict[str, list[str]] = {
    "icu": ["icu", "critical care", "intensive care", "micu", "sicu", "cvicu", "ccu"],
    "nicu": ["nicu", "neonatal"],
    "picu": ["picu", "pediatric icu"],
    "emergency": ["er", "ed", "emergency", "emergency room", "emergency department", "trauma"],
    "labor_delivery": ["l&d", "labor and delivery", "labor & delivery", "ob", "obstetrics"],
    "mother_baby": ["mother baby", "postpartum", "nursery", "women's health"],
    "operating_room": ["or", "operating room", "periop", "perioperative", "surgery", "circulator"],
    "pacu_preop": ["pacu", "pre-op", "preop", "recovery", "post anesthesia"],
    "cath_lab": ["cath lab", "interventional", "ep lab"],
    "med_surg": ["med surg", "med-surg", "medsurg", "medical surgical"],
    "telemetry": ["tele", "telemetry", "step down", "stepdown", "pcu", "progressive care"],
    "oncology": ["oncology", "onc", "cancer", "hematology"],
    "infusion": ["infusion"],
    "psych": ["psych", "psychiatric", "behavioral health", "mental health"],
    "pediatrics": ["peds", "pediatrics", "pediatric"],
    "dialysis": ["dialysis", "nephrology", "renal"],
    "home_health": ["home health", "home care"],
    "hospice": ["hospice", "palliative"],
    "rehab": ["rehab", "rehabilitation"],
    "long_term_care": ["ltc", "long term care", "snf", "skilled nursing", "nursing home", "assisted living"],
    "ambulatory": ["clinic", "ambulatory", "outpatient", "primary care"],
    "urgent_care": ["urgent care"],
    "cardiology": ["cardiac", "cardiology", "cardiovascular"],
    "neuro": ["neuro", "neurology", "stroke"],
    "ortho": ["ortho", "orthopedics"],
    "gi_endoscopy": ["gi", "endoscopy"],
    "wound_care": ["wound care", "wound"],
    "case_management": ["case management", "case manager", "utilization review", "care coordination"],
    "infection_prevention": ["infection prevention", "infection control"],
    "occupational_health": ["occupational health", "employee health"],
    "school": ["school", "school nurse"],
    "correctional": ["correctional", "corrections", "prison", "jail"],
    "float_pool": ["float", "float pool"],
    "telehealth": ["telehealth", "remote", "virtual", "telemedicine"],
    "informatics": ["informatics", "quality"],
    "transplant": ["transplant"],
    "burn": ["burn"],
}


def taxonomy() -> dict:
    return {
        "roles": [
            {"slug": slug, "label": label, "soc": soc, "aliases": ROLE_ALIASES.get(slug, [])}
            for slug, label, soc, _, _ in ROLES
        ],
        "specialties": [
            {"slug": slug, "label": label, "aliases": SPECIALTY_ALIASES.get(slug, [])}
            for slug, label, _ in SPECIALTIES
        ],
        "settings": [{"slug": k, "label": v} for k, v in SETTING_LABELS.items()],
        "employment_types": EMPLOYMENT_TYPES,
        "shifts": ["days", "nights", "evenings", "rotating", "weekends", "prn"],
        "levels": ["new_grad", "staff", "charge", "educator", "leadership"],
    }
