import json
from pathlib import Path

import pytest
from ossdex_server import cli
from typer.testing import CliRunner


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    path = tmp_path / "Claude" / "claude_desktop_config.json"
    monkeypatch.setattr(cli, "claude_config_path", lambda: path)
    monkeypatch.setattr(cli, "claude_entry", lambda: {"command": "/abs/uv", "args": ["run", "--directory", "/abs/root"]})
    return path


def run(*args):
    return CliRunner().invoke(cli.app, ["claude-config", *args])


def test_install_creates_the_file(cfg):
    assert run("--install").exit_code == 0
    assert json.loads(cfg.read_text())["mcpServers"]["ossdex"]["command"] == "/abs/uv"


def test_install_keeps_other_servers_and_writes_a_backup(cfg):
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"theme": "x", "mcpServers": {"other": {"command": "foo"}}}))
    assert run("--install").exit_code == 0
    data = json.loads(cfg.read_text())
    assert data["theme"] == "x" and data["mcpServers"]["other"] == {"command": "foo"} and "ossdex" in data["mcpServers"]
    assert json.loads(Path(str(cfg) + ".bak").read_text())["mcpServers"] == {"other": {"command": "foo"}}


def test_install_refuses_invalid_json(cfg):
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{ not json")
    res = run("--install")
    assert res.exit_code == 1 and cfg.read_text() == "{ not json"


def test_without_install_only_prints(cfg):
    res = run()
    assert res.exit_code == 0 and '"ossdex"' in res.output and not cfg.exists()


def test_real_entry_uses_absolute_paths(monkeypatch):
    monkeypatch.setenv("UV", "/usr/bin/env")  # any existing executable; the test is about path shape
    entry = cli.claude_entry()
    assert Path(entry["command"]).is_absolute() and Path(entry["args"][2]).is_absolute()
    assert Path(entry["env"]["OSSDEX_DB"]).is_absolute()
