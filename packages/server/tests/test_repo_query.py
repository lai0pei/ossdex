import sqlite3

import pytest
from ossdex_server import repo_query as rq
from ossdex_server.db import DbError, ReadDb

from testsupport.helpers import build_fixture_db


def names(res):
    return [i["full_name"] for i in res["items"]]


def test_default_hides_gone_filtered_and_below(db):
    res = rq.list_repos(db, rq.RepoFilters())
    assert set(names(res)) == {"acme/golang-api", "acme/langchain-agent", "acme/rag-kit",
                               "acme/rust-db", "bare/unenriched", "foo/vector-search"}
    assert res["total"] == 6
    for hidden in ("gone/deleted", "old/archived-go", "acme/fork-py", "low/below-threshold"):
        assert hidden not in names(res)


def test_language_is_case_insensitive(db):
    res = rq.list_repos(db, rq.RepoFilters(languages=["go"]))
    assert set(names(res)) == {"acme/golang-api", "bare/unenriched"}  # "Go" and "GO"


def test_topics_require_all(db):
    assert names(rq.list_repos(db, rq.RepoFilters(topics=["langchain"]))) == ["acme/langchain-agent"]
    assert rq.list_repos(db, rq.RepoFilters(topics=["langchain", "go"]))["total"] == 0


def test_star_range_license_and_readme_filters(db):
    assert rq.list_repos(db, rq.RepoFilters(min_stars=3000))["total"] == 3
    assert rq.list_repos(db, rq.RepoFilters(max_stars=1000))["total"] == 1
    assert rq.list_repos(db, rq.RepoFilters(licenses=["apache-2.0"]))["total"] == 1
    with_readme = rq.list_repos(db, rq.RepoFilters(with_readme=True))
    assert "bare/unenriched" not in names(with_readme) and with_readme["total"] == 5


def test_date_filters(db):
    from datetime import date

    assert rq.list_repos(db, rq.RepoFilters(created_after=date(2025, 1, 1)))["total"] == 2
    assert set(names(rq.list_repos(db, rq.RepoFilters(pushed_after=date(2026, 10, 15))))) == {
        "acme/golang-api", "acme/langchain-agent", "foo/vector-search"}


def test_growth_is_measured_from_the_newest_snapshot(db):
    by = {i["full_name"]: i for i in rq.list_repos(db, rq.RepoFilters())["items"]}
    assert by["acme/langchain-agent"]["gain_1d"] == 50 and by["acme/langchain-agent"]["gain_7d"] == 300
    assert by["acme/golang-api"]["gain_1d"] == 20 and by["acme/golang-api"]["gain_7d"] == 120
    assert by["foo/vector-search"]["gain_1d"] == 30 and by["foo/vector-search"]["gain_7d"] == 150
    assert by["acme/rust-db"]["gain_1d"] is None  # only today's snapshot
    assert by["acme/rust-db"]["gain_7d"] is None


def test_min_gain_filter(db):
    got = rq.list_repos(db, rq.RepoFilters(min_gain=130, gain_days=7))
    assert set(names(got)) == {"acme/langchain-agent", "foo/vector-search"}
    got = rq.list_repos(db, rq.RepoFilters(min_gain=40, gain_days=1))
    assert names(got) == ["acme/langchain-agent"]


def test_min_gain_without_any_snapshots_matches_nothing(tmp_path):
    path = build_fixture_db(tmp_path / "empty.db")
    c = sqlite3.connect(path)
    c.execute("DELETE FROM repo_stats")
    c.commit()
    c.close()
    d = ReadDb(path)
    assert d.latest_day() is None and d.history_days() == 0
    assert rq.list_repos(d, rq.RepoFilters(min_gain=1))["total"] == 0
    assert rq.list_repos(d, rq.RepoFilters())["total"] == 6
    d.close()


def test_sorts_put_missing_values_last(db):
    by_gain = names(rq.list_repos(db, rq.RepoFilters(), sort="gain_7d"))
    assert by_gain[:3] == ["acme/langchain-agent", "foo/vector-search", "acme/golang-api"]
    assert by_gain[3:] == ["acme/rust-db", "acme/rag-kit", "bare/unenriched"]  # no gain: by stars
    assert names(rq.list_repos(db, rq.RepoFilters(), sort="gain_1d"))[:3] == [
        "acme/langchain-agent", "foo/vector-search", "acme/golang-api"]
    assert names(rq.list_repos(db, rq.RepoFilters(), sort="stars"))[0] == "acme/langchain-agent"
    assert names(rq.list_repos(db, rq.RepoFilters(), sort="forks"))[:2] == [
        "acme/langchain-agent", "acme/golang-api"]


