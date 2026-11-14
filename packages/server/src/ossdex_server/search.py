"""Keyword search: FTS5 over README chunks plus a lexical pass over names/topics/descriptions,
fused with Reciprocal Rank Fusion."""

from __future__ import annotations

import json
import re

from .db import VISIBLE, ReadDb
from .repo_query import RepoFilters, dtos_for_ids, matching_ids

RRF_K = 60
CANDIDATES = 300
LEXICAL_WEIGHT = 1.0

STOPWORDS = frozenset(
    ["a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how", "i", "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was", "what", "which", "who", "with", "would", "could", "should", "can", "do", "does", "did", "me", "my", "show", "list", "find", "give", "tell", "about", "any", "some", "good", "best", "top", "projects", "project", "repos", "repo", "repositories"]
)


def fts_query(q: str) -> str | None:
    """Quote every word so user text can't break FTS5 syntax; OR them together."""
    terms = re.findall(r"\w+", q)
    return " OR ".join(f'"{t}"' for t in terms) if terms else None


def query_terms(q: str) -> list[str]:
    words = re.findall(r"\w+", q.lower())
    terms = [w for w in words if w not in STOPWORDS and len(w) > 1]
    return terms or words


MAX_LEXICAL_TERMS = 8  # a long query (find_similar sends a repo's whole description + topics)


def _lexical(db: ReadDb, terms: list[str], allowed: set[int] | None) -> list[tuple[int, float, str]]:
    """Repos whose topics / name / description mention a query term: (ghr_id, score, reason).

    SQL first narrows the table to rows containing a term as a substring in the name, description,
    topics or language: a superset of everything the scoring below can match (it needs a substring
    or a word-start match in one of them, or an exact language). Only those rows are scored in Python."""
    terms = list(dict.fromkeys(terms))[:MAX_LEXICAL_TERMS]
    if not terms:
        return []
    patterns = [(t, re.compile(rf"\b{re.escape(t)}", re.IGNORECASE)) for t in terms]
    conds, params = [], []
    if all(t.isascii() for t in terms):  # SQLite's lower() is ASCII-only: don't prefilter otherwise
        for t in terms:
            conds.append("instr(lower(full_name), ?) > 0 OR instr(lower(description), ?) > 0 "
                         "OR instr(lower(topics), ?) > 0 OR lower(language) = ?")
            params += [t, t, t, t]
    where = f" AND ({' OR '.join(conds)})" if conds else ""
    out = []
    for r in db.query("SELECT ghr_id, full_name, description, topics, language FROM repos "
                      f"WHERE {VISIBLE}{where}", params):
        if allowed is not None and r["ghr_id"] not in allowed:
            continue
        name = r["full_name"].lower()
        desc = (r["description"] or "").lower()
        topics_raw = (r["topics"] or "").lower()
        topics: set[str] | None = None
        lang = (r["language"] or "").lower()
        score, reason = 0.0, ""
        for t, pat in patterns:
            if t in topics_raw:
                if topics is None:
                    try:
                        topics = {x.lower() for x in json.loads(r["topics"] or "[]") if isinstance(x, str)}
                    except ValueError:
                        topics = set()
                if t in topics or any(t in x for x in topics if len(t) > 3):
                    score += 3
                    reason = reason or "topic"
            if pat.search(name):
                score += 2
                reason = reason or "name"
            if t == lang:
                score += 1.5
            if pat.search(desc):
                score += 1
                reason = reason or "description"
        if score:
            out.append((r["ghr_id"], score, reason))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out[:CANDIDATES]


