"""What keeps a public, anonymous server fast and bounded: per-thread connections, a query cap,
interruptible deadlines, and a response cache that follows the database."""

import re
import sqlite3
import threading
import time

import pytest
from fastapi.testclient import TestClient
from ossdex_core.store import connect, finish
from ossdex_server import search as S
from ossdex_server.api import create_app
from ossdex_server.cache import ApiCacheMiddleware, ResponseCache
from ossdex_server.db import QueryTimeout, ReadDb
from ossdex_server.tools import Toolbox

# an endless-looking query: a cross join over a recursive counter
SLOW = ("WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 50000000) "
        "SELECT COUNT(*) FROM c")


# ---- connections and the time budget ----
def test_each_thread_gets_its_own_connection(db_path):
    db = ReadDb(db_path)
    expected = db.scalar("SELECT COUNT(*) FROM repos")
    seen, counts = {}, {}

    def work(i):
        seen[i] = id(db.conn)
        counts[i] = db.scalar("SELECT COUNT(*) FROM repos")

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert len(seen) == 4 and len(set(seen.values())) == 4 and id(db.conn) not in seen.values()
    assert set(counts.values()) == {expected} and expected > 0
    db.close()


def test_a_budget_interrupts_a_running_query(db_path):
    db = ReadDb(db_path, query_timeout=0.3)
    started = time.perf_counter()
    with pytest.raises(QueryTimeout), db.budget():
        db.query(SLOW)
    assert time.perf_counter() - started < 3, "the query kept running past its deadline"
    # the connection is healthy afterwards, and a later budget starts fresh
    with db.budget(5):
        assert db.scalar("SELECT 1") == 1
    db.close()


def test_the_budget_is_shared_by_all_queries_of_a_request(db_path):
    db = ReadDb(db_path)
    with pytest.raises(QueryTimeout), db.budget(0.05):
        db.query("SELECT 1")
        time.sleep(0.1)
        db.query("SELECT 2")  # the request's time is already gone
    db.close()


def test_waiting_for_a_query_slot_gives_up_at_the_deadline(db_path):
    db = ReadDb(db_path, max_concurrent=1)
    release = threading.Event()
    holder_in = threading.Event()

    def hold():
        with db._gate:  # occupy the only slot
            holder_in.set()
            release.wait(5)

    t = threading.Thread(target=hold)
    t.start()
    holder_in.wait(2)
    started = time.perf_counter()
    with pytest.raises(QueryTimeout, match="busy"), db.budget(0.2):
        db.query("SELECT 1")
    assert 0.15 < time.perf_counter() - started < 2
    release.set()
    t.join()
    assert db.scalar("SELECT 1") == 1  # the slot came back
    db.close()


def test_the_query_cap_is_released_after_errors(db_path):
    db = ReadDb(db_path, max_concurrent=1)
    for _ in range(3):
        with pytest.raises(sqlite3.OperationalError):
            db.query("SELECT * FROM no_such_table")
    assert db.scalar("SELECT 1") == 1
    db.close()


def test_an_api_request_over_budget_is_a_503_with_retry_after(settings, monkeypatch):
    db = ReadDb(settings.db_path, query_timeout=0.2)
    monkeypatch.setattr("ossdex_server.repo_query.facets",
                        lambda *a, **k: db.query(SLOW), raising=True)
    client = TestClient(create_app(settings, toolbox=Toolbox(db, settings)))
    res = client.get("/api/facets")
    assert res.status_code == 503 and res.headers["retry-after"] == "5"
    db.close()


def test_a_tool_call_over_budget_returns_an_error_result(settings):
    db = ReadDb(settings.db_path, query_timeout=0.2)
    tb = Toolbox(db, settings)
    tb.tools["facets"].handler = lambda _: {"rows": db.query(SLOW)}
    res = tb.call("facets", {})
    assert "error" in res and "budget" in res["error"]
    db.close()


