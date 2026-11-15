import pytest
from fastapi.testclient import TestClient
from ossdex_server.api import create_app
from ossdex_server.tools import Toolbox


@pytest.fixture
def tb(db, settings):
    return Toolbox(db, settings)


@pytest.fixture
def client(settings, tb):
    return TestClient(create_app(settings, toolbox=tb))


def test_status(client):
    s = client.get("/api/status").json()
    assert s["repos"] == 6 and s["enriched"] == 5 and s["min_stars"] == "100"
    assert s["history_days"] == 30 and s["require_license"] is True
    assert "index" not in s and s["as_of"].startswith("2026-10-27")
    assert "providers" not in s


def test_repos_list_mode_with_filters(client):
    r = client.get("/api/repos", params={"languages": ["go"], "sort": "stars"}).json()
    assert r["mode"] == "list" and [i["full_name"] for i in r["items"]] == [
        "acme/golang-api", "bare/unenriched"]
    r = client.get("/api/repos", params={"min_gain": 130, "sort": "gain_7d"}).json()
    assert [i["full_name"] for i in r["items"]] == ["acme/langchain-agent", "foo/vector-search"]
    assert r["items"][0]["gain_7d"] == 300
    r = client.get("/api/repos", params={"sort": "gain_1d"}).json()
    assert r["items"][0]["full_name"] == "acme/langchain-agent"
    assert r["items"][0]["gain_1d"] == 50
    # the UI always sends the window as a string
    r = client.get("/api/repos", params={"min_gain": 40, "gain_days": "1"}).json()
    assert [i["full_name"] for i in r["items"]] == ["acme/langchain-agent"]
    r = client.get("/api/repos", params={"min_gain": 500, "gain_days": "30"}).json()
    assert [i["full_name"] for i in r["items"]] == ["acme/langchain-agent"]
    assert client.get("/api/facets", params={"gain_days": "1"}).status_code == 200
    assert client.get("/api/facets", params={"gain_days": "7"}).status_code == 200
    assert client.get("/api/repos", params={"gain_days": "14"}).status_code == 422


def test_repos_search_mode(client):
    r = client.get("/api/repos", params={"q": "AI agents based on langchain"}).json()
    assert r["mode"] == "search" and r["items"][0]["full_name"] == "acme/langchain-agent"
    assert r["items"][0]["why"] and "keyword_only" not in r
    by_stars = client.get("/api/repos", params={"q": "langchain", "sort": "stars"}).json()
    stars = [i["stars"] for i in by_stars["items"]]
    assert stars == sorted(stars, reverse=True)
    assert client.get("/api/repos", params={"sort": "bogus"}).status_code == 422
    for params in ({"sort": "oldest"}, {"q": "langchain", "sort": "oldest"}):
        items = client.get("/api/repos", params=params).json()["items"]
        dated = [i["created_at"] for i in items if i["created_at"]]
        assert dated and dated == sorted(dated)
        assert [i["created_at"] for i in items[len(dated):]] == [None] * (len(items) - len(dated))


def test_pagination_and_names_filter(client):
    r = client.get("/api/repos", params={"page_size": 2, "page": 2}).json()
    assert len(r["items"]) == 2 and r["total"] == 6
    r = client.get("/api/repos", params={"names": ["acme/rag-kit", "Acme/Rust-DB"]}).json()
    assert {i["full_name"] for i in r["items"]} == {"acme/rag-kit", "acme/rust-db"}


def test_facets_and_detail(client):
    f = client.get("/api/facets", params={"languages": ["rust"]}).json()
    assert {x["value"] for x in f["topics"]} == {"rust", "database"}
    d = client.get("/api/repos/acme/langchain-agent").json()
    assert d["readme_excerpt"].startswith("# langchain-agent") and d["history"]
    assert "readme" not in d and d["readme_url"].endswith("/acme/langchain-agent#readme")
    assert client.get("/api/repos/nope/nope").status_code == 404
    assert client.get("/api/repos/gone/deleted").status_code == 404


def test_licensed_only_query_param(client):
    r = client.get("/api/repos", params={"licensed_only": "true"})
    assert r.status_code == 200 and r.json()["total"] == 6  # every fixture repo has a license


def test_license_kinds_query_param(client):
    ok = client.get("/api/repos", params={"license_kinds": "permissive", "min_forks": "300"})
    assert ok.status_code == 200 and ok.json()["total"] == 2
    assert client.get("/api/repos", params={"license_kinds": "bogus"}).status_code == 422


