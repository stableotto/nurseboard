"""Weekly AI-agent traffic report from Workers Analytics Engine.

frontend/_agent.js writes one data point per agent API/MCP request and per AI
crawler page fetch to the dataset below (binding AGENT_METRICS):

    index1 / blob1  kind: api | mcp | crawl
    blob2           path
    blob3           detail: MCP tool or method, or the crawler's user agent token
    blob4           AI family (openai, anthropic, perplexity, ...) when known
    blob5           HTTP status
    blob6           query summary (role/specialty/state/shift/employment_type)

Prints a Markdown report. Needs CLOUDFLARE_API_TOKEN with Account Analytics:Read.

Usage:
    python -m pipeline.agent_traffic > report.md
"""

from __future__ import annotations

import os
import sys

import requests

DATASET = "scrubshifts_agent_traffic"
DAYS = 7


def query(sql: str) -> list[dict]:
    account = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    r = requests.post(
        f"https://api.cloudflare.com/client/v4/accounts/{account}/analytics_engine/sql",
        headers={"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"},
        data=sql,
        timeout=30,
    )
    if r.status_code in (401, 403):
        raise PermissionError(r.status_code)
    r.raise_for_status()
    return r.json().get("data", [])


def table(rows: list[dict], cols: list[tuple[str, str]]) -> str:
    if not rows:
        return "_none_\n"
    out = "| " + " | ".join(h for h, _ in cols) + " |\n|" + "---|" * len(cols) + "\n"
    for r in rows:
        out += "| " + " | ".join(str(r.get(k) or "—") for _, k in cols) + " |\n"
    return out


def main() -> None:
    since = f"timestamp > NOW() - INTERVAL '{DAYS}' DAY"
    try:
        by_kind = query(
            f"SELECT blob1 AS kind, blob4 AS family, SUM(_sample_interval) AS n FROM {DATASET} "
            f"WHERE {since} GROUP BY kind, family ORDER BY n DESC"
        )
        tools = query(
            f"SELECT blob3 AS tool, SUM(_sample_interval) AS n FROM {DATASET} "
            f"WHERE {since} AND blob1 = 'mcp' GROUP BY tool ORDER BY n DESC LIMIT 10"
        )
        asks = query(
            f"SELECT blob6 AS query, SUM(_sample_interval) AS n FROM {DATASET} "
            f"WHERE {since} AND blob1 IN ('api', 'mcp') AND blob6 != '' GROUP BY query ORDER BY n DESC LIMIT 15"
        )
        crawlers = query(
            f"SELECT blob3 AS agent, blob4 AS family, SUM(_sample_interval) AS n FROM {DATASET} "
            f"WHERE {since} AND blob1 = 'crawl' GROUP BY agent, family ORDER BY n DESC LIMIT 15"
        )
    except PermissionError as e:
        print(
            f"## Agent traffic\n\nCould not read Analytics Engine (HTTP {e}). Give the `CLOUDFLARE_API_TOKEN` "
            "secret the **Account Analytics: Read** permission, or add a separate token."
        )
        return
    except requests.RequestException as e:
        print(f"## Agent traffic\n\nAnalytics Engine query failed: {e}")
        return

    total = {k: sum(int(r["n"]) for r in by_kind if r["kind"] == k) for k in ("api", "mcp", "crawl")}
    print(f"## Agent traffic, last {DAYS} days\n")
    print(f"- **API calls:** {total['api']:,}\n- **MCP calls:** {total['mcp']:,}\n- **AI crawler page fetches:** {total['crawl']:,}\n")
    print("### By kind and AI family\n")
    print(table(by_kind, [("Kind", "kind"), ("AI family", "family"), ("Requests", "n")]))
    print("### MCP tools and methods\n")
    print(table(tools, [("Tool / method", "tool"), ("Calls", "n")]))
    print("### Most requested searches\n")
    print(table(asks, [("Filters", "query"), ("Requests", "n")]))
    print("### AI crawlers\n")
    print(table(crawlers, [("User agent", "agent"), ("Family", "family"), ("Fetches", "n")]))


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # report, don't fail the workflow
        print(f"## Agent traffic\n\nReport failed: {e}")
        sys.exit(0)
