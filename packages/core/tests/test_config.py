import subprocess
import sys
from pathlib import Path

from ossdex_core.config import ROOT, load_settings


def test_relative_paths_in_env_resolve_against_the_project(monkeypatch):
    monkeypatch.setenv("OSSDEX_DB", "../elsewhere/ossdex.db")
    s = load_settings()
    assert s.db_path.is_absolute() and s.db_path == (ROOT / "../elsewhere/ossdex.db").resolve()


def test_root_is_the_workspace_not_a_package_directory():
    assert (ROOT / "packages" / "core").is_dir() and (ROOT / "web").is_dir()
    assert "[tool.uv.workspace]" in (ROOT / "pyproject.toml").read_text()


def test_ossdex_home_overrides_the_root(tmp_path):
    out = subprocess.run(
        [sys.executable, "-I", "-c", "from ossdex_core.config import ROOT; print(ROOT)"],
        capture_output=True, text=True, check=True, env={"OSSDEX_HOME": str(tmp_path)})
    assert Path(out.stdout.strip()) == tmp_path.resolve()
