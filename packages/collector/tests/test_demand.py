"""`ossdex demand`: most-upvoted open issues and help-wanted/bounty counts per repo."""

import json
import re

import httpx
import respx
from ossdex_collector import cli
from ossdex_collector.demand import fetch_demand, pick_repos
from ossdex_collector.github import GitHub
from ossdex_core.store import connect, prune
from typer.testing import CliRunner

BASE = "https://gh.test"
ISSUES = {
    "o/busy": [(7, "Add SSO", 40, 12), (9, "Dark mode", 9, 2)],
    "o/quiet": [],
}
COUNTS = {"o/busy": (5, 1, 2), "o/quiet": (0, 0, 0)}  # help wanted, bounty, 💎 Bounty
IDS = {"o/busy": 1, "o/quiet": 2, "o/moved": 99}


def handler(request: httpx.Request) -> httpx.Response:
    handler.queries.append(json.loads(request.content)["query"])
    query = handler.queries[-1]
    data: dict = {"rateLimit": {"cost": 1, "remaining": 4000, "resetAt": "2099-01-01T00:00:00Z"}}
    for i, owner, name in re.findall(r'r(\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)', query):
        full = f"{owner}/{name}"
        if full not in COUNTS:
            data[f"r{i}"] = None  # deleted repo
            data[f"s{i}"] = {"nodes": []}
            continue
        hw, bt, al = COUNTS[full]
        data[f"r{i}"] = {"databaseId": IDS[full], "hw": {"totalCount": hw}, "bt": {"totalCount": bt},
                         "al": {"totalCount": al}}
        data[f"s{i}"] = {"nodes": [
            {"number": n, "title": t, "url": f"https://github.com/{full}/issues/{n}",
             "createdAt": "2026-01-01T00:00:00Z", "comments": {"totalCount": c},
             "reactions": {"totalCount": r}, "labels": {"nodes": [{"name": "feature"}]}}
            for n, t, r, c in ISSUES[full]]}
    return httpx.Response(200, json={"data": data})


handler.queries = []


def world(tmp_path):
    handler.queries.clear()
    mock = respx.mock(base_url=BASE, assert_all_called=False)
    mock.route().mock(side_effect=handler)
    mock.start()
    gh = GitHub("t", base_url=BASE, sleep=lambda s: None, min_interval=0)
    conn = connect(tmp_path / "ossdex.db")
    for i, (name, topics, stars) in enumerate([("o/busy", '["automation"]', 900), ("o/quiet", '["automation"]', 500),
                                                ("o/other", '["db"]', 100)], 1):
        conn.execute("INSERT INTO repos (ghr_id, full_name, topics, stars, enrich_status) VALUES (?,?,?,?, 'ok')",
                     (i, name, topics, stars))
    conn.commit()
    return mock, gh, conn


def test_pick_by_name_and_by_topic(tmp_path):
    mock, _, conn = world(tmp_path)
    try:
        assert pick_repos(conn, names=["O/Busy", "nope/x"]) == [(1, "o/busy")]
        assert pick_repos(conn, topic="automation", top=1) == [(1, "o/busy")]
        assert [n for _, n in pick_repos(conn, topic="AUTOMATION", top=5)] == ["o/busy", "o/quiet"]
    finally:
        mock.stop()


def test_fetch_stores_counts_and_issues_and_skips_fresh(tmp_path):
    mock, gh, conn = world(tmp_path)
    try:
        repos = [(1, "o/busy"), (2, "o/quiet"), (99, "o/moved")]
        r = fetch_demand(gh, conn, repos, days=7)
        assert (r.wanted, r.fetched, r.gone, r.fresh) == (3, 2, 1, 0)
        assert len(handler.queries) == 1  # one batch
        assert '"💎 Bounty"' in handler.queries[0] and "reactions(content: THUMBS_UP)" in handler.queries[0]
        assert "sort:reactions-+1-desc" in handler.queries[0]
        row = conn.execute("SELECT help_wanted, bounties FROM repo_demand WHERE ghr_id = 1").fetchone()
        assert (row[0], row[1]) == (5, 3)  # bounty + 💎 Bounty
        titles = [r[0] for r in conn.execute("SELECT title FROM repo_issues WHERE ghr_id = 1 ORDER BY reactions DESC")]
        assert titles == ["Add SSO", "Dark mode"]
        again = fetch_demand(gh, conn, repos, days=7)
        assert again.fresh == 2 and again.fetched == 0 and again.gone == 1
        ISSUES["o/busy"] = [(7, "Add SSO", 41, 12)]
        conn.execute("UPDATE repo_demand SET fetched_at = '2020-01-01T00:00:00Z'")
        fetch_demand(gh, conn, [(1, "o/busy")], days=7)
        assert [tuple(r) for r in conn.execute("SELECT number, reactions FROM repo_issues WHERE ghr_id = 1")] == [(7, 41)]
    finally:
        ISSUES["o/busy"] = [(7, "Add SSO", 40, 12), (9, "Dark mode", 9, 2)]
        mock.stop()


def test_batches_of_five(tmp_path):
    mock, gh, conn = world(tmp_path)
    try:
        r = fetch_demand(gh, conn, [(100 + i, f"x/y{i}") for i in range(7)], days=7)
        assert r.gone == 7 and len(handler.queries) == 2
    finally:
        mock.stop()


def test_prune_removes_demand(tmp_path):
    mock, gh, conn = world(tmp_path)
    try:
        fetch_demand(gh, conn, [(1, "o/busy")], days=7)
        conn.execute("UPDATE repos SET enrich_status = 'gone' WHERE ghr_id = 1")
        prune(conn)
        for t in ("repo_demand", "repo_issues"):
            assert conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0
    finally:
        mock.stop()


def test_cli_demand(tmp_path, monkeypatch):
    mock, gh, conn = world(tmp_path)
    conn.close()
    try:
        monkeypatch.setattr(cli, "_github", lambda settings, budget: gh)
        monkeypatch.setenv("OSSDEX_DB", str(tmp_path / "ossdex.db"))
        runner = CliRunner()
        assert runner.invoke(cli.app, ["demand"]).exit_code == 1
        out = runner.invoke(cli.app, ["demand", "--topic", "automation", "--top", "2"])
        assert out.exit_code == 0, out.output
        assert "demand: 2 fetched" in out.output
        out = runner.invoke(cli.app, ["demand", "o/busy"])
        assert "1 fresh enough to skip" in out.output
        assert runner.invoke(cli.app, ["demand", "no/such"]).exit_code == 1
    finally:
        mock.stop()
