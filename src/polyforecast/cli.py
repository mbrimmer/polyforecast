"""polyforecast CLI."""

from __future__ import annotations

import asyncio
import logging
import os

import click
import structlog

from polyforecast.config import settings


def _configure_logging(json_format: bool) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(message)s",
    )
    processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    processors.append(
        structlog.processors.JSONRenderer()
        if json_format
        else structlog.dev.ConsoleRenderer()
    )
    structlog.configure(processors=processors, cache_logger_on_first_use=True)


@click.group()
@click.option(
    "--json-logs/--console-logs",
    default=lambda: os.environ.get("LOG_FORMAT", "console").lower() == "json",
    help="Render logs as JSON (cron) or human-readable (interactive).",
)
def main(json_logs: bool) -> None:
    """polyforecast — LLM forecasting on Polymarket prediction markets."""
    _configure_logging(json_format=json_logs)


@main.command("scan")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Walk the pipeline but don't write to the database.",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Stop pagination after N raw markets (testing / cost-control).",
)
def scan_cmd(dry_run: bool, limit: int | None) -> None:
    """Pull, filter, and persist a fresh batch of Polymarket markets."""
    from polyforecast.scanner import scan

    result = asyncio.run(scan(dry_run=dry_run, market_limit=limit))
    click.echo(
        f"seen={result.total_markets_seen}  "
        f"active={result.passed_activity}  "
        f"liquid={result.passed_liquidity}  "
        f"persisted={result.persisted}"
        + ("  (dry-run, nothing written)" if dry_run else "")
    )


if __name__ == "__main__":
    main()
