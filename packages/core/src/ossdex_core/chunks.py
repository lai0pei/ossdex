"""Search chunks: one card per repo plus its README split into sections.

Chunks feed the FTS5 keyword index. The card holds nothing that changes daily (no star
counts), so a repo's chunks are only rewritten when its text really changes.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass

from .store import HIDDEN, touch_sync

CHUNK_CHARS = 1800
OVERLAP = 200
MAX_README_CHUNKS = 12
MAX_CODE_LINES = 30

_BADGE = re.compile(r"\[!\[[^\]]*\]\([^)]*\)\]\([^)]*\)")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
_FENCE = re.compile(r"^\s*(```|~~~)")


def build_card(repo, extras: list[str] | None = None) -> str:
    topics = json.loads(repo["topics"]) if repo["topics"] else []
    desc = repo["description"] or ""
    lines = [f"{repo['full_name']} — {desc}" if desc else repo["full_name"]]
    meta = []
    if repo["language"]:
        meta.append(f"Language: {repo['language']}")
    if topics:
        meta.append(f"Topics: {', '.join(topics)}")
    if repo["license"]:
        meta.append(f"License: {repo['license']}")
    if repo["created_at"]:
        meta.append(f"Created {repo['created_at'][:7]}")
    if meta:
        lines.append(" · ".join(meta))
    lines += extras or []
    return "\n".join(lines)


def _tags(raw: str | None) -> list:
    try:
        v = json.loads(raw) if raw else []
    except ValueError:
        return []
    return v if isinstance(v, list) else []


def card_extras(conn: sqlite3.Connection, ghr_id: int) -> list[str]:
    """Card lines from enrichment: the Awesome lists a repo is in and the papers its README cites."""
    lines = []
    lists = [f"{r['full_name'].split('/')[-1]} ({r['section']})" if r["section"]
             else r["full_name"].split("/")[-1]
             for r in conn.execute(
                 "SELECT l.full_name, rl.section FROM repo_lists rl JOIN repos l ON l.ghr_id = rl.list_id "
                 "WHERE rl.ghr_id = ? ORDER BY l.stars DESC LIMIT 5", (ghr_id,))]
    if lists:
        lines.append(f"Listed in: {'; '.join(lists)}")
    money = conn.execute("SELECT funding, signals FROM repo_money WHERE ghr_id = ?", (ghr_id,)).fetchone()
    if money:
        tags = _tags(money["signals"]) + (["sponsors"] if _tags(money["funding"]) else [])
        if tags:
            lines.append(f"Business model hints: {', '.join(tags)}")
    papers = [r[0] for r in conn.execute(
        "SELECT p.title FROM repo_papers rp JOIN papers p ON p.arxiv_id = rp.arxiv_id "
        "WHERE rp.ghr_id = ? AND p.title IS NOT NULL ORDER BY rp.arxiv_id LIMIT 3", (ghr_id,))]
    if papers:
        lines.append(f"README mentions papers: {'; '.join(papers)}")
    return lines


def clean_readme(text: str) -> str:
    out: list[str] = []
    block: list[str] = []
    in_code = False
    text = _HTML_COMMENT.sub("", text)
    for line in text.splitlines():
        if _FENCE.match(line):
            if not in_code:
                in_code, block = True, [line]
            else:
                block.append(line)
                if len(block) - 2 > MAX_CODE_LINES:
                    out.append("[code block omitted]")
                else:
                    out.extend(block)
                in_code, block = False, []
            continue
        if in_code:
            block.append(line)
            continue
        line = _BADGE.sub("", line)
        line = _IMAGE.sub("", line)
        line = _HTML_TAG.sub("", line)
        out.append(line.rstrip())
    if in_code:  # unterminated fence
        out.extend(block[: MAX_CODE_LINES + 1])
    cleaned = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def split_sections(text: str) -> list[tuple[str, str]]:
    """Split at # / ## headings (ignoring fenced code). Returns [(heading, body)]."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    in_code = False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_code = not in_code
        m = None if in_code else re.match(r"^(#{1,2})\s+(.*\S)", line)
        if m:
            sections.append((m.group(2).strip(), []))
        else:
            sections[-1][1].append(line)
    return [(h, "\n".join(b).strip()) for h, b in sections if "\n".join(b).strip() or h]


