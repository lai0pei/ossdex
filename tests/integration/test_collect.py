from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import respx
from ossdex_collector import collect
from ossdex_collector.collect import (
    base_query,
    discover,
    fetch_readmes,
    plan_slices,
    refresh,
    run_started,
)
from ossdex_collector.github import GitHub, RateLimited
from ossdex_core.config import Settings
from ossdex_core.store import apply_threshold, connect, get_meta, prune, reject_reason, upsert_repo
from ossdex_server import repo_query as rq
from ossdex_server.db import ReadDb

from testsupport.fake_github import BASE, FakeGitHub, make_repo


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def make_settings(tmp_path, **kw) -> Settings:
    return Settings(
        db_path=tmp_path / "ossdex.db", 
        min_stars=1000, exclude_topics=("awesome",), **kw)


def start(repos, tmp_path):
    fake = FakeGitHub(repos)
    clock = Clock()
    mock = respx.mock(base_url=BASE, assert_all_called=False)
    mock.route().mock(side_effect=fake.handler)
    mock.start()
    gh = GitHub("t", base_url=BASE, sleep=clock.sleep, now=clock.now, min_interval=0)
    conn = connect(tmp_path / "ossdex.db")
    return SimpleNamespace(fake=fake, gh=gh, conn=conn, mock=mock,
                           settings=make_settings(tmp_path), path=tmp_path / "ossdex.db")


@pytest.fixture
def world(tmp_path):
    repos = [make_repo(i, stars=1000 + i * 500) for i in range(1, 7)]  # 1500 .. 4000
    repos += [make_repo(20, stars=2000, license=None),            # unlicensed: read, then dropped
              make_repo(21, stars=999),                           # below the threshold
              make_repo(22, stars=3000, topics=("awesome",)),     # excluded topic
              make_repo(23, stars=3500, fork=True)]               # fork
    w = start(repos, tmp_path)
    yield w
    w.mock.stop()
    w.conn.close()


def rows(conn, status="ok"):
    return {r["ghr_id"]: r for r in conn.execute("SELECT * FROM repos WHERE enrich_status = ?",
                                                 (status,))}


# ---- slicing ----


def dense_world():
    repos, i = [], 1
    for k in range(1500):  # 1500 repos with exactly 1234 stars, each created on its own day
        repos.append(make_repo(i, stars=1234, created=(date(2015, 1, 1) + timedelta(days=k)).isoformat()))
        i += 1
    for k in range(1300):  # spread over 1000..2999 stars
        repos.append(make_repo(i, stars=1000 + (k * 7) % 2000,
                               created=(date(2016, 1, 1) + timedelta(days=k % 900)).isoformat()))
        i += 1
    for k in range(40):  # a few giants
        repos.append(make_repo(i, stars=5000 + k * 1500))
        i += 1
    return repos


def test_plan_slices_covers_every_repo_exactly_once(tmp_path):
    w = start(dense_world(), tmp_path)
    try:
        plan = plan_slices(w.gh, base_query(()), 1000, cap=1000, today=date(2026, 10, 27))
        assert len(plan) > 3 and all(n <= 1000 and not trunc for _, n, trunc in plan)
        seen = []
        for q, n, _ in plan:
            hits = w.fake.search(q)
            assert len(hits) == n
            seen += [r["id"] for r in hits]
        everything = [r["id"] for r in w.fake.repos if r["stars"] >= 1000]
        assert sorted(seen) == sorted(everything)  # nothing missed, nothing twice
        assert any("created:" in q for q, *_ in plan)  # the 1234-star pile needed date splits
    finally:
        w.mock.stop()


def test_a_dense_single_day_terminates_and_is_marked_truncated(tmp_path):
    repos = [make_repo(i, stars=777, created="2020-05-05") for i in range(1, 1201)]
    w = start(repos, tmp_path)
    try:
        plan = plan_slices(w.gh, base_query(()), 700, cap=1000, today=date(2026, 10, 27))
        assert [(n, t) for _, n, t in plan] == [(1200, True)]
        assert w.fake.counts < 80  # bisection, not a crawl
        rep = discover(w.gh, w.conn, w.settings, min_stars=700)
        assert rep.truncated == 1 and rep.seen == 1000 and rep.finished  # reads what search allows
    finally:
        w.mock.stop()


def test_dry_run_counts_without_writing(world):
    rep = discover(world.gh, None, world.settings, dry_run=True)
    assert rep.estimate == 7 and rep.slices >= 1  # upper bound: includes the unlicensed repo
    assert world.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 0


