"""ossdex-collector command line: fetch repos from GitHub into the SQLite database."""

from __future__ import annotations

import shutil
import sys
from typing import Annotated

import typer
from ossdex_core.config import ROOT, Settings, load_settings, resolve_token

app = typer.Typer(help="Collect notable open-source GitHub repos into a local SQLite database "
                       "(the web UI and MCP server are the separate ossdex-server)",
                  no_args_is_help=True)
schedule_app = typer.Typer(help="Run `ossdex-collector update` every day with launchd")
app.add_typer(schedule_app, name="schedule")


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(1)


def _github(settings: Settings, budget: int | None):
    from .github import GitHub, GithubError

    token = resolve_token(settings)
    if not token:
        raise _fail("no GitHub token: set GITHUB_TOKEN in .env (a classic token with no "
                    "scopes is enough), or log in with `gh auth login`")
    try:
        return GitHub(token, budget=budget)
    except GithubError as e:
        raise _fail(str(e)) from e


def _log(message: str) -> None:
    typer.echo(message, err=True)


def _guard(fn):
    """Run a collector step; a GitHub limit or error ends the command cleanly (it can resume)."""
    from .github import GithubError

    try:
        return fn()
    except GithubError as e:
        raise _fail(f"{e}") from e


def _print_enrich(r: dict) -> None:
    a, p, t = r["awesome"], r["papers"], r["titles"]
    typer.echo(f"enrich: {a['lists']} awesome lists linking {a['links']} repo entries (total); "
               f"this run read {p['scanned']} READMEs for papers ({p['repos_with_papers']} with "
               f"papers, {p['reading_lists_skipped']} reading lists skipped) and "
               f"{r['money']['scanned']} for business hints ({r['money']['tagged']} tagged); "
               f"{t['titles']} paper titles fetched, {t['pending']} pending")


def _print_discover(r) -> None:
    skipped = ", ".join(f"{n} {why}" for why, n in sorted(r.skipped.items())) or "none"
    typer.echo(f"discover{' (resumed)' if r.resumed else ''}: {r.seen} repos read in {r.pages} "
               f"pages, {r.new} new, {r.updated} updated; skipped: {skipped}")
    if r.truncated:
        typer.echo(f"  {r.truncated} slice(s) held more than 1000 repos on a single day and star "
                   "count; only the first 1000 of each could be read")
    if r.failed_slices:
        typer.echo(f"  {r.failed_slices} slice(s) kept failing on GitHub's side; run again to retry "
                   "just those", err=True)


