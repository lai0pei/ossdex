"""Structured queries over ossdex.db: the filtered list, facets and the repo detail page.

Every query hides repos that are not visible (`gone`, `filtered`, `below` the star threshold).
Language is always compared lowercased (the DB holds mixed casings). Star growth over 7 or 30 days
is today's stars minus the closest snapshot at least that many days older than the newest snapshot;
it is NULL until the collector has run for that long.
"""

from __future__ import annotations

import json
import statistics
from datetime import date, timedelta
from typing import Literal

from ossdex_core.licenses import LicenseKind, ids_for, known_ids, license_kind
from pydantic import BaseModel, Field

from .db import ENRICHED, VISIBLE, ReadDb

Sort = Literal["relevance", "stars", "forks", "gain_1d", "gain_7d", "gain_30d", "pushed", "created", "oldest"]
SORTS = ("relevance", "stars", "forks", "gain_1d", "gain_7d", "gain_30d", "pushed", "created", "oldest")
GainDays = Literal[1, 7, 30]


class RepoFilters(BaseModel):
    languages: list[str] = Field(default_factory=list, max_length=50, description="Programming languages, e.g. ['go']. Case-insensitive.")
    topics: list[str] = Field(default_factory=list, max_length=50, description="GitHub topics the repo must have, e.g. ['langchain']. Use facets() to see valid ones.")
    licenses: list[str] = Field(default_factory=list, max_length=50, description="Exact licenses (SPDX ids), e.g. ['mit', 'apache-2.0']. See facets() for the ones present.")
    license_kinds: list[LicenseKind] = Field(default_factory=list, description="Any of these license kinds. For a commercial/closed product or a SaaS use ['permissive'] (add 'weak_copyleft' with a caveat); 'network_copyleft' is AGPL; 'other' is unclassified or source-available.")
    min_stars: int | None = Field(None, description="Minimum GitHub stars.")
    max_stars: int | None = Field(None, description="Maximum GitHub stars (find less famous projects).")
    min_forks: int | None = Field(None, description="Minimum forks. Many forks means many people run and customize the project.")
    max_forks: int | None = Field(None, description="Maximum forks (find projects with fewer forks).")
    created_after: date | None = Field(None, description="Only repos created on/after this date (YYYY-MM-DD).")
    pushed_after: date | None = Field(None, description="Only repos pushed to on/after this date (YYYY-MM-DD), i.e. still maintained.")
    pushed_before: date | None = Field(None, description="Only repos last pushed to before this date (YYYY-MM-DD), i.e. stale or abandoned.")
    with_readme: bool = Field(False, description="Only repos whose README is stored. Nearly all have one once collected, so leave this off unless you need README content.")
    licensed_only: bool = Field(False, description="Only repos with a license. Set it for open-source or commercial-use questions: a repo without one is all rights reserved.")
    min_gain: int | None = Field(None, description="Stars gained over `gain_days` must be at least this (rising repos). Needs a few days of collected history.")
    gain_days: GainDays = Field(7, description="Window for min_gain (1 for daily, 7 for weekly, 30 for monthly).")
    names: list[str] = Field(default_factory=list, max_length=50, description="Restrict to these owner/repo names.")
    in_lists: list[str] = Field(default_factory=list, max_length=50, description="Only repos listed in any of these Awesome lists (owner/repo of the list, e.g. ['vinta/awesome-python']). Use facets() 'lists' to see the ones present.")
    money: list[str] = Field(default_factory=list, max_length=50, description="Only repos with any of these business-model hints: hosted_cloud, enterprise, pricing, support_consulting (from the README) or sponsors (lists funding links). They show companies already pay for services around the project. See facets() 'money'.")
    mentions_paper: bool = Field(False, description="Only repos whose README links to an arXiv paper. This means the README mentions a paper, not that the repo implements it.")

    def to_filters(self) -> RepoFilters:
        return RepoFilters(**{k: getattr(self, k) for k in RepoFilters.model_fields})


def gain_expr(days: int) -> str:
    """SQL for the stars a repo gained over `days` days; one `?` (the newest snapshot day)."""
    return (f"(r.stars - (SELECT s.stars FROM repo_stats s WHERE s.ghr_id = r.ghr_id "
            f"AND s.day <= date(?, '-{int(days)} days') ORDER BY s.day DESC LIMIT 1))")


