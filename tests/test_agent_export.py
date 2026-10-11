"""Tests for the agent export helpers. Run: python -m pytest tests/"""

from pipeline.agent_export import build_pay_benchmarks, dedupe_records, _compact, KEYS
from pipeline.classify import classify
from pipeline.export import _locate, _place_names


def test_place_names_strip_census_suffixes():
    assert _place_names("Arcadia city") == ["arcadia"]
    assert _place_names("Boise City city") == ["boise city"]
    assert _place_names("Indianapolis city (balance)") == ["indianapolis"]
    assert _place_names("Nashville-Davidson metropolitan government (balance)") == [
        "nashville-davidson",
        "nashville",
    ]
    assert _place_names("Urban Honolulu CDP") == ["urban honolulu", "honolulu"]
    assert "saint louis" in _place_names("St. Louis city")


def test_locate_fallbacks():
    cities = {"phoenix|AZ": [33.57, -112.09], "st. george|UT": [37.1, -113.6]}
    zips = {"55407": [44.94, -93.25]}
    assert _locate({"location": "St George, UT", "state": "UT"}, "", cities, zips) == ("UT", [37.1, -113.6], "city")
    assert _locate({"location": "BUMC Phoenix"}, "Primary City/State: Phoenix, Arizona Department Name: ICU", cities, zips) == (
        "AZ",
        [33.57, -112.09],
        "city",
    )
    assert _locate({"location": "Abbott Northwestern"}, "2800 10th Ave Minneapolis MN 55407", cities, zips) == (
        "MN",
        [44.94, -93.25],
        "zip",
    )
    assert _locate({"location": "Texas"}, "", cities, zips) == ("TX", None, None)
    assert _locate({"location": "Main Campus"}, "", cities, zips) == (None, None, None)


def test_classify_ignores_non_string_departments():
    assert classify("RN", None, [None, {"name": "x"}, "ICU"])["specialties"] == ["icu"]


def test_pay_benchmarks():
    recs = [{"role": "rn", "state": "CO", "hourly_min": h, "hourly_max": h + 10} for h in (40, 45, 50, 55, 60)]
    recs.append({"role": "rn", "state": "CO"})  # no pay: counted in jobs, not in pay stats
    out = build_pay_benchmarks(recs)
    row = out["state"][0]
    assert row["jobs"] == 6 and row["jobs_with_pay"] == 5
    assert row["hourly_median"] == 55.0  # midpoints 45..65
    assert row["hourly_p25"] == 50.0 and row["hourly_p75"] == 60.0
    assert build_pay_benchmarks(recs[:4])["state"] == []  # under MIN_PAY_SAMPLES


def test_dedupe_cross_posted_copies():
    base = {"title": "RN Clinical - 4 S ICU - Full Time 12 Hour Nights", "location": "Los Angeles, CA",
            "hourly_min": 44.0, "hourly_max": 95.0, "posted_date": "2026-05-26"}
    a = {**base, "id": "a", "company": "USC"}
    b = {**base, "id": "b", "company": "USC University of Southern California", "setting": "hospital"}
    other = {**base, "id": "c", "company": "Cedars-Sinai"}
    generic1 = {"id": "d", "title": "Registered Nurse", "location": "Austin, TX", "company": "Baptist Health"}
    generic2 = {"id": "e", "title": "Registered Nurse", "location": "Austin, TX", "company": "Baptist Memorial"}
    out = {r["id"]: r for r in dedupe_records([a, b, other, generic1, generic2])}
    assert set(out) == {"b", "c", "d", "e"}  # b is more complete than a
    assert out["b"]["duplicate_ids"] == ["a"]
    # One employer's identical openings are separate jobs, not duplicates.
    reqs = [{**base, "id": f"r{i}", "company": "Allina Health"} for i in range(3)]
    assert len(dedupe_records(reqs)) == 3


def test_compact_keys_roundtrip():
    rec = {"id": "abc", "title": "RN", "remote": True, "new_grad_ok": False, "specialties": []}
    c = _compact(rec)
    assert c == {"i": "abc", "t": "RN", "rm": 1, "ng": 0}
    assert len(set(KEYS.values())) == len(KEYS)