def test_sort_oldest(db):
    items = rq.list_repos(db, rq.RepoFilters(), sort="oldest")["items"]
    dated = [i["created_at"] for i in items if i["created_at"]]
    assert dated == sorted(dated) and items[0]["full_name"] == "acme/rust-db"
    assert items[-1]["created_at"] is None  # no creation date -> last
    newest = [i["created_at"] for i in rq.list_repos(db, rq.RepoFilters(), sort="created")["items"]
              if i["created_at"]]
    assert dated == newest[::-1]


def test_pagination(db):
    p1 = rq.list_repos(db, rq.RepoFilters(), page=1, page_size=4)
    p2 = rq.list_repos(db, rq.RepoFilters(), page=2, page_size=4)
    assert len(p1["items"]) == 4 and len(p2["items"]) == 2 and p1["total"] == 6


def test_facets_ignore_own_filter_and_merge_case(db):
    f = rq.facets(db, rq.RepoFilters(languages=["rust"]))
    langs = {x["value"]: x["count"] for x in f["languages"]}
    assert langs["go"] == 2 and langs["python"] == 3 and "rust" in langs  # not limited to rust
    topics = {x["value"] for x in f["topics"]}
    assert topics == {"rust", "database"}  # topic facet follows the language filter


def test_repo_detail(db):
    d = rq.repo_detail(db, "ACME/Langchain-Agent")
    assert d["full_name"] == "acme/langchain-agent" and d["has_readme"] is True
    assert d["github_url"] == "https://github.com/acme/langchain-agent"
    assert [h["day"] for h in d["history"]] == ["2026-09-27", "2026-10-20", "2026-10-26", "2026-10-27"]
    assert d["history"][-1]["stars"] == 9000 and d["open_issues"] == 2
    assert d["readme"].startswith("# langchain-agent") and d["card"].startswith("acme/langchain-agent")
    assert rq.repo_detail(db, "gone/deleted") is None
    assert rq.repo_detail(db, "low/below-threshold") is None
    assert rq.repo_detail(db, "nope/nope") is None


def test_schema_version_is_checked(db_path):
    c = sqlite3.connect(db_path)
    c.execute("PRAGMA user_version = 7")
    c.commit()
    c.close()
    try:
        ReadDb(db_path)
        raise AssertionError("expected DbError")
    except DbError as e:
        assert "schema version 7" in str(e)


def test_db_is_read_only(db):
    try:
        db.conn.execute("DELETE FROM repos")
        raise AssertionError("write succeeded")
    except sqlite3.OperationalError as e:
        assert "readonly" in str(e)


def test_reader_works_while_the_collector_holds_a_write_transaction(db_path):
    from ossdex_core.store import connect

    writer = connect(db_path)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("UPDATE repos SET stars = 1 WHERE ghr_id = 1")  # uncommitted
    reader = ReadDb(db_path)
    try:
        assert reader.scalar("SELECT stars FROM repos WHERE ghr_id = 1") == 5000  # not 1
        assert rq.list_repos(reader, rq.RepoFilters())["total"] == 6
    finally:
        reader.close()
        writer.rollback()
        writer.close()


def test_licensed_only_skips_repos_without_a_license(db_path):
    with sqlite3.connect(db_path) as c:
        c.execute("UPDATE repos SET license = NULL WHERE full_name = 'acme/rag-kit'")
    d = ReadDb(db_path)
    try:
        everyone = names(rq.list_repos(d, rq.RepoFilters(), "stars", 1, 50))
        licensed = names(rq.list_repos(d, rq.RepoFilters(licensed_only=True), "stars", 1, 50))
        assert "acme/rag-kit" in everyone and "acme/rag-kit" not in licensed
        assert len(licensed) == len(everyone) - 1
    finally:
        d.close()


def test_license_kinds_filter(db_path):
    with sqlite3.connect(db_path) as c:
        c.execute("UPDATE repos SET license = 'AGPL-3.0' WHERE full_name = 'acme/rag-kit'")
        c.execute("UPDATE repos SET license = 'NOASSERTION' WHERE full_name = 'acme/rust-db'")
        c.execute("UPDATE repos SET license = 'GPL-3.0-only' WHERE full_name = 'acme/golang-api'")
        c.execute("UPDATE repos SET license = NULL WHERE full_name = 'bare/unenriched'")
    d = ReadDb(db_path)
    try:
        def kinds(*k):
            return set(names(rq.list_repos(d, rq.RepoFilters(license_kinds=list(k)), "stars", 1, 50)))

        assert kinds("permissive") == {"acme/langchain-agent", "foo/vector-search"}
        assert kinds("network_copyleft") == {"acme/rag-kit"}
        assert kinds("copyleft") == {"acme/golang-api"}
        assert kinds("other") == {"acme/rust-db"}
        assert kinds("none") == {"bare/unenriched"}
        assert kinds("permissive", "other") == {"acme/langchain-agent", "foo/vector-search",
                                                  "acme/rust-db"}
        dto = rq.list_repos(d, rq.RepoFilters(license_kinds=["copyleft"]), "stars", 1, 5)["items"][0]
        assert dto["license_kind"] == "copyleft"
    finally:
        d.close()