@app.command()
def discover(
    min_stars: int = typer.Option(None, "--min-stars", help="star threshold (default OSSDEX_MIN_STARS)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="only count what the threshold would collect"),
    budget: int = typer.Option(None, "--budget", help="stop after this many GraphQL points"),
) -> None:
    """Search GitHub for maintained repos above the star threshold (licensed ones unless
    OSSDEX_REQUIRE_LICENSE=false) and store them."""
    from ossdex_core.store import connect

    from .collect import discover as run

    settings = load_settings()
    threshold = settings.min_stars if min_stars is None else min_stars
    gh = _github(settings, budget)
    if dry_run:
        r = _guard(lambda: run(gh, None, settings, min_stars=threshold, dry_run=True, log=_log))
        typer.echo(f"{r.estimate:,} repos match stars >= {threshold:,} in {r.slices} search slices "
                   f"(an upper bound: repos without a license are dropped after reading)")
        pages = -(-r.estimate // 100)
        typer.echo(f"rough estimate: {pages:,} search pages (about {2 * pages:,} GraphQL points) to "
                   f"read them, and about {-(-r.estimate // 20):,} more requests for the READMEs; "
                   "every later run reads the same search pages again to take the daily snapshots")
        if r.estimate > 50_000:
            typer.echo("that is a large run: consider a higher --min-stars first")
        return
    conn = connect(settings.db_path)
    _print_discover(_guard(lambda: run(gh, conn, settings, min_stars=threshold, log=_log)))


@app.command()
def refresh(limit: int = typer.Option(None, help="check at most this many repos"),
            budget: int = typer.Option(None, "--budget")) -> None:
    """Re-check repos the last discover run did not return (deleted, unlicensed, renamed...)."""
    from datetime import UTC, datetime, timedelta

    from ossdex_core.store import connect

    from .collect import refresh as run
    from .collect import run_started

    settings = load_settings()
    conn = connect(settings.db_path)
    cutoff = run_started(conn) or (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    r = _guard(lambda: run(_github(settings, budget), conn, settings, cutoff=cutoff, limit=limit,
                           log=_log))
    typer.echo(f"refresh: {r.checked} checked, {r.updated} updated, {r.gone} gone, "
               f"{r.filtered} no longer qualify" + (f", {r.errors} could not be checked" if r.errors else ""))


@app.command()
def readmes(limit: int = typer.Option(None, help="fetch at most this many READMEs"),
            days: int = typer.Option(30, help="refetch READMEs older than this many days"),
            budget: int = typer.Option(None, "--budget")) -> None:
    """Fetch READMEs for repos that have none yet (biggest repos first)."""
    from ossdex_core.store import connect

    from .collect import fetch_readmes

    settings = load_settings()
    conn = connect(settings.db_path)
    r = _guard(lambda: fetch_readmes(_github(settings, budget), conn, days=days, limit=limit,
                                     log=_log))
    typer.echo(f"readmes: {r.due} due, {r.stored} stored, {r.unchanged} unchanged, "
               f"{r.none} repos without a README" + (f", {r.failed} failed" if r.failed else ""))


@app.command()
def index(full: bool = typer.Option(False, "--full", help="rebuild the search chunks from scratch")) -> None:
    """Build the keyword-search chunks (`update` already does this after fetching)."""
    from ossdex_core.chunks import index_chunks
    from ossdex_core.store import connect

    c = index_chunks(connect(load_settings().db_path), full=full)
    typer.echo(f"chunks: {c['written']} written, {c['removed']} removed, {c['chunks']} total")


@app.command()
def update(
    min_stars: int = typer.Option(None, "--min-stars"),
    budget: int = typer.Option(None, "--budget", help="GraphQL points to spend in this run"),
) -> None:
    """The daily fetch: discover, refresh, READMEs, then enrich (Awesome lists, arXiv papers) and
    rebuild the keyword-search chunks. Safe to stop and run again."""
    from ossdex_core.store import connect

    from .collect import discover as run_discover
    from .collect import fetch_readmes, run_started
    from .collect import refresh as run_refresh

    settings = load_settings()
    threshold = settings.min_stars if min_stars is None else min_stars
    gh = _github(settings, budget)
    conn = connect(settings.db_path)
    try:
        found = _guard(lambda: run_discover(gh, conn, settings, min_stars=threshold, log=_log))
        _print_discover(found)
        if found.finished:
            r = _guard(lambda: run_refresh(gh, conn, settings, cutoff=run_started(conn) or "",
                                           log=_log))
            typer.echo(f"refresh: {r.checked} checked, {r.gone} gone, {r.filtered} no longer "
                       f"qualify" + (f", {r.errors} could not be checked" if r.errors else ""))
        else:  # repos from the failed slices would look "missing": do not judge them yet
            typer.echo("discover is incomplete: skipping refresh until it has finished")
        rd = _guard(lambda: fetch_readmes(gh, conn, log=_log))
        typer.echo(f"readmes: {rd.stored} stored, {rd.unchanged} unchanged, {rd.none} without one"
                   + (f", {rd.failed} failed" if rd.failed else ""))
        from .enrich import enrich_all
        _print_enrich(enrich_all(conn, log=_log))
        from ossdex_core.chunks import index_chunks
        c = index_chunks(conn)
        typer.echo(f"keyword search: {c['written']} chunks written, {c['removed']} removed")
        from ossdex_core.store import finish
        if not finish(conn):
            typer.echo("note: readers held up the WAL checkpoint; it is retried on the next run",
                       err=True)
    finally:
        typer.echo(f"GitHub: {gh.requests} requests, {gh.spent} GraphQL points used", err=True)


@app.command()
def enrich(offline: bool = typer.Option(False, "--offline", help="skip the arXiv title lookup")) -> None:
    """Tag repos with the Awesome lists they are in and the arXiv papers their README links to
    (reads stored READMEs; only the paper titles come from arXiv). Part of `update`."""
    from ossdex_core.store import connect

    from .enrich import enrich_all

    conn = connect(load_settings().db_path)
    try:
        _print_enrich(enrich_all(conn, offline=offline, log=_log))
    finally:
        conn.close()


@app.command()
def demand(
    repos: Annotated[list[str] | None, typer.Argument(help="owner/repo names to look at")] = None,
    topic: str = typer.Option(None, "--topic", help="or the most-starred repos of this topic"),
    top: int = typer.Option(10, "--top", help="how many repos for --topic"),
    days: int = typer.Option(7, "--days", help="skip repos fetched within this many days"),
    budget: int = typer.Option(None, "--budget", help="GraphQL points to spend in this run"),
) -> None:
    """What users of some projects ask for: most-upvoted open issues, help-wanted and bounty counts.
    Costs a GitHub search per repo, so it runs on the repos you name, not in `update`."""
    from ossdex_core.store import connect

    from .demand import fetch_demand, pick_repos

    if not repos and not topic:
        raise _fail("give repo names (owner/repo) or --topic")
    settings = load_settings()
    gh = _github(settings, budget)
    conn = connect(settings.db_path)
    try:
        picked = pick_repos(conn, names=repos or [], topic=topic, top=top)
        if not picked:
            raise _fail("none of these repos is in the database")
        r = _guard(lambda: fetch_demand(gh, conn, picked, days=days, log=_log))
        typer.echo(f"demand: {r.fetched} fetched, {r.fresh} fresh enough to skip"
                   + (f", {r.gone} gone" if r.gone else ""))
        typer.echo("next: use get_demand / opportunity_report in MCP, or open the repo")
    finally:
        typer.echo(f"GitHub: {gh.requests} requests, {gh.spent} GraphQL points used", err=True)
        conn.close()


@app.command()
def prune(yes: bool = typer.Option(False, "--yes", help="do not ask")) -> None:
    """Delete hidden repos (gone, no longer qualifying, below the threshold) for good."""
    from ossdex_core.store import connect
    from ossdex_core.store import prune as run

    conn = connect(load_settings().db_path)
    plan = run(conn, dry_run=True)
    if not plan["repos"]:
        typer.echo("nothing to prune")
        return
    typer.echo(f"would delete {plan['repos']} repos, {plan['chunks']} chunks, "
               f"{plan['snapshots']} star snapshots")
    if not yes and not typer.confirm("delete them?"):
        raise typer.Exit(1)
    run(conn)
    typer.echo("pruned")


def _readonly(path):
    import sqlite3

    if not path.exists():
        raise _fail(f"database not found: {path} (run `ossdex-collector update` first)")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@app.command()
def status() -> None:
    """What is in the database."""
    settings = load_settings()
    conn = _readonly(settings.db_path)

    def scalar(sql: str):
        return conn.execute(sql).fetchone()[0]

    def meta(key: str):
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def has(*tables: str) -> bool:
        got = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        return set(tables) <= got

    by = {r[0]: r[1] for r in conn.execute("SELECT COALESCE(enrich_status,'new'), COUNT(*) FROM repos "
                                           "GROUP BY 1")}
    withreadme = scalar("SELECT COUNT(*) FROM repos WHERE enrich_status='ok' AND readme IS NOT NULL")
    days = scalar("SELECT COALESCE(julianday(MAX(day)) - julianday(MIN(day)), 0) FROM repo_stats")
    typer.echo(f"database: {settings.db_path}")
    typer.echo(f"visible repos: {by.get('ok', 0):,} ({withreadme:,} with a README); "
               f"hidden: {by.get('below', 0):,} below threshold, {by.get('filtered', 0):,} filtered, "
               f"{by.get('gone', 0):,} gone")
    typer.echo(f"star threshold: {meta('min_stars') or 'not set'}; data as of {meta('last_sync')}; "
               f"{int(days)} days of star history")
    if has("repo_lists", "repo_papers"):
        typer.echo(f"enrichment: {scalar('SELECT COUNT(DISTINCT list_id) FROM repo_lists')} awesome "
                   f"lists, {scalar('SELECT COUNT(DISTINCT ghr_id) FROM repo_lists')} listed repos, "
                   f"{scalar('SELECT COUNT(DISTINCT ghr_id) FROM repo_papers')} repos mentioning papers")
    if meta("require_license") == "0":
        unlicensed = scalar("SELECT COUNT(*) FROM repos WHERE enrich_status='ok' AND license IS NULL")
        typer.echo(f"unlicensed repos: kept ({unlicensed:,} visible)")
    else:
        typer.echo("unlicensed repos: skipped")


@schedule_app.command("install")
def schedule_install(hour: int = 4, minute: int = 30,
                     print_only: bool = typer.Option(False, "--print", help="show the plist only"),
                     no_load: bool = typer.Option(False, "--no-load", help="write it but do not load it")) -> None:
    """Install a launchd job that runs `ossdex-collector update` daily (macOS); elsewhere, print a cron line."""
    from . import schedule

    if sys.platform != "darwin":
        uv = shutil.which("uv") or "uv"
        typer.echo("launchd is macOS only. Add this line with `crontab -e`:\n")
        typer.echo(schedule.cron_line(uv=uv, project=ROOT, hour=hour, minute=minute))
        return
    try:
        data = schedule.default_plist(hour, minute)
        if print_only:
            typer.echo(data.decode())
            return
        path = schedule.install(data, load=not no_load)
    except RuntimeError as e:
        raise _fail(str(e)) from e
    typer.echo(f"installed {path}: runs `ossdex-collector update` daily at {hour:02d}:{minute:02d}")


@schedule_app.command("remove")
def schedule_remove() -> None:
    """Remove the daily launchd job."""
    from . import schedule

    typer.echo("removed" if schedule.remove() else "no schedule was installed")
