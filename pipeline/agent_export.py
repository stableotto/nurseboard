"""Machine-readable job data for AI agents.

Writes everything under frontend/data/agent/ (gitignored, regenerated each run):

  index.json             shard manifest, state bounding boxes, taxonomy, counts
  shards/state/XX.json   every live job in a state (compact keys, see KEYS)
  shards/remote.json     remote / telehealth jobs
  shards/national/*.json newest jobs per role (and role × specialty when the
                         role shard is truncated), for queries with no location
  pay.json               posted-pay benchmarks by role × (nation|state|metro|specialty)
  jobs.ndjson.gz         full bulk feed, one job per line, readable keys

The worker (frontend/_worker.js) answers /api/v1/* and /mcp from these files:
it picks the smallest shard set that covers a query, filters, and paginates.
Shards are sized like the existing /data/jobs/{prefix}.json detail chunks, which
the worker already parses per request.
"""

from __future__ import annotations

import gzip
import json
import logging
import os
import shutil
import statistics
from datetime import datetime, timezone

from pipeline.classify import ROLE_LABELS, taxonomy

logger = logging.getLogger(__name__)

AGENT_DIR = "frontend/data/agent"
SITE_URL = "https://scrubshifts.com"

# Cap for shards that are a convenience slice (national / role) rather than a
# complete partition. State and remote shards are never capped.
NATIONAL_SHARD_CAP = 4000
# Minimum pay samples before a benchmark is published.
MIN_PAY_SAMPLES = 5
# Cloudflare Pages rejects files over 25 MiB; stay clear of it.
MAX_FILE_BYTES = 24 * 1024 * 1024

# Full key -> compact shard key. The worker holds the inverse map; keep in sync
# with SHARD_KEYS in frontend/_worker.js.
KEYS = {
    "id": "i",
    "title": "t",
    "company": "c",
    "location": "l",
    "state": "s",
    "metro": "m",
    "lat": "la",
    "lng": "ln",
    "remote": "rm",
    "role": "r",
    "level": "v",
    "specialties": "sp",
    "setting": "se",
    "employment_type": "e",
    "shift": "sh",
    "shift_hours": "h",
    "weekend": "w",
    "hourly_min": "pl",
    "hourly_max": "ph",
    "pay_source": "ps",
    "sign_on_bonus": "b",
    "certifications": "ce",
    "compact_license": "cl",
    "min_years_experience": "y",
    "new_grad_ok": "ng",
    "bsn": "bs",
    "posted_date": "d",
    "first_seen": "f",
    "slug": "u",
    "apply_url": "a",
}


def build_record(entry: dict, facets: dict, pay: dict, apply_url: str, coords, last_verified) -> dict:
    """One job as agents see it: readable keys, no description, no None values."""
    sched = facets.get("schedule", {})
    req = facets.get("requirements", {})
    rec = {
        "id": entry["id"],
        "title": entry["title"],
        "company": entry.get("company_name"),
        "location": entry.get("location"),
        "state": entry.get("state"),
        "metro": entry.get("metro"),
        "lat": coords[0] if coords else None,
        "lng": coords[1] if coords else None,
        "remote": facets.get("remote"),
        "role": facets["role"],
        "soc": facets.get("soc"),
        "level": facets.get("level"),
        "specialties": facets.get("specialties"),
        "setting": facets.get("setting"),
        "employment_type": facets.get("employment_type"),
        "shift": entry.get("shift"),
        "shift_hours": sched.get("shift_hours"),
        "weekend": sched.get("weekend"),
        "hours_per_week": sched.get("hours_per_week"),
        "fte": sched.get("fte"),
        "hourly_min": pay.get("hourly_min"),
        "hourly_max": pay.get("hourly_max"),
        "annual_min": pay.get("annual_min"),
        "annual_max": pay.get("annual_max"),
        "pay_source": pay.get("source"),
        "sign_on_bonus": round(entry["bonus"] / 100) if entry.get("bonus") else None,
        "certifications": req.get("certifications"),
        "compact_license": req.get("compact_license"),
        "min_years_experience": req.get("min_years_experience"),
        "new_grad_ok": req.get("new_grad_ok"),
        "bsn": req.get("bsn"),
        "posted_date": (entry.get("posted_date") or "")[:10] or None,
        "first_seen": (entry.get("first_seen_at") or "")[:10] or None,
        "last_verified": (last_verified or "")[:10] or None,
        "slug": entry["slug"],
        "listing_url": f"{SITE_URL}/listing/{entry['slug']}/",
        "apply_url": apply_url,
    }
    # False is dropped like None, except new_grad_ok where "no" is an answer.
    return {
        k: v
        for k, v in rec.items()
        if v is not None and v != [] and (v is not False or k == "new_grad_ok")
    }