def search(
    db: ReadDb,
    q: str,
    filters: RepoFilters | None = None,
    limit: int = 20,
) -> list[dict]:
    """Ranked repo DTOs (see repo_query.rows_to_dtos) plus `score`, `why` and `snippet`."""
    f = filters or RepoFilters()
    allowed = matching_ids(db, f)
    if not allowed:
        return []
    terms = query_terms(q)

    # chunk-level candidate lists -> {chunk key: (ghr_id, kind)}
    chunk_info: dict[str, tuple[int, str]] = {}
    bm25_keys: list[str] = []
    match = fts_query(" ".join(terms))
    if match:
        rows = db.query(
            "SELECT f.rowid AS id, c.ghr_id, c.kind FROM chunks_fts f JOIN chunks c ON c.id = f.rowid "
            "WHERE chunks_fts MATCH ? ORDER BY bm25(chunks_fts) LIMIT ?", (match, CANDIDATES),
        )
        for r in rows:
            if r["ghr_id"] in allowed:
                key = f"c{r['id']}"
                chunk_info[key] = (r["ghr_id"], r["kind"])
                bm25_keys.append(key)
        bm25_keys = bm25_keys[:100]

    scores: dict[str, float] = {}
    via: dict[str, set[str]] = {}
    for name, keys in (("keyword", bm25_keys),):
        for rank, key in enumerate(keys, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank)
            via.setdefault(key, set()).add(name)

    per_repo: dict[int, list[tuple[float, str]]] = {}
    for key, s in scores.items():
        per_repo.setdefault(chunk_info[key][0], []).append((s, key))
    repo_score: dict[int, float] = {}
    repo_why: dict[int, set[str]] = {}
    snippet_key: dict[int, str] = {}
    for g, lst in per_repo.items():
        lst.sort(reverse=True)
        repo_score[g] = lst[0][0] + (0.1 * lst[1][0] if len(lst) > 1 else 0.0)
        repo_why[g] = set().union(*(via[k] for _, k in lst))
        snippet_key[g] = next((k for _, k in lst if chunk_info[k][1] == "readme"), "")

    for rank, (g, _, reason) in enumerate(_lexical(db, terms, allowed), start=1):
        repo_score[g] = repo_score.get(g, 0.0) + LEXICAL_WEIGHT / (RRF_K + rank)
        repo_why.setdefault(g, set()).add(reason)

    top = sorted(repo_score.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    dtos = dtos_for_ids(db, [g for g, _ in top], f)
    snippets = _snippets(db, {g: snippet_key[g] for g, _ in top if snippet_key.get(g)})
    out = []
    for dto in dtos:
        g = dto["ghr_id"]
        out.append(dto | {"score": round(repo_score[g], 5), "why": sorted(repo_why[g]),
                          "snippet": snippets.get(g)})
    return out


def _snippets(db: ReadDb, keys: dict[int, str]) -> dict[int, str]:
    ids = [int(k[1:]) for k in keys.values() if k.startswith("c")]
    if not ids:
        return {}
    text = {r["id"]: r["text"] for r in db.query(
        f"SELECT id, text FROM chunks WHERE id IN ({','.join('?' * len(ids))})", ids)}
    out = {}
    for g, k in keys.items():
        t = text.get(int(k[1:]))
        if t:
            out[g] = (t.split("\n", 1)[1] if "\n" in t else t).strip()[:400]
    return out


def readme_sections(db: ReadDb, ghr_id: int, query: str, n: int = 3) -> list[dict]:
    """Best README chunks of one repo for a query, ranked by keyword overlap."""
    chunks = db.query("SELECT id, heading, text FROM chunks WHERE ghr_id = ? AND kind = 'readme' "
                      "ORDER BY ord", (ghr_id,))
    if not chunks:
        return []
    terms = set(query_terms(query))
    ranked = sorted(chunks, key=lambda c: -sum(t in c["text"].lower() for t in terms))
    return [{"heading": c["heading"], "text": c["text"]} for c in ranked[:n]]


def similar(db: ReadDb, full_name: str, filters: RepoFilters | None = None,
            limit: int = 10) -> dict | None:
    """Repos closest to `full_name` by keyword search on its description and topics:
    {"repos": [dto]}. None when the repo is not in the database."""
    row = db.one(f"SELECT ghr_id, description, topics, language FROM repos r "
                 f"WHERE lower(r.full_name) = lower(?) AND {VISIBLE}", (full_name,))
    if row is None:
        return None
    f = filters or RepoFilters()
    topics = " ".join(t for t in json.loads(row["topics"] or "[]") if isinstance(t, str))
    text = f"{row['description'] or ''} {topics}".strip() or full_name
    hits = [h for h in search(db, text, f, limit + 1) if h["ghr_id"] != row["ghr_id"]]
    return {"repos": hits[:limit], "note": "matched by keywords in the description and topics"}


__all__ = ["fts_query", "query_terms", "readme_sections", "search", "similar"]
