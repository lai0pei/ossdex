"""Collecting repos from GitHub: discover (search), refresh (lookups) and READMEs.

GitHub search returns at most 1000 results per query, so discovery splits the star range in two
until every slice fits. A star count that still holds more than 1000 repos is split by creation
date. The plan and each slice's page cursor are saved, so a stopped run resumes where it was.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from ossdex_core.config import Settings
from ossdex_core.store import (
    apply_threshold,
    get_meta,
    mark,
    now_iso,
    reject_reason,
    set_meta,
    today_iso,
    touch_sync,
    upsert_repo,
)

from .github import README_BATCH, BudgetExhausted, GitHub, GithubError, RateLimited

SLICE_CAP = 1000  # GitHub's per-query result limit
FIRST_DAY = date(2007, 1, 1)  # before GitHub existed
PLAN_MAX_AGE = timedelta(days=2)  # an older unfinished plan is counted again
README_MAX_CHARS = 200_000
REFRESH_BATCH = 100

Log = Callable[[str], None]


@dataclass
class DiscoverReport:
    resumed: bool = False
    slices: int = 0
    estimate: int = 0  # repos the search matched; an upper bound, as unlicensed ones are dropped
    slices_done: int = 0
    pages: int = 0
    seen: int = 0
    new: int = 0
    updated: int = 0
    skipped: dict[str, int] = field(default_factory=dict)
    truncated: int = 0  # slices that still held more than the cap (a rare, very dense star count)
    failed_slices: int = 0  # slices GitHub kept failing on; the next run tries them again
    finished: bool = False


def base_query(exclude_topics: tuple[str, ...]) -> str:
    parts = ["fork:false", "archived:false", "mirror:false", "template:false", "is:public"]
    parts += [f"-topic:{t}" for t in exclude_topics]
    return " ".join(parts)


def _stars(lo: int, hi: int | None) -> str:
    if hi is None:
        return f"stars:>={lo}"
    return f"stars:{lo}..{hi}" if lo != hi else f"stars:{lo}"


def plan_slices(gh: GitHub, base: str, lo: int, *, cap: int = SLICE_CAP,
                today: date | None = None, log: Log = lambda m: None) -> list[tuple[str, int, bool]]:
    """[(query, count, truncated)] covering every repo with at least `lo` stars, each slice
    holding at most `cap` repos. Always terminates: stars are bisected down to one value, then
    that value's repos are bisected by creation date, down to a single day."""
    today = today or datetime.now(UTC).date()
    out: list[tuple[str, int, bool]] = []

    def by_date(star: int, d0: date, d1: date) -> None:
        q = f"{base} stars:{star} created:{d0.isoformat()}..{d1.isoformat()}"
        n = gh.search_count(q)
        if n == 0:
            return
        if n <= cap:
            out.append((q, n, False))
        elif d0 < d1:
            mid = d0 + (d1 - d0) // 2
            by_date(star, d0, mid)
            by_date(star, mid + timedelta(days=1), d1)
        else:  # one star count, one day, still over the cap: the search can only show `cap`
            log(f"  {q}: {n} repos on one day; only the first {cap} can be read")
            out.append((q, n, True))

    def by_stars(a: int, b: int | None) -> None:
        q = f"{base} {_stars(a, b)}"
        n = gh.search_count(q)
        if n == 0:
            return
        if n <= cap:
            out.append((q, n, False))
        elif b is not None and a < b:
            mid = (a + b) // 2
            by_stars(a, mid)
            by_stars(mid + 1, b)
        elif b is not None:  # a == b
            by_date(a, FIRST_DAY, today)
        else:
            top = gh.top_stars(f"{base} stars:>={a}")
            by_stars(a, max(top or a, a))

    by_stars(lo, None)
    return out


def _load_state(conn: sqlite3.Connection) -> dict | None:
    raw = get_meta(conn, "discover_run")
    return json.loads(raw) if raw else None


