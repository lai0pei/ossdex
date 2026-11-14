"""What an anonymous caller must not be able to do or see (the server is public, with no login)."""

import sqlite3

import pytest
from fastapi.testclient import TestClient
from ossdex_server import repo_query as rq
from ossdex_server.api import create_app
from ossdex_server.tools import Toolbox


@pytest.fixture
def tb(db, settings):
    return Toolbox(db, settings)


@pytest.fixture
def client(settings, tb):
    return TestClient(create_app(settings, toolbox=tb))


def _demand_rows(path):
    c = sqlite3.connect(path)
    try:
        return c.execute("SELECT COUNT(*) FROM repo_demand").fetchone()[0]
    except sqlite3.OperationalError:  # table absent in this fixture
        return None
    finally:
        c.close()


def test_get_demand_never_touches_the_network_or_writes(tb, db_path, monkeypatch):
    import httpx

    def boom(*a, **k):
        raise AssertionError("the public server must not make network calls")

    monkeypatch.setenv("GITHUB_TOKEN", "ghp_should_never_be_used")
    monkeypatch.setattr(httpx.Client, "send", boom)
    monkeypatch.setattr(httpx.AsyncClient, "send", boom)
    before = _demand_rows(db_path)
    res = tb.call("get_demand", {"full_name": "acme/rag-kit"})
    assert res["fetched"] is False and "no demand data" in res["note"]
    assert _demand_rows(db_path) == before


def test_local_machine_inspection_is_gone(tb, client):
    import ossdex_server.alternatives as alt

    assert not hasattr(alt, "inspect_local_environment")
    assert "inspect_local_environment" not in tb.tools
    assert client.get("/api/local-profile").status_code == 404


def test_alternatives_use_the_callers_setup_not_the_hosts(tb):
    res = tb.call("find_oss_alternatives", {"paid_product": "Notion", "os": "windows",
                                            "habits": ["local-first"], "installed_software": ["winget"]})
    assert res["target_os"] == "windows" and res["installed_software"] == ["winget"]
    assert tb.call("find_oss_alternatives", {"paid_product": "Notion", "os": "auto"})["error"]


def test_readme_excerpt_cuts_at_a_paragraph_and_links_to_github():
    text = "\n\n".join(["word " * 100] * 10)
    excerpt, truncated = rq.readme_excerpt(text)
    assert truncated and len(excerpt) <= rq.README_EXCERPT_CHARS and text.startswith(excerpt)
    assert excerpt.endswith("word")  # cut between paragraphs, trailing space stripped
    assert rq.readme_excerpt("short") == ("short", False)
    assert rq.readme_excerpt(None) == (None, False)
    assert rq.readme_excerpt("x" * 5000)[0] == "x" * rq.README_EXCERPT_CHARS


def test_api_serves_an_excerpt_not_the_full_readme(client, db):
    d = client.get("/api/repos/acme/langchain-agent").json()
    assert "readme" not in d and d["readme_excerpt"] and "readme_truncated" in d
    assert rq.repo_detail(db, "acme/langchain-agent")["readme"]  # internal analysis keeps the full text


@pytest.mark.parametrize("path", [
    "/api/repos?q=" + "a" * 201,
    "/api/alternatives?product=" + "a" * 101,
])
def test_overlong_text_is_rejected_by_the_api(client, path):
    assert client.get(path).status_code == 422


def test_overlong_tool_arguments_are_rejected(tb):
    assert tb.call("search_repos", {"query": "a" * 201})["error"] == "invalid arguments"
    assert tb.call("get_repo", {"full_name": "a/" + "b" * 100})["error"] == "invalid arguments"
    assert tb.call("saas_base", {"idea": "x" * 501})["error"] == "invalid arguments"
    assert tb.call("search_repos", {"query": "a" * 200})["count"] >= 0
    assert tb.call("search_repos", {"languages": ["go"] * 51, "query": "x"})["error"] == "invalid arguments"


def test_server_never_imports_the_collector():
    """The server must not depend on the GitHub-fetching side (and its token handling)."""
    import subprocess
    import sys

    code = ("import sys; from ossdex_server.api import create_app; import ossdex_server.mcp, "
            "ossdex_server.cli; bad = [m for m in sys.modules if m.startswith('ossdex_collector')]; "
            "print(bad); sys.exit(1 if bad else 0)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