# ---- discover ----


def test_discover_keeps_only_licensed_open_source_repos(world):
    rep = discover(world.gh, world.conn, world.settings)
    assert rep.finished and rep.new == 6 and rep.skipped == {"unlicensed": 1}
    ok = rows(world.conn)
    assert set(ok) == {1, 2, 3, 4, 5, 6}
    r = ok[2]
    assert r["url"] == "https://github.com/org2/repo2" and r["node_id"] == "R_2"
    assert r["license"] == "MIT" and r["stars"] == 2000 and r["forks"] == 200
    assert r["topics"] == '["tool"]' and r["open_issues"] == 3 and r["enrich_status"] == "ok"
    assert r["readme"] is None  # READMEs are fetched by a later step
    assert get_meta(world.conn, "min_stars") == "1000" and get_meta(world.conn, "last_sync")
    assert world.conn.execute("SELECT COUNT(*) FROM repo_stats").fetchone()[0] == 6


def test_discover_twice_is_idempotent(world):
    discover(world.gh, world.conn, world.settings)
    rep = discover(world.gh, world.conn, world.settings)
    assert rep.new == 0 and rep.updated == 6
    assert world.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 6
    assert world.conn.execute("SELECT COUNT(*) FROM repo_stats").fetchone()[0] == 6  # one per day


def test_snapshots_on_different_days_give_star_growth(world, monkeypatch):
    monkeypatch.setattr(collect, "today_iso", lambda: "2026-10-20")
    discover(world.gh, world.conn, world.settings)
    world.fake.by_id[3]["stars"] += 250
    monkeypatch.setattr(collect, "today_iso", lambda: "2026-10-27")
    discover(world.gh, world.conn, world.settings)
    db = ReadDb(world.path)
    try:
        assert db.latest_day() == "2026-10-27" and db.history_days() == 7
        by = {i["ghr_id"]: i for i in rq.list_repos(db, rq.RepoFilters())["items"]}
        assert by[3]["gain_7d"] == 250 and by[1]["gain_7d"] == 0
        assert rq.list_repos(db, rq.RepoFilters(min_gain=100))["total"] == 1
    finally:
        db.close()


def test_discover_resumes_after_a_rate_limit_without_rereading(tmp_path):
    repos = [make_repo(i, stars=1000 + i) for i in range(1, 251)]  # 250 repos
    w = start(repos, tmp_path)
    try:
        w.fake.fail_after_pages = 2  # plan done; the limit hits while reading
        with pytest.raises(RateLimited):
            discover(w.gh, w.conn, w.settings, cap=100)
        stored = w.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0]
        assert 0 < stored < 250 and w.fake.search_pages == 2
        w.fake.fail_after_pages = None
        rep = discover(w.gh, w.conn, w.settings, cap=100)
        assert rep.resumed and rep.finished
        assert w.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 250
        slices = w.conn.execute("SELECT COUNT(*) FROM slices").fetchone()[0]
        assert w.fake.search_pages == slices  # each one-page slice was read exactly once
    finally:
        w.mock.stop()


def test_discover_resumes_inside_a_slice_from_its_cursor(tmp_path):
    repos = [make_repo(i, stars=5000 + i) for i in range(1, 151)]  # one slice, two pages
    w = start(repos, tmp_path)
    try:
        w.fake.fail_after_pages = 1
        with pytest.raises(RateLimited):
            discover(w.gh, w.conn, w.settings)
        assert w.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 100
        assert w.conn.execute("SELECT cursor FROM slices").fetchone()[0] == "100"
        w.fake.fail_after_pages = None
        before = w.fake.search_pages
        rep = discover(w.gh, w.conn, w.settings)
        assert rep.resumed and w.fake.search_pages - before == 1  # only the second page
        assert w.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 150
    finally:
        w.mock.stop()


def test_changing_the_threshold_starts_a_fresh_run(world):
    discover(world.gh, world.conn, world.settings, min_stars=3000)
    assert set(rows(world.conn)) == {4, 5, 6}  # 3000, 3500 and 4000 stars
    rep = discover(world.gh, world.conn, world.settings, min_stars=1000)
    assert not rep.resumed and rep.new == 3  # only the repos below 3000 were missing


# ---- threshold, prune ----


