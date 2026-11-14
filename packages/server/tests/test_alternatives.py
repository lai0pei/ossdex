"""Tests for personalized open-source alternative finder and local workflow articulator."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from ossdex_server import alternatives as alt
from ossdex_server.api import create_app
from ossdex_server.mcp import create_mcp
from ossdex_server.tools import Toolbox


@pytest.fixture
def tb(db, settings):
    return Toolbox(db, settings)


@pytest.fixture
def client(settings, tb):
    return TestClient(create_app(settings, toolbox=tb))



def test_find_oss_alternatives_catalog_match(db, settings):
    args = alt.FindAlternativesArgs(
        paid_product="Postman",
        os="macos",
        habits=["cli-first", "keyboard-driven"],
        installed_software=["brew", "nvim", "tmux"],
        limit=5,
    )
    res = alt.find_oss_alternatives(db, args)
    assert res["paid_product"] == "Postman"
    assert res["category"] == "API Client & Testing"
    assert res["target_os"] == "macos"
    assert "cli-first" in res["user_habits"]
    assert len(res["alternatives"]) >= 1

    top = res["alternatives"][0]
    assert "full_name" in top
    assert 0 <= top["fit_score"] <= 100
    assert "fit_badge" in top
    assert "tailored_install_command" in top
    assert isinstance(top["workflow_synergies"], list)

    guide = res["articulation_guide"]
    assert guide["best_overall_pick"] is not None
    assert "Postman" in guide["summary"]


def test_find_oss_alternatives_habit_scoring(db, settings):

    # CLI-first profile
    args_cli = alt.FindAlternativesArgs(
        paid_product="Notion",
        os="macos",
        habits=["cli-first"],
        installed_software=["brew"],
    )
    res_cli = alt.find_oss_alternatives(db, args_cli)

    # Native-GUI profile
    args_gui = alt.FindAlternativesArgs(
        paid_product="Notion",
        os="macos",
        habits=["native-gui"],
        installed_software=["brew"],
    )
    res_gui = alt.find_oss_alternatives(db, args_gui)

    assert len(res_cli["alternatives"]) >= 1
    assert len(res_gui["alternatives"]) >= 1


def test_find_oss_alternatives_freetext_fallback(db, settings):
    args = alt.FindAlternativesArgs(
        paid_product="Proprietary Agent Framework",
        os="linux",
        habits=["self-hosted-docker"],
        installed_software=["docker"],
    )
    res = alt.find_oss_alternatives(db, args)
    assert res["target_os"] == "linux"
    assert res["as_of"] is not None


def test_api_alternatives(client):
    assert client.get("/api/local-profile").status_code == 404  # the server never profiles itself

    r_alt = client.get("/api/alternatives", params={"product": "Notion", "os": "macos"})
    assert r_alt.status_code == 200
    alt_data = r_alt.json()
    assert alt_data["paid_product"] == "Notion"
    assert len(alt_data["alternatives"]) >= 1


def test_mcp_alternatives_tools_and_prompt(tb):
    mcp = create_mcp(tb)

    async def run():
        tools = {t.name for t in await mcp.list_tools()}
        prompts = {p.name for p in await mcp.list_prompts()}
        assert "inspect_local_environment" not in tools
        assert "find_oss_alternatives" in tools
        assert "find_oss_alternative" in prompts

        alts = await mcp.call_tool("find_oss_alternatives", {"paid_product": "Postman", "limit": 3})
        assert "alternatives" in alts[0].text or "Postman" in str(alts)

        prompt_res = await mcp.get_prompt("find_oss_alternative", {"paid_product": "Docker Desktop"})
        text = prompt_res.messages[0].content.text
        assert "Docker Desktop" in text
        assert "inspect_local_environment" not in text
        assert "operating system" in text
        assert "find_oss_alternatives" in text
        assert "15-Minute Migration Plan" in text

    asyncio.run(run())
