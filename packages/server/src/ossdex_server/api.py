"""FastAPI app: JSON API for the UI and the built frontend."""

from __future__ import annotations

import functools
import logging
import os
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from ossdex_core.config import ROOT, Settings, load_settings
from pydantic import ValidationError
from starlette.routing import Route

from . import repo_query as rq
from .cache import ApiCacheMiddleware, ResponseCache
from .db import QueryTimeout, open_db
from .limits import Limits, RateLimitMiddleware
from .mcp import create_mcp, public_host, transport_security
from .search import search
from .tools import Toolbox

log = logging.getLogger("ossdex.api")
SEARCH_DEPTH = 300  # results kept for a text search; the UI pages through them


def web_dist() -> Path:
    """The built UI: `OSSDEX_WEB_DIST` if set, else `web/dist` in the project."""
    return Path(os.environ.get("OSSDEX_WEB_DIST") or ROOT / "web" / "dist")


def filters_dep(
    languages: Annotated[list[str], Query()] = [],  # noqa: B006 (FastAPI copies defaults)
    topics: Annotated[list[str], Query()] = [],  # noqa: B006
    licenses: Annotated[list[str], Query()] = [],  # noqa: B006
    names: Annotated[list[str], Query()] = [],  # noqa: B006
    license_kinds: Annotated[list[str], Query()] = [],  # noqa: B006
    in_lists: Annotated[list[str], Query()] = [],  # noqa: B006
    mentions_paper: bool = False,
    money: Annotated[list[str], Query()] = [],  # noqa: B006
    min_stars: int | None = None,
    max_stars: int | None = None,
    min_forks: int | None = None,
    max_forks: int | None = None,
    created_after: date | None = None,
    pushed_after: date | None = None,
    pushed_before: date | None = None,
    with_readme: bool = False,
    licensed_only: bool = False,
    min_gain: int | None = None,
    gain_days: int = 7,
) -> rq.RepoFilters:
    try:
        return rq.RepoFilters.model_validate(locals())
    except ValidationError as e:
        raise HTTPException(422, str(e)) from e


Filters = Annotated[rq.RepoFilters, Depends(filters_dep)]

_SORT_KEYS: dict[str, Callable[[dict], tuple]] = {
    "stars": lambda d: (-(d["stars"] or 0),),
    "pushed": lambda d: (d["pushed_at"] is None, _neg(d["pushed_at"])),
    "created": lambda d: (d["created_at"] is None, _neg(d["created_at"])),
    "oldest": lambda d: (d["created_at"] is None, d["created_at"] or ""),
    "forks": lambda d: (-(d["forks"] or 0),),
    "gain_1d": lambda d: (d["gain_1d"] is None, -(d["gain_1d"] or 0)),
    "gain_7d": lambda d: (d["gain_7d"] is None, -(d["gain_7d"] or 0)),
    "gain_30d": lambda d: (d["gain_30d"] is None, -(d["gain_30d"] or 0)),
}


def _neg(s: str | None) -> tuple:
    return tuple(-ord(c) for c in (s or ""))