def test_min_forks_and_offset(db):
    big = rq.list_repos(db, rq.RepoFilters(min_forks=300), "stars", 1, 50)
    assert set(names(big)) == {"acme/golang-api", "acme/langchain-agent"}
    first = names(rq.list_repos(db, rq.RepoFilters(), "stars", 1, 2))
    second = names(rq.list_repos(db, rq.RepoFilters(), "stars", 1, 2, offset=2))
    assert len(first) == 2 and not set(first) & set(second)
    assert first + second == names(rq.list_repos(db, rq.RepoFilters(), "stars", 1, 4))


def test_grouped_counts(db):
    by_lang = rq.grouped_counts(db, rq.RepoFilters(), "language")
    langs = {g["value"]: g for g in by_lang["groups"]}
    assert by_lang["total_matching"] == 6 and langs["python"]["repos"] == 3
    assert langs["python"]["total_stars"] == 9000 + 1200 + 2500
    assert langs["python"]["median_stars"] == 2500
    assert langs["go"]["repos"] == 2  # "Go" and "GO" are one language
    kinds = {g["value"]: g["repos"] for g in rq.grouped_counts(db, rq.RepoFilters(), "license_kind")["groups"]}
    assert kinds == {"permissive": 6}
    topics = {g["value"] for g in rq.grouped_counts(db, rq.RepoFilters(), "topic")["groups"]}
    assert {"go", "langchain", "rust"} <= topics
    years = {g["value"] for g in rq.grouped_counts(db, rq.RepoFilters(), "created_year")["groups"]}
    assert {"2022", "2024"} <= years
    only_go = rq.grouped_counts(db, rq.RepoFilters(languages=["go"]), "language")
    assert only_go["total_matching"] == 2
    with pytest.raises(ValueError):
        rq.grouped_counts(db, rq.RepoFilters(), "stars")


def test_enrichment_filters_facets_detail(db_path):
    import sqlite3

    from ossdex_server.db import ReadDb
    from ossdex_server.repo_query import RepoFilters, facets, list_repos, repo_detail

    conn = sqlite3.connect(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS repo_lists (ghr_id INTEGER, list_id INTEGER, section TEXT,
                                               PRIMARY KEY (ghr_id, list_id));
        CREATE TABLE IF NOT EXISTS repo_papers (ghr_id INTEGER, arxiv_id TEXT, PRIMARY KEY (ghr_id, arxiv_id));
        CREATE TABLE IF NOT EXISTS papers (arxiv_id TEXT PRIMARY KEY, title TEXT, published TEXT, fetched_at TEXT);
        INSERT INTO repo_lists VALUES (2, 4, 'Agents');
        INSERT INTO repo_papers VALUES (3, '2301.00001');
        INSERT INTO papers VALUES ('2301.00001', 'A Paper', NULL, NULL);
    """)
    conn.commit()
    conn.close()
    db = ReadDb(db_path)
    got = list_repos(db, RepoFilters(in_lists=["ACME/rust-db"]))
    assert [r["full_name"] for r in got["items"]] == ["acme/langchain-agent"]
    got = list_repos(db, RepoFilters(mentions_paper=True))
    assert [r["full_name"] for r in got["items"]] == ["acme/rag-kit"]
    assert facets(db, RepoFilters())["lists"] == [{"value": "acme/rust-db", "count": 1}]
    assert repo_detail(db, "acme/langchain-agent")["lists"][0]["section"] == "Agents"
    assert repo_detail(db, "acme/rag-kit")["papers"][0]["title"] == "A Paper"
    db.close()


def test_old_database_without_enrichment_tables(db_path):
    import sqlite3

    from ossdex_server.db import ReadDb
    from ossdex_server.repo_query import RepoFilters, facets, repo_detail

    conn = sqlite3.connect(db_path)
    conn.executescript("DROP TABLE repo_lists; DROP TABLE repo_papers; DROP TABLE papers;")
    conn.close()
    db = ReadDb(db_path)
    assert not db.has_enrich
    assert facets(db, RepoFilters())["lists"] == []
    assert repo_detail(db, "acme/rag-kit")["papers"] == []
    db.close()
