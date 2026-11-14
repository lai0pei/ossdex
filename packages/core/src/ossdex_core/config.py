"""Settings from environment variables (and a local .env)."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _find_root() -> Path:
    """The project directory that holds `.env`, `data/` and `web/`: `OSSDEX_HOME` if set, else the
    nearest parent of this file with the uv workspace `pyproject.toml`, else the current directory
    (an installed, non-editable package has no workspace above it)."""
    home = os.environ.get("OSSDEX_HOME")
    if home:
        return Path(home).expanduser().resolve()
    for parent in Path(__file__).resolve().parents:
        pyproject = parent / "pyproject.toml"
        try:
            if pyproject.is_file() and "[tool.uv.workspace]" in pyproject.read_text():
                return parent
        except OSError:
            continue
    return Path.cwd()


ROOT = _find_root()
DEFAULT_MIN_STARS = 1000
DEFAULT_EXCLUDE_TOPICS = ("awesome-list", "awesome", "books", "tutorial", "interview")


@dataclass(frozen=True)
class Settings:
    db_path: Path
    github_token: str | None = None  # collector only; `resolve_token` also tries `gh auth token`
    min_stars: int = DEFAULT_MIN_STARS
    exclude_topics: tuple[str, ...] = DEFAULT_EXCLUDE_TOPICS
    require_license: bool = True  # unlicensed repos are "all rights reserved", not open source


def _path(value: str | Path) -> Path:
    """Relative paths in .env are relative to the project, not to wherever the server was started."""
    p = Path(value).expanduser()
    return p if p.is_absolute() else (ROOT / p).resolve()


def _topics(raw: str | None) -> tuple[str, ...]:
    if raw is None:
        return DEFAULT_EXCLUDE_TOPICS
    return tuple(t.strip().lower() for t in raw.split(",") if t.strip())


def _flag(raw: str | None, default: bool) -> bool:
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("false", "0", "no", "off")


def load_settings() -> Settings:
    load_dotenv(ROOT / ".env")
    env = os.environ.get
    data = _path(env("OSSDEX_DATA", ROOT / "data"))
    return Settings(
        db_path=_path(env("OSSDEX_DB", data / "ossdex.db")),
        github_token=env("OSSDEX_GITHUB_TOKEN") or env("GITHUB_TOKEN") or None,
        min_stars=int(env("OSSDEX_MIN_STARS", str(DEFAULT_MIN_STARS))),
        exclude_topics=_topics(env("OSSDEX_EXCLUDE_TOPICS")),
        require_license=_flag(env("OSSDEX_REQUIRE_LICENSE"), True),
    )


def resolve_token(settings: Settings) -> str | None:
    """The GitHub token from the environment, else from the `gh` CLI. Never logged or printed."""
    if settings.github_token:
        return settings.github_token
    try:
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10,
                             check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    token = out.stdout.strip()
    return token if out.returncode == 0 and token else None