def pack(body: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP) -> list[str]:
    if len(body) <= size:
        return [body]
    paras: list[str] = []
    for p in re.split(r"\n\s*\n", body):
        while len(p) > size:
            paras.append(p[:size])
            p = p[size:]
        paras.append(p)
    chunks: list[str] = []
    cur = ""
    for p in paras:
        if cur and len(cur) + len(p) + 2 > size:
            chunks.append(cur)
            cur = cur[-overlap:] + "\n\n" + p
        else:
            cur = f"{cur}\n\n{p}" if cur else p
    if cur.strip():
        chunks.append(cur)
    return chunks


def readme_chunks(full_name: str, readme: str) -> list[tuple[str, str]]:
    """[(heading, text)], capped at MAX_README_CHUNKS (the earliest sections are kept)."""
    out: list[tuple[str, str]] = []
    for heading, body in split_sections(clean_readme(readme)):
        for piece in pack(body):
            label = f"{full_name} › {heading}" if heading else full_name
            if piece.strip() or heading:
                out.append((heading, f"{label}\n{piece}".strip()))
        if len(out) >= MAX_README_CHUNKS:
            break
    return out[:MAX_README_CHUNKS]


@dataclass
class Pending:
    ghr_id: int
    kind: str
    ord: int
    heading: str | None
    text: str
    hash: str


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def index_chunks(conn: sqlite3.Connection, full: bool = False) -> dict[str, int]:
    """Bring the chunks table in line with the repos: only changed chunks are rewritten.
    Hidden repos (gone, filtered, below the threshold) keep no chunks."""
    if full:
        conn.execute("DELETE FROM chunks")
    marks = ",".join("?" * len(HIDDEN))
    removed = conn.execute(
        f"DELETE FROM chunks WHERE ghr_id IN (SELECT ghr_id FROM repos "
        f"WHERE enrich_status IN ({marks}))", HIDDEN).rowcount
    removed += conn.execute(
        "DELETE FROM chunks WHERE ghr_id NOT IN (SELECT ghr_id FROM repos)").rowcount
    existing: dict[int, dict[tuple[str, int], sqlite3.Row]] = {}
    for r in conn.execute("SELECT id, ghr_id, kind, ord, text_hash FROM chunks"):
        existing.setdefault(r["ghr_id"], {})[(r["kind"], r["ord"])] = r
    written = 0
    # ids first, then one row at a time: READMEs are large and there can be tens of thousands
    ids = [r[0] for r in conn.execute(
        "SELECT ghr_id FROM repos WHERE enrich_status = 'ok' AND full_name NOT LIKE '%~%'")]
    for ghr_id in ids:
        repo = conn.execute("SELECT * FROM repos WHERE ghr_id = ?", (ghr_id,)).fetchone()
        card = build_card(repo, card_extras(conn, ghr_id))
        desired = [Pending(repo["ghr_id"], "card", 0, None, card, _hash(card))]
        if repo["readme"]:
            for i, (heading, text) in enumerate(readme_chunks(repo["full_name"], repo["readme"])):
                desired.append(Pending(repo["ghr_id"], "readme", i, heading or None, text,
                                       _hash(text)))
        have = existing.get(repo["ghr_id"], {})
        keep: set[int] = set()
        for d in desired:
            ex = have.get((d.kind, d.ord))
            if ex and ex["text_hash"] == d.hash:
                keep.add(ex["id"])
            else:
                if ex:
                    conn.execute("DELETE FROM chunks WHERE id = ?", (ex["id"],))
                    removed += 1
                conn.execute("INSERT INTO chunks (ghr_id, kind, ord, heading, text, text_hash) "
                             "VALUES (?,?,?,?,?,?)",
                             (d.ghr_id, d.kind, d.ord, d.heading, d.text, d.hash))
                written += 1
        wanted = {(d.kind, d.ord) for d in desired}
        for key, r in have.items():  # obsolete: the README got shorter
            if r["id"] not in keep and key not in wanted:
                conn.execute("DELETE FROM chunks WHERE id = ?", (r["id"],))
                removed += 1
    if written or removed:
        touch_sync(conn)
    conn.commit()
    return {"written": written, "removed": removed,
            "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]}