def test_raising_the_threshold_hides_and_lowering_restores(world):
    discover(world.gh, world.conn, world.settings, min_stars=1000)
    discover(world.gh, world.conn, world.settings, min_stars=3000)
    assert set(rows(world.conn)) == {4, 5, 6}
    assert set(rows(world.conn, "below")) == {1, 2, 3}  # hidden, not deleted
    db = ReadDb(world.path)
    assert rq.list_repos(db, rq.RepoFilters())["total"] == 3
    db.close()
    apply_threshold(world.conn, 1000)  # lowering it brings them back with the stars we last saw
    assert set(rows(world.conn)) == {1, 2, 3, 4, 5, 6} and not rows(world.conn, "below")
    assert get_meta(world.conn, "min_stars") == "1000"


def test_prune_deletes_hidden_repos_with_their_chunks_and_snapshots(world):
    from ossdex_core.chunks import index_chunks

    discover(world.gh, world.conn, world.settings, min_stars=1000)
    index_chunks(world.conn)
    apply_threshold(world.conn, 3000)
    plan = prune(world.conn, dry_run=True)
    assert plan["repos"] == 3 and plan["chunks"] == 3 and plan["snapshots"] == 3
    assert world.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 6  # dry run
    prune(world.conn)
    left = {r[0] for r in world.conn.execute("SELECT ghr_id FROM repos")}
    assert left == {4, 5, 6}
    assert world.conn.execute("SELECT COUNT(*) FROM repo_stats WHERE ghr_id IN (1,2,3)").fetchone()[0] == 0


# ---- refresh ----


def test_refresh_marks_gone_filtered_and_below(world):
    discover(world.gh, world.conn, world.settings)
    world.conn.execute("UPDATE repos SET last_seen = '2020-01-01T00:00:00Z'")  # long ago
    world.conn.commit()
    del world.fake.by_id[1]  # repo 1 was deleted on GitHub
    world.fake.repos[:] = [r for r in world.fake.repos if r["id"] != 1]
    world.fake.by_id[2]["fork"] = True  # repo 2 became a fork: search no longer returns it
    world.fake.by_id[5]["license"] = None  # repo 5 lost its license: search still returns it
    world.fake.by_id[3]["stars"] = 400  # repo 3 fell under the threshold, still open source
    world.fake.by_id[4]["name"] = "renamed/repo4"  # repo 4 was renamed (and is still found)
    rep = discover(world.gh, world.conn, world.settings)
    rep2 = refresh(world.gh, world.conn, world.settings, cutoff=run_started(world.conn))
    assert rep.skipped == {"unlicensed": 2}  # repo 20 (never stored) and repo 5, which it hides
    assert (rep2.checked, rep2.gone, rep2.filtered) == (3, 1, 1)  # repos 1, 2 and 3 were not returned
    assert set(rows(world.conn, "gone")) == {1} and set(rows(world.conn, "filtered")) == {2, 5}
    assert set(rows(world.conn, "below")) == {3}
    assert rows(world.conn)[4]["full_name"] == "renamed/repo4"
    assert set(rows(world.conn)) == {4, 6}


def test_refresh_ignores_repos_seen_in_this_run(world):
    discover(world.gh, world.conn, world.settings)
    rep = refresh(world.gh, world.conn, world.settings, cutoff=run_started(world.conn))
    assert rep.checked == 0


# ---- one bad repo must not stall the run ----


def test_a_poisoned_readme_batch_is_split_and_the_run_moves_on(world):
    discover(world.gh, world.conn, world.settings)
    world.fake.poison = {4}  # any README query touching repo 4 fails
    rep = fetch_readmes(world.gh, world.conn)
    assert rep.due == 6 and rep.stored == 5 and rep.failed == 1
    got = {r["ghr_id"]: r for r in world.conn.execute("SELECT * FROM repos")}
    assert got[4]["readme"] is None and got[4]["readme_at"]  # stamped: not retried every run
    assert all(got[i]["readme"] for i in (1, 2, 3, 5, 6))
    assert fetch_readmes(world.gh, world.conn).due == 0


def test_a_poisoned_refresh_batch_checks_the_others(world):
    discover(world.gh, world.conn, world.settings)
    world.conn.execute("UPDATE repos SET last_seen = '2020-01-01T00:00:00Z'")
    world.conn.commit()
    del world.fake.by_id[2]
    world.fake.repos[:] = [r for r in world.fake.repos if r["id"] != 2]
    world.fake.poison = {5}
    rep = refresh(world.gh, world.conn, world.settings, cutoff="2030-01-01T00:00:00Z")
    assert (rep.checked, rep.errors, rep.gone, rep.updated) == (6, 1, 1, 4)
    assert 5 in rows(world.conn) and 2 not in rows(world.conn)  # repo 5 stays visible, retried later


