"""ossdex-server command line: the web UI/API and the MCP server over the collector's database."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

import json
import os
import shutil
import sys
from pathlib import Path

import typer

app = typer.Typer(help="Read-only web UI, API and MCP server over the ossdex database "
                       "(filled by the separate ossdex-collector)", no_args_is_help=True)


def _fail(message: str) -> typer.Exit:
    typer.echo(f"error: {message}", err=True)
    return typer.Exit(1)


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8200,
    workers: int = typer.Option(1, "--workers", "-w", envvar="OSSDEX_WORKERS", min=1,
                                help="server processes (about one per CPU core on a busy server)"),
) -> None:
    """Run the web UI, the API and the MCP server (at /mcp) in one process group.
    Build the UI first: `npm run build` in web/."""
    from .api import run_server

    run_server(host, port, workers)


@app.command()
def mcp(
    transport: str = typer.Option("stdio", "--transport", "-t", help="transport: stdio, sse, or streamable-http"),
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="host to bind to (for sse or streamable-http)"),
    port: int = typer.Option(8201, "--port", "-p", help="port to bind to (for sse or streamable-http)"),
) -> None:
    """Run the MCP server (stdio by default; supports sse / streamable-http for remote/desktop connectors)."""
    from .mcp import serve_mcp

    if transport not in ("stdio", "sse", "streamable-http"):
        raise _fail(f"invalid transport {transport!r}: must be stdio, sse, or streamable-http")
    serve_mcp(transport=transport, host=host, port=port)  # type: ignore[arg-type]


def claude_config_path() -> Path:
    """Where Claude Desktop keeps its config file on this OS."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def claude_entry() -> dict:
    """The `ossdex` server entry for Claude Desktop. Claude Desktop does not inherit the shell PATH,
    so every path in it is absolute."""
    from ossdex_core.config import ROOT, load_settings

    uv = os.environ.get("UV") or shutil.which("uv")
    if not uv:
        raise _fail("could not find `uv`. Install it (https://docs.astral.sh/uv/) or connect through a "
                    "hosted ossdex: Claude -> Settings -> Connectors -> Add custom connector.")
    return {"command": str(Path(uv).resolve()),
            "args": ["run", "--directory", str(ROOT), "--package", "ossdex-server", "ossdex-server", "mcp"],
            "env": {"OSSDEX_DB": str(load_settings().db_path)}}


@app.command("claude-config")
def claude_config(
    install: bool = typer.Option(False, "--install", help="add ossdex to Claude Desktop's config file"),
) -> None:
    """Connect Claude Desktop to this computer's ossdex. Prints the config entry; with --install,
    merges it into Claude's config file (keeping your other servers) and saves a .bak copy."""
    entry = claude_entry()
    path = claude_config_path()
    if not install:
        typer.echo(json.dumps({"mcpServers": {"ossdex": entry}}, indent=2))
        typer.echo(f"\nPaste the \"ossdex\" entry into {path}\n"
                   "(in Claude: Settings -> Developer -> Edit Config), or run this command with --install.")
        return
    config: dict = {}
    if path.exists():
        try:
            config = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError as e:
            raise _fail(f"{path} is not valid JSON ({e}). Nothing was changed.")
        if not isinstance(config, dict):
            raise _fail(f"{path} is not a JSON object. Nothing was changed.")
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    servers = config.get("mcpServers")
    if not isinstance(servers, dict):
        servers = config["mcpServers"] = {}
    servers["ossdex"] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2) + "\n")
    typer.echo(f"Done. ossdex was added to {path}\n"
               "Now fully quit Claude (Cmd+Q on Mac, or right-click the tray icon -> Quit on Windows) "
               "and open it again.")