# ---- the cache ----
def test_cache_hits_and_lru_bounds():
    class FakeDb:
        def data_version(self):
            return 1

    c = ResponseCache(FakeDb(), max_entries=3, max_bytes=10_000)
    for i in range(5):
        c.put(("k", i), b"x" * 10)
    assert len(c) == 3 and c.get(("k", 0)) is None and c.get(("k", 4)) == b"x" * 10
    c.put("huge", b"x" * 5_000)  # more than 1/8 of the budget: never stored
    assert c.get("huge") is None


def test_cache_is_dropped_when_the_database_changes(db_path):
    clock = [0.0]
    db = ReadDb(db_path)
    cache = ResponseCache(db, recheck=1.0, clock=lambda: clock[0])
    cache.put(("a",), b"old")
    assert cache.get(("a",)) == b"old"
    w = connect(db_path)
    w.execute("UPDATE meta SET value = 'changed' WHERE key = 'last_sync'")
    w.commit()
    assert cache.get(("a",)) == b"old"  # not rechecked yet
    clock[0] = 2.0
    assert cache.get(("a",)) is None  # the collector committed: everything is stale
    w.close()
    db.close()


def test_tool_results_are_cached_and_errors_are_not(settings, db):
    tb = Toolbox(db, settings)
    tb.cache = ResponseCache(db)
    calls = []
    real = tb.tools["count_repos"].handler
    tb.tools["count_repos"].handler = lambda a: (calls.append(1), real(a))[1]
    args = {"group_by": "language"}
    first = tb.call("count_repos", args)
    second = tb.call("count_repos", dict(reversed(list(args.items()))))
    assert first == second and len(calls) == 1
    second["tampered"] = True  # a caller changing its copy cannot poison the cache
    assert "tampered" not in tb.call("count_repos", args)
    assert "error" in tb.call("get_repo", {"full_name": "nobody/nothing"})
    tb.call("get_repo", {"full_name": "nobody/nothing"})
    assert len(tb.cache) == 1


def test_api_replies_are_cached_with_cache_control(settings, db):
    client = TestClient(create_app(settings, toolbox=Toolbox(db, settings)))
    a = client.get("/api/repos", params={"page_size": 2, "sort": "stars"})
    b = client.get("/api/repos", params=[("sort", "stars"), ("page_size", "2")])  # same, reordered
    assert a.headers["x-cache"] == "miss" and b.headers["x-cache"] == "hit"
    assert a.json() == b.json() and b.headers["content-length"] == str(len(b.content))
    assert a.headers["cache-control"] == "public, max-age=300"
    assert client.get("/api/status").headers["cache-control"] == "public, max-age=60"
    assert client.get("/api/repos/nope/nope").status_code == 404
    assert "x-cache" not in client.get("/api/repos/nope/nope").headers  # failures are not cached


def test_only_api_gets_are_cached(settings, db):
    client = TestClient(create_app(settings, toolbox=Toolbox(db, settings)))
    assert "x-cache" not in client.get("/").headers
    assert "x-cache" not in client.post("/api/repos").headers
    assert ApiCacheMiddleware  # imported for the wiring above


# ---- the cheaper lexical pass ----
def _reference_lexical(db, terms):
    """The scoring as it was before the SQL prefilter: every visible repo, in Python."""
    import json

    from ossdex_server.db import VISIBLE

    patterns = [(t, re.compile(rf"\b{re.escape(t)}", re.IGNORECASE)) for t in terms]
    out = []
    for r in db.query(f"SELECT ghr_id, full_name, description, topics, language FROM repos WHERE {VISIBLE}"):
        name, desc = r["full_name"].lower(), (r["description"] or "").lower()
        raw, lang = (r["topics"] or "").lower(), (r["language"] or "").lower()
        topics, score, reason = None, 0.0, ""
        for t, pat in patterns:
            if t in raw:
                if topics is None:
                    topics = {x.lower() for x in json.loads(r["topics"] or "[]") if isinstance(x, str)}
                if t in topics or any(t in x for x in topics if len(t) > 3):
                    score, reason = score + 3, reason or "topic"
            if pat.search(name):
                score, reason = score + 2, reason or "name"
            if t == lang:
                score += 1.5
            if pat.search(desc):
                score, reason = score + 1, reason or "description"
        if score:
            out.append((r["ghr_id"], score, reason))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out[:S.CANDIDATES]