def where_clause(f: RepoFilters, anchor: str | None = None) -> tuple[str, list]:
    """WHERE fragment over `repos r` (always present: hides repos that are not visible).
    `anchor` is the newest snapshot day, needed only for the growth filter."""
    parts, params = [f"{VISIBLE}"], []
    if f.languages:
        parts.append(f"lower(r.language) IN ({','.join('?' * len(f.languages))})")
        params += [x.lower() for x in f.languages]
    for t in f.topics:
        parts.append("EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid(r.topics) "
                     "THEN r.topics ELSE '[]' END) WHERE lower(value) = ?)")
        params.append(t.lower())
    if f.licenses:
        parts.append(f"lower(r.license) IN ({','.join('?' * len(f.licenses))})")
        params += [x.lower() for x in f.licenses]
    if f.license_kinds:
        ors, kparams = [], []
        for kind in dict.fromkeys(f.license_kinds):
            if kind == "none":
                ors.append("r.license IS NULL")
            elif kind == "other":
                known = known_ids()
                ors.append(f"(r.license IS NOT NULL AND lower(r.license) NOT IN "
                           f"({','.join('?' * len(known))}))")
                kparams += known
            else:
                ids = ids_for(kind)
                ors.append(f"lower(r.license) IN ({','.join('?' * len(ids))})")
                kparams += ids
        parts.append("(" + " OR ".join(ors) + ")")
        params += kparams
    if f.min_stars is not None:
        parts.append("r.stars >= ?")
        params.append(f.min_stars)
    if f.max_stars is not None:
        parts.append("r.stars <= ?")
        params.append(f.max_stars)
    if f.min_forks is not None:
        parts.append("r.forks >= ?")
        params.append(f.min_forks)
    if f.max_forks is not None:
        parts.append("r.forks <= ?")
        params.append(f.max_forks)
    if f.created_after:
        parts.append("r.created_at >= ?")
        params.append(f.created_after.isoformat())
    if f.pushed_after:
        parts.append("r.pushed_at >= ?")
        params.append(f.pushed_after.isoformat())
    if f.pushed_before:
        parts.append("r.pushed_at < ?")
        params.append(f.pushed_before.isoformat())
    if f.with_readme:
        parts.append(f"{ENRICHED}")
    if f.licensed_only:
        parts.append("r.license IS NOT NULL")
    if f.min_gain is not None:
        if anchor is None:
            parts.append("0 = 1")  # no snapshots yet: no repo has a measurable gain
        else:
            parts.append(f"{gain_expr(f.gain_days)} >= ?")
            params += [anchor, f.min_gain]
    if f.names:
        parts.append(f"lower(r.full_name) IN ({','.join('?' * len(f.names))})")
        params += [x.lower() for x in f.names]
    if f.in_lists:
        parts.append("EXISTS (SELECT 1 FROM repo_lists rl JOIN repos l ON l.ghr_id = rl.list_id "
                     f"WHERE rl.ghr_id = r.ghr_id AND lower(l.full_name) IN ({','.join('?' * len(f.in_lists))}))")
        params += [x.lower() for x in f.in_lists]
    if f.mentions_paper:
        parts.append("EXISTS (SELECT 1 FROM repo_papers rp WHERE rp.ghr_id = r.ghr_id)")
    if f.money:
        ors = []
        for m in dict.fromkeys(f.money):
            if m == "sponsors":
                ors.append("EXISTS (SELECT 1 FROM repo_money m WHERE m.ghr_id = r.ghr_id "
                           "AND COALESCE(m.funding, '[]') NOT IN ('', '[]'))")
            else:
                ors.append("EXISTS (SELECT 1 FROM repo_money m, json_each(CASE WHEN "
                           "json_valid(m.signals) THEN m.signals ELSE '[]' END) j "
                           "WHERE m.ghr_id = r.ghr_id AND j.value = ?)")
                params.append(m)
        parts.append("(" + " OR ".join(ors) + ")")
    return " AND ".join(parts), params


def matching_ids(db: ReadDb, f: RepoFilters) -> set[int]:
    where, params = where_clause(f, db.latest_day())
    return {r[0] for r in db.query(f"SELECT r.ghr_id FROM repos r WHERE {where}", params)}


