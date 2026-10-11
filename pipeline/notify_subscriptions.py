"""Deliver saved-search webhooks after a data refresh.

Agents register saved searches with POST /api/v1/subscriptions (see
frontend/_agent.js); each is stored in the SUBSCRIBERS KV namespace under
"webhook:<id>" (written only by the API, so a user's DELETE is never undone
here). This script keeps its own delivery state under "state:<id>":
{"cursor": <data_as_of of the last delivery>, "failures": n}.

After each deploy it runs every saved search against the live API with
first_seen_after = cursor (jobs that first appeared on ScrubShifts since the
last delivery), pages through all results, and POSTs them to the webhook:

    POST <webhook_url>
    Content-Type: application/json
    X-ScrubShifts-Signature: sha256=<HMAC-SHA256(secret, body) hex>
    {"subscription_id": ..., "data_as_of": ..., "jobs": [...], "manage_url": ...}

Matching goes through the public search API, so a saved search returns exactly
what the same query would return interactively.

Environment: CLOUDFLARE_API_TOKEN, CLOUDFLARE_ACCOUNT_ID. The KV namespace id
is read from wrangler.toml.

Usage:
    python -m pipeline.notify_subscriptions
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
import os
import socket
import sys
import time
import tomllib
import urllib.parse

import requests

logger = logging.getLogger(__name__)

SITE = "https://scrubshifts.com"
CF_API = "https://api.cloudflare.com/client/v4"
PAGE_SIZE = 50
MAX_JOBS_PER_RUN = 500
MAX_FAILURES = 10
TIMEOUT = 15


def _kv_namespace_id(binding: str = "SUBSCRIBERS") -> str | None:
    try:
        with open("wrangler.toml", "rb") as f:
            cfg = tomllib.load(f)
    except OSError:
        return None
    for ns in cfg.get("kv_namespaces", []):
        if ns.get("binding") == binding:
            return ns.get("id")
    return None


class KV:
    """Minimal Workers KV REST client with backoff on rate limits."""

    def __init__(self, token: str, account: str, namespace: str):
        self.base = f"{CF_API}/accounts/{account}/storage/kv/namespaces/{namespace}"
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def _call(self, method: str, path: str, **kw) -> requests.Response:
        for attempt in range(5):
            r = self.session.request(method, f"{self.base}{path}", timeout=TIMEOUT, **kw)
            if r.status_code != 429:
                return r
            time.sleep(min(60, 5 * 2**attempt))
        return r

    def keys(self, prefix: str) -> list[str]:
        out, cursor = [], None
        while True:
            params = {"prefix": prefix, "limit": 1000}
            if cursor:
                params["cursor"] = cursor
            r = self._call("GET", "/keys", params=params)
            r.raise_for_status()
            data = r.json()
            out += [k["name"] for k in data.get("result", [])]
            cursor = (data.get("result_info") or {}).get("cursor")
            if not cursor:
                return out

    def get(self, key: str) -> dict | None:
        r = self._call("GET", f"/values/{urllib.parse.quote(key, safe='')}")
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return json.loads(r.text)

    def put(self, key: str, value) -> None:
        r = self._call("PUT", f"/values/{urllib.parse.quote(key, safe='')}",
                       data=json.dumps(value), headers={"Content-Type": "text/plain"})
        r.raise_for_status()

    def delete(self, key: str) -> None:
        self._call("DELETE", f"/values/{urllib.parse.quote(key, safe='')}")


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def public_host(url: str) -> bool:
    """True when every address the webhook host resolves to is public.

    Checked right before each delivery (the API also refuses IP literals and
    internal names at creation), so a name pointed at a private, loopback,
    link-local or metadata address is never contacted from CI.
    """
    host = urllib.parse.urlsplit(url).hostname or ""
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        return False
    addrs = {info[4][0] for info in infos}
    return bool(addrs) and all(ipaddress.ip_address(a.split("%")[0]).is_global for a in addrs)


def _params(query: dict) -> dict:
    # Lists become comma-separated (repeated keys would keep only the last).
    return {k: ",".join(map(str, v)) if isinstance(v, list) else v for k, v in query.items()}


def new_jobs_for(query: dict, cursor: str) -> tuple[list[dict], str | None]:
    """All jobs first seen after cursor that match the saved search."""
    jobs: list[dict] = []
    offset, data_as_of = 0, None
    while len(jobs) < MAX_JOBS_PER_RUN:
        params = {**_params(query), "first_seen_after": cursor, "sort": "newest",
                  "limit": PAGE_SIZE, "offset": offset}
        r = requests.get(f"{SITE}/api/v1/jobs", params=params, timeout=30,
                         headers={"User-Agent": "ScrubShifts-Notifier/1.0"})
        r.raise_for_status()
        data = r.json()
        data_as_of = data.get("data_as_of")
        jobs += data.get("results", [])
        if data.get("next_offset") is None:
            break
        offset = data["next_offset"]
    return jobs[:MAX_JOBS_PER_RUN], data_as_of


def deliver(sub: dict, jobs: list[dict], data_as_of: str) -> bool:
    if not public_host(sub["webhook_url"]):
        logger.warning("Webhook host for %s does not resolve to public addresses; not delivering", sub["id"])
        return False
    for i in range(0, len(jobs), PAGE_SIZE):
        body = json.dumps({
            "subscription_id": sub["id"],
            "data_as_of": data_as_of,
            "query": sub.get("query", {}),
            "jobs": jobs[i:i + PAGE_SIZE],
            "manage_url": f"{SITE}/api/v1/subscriptions/{sub['id']}",
        }).encode()
        try:
            r = requests.post(
                sub["webhook_url"],
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "ScrubShifts-Webhooks/1.0",
                    "X-ScrubShifts-Signature": sign(sub["secret"], body),
                },
                timeout=TIMEOUT,
                allow_redirects=False,
            )
        except requests.RequestException:
            return False
        if not 200 <= r.status_code < 300:
            return False
    return True


def process(kv: KV, key: str) -> str:
    """Handle one saved search. Returns delivered|idle|failed|removed|gone."""
    sub = kv.get(key)
    if not sub:
        return "gone"
    sid = sub["id"]
    state = kv.get(f"state:{sid}") or {"cursor": sub.get("start_after"), "failures": 0}

    def fail() -> str:
        state["failures"] = state.get("failures", 0) + 1
        if state["failures"] >= MAX_FAILURES:
            kv.delete(key)
            kv.delete(f"state:{sid}")
            return "removed"
        kv.put(f"state:{sid}", state)  # cursor unchanged: retried next run
        return "failed"

    try:
        jobs, data_as_of = new_jobs_for(sub.get("query", {}), state["cursor"])
    except requests.HTTPError as e:
        if e.response is not None and 400 <= e.response.status_code < 500:
            logger.warning("Search rejected for %s (%s)", sid, e.response.status_code)
            return fail()
        raise
    if not jobs or not data_as_of or data_as_of <= (state["cursor"] or ""):
        return "idle"  # nothing new; no KV write
    if not deliver(sub, jobs, data_as_of):
        return fail()
    kv.put(f"state:{sid}", {"cursor": data_as_of, "failures": 0, "last_delivered": len(jobs)})
    return "delivered"


def run() -> None:
    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    account = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    namespace = _kv_namespace_id()
    if not (token and account and namespace):
        logger.info("Saved searches not configured (need token, account and SUBSCRIBERS in wrangler.toml); skipping")
        return
    kv = KV(token, account, namespace)
    keys = kv.keys("webhook:")
    logger.info("=== Saved searches === %d subscriptions", len(keys))
    tally: dict[str, int] = {}
    for key in keys:
        try:
            outcome = process(kv, key)
        except Exception as e:  # one bad subscription must not stop the rest
            logger.warning("Saved search %s errored: %s", key, e)
            outcome = "error"
        tally[outcome] = tally.get(outcome, 0) + 1
    # Keep the API's capacity counter honest (expired or removed subscriptions).
    try:
        live = len(keys) - tally.get("removed", 0) - tally.get("gone", 0)
        if (kv.get("meta:webhook_count") or 0) != live:
            kv.put("meta:webhook_count", live)
    except Exception as e:
        logger.warning("Could not update subscription count: %s", e)
    logger.info("Saved searches: %s", tally)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    try:
        run()
    except Exception:
        logger.exception("Saved-search delivery failed")
    sys.exit(0)  # never fail the deploy workflow over notifications
