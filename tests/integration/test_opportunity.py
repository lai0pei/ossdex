"""Niche finder, money signals and the opportunity report."""

import json
import sqlite3

import pytest
from ossdex_collector.enrich import money_signals, money_tags
from ossdex_core.store import connect, prune, upsert_repo
from ossdex_server import repo_query as rq
from ossdex_server.db import ReadDb
from ossdex_server.tools import Toolbox


def test_niches_sum_the_gains_of_a_topics_repos(db):
    res = rq.niches(db, rq.RepoFilters(), days=7, min_repos=1, limit=50)
    by = {n["topic"]: n for n in res["niches"]}
    gain2 = rq.repo_detail(db, "acme/langchain-agent")["gain_7d"]
    assert by["langchain"]["repos"] == 1 and by["langchain"]["gain"] == gain2 > 0
    assert by["langchain"]["top_repos"][0]["repo"] == "acme/langchain-agent"
    assert "rag" in by
    assert "go" not in by  # a language name is not a niche
    gains = [n["gain"] for n in res["niches"]]
    assert gains == sorted(gains, reverse=True)  # growth order
    assert res["window_days"] == 7 and res["history_days"] > 0


def test_niches_min_repos_sort_and_filters(db):
    assert rq.niches(db, rq.RepoFilters(), min_repos=2)["niches"] == []
    res = rq.niches(db, rq.RepoFilters(languages=["python"]), min_repos=1, sort="size")
    assert {n["topic"] for n in res["niches"]} >= {"langchain", "rag", "vector"}
    assert "go" not in {n["topic"] for n in res["niches"]}
    sizes = [n["total_stars"] for n in res["niches"]]
    assert sizes == sorted(sizes, reverse=True)
    res = rq.niches(db, rq.RepoFilters(), days=30, min_repos=1, sort="momentum")
    assert res["window_days"] == 30 and "note" not in res


def test_niches_say_when_history_is_short(db_path):
    c = sqlite3.connect(db_path)
    c.execute("DELETE FROM repo_stats WHERE day < '2026-10-20'")
    c.commit()
    c.close()
    res = rq.niches(ReadDb(db_path), rq.RepoFilters(), days=30, min_repos=1)
    assert "days of star history" in res["note"]


@pytest.mark.parametrize(("text", "tags"), [
    ("Try our managed cloud, see pricing.", ["hosted_cloud", "pricing"]),
    ("Enterprise Edition with SSO. Professional services available.", ["enterprise", "support_consulting"]),
    ("A tiny library. Runs on Google Cloud and the cloud-native stack.", []),
    ("Compares model pricing across providers.", []),
    ("Commercial support plans and a cloud-hosted offering", ["hosted_cloud", "support_consulting"]),
])
def test_money_tags(text, tags):
    assert money_tags(text) == tags


def money_db(tmp_path):
    conn = connect(tmp_path / "t.db")
    for i, (name, readme) in enumerate([("a/cloudy", "Use our hosted version. See pricing."),
                                        ("b/plain", "Just a library."), ("c/sponsored", "Plain.")], 1):
        conn.execute("INSERT INTO repos (ghr_id, full_name, topics, readme, readme_sha, stars, "
                     "enrich_status) VALUES (?,?,?,?,?,?, 'ok')", (i, name, "[]", readme, f"s{i}", 10))
    conn.execute("INSERT INTO repo_money(ghr_id, funding) VALUES (3, ?)",
                 (json.dumps([{"platform": "GITHUB", "url": "https://github.com/sponsors/c"}]),))
    conn.commit()
    return conn


def test_money_signals_are_incremental_and_keep_funding(tmp_path):
    conn = money_db(tmp_path)
    assert money_signals(conn) == {"scanned": 3, "tagged": 1}
    assert json.loads(conn.execute("SELECT signals FROM repo_money WHERE ghr_id = 1").fetchone()[0]) == [
        "hosted_cloud", "pricing"]
    assert "sponsors/c" in conn.execute("SELECT funding FROM repo_money WHERE ghr_id = 3").fetchone()[0]
    assert money_signals(conn)["scanned"] == 0
    conn.execute("UPDATE repos SET readme = 'Enterprise edition', readme_sha = 'new' WHERE ghr_id = 2")
    assert money_signals(conn) == {"scanned": 1, "tagged": 1}
    conn.execute("UPDATE repos SET enrich_status = 'gone' WHERE ghr_id IN (1, 3)")
    prune(conn)
    assert [r[0] for r in conn.execute("SELECT ghr_id FROM repo_money")] == [2]
    conn.close()


