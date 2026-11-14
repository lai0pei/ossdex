"""The writable side of ossdex.db: schema, upserts and the visibility rules.

`enrich_status` decides what the web side shows: `ok` is visible; `gone` (deleted on GitHub),
`filtered` (no longer qualifies: fork, archived, unlicensed...) and `below` (under the current star
threshold) are hidden. Nothing is deleted until `ossdex prune`.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

SCHEMA_VERSION = 1
HIDDEN = ("gone", "filtered", "below")

SCHEMA = """
CREATE TABLE repos (
  ghr_id INTEGER PRIMARY KEY,
  node_id TEXT,
  full_name TEXT NOT NULL,
  url TEXT,
  language TEXT, description TEXT, topics TEXT,
  homepage TEXT, license TEXT, archived INTEGER, is_fork INTEGER,
  stars INTEGER, forks INTEGER, open_issues INTEGER, stars_at TEXT,
  created_at TEXT, pushed_at TEXT,
  readme TEXT, readme_sha TEXT, readme_at TEXT,
  first_seen TEXT, last_seen TEXT,
  enriched_at TEXT, enrich_status TEXT
);
CREATE UNIQUE INDEX repos_full_name ON repos(lower(full_name));
CREATE INDEX repos_status ON repos(enrich_status);
CREATE INDEX repos_stars ON repos(stars);
CREATE INDEX IF NOT EXISTS repos_language ON repos(lower(language));
CREATE INDEX IF NOT EXISTS repos_pushed ON repos(pushed_at);
CREATE INDEX IF NOT EXISTS repos_created ON repos(created_at);
CREATE INDEX IF NOT EXISTS repos_forks ON repos(forks);

CREATE TABLE repo_stats (
  ghr_id INTEGER NOT NULL REFERENCES repos, day TEXT NOT NULL,
  stars INTEGER, forks INTEGER,
  PRIMARY KEY (ghr_id, day)
) WITHOUT ROWID;
CREATE INDEX repo_stats_day ON repo_stats(day);

CREATE TABLE slices (
  query TEXT PRIMARY KEY, total INTEGER NOT NULL, cursor TEXT,
  done INTEGER NOT NULL DEFAULT 0, truncated INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE chunks (
  id INTEGER PRIMARY KEY, ghr_id INTEGER NOT NULL REFERENCES repos,
  kind TEXT NOT NULL,
  ord INTEGER NOT NULL, heading TEXT, text TEXT NOT NULL, text_hash TEXT NOT NULL
);
CREATE INDEX chunks_repo ON chunks(ghr_id);
CREATE VIRTUAL TABLE chunks_fts USING fts5(
  text, heading, content='chunks', content_rowid='id', tokenize='porter unicode61'
);
CREATE TRIGGER chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text, heading) VALUES (new.id, new.text, new.heading);
END;
CREATE TRIGGER chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, heading)
  VALUES ('delete', old.id, old.text, old.heading);
END;
CREATE TRIGGER chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text, heading)
  VALUES ('delete', old.id, old.text, old.heading);
  INSERT INTO chunks_fts(rowid, text, heading) VALUES (new.id, new.text, new.heading);
