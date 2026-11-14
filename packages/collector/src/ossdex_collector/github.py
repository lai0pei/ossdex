"""GitHub client for the collector: GraphQL search and lookups with rate-limit handling.

Requests go one at a time. A primary-limit reset that is close is waited out; a far one raises
`RateLimited` so the run stops cleanly and can be resumed. Secondary limits and 5xx errors back off
and retry. The token is only ever sent in the Authorization header: it is never logged.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from datetime import datetime

import httpx

log = logging.getLogger("ossdex.github")

API = "https://api.github.com"
MAX_AUTO_WAIT = 120.0  # seconds we wait for a limit reset on our own
MIN_REMAINING = 50  # stop issuing requests when fewer points are left
RETRIES = 3
SEARCH_PAGE = 100
MIN_SEARCH_PAGE = 25  # GitHub timing out on big pages: halve down to this, then give up
README_BATCH = 20
DEMAND_ISSUES = 10
DEMAND_BATCH = 5  # repos per query: each one adds a search
# (alias, labels): GitHub's usual ones, plus the label Algora puts on bounty issues
DEMAND_LABELS = (("hw", ["help wanted"]), ("bt", ["bounty"]), ("al", ["💎 Bounty"]))
README_FILES = ("README.md", "readme.md", "README.rst", "README")


class GithubError(RuntimeError):
    pass


class ServerError(GithubError):
    """GitHub could not answer (5xx, or a body that is not JSON) even after retries."""


class RateLimited(GithubError):
    def __init__(self, reset_at: float | None, message: str):
        super().__init__(message)
        self.reset_at = reset_at  # epoch seconds, if known


class BudgetExhausted(GithubError):
    pass


REPO_FIELDS = """
  databaseId id nameWithOwner url description homepageUrl
  primaryLanguage { name }
  repositoryTopics(first: 20) { nodes { topic { name } } }
  licenseInfo { spdxId key }
  stargazerCount forkCount openIssues: issues(states: OPEN) { totalCount }
  pushedAt createdAt isArchived isFork isMirror isTemplate
  fundingLinks { platform url }
