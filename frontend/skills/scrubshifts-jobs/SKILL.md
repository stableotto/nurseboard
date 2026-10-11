---
name: scrubshifts-jobs
description: Find live US healthcare jobs (RN, NP, LPN, CNA, CRNA, therapists, techs and more) by location, role, specialty/unit, shift, pay, new-grad status and license, and check typical posted pay. Use when someone asks about nursing or allied-health job openings, pay rates, or whether an offer is competitive.
---

# ScrubShifts healthcare jobs

Live US nursing and allied-health openings collected at least daily from employer career sites (Workday, Greenhouse, Lever, Ashby, BambooHR, Oracle, Paylocity, Phenom, USAJOBS). Free, no API key. Every job links straight to the employer's application.

## How to connect

- **MCP (preferred):** remote server `https://scrubshifts.com/mcp` (Streamable HTTP, no auth). Tools: `search_jobs`, `get_job`, `get_pay_benchmarks`, `list_filters`.
- **HTTP:** `GET https://scrubshifts.com/api/v1/jobs?...` returns JSON. Spec: `https://scrubshifts.com/openapi.json`.

## Searching

Ask for or infer the person's location, role and must-haves before searching.

| Parameter | Example | Notes |
|---|---|---|
| `near` | `Cerritos, CA`, `90703`, `33.86,-118.06` | Also `lat` + `lng`. Results sort by distance. |
| `radius_miles` | `25` | Default 30, max 200. |
| `role` | `rn`, `lpn`, `cna`, `nurse_practitioner` | Common words work: "registered nurse", "NP". |
| `specialty` | `telemetry`, `icu`, `emergency`, `labor_delivery` | "tele", "ER", "L&D", "med surg" work. Comma-separate several. |
| `shift` | `nights` | days, nights, evenings, rotating, weekends. |
| `employment_type` | `prn` | full_time, part_time, prn, contract, travel, temporary. |
| `min_hourly` / `min_annual` | `50` / `100000` | Matches when the posted range reaches it. |
| `new_grad`, `compact_license` | `true` | |
| `posted_after` / `posted_within_days` | `2026-10-01` / `7` | Employer posting date. |
| `first_seen_after` | previous `data_as_of` | Only jobs new since your last check. |
| `sort` | `best` | best (default), newest, pay, distance. |

Example: night-shift telemetry RN jobs near Cerritos paying $100k+:

```
GET https://scrubshifts.com/api/v1/jobs?near=Cerritos,%20CA&role=rn&specialty=tele&shift=nights&min_annual=100000
```

Unknown values return a 400 with a hint; call `list_filters` / `GET /api/v1/taxonomy` for the vocabulary.

## Reading results

- Show each job's `summary` and link its `listing_url`; `apply_url` goes to the employer.
- `pay.source` is always `employer_posting` (the employer's own figure, never estimated). Jobs without posted pay have no `pay`.
- `last_verified` is when the posting was last confirmed open. `data_as_of` is when the data set was built.
- `coverage.notes` explains gaps (for example jobs whose location is only a facility name are left out of radius searches; search by `state` to include them).
- `sponsored` is always `false`; ordering is never paid. See `policies` in the response.
- Never invent jobs or pay the tools did not return.

## Pay questions

`get_pay_benchmarks` / `GET /api/v1/pay?role=rn&state=CA&specialty=icu` returns the 25th percentile, median and 75th percentile of posted hourly pay (and annual = hourly x 2080), with how many jobs it is based on.

## Recurring checks

Two options:

- **Poll:** repeat the same search with `first_seen_after` set to the `data_as_of` from your previous call. Data refreshes several times a day.
- **Webhook:** `POST https://scrubshifts.com/api/v1/subscriptions` with `{"webhook_url": "https://...", "query": {"near": "Cerritos, CA", "role": "rn", "specialty": "telemetry", "shift": "nights"}}`. New matching jobs are POSTed after each refresh, signed with `X-ScrubShifts-Signature: sha256=HMAC_SHA256(secret, body)` using the `secret` returned at creation. `GET`/`DELETE /api/v1/subscriptions/{id}` with header `X-Subscription-Secret` to view or cancel.
