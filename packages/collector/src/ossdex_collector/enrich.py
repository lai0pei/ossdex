"""Signals derived from READMEs already stored: Awesome-list membership, arXiv paper mentions and
business-model hints.

Nothing here talks to GitHub. `link_awesome` and `extract_papers` read the stored READMEs;
`fetch_paper_titles` asks arXiv for the titles of the papers found. A link means "the README
mentions this paper", not "the repo implements it".
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable

import httpx
from ossdex_core.store import now_iso, touch_sync

LIST_TOPICS = ("awesome-list", "awesome")
MIN_LIST_LINKS = 20  # fewer resolved links and it is not a list worth tagging with
MAX_PAPERS_PER_REPO = 10  # more than this is a reading list, not a project
ARXIV_URL = "https://export.arxiv.org/api/query"
ARXIV_BATCH = 50
SKIP_LINKS = {"sindresorhus/awesome"}  # the badge nearly every list carries

_GH_LINK = re.compile(r"github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)", re.IGNORECASE)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_PAPER = re.compile(r"(?:arxiv\.org/(?:abs|pdf)|huggingface\.co/papers)/(\d{4}\.\d{4,5})(?:v\d+)?",
                    re.IGNORECASE)
_ATOM = "{http://www.w3.org/2005/Atom}"

# How a project makes money, read from its README. Conservative on purpose: a tag is a hint that
# companies already pay for something around the project, not a measurement.
MONEY_PATTERNS = {
    "hosted_cloud": re.compile(
        r"managed (?:cloud|service|hosting)|hosted (?:version|service|solution|offering|platform)"
        r"|cloud[- ]hosted|(?:our|the) (?:hosted )?cloud (?:version|service|offering|platform)"
        r"|cloud edition", re.IGNORECASE),
    "enterprise": re.compile(
        r"enterprise (?:edition|plan|version|license|support|features|tier)"
        r"|commercial (?:license|edition|version)", re.IGNORECASE),
    "pricing": re.compile(
        r"pricing (?:page|plans?|tiers?)|(?:see|view|check|our) (?:the )?pricing|/pricing\b"
        r"|\[pricing\]", re.IGNORECASE),
    "support_consulting": re.compile(
        r"professional services|paid support|commercial support|support plans?|support contracts?"
        r"|(?:custom|premium) support|\bconsulting\b", re.IGNORECASE),
}
MONEY_TAGS = (*MONEY_PATTERNS, "sponsors")  # `sponsors`: the repo lists funding links

Log = Callable[[str], None]


def github_links(text: str) -> list[tuple[str, str]]:
    """[(section, 'owner/repo')] for every github.com repo link, in order. `section` is the
    nearest preceding heading. Paths (/tree/..., /blob/...), `.git`, queries and anchors are dropped."""
    out: list[tuple[str, str]] = []
    section = ""
    for line in text.splitlines():
        m = _HEADING.match(line)
        if m:
            section = _MD_LINK.sub(r"\1", m.group(1)).strip()
        for owner, name in _GH_LINK.findall(line):
            name = name.removesuffix(".git").rstrip(".")
            if name:
                out.append((section, f"{owner}/{name}"))
    return out


def arxiv_ids(text: str) -> list[str]:
    """Distinct new-style arXiv ids a README links to (version suffix dropped), in order."""
    return list(dict.fromkeys(_PAPER.findall(text)))


def _visible_names(conn: sqlite3.Connection) -> dict[str, int]:
    return {r[0].lower(): r[1] for r in conn.execute(
        "SELECT full_name, ghr_id FROM repos WHERE enrich_status = 'ok' AND full_name NOT LIKE '%~%'")}


def link_awesome(conn: sqlite3.Connection) -> dict[str, int]:
    """Rebuild `repo_lists` from the READMEs of repos topped `awesome-list`/`awesome`. Cheap, so it
    is redone in full each time (a list can link to repos that were collected later)."""
    names = _visible_names(conn)
    marks = ",".join("?" * len(LIST_TOPICS))
    lists = conn.execute(
        f"SELECT ghr_id, full_name, readme FROM repos WHERE enrich_status = 'ok' "
        f"AND readme IS NOT NULL AND EXISTS (SELECT 1 FROM json_each(CASE WHEN json_valid(topics) "
        f"THEN topics ELSE '[]' END) WHERE lower(value) IN ({marks}))", LIST_TOPICS).fetchall()
    rows: list[tuple[int, int, str]] = []
    kept = 0
    for lst in lists:
        found: dict[int, str] = {}
        for section, name in github_links(lst["readme"]):
            key = name.lower()
            gid = names.get(key)
            if gid is None or gid == lst["ghr_id"] or key in SKIP_LINKS:
                continue
            found.setdefault(gid, section)
        if len(found) >= MIN_LIST_LINKS:
            kept += 1
            rows += [(gid, lst["ghr_id"], section) for gid, section in found.items()]
    conn.execute("DELETE FROM repo_lists")
    conn.executemany("INSERT INTO repo_lists(ghr_id, list_id, section) VALUES (?,?,?)", rows)
    conn.commit()
    return {"lists": kept, "links": len(rows)}


def extract_papers(conn: sqlite3.Connection) -> dict[str, int]:
    """Fill `repo_papers` for repos whose README changed since last time (by `readme_sha`)."""
    done = {r[0]: r[1] for r in conn.execute("SELECT ghr_id, readme_sha FROM paper_src")}
    ids = [r[0] for r in conn.execute(
        "SELECT ghr_id FROM repos WHERE enrich_status = 'ok' AND readme IS NOT NULL")]
    scanned = linked = skipped = 0
    for ghr_id in ids:
        repo = conn.execute("SELECT readme, readme_sha FROM repos WHERE ghr_id = ?",
                            (ghr_id,)).fetchone()
        sha = repo["readme_sha"] or ""
        if done.get(ghr_id) == sha:
            continue
        scanned += 1
        found = arxiv_ids(repo["readme"])
        conn.execute("DELETE FROM repo_papers WHERE ghr_id = ?", (ghr_id,))
        if len(found) > MAX_PAPERS_PER_REPO:
            skipped += 1
        elif found:
            linked += 1
            conn.executemany("INSERT INTO repo_papers(ghr_id, arxiv_id) VALUES (?,?)",
                             [(ghr_id, a) for a in found])
        conn.execute("INSERT OR REPLACE INTO paper_src(ghr_id, readme_sha) VALUES (?,?)",
                     (ghr_id, sha))
    conn.commit()
    return {"scanned": scanned, "repos_with_papers": linked, "reading_lists_skipped": skipped}


def money_tags(text: str) -> list[str]:
    """Business-model tags a README mentions, in a fixed order."""
    return [tag for tag, rx in MONEY_PATTERNS.items() if rx.search(text)]


def money_signals(conn: sqlite3.Connection) -> dict[str, int]:
    """Fill `repo_money.signals` for repos whose README changed since last time. Funding links
    (`repo_money.funding`) come from discover and are left alone."""
    done = {r[0]: r[1] for r in conn.execute(
        "SELECT ghr_id, readme_sha FROM repo_money WHERE signals IS NOT NULL")}
    ids = [r[0] for r in conn.execute(
        "SELECT ghr_id FROM repos WHERE enrich_status = 'ok' AND readme IS NOT NULL")]
    scanned = tagged = 0
    for ghr_id in ids:
        repo = conn.execute("SELECT readme, readme_sha FROM repos WHERE ghr_id = ?",
                            (ghr_id,)).fetchone()
        sha = repo["readme_sha"] or ""
        if ghr_id in done and done[ghr_id] == sha:
            continue
        scanned += 1
        tags = money_tags(repo["readme"])
        tagged += bool(tags)
        conn.execute("INSERT INTO repo_money(ghr_id, signals, readme_sha) VALUES (?,?,?) "
                     "ON CONFLICT(ghr_id) DO UPDATE SET signals = excluded.signals, "
                     "readme_sha = excluded.readme_sha", (ghr_id, json.dumps(tags), sha))
    conn.commit()
    return {"scanned": scanned, "tagged": tagged}


def parse_atom(xml_text: str) -> dict[str, tuple[str, str | None]]:
    """{arxiv_id: (title, published)} from an arXiv API response."""
    out: dict[str, tuple[str, str | None]] = {}
    root = ET.fromstring(xml_text)
    for entry in root.iter(f"{_ATOM}entry"):
        ident = (entry.findtext(f"{_ATOM}id") or "").rsplit("/abs/", 1)[-1]
        ident = re.sub(r"v\d+$", "", ident)
        title = " ".join((entry.findtext(f"{_ATOM}title") or "").split())
        if ident and title:
            out[ident] = (title, entry.findtext(f"{_ATOM}published"))
    return out


def fetch_paper_titles(conn: sqlite3.Connection, *, client: httpx.Client | None = None,
                       delay: float = 3.0, log: Log = lambda m: None) -> dict[str, int]:
    """Look up titles for linked ids not yet in `papers`, politely (batched, `delay` s apart).
    Ids arXiv does not know are stored without a title so they are not asked again."""
    todo = [r[0] for r in conn.execute(
        "SELECT DISTINCT arxiv_id FROM repo_papers WHERE arxiv_id NOT IN (SELECT arxiv_id FROM papers) "
        "ORDER BY arxiv_id")]
    own = client is None
    client = client or httpx.Client(timeout=30, headers={"User-Agent": "ossdex"})
    fetched = unknown = 0
    try:
        for i in range(0, len(todo), ARXIV_BATCH):
            batch = todo[i:i + ARXIV_BATCH]
            if i:
                time.sleep(delay)
            try:
                resp = client.get(ARXIV_URL, params={"id_list": ",".join(batch),
                                                     "max_results": len(batch)})
                resp.raise_for_status()
                titles = parse_atom(resp.text)
            except (httpx.HTTPError, ET.ParseError) as e:
                log(f"arXiv lookup stopped: {e}")
                break
            now = now_iso()
            for a in batch:
                title, published = titles.get(a, (None, None))
                conn.execute("INSERT OR REPLACE INTO papers(arxiv_id, title, published, fetched_at) "
                             "VALUES (?,?,?,?)", (a, title, published, now))
                fetched += title is not None
                unknown += title is None
            conn.commit()
    finally:
        if own:
            client.close()
    return {"titles": fetched, "unknown": unknown, "pending": len(todo) - fetched - unknown}


def enrich_all(conn: sqlite3.Connection, *, client: httpx.Client | None = None,
               delay: float = 3.0, offline: bool = False,
               log: Log = lambda m: None) -> dict[str, dict[str, int]]:
    out = {"awesome": link_awesome(conn), "papers": extract_papers(conn),
           "money": money_signals(conn)}
    out["titles"] = ({"titles": 0, "unknown": 0, "pending": 0} if offline
                     else fetch_paper_titles(conn, client=client, delay=delay, log=log))
    touch_sync(conn)
    conn.commit()
    return out

