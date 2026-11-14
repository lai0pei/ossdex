"""ossdex-server command line: the web UI/API and the MCP server over the collector's database."""

from __future__ import annotations

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
