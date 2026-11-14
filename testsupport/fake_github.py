"""An in-memory GitHub for the collector tests: GraphQL search (with the real 1000-result cap and
the stars:/created:/-topic: qualifiers), node lookups by id, README blobs and the REST fallback."""

from __future__ import annotations

import json
import re

import httpx

BASE = "https://gh.test"
SEARCH_CAP = 1000


def make_repo(i: int, *, stars: int, created: str = "2020-01-01", license: str | None = "MIT",
              topics: tuple[str, ...] = ("tool",), **kw) -> dict:
    return {"id": i, "name": f"org{i % 7}/repo{i}", "stars": stars, "created": created,
            "license": license, "topics": list(topics), "fork": False, "archived": False,
            "mirror": False, "template": False, "forks": stars // 10, "language": "Python",
            "description": f"repo number {i}", "pushed": "2026-10-20T00:00:00Z",
            "readme": {"README.md": f"# repo{i}\nHello from repo {i}.\n"}, **kw}


def node(r: dict) -> dict:
    lic = r["license"]
    return {
        "databaseId": r["id"], "id": f"R_{r['id']}", "nameWithOwner": r["name"],
        "url": f"https://github.com/{r['name']}", "description": r["description"],
        "homepageUrl": None, "primaryLanguage": {"name": r["language"]},
        "repositoryTopics": {"nodes": [{"topic": {"name": t}} for t in r["topics"]]},
        "licenseInfo": {"spdxId": lic, "key": lic.lower()} if lic else None,
        "stargazerCount": r["stars"], "forkCount": r["forks"], "openIssues": {"totalCount": 3},
        "pushedAt": r["pushed"], "createdAt": f"{r['created']}T00:00:00Z",
        "isArchived": r["archived"], "isFork": r["fork"], "isMirror": r["mirror"],
        "isTemplate": r["template"],
    }


def _matches(r: dict, q: str) -> bool:
    for tok in q.split():
        if tok.startswith("stars:"):
            v = tok[6:]
            if v.startswith(">="):
                ok = r["stars"] >= int(v[2:])
            elif ".." in v:
                a, b = v.split("..")
                ok = int(a) <= r["stars"] <= int(b)
            else:
                ok = r["stars"] == int(v)
            if not ok:
                return False
        elif tok.startswith("created:"):
            a, b = tok[8:].split("..")
            if not (a <= r["created"] <= b):
                return False
        elif tok.startswith("-topic:"):
            if tok[7:] in r["topics"]:
                return False
        elif tok in ("fork:false", "archived:false", "mirror:false", "template:false"):
            if r[tok.split(":")[0]]:
                return False
    return True


class FakeGitHub:
    def __init__(self, repos: list[dict]):
        self.repos = repos
        self.by_id = {r["id"]: r for r in repos}
        self.search_pages = 0
        self.counts = 0
        self.requests = 0
        self.seen: list[httpx.Request] = []
        self.fail_after_pages: int | None = None  # then answer 403 "primary limit"
        self.remaining = 5000
        self.rest_readmes: dict[str, str] = {}
        self.statuses: list[int | str] = []  # canned statuses for the next requests
        self.html_pages = 0  # the next search pages come back as an HTML page (HTTP 200)
        self.poison: set[int] = set()  # a query touching one of these repos fails (HTTP 200 + errors)

    def search(self, q: str) -> list[dict]:
        out = [r for r in self.repos if _matches(r, q)]
        return sorted(out, key=lambda r: (-r["stars"], r["id"])) if "sort:stars-desc" in q else out

    def _rate(self) -> dict:
        return {"cost": 1, "remaining": self.remaining, "resetAt": "2099-01-01T00:00:00Z"}

    @staticmethod
    def _boom(data: dict) -> httpx.Response:
        """What GitHub sends when a query times out or hits a bad repo: data, with errors."""
        return httpx.Response(200, json={"data": data, "errors": [
            {"type": "INTERNAL", "message": "Something went wrong while executing your query."}]})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        self.seen.append(request)
        if self.statuses:
            code = self.statuses.pop(0)
            if code == "html":
                return httpx.Response(200, text="<html>unicorn</html>")
            if code != 200:
                return httpx.Response(code, text="boom")
        if request.url.path.endswith("/readme"):
            name = request.url.path[len("/repos/"):-len("/readme")]
            text = self.rest_readmes.get(name.lower())
            return httpx.Response(200 if text else 404, text=text or "")
        body = json.loads(request.content)
        query, v = body["query"], body.get("variables") or {}
        data: dict = {"rateLimit": self._rate()}
        if "nodes(ids:" in query:
            if self.poison & {int(i[2:]) for i in v["ids"]}:
                return self._boom({"nodes": None})
            data["nodes"] = [node(self.by_id[int(i[2:])]) if int(i[2:]) in self.by_id else None
                             for i in v["ids"]]
        elif "pageInfo" in query:
            if self.fail_after_pages is not None and self.search_pages >= self.fail_after_pages:
                return httpx.Response(403, text="rate limit", headers={
                    "x-ratelimit-remaining": "0", "x-ratelimit-reset": "99999999999"})
            if self.html_pages:
                self.html_pages -= 1
                return httpx.Response(200, text="<html>unicorn</html>")
            self.search_pages += 1
            hits = self.search(v["q"])
            if self.poison & {r["id"] for r in hits[:SEARCH_CAP]}:
                return self._boom({"search": None})
            start = int(v["after"] or 0)
            shown = hits[:SEARCH_CAP]
            end = min(start + v["first"], len(shown))
            data["search"] = {"repositoryCount": len(hits),
                              "pageInfo": {"hasNextPage": end < len(shown), "endCursor": str(end)},
                              "nodes": [node(r) for r in shown[start:end]]}
        elif "search(" in query and "nodes" in query:
            hits = self.search(v["q"])
            data["search"] = {"repositoryCount": len(hits),
                              "nodes": [{"stargazerCount": hits[0]["stars"]}] if hits else []}
        elif "search(" in query:
            self.counts += 1
            data["search"] = {"repositoryCount": len(self.search(v["q"]))}
        else:  # README batch
            for m in re.finditer(r'(r\d+): repository\(owner: "([^"]+)", name: "([^"]+)"\)', query):
                alias, owner, name = m.groups()
                full = f"{owner}/{name}".lower()
                repo = next((r for r in self.repos if r["name"].lower() == full), None)
                if repo is None:
                    data[alias] = None
                    continue
                if repo["id"] in self.poison:
                    return self._boom({alias: None})
                out = {"databaseId": repo["id"]}
                for j, fname in enumerate(("README.md", "readme.md", "README.rst", "README")):
                    text = repo["readme"].get(fname)
                    out[f"f{j}"] = {"text": text, "oid": f"sha-{len(text)}-{repo['id']}"} if text else None
                data[alias] = out
        return httpx.Response(200, json={"data": data})
