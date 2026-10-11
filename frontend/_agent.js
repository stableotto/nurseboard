// Agent-facing API for ScrubShifts: REST (/api/v1/*) and a remote MCP server
// (/mcp, Streamable HTTP, stateless). Both answer from the static files that
// pipeline/agent_export.py writes under /data/agent/ on every pipeline run:
//
//   index.json            shard manifest, state bounding boxes, taxonomy
//   shards/state/XX.json  every live job in a state, compact keys
//   shards/remote.json    remote / telehealth jobs
//   shards/national/*     newest jobs per role (and role × specialty)
//   pay.json              posted-pay benchmarks
//
// A query loads the smallest shard set that covers it (a state, the states a
// radius touches, remote, or a national role slice), filters in memory and
// paginates. Shards are the same size class as /data/jobs/{prefix}.json, which
// the listing route already parses per request.

const SITE = "https://scrubshifts.com";
const SERVER_VERSION = "1.0.0";
const MCP_PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"];
const DEFAULT_LIMIT = 10;
const MAX_LIMIT = 50;
const DEFAULT_RADIUS = 30;
const MAX_RADIUS = 200;

const ATTRIBUTION =
  "Job data from ScrubShifts (scrubshifts.com), refreshed daily from employer career sites. " +
  "When showing a job, link its listing_url; apply_url goes straight to the employer.";

// Published guarantees, returned with search results and the API index.
const POLICIES = {
  freshness:
    "Every job is re-read from the employer's career site at least daily. A job that leaves its source is " +
    "removed from results, usually within a day, and a rotating live check re-confirms open postings. " +
    "last_verified is when the posting was last confirmed open; data_as_of is when this data set was built.",
  ranking:
    "Results are ordered only by the requested sort: best (+2 for listed pay, -1 per week since posting, " +
    "-1 per 10 miles), newest, pay, or distance, with ties broken by job id. There is no paid placement; " +
    "if sponsored listings are ever added they will carry sponsored: true and never change this ordering.",
  pay:
    "Pay is the employer's own posted figure (ATS pay field or the range in the posting) and is never " +
    "estimated. Jobs without posted pay have no pay field. Annual = hourly x 2080.",
  duplicates:
    "Cross-posted copies of one job are merged into one result; also_listed_as lists the merged ids.",
};

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
  "Access-Control-Allow-Headers":
    "Content-Type, Accept, Authorization, Mcp-Session-Id, Mcp-Protocol-Version, X-Subscription-Secret",
  "Access-Control-Expose-Headers": "Mcp-Session-Id",
};

// ---------------------------------------------------------------------------
// Data loading. Parsed files are cached per isolate: the index and pay data
// always, plus the most recently used shards (bounded to keep memory low).
// ---------------------------------------------------------------------------

const cache = new Map();
const SHARD_CACHE_LIMIT = 3;
const CACHE_TTL_MS = 10 * 60 * 1000;

async function loadJSON(env, origin, path, { pin = false } = {}) {
  const hit = cache.get(path);
  if (hit && Date.now() - hit.at < CACHE_TTL_MS) {
    // Refresh LRU position.
    cache.delete(path);
    cache.set(path, hit);
    return hit.data;
  }
  const resp = await env.ASSETS.fetch(new Request(new URL(path, origin)));
  if (!resp.ok) return null;
  const ct = resp.headers.get("content-type") || "";
  // Unknown paths can fall back to HTML; never parse that as data.
  if (ct.includes("text/html")) return null;
  const data = await resp.json();
  cache.delete(path);
  cache.set(path, { data, at: Date.now(), pin });
  const unpinned = [...cache.entries()].filter(([, v]) => !v.pin);
  while (unpinned.length > SHARD_CACHE_LIMIT) {
    cache.delete(unpinned.shift()[0]);
  }
  return data;
}

const loadIndex = (env, origin) =>
  loadJSON(env, origin, "/data/agent/index.json", { pin: true });

// ---------------------------------------------------------------------------
// Vocabulary: map what people type ("ER", "L&D", "per diem", "Denver, CO") to
// the slugs the data uses. Role and specialty aliases come from index.json so
// the pipeline is the single source of truth.
// ---------------------------------------------------------------------------

const STATES = {
  AL: "alabama", AK: "alaska", AZ: "arizona", AR: "arkansas", CA: "california",
  CO: "colorado", CT: "connecticut", DE: "delaware", DC: "district of columbia",
  FL: "florida", GA: "georgia", HI: "hawaii", ID: "idaho", IL: "illinois",
  IN: "indiana", IA: "iowa", KS: "kansas", KY: "kentucky", LA: "louisiana",
  ME: "maine", MD: "maryland", MA: "massachusetts", MI: "michigan",
  MN: "minnesota", MS: "mississippi", MO: "missouri", MT: "montana",
  NE: "nebraska", NV: "nevada", NH: "new hampshire", NJ: "new jersey",
  NM: "new mexico", NY: "new york", NC: "north carolina", ND: "north dakota",
  OH: "ohio", OK: "oklahoma", OR: "oregon", PA: "pennsylvania",
  RI: "rhode island", SC: "south carolina", SD: "south dakota",
  TN: "tennessee", TX: "texas", UT: "utah", VT: "vermont", VA: "virginia",
  WA: "washington", WV: "west virginia", WI: "wisconsin", WY: "wyoming",
  PR: "puerto rico",
};
const STATE_BY_NAME = Object.fromEntries(
  Object.entries(STATES).map(([k, v]) => [v, k]),
);

const EMPLOYMENT_ALIASES = {
  full_time: ["full_time", "full time", "full-time", "ft", "fulltime"],
  part_time: ["part_time", "part time", "part-time", "pt", "parttime"],
  prn: ["prn", "per diem", "per-diem", "perdiem", "casual", "on call", "contingent"],
  contract: ["contract", "contractor", "locum", "locums"],
  travel: ["travel", "traveler", "travel nurse", "travel contract"],
  temporary: ["temporary", "temp", "seasonal"],
  internship: ["internship", "intern", "externship", "extern"],
};
const SHIFT_ALIASES = {
  days: ["days", "day", "day shift", "morning", "first shift"],
  nights: ["nights", "night", "night shift", "noc", "overnight", "third shift"],
  evenings: ["evenings", "evening", "evening shift", "second shift", "swing"],
  rotating: ["rotating", "rotation", "variable"],
  weekends: ["weekends", "weekend", "weekend only", "baylor"],
  prn: ["prn"],
};
// Documented, deterministic orderings. No paid placement exists or affects
// any of them; ties always break by job id.
const SORTS = ["best", "newest", "pay", "distance"];