def discover(gh: GitHub, conn: sqlite3.Connection, settings: Settings, *,
             min_stars: int | None = None, dry_run: bool = False, cap: int = SLICE_CAP,
             log: Log = lambda m: None) -> DiscoverReport:
    """Search GitHub for repos with at least `min_stars` stars and store the ones that qualify."""
    min_stars = settings.min_stars if min_stars is None else min_stars
    exclude = tuple(settings.exclude_topics)
    base = base_query(exclude)
    report = DiscoverReport()

    if dry_run:
        plan = plan_slices(gh, base, min_stars, cap=cap, log=log)
        report.slices = len(plan)
        report.estimate = sum(n for _, n, _ in plan)
        report.truncated = sum(1 for *_, t in plan if t)
        return report

    state = _load_state(conn)
    started = datetime.fromisoformat(state["started"]) if state else None
    resume = bool(state and not state.get("finished") and state["min_stars"] == min_stars
                  and state["exclude"] == list(exclude) and state.get("planned")
                  and datetime.now(UTC) - started < PLAN_MAX_AGE)
    if resume:
        report.resumed = True
        log("resuming the unfinished run")
    else:
        started_at = now_iso()
        state = {"min_stars": min_stars, "exclude": list(exclude), "started": started_at,
                 "planned": False, "finished": False}
        set_meta(conn, "discover_run", json.dumps(state))
        conn.execute("DELETE FROM slices")
        conn.commit()
        log("planning slices...")
        plan = plan_slices(gh, base, min_stars, cap=cap, log=log)
        conn.executemany("INSERT OR REPLACE INTO slices(query, total, truncated) VALUES (?,?,?)",
                         [(q, n, int(t)) for q, n, t in plan])
        state["planned"] = True
        set_meta(conn, "discover_run", json.dumps(state))
        conn.commit()

    rows = conn.execute("SELECT query, total, cursor, done, truncated FROM slices").fetchall()
    report.slices = len(rows)
    report.estimate = sum(r["total"] for r in rows)
    report.truncated = sum(r["truncated"] for r in rows)
    report.slices_done = sum(r["done"] for r in rows)
    day, now = today_iso(), now_iso()
    for row in rows:
        if row["done"]:
            continue
        if _read_slice(gh, conn, row, exclude, day, now, report, log,
                       require_license=settings.require_license):
            report.slices_done += 1
            log(f"slice {report.slices_done}/{report.slices} done ({report.seen} repos read)")

    apply_threshold(conn, min_stars)
    set_meta(conn, "require_license", "1" if settings.require_license else "0")
    if report.failed_slices == 0:
        state["finished"] = True
        set_meta(conn, "discover_run", json.dumps(state))
        report.finished = True
    touch_sync(conn)
    conn.commit()
    return report


def _read_slice(gh: GitHub, conn: sqlite3.Connection, row, exclude: tuple[str, ...], day: str,
                now: str, report: DiscoverReport, log: Log, *, require_license: bool) -> bool:
    """Read one slice page by page. False when GitHub keeps failing on it (not a rate limit):
    the slice stays unfinished with its cursor, so the next run resumes it."""
    cursor = row["cursor"]
    while True:
        try:
            nodes, page, _ = gh.search_page(row["query"], cursor)
        except (RateLimited, BudgetExhausted):
            raise
        except GithubError as e:
            report.failed_slices += 1
            log(f"slice failed, it will be retried next run: {e}")
            return False
        report.pages += 1
        for node in nodes:
            report.seen += 1
            why = reject_reason(node, exclude, require_license=require_license)
            if why:
                report.skipped[why] = report.skipped.get(why, 0) + 1
                if conn.execute("SELECT 1 FROM repos WHERE ghr_id = ?",
                                (node["databaseId"],)).fetchone():
                    mark(conn, node["databaseId"], "filtered", now)
                continue
            if upsert_repo(conn, node, now=now, day=day):
                report.new += 1
            else:
                report.updated += 1
        cursor = page.get("endCursor")
        done = not page.get("hasNextPage")
        conn.execute("UPDATE slices SET cursor = ?, done = ? WHERE query = ?",
                     (cursor, int(done), row["query"]))
        conn.commit()  # the page and its cursor land together: a stop never loses or repeats it
        if done:
            return True


def run_started(conn: sqlite3.Connection) -> str | None:
    """When the latest discover run began: repos not seen since then were not in its results."""
    state = _load_state(conn)
    return state["started"] if state else None


FAILED = object()


def resilient(batch: list, fetch: Callable[[list], list]) -> list[tuple]:
    """[(item, result)] for `fetch(batch)`, which returns one result per item. When GitHub fails a
    batch (not a rate limit), it is halved until the bad item is alone; that item gets FAILED, so
    one poisoned repo cannot stall every run at the same place."""
    try:
        return list(zip(batch, fetch(batch), strict=True))
    except (RateLimited, BudgetExhausted):
        raise
    except GithubError:
        if len(batch) == 1:
            return [(batch[0], FAILED)]
        mid = len(batch) // 2
        return resilient(batch[:mid], fetch) + resilient(batch[mid:], fetch)


