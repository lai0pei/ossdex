import json

import pytest
from ossdex_server.tools import Toolbox, cap


@pytest.fixture
def tb(db, settings):
    return Toolbox(db, settings)


def test_schemas_cover_all_tools(tb):
    schemas = {s["name"]: s for s in tb.schemas()}
    expected = {
        "search_repos", "list_repos", "get_repo", "get_readme_section",
        "get_rising", "facets", "find_similar", "compare_repos", "count_repos",
        "find_niches", "get_demand", "opportunity_report",
        # 14 new tools
        "classify_artifact", "get_runtime_dependencies", "classify_growth",
        "get_package_adoption", "analyze_forks", "get_maintainer_health",
        "classify_issues", "get_commercial_landscape", "get_company_events",
        "check_name_collision", "license_audit", "platform_compat",
        "saas_base", "evaluate_brief",
        # alternative finder
        "find_oss_alternatives",
    }
    assert set(schemas) == expected
    assert len(schemas) == 27
    assert "query" in schemas["search_repos"]["input_schema"]["properties"]
    assert all(s["description"] for s in schemas.values())


def test_search_repos_tool(tb):
    res = tb.call("search_repos", {"query": "langchain agents", "limit": 3})
    assert res["repos"][0]["repo"] == "acme/langchain-agent"
    assert res["as_of"] == "2026-10-27T06:13:21Z"
    top = res["repos"][0]
    assert top["stars_gained_1d"] == 50 and top["stars_gained_7d"] == 300 and top["stars_gained_30d"] == 800 and top["forks"] == 900


def test_list_repos_tool_and_sort(tb):
    res = tb.call("list_repos", {"languages": ["go"], "sort": "stars"})
    assert [r["repo"] for r in res["repos"]] == ["acme/golang-api", "bare/unenriched"]
    assert res["total_matching"] == 2


def test_get_repo_and_errors(tb):
    res = tb.call("get_repo", {"full_name": "acme/langchain-agent"})
    assert res["readme_intro"].startswith("# langchain-agent")
    assert [h["day"] for h in res["star_history"]] == ["2026-09-27", "2026-10-20", "2026-10-26", "2026-10-27"]
    assert res["open_issues"] == 2 and res["github_url"] == "https://github.com/acme/langchain-agent"
    assert "not in the database" in tb.call("get_repo", {"full_name": "x/y"})["error"]
    assert "note" in tb.call("get_repo", {"full_name": "bare/unenriched"})
    assert tb.call("nope", {})["error"].startswith("unknown tool")
    assert tb.call("search_repos", {})["error"] == "invalid arguments"


def test_get_rising_ranks_by_star_gain(tb):
    res = tb.call("get_rising", {"days": 7})
    assert [r["repo"] for r in res["repos"]] == ["acme/langchain-agent", "foo/vector-search",
                                                  "acme/golang-api"]
    assert res["history_days"] == 30 and res["window_days"] == 7
    res1 = tb.call("get_rising", {"days": 1, "language": "go"})
    assert [r["repo"] for r in res1["repos"]] == ["acme/golang-api"]
    assert "note" in tb.call("get_rising", {"days": 1, "language": "rust"})  # nothing measurable


def test_list_repos_sorts_and_filters_by_growth(tb):
    res = tb.call("list_repos", {"min_gain": 130, "sort": "gain_7d"})
    assert [r["repo"] for r in res["repos"]] == ["acme/langchain-agent", "foo/vector-search"]
    res_daily = tb.call("list_repos", {"sort": "gain_1d"})
    assert [r["repo"] for r in res_daily["repos"]][:3] == ["acme/langchain-agent", "foo/vector-search", "acme/golang-api"]
    assert res["history_days"] == 30


def test_facets_tool_and_readme_tool(tb):
    f = tb.call("facets", {})
    assert {x["value"] for x in f["languages"]} >= {"go", "python", "rust"}
    r = tb.call("get_readme_section", {"full_name": "acme/rag-kit", "query": "langchain"})
    assert "langchain" in r["sections"][0]["text"].lower()


def test_cap_trims_lists_to_the_size_limit():
    res = cap({"repos": [{"repo": f"a/{i}", "description": "x" * 500} for i in range(100)]}, 5000)
    assert len(json.dumps(res)) <= 5200 and "truncated" in res and len(res["repos"]) < 100


