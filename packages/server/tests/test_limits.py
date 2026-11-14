"""Abuse protection: rate limits per client, the proxy-trust rule, and caps on requests in flight."""

import asyncio

import httpx
import pytest
from ossdex_server.api import create_app
from ossdex_server.limits import Limits, RateLimitMiddleware, TokenBuckets, client_key
from ossdex_server.tools import Toolbox


def scope(peer, **headers):
    return {"client": (peer, 5000), "headers": [(k.replace("_", "-").encode(), v.encode())
                                                for k, v in headers.items()]}


# ---- token buckets ----
def test_a_bucket_allows_a_burst_then_makes_the_client_wait():
    now = [0.0]
    b = TokenBuckets(per_min=60, burst=3, clock=lambda: now[0])  # 1 token per second
    assert [b.take("a") for _ in range(3)] == [0.0, 0.0, 0.0]
    wait = b.take("a")
    assert 0.9 < wait <= 1.0  # the fourth must wait for a token
    assert b.take("b") == 0.0  # other clients are unaffected
    now[0] = 1.0
    assert b.take("a") == 0.0  # refilled one token
    assert b.take("a") > 0


def test_tokens_do_not_pile_up_beyond_the_burst():
    now = [0.0]
    b = TokenBuckets(per_min=60, burst=2, clock=lambda: now[0])
    b.take("a")
    now[0] = 3600.0  # an hour idle
    assert [b.take("a") for _ in range(3)] == [0.0, 0.0, pytest.approx(1.0, abs=0.01)]


def test_idle_clients_are_evicted_oldest_first():
    b = TokenBuckets(60, 2, max_keys=3)
    for k in "abcd":
        b.take(k)
    assert len(b) == 3 and "a" not in b._state


# ---- who is the client? ----
def test_a_direct_client_is_its_tcp_address_and_headers_are_ignored():
    s = scope("203.0.113.9", cf_connecting_ip="198.51.100.1", x_forwarded_for="198.51.100.2")
    assert client_key(s) == "203.0.113.9"  # a spoofed header from a non-proxy changes nothing


def test_a_trusted_proxy_vouches_for_the_cloudflare_header():
    assert client_key(scope("127.0.0.1", cf_connecting_ip="198.51.100.1")) == "198.51.100.1"
    # without Cloudflare: the address Caddy appended is the last X-Forwarded-For entry
    assert client_key(scope("127.0.0.1", x_forwarded_for="6.6.6.6, 198.51.100.7")) == "198.51.100.7"
    assert client_key(scope("127.0.0.1")) == "127.0.0.1"
    assert client_key(scope("127.0.0.1", cf_connecting_ip="not-an-ip")) == "127.0.0.1"


def test_extra_trusted_proxies_can_be_configured():
    s = scope("10.0.0.5", cf_connecting_ip="198.51.100.1")
    assert client_key(s) == "10.0.0.5"
    assert client_key(s, trusted=("10.0.0.5",)) == "198.51.100.1"


def test_ipv6_clients_share_a_bucket_per_64():
    a = client_key(scope("127.0.0.1", cf_connecting_ip="2001:db8:1:2:aaaa::1"))
    b = client_key(scope("127.0.0.1", cf_connecting_ip="2001:db8:1:2:bbbb::9"))
    c = client_key(scope("127.0.0.1", cf_connecting_ip="2001:db8:1:3::1"))
    assert a == b == "2001:db8:1:2::/64" and c != a


# ---- the middleware, with a stub app ----
async def ok_app(scope_, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


def client_for(app, peer="203.0.113.9"):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=(peer, 5000)),
                             base_url="http://test")


def limited(app=ok_app, **kw):
    return RateLimitMiddleware(app, Limits(enabled=True, **kw))


def test_over_the_rate_gets_429_with_retry_after_and_other_paths_are_free():
    async def run():
        mw = limited(web_per_min=30)  # burst = 10
        async with client_for(mw) as c:
            codes = [(await c.get("/api/status")).status_code for _ in range(14)]
            blocked = await c.get("/api/status")
            static = await c.get("/index.html")
            other = await client_for(mw, "203.0.113.77").__aenter__()
            fresh = await other.get("/api/status")
            await other.aclose()
        return codes, blocked, static.status_code, fresh.status_code

    codes, blocked, static, fresh = asyncio.run(run())
    assert codes[:10] == [200] * 10 and set(codes[10:]) == {429}
    assert blocked.status_code == 429 and int(blocked.headers["retry-after"]) >= 1
    assert blocked.json() == {"detail": "rate limit exceeded"}
    assert static == 200 and fresh == 200  # static files and other clients are not limited


def test_mcp_and_api_have_separate_budgets():
    async def run():
        mw = limited(web_per_min=6, mcp_per_min=600)  # api burst 10, mcp burst 100
        async with client_for(mw) as c:
            for _ in range(12):
                await c.get("/api/status")
            api = (await c.get("/api/status")).status_code
            mcp = (await c.post("/mcp", json={})).status_code
        return api, mcp

    assert asyncio.run(run()) == (429, 200)


