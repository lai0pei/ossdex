"""A per-process response cache.

The data changes when the collector commits (once a day), while the same lists, facets and searches
are asked for all day. Entries are kept as serialized bytes (no aliasing of mutable results) in an
LRU bounded by count and total size, and the whole cache is dropped when the database changes
(`ReadDb.data_version`, checked at most every few seconds).
"""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from urllib.parse import parse_qsl

from .db import ReadDb

MAX_ENTRIES = 2000
MAX_BYTES = 64 * 1024 * 1024
RECHECK_SECONDS = 5.0


class ResponseCache:
    def __init__(self, db: ReadDb, *, max_entries: int = MAX_ENTRIES, max_bytes: int = MAX_BYTES,
                 recheck: float = RECHECK_SECONDS, clock: Callable[[], float] = time.monotonic):
        self.db = db
        self.max_entries, self.max_bytes, self.recheck, self.clock = (
            max_entries, max_bytes, recheck, clock)
        self._data: OrderedDict[object, bytes] = OrderedDict()
        self._bytes = 0
        self._lock = threading.Lock()
        self._version: int | None = None
        self._checked = float("-inf")
        self.hits = self.misses = 0

    def _refresh(self) -> None:
        now = self.clock()
        if now - self._checked < self.recheck:
            return
        self._checked = now
        version = self.db.data_version()
        with self._lock:
            if version != self._version:
                self._data.clear()
                self._bytes = 0
                self._version = version

    def snapshot(self) -> int | None:
        """The database version a request starts under. Pass it to `put` so an answer computed
        before a collector commit is never stored after the cache was cleared for that commit."""
        self._refresh()
        return self._version

    def get(self, key: object) -> bytes | None:
        self._refresh()
        with self._lock:
            value = self._data.get(key)
            if value is None:
                self.misses += 1
                return None
            self._data.move_to_end(key)
            self.hits += 1
            return value

    def put(self, key: object, value: bytes, version: int | None = None) -> None:
        if len(value) > self.max_bytes // 8:  # never let one huge answer flush everything else
            return
        self._refresh()
        with self._lock:
            if version is not None and version != self._version:
                return  # the database changed while this was being computed
            old = self._data.pop(key, None)
            if old is not None:
                self._bytes -= len(old)
            self._data[key] = value
            self._bytes += len(value)
            while len(self._data) > self.max_entries or self._bytes > self.max_bytes:
                _, evicted = self._data.popitem(last=False)
                self._bytes -= len(evicted)

    def __len__(self) -> int:
        return len(self._data)

    # ---- MCP tool results ----
    @staticmethod
    def tool_key(name: str, arguments: dict | None) -> tuple:
        return ("tool", name, json.dumps(arguments or {}, sort_keys=True, default=str))

    def get_tool(self, name: str, arguments: dict | None) -> dict | None:
        raw = self.get(self.tool_key(name, arguments))
        return None if raw is None else json.loads(raw)

    def put_tool(self, name: str, arguments: dict | None, result: dict,
                 version: int | None = None) -> None:
        if "error" not in result:  # failures are not remembered
            self.put(self.tool_key(name, arguments), json.dumps(result, default=str).encode(),
                     version)


class ApiCacheMiddleware:
    """Pure ASGI middleware: caches 200 replies to `GET /api/*` and tells browsers and CDNs how long
    they may keep them. The key is the path plus the sorted query string, so `?a=1&b=2` and
    `?b=2&a=1` share an entry."""

    def __init__(self, app, cache: ResponseCache, *, max_age: int = 300, status_max_age: int = 60):
        self.app, self.cache = app, cache
        self.max_age, self.status_max_age = max_age, status_max_age

    def _cacheable(self, scope) -> bool:
        return (scope["type"] == "http" and scope["method"] == "GET"
                and scope["path"].startswith("/api/"))

    @staticmethod
    def _key(scope) -> tuple:
        query = tuple(sorted(parse_qsl(scope["query_string"].decode("latin-1"),
                                       keep_blank_values=True)))
        return ("api", scope["path"], query)

    def _cache_control(self, scope) -> bytes:
        age = self.status_max_age if scope["path"] == "/api/status" else self.max_age
        return f"public, max-age={age}".encode()

    async def __call__(self, scope, receive, send):
        if not self._cacheable(scope):
            return await self.app(scope, receive, send)
        key = self._key(scope)
        version = self.cache.snapshot()
        hit = self.cache.get(key)
        if hit is not None:
            head, body = _unpack(hit)
            headers = [*head, (b"content-length", str(len(body)).encode()),
                       (b"cache-control", self._cache_control(scope)), (b"x-cache", b"hit")]
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send({"type": "http.response.body", "body": body})
            return

        started: dict = {}
        chunks: list[bytes] = []

        async def capture(message):
            if message["type"] == "http.response.start":
                started.update(status=message["status"], headers=list(message.get("headers", [])))
                if message["status"] == 200:
                    message = {**message, "headers": [*started["headers"],
                                                      (b"cache-control", self._cache_control(scope)),
                                                      (b"x-cache", b"miss")]}
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False) and started.get("status") == 200:
                    keep = [(k, v) for k, v in started["headers"]
                            if k.lower() not in (b"content-length", b"cache-control")]
                    self.cache.put(key, _pack(keep, b"".join(chunks)), version)
            await send(message)

        await self.app(scope, receive, capture)


def _pack(headers: list[tuple[bytes, bytes]], body: bytes) -> bytes:
    head = json.dumps([[k.decode("latin-1"), v.decode("latin-1")] for k, v in headers]).encode()
    return len(head).to_bytes(4, "big") + head + body


def _unpack(blob: bytes) -> tuple[list[tuple[bytes, bytes]], bytes]:
    n = int.from_bytes(blob[:4], "big")
    head = json.loads(blob[4:4 + n])
    return [(k.encode("latin-1"), v.encode("latin-1")) for k, v in head], blob[4 + n:]