def create_app(settings: Settings | None = None, *, toolbox: Toolbox | None = None,
               limits: Limits | None = None) -> FastAPI:
    settings = settings or load_settings()
    if toolbox is None:
        toolbox = Toolbox(open_db(settings.db_path), settings)
    tb = toolbox
    db = tb.db
    # The MCP server lives in this process, at exactly /mcp. Stateless + JSON replies, so any worker
    # can answer any request (no per-session memory to share between workers).
    mcp = create_mcp(tb, stateless_http=True, json_response=True,
                     transport_security=transport_security(public_host()))
    mcp_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title="ossdex", lifespan=lifespan)
    app.state.toolbox = tb
    app.state.mcp = mcp
    cache = tb.cache = ResponseCache(db)  # shared by the API middleware and the MCP tools
    app.state.cache = cache
    app.add_middleware(ApiCacheMiddleware, cache=cache)
    # added last = outermost: rate limits apply before the cache, so cached replies count too
    app.state.limits = limits or Limits.from_env()
    app.add_middleware(RateLimitMiddleware, limits=app.state.limits)

    @app.exception_handler(QueryTimeout)
    async def busy(_, exc: QueryTimeout) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503, headers={"Retry-After": "5"})

    def get(path: str):
        """`app.get`, with the handler's queries under one time budget (set in the handler's own
        thread, where the thread-local deadline is read)."""
        def deco(fn):
            @functools.wraps(fn)
            def bounded(*args, **kwargs):
                with db.budget():
                    return fn(*args, **kwargs)
            return app.get(path)(bounded)
        return deco

    @get("/api/status")
    def status() -> dict:
        meta = tb.meta()
        return {
            "db_path": str(settings.db_path), **tb.stats(), "as_of": meta["as_of"],
            "min_stars": db.meta("min_stars"),
        }

    @get("/api/repos")
    def repos(f: Filters, q: Annotated[str, Query(max_length=200)] = "", sort: str = "", page: int = Query(1, ge=1),
              page_size: int = Query(50, ge=1, le=100)) -> dict:
        sort = sort or ("relevance" if q.strip() else "stars")
        if sort not in rq.SORTS:
            raise HTTPException(422, f"sort must be one of {rq.SORTS}")
        if not q.strip():
            return rq.list_repos(db, f, "stars" if sort == "relevance" else sort, page, page_size)
        hits = search(db, q, f, SEARCH_DEPTH)
        if sort != "relevance":
            hits.sort(key=_SORT_KEYS[sort])
        start = (page - 1) * page_size
        page_items = rq.enrich_dtos(db, hits[start:start + page_size])
        return {"items": page_items, "total": len(hits), "mode": "search"}

    @get("/api/facets")
    def facets(f: Filters) -> dict:
        return rq.facets(db, f)

    @get("/api/repos/{owner}/{name}")
    def repo(owner: str, name: str) -> dict:
        d = rq.repo_detail(db, f"{owner}/{name}")
        if d is None:
            raise HTTPException(404, f"{owner}/{name} not found")
        return rq.public_detail(d)

    @get("/api/repos/{owner}/{name}/similar")
    def repo_similar(owner: str, name: str, limit: int = Query(6, ge=1, le=20)) -> dict:
        from .search import similar
        res = similar(db, f"{owner}/{name}", limit=limit)
        if res is None:
            raise HTTPException(404, f"{owner}/{name} not found")
        return res

    # Registered before the static mount at "/", which would otherwise swallow /mcp. Adding the
    # routes directly (not mounting the sub-app) keeps the URL /mcp, not /mcp/mcp, with no redirect.
    app.router.routes.extend(mcp_app.routes)
    # /mcp/ answers too (same endpoint, not a redirect: a redirected POST breaks MCP clients)
    app.router.routes.extend(Route(r.path + "/", endpoint=r.endpoint) for r in mcp_app.routes
                             if isinstance(r, Route) and not r.path.endswith("/"))

    dist = web_dist()
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="web")
    return app


def run_server(host: str = "127.0.0.1", port: int = 8200, workers: int = 1) -> None:
    """Serve the UI, API and MCP. `create_app` is passed as an import string so each worker process
    builds its own app (and its own read-only database connection)."""
    import uvicorn

    os.environ["OSSDEX_WORKERS"] = str(workers)  # the workers split the rate limits between them
    # proxy_headers off: uvicorn would replace the client address with X-Forwarded-For (Cloudflare's
    # edge IP), hiding the real TCP peer that limits.client_key needs to decide whom to believe.
    uvicorn.run("ossdex_server.api:create_app", factory=True, host=host, port=port,
                workers=workers, proxy_headers=False, log_level="info")


__all__ = ["Path", "create_app", "run_server"]