END;
"""

# Enrichment tables (see enrich.py). `IF NOT EXISTS`, so older databases gain them without a
# schema-version bump; a snapshot from an older collector simply lacks them (ReadDb copes).
ENRICH_SCHEMA = """
CREATE TABLE IF NOT EXISTS repo_lists (
  ghr_id INTEGER NOT NULL, list_id INTEGER NOT NULL, section TEXT,
  PRIMARY KEY (ghr_id, list_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS repo_lists_list ON repo_lists(list_id);
CREATE TABLE IF NOT EXISTS repo_papers (
  ghr_id INTEGER NOT NULL, arxiv_id TEXT NOT NULL, PRIMARY KEY (ghr_id, arxiv_id)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS papers (
  arxiv_id TEXT PRIMARY KEY, title TEXT, published TEXT, fetched_at TEXT
);
CREATE TABLE IF NOT EXISTS paper_src (ghr_id INTEGER PRIMARY KEY, readme_sha TEXT);
CREATE TABLE IF NOT EXISTS repo_money (
  ghr_id INTEGER PRIMARY KEY,
  funding TEXT,   -- JSON [{platform, url}] from the repo's funding links (set by discover)
  signals TEXT,   -- JSON ["hosted_cloud", ...] business-model tags found in the README
  readme_sha TEXT -- the README the signals were read from
);
CREATE TABLE IF NOT EXISTS repo_issues (
  ghr_id INTEGER NOT NULL, number INTEGER NOT NULL, title TEXT, url TEXT,
  reactions INTEGER, comments INTEGER, labels TEXT, created_at TEXT,
  PRIMARY KEY (ghr_id, number)
) WITHOUT ROWID;
CREATE TABLE IF NOT EXISTS repo_demand (
  ghr_id INTEGER PRIMARY KEY, help_wanted INTEGER, bounties INTEGER, fetched_at TEXT
);
"""

# GitHub timestamps are `...Z`; ours use the same shape so they compare correctly as text.
def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_iso() -> str:
    return datetime.now(UTC).date().isoformat()


def finish(conn: sqlite3.Connection) -> bool:
    """End-of-run housekeeping: refresh the query planner's statistics, then fold the write-ahead
    log back into the database and truncate it. Readers that never stop (the web server) would
    otherwise keep the WAL file growing. Returns False if readers held it up (it is retried on the
    next run)."""
    conn.commit()
    conn.execute("PRAGMA optimize")
    busy, _, _ = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
    return not busy


def connect(path: Path | str) -> sqlite3.Connection:
    """Open (and create) the database for writing. WAL, so the web server can read meanwhile."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == 0:
        conn.executescript(SCHEMA)
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.commit()
    elif version != SCHEMA_VERSION:
        conn.close()
        raise RuntimeError(f"{path} has schema version {version}, expected {SCHEMA_VERSION}")
    # Ensure helpful secondary indexes exist
    conn.execute("CREATE INDEX IF NOT EXISTS repos_language ON repos(lower(language))")
    conn.execute("CREATE INDEX IF NOT EXISTS repos_pushed ON repos(pushed_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS repos_created ON repos(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS repos_forks ON repos(forks)")
    conn.executescript(ENRICH_SCHEMA)
    conn.commit()
    return conn


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta(key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def touch_sync(conn: sqlite3.Connection) -> None:
    """`meta.last_sync` is the data's "as of"; the web side shows it and keys its index on it."""
    set_meta(conn, "last_sync", now_iso())


def reject_reason(node: dict, exclude_topics: tuple[str, ...] = (), *,
                  require_license: bool = True) -> str | None:
    """Why a GitHub repo node is not a repo we keep, or None if it qualifies."""
    if node.get("isFork"):
        return "fork"
    if node.get("isArchived"):
        return "archived"
    if node.get("isMirror"):
        return "mirror"
    if node.get("isTemplate"):
        return "template"
    if require_license and not node.get("licenseInfo"):
        return "unlicensed"
    if exclude_topics and set(node_topics(node)) & set(exclude_topics):
        return "excluded-topic"
    return None


def node_topics(node: dict) -> list[str]:
    nodes = ((node.get("repositoryTopics") or {}).get("nodes")) or []
    return [n["topic"]["name"].lower() for n in nodes if n and n.get("topic")]


def upsert_repo(conn: sqlite3.Connection, node: dict, *, now: str, day: str) -> bool:
    """Insert or update one repo from a GraphQL node and record today's star snapshot.
    Returns True when the repo is new. README columns are never touched here."""
    ghr_id, name = node["databaseId"], node["nameWithOwner"]
    # a name can be reused by a different repo after a rename: free it up first
    clash = conn.execute("SELECT ghr_id FROM repos WHERE lower(full_name) = lower(?) AND ghr_id != ?",
                         (name, ghr_id)).fetchone()
    if clash:
        conn.execute("UPDATE repos SET full_name = full_name || '~' || ghr_id WHERE ghr_id = ?",
                     (clash[0],))
    existed = conn.execute("SELECT 1 FROM repos WHERE ghr_id = ?", (ghr_id,)).fetchone() is not None
    lic = node.get("licenseInfo") or {}
    stars = node.get("stargazerCount")
    conn.execute(
        """INSERT INTO repos (ghr_id, node_id, full_name, url, language, description, topics,
             homepage, license, archived, is_fork, stars, forks, open_issues, stars_at,
             created_at, pushed_at, first_seen, last_seen, enriched_at, enrich_status)
           VALUES (:id, :node, :name, :url, :lang, :desc, :topics, :home, :lic, :arch, :fork,
             :stars, :forks, :issues, :now, :created, :pushed, :now, :now, :now, 'ok')
           ON CONFLICT(ghr_id) DO UPDATE SET
             node_id = excluded.node_id, full_name = excluded.full_name, url = excluded.url,
             language = excluded.language, description = excluded.description,
             topics = excluded.topics, homepage = excluded.homepage, license = excluded.license,
             archived = excluded.archived, is_fork = excluded.is_fork, stars = excluded.stars,
             forks = excluded.forks, open_issues = excluded.open_issues,
             stars_at = excluded.stars_at, created_at = excluded.created_at,
             pushed_at = excluded.pushed_at, last_seen = excluded.last_seen,
             enriched_at = excluded.enriched_at, enrich_status = 'ok'""",
        {"id": ghr_id, "node": node.get("id"), "name": name,
         "url": node.get("url") or f"https://github.com/{name}",
         "lang": (node.get("primaryLanguage") or {}).get("name"),
         "desc": node.get("description"), "topics": json.dumps(node_topics(node)),
         "home": node.get("homepageUrl") or None, "lic": lic.get("spdxId") or lic.get("key"),
         "arch": int(bool(node.get("isArchived"))), "fork": int(bool(node.get("isFork"))),
         "stars": stars, "forks": node.get("forkCount"),
         "issues": (node.get("openIssues") or {}).get("totalCount"), "now": now,
         "created": node.get("createdAt"), "pushed": node.get("pushedAt")})
    if isinstance(node.get("fundingLinks"), list):
        links = [{"platform": x.get("platform"), "url": x.get("url")} for x in node["fundingLinks"]]
        conn.execute("INSERT INTO repo_money(ghr_id, funding) VALUES (?, ?) "
                     "ON CONFLICT(ghr_id) DO UPDATE SET funding = excluded.funding",
                     (ghr_id, json.dumps(links)))
    if stars is not None:
        conn.execute("INSERT OR REPLACE INTO repo_stats(ghr_id, day, stars, forks) VALUES (?,?,?,?)",
                     (ghr_id, day, stars, node.get("forkCount")))
    return not existed


def mark(conn: sqlite3.Connection, ghr_id: int, status: str, now: str) -> None:
    conn.execute("UPDATE repos SET enrich_status = ?, enriched_at = ? WHERE ghr_id = ?",
                 (status, now, ghr_id))


def apply_threshold(conn: sqlite3.Connection, min_stars: int) -> None:
    """Visible means: qualifies and has at least `min_stars`. Lowering the threshold brings the
    hidden `below` repos back with the stars we last saw; raising it hides without deleting."""
    conn.execute("UPDATE repos SET enrich_status = 'below' "
                 "WHERE enrich_status = 'ok' AND COALESCE(stars, 0) < ?", (min_stars,))
    conn.execute("UPDATE repos SET enrich_status = 'ok' "
                 "WHERE enrich_status = 'below' AND COALESCE(stars, 0) >= ?", (min_stars,))
    set_meta(conn, "min_stars", str(min_stars))


def prune(conn: sqlite3.Connection, *, dry_run: bool = False) -> dict[str, int]:
    """Delete hidden repos for good, with their chunks and star snapshots."""
    marks = ",".join("?" * len(HIDDEN))
    ids = [r[0] for r in conn.execute(f"SELECT ghr_id FROM repos WHERE enrich_status IN ({marks})",
                                      HIDDEN)]
    out = {"repos": len(ids), "chunks": 0, "snapshots": 0}
    for i in range(0, len(ids), 500):
        part = ids[i:i + 500]
        q = ",".join("?" * len(part))
        out["chunks"] += conn.execute(f"SELECT COUNT(*) FROM chunks WHERE ghr_id IN ({q})",
                                      part).fetchone()[0]
        out["snapshots"] += conn.execute(f"SELECT COUNT(*) FROM repo_stats WHERE ghr_id IN ({q})",
                                         part).fetchone()[0]
        if not dry_run:
            conn.execute(f"DELETE FROM chunks WHERE ghr_id IN ({q})", part)
            conn.execute(f"DELETE FROM repo_lists WHERE ghr_id IN ({q}) OR list_id IN ({q})",
                         part + part)
            conn.execute(f"DELETE FROM repo_papers WHERE ghr_id IN ({q})", part)
            conn.execute(f"DELETE FROM paper_src WHERE ghr_id IN ({q})", part)
            for table in ("repo_money", "repo_issues", "repo_demand"):
                conn.execute(f"DELETE FROM {table} WHERE ghr_id IN ({q})", part)
            conn.execute(f"DELETE FROM repo_stats WHERE ghr_id IN ({q})", part)
            conn.execute(f"DELETE FROM repos WHERE ghr_id IN ({q})", part)
    if not dry_run:
        touch_sync(conn)
        conn.commit()
    return out