def _order_by(sort: str, anchor: str | None) -> tuple[str, list]:
    exprs = {
        "stars": ("r.stars DESC", []),
        "forks": ("r.forks DESC", []),
        "pushed": ("r.pushed_at DESC", []),
        "created": ("r.created_at DESC", []),
        "oldest": ("r.created_at ASC", []),
    }
    for days in (1, 7, 30):
        exprs[f"gain_{days}d"] = (f"{gain_expr(days)} DESC", [anchor]) if anchor else ("NULL", [])
    expr, params = exprs.get(sort, exprs["stars"])
    return f"{expr} NULLS LAST, r.stars DESC, r.ghr_id", params


def _topics(raw: str | None) -> list[str]:
    try:
        v = json.loads(raw) if raw else []
    except ValueError:
        return []
    return [t for t in v if isinstance(t, str)] if isinstance(v, list) else []


REPO_COLS = ("r.ghr_id, r.full_name, r.url, r.description, r.language, r.topics, r.stars, r.forks, "
             "r.license, r.homepage, r.open_issues, r.pushed_at, r.created_at, "
             "(r.readme IS NOT NULL) AS has_readme")


def _select_cols(anchor: str | None) -> tuple[str, list]:
    if anchor:
        return f"{REPO_COLS}, {gain_expr(1)} AS g1, {gain_expr(7)} AS g7, {gain_expr(30)} AS g30", [anchor, anchor, anchor]
    return f"{REPO_COLS}, NULL AS g1, NULL AS g7, NULL AS g30", []


def rows_to_dtos(rows) -> list[dict]:
    """Repo rows -> list DTOs."""
    return [{
        "ghr_id": r["ghr_id"], "full_name": r["full_name"], "url": r["url"],
        "description": r["description"], "language": r["language"],
        "topics": _topics(r["topics"]), "stars": r["stars"], "forks": r["forks"],
        "license": r["license"], "license_kind": license_kind(r["license"]),
        "homepage": r["homepage"], "open_issues": r["open_issues"],
        "pushed_at": r["pushed_at"], "created_at": r["created_at"],
        "has_readme": bool(r["has_readme"]), "gain_1d": r["g1"], "gain_7d": r["g7"], "gain_30d": r["g30"],
    } for r in rows]


def enrich_dtos(db: ReadDb, dtos: list[dict]) -> list[dict]:
    """Batch-attach sparkline points, business signals, lists/papers count to repo DTOs."""
    if not dtos:
        return dtos

    gids = [r["ghr_id"] for r in dtos if "ghr_id" in r]
    if not gids:
        return dtos

    marks = ",".join("?" * len(gids))

    # 1. Sparkline points: recent star history per repo (up to 14 latest snapshots)
    sparklines: dict[int, list[int]] = {gid: [] for gid in gids}
    rows = db.query(
        f"SELECT ghr_id, stars FROM repo_stats WHERE ghr_id IN ({marks}) AND stars IS NOT NULL ORDER BY day ASC",
        gids,
    )
    for r in rows:
        sparklines[r["ghr_id"]].append(r["stars"])
    # Cap to the latest 14 points
    for gid in sparklines:
        if len(sparklines[gid]) > 14:
            sparklines[gid] = sparklines[gid][-14:]

    # 2. Money signals
    money_map = money_for(db, gids) if db.has_money else {}

    # 3. Lists and papers counts
    list_counts: dict[int, int] = {}
    paper_counts: dict[int, int] = {}
    if db.has_enrich:
        for r in db.query(f"SELECT ghr_id, COUNT(*) FROM repo_lists WHERE ghr_id IN ({marks}) GROUP BY ghr_id", gids):
            list_counts[r[0]] = r[1]
        for r in db.query(f"SELECT ghr_id, COUNT(*) FROM repo_papers WHERE ghr_id IN ({marks}) GROUP BY ghr_id", gids):
            paper_counts[r[0]] = r[1]

    for d in dtos:
        gid = d.get("ghr_id")
        if gid is None:
            continue
        d["sparkline"] = sparklines.get(gid, [])
        m = money_map.get(gid)
        d["money_signals"] = m["signals"] if m else []
        d["lists_count"] = list_counts.get(gid, 0)
        d["papers_count"] = paper_counts.get(gid, 0)

    return dtos


