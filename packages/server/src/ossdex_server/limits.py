"""Abuse protection for a public server with no login: per-client rate limits, caps on requests
in flight, and a limit on query-string size.

Clients are told apart by IP address. Behind Cloudflare and Caddy the TCP peer is always Caddy
(127.0.0.1), so the real address comes from `CF-Connecting-IP` (or, without Cloudflare, the address
Caddy appended to `X-Forwarded-For`). Those headers are believed only when the TCP peer is a
trusted proxy; from anyone else they are ignored, so a client cannot choose its own identity.

State is per process. With N worker processes a client can use up to N times its limit, so the
configured totals are divided by the worker count.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_TRUSTED = ("127.0.0.1", "::1")
MAX_KEYS = 50_000  # distinct clients remembered per limiter


@dataclass(frozen=True)
class Limits:
    enabled: bool = False
    web_per_min: int = 120        # /api requests per client IP per minute, all workers together
    mcp_per_min: int = 600        # /mcp requests per client IP (Claude's servers share a few IPs)
    max_inflight_api: int = 64    # /api requests being handled at once, per process
    max_inflight_mcp: int = 32    # /mcp requests being handled at once, per process
    max_query_string: int = 8192
    workers: int = 1
    trusted_proxies: tuple[str, ...] = DEFAULT_TRUSTED

    @classmethod
    def from_env(cls) -> Limits:
        """On when `OSSDEX_PUBLIC_HOST` is set (a public server) or `OSSDEX_RATE_LIMIT=on`; a server
        you run for yourself on localhost is not rate limited unless you ask."""
        env = os.environ.get
        flag = (env("OSSDEX_RATE_LIMIT") or "").strip().lower()
        enabled = flag in ("on", "true", "1", "yes") or (
            flag == "" and bool((env("OSSDEX_PUBLIC_HOST") or "").strip()))
        proxies = tuple(p.strip() for p in (env("OSSDEX_TRUSTED_PROXIES") or "").split(",") if p.strip())
        return cls(
            enabled=enabled,
            web_per_min=int(env("OSSDEX_RATE_WEB") or cls.web_per_min),
            mcp_per_min=int(env("OSSDEX_RATE_MCP") or cls.mcp_per_min),
            max_inflight_api=int(env("OSSDEX_MAX_INFLIGHT_API") or cls.max_inflight_api),
            max_inflight_mcp=int(env("OSSDEX_MAX_INFLIGHT_MCP") or cls.max_inflight_mcp),
            workers=max(int(env("OSSDEX_WORKERS") or 1), 1),
            trusted_proxies=proxies or DEFAULT_TRUSTED,
        )


class TokenBuckets:
    """One bucket per key: it holds up to `burst` tokens and refills at `per_min` per minute. A
    request takes one token; with none left it must wait. Idle keys are evicted oldest first."""

    def __init__(self, per_min: float, burst: float, clock: Callable[[], float] = time.monotonic,
                 max_keys: int = MAX_KEYS):
        self.rate = per_min / 60.0
        self.burst = max(burst, 1.0)
        self.clock, self.max_keys = clock, max_keys
        self._state: OrderedDict[str, tuple[float, float]] = OrderedDict()

    def take(self, key: str) -> float:
        """0.0 if the request may go ahead, else the seconds until it could."""
        now = self.clock()
        tokens, last = self._state.pop(key, (self.burst, now))
        tokens = min(self.burst, tokens + (now - last) * self.rate)
        if tokens >= 1.0:
            wait, tokens = 0.0, tokens - 1.0
        else:
            wait = (1.0 - tokens) / self.rate if self.rate > 0 else 3600.0
        self._state[key] = (tokens, now)
        while len(self._state) > self.max_keys:
            self._state.popitem(last=False)
        return wait

    def __len__(self) -> int:
        return len(self._state)


def _valid_ip(text: str) -> str | None:
    try:
        return str(ipaddress.ip_address(text.strip()))
    except ValueError:
        return None


def client_key(scope: dict, trusted: tuple[str, ...] = DEFAULT_TRUSTED) -> str:
    """Who is calling. The TCP peer, unless it is a trusted proxy and names the real client in
    `CF-Connecting-IP` or (last entry of) `X-Forwarded-For`. An IPv6 client is identified by its
    /64, since a single user typically controls a whole /64 and could otherwise rotate addresses."""
    peer = (scope.get("client") or ("unknown", 0))[0]
    who = peer
    if peer in trusted:
        headers = {k: v for k, v in scope.get("headers", [])}
        claimed = None
        cf = headers.get(b"cf-connecting-ip")
        if cf:
            claimed = _valid_ip(cf.decode("latin-1"))
        if claimed is None and headers.get(b"x-forwarded-for"):
            claimed = _valid_ip(headers[b"x-forwarded-for"].decode("latin-1").split(",")[-1])
        who = claimed or peer
    addr = _valid_ip(who)
    if addr and ":" in addr:
        return str(ipaddress.ip_network(f"{addr}/64", strict=False).network_address) + "/64"
    return addr or who


def _kind(path: str) -> str | None:
    if path == "/mcp" or path.startswith("/mcp/"):
        return "mcp"
    if path.startswith("/api/"):
        return "api"
    return None  # the UI's static files are not limited here (Caddy and Cloudflare serve them)


class RateLimitMiddleware:
    """Pure ASGI middleware for `/api/*` and `/mcp`. Answers 414 for an oversized query string, 429
    (with Retry-After) for a client over its rate, and 503 when too many requests are already being
    handled; everything else passes through untouched."""

    def __init__(self, app, limits: Limits, clock: Callable[[], float] = time.monotonic):
        self.app, self.limits = app, limits
        w = limits.workers  # each process enforces its share of the totals
        web, mcp = max(limits.web_per_min / w, 1), max(limits.mcp_per_min / w, 1)
        self.buckets = {"api": TokenBuckets(web, max(web / 3, 10), clock),
                        "mcp": TokenBuckets(mcp, max(mcp / 6, 10), clock)}
        self.cap = {"api": limits.max_inflight_api, "mcp": limits.max_inflight_mcp}
        self.inflight = {"api": 0, "mcp": 0}
        self.rejected = {"rate": 0, "busy": 0, "uri": 0}

    async def __call__(self, scope, receive, send):
        kind = _kind(scope["path"]) if scope["type"] == "http" and self.limits.enabled else None
        if kind is None:
            return await self.app(scope, receive, send)
        if len(scope.get("query_string", b"")) > self.limits.max_query_string:
            self.rejected["uri"] += 1
            return await _reply(send, 414, "query string too long")
        wait = self.buckets[kind].take(client_key(scope, self.limits.trusted_proxies))
        if wait:
            self.rejected["rate"] += 1
            return await _reply(send, 429, "rate limit exceeded", retry_after=math.ceil(wait))
        if self.inflight[kind] >= self.cap[kind]:
            self.rejected["busy"] += 1
            return await _reply(send, 503, "server busy", retry_after=2)
        self.inflight[kind] += 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.inflight[kind] -= 1


async def _reply(send, status: int, detail: str, retry_after: int | None = None) -> None:
    body = json.dumps({"detail": detail}).encode()
    headers = [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode()),
               (b"cache-control", b"no-store")]
    if retry_after is not None:
        headers.append((b"retry-after", str(retry_after).encode()))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})