@pytest.mark.parametrize("query", ["langchain agents", "go", "rust database", "unenriched", "ai",
                                   "golang api framework", "café ünï", "zzzz-no-such-thing"])
def test_prefiltered_lexical_matches_the_full_scan(db, query):
    terms = S.query_terms(query)[:S.MAX_LEXICAL_TERMS]
    assert S._lexical(db, terms, None) == _reference_lexical(db, terms)


def test_long_queries_use_at_most_eight_terms(db):
    many = [f"term{i}" for i in range(30)] + ["langchain"]
    assert S._lexical(db, many, None) == []  # "langchain" is the 31st term: beyond the cap
    assert S._lexical(db, ["langchain", *many], None)


# ---- housekeeping ----
def test_finish_truncates_the_wal(tmp_path):
    path = tmp_path / "w.db"
    conn = connect(path)
    conn.executemany("INSERT INTO meta(key, value) VALUES (?, ?)", [(f"k{i}", "x" * 1000) for i in range(500)])
    conn.commit()
    wal = tmp_path / "w.db-wal"
    assert wal.exists() and wal.stat().st_size > 0
    assert finish(conn) is True
    assert wal.stat().st_size == 0
    conn.close()


def test_an_answer_computed_before_a_commit_is_not_stored_after_it(db_path):
    clock = [0.0]
    db = ReadDb(db_path)
    cache = ResponseCache(db, recheck=1.0, clock=lambda: clock[0])
    started_under = cache.snapshot()  # a request begins
    w = connect(db_path)
    w.execute("UPDATE meta SET value = 'changed' WHERE key = 'last_sync'")
    w.commit()
    clock[0] = 2.0
    assert cache.get(("late",)) is None  # another request notices the commit and clears the cache
    cache.put(("late",), b"computed from the old data", started_under)
    assert cache.get(("late",)) is None  # ...so the slow request's stale answer is dropped
    cache.put(("fresh",), b"ok", cache.snapshot())
    assert cache.get(("fresh",)) == b"ok"
    w.close()
    db.close()


def test_a_request_holds_one_slot_for_all_its_queries(db_path):
    """Two requests must not interleave their queries: the second waits for the first to finish."""
    db = ReadDb(db_path, max_concurrent=1, query_timeout=5)
    order = []
    first_in = threading.Event()

    def first():
        with db.budget():
            db.query("SELECT 1")
            first_in.set()
            time.sleep(0.3)  # still inside its request, between two queries
            db.query("SELECT 2")
            order.append("first done")

    def second():
        first_in.wait(2)
        with db.budget():
            order.append("second runs")
            db.query("SELECT 3")

    ts = [threading.Thread(target=first), threading.Thread(target=second)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert order == ["first done", "second runs"]
    db.close()


def test_nested_budgets_do_not_deadlock_on_the_slot(db_path):
    db = ReadDb(db_path, max_concurrent=1, query_timeout=2)
    with db.budget(), db.budget(1):
        assert db.scalar("SELECT 1") == 1
    assert db.scalar("SELECT 2") == 2  # the slot was released exactly once
    db.close()


def test_a_request_queued_past_its_deadline_is_refused_not_run(db_path):
    db = ReadDb(db_path, max_concurrent=1)
    release = threading.Event()
    held = threading.Event()

    def hold():
        with db.budget(10):
            held.set()
            release.wait(5)

    t = threading.Thread(target=hold)
    t.start()
    held.wait(2)
    started = time.perf_counter()
    with pytest.raises(QueryTimeout, match="busy"), db.budget(0.2):
        pytest.fail("the body must not run without a slot")
    assert time.perf_counter() - started < 1.5
    release.set()
    t.join()
    with db.budget(1):
        assert db.scalar("SELECT 1") == 1
    db.close()