def list_repos(db: ReadDb, f: RepoFilters, sort: str = "stars", page: int = 1,
               page_size: int = 50, offset: int | None = None) -> dict:
    anchor = db.latest_day()
    cols, cparams = _select_cols(anchor)
    where, params = where_clause(f, anchor)
    total = db.scalar(f"SELECT COUNT(*) FROM repos r WHERE {where}", params)
    order, oparams = _order_by(sort, anchor)
    page = max(page, 1)
    rows = db.query(
        f"SELECT {cols} FROM repos r WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
        cparams + params + oparams + [page_size, offset if offset is not None else (page - 1) * page_size],
    )
    dtos = enrich_dtos(db, rows_to_dtos(rows))
    return {"items": dtos, "total": total, "mode": "list"}


def dtos_for_ids(db: ReadDb, ids: list[int], f: RepoFilters | None = None) -> list[dict]:
    """DTOs for the given repos, in the order given."""
    if not ids:
        return []
    cols, cparams = _select_cols(db.latest_day())
    rows = db.query(f"SELECT {cols} FROM repos r WHERE r.ghr_id IN ({','.join('?' * len(ids))})",
                    cparams + ids)
    by_id = {r["ghr_id"]: r for r in rows}
    return rows_to_dtos([by_id[i] for i in ids if i in by_id])


def facets(db: ReadDb, f: RepoFilters, topic_limit: int = 50) -> dict:
    """Value counts for the filter dropdowns. Each facet ignores its own filter."""
    anchor = db.latest_day()

    def counts(sql_expr: str, join: str, own: dict) -> list[dict]:
        where, params = where_clause(f.model_copy(update=own), anchor)
        rows = db.query(
            f"SELECT {sql_expr} AS v, COUNT(DISTINCT r.ghr_id) AS n FROM repos r {join} "
            f"WHERE {where} AND {sql_expr} IS NOT NULL AND {sql_expr} <> '' "
            f"GROUP BY v ORDER BY n DESC, v LIMIT ?", params + [topic_limit * 4],
        )
        return [{"value": r["v"], "count": r["n"]} for r in rows]

    langs = counts("lower(r.language)", "", {"languages": []})
    topics = counts(
        "lower(t.value)",
        ", json_each(CASE WHEN json_valid(r.topics) THEN r.topics ELSE '[]' END) t",
        {"topics": []},
    )[:topic_limit]
    licenses = counts("r.license", "", {"licenses": []})
    lists: list[dict] = []
    if db.has_enrich:
        where, params = where_clause(f.model_copy(update={"in_lists": []}), anchor)
        lists = [{"value": r["v"], "count": r["n"]} for r in db.query(
            f"SELECT (SELECT l.full_name FROM repos l WHERE l.ghr_id = rl.list_id) AS v, "
            f"COUNT(DISTINCT r.ghr_id) AS n FROM repos r JOIN repo_lists rl ON rl.ghr_id = r.ghr_id "
            f"WHERE {where} GROUP BY rl.list_id ORDER BY n DESC, v LIMIT ?", params + [topic_limit])]
    money: list[dict] = []
    if db.has_money:
        where, params = where_clause(f.model_copy(update={"money": []}), anchor)
        counts_ = {r["v"]: r["n"] for r in db.query(
            f"SELECT j.value AS v, COUNT(DISTINCT r.ghr_id) AS n FROM repos r JOIN repo_money m "
            f"ON m.ghr_id = r.ghr_id, json_each(CASE WHEN json_valid(m.signals) THEN m.signals "
            f"ELSE '[]' END) j WHERE {where} GROUP BY j.value", params)}
        counts_["sponsors"] = db.scalar(
            f"SELECT COUNT(DISTINCT r.ghr_id) FROM repos r JOIN repo_money m ON m.ghr_id = r.ghr_id "
            f"WHERE {where} AND COALESCE(m.funding, '[]') NOT IN ('', '[]')", params) or 0
        money = [{"value": k, "count": n} for k, n in sorted(counts_.items(), key=lambda kv: -kv[1])
                 if n]
    return {"languages": langs, "topics": topics, "licenses": licenses, "lists": lists,
            "money": money}


