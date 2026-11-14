import plistlib

import pytest
from ossdex_collector import schedule
from ossdex_collector.cli import app
from ossdex_core.chunks import build_card, clean_readme, index_chunks, readme_chunks
from ossdex_core.store import connect
from typer.testing import CliRunner

from testsupport.helpers import build_fixture_db


def test_card_has_no_star_counts_so_daily_growth_never_re_embeds(tmp_path):
    conn = connect(build_fixture_db(tmp_path / "o.db"))
    row = conn.execute("SELECT * FROM repos WHERE ghr_id = 2").fetchone()
    card = build_card(row)
    assert card.startswith("acme/langchain-agent — AI agents built on langchain")
    assert "Language: Python" in card and "License: Apache-2.0" in card and "★" not in card
    before = conn.execute("SELECT text_hash FROM chunks WHERE ghr_id = 2 AND kind = 'card'").fetchone()[0]
    conn.execute("UPDATE repos SET stars = 99999, forks = 5 WHERE ghr_id = 2")
    assert index_chunks(conn)["written"] == 0
    assert conn.execute("SELECT text_hash FROM chunks WHERE ghr_id = 2 AND kind = 'card'").fetchone()[0] == before


def test_index_chunks_is_incremental_and_follows_visibility(tmp_path):
    conn = connect(build_fixture_db(tmp_path / "o.db"))
    assert conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 11
    assert index_chunks(conn) == {"written": 0, "removed": 0, "chunks": 11}  # nothing changed
    conn.execute("UPDATE repos SET readme = '# changed\nnew words' WHERE ghr_id = 3")
    assert index_chunks(conn)["written"] == 1
    conn.execute("UPDATE repos SET enrich_status = 'below' WHERE ghr_id = 1")  # hidden: no chunks
    out = index_chunks(conn)
    assert out["removed"] >= 2 and conn.execute("SELECT COUNT(*) FROM chunks WHERE ghr_id = 1").fetchone()[0] == 0
    conn.execute("UPDATE repos SET readme = NULL WHERE ghr_id = 9")  # README went away
    index_chunks(conn)
    kinds = [r[0] for r in conn.execute("SELECT kind FROM chunks WHERE ghr_id = 9")]
    assert kinds == ["card"]
    hits = conn.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'goroutines'").fetchall()
    assert hits == []  # full-text index follows the deletes (repo 1 is hidden now)


def test_readme_cleaning_and_splitting():
    md = "# Title\n[![ci](a.svg)](b)\n<!-- hidden -->\n<img src='x'>text\n\n## Install\n```sh\npip install x\n```\n"
    clean = clean_readme(md)
    assert "ci" not in clean and "hidden" not in clean and "<img" not in clean and "pip install x" in clean
    chunks = readme_chunks("o/r", md)
    assert [h for h, _ in chunks] == ["Title", "Install"]
    assert chunks[1][1].startswith("o/r › Install")
    long = "# Big\n" + "\n\n".join(f"para {i} " + "x" * 800 for i in range(40))
    assert len(readme_chunks("o/r", long)) == 12  # capped


# ---- schedule ----


def test_plist_runs_update_daily(tmp_path):
    data = schedule.build_plist(uv="/usr/local/bin/uv", project=tmp_path, hour=3, minute=15,
                                log=tmp_path / "u.log", path_env="/usr/bin")
    p = plistlib.loads(data)
    assert p["Label"] == "dev.ossdex.update"
    assert p["ProgramArguments"] == ["/usr/local/bin/uv", "--directory", str(tmp_path), "run", "--package", "ossdex-collector",
                                      "ossdex-collector", "update"]
    assert p["StartCalendarInterval"] == {"Hour": 3, "Minute": 15} and p["RunAtLoad"] is False


def test_install_and_remove_use_the_given_path_and_runner(tmp_path):
    calls = []
    target = tmp_path / "LaunchAgents" / "dev.ossdex.update.plist"
    path = schedule.install(b"data", path=target, runner=lambda cmd: calls.append(cmd) or 0)
    assert path == target and target.read_bytes() == b"data"
    assert calls[0][:2] == ["launchctl", "bootout"] and calls[1][:2] == ["launchctl", "bootstrap"]
    assert schedule.remove(path=target, runner=lambda cmd: calls.append(cmd) or 0) is True
    assert not target.exists() and schedule.remove(path=target, runner=lambda cmd: 0) is False


def test_install_without_load_never_calls_launchctl(tmp_path):
    calls = []
    schedule.install(b"x", path=tmp_path / "p.plist", load=False, runner=lambda cmd: calls.append(cmd) or 0)
    assert calls == []


def test_a_failing_launchctl_is_reported(tmp_path):
    import pytest

    def runner(cmd):
        return 1 if cmd[1] == "bootstrap" else 0

    with pytest.raises(RuntimeError, match="launchctl could not load"):
        schedule.install(b"x", path=tmp_path / "p.plist", runner=runner)


def test_schedule_install_off_macos_prints_a_cron_line(monkeypatch, tmp_path):
    from ossdex_collector import cli

    monkeypatch.setattr(cli.sys, "platform", "linux")
    monkeypatch.setattr(schedule, "install", lambda *a, **k: pytest.fail("must not install"))
    res = CliRunner().invoke(cli.app, ["schedule", "install", "--hour", "3", "--minute", "15"])
    assert res.exit_code == 0, res.output
    assert "crontab -e" in res.output and "15 3 * * *" in res.output
    assert "run --package ossdex-collector ossdex-collector update" in res.output and "update.log" in res.output


# ---- CLI ----


def test_cli_status_and_prune(tmp_path, monkeypatch):
    path = build_fixture_db(tmp_path / "ossdex.db")
    monkeypatch.setenv("OSSDEX_DB", str(path))
    monkeypatch.setenv("GITHUB_TOKEN", "")
    runner = CliRunner()
    out = runner.invoke(app, ["status"]).output
    assert "visible repos: 6" in out and "4 hidden" not in out
    assert "1 below threshold, 2 filtered, 1 gone" in out and "30 days of star history" in out
    assert "would delete 4 repos" in runner.invoke(app, ["prune"], input="n\n").output
    assert connect(path).execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 10  # declined
    assert runner.invoke(app, ["prune", "--yes"]).exit_code == 0
    assert connect(path).execute("SELECT COUNT(*) FROM repos").fetchone()[0] == 6


def test_cli_without_a_token_explains_what_to_do(tmp_path, monkeypatch):
    monkeypatch.setenv("OSSDEX_DB", str(tmp_path / "x.db"))
    monkeypatch.setenv("GITHUB_TOKEN", "")
    monkeypatch.setenv("OSSDEX_GITHUB_TOKEN", "")
    monkeypatch.setattr("ossdex_core.config.subprocess.run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    res = CliRunner().invoke(app, ["discover", "--dry-run"])
    assert res.exit_code == 1 and "GITHUB_TOKEN" in res.output
