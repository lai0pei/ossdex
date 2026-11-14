"""Run `ossdex-collector update` every day with launchd (macOS).

Daily snapshots are what star growth is computed from, so the collector should run daily. This only
builds and installs a user LaunchAgent when the user runs `ossdex-collector schedule install`.
"""

from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from ossdex_core.config import ROOT

LABEL = "dev.ossdex.update"


def plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def build_plist(*, uv: str, project: Path, hour: int, minute: int, log: Path,
                path_env: str) -> bytes:
    return plistlib.dumps({
        "Label": LABEL,
        "ProgramArguments": [uv, "--directory", str(project), "run", "--package", "ossdex-collector",
                             "ossdex-collector", "update"],
        "StartCalendarInterval": {"Hour": hour, "Minute": minute},
        "EnvironmentVariables": {"PATH": path_env},
        "StandardOutPath": str(log),
        "StandardErrorPath": str(log),
        "RunAtLoad": False,
    })


def default_plist(hour: int = 4, minute: int = 30) -> bytes:
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError("`uv` was not found on PATH; install it or run `ossdex-collector update` yourself")
    return build_plist(uv=uv, project=ROOT, hour=hour, minute=minute,
                       log=ROOT / "data" / "update.log",
                       path_env=os.environ.get("PATH", "/usr/bin:/bin:/usr/local/bin"))


def cron_line(*, uv: str, project: Path, hour: int, minute: int) -> str:
    """The crontab entry for systems without launchd. Nothing is written for the user."""
    log = project / "data" / "update.log"
    return (f"{minute} {hour} * * * {uv} --directory {project} run --package ossdex-collector ossdex-collector update "
            f">> {log} 2>&1")


Runner = Callable[[list[str]], int]


def _run(cmd: list[str]) -> int:
    return subprocess.run(cmd, capture_output=True, check=False).returncode


def install(data: bytes, *, path: Path | None = None, load: bool = True,
            runner: Runner = _run) -> Path:
    path = path or plist_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if load:
        uid = str(os.getuid())
        runner(["launchctl", "bootout", f"gui/{uid}/{LABEL}"])  # replace an older one, if any
        if runner(["launchctl", "bootstrap", f"gui/{uid}", str(path)]) != 0:
            raise RuntimeError(f"launchctl could not load {path}; load it yourself with: "
                               f"launchctl bootstrap gui/{uid} {path}")
    return path


def remove(*, path: Path | None = None, runner: Runner = _run) -> bool:
    path = path or plist_path()
    runner(["launchctl", "bootout", f"gui/{os.getuid()}/{LABEL}"])
    if path.exists():
        path.unlink()
        return True
    return False