def test_mcp_exposes_tools_prompts_and_a_readme_resource(tb):
    import asyncio

    from ossdex_server.mcp import create_mcp

    mcp = create_mcp(tb)

    async def run():
        tools = {t.name for t in await mcp.list_tools()}
        prompts = {p.name for p in await mcp.list_prompts()}
        saas = await mcp.get_prompt("saas_base", {"idea": "a CRM", "language": "Go"})
        vertical = await mcp.get_prompt(
            "vertical_saas_idea", {"repo_or_niche": "n8n", "target_industry": "Healthcare"}
        )
        art_repo = await mcp.get_prompt(
            "articulate_repo_ideas", {"full_name": "acme/rag-kit", "target_audience": "FinTech"}
        )
        art_stack = await mcp.get_prompt(
            "articulate_stack_ideas", {"repos": "acme/rag-kit, acme/langchain-agent", "domain_hint": "Support Copilot"}
        )
        learn_repo = await mcp.get_prompt(
            "learn_repo_80_20", {"full_name": "acme/rag-kit", "background": "Python beginner"}
        )
        learn_stack = await mcp.get_prompt(
            "learn_stack_80_20", {"repos": "acme/rag-kit, acme/langchain-agent"}
        )
        res = await mcp.read_resource("ossdex://repo/acme/rag-kit")
        listed = await mcp.call_tool("list_repos", {"license_kinds": ["permissive"], "limit": 2})
        return tools, prompts, saas, vertical, art_repo, art_stack, learn_repo, learn_stack, res, listed

    tools, prompts, saas, vertical, art_repo, art_stack, learn_repo, learn_stack, res, listed = asyncio.run(run())
    assert {"find_similar", "compare_repos", "count_repos", "search_repos", "list_repos",
            "get_repo", "get_readme_section", "get_rising", "facets"} <= tools
    assert prompts == {
        "saas_base",
        "freelance_niches",
        "oss_solution",
        "vertical_saas_idea",
        "compose_product_stack",
        "fork_and_rebrand_audit",
        "competitive_moat_analysis",
        "breakout_opportunity_scan",
        "evaluate_product_brief",
        "articulate_repo_ideas",
        "articulate_stack_ideas",
        "learn_repo_80_20",
        "learn_stack_80_20",
    }
    text = saas.messages[0].content.text
    assert "a CRM" in text and "in Go" in text and "permissive" in text and "not legal advice" in text
    v_text = vertical.messages[0].content.text
    assert "n8n" in v_text and "Healthcare" in v_text and "compliance" in v_text
    r_text = art_repo.messages[0].content.text
    assert "acme/rag-kit" in r_text and "FinTech" in r_text and "80/20 Value Split" in r_text
    s_text = art_stack.messages[0].content.text
    assert "acme/rag-kit" in s_text and "Support Copilot" in s_text and "1+1=3" in s_text
    lr_text = learn_repo.messages[0].content.text
    assert "acme/rag-kit" in lr_text and "Python beginner" in lr_text and "80/20" in lr_text and "Must-Know Now" in lr_text
    ls_text = learn_stack.messages[0].content.text
    assert "acme/rag-kit" in ls_text and "80/20" in ls_text and "Integration Surface" in ls_text
    assert "wraps langchain retrievers" in next(iter(res)).content
    assert "acme/" in str(listed)


def test_mcp_inputs_carry_enums_and_descriptions(tb):
    import asyncio

    from ossdex_server.mcp import create_mcp

    tools = {t.name: t.inputSchema["properties"] for t in asyncio.run(create_mcp(tb).list_tools())}
    kinds = str(tools["list_repos"]["license_kinds"])
    assert "permissive" in kinds and "network_copyleft" in kinds and "SaaS" in kinds
    assert "created_year" in str(tools["count_repos"]["group_by"])
    assert "fork" in tools["find_similar"]["min_forks"]["description"].lower()
    assert "stars" in str(tools["list_repos"]["sort"])
    for name in ("search_repos", "list_repos", "find_similar", "count_repos"):
        assert {"max_forks", "pushed_before"} <= tools[name].keys()
    for name in ("search_repos", "list_repos"):
        assert {"in_lists", "mentions_paper", "money"} <= tools[name].keys()
    assert {"find_niches", "opportunity_report"} <= tools.keys()
    assert "gain_1d" in str(tools["list_repos"]["sort"]) and "gain_7d" in str(tools["list_repos"]["sort"])


def test_mcp_get_rising_defaults_to_daily(tb):
    import asyncio

    from ossdex_server.mcp import create_mcp

    mcp = create_mcp(tb)

    async def run():
        res = await mcp.call_tool("get_rising", {})
        return res

    res = asyncio.run(run())
    # FastMCP call_tool returns CallToolResult with content
    assert res is not None


def test_enrichment_filters_over_http(client, db_path):
    import sqlite3

    c = sqlite3.connect(db_path)
    c.executescript("""
        INSERT INTO repo_money(ghr_id, funding, signals, readme_sha) VALUES (2, '[]', '["enterprise"]', 'x');
    """)
    c.commit()
    c.close()
    def names(p):
        return [i["full_name"] for i in client.get("/api/repos", params=p).json()["items"]]

    assert names({"money": ["enterprise"]}) == ["acme/langchain-agent"]
    assert {"value": "enterprise", "count": 1} in client.get("/api/facets").json()["money"]
    d = client.get("/api/repos/acme/langchain-agent").json()
    assert d["money"]["signals"] == ["enterprise"]