def test_a_slice_that_keeps_failing_does_not_stop_the_others(tmp_path):
    repos = [make_repo(i, stars=1000 + i) for i in range(1, 251)]
    w = start(repos, tmp_path)
    try:
        w.fake.poison = {5}
        rep = discover(w.gh, w.conn, w.settings, cap=100)
        assert rep.failed_slices == 1 and not rep.finished
        stored = w.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0]
        assert 100 < stored < 250  # the other slices were read
        w.fake.poison = set()  # GitHub recovered
        rep = discover(w.gh, w.conn, w.settings, cap=100)
        assert rep.resumed and rep.finished and rep.failed_slices == 0
        assert w.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 250
    finally:
        w.mock.stop()


def test_html_replies_fail_only_their_slice_and_the_next_run_resumes_it(tmp_path):
    repos = [make_repo(i, stars=1000 + i) for i in range(1, 251)]
    w = start(repos, tmp_path)
    try:
        w.fake.html_pages = 12  # 4 attempts at each of the page sizes 100, 50 and 25
        rep = discover(w.gh, w.conn, w.settings, cap=100)
        assert rep.failed_slices == 1 and not rep.finished
        assert 100 < w.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] < 250
        rep = discover(w.gh, w.conn, w.settings, cap=100)
        assert rep.resumed and rep.finished and rep.failed_slices == 0
        assert w.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 250
    finally:
        w.mock.stop()


# ---- upsert details ----


def test_a_reused_name_frees_up_the_old_holder(world):
    a, b = make_repo(100, stars=2000), make_repo(101, stars=2100)
    from testsupport.fake_github import node

    upsert_repo(world.conn, node(a), now="2026-10-27T00:00:00Z", day="2026-10-27")
    b["name"] = a["name"]  # repo 101 now has the name repo 100 used to have
    upsert_repo(world.conn, node(b), now="2026-10-27T00:00:00Z", day="2026-10-27")
    names = {r["ghr_id"]: r["full_name"] for r in world.conn.execute("SELECT * FROM repos")}
    assert names == {100: f"{a['name']}~100", 101: a["name"]}


def test_reject_reasons():
    ok = {"licenseInfo": {"spdxId": "MIT"}, "repositoryTopics": {"nodes": []}}
    assert reject_reason(ok) is None
    assert reject_reason({**ok, "isFork": True}) == "fork"
    assert reject_reason({**ok, "isArchived": True}) == "archived"
    assert reject_reason({**ok, "isMirror": True}) == "mirror"
    assert reject_reason({**ok, "isTemplate": True}) == "template"
    assert reject_reason({**ok, "licenseInfo": None}) == "unlicensed"
    topical = {**ok, "repositoryTopics": {"nodes": [{"topic": {"name": "Awesome"}}]}}
    assert reject_reason(topical, ("awesome",)) == "excluded-topic" and reject_reason(topical) is None


# ---- READMEs ----


def test_readmes_are_fetched_once_and_not_repeated(world):
    discover(world.gh, world.conn, world.settings)
    world.fake.by_id[1]["readme"] = {}  # no README at all
    world.fake.by_id[2]["readme"] = {"README.md": "x" * 300_000}  # over the storage cap
    rep = fetch_readmes(world.gh, world.conn)
    assert rep.due == 6 and rep.stored == 5 and rep.none == 1
    got = {r["ghr_id"]: r for r in world.conn.execute("SELECT * FROM repos")}
    assert got[3]["readme"].startswith("# repo3") and got[3]["readme_sha"]
    assert len(got[2]["readme"]) == 200_000 and got[1]["readme"] is None
    assert all(r["readme_at"] for r in got.values() if r["enrich_status"] == "ok")
    assert fetch_readmes(world.gh, world.conn).due == 0  # fetched recently: nothing due
    again = fetch_readmes(world.gh, world.conn, days=-1)  # forced: everything is due
    assert again.unchanged == 5 and again.stored == 0 and again.none == 1
    world.fake.by_id[3]["readme"] = {"README.md": "# changed"}
    assert fetch_readmes(world.gh, world.conn, days=-1).stored == 1


def test_readmes_go_biggest_repo_first_and_honor_the_limit(world):
    discover(world.gh, world.conn, world.settings)
    fetch_readmes(world.gh, world.conn, limit=2)
    done = {r[0] for r in world.conn.execute("SELECT ghr_id FROM repos WHERE readme IS NOT NULL")}
    assert done == {6, 5}  # 4000 and 3500 stars


