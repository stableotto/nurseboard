/**
 * Radius search: find jobs within X miles of a zip code.
 * Uses static zip/city centroid data — no API calls.
 */

let zipData = null;
let cityData = null;

const EARTH_RADIUS_MILES = 3958.8;

function haversine(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return EARTH_RADIUS_MILES * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

async function loadZipData() {
  if (zipData) return zipData;
  try {
    const resp = await fetch("/data/zips.json");
    if (resp.ok) zipData = await resp.json();
  } catch {}
  return zipData;
}

async function loadCityData() {
  if (cityData) return cityData;
  try {
    const resp = await fetch("/data/cities.json");
    if (resp.ok) cityData = await resp.json();
  } catch {}
  return cityData;
}

export async function lookupZip(zip) {
  const data = await loadZipData();
  if (!data || !data[zip]) return null;
  return { lat: data[zip][0], lng: data[zip][1] };
}

export async function filterByRadius(jobs, zip, radiusMiles) {
  if (!zip || !radiusMiles) return jobs;

  const origin = await lookupZip(zip);
  if (!origin) return jobs;

  const cities = await loadCityData();
  if (!cities) return jobs;

  return jobs.filter((j) => {
    const loc = j.location || "";
    const state = j.state;
    if (!loc.includes(",") || !state) return false;

    const city = loc.split(",")[0].trim().toLowerCase();
    const key = `${city}|${state}`;
    const coords = cities[key];
    if (!coords) return false;

    const dist = haversine(origin.lat, origin.lng, coords[0], coords[1]);
    j._distance = Math.round(dist);
    return dist <= radiusMiles;
  });
}
