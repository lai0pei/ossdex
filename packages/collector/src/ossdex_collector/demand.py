"""What users of a project are asking for: its most-upvoted open issues and how many open issues
carry a help-wanted or bounty label. Fetched on request for chosen repos (`ossdex-collector demand`), not
in the daily `update`: it costs a GitHub search per repo."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from ossdex_core.store import now_iso

from .github import DEMAND_BATCH, GitHub

Log = Callable[[str], None]


@dataclass
class DemandReport:
    wanted: int = 0
    fetched: int = 0
    fresh: int = 0  # skipped: fetched within the last `days`
    gone: int = 0


def pick_repos(conn: sqlite3.Connection, *, names: list[str] = (), topic: str | None = None,
               top: int = 20) -> list[tuple[int, str]]:
    """[(ghr_id, full_name)] for the named repos, or the `top` most-starred visible repos of `topic`."""
    if names:
        marks = ",".join("?" * len(names))
        rows = conn.execute(f"SELECT ghr_id, full_name FROM repos WHERE enrich_status = 'ok' "
                            f"AND lower(full_name) IN ({marks})", [n.lower() for n in names])
    else:
        rows = conn.execute(
            "SELECT ghr_id, full_name FROM repos WHERE enrich_status = 'ok' AND full_name NOT LIKE '%~%' "
            "AND EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid(topics) THEN topics ELSE '[]' END) "
            "WHERE lower(value) = ?) ORDER BY stars DESC LIMIT ?", ((topic or "").lower(), top))
    return [(r[0], r[1]) for r in rows]


def fetch_demand(gh: GitHub, conn: sqlite3.Connection, repos: list[tuple[int, str]], *,
                 days: int = 7, log: Log = lambda m: None) -> DemandReport:
    """Store the demand signals of `repos`, skipping those fetched in the last `days`.
    Commits after each batch, so a stopped run (budget, rate limit) keeps what it got."""
    report = DemandReport(wanted=len(repos))
    cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    todo = []
    for ghr_id, name in repos:
        row = conn.execute("SELECT fetched_at FROM repo_demand WHERE ghr_id = ?", (ghr_id,)).fetchone()
        if row and row[0] and row[0] >= cutoff:
            report.fresh += 1
        else:
            todo.append((ghr_id, name))
    for i in range(0, len(todo), DEMAND_BATCH):
        batch = todo[i:i + DEMAND_BATCH]
        got = gh.issue_demand(batch)
        now = now_iso()
        for ghr_id, _ in batch:
            d = got.get(ghr_id)
            if d is None:
                report.gone += 1
                continue
            report.fetched += 1
            conn.execute("INSERT OR REPLACE INTO repo_demand(ghr_id, help_wanted, bounties, fetched_at) "
                         "VALUES (?,?,?,?)", (ghr_id, d["help_wanted"], d["bounties"], now))
            conn.execute("DELETE FROM repo_issues WHERE ghr_id = ?", (ghr_id,))
            conn.executemany(
                "INSERT INTO repo_issues(ghr_id, number, title, url, reactions, comments, labels, "
                "created_at) VALUES (?,?,?,?,?,?,?,?)",
                [(ghr_id, x["number"], x["title"], x["url"], x["reactions"], x["comments"],
                  json.dumps(x["labels"]), x["created_at"]) for x in d["issues"]])
        conn.commit()
        log(f"demand: {min(i + DEMAND_BATCH, len(todo))}/{len(todo)}")
    return report
