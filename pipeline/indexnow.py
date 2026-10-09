"""Notify IndexNow (Bing, Yandex, Seznam, Naver …) of new and updated URLs.

Bing powers much of what AI assistants retrieve (ChatGPT search, Copilot), so
getting fresh listings into Bing quickly matters as much as Google. IndexNow
needs no account: the key below is public by design and is served from
frontend/<key>.txt so engines can verify we own the host.

Usage:
    python -m pipeline.indexnow [--with-pages] frontend/sitemap-pages.xml frontend/sitemap-jobs-*.xml

Category pages get a fresh lastmod on every export, so they are only submitted
with --with-pages (the once-daily full pipeline), not on the 4x/day enrich runs.
"""

import logging
import os
import sys
from datetime import datetime, timedelta, timezone

import requests

from pipeline.google_indexing import _parse_sitemap_entries

logger = logging.getLogger(__name__)

HOST = "scrubshifts.com"
KEY = "eda428030748d2a0f056d4bd127db3e3"
KEY_LOCATION = f"https://{HOST}/{KEY}.txt"
ENDPOINT = "https://api.indexnow.org/indexnow"
MAX_URLS_PER_REQUEST = 10_000
# Only URLs whose sitemap lastmod is this recent. IndexNow is for changes;
# resubmitting the whole catalog daily is treated as spam.
RECENT_DAYS = 2


def select_urls(
    entries: list[tuple[str, str]], with_pages: bool = False, now: datetime | None = None
) -> list[str]:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=RECENT_DAYS)).strftime("%Y-%m-%d")
    # Category pages first (their job lists rotate daily), then newest jobs.
    pages = [loc for loc, _ in entries if "/listing/" not in loc] if with_pages else []
    jobs = sorted(
        ((loc, lm) for loc, lm in entries if "/listing/" in loc and lm and lm[:10] >= cutoff),
        key=lambda e: e[1],
        reverse=True,
    )
    urls = pages + [loc for loc, _ in jobs]
    seen = set()
    out = []
    for u in urls:
        if u not in seen and u.startswith(f"https://{HOST}/"):
            seen.add(u)
            out.append(u)
    return out[:MAX_URLS_PER_REQUEST]


def run(sitemap_paths: list[str], with_pages: bool = False) -> None:
    entries: list[tuple[str, str]] = []
    for path in sitemap_paths:
        if os.path.exists(path):
            entries.extend(_parse_sitemap_entries(path))
        else:
            logger.warning("Sitemap not found: %s", path)
    urls = select_urls(entries, with_pages)
    if not urls:
        logger.info("=== IndexNow === nothing new to submit")
        return
    logger.info("=== IndexNow === submitting %d URLs", len(urls))
    resp = requests.post(
        ENDPOINT,
        json={"host": HOST, "key": KEY, "keyLocation": KEY_LOCATION, "urlList": urls},
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=60,
    )
    # 200 OK and 202 Accepted are both success (202: key validation pending).
    if resp.status_code in (200, 202):
        logger.info("IndexNow accepted (%d)", resp.status_code)
    else:
        logger.warning("IndexNow returned %d: %s", resp.status_code, resp.text[:300])


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    args = sys.argv[1:]
    with_pages = "--with-pages" in args
    paths = [a for a in args if a != "--with-pages"]
    run(paths or ["frontend/sitemap-pages.xml", "frontend/sitemap-jobs-1.xml"], with_pages)
