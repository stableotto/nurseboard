"""Fetch upstream job data from GitHub."""

import gzip
import io
import json
import logging

import requests

from pipeline.config import UPSTREAM_MANIFEST_URL

logger = logging.getLogger(__name__)


def download_upstream_jobs() -> list[dict]:
    """Download all jobs from the upstream aggregator repo."""
    session = requests.Session()

    logger.info("Fetching manifest from %s", UPSTREAM_MANIFEST_URL)
    resp = session.get(UPSTREAM_MANIFEST_URL, timeout=30)
    resp.raise_for_status()
    manifest = resp.json()

    base_url = UPSTREAM_MANIFEST_URL.rsplit("/", 1)[0]
    chunks = manifest.get("chunks", [])
    logger.info("Manifest has %d chunks", len(chunks))

    all_jobs = []
    for chunk_info in chunks:
        filename = chunk_info if isinstance(chunk_info, str) else chunk_info.get("filename", "")
        url = f"{base_url}/{filename}"
        logger.info("Downloading %s", filename)

        chunk_resp = session.get(url, timeout=60)
        chunk_resp.raise_for_status()

        if filename.endswith(".gz"):
            raw = gzip.decompress(chunk_resp.content)
            jobs = json.loads(raw)
        else:
            jobs = chunk_resp.json()

        if isinstance(jobs, list):
            all_jobs.extend(jobs)
        else:
            logger.warning("Unexpected chunk format for %s", filename)

    logger.info("Downloaded %d total jobs", len(all_jobs))
    return all_jobs
