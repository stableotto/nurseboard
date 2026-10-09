"""Unit tests for pipeline.classify. Run: python -m pytest tests/"""

from pipeline.classify import classify, classify_role, classify_specialties, normalize_pay


def test_role_full_names_beat_abbreviations():
    assert classify_role("Phlebotomist PT Days") == "phlebotomist"  # PT = part-time
    assert classify_role("RN - Boston, MA Clinic") == "rn"  # MA = Massachusetts
    assert classify_role("Physical Therapist Assistant") == "physical_therapist_assistant"
    assert classify_role("Pharmacy Technician") == "pharmacy_technician"
    assert classify_role("Speech-Language Pathologist") == "speech_language_pathologist"
    assert classify_role("Physician Practice RN") == "rn"


def test_role_nursing_ladder():
    assert classify_role("Nurse Practitioner - Urgent Care") == "nurse_practitioner"
    assert classify_role("CRNA - Main OR") == "crna"
    assert classify_role("LPN Charge Nurse") == "lpn"
    assert classify_role("Certified Nursing Assistant - Nights") == "cna"
    assert classify_role("Director of Nursing") == "rn"
    assert classify_role("Ambulette Driver") == "other"


def test_specialty_abbreviations_are_case_sensitive():
    assert classify_specialties("OR Nurse Circulator") == ["operating_room"]
    assert "operating_room" not in classify_specialties("RN or LPN - Med Surg")
    assert classify_specialties("Travel ICU RN") == ["icu"]
    assert "icu" not in classify_specialties("NICU RN")


def test_full_classification():
    c = classify(
        "Registered Nurse - 4th Floor Med/Surg Telemetry - Full Time 12 Hour Nights",
        "Requirements: BLS and ACLS required. 1 year of acute care experience. "
        "Compact license accepted. BSN preferred.",
        company="Glendale Memorial Hospital",
        location="Glendale, CA",
        shift="nights",
    )
    assert c["role"] == "rn"
    assert c["soc"] == "29-1141"
    assert c["specialties"] == ["med_surg", "telemetry"]
    assert c["setting"] == "hospital"
    assert c["employment_type"] == "full_time"
    assert c["schedule"]["shift_hours"] == 12
    req = c["requirements"]
    assert req["certifications"] == ["ACLS", "BLS"]
    assert req["compact_license"] is True
    assert req["min_years_experience"] == 1
    assert req["new_grad_ok"] is False
    assert req["bsn"] == "preferred"


def test_new_grad_and_prn():
    c = classify("Residency Program - New Nurse Graduates")
    assert c["level"] == "new_grad" and c["requirements"]["new_grad_ok"] is True
    assert classify("Pharmacist - Inpatient (Contingent)")["employment_type"] == "prn"
    assert classify("Float Pool RN")["specialties"] == ["float_pool"]
    assert "employment_type" not in classify("Float Pool RN")


def test_new_grad_ok_needs_explicit_welcome():
    instructor = classify("Travel Clinical Nurse Instructor", "Teach and support new graduate nurses on the unit.")
    assert "new_grad_ok" not in instructor.get("requirements", {})
    staff = classify("RN - Med Surg", "New grads welcome! Supportive preceptorship.")
    assert staff["requirements"]["new_grad_ok"] is True
    mentions = classify("RN - Med Surg", "Mentor new graduate nurses as a preceptor.")
    assert "new_grad_ok" not in mentions.get("requirements", {})


def test_remote_sets_telehealth():
    c = classify("Virtual Family Nurse Practitioner", location="Remote")
    assert c["remote"] is True and c["setting"] == "telehealth"


def test_normalize_pay():
    p = normalize_pay(10400000, 12480000, "posted")  # $50–60/hr annualized, in cents
    assert p["hourly_min"] == 50.0 and p["hourly_max"] == 60.0
    assert p["annual_min"] == 104000 and p["annual_max"] == 124800
    assert normalize_pay("4652960", None, None)["annual_max"] == 46530  # string input
    assert normalize_pay(None, None, None) == {}
    assert normalize_pay(100, 200, None) == {}  # implausible