def repo_detail(db: ReadDb, full_name: str) -> dict | None:
    cols, cparams = _select_cols(db.latest_day())
    row = db.one(
        f"SELECT {cols}, r.readme FROM repos r "
        f"WHERE lower(r.full_name) = lower(?) AND {VISIBLE}", cparams + [full_name],
    )
    if row is None:
        return None
    dto = rows_to_dtos([row])[0]
    history = [{"day": h["day"], "stars": h["stars"], "forks": h["forks"]} for h in db.query(
        "SELECT day, stars, forks FROM repo_stats WHERE ghr_id = ? ORDER BY day", (row["ghr_id"],))]
    card = db.one("SELECT text FROM chunks WHERE ghr_id = ? AND kind = 'card'", (row["ghr_id"],))
    lists, papers = [], []
    if db.has_enrich:
        lists = [{"list": r["full_name"], "section": r["section"], "url": r["url"]} for r in db.query(
            "SELECT l.full_name, l.url, rl.section FROM repo_lists rl JOIN repos l "
            "ON l.ghr_id = rl.list_id WHERE rl.ghr_id = ? ORDER BY l.stars DESC", (row["ghr_id"],))]
        papers = [{"arxiv_id": r["arxiv_id"], "title": r["title"],
                   "url": f"https://arxiv.org/abs/{r['arxiv_id']}"} for r in db.query(
            "SELECT rp.arxiv_id, p.title FROM repo_papers rp LEFT JOIN papers p "
            "ON p.arxiv_id = rp.arxiv_id WHERE rp.ghr_id = ? ORDER BY rp.arxiv_id", (row["ghr_id"],))]
    return {
        **dto,
        "lists": lists, "papers": papers,
        "money": money_for(db, [row["ghr_id"]]).get(row["ghr_id"]),
        "homepage": row["homepage"], "open_issues": row["open_issues"], "readme": row["readme"],
        "card": card["text"] if card else None, "history": history,
        "github_url": row["url"] or f"https://github.com/{row['full_name']}",
    }


README_EXCERPT_CHARS = 1500


