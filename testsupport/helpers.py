"""Builds a small ossdex.db with the real schema."""

from __future__ import annotations

import json
from pathlib import Path

from ossdex_core.chunks import index_chunks
from ossdex_core.store import connect

# ghr_id, full_name, language, desc, topics, license, stars, forks, status, pushed, created
REPOS = [
    (1, "acme/golang-api", "Go", "Fast HTTP API framework for Go", ["go", "api"], "MIT", 5000, 400,
     "ok", "2026-10-20", "2022-01-01"),
    (2, "acme/langchain-agent", "Python", "AI agents built on langchain", ["langchain", "ai", "llm"],
     "Apache-2.0", 9000, 900, "ok", "2026-10-25", "2024-03-01"),
    (3, "acme/rag-kit", "Python", "Toolkit for retrieval augmented generation", ["rag"], "MIT", 1200,
     80, "ok", "2026-10-10", "2025-01-01"),
    (4, "acme/rust-db", "Rust", "Embedded database written in Rust", ["database", "rust"], "MIT",
     3000, 200, "ok", "2026-09-01", "2021-05-05"),
    (5, "old/archived-go", "Go", "Abandoned Go project", ["go"], "MIT", 800, 50, "filtered",
     "2020-01-01", "2018-01-01"),
    (6, "bare/unenriched", "GO", None, None, "MIT", 400, 10, "ok", None, None),
    (7, "gone/deleted", "Go", "Was removed", ["go"], "MIT", 100, 5, "gone", None, None),
    (8, "acme/fork-py", "Python", "A fork of a python tool", ["python"], "MIT", 50, 2, "filtered",
     "2026-10-01", "2025-06-01"),
    (9, "foo/vector-search", "Python", "Nearest neighbour search over embeddings",
     ["vector", "search"], "MIT", 2500, 130, "ok", "2026-10-22", "2025-02-02"),
    (10, "low/below-threshold", "Go", "Small go helper", ["go"], "MIT", 90, 3, "below",
     "2026-10-01", "2023-01-01"),
]

# the newest snapshot day is 2026-10-27: gains are measured back from it
LAST_DAY = "2026-10-27"
SNAPSHOTS = {  # ghr_id -> {day: stars}; the current stars are added for LAST_DAY
    1: {"2026-09-27": 4700, "2026-10-20": 4880, "2026-10-26": 4980},
    2: {"2026-09-27": 8200, "2026-10-20": 8700, "2026-10-26": 8950},
    9: {"2026-10-20": 2350, "2026-10-26": 2470},
}

README = {
    1: "# golang-api\nA fast HTTP framework for Go using goroutines.\n",
    2: "# langchain-agent\nBuild agents with langchain and any llm.\n",
    3: "# rag-kit\nThis toolkit wraps langchain retrievers for question answering.\n",
    4: "# rust-db\nA small embedded storage engine.\n",
    9: "# vector-search\nFind nearest neighbours using embeddings and similarity.\n",
}


def build_fixture_db(path: Path) -> Path:
    """A small ossdex.db made with the real schema and the real chunk builder."""
    conn = connect(path)
    conn.execute("INSERT INTO meta VALUES ('last_sync', '2026-10-27T06:13:21Z')")
    conn.execute("INSERT INTO meta VALUES ('min_stars', '100')")
    for (gid, name, lang, desc, topics, lic, stars, forks, status, pushed, created) in REPOS:
        conn.execute(
            "INSERT INTO repos (ghr_id, node_id, full_name, url, language, description, topics, "
            "license, stars, forks, open_issues, enrich_status, pushed_at, created_at, readme, "
            "first_seen, last_seen, enriched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (gid, f"node{gid}", name, f"https://github.com/{name}", lang, desc,
             json.dumps(topics) if topics is not None else None, lic, stars, forks, gid, status,
             pushed, created, README.get(gid), "2026-10-01T00:00:00Z", "2026-10-27T00:00:00Z",
             "2026-10-27T00:00:00Z"),
        )
        if status in ("ok", "below"):
            snaps = {**SNAPSHOTS.get(gid, {}), LAST_DAY: stars}
            conn.executemany("INSERT INTO repo_stats(ghr_id, day, stars, forks) VALUES (?,?,?,?)",
                             [(gid, d, n, forks) for d, n in snaps.items()])
    conn.commit()
    index_chunks(conn)
    conn.execute("UPDATE meta SET value = '2026-10-27T06:13:21Z' WHERE key = 'last_sync'")
    conn.commit()
    conn.close()
    return path
