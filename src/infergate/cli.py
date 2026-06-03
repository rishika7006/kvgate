"""``infergate`` command-line interface."""

from __future__ import annotations

import logging
import os

import click

from . import __version__
from .config import load_settings


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@click.group(help="InferGate — OpenAI-compatible LLM inference gateway.")
@click.version_option(__version__, prog_name="infergate")
def main() -> None:
    pass


@main.command(help="Run the gateway server.")
@click.option("--config", "-c", default=None, help="Path to a YAML config file.")
@click.option("--host", default=None, help="Bind host (overrides config).")
@click.option("--port", "-p", type=int, default=None, help="Bind port (overrides config).")
@click.option("--reload", is_flag=True, help="Auto-reload on code changes (dev only).")
def run(config: str, host: str, port: int, reload: bool) -> None:
    import uvicorn

    settings = load_settings(config)
    _setup_logging(settings.server.log_level)
    host = host or settings.server.host
    port = port or settings.server.port

    if config:
        os.environ["INFERGATE_CONFIG"] = config

    if reload:
        uvicorn.run("infergate.server:app", host=host, port=port, reload=True)
    else:
        from .app import create_app

        uvicorn.run(create_app(settings), host=host, port=port)


@main.command(help="Validate a config file and print a summary.")
@click.option("--config", "-c", default=None, help="Path to a YAML config file.")
def validate(config: str) -> None:
    settings = load_settings(config)
    click.echo(click.style("✓ config is valid", fg="green"))
    click.echo(f"  providers : {[p.name for p in settings.providers]}")
    click.echo(f"  models    : {[m.name for m in settings.models]}")
    click.echo(f"  strategy  : {settings.routing.strategy}")
    click.echo(
        f"  cache     : {'on' if settings.cache.enabled else 'off'} "
        f"({settings.cache.backend}, semantic={'on' if settings.cache.semantic.enabled else 'off'})"
    )
    click.echo(
        f"  ratelimit : {'on' if settings.ratelimit.enabled else 'off'} "
        f"({settings.ratelimit.default_rpm} rpm)"
    )


if __name__ == "__main__":  # pragma: no cover
    main()