def test_upsert_stores_funding_links(tmp_path):
    from ossdex_core.store import now_iso, today_iso
    conn = connect(tmp_path / "t.db")
    node = {"databaseId": 7, "id": "R_7", "nameWithOwner": "o/r", "stargazerCount": 5,
            "fundingLinks": [{"platform": "GITHUB", "url": "https://github.com/sponsors/o"}]}
    upsert_repo(conn, node, now=now_iso(), day=today_iso())
    assert json.loads(conn.execute("SELECT funding FROM repo_money WHERE ghr_id = 7").fetchone()[0])[0][
        "platform"] == "GITHUB"
    upsert_repo(conn, {**node, "fundingLinks": []}, now=now_iso(), day=today_iso())
    assert conn.execute("SELECT funding FROM repo_money WHERE ghr_id = 7").fetchone()[0] == "[]"
    conn.close()


@pytest.fixture
def money_world(db_path):
    c = sqlite3.connect(db_path)
    c.executescript("""
        INSERT INTO repo_money(ghr_id, funding, signals, readme_sha) VALUES
          (2, '[]', '["hosted_cloud","enterprise"]', 'x'),
          (1, '[{"platform":"GITHUB","url":"https://github.com/sponsors/acme"}]', '[]', 'x');
        INSERT INTO repo_demand VALUES (2, 7, 2, '2026-10-26T00:00:00Z');
        INSERT INTO repo_issues VALUES (2, 11, 'Add SSO', 'https://x/11', 40, 5, '["feature"]', '2026-01-01'),
                                       (2, 12, 'Dark mode', 'https://x/12', 9, 1, '[]', '2026-02-01');
    """)
    c.commit()
    c.close()
    return ReadDb(db_path)


def test_money_filters_facets_and_detail(money_world):
    db = money_world

    def names(f):
        return [r["full_name"] for r in rq.list_repos(db, f)["items"]]

    assert names(rq.RepoFilters(money=["enterprise"])) == ["acme/langchain-agent"]
    assert names(rq.RepoFilters(money=["sponsors"])) == ["acme/golang-api"]
    assert sorted(names(rq.RepoFilters(money=["sponsors", "hosted_cloud"]))) == [
        "acme/golang-api", "acme/langchain-agent"]
    assert names(rq.RepoFilters(has_bounties=True)) == ["acme/langchain-agent"]
    facets = {m["value"]: m["count"] for m in rq.facets(db, rq.RepoFilters())["money"]}
    assert facets == {"hosted_cloud": 1, "enterprise": 1, "sponsors": 1}
    d = rq.repo_detail(db, "acme/langchain-agent")
    assert d["money"]["signals"] == ["hosted_cloud", "enterprise"]
    assert d["demand"]["bounties"] == 2 and [i["title"] for i in d["demand"]["top_issues"]] == [
        "Add SSO", "Dark mode"]
    assert rq.repo_detail(db, "acme/rag-kit")["money"] is None


def test_tools_niches_demand_and_report(money_world, settings):
    tb = Toolbox(money_world, settings)
    res = tb.call("find_niches", {"min_repos": 1, "limit": 5})
    assert res["niches"] and res["niches"][0]["gain"] >= res["niches"][-1]["gain"]
    got = tb.call("get_demand", {"full_name": "acme/langchain-agent"})
    assert got["bounties"] == 2 and got["top_issues"][0]["reactions"] == 40
    assert "no demand data" in tb.call("get_demand", {"full_name": "acme/rag-kit"})["note"]
    assert "error" in tb.call("get_demand", {"full_name": "nope/nope"})
    rep = tb.call("opportunity_report", {"language": "python", "min_repos": 1, "limit": 3})
    assert rep["niches"] and "how_to_read" in rep
    agent = next(r for n in rep["niches"] for r in n["rising"] if r["repo"] == "acme/langchain-agent")
    assert agent["business_hints"] == ["hosted_cloud", "enterprise"] and agent["demand"]["bounties"] == 2
    assert all(r["repo"] != "acme/golang-api" for n in rep["niches"] for r in n["rising"])  # not python
    rep = tb.call("opportunity_report", {"topic": "langchain", "min_repos": 1})
    assert [n["topic"] for n in rep["niches"]] and all("demand" in r for n in rep["niches"]
                                                      for r in n["rising"][:1])
    assert tb.call("get_repo", {"full_name": "acme/langchain-agent"})["business_hints"]


def test_old_database_without_money_and_demand_tables(db_path):
    c = sqlite3.connect(db_path)
    c.executescript("DROP TABLE repo_money; DROP TABLE repo_demand; DROP TABLE repo_issues;")
    c.close()
    db = ReadDb(db_path)
    assert not db.has_money and not db.has_demand and db.has_enrich
    assert rq.facets(db, rq.RepoFilters())["money"] == []
    assert rq.list_repos(db, rq.RepoFilters(money=["enterprise"]))["items"] == []
    assert rq.repo_detail(db, "acme/rag-kit")["demand"] is None
    assert rq.niches(db, rq.RepoFilters(), min_repos=1)["niches"]
