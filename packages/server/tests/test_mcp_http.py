"""The MCP server mounted in the web app: one process, one URL (/mcp), stateless JSON."""

import asyncio
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from ossdex_server.api import create_app
from ossdex_server.tools import Toolbox

HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


@pytest.fixture(autouse=True)
def public_host(monkeypatch):
    monkeypatch.setenv("OSSDEX_PUBLIC_HOST", "testserver")  # the TestClient's Host header


@pytest.fixture
def app(settings, db):
    return create_app(settings, toolbox=Toolbox(db, settings))


def rpc(client, method, params=None, id=1, headers=None):
    body = {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}
    return client.post("/mcp", json=body, headers=HEADERS | (headers or {}), follow_redirects=False)


def test_mcp_lists_and_calls_tools_over_http(app):
    with TestClient(app) as c:
        init = rpc(c, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                     "clientInfo": {"name": "t", "version": "1"}})
        assert init.status_code == 200 and init.headers["content-type"].startswith("application/json")
        assert init.json()["result"]["serverInfo"]["name"] == "ossdex"
        tools = rpc(c, "tools/list").json()["result"]["tools"]
        assert len(tools) == 27 and "inspect_local_environment" not in {t["name"] for t in tools}
        res = rpc(c, "tools/call", {"name": "search_repos", "arguments": {"query": "langchain"}})
        payload = json.loads(res.json()["result"]["content"][0]["text"])
        assert payload["repos"][0]["repo"] == "acme/langchain-agent"


def test_the_url_is_exactly_mcp_with_no_redirect(app):
    with TestClient(app) as c:
        assert rpc(c, "tools/list").status_code == 200  # a POST to /mcp is answered, not redirected
        assert c.post("/mcp/", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}, headers=HEADERS,
                      follow_redirects=False).status_code == 200  # a pasted trailing slash works too
        # no doubled path: /mcp/mcp is not an MCP endpoint (404, or 405 from the UI mount at "/")
        assert c.post("/mcp/mcp", json={}, headers=HEADERS, follow_redirects=False).status_code in (404, 405)


def test_ui_and_mcp_share_the_port(settings, db, tmp_path, monkeypatch):
    (tmp_path / "index.html").write_text("<html>ossdex-ui</html>")
    monkeypatch.setenv("OSSDEX_WEB_DIST", str(tmp_path))
    with TestClient(create_app(settings, toolbox=Toolbox(db, settings))) as c:
        assert "ossdex-ui" in c.get("/").text  # the static mount at "/" did not swallow /mcp
        assert rpc(c, "tools/list").status_code == 200
        assert c.get("/api/status").status_code == 200


def test_requests_for_an_unknown_host_are_refused(app):
    with TestClient(app) as c:
        res = rpc(c, "tools/list", headers={"Host": "evil.example.com"})
        assert res.status_code in (400, 403, 421)


def test_a_slow_tool_does_not_block_other_requests(app):
    """Tools run in worker threads: a 1 s query must not hold up /api/status on the same loop."""
    tb: Toolbox = app.state.toolbox
    handler = tb.tools["count_repos"].handler

    def slow(args):
        time.sleep(1.0)
        return handler(args)

    tb.tools["count_repos"].handler = slow

    async def run():
        transport = httpx.ASGITransport(app=app)
        async with app.state.mcp.session_manager.run():
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
                body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                        "params": {"name": "count_repos", "arguments": {"group_by": "language"}}}
                slow_call = asyncio.create_task(c.post("/mcp", json=body, headers=HEADERS))
                await asyncio.sleep(0.2)  # the slow call is now running in its thread
                t = time.perf_counter()
                status = await c.get("/api/status")
                fast = time.perf_counter() - t
                done = await slow_call
                return status.status_code, fast, done.status_code

    status, fast, done = asyncio.run(run())
    assert status == 200 and done == 200
    assert fast < 0.5, f"/api/status waited {fast:.2f}s behind a slow MCP call"
