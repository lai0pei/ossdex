"""Load test for a running ossdex-server.

Closed loop: N virtual users each send a request, wait for the reply, and send the next one until
the duration ends. By default every request is *uncached* (random filters and search words), which
is the worst case; `--cached` draws from a small fixed pool instead, to see the cache's effect.

    uv run python scripts/loadtest.py --base-url http://127.0.0.1:8200 --scenario mix -c 20 -d 30
    uv run python scripts/loadtest.py --scenario mcp -c 20 --host-header ossdex.example.com

Scenarios:
  mix  60% list, 25% text search, 15% repo detail / MCP tool call   (the web UI plus some MCP)
  mcp  100% MCP tools/call (search_repos, list_repos, get_repo, find_similar, count_repos)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import time
from collections import Counter

import httpx

MCP_HEADERS = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}
SORTS = ["stars", "pushed", "forks", "gain_7d", "created"]


class Pools:
    def __init__(self, languages: list[str], topics: list[str], repos: list[str]):
        self.languages, self.topics, self.repos = languages, topics, repos


async def discover(client: httpx.AsyncClient) -> Pools:
    facets = (await client.get("/api/facets")).json()
    languages = [x["value"] for x in facets.get("languages", [])][:40] or ["Python"]
    topics = [x["value"] for x in facets.get("topics", [])][:300] or ["ai"]
    page = (await client.get("/api/repos", params={"page_size": 100})).json()
    repos = [r["full_name"] for r in page["items"]] or ["acme/example"]
    return Pools(languages, topics, repos)


def make_requests(pools: Pools, rng: random.Random, scenario: str, cached: bool):
    """Return a function that yields one (label, method, url, params, json_body) per call."""
    def pick(seq):
        return rng.choice(seq[:5]) if cached else rng.choice(seq)

    def stars():
        return rng.choice([1000, 5000]) if cached else rng.randint(1000, 30000)

    def words():
        return " ".join(pick(pools.topics) for _ in range(rng.choice([1, 2, 2, 3])))

    def rpc(tool, arguments):
        body = {"jsonrpc": "2.0", "id": rng.randint(1, 10**9), "method": "tools/call",
                "params": {"name": tool, "arguments": arguments}}
        return (f"mcp:{tool}", "POST", "/mcp", None, body)

    def list_req():
        return ("list", "GET", "/api/repos", {"sort": rng.choice(SORTS[:2] if cached else SORTS),
                "languages": pick(pools.languages), "min_stars": stars(),
                "page": 1 if cached else rng.randint(1, 5), "page_size": 50}, None)

    def search_req():
        return ("search", "GET", "/api/repos", {"q": words(), "min_stars": stars()}, None)

    def detail_req():
        return ("detail", "GET", f"/api/repos/{pick(pools.repos)}", None, None)

    def mcp_req():
        kind = rng.choices(["search_repos", "list_repos", "get_repo", "find_similar", "count_repos"],
                           [40, 25, 15, 10, 10])[0]
        if kind == "search_repos":
            return rpc(kind, {"query": words(), "limit": 10})
        if kind == "list_repos":
            return rpc(kind, {"languages": [pick(pools.languages)], "min_stars": stars(), "limit": 10})
        if kind == "get_repo":
            return rpc(kind, {"full_name": pick(pools.repos)})
        if kind == "find_similar":
            return rpc(kind, {"full_name": pick(pools.repos), "limit": 6})
        return rpc(kind, {"group_by": rng.choice(["language", "license_kind", "created_year"]),
                          "min_stars": stars()})

    def mix():
        r = rng.random()
        if r < 0.60:
            return list_req()
        if r < 0.85:
            return search_req()
        return detail_req() if r < 0.925 else mcp_req()

    return mcp_req if scenario == "mcp" else mix


async def user(client, pools, scenario, cached, seed, deadline, results, host_header):
    rng = random.Random(seed)
    nxt = make_requests(pools, rng, scenario, cached)
    extra = {"Host": host_header} if host_header else {}
    while time.monotonic() < deadline:
        label, method, url, params, body = nxt()
        headers = extra | (MCP_HEADERS if body else {})
        started = time.perf_counter()
        try:
            resp = await client.request(method, url, params=params, json=body, headers=headers)
            status = resp.status_code
            if status == 200 and body:  # an MCP reply can be 200 with a JSON-RPC error inside
                status = 200 if "error" not in resp.json() else 599
        except httpx.HTTPError as e:
            status = type(e).__name__
        results.append((label, status, time.perf_counter() - started))


def pct(values: list[float], q: float) -> float:
    return statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1] if len(values) > 1 else (
        values[0] if values else 0.0)


def report(results, elapsed: float, label: str) -> dict:
    ok = [t for _, s, t in results if s == 200]
    codes = Counter(str(s) for _, s, _ in results)
    summary = {"requests": len(results), "rps": round(len(results) / elapsed, 1),
               "ok": len(ok), "statuses": dict(codes),
               "p50_ms": round(1000 * pct(ok, 50)), "p95_ms": round(1000 * pct(ok, 95)),
               "p99_ms": round(1000 * pct(ok, 99)), "max_ms": round(1000 * max(ok, default=0))}
    print(f"\n== {label}")
    print(f"{summary['requests']} requests in {elapsed:.0f}s = {summary['rps']} req/s; statuses {summary['statuses']}")
    print(f"latency of the 200s: p50 {summary['p50_ms']} ms  p95 {summary['p95_ms']} ms  "
          f"p99 {summary['p99_ms']} ms  max {summary['max_ms']} ms")
    by = {}
    for lab, s, t in results:
        if s == 200:
            by.setdefault(lab, []).append(t)
    for lab, ts in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print(f"  {lab:22} n={len(ts):5d}  p50 {1000 * pct(ts, 50):6.0f} ms  p95 {1000 * pct(ts, 95):6.0f} ms")
    return summary


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base-url", default="http://127.0.0.1:8200")
    ap.add_argument("--scenario", choices=["mix", "mcp"], default="mix")
    ap.add_argument("-c", "--concurrency", type=int, default=20)
    ap.add_argument("-d", "--duration", type=float, default=30.0, help="seconds")
    ap.add_argument("--cached", action="store_true", help="draw from a small pool (cache-friendly)")
    ap.add_argument("--host-header", help="Host to send (the OSSDEX_PUBLIC_HOST value, for /mcp)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--json", action="store_true", help="also print the summary as one JSON line")
    args = ap.parse_args()

    limits = httpx.Limits(max_connections=args.concurrency + 5)
    async with httpx.AsyncClient(base_url=args.base_url, limits=limits, timeout=30) as client:
        pools = await discover(client)
        results: list = []
        t0 = time.monotonic()
        await asyncio.gather(*(user(client, pools, args.scenario, args.cached, args.seed * 1000 + i,
                                    t0 + args.duration, results, args.host_header)
                               for i in range(args.concurrency)))
        elapsed = time.monotonic() - t0
    label = (f"{args.scenario}, {args.concurrency} concurrent, "
             f"{'cache-friendly' if args.cached else 'uncached'}")
    summary = report(results, elapsed, label)
    if args.json:
        print(json.dumps({"label": label, **summary}))


if __name__ == "__main__":
    asyncio.run(main())