@dataclass
class RefreshReport:
    checked: int = 0
    updated: int = 0
    gone: int = 0
    filtered: int = 0
    errors: int = 0  # repos GitHub would not answer for; checked again next run


def refresh(gh: GitHub, conn: sqlite3.Connection, settings: Settings, *, cutoff: str,
            limit: int | None = None, log: Log = lambda m: None) -> RefreshReport:
    """Look up visible repos last seen before `cutoff` by id: they dropped out of the search
    (deleted, no longer qualify, renamed, or simply missed), so check each one directly."""
    report = RefreshReport()
    exclude = tuple(settings.exclude_topics)
    sql = ("SELECT ghr_id, node_id FROM repos WHERE enrich_status = 'ok' AND node_id IS NOT NULL "
           "AND (last_seen IS NULL OR last_seen < ?) ORDER BY stars DESC")
    todo = conn.execute(sql + (f" LIMIT {int(limit)}" if limit else ""), (cutoff,)).fetchall()
    day, now = today_iso(), now_iso()
    for i in range(0, len(todo), REFRESH_BATCH):
        batch = todo[i:i + REFRESH_BATCH]
        for row, node in resilient(batch, lambda b: gh.nodes_by_ids([r["node_id"] for r in b])):
            report.checked += 1
            if node is FAILED:
                report.errors += 1
            elif node is None or node.get("databaseId") != row["ghr_id"]:
                mark(conn, row["ghr_id"], "gone", now)
                report.gone += 1
            elif reject_reason(node, exclude, require_license=settings.require_license):
                mark(conn, row["ghr_id"], "filtered", now)
                report.filtered += 1
            else:
                upsert_repo(conn, node, now=now, day=day)
                report.updated += 1
        conn.commit()
        log(f"refreshed {report.checked}/{len(todo)}")
    apply_threshold(conn, int(get_meta(conn, "min_stars") or settings.min_stars))
    touch_sync(conn)
    conn.commit()
    return report


@dataclass
class ReadmeReport:
    due: int = 0
    stored: int = 0
    unchanged: int = 0
    none: int = 0  # repos without a README (checked again after `days`)
    failed: int = 0  # repos GitHub would not answer for; not tried again for `days` either


def fetch_readmes(gh: GitHub, conn: sqlite3.Connection, *, days: int = 30,
                  limit: int | None = None, log: Log = lambda m: None) -> ReadmeReport:
    """Fetch READMEs for visible repos that have none yet or whose copy is older than `days`."""
    report = ReadmeReport()
    cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sql = ("SELECT ghr_id, full_name, readme_sha FROM repos WHERE enrich_status = 'ok' "
           "AND full_name NOT LIKE '%~%' AND (readme_at IS NULL OR readme_at < ?) "
           "ORDER BY stars DESC")
    todo = conn.execute(sql + (f" LIMIT {int(limit)}" if limit else ""), (cutoff,)).fetchall()
    report.due = len(todo)
    for i in range(0, len(todo), README_BATCH):
        batch = todo[i:i + README_BATCH]
        def fetch(b: list) -> list:
            got = gh.readmes([(r["ghr_id"], r["full_name"]) for r in b])
            return [got.get(r["ghr_id"]) for r in b]

        now = now_iso()
        for row, found in resilient(batch, fetch):
            if found is FAILED:  # stamp it so the run moves on; it is retried after `days`
                conn.execute("UPDATE repos SET readme_at = ? WHERE ghr_id = ?", (now, row["ghr_id"]))
                report.failed += 1
            elif found is None:
                conn.execute("UPDATE repos SET readme_at = ? WHERE ghr_id = ?", (now, row["ghr_id"]))
                report.none += 1
            elif found[1] == row["readme_sha"]:
                conn.execute("UPDATE repos SET readme_at = ? WHERE ghr_id = ?", (now, row["ghr_id"]))
                report.unchanged += 1
            else:
                conn.execute("UPDATE repos SET readme = ?, readme_sha = ?, readme_at = ? "
                             "WHERE ghr_id = ?",
                             (found[0][:README_MAX_CHARS], found[1], now, row["ghr_id"]))
                report.stored += 1
        touch_sync(conn)
        conn.commit()
        log(f"readmes {min(i + README_BATCH, len(todo))}/{len(todo)}")
    return report
