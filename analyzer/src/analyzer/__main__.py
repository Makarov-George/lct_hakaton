"""Точка входа Analyzer."""

from __future__ import annotations

import asyncio
import logging
import signal

import structlog

from .config import load_settings
from .db import create_pool
from .scheduler import build_scheduler, run_once


def configure_logging(level: str) -> None:
    """Настраивает ``structlog`` и стандартный ``logging``."""
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


async def main() -> None:
    """Основная корутина процесса."""
    settings = load_settings()
    configure_logging(settings.log_level)
    log = structlog.get_logger("analyzer")

    pool = await create_pool(settings)
    log.info("analyzer started", interval=settings.analyzer.interval_seconds)

    scheduler = build_scheduler(pool, settings)
    scheduler.start()

    # Первый прогон сразу при старте — не ждём интервал.
    await run_once(pool, settings)

    # Ожидаем сигнала остановки.
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    await stop.wait()
    scheduler.shutdown(wait=False)
    await pool.close()
    log.info("analyzer stopped")


if __name__ == "__main__":
    asyncio.run(main())