"""

RATE = "rateLimit { cost remaining resetAt }"

SEARCH = ("query($q: String!, $first: Int!, $after: String) { " + RATE +
          " search(query: $q, type: REPOSITORY, first: $first, after: $after) {"
          " repositoryCount pageInfo { hasNextPage endCursor }"
          " nodes { ... on Repository { " + REPO_FIELDS + " } } } }")
COUNT = ("query($q: String!) { " + RATE +
         " search(query: $q, type: REPOSITORY, first: 1) { repositoryCount } }")
TOP = ("query($q: String!) { " + RATE +
       " search(query: $q, type: REPOSITORY, first: 1) {"
       " repositoryCount nodes { ... on Repository { stargazerCount } } } }")
NODES = ("query($ids: [ID!]!) { " + RATE +
         " nodes(ids: $ids) { ... on Repository { " + REPO_FIELDS + " } } }")


def _epoch(iso: str | None) -> float | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).timestamp()
    except ValueError:
        return None


class GitHub:
    def __init__(self, token: str, *, client: httpx.Client | None = None,
                 sleep: Callable[[float], None] = time.sleep,
                 now: Callable[[], float] = time.time, min_interval: float = 0.4,
                 budget: int | None = None, base_url: str = API):
        if not token:
            raise GithubError("a GitHub token is required: set GITHUB_TOKEN in .env "
                              "(or log in with `gh auth login`)")
        self.http = client or httpx.Client(
            timeout=60, headers={"Authorization": f"Bearer {token}", "User-Agent": "ossdex",
                                 "Accept": "application/vnd.github+json"})
        self.sleep, self.now, self.min_interval = sleep, now, min_interval
        self.budget, self.base_url = budget, base_url.rstrip("/")
        self.remaining: int | None = None
        self.reset_at: float | None = None
        self.spent = 0
        self.requests = 0
        self._last = 0.0
        self.search_first = SEARCH_PAGE

    # ---- plumbing ----

    def _before(self) -> None:
        if self.budget is not None and self.spent >= self.budget:
            raise BudgetExhausted(f"used the {self.budget}-point budget for this run")
        if self.remaining is not None and self.remaining < MIN_REMAINING:
            self._wait_for_reset(self.reset_at, f"only {self.remaining} points left")
            self.remaining = None
        gap = self.min_interval - (self.now() - self._last)
        if gap > 0:
            self.sleep(gap)

    def _wait_for_reset(self, reset_at: float | None, why: str) -> None:
        wait = (reset_at - self.now() + 1) if reset_at else 60.0
        if wait > MAX_AUTO_WAIT:
            raise RateLimited(reset_at, f"GitHub rate limit ({why}); resets in {int(wait)}s. "
                                        "Run the command again later to resume.")
        log.info("rate limit (%s): waiting %.0fs", why, max(wait, 0))
        self.sleep(max(wait, 0))

    def _send(self, method: str, url: str, **kw) -> httpx.Response:
        for attempt in range(1, RETRIES + 2):
            self._before()
            try:
                resp = self.http.request(method, url, **kw)
            except httpx.TransportError as e:
                if attempt > RETRIES:
                    raise GithubError(f"network error: {type(e).__name__}") from e
                self.sleep(2.0 * attempt)
                continue
            finally:
                self._last = self.now()
                self.requests += 1
            if resp.status_code in (403, 429):
                retry_after = resp.headers.get("retry-after")
                reset = resp.headers.get("x-ratelimit-reset")
                if resp.headers.get("x-ratelimit-remaining") == "0" and reset:
                    self._wait_for_reset(float(reset), "primary limit")
                elif retry_after:
                    self._wait_for_reset(self.now() + float(retry_after), "retry-after")
                elif resp.status_code == 403 and "rate limit" not in resp.text.lower():
                    raise GithubError(f"GitHub {resp.status_code}: {resp.text[:200]}")
                else:
                    self._wait_for_reset(self.now() + 60.0 * attempt, "secondary limit")
                if attempt > RETRIES:
                    raise RateLimited(None, "GitHub keeps rate limiting; try again later")
                continue
            if resp.status_code >= 500:
                if attempt > RETRIES:
                    raise ServerError(f"GitHub {resp.status_code} after {RETRIES} retries")
                self.sleep(2.0 ** attempt)
                continue
            return resp
        raise GithubError("unreachable")  # pragma: no cover

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        """Run a query and return its `data`. A NOT_FOUND error just leaves that field null (a
        deleted repo); any other error (a timeout, "something went wrong", a blocked repo) is
        retried with a backoff and then raised, so a half-answered query is never used."""
        for attempt in range(1, RETRIES + 2):
            resp = self._send("POST", f"{self.base_url}/graphql",
                              json={"query": query, "variables": variables or {}})
            if resp.status_code == 401:
                raise GithubError("GitHub rejected the token (401): check GITHUB_TOKEN")
            if resp.status_code != 200:
                raise GithubError(f"GitHub GraphQL {resp.status_code}: {resp.text[:200]}")
            try:
                payload = resp.json()
            except ValueError:  # an HTML error page, an empty or cut-off body
                payload = None
            if not isinstance(payload, dict):
                if attempt > RETRIES:
                    raise ServerError("GitHub sent a response that is not JSON (HTTP 200)")
                self.sleep(2.0 ** attempt)
                continue
            data = payload.get("data")
            errors = [e for e in (payload.get("errors") or []) if (e or {}).get("type") != "NOT_FOUND"]
            if data is not None:
                self._note_rate(data.get("rateLimit"))
            if any((e or {}).get("type") == "RATE_LIMITED" for e in errors):
                raise RateLimited(None, "GitHub GraphQL rate limit reached")
            if data is not None and not errors:
                return data
            if attempt > RETRIES:
                raise GithubError(f"GitHub GraphQL error: {json.dumps(errors)[:300]}")
            self.sleep(2.0 ** attempt)
        raise GithubError("unreachable")  # pragma: no cover

    def _note_rate(self, rate: dict | None) -> None:
        if rate:
            self.spent += int(rate.get("cost") or 0)
            self.remaining = rate.get("remaining")
            self.reset_at = _epoch(rate.get("resetAt"))

    # ---- search ----

    def search_count(self, q: str) -> int:
        return self.graphql(COUNT, {"q": q})["search"]["repositoryCount"]

    def top_stars(self, q: str) -> int | None:
        """Stars of the most-starred repo matching `q`."""
        nodes = self.graphql(TOP, {"q": f"{q} sort:stars-desc"})["search"]["nodes"]
        return (nodes[0] or {}).get("stargazerCount") if nodes else None

    def search_page(self, q: str, after: str | None = None) -> tuple[list[dict], dict, int]:
        while True:
            try:
                s = self.graphql(SEARCH, {"q": f"{q} sort:stars-desc", "first": self.search_first,
                                          "after": after})["search"]
                break
            except ServerError:
                # big pages are what time out: ask for smaller ones for the rest of the run
                if self.search_first // 2 < MIN_SEARCH_PAGE:
                    raise
                self.search_first //= 2
                log.warning("GitHub is struggling: search pages of %d from now on",
                            self.search_first)
        if s is None:
            raise GithubError("GitHub returned no search result")
        return [n for n in s["nodes"] if n], s["pageInfo"], s["repositoryCount"]

    # ---- lookups ----

    def nodes_by_ids(self, node_ids: list[str]) -> list[dict | None]:
        """Repos by GraphQL node id, in order; None where the repo no longer exists."""
        return self.graphql(NODES, {"ids": node_ids})["nodes"]

    def readmes(self, repos: list[tuple[int, str]]) -> dict[int, tuple[str, str] | None]:
        """{ghr_id: (text, sha)} for each (ghr_id, full_name); None when the repo has no README
        (or its id no longer matches the name)."""
        parts = []
        for i, (_, full_name) in enumerate(repos):
            owner, name = full_name.split("/", 1)
            blobs = " ".join(
                f"f{j}: object(expression: {json.dumps('HEAD:' + f)}) "
                f"{{ ... on Blob {{ text oid }} }}" for j, f in enumerate(README_FILES))
            parts.append(f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) "
                         f"{{ databaseId {blobs} }}")
        data = self.graphql("query { " + RATE + " " + " ".join(parts) + " }")
        out: dict[int, tuple[str, str] | None] = {}
        for i, (ghr_id, full_name) in enumerate(repos):
            node = data.get(f"r{i}")
            if node is None or node.get("databaseId") != ghr_id:
                out[ghr_id] = None
                continue
            found = next((node[f"f{j}"] for j in range(len(README_FILES))
                          if (node.get(f"f{j}") or {}).get("text") is not None), None)
            if found is None:
                text = self.readme_rest(full_name)  # another file name (README.markdown, ...)
                out[ghr_id] = (text, hashlib.sha1(text.encode()).hexdigest()) if text else None
            else:
                out[ghr_id] = (found["text"], found["oid"])
        return out

    def issue_demand(self, repos: list[tuple[int, str]]) -> dict[int, dict | None]:
        """{ghr_id: {help_wanted, bounties, issues}} for each (ghr_id, full_name): how many open
        issues carry a help-wanted / bounty label and the 10 open issues with the most 👍.
        None when the repo is gone (or its id no longer matches the name)."""
        parts = []
        for i, (_, full_name) in enumerate(repos):
            owner, name = full_name.split("/", 1)
            counts = " ".join(
                f"{key}: issues(states: OPEN, labels: {json.dumps(labels, ensure_ascii=False)}) "
                f"{{ totalCount }}" for key, labels in DEMAND_LABELS)
            q = json.dumps(f"repo:{full_name} is:issue is:open sort:reactions-+1-desc")
            parts.append(
                f"r{i}: repository(owner: {json.dumps(owner)}, name: {json.dumps(name)}) "
                f"{{ databaseId {counts} }} "
                f"s{i}: search(query: {q}, type: ISSUE, first: {DEMAND_ISSUES}) {{ nodes {{ "
                f"... on Issue {{ number title url createdAt comments {{ totalCount }} "
                f"reactions(content: THUMBS_UP) {{ totalCount }} "
                f"labels(first: 5) {{ nodes {{ name }} }} }} }} }}")
        data = self.graphql("query { " + RATE + " " + " ".join(parts) + " }")
        out: dict[int, dict | None] = {}
        for i, (ghr_id, _) in enumerate(repos):
            node = data.get(f"r{i}")
            if node is None or node.get("databaseId") != ghr_id:
                out[ghr_id] = None
                continue
            issues = [{
                "number": n["number"], "title": n["title"], "url": n["url"],
                "created_at": n["createdAt"], "comments": (n.get("comments") or {}).get("totalCount", 0),
                "reactions": (n.get("reactions") or {}).get("totalCount", 0),
                "labels": [x["name"] for x in ((n.get("labels") or {}).get("nodes") or []) if x],
            } for n in ((data.get(f"s{i}") or {}).get("nodes") or []) if n and n.get("number")]
            out[ghr_id] = {
                "help_wanted": node["hw"]["totalCount"],
                "bounties": node["bt"]["totalCount"] + node["al"]["totalCount"],
                "issues": issues,
            }
        return out

    def readme_rest(self, full_name: str) -> str | None:
        resp = self._send("GET", f"{self.base_url}/repos/{full_name}/readme",
                          headers={"Accept": "application/vnd.github.raw+json"})
        return resp.text if resp.status_code == 200 else None