def test_a_spoofed_cloudflare_header_does_not_buy_a_fresh_bucket():
    async def run():
        mw = limited(web_per_min=6)
        async with client_for(mw, "203.0.113.9") as c:  # not a trusted proxy
            codes = [(await c.get("/api/status", headers={"CF-Connecting-IP": f"198.51.100.{i}"}))
                     .status_code for i in range(1, 40)]
        return codes

    codes = asyncio.run(run())
    assert codes.count(200) == 10 and codes[-1] == 429


def test_behind_a_trusted_proxy_each_real_client_has_its_own_bucket():
    async def run():
        mw = limited(web_per_min=6)
        out = {}
        async with client_for(mw, "127.0.0.1") as c:  # Caddy
            for who in ("198.51.100.1", "198.51.100.2"):
                out[who] = [(await c.get("/api/status", headers={"CF-Connecting-IP": who})).status_code
                            for _ in range(12)]
        return out

    out = asyncio.run(run())
    assert all(codes.count(200) == 10 and codes[-1] == 429 for codes in out.values())


def test_workers_split_the_configured_total():
    async def run():
        mw = limited(web_per_min=120, workers=4)  # 30 a minute each, burst 10
        async with client_for(mw) as c:
            return [(await c.get("/api/x")).status_code for _ in range(12)]

    codes = asyncio.run(run())
    assert codes.count(200) == 10


def test_a_huge_query_string_is_refused():
    async def run():
        async with client_for(limited(max_query_string=100)) as c:
            return (await c.get("/api/repos?q=" + "a" * 500)).status_code, \
                   (await c.get("/api/repos?q=ok")).status_code

    assert asyncio.run(run()) == (414, 200)


def test_too_many_requests_in_flight_get_503():
    async def run():
        gate = asyncio.Event()

        async def slow(scope_, receive, send):
            await gate.wait()
            await ok_app(scope_, receive, send)

        mw = limited(slow, max_inflight_mcp=2, mcp_per_min=6000)
        async with client_for(mw) as c:
            held = [asyncio.create_task(c.post("/mcp", json={})) for _ in range(2)]
            await asyncio.sleep(0.05)
            refused = await c.post("/mcp", json={})
            api_fine = asyncio.create_task(c.get("/api/status"))  # a different class: not affected
            await asyncio.sleep(0.05)
            gate.set()
            done = [r.status_code for r in await asyncio.gather(*held)]
            after = (await c.post("/mcp", json={})).status_code
            return refused, done, (await api_fine).status_code, after, mw.inflight

    refused, done, api, after, inflight = asyncio.run(run())
    assert refused.status_code == 503 and refused.headers["retry-after"] == "2"
    assert done == [200, 200] and api == 200 and after == 200
    assert inflight == {"api": 0, "mcp": 0}  # the counters come back down


def test_a_disabled_limiter_does_nothing():
    async def run():
        async with client_for(RateLimitMiddleware(ok_app, Limits(enabled=False, web_per_min=1))) as c:
            return {(await c.get("/api/x")).status_code for _ in range(50)}

    assert asyncio.run(run()) == {200}


# ---- configuration and the real app ----
def test_limits_are_on_for_a_public_server_and_off_for_a_local_one(monkeypatch):
    for var in ("OSSDEX_PUBLIC_HOST", "OSSDEX_RATE_LIMIT", "OSSDEX_RATE_WEB", "OSSDEX_WORKERS"):
        monkeypatch.delenv(var, raising=False)
    assert Limits.from_env().enabled is False
    monkeypatch.setenv("OSSDEX_PUBLIC_HOST", "ossdex.example.com")
    assert Limits.from_env().enabled is True
    monkeypatch.setenv("OSSDEX_RATE_LIMIT", "off")
    assert Limits.from_env().enabled is False
    monkeypatch.setenv("OSSDEX_RATE_LIMIT", "on")
    monkeypatch.setenv("OSSDEX_RATE_WEB", "30")
    monkeypatch.setenv("OSSDEX_WORKERS", "3")
    lim = Limits.from_env()
    assert lim.enabled and lim.web_per_min == 30 and lim.workers == 3


def test_the_real_app_limits_api_and_mcp_calls(settings, db, monkeypatch):
    monkeypatch.setenv("OSSDEX_PUBLIC_HOST", "test")
    app = create_app(settings, toolbox=Toolbox(db, settings),
                     limits=Limits(enabled=True, web_per_min=6, mcp_per_min=6))

    async def run():
        transport = httpx.ASGITransport(app=app, client=("203.0.113.9", 1))
        async with app.router.lifespan_context(app), \
                httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            api = [(await c.get("/api/status")).status_code for _ in range(12)]
            hdrs = {"Accept": "application/json, text/event-stream"}
            rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
            mcp = [(await c.post("/mcp", json=rpc, headers=hdrs)).status_code for _ in range(12)]
        return api, mcp

    api, mcp = asyncio.run(run())
    assert api.count(200) == 10 and api[-1] == 429
    assert mcp.count(200) == 10 and mcp[-1] == 429
