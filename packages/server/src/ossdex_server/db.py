"""Read-only access to ossdex.db (the collector owns writes; the web side only reads)."""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

from ossdex_core.store import HIDDEN, SCHEMA_VERSION

BUSY_RETRIES = 5
MMAP_BYTES = 2_147_418_112  # SQLite's default ceiling; the database is mapped, not read()
ENRICH_TABLES = r"repo_lists|repo_papers|papers|repo_money"

# `gone`, `filtered` and `below` (under the star threshold) repos are hidden everywhere.
VISIBLE = "COALESCE(enrich_status, '') NOT IN (" + ",".join(f"'{s}'" for s in HIDDEN) + ")"
# a repo with a README is fully indexed; the rest are known by their GitHub metadata only
ENRICHED = "readme IS NOT NULL"


class DbError(RuntimeError):
    pass


class QueryTimeout(DbError):
    """The request used up its time budget, or waited too long for a free query slot."""


class ReadDb:
    """Read-only access with one SQLite connection per thread.

    SQLite releases the GIL while it runs a query, so threads with their own connections really run
    in parallel (WAL mode: readers never block each other or the collector's writer). Three limits
    keep a busy public server healthy:
    - `max_concurrent` caps the requests using SQLite at once *in this process* (default 1, see
      `open_db`): Python's sqlite3 hands the GIL over on every row step, so competing threads burn
      CPU in the kernel instead of working (measured: 4 threads in one process are slower than 1,
      while 4 processes are 4x faster). Scale with worker processes, not threads;
    - `budget()` gives a request a deadline and holds a slot for the whole request, so requests do
      not interleave; waiting for the slot counts against the deadline, and a request that cannot
      get one in time is refused (QueryTimeout) instead of piling up;
    - SQLite is *interrupted* when the deadline passes, so an abandoned query cannot keep a thread
      and a slot busy.
    """

    PROGRESS_STEPS = 20_000  # SQLite VM instructions between deadline checks

    def __init__(self, path: Path, *, check_schema: bool = True, max_concurrent: int | None = None,
                 query_timeout: float | None = None):
        self.path = Path(path)
        if not self.path.exists():
            raise DbError(f"database not found: {self.path} "
                          "(run `ossdex-collector update` to collect repos, or set OSSDEX_DB)")
        self.query_timeout = query_timeout
        self._gate = threading.BoundedSemaphore(max_concurrent) if max_concurrent else None
        self._local = threading.local()
        self._conns: list[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()
        self._have: set[str] = set()
        self._ver_conn: sqlite3.Connection | None = None
        self._ver_lock = threading.Lock()
        if check_schema:
            version = self.conn.execute("PRAGMA user_version").fetchone()[0]
            if version != SCHEMA_VERSION:
                raise DbError(f"{self.path} has schema version {version}, expected "
                              f"{SCHEMA_VERSION}")

    def _connect(self) -> sqlite3.Connection:
        # each connection is used by its own thread only; the flag just lets close() run anywhere
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=10,
                               check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA mmap_size = {MMAP_BYTES}")  # no read() calls: pages come from the OS cache
        with self._conns_lock:
            self._conns.append(conn)
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        """This thread's connection (created on first use)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._local.conn = self._connect()
        return conn

    # ---- time budget ----
    @contextmanager
    def budget(self, seconds: float | None = None) -> Iterator[None]:
        """Give the queries this thread runs inside the block one shared deadline. Nested blocks keep
        the earlier deadline."""
        seconds = self.query_timeout if seconds is None else seconds
        previous = getattr(self._local, "deadline", None)
        if seconds is not None:
            deadline = time.monotonic() + seconds
            self._local.deadline = deadline if previous is None else min(previous, deadline)
        outermost = not getattr(self._local, "holding", False) and self._gate is not None
        try:
            if outermost:
                if not self._gate.acquire(timeout=seconds):
                    raise QueryTimeout("server busy: no free query slot before the time budget ended")
                self._local.holding = True
            try:
                yield
            finally:
                if outermost:
                    self._local.holding = False
                    self._gate.release()
        finally:
            self._local.deadline = previous

    def _run(self, sql: str, params: tuple) -> list[sqlite3.Row]:
        deadline = getattr(self._local, "deadline", None)
        conn = self.conn
        if deadline is None:
            return conn.execute(sql, params).fetchall()
        if time.monotonic() >= deadline:
            raise QueryTimeout("request time budget used up")
        conn.set_progress_handler(lambda: time.monotonic() >= deadline, self.PROGRESS_STEPS)
        try:
            return conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e):
                raise QueryTimeout("query exceeded the time budget") from e
            raise
        finally:
            conn.set_progress_handler(None, 0)

    def _has(self, *names: str) -> bool:
        """Whether these tables exist. Snapshots from an older collector lack the newer ones; a
        `True` is remembered, a `False` is re-checked (the collector may add them while we run)."""
        if not self._have.issuperset(names):
            marks = ",".join("?" * len(names))
            got = {r[0] for r in self.conn.execute(
                f"SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ({marks})", names)}
            self._have |= got
        return self._have.issuperset(names)

    @property
    def has_enrich(self) -> bool:  # Awesome lists and paper mentions
        return self._has("repo_lists", "repo_papers", "papers")

    @property
    def has_money(self) -> bool:  # funding links and business-model tags
        return self._has("repo_money")

    def data_version(self) -> int:
        """Changes whenever another connection (the collector) commits. It is only meaningful on one
        long-lived connection, so this uses its own, not the per-thread ones."""
        with self._ver_lock:
            if self._ver_conn is None:
                self._ver_conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True, timeout=10,
                                                 check_same_thread=False)
            return self._ver_conn.execute("PRAGMA data_version").fetchone()[0]

    def query(self, sql: str, params: Iterable = ()) -> list[sqlite3.Row]:
        params = tuple(params)
        deadline = getattr(self._local, "deadline", None)
        take_slot = self._gate is not None and not getattr(self._local, "holding", False)
        if take_slot:  # outside a budget() block: one slot per query
            wait = None if deadline is None else max(deadline - time.monotonic(), 0.0)
            if not self._gate.acquire(timeout=wait):
                raise QueryTimeout("server busy: no free query slot before the time budget ended")
        try:
            for attempt in range(BUSY_RETRIES):
                try:
                    return self._run(sql, params)
                except sqlite3.OperationalError as e:
                    if "no such table" in str(e) and re.search(ENRICH_TABLES, str(e)):
                        return []  # a filter on enrichment data this database lacks: nothing matches
                    busy = "locked" in str(e) or "busy" in str(e)
                    if not busy or attempt == BUSY_RETRIES - 1:
                        raise
                    time.sleep(0.2 * (attempt + 1))
            return []
        finally:
            if take_slot:
                self._gate.release()

    def one(self, sql: str, params: Iterable = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def scalar(self, sql: str, params: Iterable = ()):
        row = self.one(sql, params)
        return row[0] if row else None

    def meta(self, key: str) -> str | None:
        return self.scalar("SELECT value FROM meta WHERE key = ?", (key,))

    @property
    def as_of(self) -> str | None:
        return self.meta("last_sync")

    def latest_day(self) -> str | None:
        """The newest star-snapshot day. Growth is measured back from it, not from the wall clock,
        so a few days without a collector run don't turn every gain into "no data"."""
        return self.scalar("SELECT MAX(day) FROM repo_stats")

    def history_days(self) -> int:
        """How many days of star snapshots exist (a growth window needs at least that many)."""
        row = self.one("SELECT julianday(MAX(day)) - julianday(MIN(day)) FROM repo_stats")
        return int(row[0] or 0) if row else 0

    def close(self) -> None:
        with self._conns_lock:
            conns, self._conns = self._conns, []
        for c in conns:
            c.close()
        if self._ver_conn is not None:
            self._ver_conn.close()
            self._ver_conn = None


def open_db(path: Path) -> ReadDb:
    """The production reader: `OSSDEX_MAX_QUERIES` requests using SQLite at once per process
    (default 1: add worker processes instead) and each request limited to `OSSDEX_QUERY_TIMEOUT`
    seconds (default 5), queue time included."""
    cap = int(os.environ.get("OSSDEX_MAX_QUERIES") or 1)
    timeout = float(os.environ.get("OSSDEX_QUERY_TIMEOUT") or 5)
    return ReadDb(path, max_concurrent=cap, query_timeout=timeout)