def test_unlicensed_repos_are_flagged_for_the_model(db_path, settings):
    import sqlite3

    from ossdex_server.db import ReadDb
    from ossdex_server.tools import llm_repo

    d = ReadDb(db_path)
    try:
        licensed = Toolbox(d, settings)
        assert licensed.stats()["require_license"] is True
    finally:
        d.close()
    with sqlite3.connect(db_path) as c:
        c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('require_license', '0')")
    d = ReadDb(db_path)
    try:
        tb = Toolbox(d, settings)
        assert tb.stats()["require_license"] is False
    finally:
        d.close()
    assert llm_repo({"full_name": "a/b", "language": None, "stars": 1, "forks": 0, "description": None,
                     "topics": [], "license": None, "pushed_at": None, "gain_1d": None,
                     "gain_7d": None})["license"] == "none (all rights reserved)"


def test_find_similar_compare_and_count_tools(tb):
    sim = tb.call("find_similar", {"full_name": "acme/langchain-agent", "limit": 2})
    assert sim["repos"][0]["repo"] == "acme/rag-kit"
    assert "error" in tb.call("find_similar", {"full_name": "no/such"})

    cmp_ = tb.call("compare_repos", {"full_names": ["acme/golang-api", "acme/rust-db", "x/missing"]})
    assert [r["repo"] for r in cmp_["repos"]] == ["acme/golang-api", "acme/rust-db"]
    assert cmp_["missing"] == ["x/missing"]
    row = cmp_["repos"][0]
    assert row["forks_per_100_stars"] == 8.0 and row["license_kind"] == "permissive"
    assert "closed" in row["license_note"] and row["days_since_push"] is not None
    assert "error" in tb.call("compare_repos", {"full_names": ["acme/golang-api"]})  # needs 2+

    cnt = tb.call("count_repos", {"group_by": "license_kind"})
    assert cnt["groups"] == [{"value": "permissive", "repos": 6, "total_stars": 21100,
                              "median_stars": 2750}] and "permissive" in cnt["notes"]
    assert tb.call("count_repos", {"group_by": "language", "min_forks": 300})["total_matching"] == 2


def test_max_forks_and_pushed_before_filters(tb):
    got = tb.call("list_repos", {"max_forks": 200})
    assert {r["repo"] for r in got["repos"]} == {
        "acme/rag-kit", "acme/rust-db", "bare/unenriched", "foo/vector-search"}
    got = tb.call("list_repos", {"pushed_before": "2026-10-15"})  # a never-pushed repo is excluded
    assert {r["repo"] for r in got["repos"]} == {"acme/rag-kit", "acme/rust-db"}
    got = tb.call("list_repos", {"min_forks": 100, "max_forks": 400, "languages": ["python"],
                                 "pushed_after": "2026-10-01", "pushed_before": "2026-10-23"})
    assert {r["repo"] for r in got["repos"]} == {"foo/vector-search"}


def test_license_filters_and_paging_in_the_tools(tb):
    got = tb.call("list_repos", {"license_kinds": ["permissive"], "min_forks": 300})
    assert {r["repo"] for r in got["repos"]} == {"acme/golang-api", "acme/langchain-agent"}
    assert tb.call("list_repos", {"license_kinds": ["copyleft"]})["total_matching"] == 0
    page1 = tb.call("list_repos", {"limit": 2})
    page2 = tb.call("list_repos", {"limit": 2, "offset": 2})
    assert not {r["repo"] for r in page1["repos"]} & {r["repo"] for r in page2["repos"]}
    s1 = tb.call("search_repos", {"query": "langchain", "limit": 1})
    s2 = tb.call("search_repos", {"query": "langchain", "limit": 1, "offset": 1})
    assert s1["repos"][0]["repo"] != s2["repos"][0]["repo"]
    assert "error" in tb.call("list_repos", {"license_kinds": ["nonsense"]})
    assert "license_note" in tb.call("get_repo", {"full_name": "acme/rag-kit"})
    assert tb.call("get_repo", {"full_name": "acme/rag-kit"})["license_kind"] == "permissive"