def _compact(rec: dict) -> dict:
    out = {}
    for full, short in KEYS.items():
        v = rec.get(full)
        if v is None or v == []:
            continue
        if isinstance(v, bool):
            v = 1 if v else 0
        out[short] = v
    return out


def _recency(rec: dict) -> str:
    return rec.get("posted_date") or rec.get("first_seen") or ""


def _write_json(path: str, data) -> int:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    raw = json.dumps(data, separators=(",", ":"))
    with open(path, "w") as f:
        f.write(raw)
    return len(raw)


def _pct(sorted_vals: list[float], q: float) -> float:
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = (len(sorted_vals) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def build_pay_benchmarks(records: list[dict]) -> dict:
    """Median and interquartile posted hourly pay per role, sliced by nation,
    state, metro and specialty. Uses the midpoint of each posted range."""
    groups: dict[tuple, list[float]] = {}
    counts: dict[tuple, int] = {}

    def add(key, val):
        counts[key] = counts.get(key, 0) + 1
        if val is not None:
            groups.setdefault(key, []).append(val)

    for r in records:
        lo, hi = r.get("hourly_min"), r.get("hourly_max")
        mid = (lo + hi) / 2 if lo is not None and hi is not None else None
        if mid is not None and not (10 <= mid <= 400):
            mid = None
        role = r["role"]
        add(("national", role, ""), mid)
        if r.get("state"):
            add(("state", role, r["state"]), mid)
        if r.get("metro"):
            add(("metro", role, r["metro"]), mid)
        for sp in r.get("specialties", []):
            add(("specialty", role, sp), mid)
            if r.get("state"):
                add(("specialty_state", role, f"{sp}|{r['state']}"), mid)

    out: dict[str, list] = {"national": [], "state": [], "metro": [], "specialty": [], "specialty_state": []}
    for key, vals in groups.items():
        if len(vals) < MIN_PAY_SAMPLES:
            continue
        scope, role, where = key
        vals.sort()
        row = {
            "role": role,
            "role_label": ROLE_LABELS.get(role, role),
            "jobs": counts[key],
            "jobs_with_pay": len(vals),
            "hourly_p25": round(_pct(vals, 0.25), 2),
            "hourly_median": round(statistics.median(vals), 2),
            "hourly_p75": round(_pct(vals, 0.75), 2),
            "annual_median": round(statistics.median(vals) * 2080),
        }
        if scope == "state":
            row["state"] = where
        elif scope == "metro":
            row["metro"] = where
        elif scope == "specialty":
            row["specialty"] = where
        elif scope == "specialty_state":
            row["specialty"], row["state"] = where.split("|")
        out[scope].append(row)
    for rows in out.values():
        rows.sort(key=lambda x: (x["role"], x.get("state", ""), x.get("metro", ""), x.get("specialty", "")))
    return out


def export_agent_data(records: list[dict]) -> None:
    """Write shards, index, pay benchmarks and bulk feed for agent consumption."""
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Build into a scratch directory and swap it in at the end, so a failure
    # part-way never leaves a half-written data set being served.
    out = AGENT_DIR + ".tmp"
    shutil.rmtree(out, ignore_errors=True)
    records = sorted(records, key=_recency, reverse=True)

    shards: dict[str, dict] = {}
    by_state: dict[str, list] = {}
    remote: list = []
    by_role: dict[str, list] = {}
    for r in records:
        if r.get("remote"):
            remote.append(r)
        if r.get("state"):
            by_state.setdefault(r["state"], []).append(r)
        by_role.setdefault(r["role"], []).append(r)

    def write_shard(name: str, recs: list[dict], total: int, extra: dict | None = None):
        path = os.path.join(out, "shards", f"{name}.json")
        size = _write_json(path, [_compact(r) for r in recs])
        while size > MAX_FILE_BYTES:
            recs = recs[: int(len(recs) * 0.9)]
            size = _write_json(path, [_compact(r) for r in recs])
        meta = {"jobs": len(recs), "total": total, "truncated": len(recs) < total, "bytes": size}
        if extra:
            meta.update(extra)
        shards[name] = meta

    for st, recs in by_state.items():
        lats = [r["lat"] for r in recs if "lat" in r]
        lngs = [r["lng"] for r in recs if "lng" in r]
        bbox = [min(lats), min(lngs), max(lats), max(lngs)] if lats else None
        write_shard(f"state/{st}", recs, len(recs), {"bbox": bbox})
    if remote:
        write_shard("remote", remote, len(remote))
    write_shard("national/_all", records[:NATIONAL_SHARD_CAP], len(records))
    for role, recs in by_role.items():
        write_shard(f"national/{role}", recs[:NATIONAL_SHARD_CAP], len(recs))
        if len(recs) > NATIONAL_SHARD_CAP:
            by_spec: dict[str, list] = {}
            for r in recs:
                for sp in r.get("specialties", []):
                    by_spec.setdefault(sp, []).append(r)
            for sp, srecs in by_spec.items():
                write_shard(f"national/{role}__{sp}", srecs[:NATIONAL_SHARD_CAP], len(srecs))

    pay = build_pay_benchmarks(records)
    _write_json(os.path.join(out, "pay.json"), {"generated_at": generated_at, **pay})

    bulk_path = os.path.join(out, "jobs.ndjson.gz")
    bulk = records
    while True:
        with gzip.open(bulk_path, "wt", encoding="utf-8") as f:
            for r in bulk:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
        if os.path.getsize(bulk_path) <= MAX_FILE_BYTES:
            break
        bulk = bulk[: int(len(bulk) * 0.9)]
        logger.warning("jobs.ndjson.gz over size limit; keeping newest %d jobs", len(bulk))

    role_counts: dict[str, int] = {role: len(recs) for role, recs in by_role.items()}
    index = {
        "generated_at": generated_at,
        "total_jobs": len(records),
        "jobs_with_pay": sum(1 for r in records if "hourly_min" in r),
        "jobs_with_coords": sum(1 for r in records if "lat" in r),
        "bulk_feed_jobs": len(bulk),
        "role_counts": dict(sorted(role_counts.items(), key=lambda x: -x[1])),
        "state_counts": {st: len(recs) for st, recs in sorted(by_state.items())},
        "shards": shards,
        "keys": KEYS,
        "taxonomy": taxonomy(),
    }
    _write_json(os.path.join(out, "index.json"), index)
    shutil.rmtree(AGENT_DIR, ignore_errors=True)
    os.replace(out, AGENT_DIR)
    biggest = max(shards.items(), key=lambda kv: kv[1]["bytes"])
    logger.info(
        "Agent export: %d jobs, %d shards (largest %s at %.1f MB), %d with pay, %d with coords",
        len(records),
        len(shards),
        biggest[0],
        biggest[1]["bytes"] / 1e6,
        index["jobs_with_pay"],
        index["jobs_with_coords"],
    )