# ---- CLI composition ----


def test_cli_dry_run_and_update(world, monkeypatch):
    from ossdex_collector import cli
    from typer.testing import CliRunner

    monkeypatch.setattr(cli, "_github", lambda settings, budget: world.gh)
    monkeypatch.setenv("OSSDEX_DB", str(world.path))
    monkeypatch.setenv("OSSDEX_MIN_STARS", "1000")
    monkeypatch.setenv("OSSDEX_EXCLUDE_TOPICS", "awesome")
    runner = CliRunner()
    out = runner.invoke(cli.app, ["discover", "--dry-run"])
    assert out.exit_code == 0 and "7 repos match stars >= 1,000" in out.output
    assert "upper bound" in out.output and world.conn.execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 0
    out = runner.invoke(cli.app, ["update"])
    assert out.exit_code == 0, out.output
    assert "6 new" in out.output and "unlicensed" in out.output and "readmes: 6 stored" in out.output
    assert "refresh: 0 checked" in out.output
    assert "keyword search: " in out.output  # keyword-search chunks are rebuilt
    assert "vector" not in out.output
    assert world.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] > 0
    again = runner.invoke(cli.app, ["update"])
    assert "0 new, 6 updated" in again.output and "readmes: 0 stored" in again.output
    monkeypatch.setenv("OSSDEX_VECTORS", "off")
    off = runner.invoke(cli.app, ["update"])
    assert off.exit_code == 0 and "ossdex index" not in off.output  # nothing else to run


def test_cli_stops_cleanly_on_a_rate_limit_and_resumes(world, monkeypatch):
    from ossdex_collector import cli
    from typer.testing import CliRunner

    monkeypatch.setattr(cli, "_github", lambda settings, budget: world.gh)
    monkeypatch.setenv("OSSDEX_DB", str(world.path))
    monkeypatch.setenv("OSSDEX_MIN_STARS", "1000")
    monkeypatch.setenv("OSSDEX_EXCLUDE_TOPICS", "awesome")
    world.fake.fail_after_pages = 0
    res = CliRunner().invoke(cli.app, ["discover"])
    assert res.exit_code == 1 and "Run the command again later to resume" in res.output
    assert "Traceback" not in res.output
    world.fake.fail_after_pages = None
    res = CliRunner().invoke(cli.app, ["discover"])
    assert res.exit_code == 0 and "(resumed)" in res.output


def test_cli_update_skips_refresh_while_discover_is_incomplete(tmp_path, monkeypatch):
    from ossdex_collector import cli
    from typer.testing import CliRunner

    repos = [make_repo(i, stars=1000 + i) for i in range(1, 251)]
    w = start(repos, tmp_path)
    try:
        monkeypatch.setattr(cli, "_github", lambda settings, budget: w.gh)
        monkeypatch.setenv("OSSDEX_DB", str(w.path))
        monkeypatch.setenv("OSSDEX_MIN_STARS", "1000")
        monkeypatch.setenv("OSSDEX_EXCLUDE_TOPICS", "awesome")
        w.fake.poison = {5}
        res = CliRunner().invoke(cli.app, ["update"])
        assert res.exit_code == 0, res.output
        assert "kept failing on GitHub's side" in res.output
        assert "skipping refresh until it has finished" in res.output
        assert "refresh: " not in res.output.replace("skipping refresh", "")
    finally:
        w.mock.stop()


# ---- optional license requirement ----


def test_unlicensed_repos_can_be_kept_and_hidden_again(world):
    from dataclasses import replace

    keep = replace(world.settings, require_license=False)
    rep = discover(world.gh, world.conn, keep)
    assert "unlicensed" not in rep.skipped
    assert 20 in rows(world.conn) and rows(world.conn)[20]["license"] is None
    assert get_meta(world.conn, "require_license") == "0"
    refresh(world.gh, world.conn, keep, cutoff="2030-01-01T00:00:00Z")
    assert 20 in rows(world.conn)  # refresh applies the same rule
    discover(world.gh, world.conn, world.settings)  # back to licensed only
    assert 20 in rows(world.conn, "filtered")
    assert get_meta(world.conn, "require_license") == "1"


def test_reject_reason_license_rule():
    node = {"licenseInfo": None}
    assert reject_reason(node) == "unlicensed"
    assert reject_reason(node, require_license=False) is None
