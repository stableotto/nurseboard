"""Notify Google Indexing API of new/updated job URLs.

Requires a Google Cloud service account with Indexing API enabled.
The service account email must be added as an owner in Search Console.

Usage:
    python -m pipeline.google_indexing frontend/sitemap-jobs-1.xml frontend/sitemap-pages.xml

Environment:
    GOOGLE_SERVICE_ACCOUNT_JSON — service account key JSON (as a string, not file path)
"""

import json
import logging
import os
import sys
import time
import xml.etree.ElementTree as ET

import requests

logger = logging.getLogger(__name__)

INDEXING_API = "https://indexing.googleapis.com/v3/urlNotifications:publish"
BATCH_API = "https://indexing.googleapis.com/batch"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/indexing"

# Google Indexing API quota: 200 requests per day for new properties,
# can be increased. Batch endpoint counts as 1 request per inner item.
MAX_URLS_PER_RUN = 200


def _get_access_token(sa_json: dict) -> str:
    """Get OAuth2 access token using service account JWT."""
    import hashlib
    import base64
    import struct

    now = int(time.time())
    header = base64.urlsafe_b64encode(json.dumps(
        {"alg": "RS256", "typ": "JWT"}
    ).encode()).rstrip(b"=")

    payload = base64.urlsafe_b64encode(json.dumps({
        "iss": sa_json["client_email"],
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": now,
        "exp": now + 3600,
    }).encode()).rstrip(b"=")

    signing_input = header + b"." + payload

    # Sign with RSA-SHA256
    from hashlib import sha256
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        private_key = serialization.load_pem_private_key(
            sa_json["private_key"].encode(), password=None
        )
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    except ImportError:
        # Fallback: use google-auth if cryptography not available
        try:
            from google.oauth2 import service_account
            creds = service_account.Credentials.from_service_account_info(
                sa_json, scopes=[SCOPE]
            )
            creds.refresh(requests.Request())
            return creds.token
        except ImportError:
            logger.error("Need 'cryptography' or 'google-auth' package for JWT signing")
            raise

    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b"=")
    jwt_token = (signing_input + b"." + sig_b64).decode()

    resp = requests.post(TOKEN_URL, data={
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": jwt_token,
    }, timeout=15)
    resp.raise_for_status()
    return resp.json()["access_token"]


def _parse_sitemap_entries(sitemap_path: str) -> list[tuple[str, str]]:
    """Extract (loc, lastmod) pairs from a sitemap XML file."""
    tree = ET.parse(sitemap_path)
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    entries = []
    for u in tree.findall("s:url", ns):
        loc_el = u.find("s:loc", ns)
        if loc_el is None or not loc_el.text:
            continue
        lm_el = u.find("s:lastmod", ns)
        lastmod = lm_el.text if lm_el is not None and lm_el.text else ""
        entries.append((loc_el.text, lastmod))
    return entries


def _parse_sitemap_urls(sitemap_path: str) -> list[str]:
    """Extract URLs from a sitemap XML file."""
    return [loc for loc, _ in _parse_sitemap_entries(sitemap_path)]


def notify_urls(urls: list[str], access_token: str, action: str = "URL_UPDATED") -> dict:
    """Send individual URL notifications to the Indexing API.

    Returns dict with counts: {sent, success, errors}.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    sent = 0
    success = 0
    errors = 0

    for url in urls[:MAX_URLS_PER_RUN]:
        try:
            resp = requests.post(
                INDEXING_API,
                headers=headers,
                json={"url": url, "type": action},
                timeout=10,
            )
            if resp.status_code == 200:
                success += 1
            else:
                errors += 1
                if sent < 5:  # Log first few errors
                    logger.warning("  Error for %s: %s", url, resp.text[:200])
        except Exception as e:
            errors += 1
            if sent < 5:
                logger.warning("  Exception for %s: %s", url, e)

        sent += 1
        if sent % 50 == 0:
            logger.info("  Progress: %d/%d sent (%d ok, %d errors)", sent, len(urls), success, errors)

    return {"sent": sent, "success": success, "errors": errors}


def run(sitemap_paths: list[str]):
    """Main entry point: parse sitemaps and notify Google."""
    sa_json_str = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_json_str:
        logger.warning("GOOGLE_SERVICE_ACCOUNT_JSON not set, skipping indexing API ping")
        return

    sa_json = json.loads(sa_json_str)

    logger.info("=== Google Indexing API ===")
    logger.info("  Getting access token...")
    access_token = _get_access_token(sa_json)

    entries = []
    for path in sitemap_paths:
        if os.path.exists(path):
            parsed = _parse_sitemap_entries(path)
            logger.info("  Parsed %d URLs from %s", len(parsed), path)
            entries.extend(parsed)
        else:
            logger.warning("  Sitemap not found: %s", path)

    if not entries:
        logger.warning("  No URLs to submit")
        return

    # Category/landing pages: always submit (they rotate their job lists daily
    # and are the pages we most want kept fresh in the index).
    page_urls = [loc for loc, _ in entries if "/listing/" not in loc]

    # Job detail pages: the daily quota is far smaller than the catalog, so
    # spend it on the NEWEST jobs (by sitemap lastmod, descending). Re-pinging
    # the same first-N URLs every run — the previous behavior — meant freshly
    # added jobs were never notified and often expired before getting indexed.
    job_entries = [(loc, lm) for loc, lm in entries if "/listing/" in loc]
    job_entries.sort(key=lambda e: e[1], reverse=True)
    job_urls = [loc for loc, _ in job_entries]

    # Category pages first, then fill remaining quota with the newest jobs.
    submit_urls = page_urls + job_urls
    jobs_submitted = max(0, min(len(job_urls), MAX_URLS_PER_RUN - len(page_urls)))
    logger.info("  Submitting %d URLs (%d pages + %d newest jobs, capped at %d)",
                min(len(submit_urls), MAX_URLS_PER_RUN), len(page_urls), jobs_submitted,
                MAX_URLS_PER_RUN)

    result = notify_urls(submit_urls, access_token)
    logger.info("  Done: %d sent, %d success, %d errors",
                result["sent"], result["success"], result["errors"])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    paths = sys.argv[1:] or ["frontend/sitemap-pages.xml", "frontend/sitemap-jobs-1.xml"]
    run(paths)