function norm(s) {
  return String(s || "")
    .toLowerCase()
    .replace(/[_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function aliasMap(entries) {
  // entries: [{slug, aliases}] -> Map(normalized alias|slug -> slug)
  const m = new Map();
  for (const e of entries) {
    m.set(norm(e.slug), e.slug);
    for (const a of e.aliases || []) m.set(norm(a), e.slug);
  }
  return m;
}

function resolveList(value, map, field, errors) {
  if (value == null || value === "") return null;
  const raw = Array.isArray(value) ? value : String(value).split(",");
  const out = [];
  for (const v of raw) {
    const n = norm(v);
    if (!n) continue;
    const slug = map.get(n) || map.get(n.replace(/s$/, ""));
    if (slug) {
      if (!out.includes(slug)) out.push(slug);
    } else {
      errors.push(`Unknown ${field} "${v}". Call list_filters (or GET /api/v1/taxonomy) for valid values.`);
    }
  }
  return out.length ? out : null;
}

function fixedAliasMap(obj) {
  return aliasMap(Object.entries(obj).map(([slug, aliases]) => ({ slug, aliases })));
}
const EMPLOYMENT_MAP = fixedAliasMap(EMPLOYMENT_ALIASES);
const SHIFT_MAP = fixedAliasMap(SHIFT_ALIASES);

function toBool(v) {
  if (v === true || v === false) return v;
  if (v == null || v === "") return null;
  const s = String(v).toLowerCase();
  if (["1", "true", "yes", "y"].includes(s)) return true;
  if (["0", "false", "no", "n"].includes(s)) return false;
  return null;
}

function toNum(v) {
  if (v == null || v === "") return null;
  const n = Number(String(v).replace(/[$,\s]/g, "").replace(/k$/i, "000"));
  return Number.isFinite(n) ? n : null;
}

function resolveState(v) {
  if (!v) return null;
  const s = String(v).trim();
  if (STATES[s.toUpperCase()]) return s.toUpperCase();
  return STATE_BY_NAME[norm(s)] || null;
}

// Parse search parameters (from a query string or an MCP tool call) into a
// normalized query. Unknown vocabulary is reported, not silently ignored.
function parseQuery(input, index) {
  const errors = [];
  const tax = index.taxonomy;
  const q = {};
  const get = (k) => (input[k] === undefined ? null : input[k]);

  q.role = resolveList(get("role"), aliasMap(tax.roles), "role", errors);
  q.specialty = resolveList(
    get("specialty"),
    aliasMap(tax.specialties),
    "specialty",
    errors,
  );
  q.setting = resolveList(
    get("setting"),
    aliasMap(tax.settings.map((s) => ({ slug: s.slug, aliases: [s.label] }))),
    "setting",
    errors,
  );
  q.employment_type = resolveList(
    get("employment_type"),
    EMPLOYMENT_MAP,
    "employment_type",
    errors,
  );
  q.shift = resolveList(get("shift"), SHIFT_MAP, "shift", errors);

  const text = get("q") || get("query") || get("keywords");
  if (text) q.q = String(text).slice(0, 200);

  const st = get("state");
  if (st) {
    q.state = resolveState(st);
    if (!q.state) errors.push(`Unknown state "${st}". Use a two-letter code like CO.`);
  }
  let near = get("near") || get("location");
  // lat/lng as separate parameters are equivalent to near="lat,lng".
  const lat = toNum(get("lat"));
  const lng = toNum(get("lng") ?? get("lon"));
  if (!near && lat != null && lng != null) near = `${lat},${lng}`;
  if (near) q.near = String(near).slice(0, 100);
  const radius = toNum(get("radius_miles") ?? get("radius_mi"));
  q.radius_miles = Math.min(Math.max(radius || DEFAULT_RADIUS, 1), MAX_RADIUS);

  q.min_hourly = toNum(get("min_hourly"));
  const minAnnual = toNum(get("min_annual") ?? get("min_pay_annual"));
  if (minAnnual != null) q.min_annual = minAnnual;
  q.has_pay = toBool(get("has_pay"));
  q.new_grad = toBool(get("new_grad"));
  q.compact_license = toBool(get("compact_license"));
  q.remote = toBool(get("remote"));
  const maxYears = toNum(get("max_years_experience"));
  if (maxYears != null) q.max_years_experience = maxYears;
  const within = toNum(get("posted_within_days"));
  if (within != null) q.posted_within_days = Math.max(1, Math.min(within, 365));
  // Polling: posted_after filters on the employer's posting date;
  // first_seen_after on when ScrubShifts first saw the job (use the previous
  // response's data_as_of to get only jobs that are new since then).
  for (const key of ["posted_after", "first_seen_after"]) {
    const v = get(key);
    if (v == null || v === "") continue;
    const t = Date.parse(String(v));
    if (Number.isNaN(t)) errors.push(`${key} must be an ISO date or timestamp, e.g. 2026-10-01 or 2026-10-01T00:00:00Z.`);
    else q[key] = new Date(t).toISOString();
  }

  const sort = norm(get("sort"));
  if (sort && !SORTS.includes(sort)) errors.push(`sort must be one of ${SORTS.join(", ")}.`);
  q.sort = SORTS.includes(sort) ? sort : null;
  q.limit = Math.min(Math.max(toNum(get("limit")) || DEFAULT_LIMIT, 1), MAX_LIMIT);
  q.offset = Math.max(toNum(get("offset")) || 0, 0);

  for (const k of Object.keys(q)) if (q[k] == null) delete q[k];
  return { q, errors };
}

// ---------------------------------------------------------------------------
// Geocoding against the pipeline's own city and ZIP tables.
// ---------------------------------------------------------------------------

// "st louis" / "saint louis" / "st. louis" -> "st. louis" (the table holds
// both "st. x" and "saint x").
function cityKey(name) {
  return norm(name).replace(/^(?:st\.?|saint)\s+/, "st. ");
}

function titleCase(s) {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

// Split a trailing state (code or full name) off a place string. Longest
// state names are tried first so "West Virginia" wins over "Virginia".
const STATE_NAMES_BY_LENGTH = Object.values(STATES).sort((a, b) => b.length - a.length);
function splitCityState(place) {
  const s = norm(place).replace(/[,.]+$/, "");
  let m = s.match(/^(.+?)[,\s]+([a-z]{2})$/);
  if (m && STATES[m[2].toUpperCase()]) {
    return { city: cityKey(m[1].replace(/,$/, "")), state: m[2].toUpperCase() };
  }
  for (const name of STATE_NAMES_BY_LENGTH) {
    if (s.endsWith(` ${name}`) || s.endsWith(`,${name}`)) {
      const city = s.slice(0, s.length - name.length).replace(/[,\s]+$/, "");
      if (city) return { city: cityKey(city), state: STATE_BY_NAME[name] };
    }
  }
  return null;
}

async function geocode(env, origin, place, index) {
  const s = String(place).trim();
  let m = s.match(/^(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)$/);
  if (m) return { lat: +m[1], lng: +m[2], label: s };

  m = s.match(/^(\d{5})(?:-\d{4})?$/);
  if (m) {
    const zips = await loadJSON(env, origin, "/data/zips.json", { pin: true });
    const c = zips && zips[m[1]];
    return c ? { lat: c[0], lng: c[1], label: `ZIP ${m[1]}` } : null;
  }

  const cities = await loadJSON(env, origin, "/data/all_cities.json", { pin: true });
  if (!cities) return null;
  // "Denver, CO", "San Diego CA", "Saint Louis, Missouri", or just "Denver".
  const split = splitCityState(s);
  if (split) {
    const c = cities[`${split.city}|${split.state}`] || cities[`${split.city.replace(/^st\. /, "saint ")}|${split.state}`];
    if (c) return { lat: c[0], lng: c[1], label: `${titleCase(split.city)}, ${split.state}`, state: split.state };
  }
  // City without a state: prefer the state with the largest incorporated
  // place of that name (Denver -> CO), else the state with the most jobs.
  const city = cityKey(s.replace(/,.*$/, ""));
  const hints = await loadJSON(env, origin, "/data/city_hints.json", { pin: true });
  const hinted = hints && hints[city];
  if (hinted && cities[`${city}|${hinted}`]) {
    const c = cities[`${city}|${hinted}`];
    return { lat: c[0], lng: c[1], label: `${s}, ${hinted}`, state: hinted, assumed_state: true };
  }
  let best = null;
  for (const st of Object.keys(STATES)) {
    const c = cities[`${city}|${st}`];
    if (c) {
      const jobs = index.state_counts[st] || 0;
      if (!best || jobs > best.jobs) best = { lat: c[0], lng: c[1], state: st, jobs };
    }
  }
  return best
    ? { lat: best.lat, lng: best.lng, label: `${s}, ${best.state}`, state: best.state, assumed_state: true }
    : null;
}

function milesBetween(a, b) {
  const R = 3958.8;
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(h));
}

// States whose job bounding box comes within `miles` of the point.
function statesNear(index, pt, miles) {
  const dLat = miles / 69;
  const dLng = miles / (69 * Math.max(Math.cos((pt.lat * Math.PI) / 180), 0.2));
  const out = [];
  for (const [name, meta] of Object.entries(index.shards)) {
    if (!name.startsWith("state/") || !meta.bbox) continue;
    const [minLat, minLng, maxLat, maxLng] = meta.bbox;
    if (
      pt.lat + dLat >= minLat &&
      pt.lat - dLat <= maxLat &&
      pt.lng + dLng >= minLng &&
      pt.lng - dLng <= maxLng
    ) {
      out.push(name.slice(6));
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------

function expand(rec, keys) {
  const out = {};
  for (const [full, short] of Object.entries(keys)) {
    if (rec[short] !== undefined) out[full] = rec[short];
  }
  if (out.title) out.title = out.title.replace(/\s+/g, " ").trim();
  for (const k of ["remote", "weekend", "compact_license", "new_grad_ok"]) {
    if (out[k] !== undefined) out[k] = Boolean(out[k]);
  }
  return out;
}

function formatPay(job) {
  const lo = job.hourly_min;
  const hi = job.hourly_max;
  if (lo == null && hi == null) return null;
  const f = (n) => `$${Number(n).toFixed(n % 1 ? 2 : 0)}`;
  return lo === hi || hi == null ? `${f(lo)}/hr` : `${f(lo)}–${f(hi)}/hr`;
}

// One line an assistant can read out or show as-is.
function summarize(job) {
  let s = job.title;
  const where = [job.company, job.location].filter(Boolean).join(", ");
  if (where) s += ` — ${where}`;
  const details = [];
  const pay = formatPay(job);
  if (pay) details.push(pay);
  if (job.employment_type) details.push(job.employment_type.replace("_", "-"));
  if (job.shift && job.shift !== "prn") details.push(`${job.shift.replace(/s$/, "")} shift`);
  if (job.shift_hours) details.push(`${job.shift_hours}-hour shifts`);
  if (job.sign_on_bonus) details.push(`$${job.sign_on_bonus.toLocaleString("en-US")} sign-on bonus`);
  if (job.posted_date) details.push(`posted ${job.posted_date}`);
  return details.length ? `${s}. ${details.join("; ")}.` : `${s}.`;
}

function publicJob(job, labels, distance) {
  const out = {
    id: job.id,
    summary: summarize(job),
    title: job.title,
    company: job.company,
    location: job.location,
    state: job.state,
    remote: job.remote || undefined,
    distance_miles: distance != null ? Math.round(distance * 10) / 10 : undefined,
    role: job.role,
    role_label: labels.roles[job.role],
    level: job.level,
    specialties: job.specialties,
    setting: job.setting,
    employment_type: job.employment_type,
    shift: job.shift,
    shift_hours: job.shift_hours,
    pay: formatPay(job)
      ? {
          hourly_min: job.hourly_min,
          hourly_max: job.hourly_max,
          annual_min: job.hourly_min != null ? Math.round(job.hourly_min * 2080) : undefined,
          annual_max: job.hourly_max != null ? Math.round(job.hourly_max * 2080) : undefined,
          display: formatPay(job),
          // Always the employer's own posted figure (an ATS pay field or the
          // range in the posting text). Never estimated by ScrubShifts.
          source: "employer_posting",
          estimated: false,
        }
      : undefined,
    sign_on_bonus_usd: job.sign_on_bonus,
    requirements: {
      certifications_mentioned: job.certifications,
      compact_license_accepted: job.compact_license,
      min_years_experience: job.min_years_experience,
      new_grad_ok: job.new_grad_ok,
      bsn: job.bsn,
    },
    location_precision: job.location_precision,
    posted_date: job.posted_date,
    first_seen: job.first_seen,
    last_verified: job.last_verified,
    status: "active",
    sponsored: false,
    also_listed_as: job.duplicate_ids,
    listing_url: job.slug ? `${SITE}/listing/${job.slug}/` : undefined,
    apply_url: job.apply_url,
  };
  if (Object.values(out.requirements).every((v) => v === undefined)) delete out.requirements;
  return JSON.parse(JSON.stringify(out));
}

// sort=best, published in the API docs: 2 points for listed pay, minus 1 point
// per week since posting (or first seen), minus 1 point per 10 miles away.
function bestScore(hit, now) {
  const job = hit.job;
  const d = Date.parse(job.posted_date || job.first_seen || "") || now;
  let score = (job.hourly_min != null ? 2 : 0) - Math.max(0, now - d) / (7 * 86400000);
  if (hit.dist != null) score -= hit.dist / 10;
  return score;
}

function matches(job, q, now) {
  if (q.role && !q.role.includes(job.role)) return false;
  if (q.specialty && !(job.specialties || []).some((s) => q.specialty.includes(s))) return false;
  if (q.setting && !q.setting.includes(job.setting)) return false;
  if (q.employment_type && !q.employment_type.includes(job.employment_type)) return false;
  if (q.shift && !q.shift.includes(job.shift)) return false;
  if (q.remote && !job.remote) return false;
  if (q.state && job.state !== q.state) return false;
  if (q.has_pay && job.hourly_min == null) return false;
  if (q.min_hourly != null && !((job.hourly_max ?? -1) >= q.min_hourly)) return false;
  if (q.min_annual != null && !((job.hourly_max ?? -1) * 2080 >= q.min_annual)) return false;
  if (q.new_grad && !(job.new_grad_ok === true || job.level === "new_grad")) return false;
  if (q.compact_license && !job.compact_license) return false;
  if (q.max_years_experience != null && job.min_years_experience != null &&
      job.min_years_experience > q.max_years_experience) return false;
  if (q.posted_after && !(job.posted_date && Date.parse(job.posted_date) >= Date.parse(q.posted_after))) return false;
  // Strictly after, so passing a previous data_as_of never returns that
  // data set's jobs again.
  if (q.first_seen_after && !(job.first_seen && Date.parse(job.first_seen) > Date.parse(q.first_seen_after))) return false;
  if (q.posted_within_days != null) {
    const d = job.posted_date || job.first_seen;
    if (!d || now - Date.parse(d) > q.posted_within_days * 86400000) return false;
  }
  if (q.q) {
    const hay = `${job.title} ${job.company || ""} ${job.location || ""}`.toLowerCase();
    for (const tok of q.q.toLowerCase().split(/\s+/).filter(Boolean)) {
      if (!hay.includes(tok)) return false;
    }
  }
  return true;
}

function pickShards(q, index, point) {
  const has = (n) => Boolean(index.shards[n]);
  if (q.remote) return { shards: has("remote") ? ["remote"] : [], scope: "remote" };
  if (point) {
    const states = statesNear(index, point, q.radius_miles);
    if (point.state && !states.includes(point.state) && has(`state/${point.state}`)) states.push(point.state);
    return { shards: states.map((s) => `state/${s}`).filter(has), scope: "radius" };
  }
  if (q.state) return { shards: has(`state/${q.state}`) ? [`state/${q.state}`] : [], scope: "state" };
  // "New since" with no location: the recent shard holds every job published
  // in its window (index.shards["national/_recent"].since), uncapped.
  const recent = index.shards["national/_recent"];
  if (q.first_seen_after && recent && Date.parse(q.first_seen_after) >= Date.parse(recent.since)) {
    return { shards: ["national/_recent"], scope: "national_recent" };
  }
  if (q.role && q.role.length > 1 && q.role.length <= 4 && q.role.every((r) => has(`national/${r}`))) {
    return { shards: q.role.map((r) => `national/${r}`), scope: "national" };
  }
  if (q.role && q.role.length === 1) {
    const role = q.role[0];
    if (q.specialty && q.specialty.length === 1 && has(`national/${role}__${q.specialty[0]}`)) {
      return { shards: [`national/${role}__${q.specialty[0]}`], scope: "national" };
    }
    if (has(`national/${role}`)) return { shards: [`national/${role}`], scope: "national" };
    return { shards: [], scope: "national" };
  }
  return { shards: ["national/_all"], scope: "national" };
}

function taxonomyLabels(index) {
  return {
    roles: Object.fromEntries(index.taxonomy.roles.map((r) => [r.slug, r.label])),
  };
}

async function searchJobs(env, origin, input) {
  const index = await loadIndex(env, origin);
  if (!index) return { error: "Job data is temporarily unavailable." };
  const { q, errors } = parseQuery(input, index);
  if (errors.length) return { error: errors.join(" "), query: q };

  let point = null;
  if (q.near && !q.remote) {
    point = await geocode(env, origin, q.near, index);
    if (!point) {
      return {
        error: `Could not locate "${q.near}". Use "City, ST", a 5-digit ZIP, or "lat,lng".`,
        query: q,
      };
    }
  }
  const { shards, scope } = pickShards(q, index, point);
  const labels = taxonomyLabels(index);
  const now = Date.now();
  const hits = [];
  let truncated = false;
  let skippedNoCoords = 0;
  const seen = new Set();
  for (const name of shards) {
    truncated = truncated || index.shards[name].truncated;
    const rows = (await loadJSON(env, origin, `/data/agent/shards/${name}.json`)) || [];
    for (const row of rows) {
      const job = expand(row, index.keys);
      if (seen.has(job.id) || !matches(job, q, now)) continue;
      let dist = null;
      if (point) {
        if (job.lat == null) {
          skippedNoCoords++;
          continue;
        }
        dist = milesBetween(point, job);
        if (dist > q.radius_miles) continue;
      }
      // The same posting often arrives under several employer names (a health
      // system and its hospital); keep the first copy.
      const dupKey = `${job.title}|${job.location}|${job.hourly_min}|${job.hourly_max}`
        .toLowerCase()
        .replace(/\s+/g, " ");
      if (seen.has(dupKey)) continue;
      seen.add(job.id);
      seen.add(dupKey);
      hits.push({ job, dist });
    }
  }

  const sort = q.sort || (point ? "distance" : "best");
  const recency = (h) => h.job.posted_date || h.job.first_seen || "";
  const byRecency = (a, b) => (recency(b) > recency(a) ? 1 : recency(b) < recency(a) ? -1 : 0);
  const byId = (a, b) => (a.job.id < b.job.id ? -1 : a.job.id > b.job.id ? 1 : 0);
  if (sort === "distance" && point) hits.sort((a, b) => a.dist - b.dist || byRecency(a, b) || byId(a, b));
  else if (sort === "pay") hits.sort((a, b) => (b.job.hourly_max ?? -1) - (a.job.hourly_max ?? -1) || byRecency(a, b) || byId(a, b));
  else if (sort === "newest") hits.sort((a, b) => byRecency(a, b) || byId(a, b));
  else hits.sort((a, b) => bestScore(b, now) - bestScore(a, now) || byRecency(a, b) || byId(a, b));

  const page = hits.slice(q.offset, q.offset + q.limit);
  const notes = [];
  if (truncated) {
    notes.push(
      scope === "national_recent"
        ? "Very many jobs were published in this window; results include the most recently published. Add a state or near= location for complete coverage."
        : "National results are drawn from the newest jobs for this role. Add a state or near= location for complete coverage.",
    );
  }
  if (point && point.assumed_state) notes.push(`Interpreted location as ${point.label}.`);
  if (skippedNoCoords) {
    notes.push(`${skippedNoCoords} matching jobs in the area have no mappable city and were left out of the radius search; search by state to include them.`);
  }
  if (!hits.length) {
    notes.push("No matches. Try a wider radius_miles, fewer filters, or a nearby city.");
  }
  return {
    query: { ...q, sort, near_resolved: point ? { lat: point.lat, lng: point.lng, label: point.label } : undefined },
    total_matches: hits.length,
    returned: page.length,
    offset: q.offset,
    next_offset: q.offset + page.length < hits.length ? q.offset + page.length : null,
    coverage: { scope, complete: !truncated, notes },
    policies: POLICIES,
    data_as_of: index.generated_at,
    results: page.map((h) => publicJob(h.job, labels, h.dist)),
    attribution: ATTRIBUTION,
  };
}

function safeChar(code) {
  return code > 0 && code < 0x110000 ? String.fromCodePoint(code) : " ";
}

async function getJob(env, origin, id) {
  const jid = String(id || "").trim().toLowerCase().replace(/.*-/, "").replace(/\/$/, "");
  if (!/^[0-9a-f]{12}$/.test(jid)) return { error: "id must be the 12-character job id from search results." };
  const index = await loadIndex(env, origin);
  const chunk = await loadJSON(env, origin, `/data/jobs/${jid.slice(0, 2)}.json`);
  const detail = chunk && chunk[jid];
  if (!detail) {
    return { error: "No live job with that id. It may have been filled or removed; search again for current openings." };
  }
  const labels = index ? taxonomyLabels(index) : { roles: {} };
  const base = detail.agent ? { ...detail.agent, title: (detail.agent.title || "").replace(/\s+/g, " ").trim() } : {
    id: jid,
    title: detail.title,
    company: detail.company_name,
    location: detail.location,
    state: detail.state,
    shift: detail.shift,
    posted_date: detail.posted_date,
    slug: detail.slug,
    apply_url: detail.url,
  };
  const desc = (detail.description_html || "")
    .replace(/<(script|style)[\s\S]*?<\/\1>/gi, " ")
    .replace(/<\/(p|div|li|h\d)>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n")
    .replace(/<[^>]+>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&#39;|&apos;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&#(\d+);/g, (_, n) => safeChar(Number(n)))
    .replace(/&#x([0-9a-f]+);/gi, (_, n) => safeChar(parseInt(n, 16)))
    .replace(/&amp;/g, "&")
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s*\n+/g, "\n")
    .trim();
  return {
    job: {
      ...publicJob(base, labels, null),
      description: desc.length > 6000 ? `${desc.slice(0, 6000)}…` : desc,
      similar_jobs: (detail.similar || []).map((s) => ({
        title: s.title,
        company: s.company_name,
        location: s.location,
        listing_url: `${SITE}/listing/${s.slug}/`,
      })),
    },
    data_as_of: index ? index.generated_at : undefined,
    attribution: ATTRIBUTION,
  };
}

async function payBenchmarks(env, origin, input) {
  const index = await loadIndex(env, origin);
  const pay = await loadJSON(env, origin, "/data/agent/pay.json", { pin: true });
  if (!index || !pay) return { error: "Pay data is temporarily unavailable." };
  const errors = [];
  const roles = resolveList(input.role, aliasMap(index.taxonomy.roles), "role", errors);
  const specs = resolveList(input.specialty, aliasMap(index.taxonomy.specialties), "specialty", errors);
  const state = input.state ? resolveState(input.state) : null;
  if (input.state && !state) errors.push(`Unknown state "${input.state}".`);
  if (!roles) errors.push("role is required (for example rn, lpn, nurse_practitioner).");
  if (errors.length) return { error: errors.join(" ") };
  const metro = input.metro ? norm(input.metro).replace(/\s+/g, "-") : null;
  const role = roles[0];
  const spec = specs ? specs[0] : null;
  const pick = (rows, f) => rows.filter((r) => r.role === role && f(r));
  const result = { role, national: pick(pay.national, () => true)[0] || null };
  if (state) result.state = pick(pay.state, (r) => r.state === state)[0] || null;
  if (metro) result.metro = pick(pay.metro, (r) => r.metro === metro || r.metro.startsWith(metro))[0] || null;
  if (spec) {
    result.specialty = pick(pay.specialty, (r) => r.specialty === spec)[0] || null;
    if (state) result.specialty_state = pick(pay.specialty_state, (r) => r.specialty === spec && r.state === state)[0] || null;
  }
  return {
    ...result,
    method:
      "Midpoint of each live posting's listed pay range, in USD per hour (annual = hourly × 2080). " +
      "Only groups with at least 5 postings that list pay are published. Postings without pay are excluded.",
    data_as_of: pay.generated_at,
    attribution: ATTRIBUTION,
  };
}

async function listFilters(env, origin) {
  const index = await loadIndex(env, origin);
  if (!index) return { error: "Job data is temporarily unavailable." };
  const t = index.taxonomy;
  return {
    roles: t.roles.map((r) => ({ ...r, jobs: index.role_counts[r.slug] || 0 })),
    specialties: t.specialties,
    settings: t.settings,
    employment_types: Object.entries(EMPLOYMENT_ALIASES).map(([slug, aliases]) => ({ slug, aliases })),
    shifts: Object.entries(SHIFT_ALIASES).map(([slug, aliases]) => ({ slug, aliases })),
    levels: t.levels,
    states: index.state_counts,
    total_jobs: index.total_jobs,
    data_as_of: index.generated_at,
  };
}

// ---------------------------------------------------------------------------
// MCP (Streamable HTTP, stateless JSON responses)
// ---------------------------------------------------------------------------

const SEARCH_PROPS = {
  near: { type: "string", description: 'Where the person wants to work: "City, ST", a 5-digit ZIP, or "lat,lng". Results are sorted by distance.' },
  radius_miles: { type: "number", description: `Search radius around near, default ${DEFAULT_RADIUS}, max ${MAX_RADIUS}.` },
  state: { type: "string", description: "Two-letter US state code, e.g. CO. Use instead of near for a statewide search." },
  role: { type: "string", description: "Role slug or common name, comma-separated for several: rn, lpn, cna, nurse_practitioner, crna, physical_therapist, respiratory_therapist, medical_assistant, … (see list_filters)." },
  specialty: { type: "string", description: "Unit or specialty, comma-separated: icu, emergency, labor_delivery, nicu, med_surg, telemetry, operating_room, oncology, psych, pediatrics, home_health, hospice, dialysis, … Common words like ER, L&D, tele, peds work." },
  setting: { type: "string", description: "Care setting: hospital, clinic, skilled_nursing, home_health, hospice, dialysis_center, telehealth, urgent_care, school, correctional, ambulatory_surgery." },
  employment_type: { type: "string", description: "full_time, part_time, prn (per diem), contract, travel, temporary, internship." },
  shift: { type: "string", description: "days, nights, evenings, rotating, weekends." },
  min_hourly: { type: "number", description: "Minimum hourly pay in USD; matches jobs whose listed range reaches it. Implies has_pay." },
  min_annual: { type: "number", description: "Minimum annual pay in USD." },
  has_pay: { type: "boolean", description: "Only jobs that list pay." },
  new_grad: { type: "boolean", description: "Only jobs open to new graduates (residencies, 'new grads welcome', no experience required)." },
  compact_license: { type: "boolean", description: "Only jobs that mention accepting a compact (multistate) nursing license." },
  max_years_experience: { type: "number", description: "The person's years of experience; excludes jobs that state a higher minimum." },
  remote: { type: "boolean", description: "Only remote / telehealth jobs." },
  posted_within_days: { type: "number", description: "Only jobs posted in the last N days." },
  posted_after: { type: "string", description: "Only jobs the employer posted on or after this ISO date/time." },
  first_seen_after: { type: "string", description: "Only jobs that first appeared on ScrubShifts on or after this ISO time. For recurring checks, pass the previous response's data_as_of to get just the new jobs." },
  q: { type: "string", description: "Free-text words that must appear in the title, employer or location, e.g. an employer name." },
  sort: { type: "string", enum: SORTS, description: "best (default): +2 if pay is listed, -1 per week since posting, -1 per 10 miles. Or newest, pay, distance (default when near is set). No paid placement affects ordering." },
  limit: { type: "number", description: `Results per page, default ${DEFAULT_LIMIT}, max ${MAX_LIMIT}.` },
  offset: { type: "number", description: "Pagination offset; use next_offset from the previous response." },
};

const TOOLS = [
  {
    name: "search_jobs",
    title: "Search healthcare jobs",
    description:
      "Search live US nursing and allied-health job openings by location, role, specialty, shift, pay and requirements. " +
      "Data is refreshed daily from employer career sites. Each result has a one-line summary, structured pay, " +
      "a listing_url to show the person, and an apply_url that goes straight to the employer.",
    inputSchema: { type: "object", properties: SEARCH_PROPS, additionalProperties: false },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  {
    name: "get_job",
    title: "Get job details",
    description: "Full details for one job from search_jobs: description text, requirements, pay, apply link and similar jobs.",
    inputSchema: {
      type: "object",
      properties: { id: { type: "string", description: "Job id from search_jobs results." } },
      required: ["id"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  {
    name: "get_pay_benchmarks",
    title: "Get pay benchmarks",
    description:
      "Typical posted hourly pay (25th percentile, median, 75th percentile) for a healthcare role nationally and, optionally, " +
      "in a state, metro or specialty. Use it to tell someone whether an offer is competitive.",
    inputSchema: {
      type: "object",
      properties: {
        role: SEARCH_PROPS.role,
        state: SEARCH_PROPS.state,
        metro: { type: "string", description: "Metro slug, e.g. denver, dallas-fort-worth, los-angeles." },
        specialty: SEARCH_PROPS.specialty,
      },
      required: ["role"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
  {
    name: "list_filters",
    title: "List search filters",
    description: "Valid roles, specialties, settings, employment types and shifts (with aliases and job counts) for search_jobs.",
    inputSchema: { type: "object", properties: {}, additionalProperties: false },
    annotations: { readOnlyHint: true, openWorldHint: false },
  },
];

const MCP_INSTRUCTIONS =
  "ScrubShifts lists live US healthcare jobs (nurses, nurse practitioners, CNAs, therapists, techs and more), " +
  "refreshed daily from employer career sites. Use search_jobs with the person's location (near), role and any " +
  "preferences such as specialty, shift, pay or new-grad status. Show each job's summary with its listing_url. " +
  "Use get_pay_benchmarks to judge whether pay is competitive. Never invent jobs that the tools did not return.";

async function callTool(env, origin, name, args) {
  switch (name) {
    case "search_jobs":
      return searchJobs(env, origin, args || {});
    case "get_job":
      return getJob(env, origin, (args || {}).id);
    case "get_pay_benchmarks":
      return payBenchmarks(env, origin, args || {});
    case "list_filters":
      return listFilters(env, origin);
    default:
      return null;
  }
}

function rpcResult(id, result) {
  return { jsonrpc: "2.0", id, result };
}
function rpcError(id, code, message) {
  return { jsonrpc: "2.0", id: id ?? null, error: { code, message } };
}

async function handleRpc(env, origin, msg, log) {
  // A client may POST a JSON-RPC response (to a server request); we never
  // send requests, so just acknowledge it.
  if (msg && msg.jsonrpc === "2.0" && msg.method === undefined && ("result" in msg || "error" in msg)) {
    return null;
  }
  if (!msg || msg.jsonrpc !== "2.0" || typeof msg.method !== "string") {
    return rpcError(msg && msg.id, -32600, "Invalid Request");
  }
  const isNotification = msg.id === undefined || msg.id === null;
  const method = msg.method;
  const params = msg.params && typeof msg.params === "object" ? msg.params : {};
  if (isNotification) return null;

  switch (method) {
    case "initialize": {
      const requested = params.protocolVersion;
      return rpcResult(msg.id, {
        protocolVersion: MCP_PROTOCOL_VERSIONS.includes(requested) ? requested : MCP_PROTOCOL_VERSIONS[0],
        capabilities: { tools: { listChanged: false } },
        serverInfo: { name: "scrubshifts", title: "ScrubShifts Healthcare Jobs", version: SERVER_VERSION },
        instructions: MCP_INSTRUCTIONS,
      });
    }
    case "ping":
      return rpcResult(msg.id, {});
    case "tools/list":
      return rpcResult(msg.id, { tools: TOOLS });
    case "tools/call": {
      const tool = TOOLS.find((t) => t.name === params.name);
      if (!tool) return rpcError(msg.id, -32602, `Unknown tool: ${params.name}`);
      log.tool = tool.name;
      log.args = params.arguments;
      const out = await callTool(env, origin, tool.name, params.arguments || {});
      const isError = Boolean(out && out.error);
      return rpcResult(msg.id, {
        content: [{ type: "text", text: JSON.stringify(out) }],
        structuredContent: out,
        isError,
      });
    }
    case "resources/list":
      return rpcResult(msg.id, { resources: [] });
    case "prompts/list":
      return rpcResult(msg.id, { prompts: [] });
    default:
      return rpcError(msg.id, -32601, `Method not found: ${method}`);
  }
}

async function handleMcp(request, env, origin, log) {
  if (request.method === "GET" || request.method === "DELETE") {
    // Stateless server: no server-initiated stream and no sessions to end.
    return new Response(null, { status: 405, headers: { ...CORS, Allow: "POST, OPTIONS" } });
  }
  if (request.method !== "POST") {
    return new Response(null, { status: 405, headers: { ...CORS, Allow: "POST, OPTIONS" } });
  }
  let body;
  try {
    body = await request.json();
  } catch {
    return json(rpcError(null, -32700, "Parse error"), 400);
  }
  const batch = Array.isArray(body);
  if (batch && !body.length) return json(rpcError(null, -32600, "Invalid Request"), 200, { "Cache-Control": "no-store" });
  const msgs = batch ? body : [body];
  log.rpc = msgs.map((m) => m && m.method).filter(Boolean);
  const replies = [];
  for (const m of msgs) {
    let r;
    try {
      r = await handleRpc(env, origin, m, log);
    } catch (err) {
      log.error = String((err && err.message) || err);
      r = m && m.id != null ? rpcError(m.id, -32603, "Internal error") : null;
    }
    if (r) replies.push(r);
  }
  if (!replies.length) return new Response(null, { status: 202, headers: CORS });
  return json(batch ? replies : replies[0], 200, { "Cache-Control": "no-store" });
}

// ---------------------------------------------------------------------------
// REST
// ---------------------------------------------------------------------------

function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data, null, 0), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "public, max-age=300",
      ...CORS,
      ...extra,
    },
  });
}

async function handleApi(request, env, url, log) {
  const origin = url.origin;
  const path = url.pathname.replace(/\/+$/, "") || "/";
  const params = Object.fromEntries(url.searchParams.entries());
  const { secret: _ignored, ...loggable } = params;
  log.params = loggable;

  if (path === "/api" || path === "/api/v1") {
    const index = await loadIndex(env, origin);
    return json({
      name: "ScrubShifts Healthcare Jobs API",
      description: "Live US nursing and allied-health job openings, refreshed daily. Free, no key required.",
      data_as_of: index && index.generated_at,
      total_jobs: index && index.total_jobs,
      coverage: index && {
        jobs_with_posted_pay: index.jobs_with_pay,
        jobs_with_coordinates: index.jobs_with_coords,
        duplicates_merged: index.duplicates_merged,
        states: Object.keys(index.state_counts || {}).length,
      },
      policies: POLICIES,
      endpoints: {
        search: `${SITE}/api/v1/jobs?near=Denver,CO&role=rn&specialty=icu&shift=nights&min_hourly=50`,
        job: `${SITE}/api/v1/jobs/{id}`,
        pay: `${SITE}/api/v1/pay?role=rn&state=CO&specialty=icu`,
        taxonomy: `${SITE}/api/v1/taxonomy`,
        bulk: `${SITE}/data/agent/jobs.ndjson.gz`,
        openapi: `${SITE}/openapi.json`,
        mcp: `${SITE}/mcp`,
        skill: `${SITE}/skills/scrubshifts-jobs/SKILL.md`,
        api_catalog: `${SITE}/.well-known/api-catalog`,
        saved_search: `POST ${SITE}/api/v1/subscriptions {"webhook_url": "https://...", "query": {"near": "Cerritos, CA", "role": "rn", "specialty": "telemetry", "shift": "nights"}}`,
      },
      attribution: ATTRIBUTION,
    });
  }
  if (path === "/api/v1/jobs") {
    const out = await searchJobs(env, origin, params);
    return json(out, out.error ? 400 : 200);
  }
  const m = path.match(/^\/api\/v1\/jobs\/([^/]+)$/);
  if (m) {
    let id;
    try {
      id = decodeURIComponent(m[1]);
    } catch {
      return json({ error: "Malformed job id." }, 404);
    }
    const out = await getJob(env, origin, id);
    return json(out, out.error ? 404 : 200);
  }
  if (path === "/api/v1/pay") {
    const out = await payBenchmarks(env, origin, params);
    return json(out, out.error ? 400 : 200);
  }
  if (path === "/api/v1/subscriptions") {
    if (request.method !== "POST") return json({ error: "POST a saved search here." }, 405, { Allow: "POST, OPTIONS" });
    return createSubscription(request, env, origin);
  }
  const sm = path.match(/^\/api\/v1\/subscriptions\/([0-9a-f]{24})$/);
  if (sm) {
    if (!["GET", "DELETE"].includes(request.method)) return json({ error: "Use GET or DELETE." }, 405, { Allow: "GET, DELETE, OPTIONS" });
    return subscriptionById(request, env, sm[1]);
  }
  if (path === "/api/v1/taxonomy") {
    const out = await listFilters(env, origin);
    return json(out, out.error ? 503 : 200);
  }
  return json({ error: "Not found. See https://scrubshifts.com/api/v1 for endpoints." }, 404);
}

// ---------------------------------------------------------------------------
// Traffic logging: one structured line per agent request (and per AI crawler
// page fetch) so Cloudflare logs show who reads the data and what they ask.
// ---------------------------------------------------------------------------

const AI_AGENTS = [
  ["GPTBot", "openai"], ["OAI-SearchBot", "openai"], ["ChatGPT-User", "openai"],
  ["ClaudeBot", "anthropic"], ["Claude-User", "anthropic"], ["Claude-SearchBot", "anthropic"],
  ["anthropic-ai", "anthropic"], ["PerplexityBot", "perplexity"], ["Perplexity-User", "perplexity"],
  ["Google-Extended", "google"], ["Google-CloudVertexBot", "google"], ["Gemini", "google"],
  ["Applebot-Extended", "apple"], ["Applebot", "apple"], ["meta-externalagent", "meta"],
  ["Meta-ExternalFetcher", "meta"], ["bingbot", "microsoft"], ["CCBot", "commoncrawl"],
  ["Amazonbot", "amazon"], ["Bytespider", "bytedance"], ["DuckAssistBot", "duckduckgo"],
  ["MistralAI-User", "mistral"], ["cohere-ai", "cohere"], ["YouBot", "you"],
];

export function aiAgentFamily(ua) {
  const s = ua || "";
  for (const [needle, family] of AI_AGENTS) {
    if (s.includes(needle)) return { agent: needle, family };
  }
  return null;
}

// Durable usage counts in Workers Analytics Engine (binding AGENT_METRICS in
// wrangler.toml). One data point per request; a no-op without the binding.
// blobs: kind, path, detail (MCP tool / method), AI family, status, query
// summary (role/specialty/state only — never free text or locations).
export function recordMetric(env, m) {
  try {
    if (!env || !env.AGENT_METRICS) return;
    const q = m.query || {};
    const summary = ["role", "specialty", "state", "shift", "employment_type"]
      .filter((k) => q[k])
      .map((k) => `${k}=${String(q[k]).slice(0, 40)}`)
      .join("&");
    env.AGENT_METRICS.writeDataPoint({
      indexes: [m.kind],
      blobs: [m.kind, m.path.slice(0, 100), m.detail.slice(0, 100), m.family, String(m.status), summary],
      doubles: [1],
    });
  } catch {
    // Metrics must never break a response.
  }
}

export function isAgentPath(pathname) {
  return (
    pathname === "/mcp" ||
    pathname === "/api" ||
    pathname === "/api/v1" ||
    pathname.startsWith("/api/v1/") ||
    pathname === "/.well-known/api-catalog"
  );
}

// ---------------------------------------------------------------------------
// Saved searches with webhooks. Stored in the SUBSCRIBERS KV namespace under
// "webhook:<id>". After each data refresh, pipeline/notify_subscriptions.py
// runs every saved search with first_seen_after = last notification time and
// POSTs new jobs to the webhook, signed with HMAC-SHA256 using the secret
// returned at creation (header X-ScrubShifts-Signature: sha256=<hex>).
// ---------------------------------------------------------------------------

const MAX_SUBSCRIPTIONS = 1000;
const CREATES_PER_IP_PER_DAY = 5;
const SUBSCRIPTION_TTL_DAYS = 90;
// Search keys a saved search keeps, in their canonical (parsed) form.
const SAVED_KEYS = [
  "role", "specialty", "setting", "employment_type", "shift", "q", "state", "near",
  "radius_miles", "min_hourly", "min_annual", "has_pay", "new_grad", "compact_license",
  "remote", "max_years_experience",
];

// Webhook hosts must be DNS names. IP literals (v4 or v6, any notation) and
// internal names are refused here; the notifier also re-checks the resolved
// address before every delivery.
function badWebhookHost(hostname) {
  const h = hostname.toLowerCase();
  if (h.startsWith("[") || h.includes(":")) return true; // IPv6 literal
  if (/^[0-9.]+$/.test(h) || /^0x/i.test(h)) return true; // IPv4 literal / hex
  if (!h.includes(".")) return true;
  return /(^|\.)(localhost|local|internal|intranet|lan|home|corp|localdomain)$/.test(h);
}

function randomHex(bytes) {
  const a = new Uint8Array(bytes);
  crypto.getRandomValues(a);
  return [...a].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Saved query: the parsed, normalized search (aliases resolved, lists as
// comma-separated strings) so delivery runs exactly the search that was asked.
function savedQuery(q) {
  const out = {};
  for (const k of SAVED_KEYS) {
    if (q[k] == null) continue;
    out[k] = Array.isArray(q[k]) ? q[k].join(",") : q[k];
  }
  if (!out.near) delete out.radius_miles;
  return out;
}

async function createSubscription(request, env, origin) {
  if (!env.SUBSCRIBERS) return json({ error: "Saved searches are temporarily unavailable." }, 503);
  let body;
  try {
    body = await request.json();
  } catch {
    return json({ error: "Body must be JSON: {\"webhook_url\": \"https://...\", \"query\": {search parameters}}" }, 400);
  }
  let hookUrl;
  try {
    hookUrl = new URL(String((body && body.webhook_url) || ""));
  } catch {
    return json({ error: "webhook_url must be an https URL." }, 400);
  }
  if (hookUrl.protocol !== "https:" || hookUrl.username || hookUrl.password || badWebhookHost(hookUrl.hostname)) {
    return json({ error: "webhook_url must be a public https URL with a DNS host name." }, 400);
  }
  const index = await loadIndex(env, origin);
  if (!index) return json({ error: "Job data is temporarily unavailable." }, 503);
  const { q, errors } = parseQuery((body && body.query) || {}, index);
  if (errors.length) return json({ error: errors.join(" ") }, 400);
  if (q.near && !q.remote && !(await geocode(env, origin, q.near, index))) {
    return json({ error: `Could not locate "${q.near}". Use "City, ST", a 5-digit ZIP, or "lat,lng".` }, 400);
  }

  // Abuse limits: a few creations per IP per day, and a global cap tracked in
  // one counter key (approximate under KV's eventual consistency, which is fine
  // for a cap). Subscriptions expire after SUBSCRIPTION_TTL_DAYS.
  const ip = request.headers.get("CF-Connecting-IP") || "unknown";
  const day = new Date().toISOString().slice(0, 10);
  const rlKey = `rl:${ip}:${day}`;
  const used = Number((await env.SUBSCRIBERS.get(rlKey)) || 0);
  if (used >= CREATES_PER_IP_PER_DAY) {
    return json({ error: "Too many saved searches created today. Poll with first_seen_after instead." }, 429);
  }
  const count = Number((await env.SUBSCRIBERS.get("meta:webhook_count")) || 0);
  if (count >= MAX_SUBSCRIPTIONS) {
    return json({ error: "Saved-search capacity is full right now. Poll with first_seen_after instead." }, 503);
  }

  const id = randomHex(12);
  const secret = randomHex(24);
  const ttl = SUBSCRIPTION_TTL_DAYS * 86400;
  const sub = {
    id,
    webhook_url: hookUrl.toString(),
    query: savedQuery(q),
    secret,
    created_at: new Date().toISOString(),
    expires_at: new Date(Date.now() + ttl * 1000).toISOString(),
    // Delivery starts with jobs published after the current data set.
    start_after: index.generated_at,
  };
  await env.SUBSCRIBERS.put(`webhook:${id}`, JSON.stringify(sub), { expirationTtl: ttl });
  await env.SUBSCRIBERS.put(rlKey, String(used + 1), { expirationTtl: 2 * 86400 });
  await env.SUBSCRIBERS.put("meta:webhook_count", String(count + 1));
  return json(
    {
      id,
      secret,
      query: sub.query,
      webhook_url: sub.webhook_url,
      expires_at: sub.expires_at,
      delivery:
        "After each data refresh (several times a day), new matching jobs are POSTed as JSON " +
        "{subscription_id, data_as_of, jobs:[...]} with header X-ScrubShifts-Signature: sha256=HMAC_SHA256(secret, body). " +
        "Respond 2xx; 10 consecutive failures remove the subscription. Create it again to renew after expires_at.",
      manage: `${SITE}/api/v1/subscriptions/${id}`,
      note: "Keep the secret: it verifies deliveries and is required (header X-Subscription-Secret) to view or delete this subscription.",
    },
    201,
    { "Cache-Control": "no-store" },
  );
}

async function subscriptionById(request, env, id) {
  if (!env.SUBSCRIBERS) return json({ error: "Saved searches are temporarily unavailable." }, 503);
  const raw = await env.SUBSCRIBERS.get(`webhook:${id}`);
  const sub = raw && JSON.parse(raw);
  const given = request.headers.get("X-Subscription-Secret");
  if (!sub || !given || given !== sub.secret) {
    return json({ error: "Not found." }, 404, { "Cache-Control": "no-store" });
  }
  if (request.method === "DELETE") {
    await env.SUBSCRIBERS.delete(`webhook:${id}`);
    await env.SUBSCRIBERS.delete(`state:${id}`);
    const count = Number((await env.SUBSCRIBERS.get("meta:webhook_count")) || 0);
    await env.SUBSCRIBERS.put("meta:webhook_count", String(Math.max(0, count - 1)));
    return json({ deleted: true, id }, 200, { "Cache-Control": "no-store" });
  }
  const { secret, ...visible } = sub;
  const state = await env.SUBSCRIBERS.get(`state:${id}`);
  return json({ ...visible, delivery_state: state ? JSON.parse(state) : null }, 200, { "Cache-Control": "no-store" });
}

// RFC 9727 API catalog: a linkset pointing at the API's description and docs.
function apiCatalog(request) {
  const body = {
    linkset: [
      {
        anchor: `${SITE}/api/v1`,
        "service-desc": [{ href: `${SITE}/openapi.json`, type: "application/openapi+json" }],
        "service-doc": [
          { href: `${SITE}/llms.txt`, type: "text/plain" },
          { href: `${SITE}/skills/scrubshifts-jobs/SKILL.md`, type: "text/markdown" },
        ],
        "service-meta": [{ href: `${SITE}/api/v1`, type: "application/json" }],
      },
      {
        anchor: `${SITE}/mcp`,
        "service-doc": [{ href: `${SITE}/skills/scrubshifts-jobs/SKILL.md`, type: "text/markdown" }],
        "service-meta": [
          {
            href: "https://registry.modelcontextprotocol.io/v0/servers?search=io.github.stableotto/scrubshifts",
            type: "application/json",
          },
        ],
      },
    ],
  };
  const headers = {
    "Content-Type": 'application/linkset+json; profile="https://www.rfc-editor.org/info/rfc9727"',
    "Cache-Control": "public, max-age=3600",
    Link: `<${SITE}/.well-known/api-catalog>; rel="api-catalog"`,
    ...CORS,
  };
  if (request.method === "HEAD") return new Response(null, { status: 200, headers });
  return new Response(JSON.stringify(body, null, 2), { status: 200, headers });
}

export async function handleAgentRequest(request, env) {
  const url = new URL(request.url);
  const ua = request.headers.get("user-agent") || "";
  const log = { evt: "agent_api", path: url.pathname, method: request.method, ua: ua.slice(0, 160) };
  const ai = aiAgentFamily(ua);
  if (ai) log.ai = ai.family;
  let resp;
  try {
    if (request.method === "OPTIONS") {
      resp = new Response(null, { status: 204, headers: CORS });
    } else if (url.pathname === "/.well-known/api-catalog") {
      resp = apiCatalog(request);
    } else if (url.pathname === "/mcp") {
      resp = await handleMcp(request, env, url.origin, log);
    } else {
      resp = await handleApi(request, env, url, log);
    }
  } catch (err) {
    log.error = String((err && err.message) || err);
    resp = json({ error: "Internal error" }, 500);
  }
  log.status = resp.status;
  console.log(JSON.stringify(log));
  recordMetric(env, {
    kind: url.pathname === "/mcp" ? "mcp" : "api",
    path: url.pathname,
    detail: log.tool || (log.rpc || []).join(",") || "",
    family: log.ai || "",
    status: resp.status,
    query: log.params || log.args,
  });
  return resp;
}

// Exported for tests.
export const _internal = { parseQuery, geocode, milesBetween, statesNear, pickShards, expand, summarize, formatPay };