def readme_excerpt(text: str | None, limit: int = README_EXCERPT_CHARS) -> tuple[str | None, bool]:
    """The start of a README, cut at a paragraph break when one falls in the second half.
    Returns (excerpt, truncated)."""
    if not text:
        return None, False
    if len(text) <= limit:
        return text, False
    cut = text.rfind("\n\n", limit // 2, limit)
    return text[:cut if cut > 0 else limit].rstrip(), True


def public_detail(d: dict) -> dict:
    """`repo_detail` for anonymous callers: the full README (the authors' text) is replaced by an
    excerpt and a link to GitHub. Internal analysis keeps using the full `repo_detail`."""
    out = {k: v for k, v in d.items() if k != "readme"}
    out["readme_excerpt"], out["readme_truncated"] = readme_excerpt(d.get("readme"))
    out["readme_url"] = f"{d['github_url']}#readme"
    return out


def money_for(db: ReadDb, ids: list[int]) -> dict[int, dict]:
    """{ghr_id: {"signals": [...], "funding": [{platform, url}]}} for the repos that have any."""
    out: dict[int, dict] = {}
    if not ids or not db.has_money:
        return out
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        for r in db.query(f"SELECT ghr_id, funding, signals FROM repo_money "
                          f"WHERE ghr_id IN ({','.join('?' * len(part))})", part):
            signals = _json_list(r["signals"])
            funding = _json_list(r["funding"])
            if funding:
                signals = [*signals, "sponsors"]
            if signals or funding:
                out[r["ghr_id"]] = {"signals": signals, "funding": funding}
    return out


def _json_list(raw: str | None) -> list:
    try:
        v = json.loads(raw) if raw else []
    except ValueError:
        return []
    return v if isinstance(v, list) else []


NicheSort = Literal["growth", "momentum", "size"]


def niches(db: ReadDb, f: RepoFilters, days: int = 7, min_repos: int = 5, sort: NicheSort = "growth",
           limit: int = 30) -> dict:
    """Topics ranked by how fast their repos are gaining stars, over repos matching `f`:
    [{topic, repos, total_stars, median_stars, gain, gain_per_repo, active_pct, top_repos}].
    `growth` ranks by total stars gained, `momentum` by the median repo's gain (a typical repo is
    growing, not one viral one), `size` by total stars. `top_share` is the % of the topic's gain
    that its best repo carries. Few repos and a high median gain is room to specialise."""
    days = 30 if days >= 30 else (7 if days >= 7 else 1)
    anchor = db.latest_day()
    cols, cparams = _select_cols(anchor)
    where, params = where_clause(f, anchor)
    rows = rows_to_dtos(db.query(f"SELECT {cols} FROM repos r WHERE {where}", cparams + params))
    cutoff = (date.fromisoformat(anchor) if anchor else date.today()) - timedelta(days=90)
    # a topic that is just a programming language (python, rust...) says nothing about a niche
    langs = {(r["language"] or "").lower() for r in rows}
    by_topic: dict[str, list[dict]] = {}
    for r in rows:
        for t in {x.lower() for x in r["topics"] if x.strip()} - langs:
            by_topic.setdefault(t, []).append(r)
    key = f"gain_{days}d"
    out = []
    for topic, repos in by_topic.items():
        if len(repos) < min_repos:
            continue
        gains = [r[key] for r in repos if r[key] is not None]
        stars = [r["stars"] or 0 for r in repos]
        gain = sum(gains)
        top_gain = max(gains, default=0)
        out.append({
            "topic": topic, "repos": len(repos), "total_stars": sum(stars),
            "median_stars": int(statistics.median(stars)), "gain": gain,
            "gain_per_repo": round(gain / len(gains), 1) if gains else None,
            # typical repo, and how much of the topic's gain one repo carries: a high
            # `top_share` means a single viral repo, not a niche that is growing as a whole
            "median_gain": int(statistics.median(gains)) if gains else None,
            "top_share": round(100 * top_gain / gain) if gain > 0 else None,
            "active_pct": round(100 * sum(1 for r in repos if (r["pushed_at"] or "")[:10]
                                          >= cutoff.isoformat()) / len(repos)),
            "top_repos": [{"repo": r["full_name"], "stars": r["stars"], "gain": r[key]}
                          for r in sorted((r for r in repos if r[key] is not None),
                                          key=lambda r: -r[key])[:3]],
        })
    order = {"growth": lambda n: (-n["gain"], n["topic"]),
             "momentum": lambda n: (-(n["median_gain"] or 0), n["topic"]),
             "size": lambda n: (-n["total_stars"], n["topic"])}[sort]
    out.sort(key=order)
    res: dict = {"window_days": days, "history_days": db.history_days(), "sort": sort,
                 "topics_considered": len(by_topic), "niches": out[:limit]}
    if db.history_days() < days:
        res["note"] = (f"only {db.history_days()} days of star history: gains cover that much, "
                       f"not {days} days")
    return res


GROUPS = ("language", "license_kind", "topic", "created_year", "pushed_year")


def grouped_counts(db: ReadDb, f: RepoFilters, group_by: str, limit: int = 30) -> dict:
    """Repos matching `f` grouped by language, license kind, topic or year:
    [{value, repos, total_stars, median_stars}], biggest groups first."""
    if group_by not in GROUPS:
        raise ValueError(f"group_by must be one of {GROUPS}")
    where, params = where_clause(f, db.latest_day())
    rows = db.query("SELECT r.language, r.license, r.topics, r.created_at, r.pushed_at, r.stars "
                    f"FROM repos r WHERE {where}", params)
    groups: dict[str, list[int]] = {}
    for r in rows:
        if group_by == "language":
            keys = [(r["language"] or "").lower()]
        elif group_by == "license_kind":
            keys = [license_kind(r["license"])]
        elif group_by == "topic":
            keys = [t.lower() for t in _topics(r["topics"])]
        else:
            col = r["created_at"] if group_by == "created_year" else r["pushed_at"]
            keys = [(col or "")[:4]]
        for k in keys:
            if k:
                groups.setdefault(k, []).append(r["stars"] or 0)
    ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:limit]
    return {"total_matching": len(rows), "groups": [
        {"value": k, "repos": len(v), "total_stars": sum(v), "median_stars": int(statistics.median(v))}
        for k, v in ranked]}
