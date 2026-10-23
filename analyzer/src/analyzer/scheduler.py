"""Планировщик Analyzer."""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import Settings
from .db import acquire
from .services.analyzer import SiteAnalyzer

log = logging.getLogger(__name__)


async def run_once(pool, settings: Settings) -> None:
    """Один проход по всем активным участкам."""
    async with acquire(pool) as conn:
        analyzer = SiteAnalyzer(conn, settings.analyzer)
        repo_sites = await analyzer.repo.list_active_sites()

    for site in repo_sites:
        try:
            async with acquire(pool) as conn:
                await SiteAnalyzer(conn, settings.analyzer).analyze(site.id)
        except Exception:  # noqa: BLE001 — намеренно ловим всё,
            # чтобы один проблемный участок не ломал остальные.
            log.exception("analyze failed for site=%s (%s)", site.id, site.name)


def build_scheduler(pool, settings: Settings) -> AsyncIOScheduler:
    """Собирает планировщик с одним интервальным джобом."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_once,
        trigger=IntervalTrigger(seconds=settings.analyzer.interval_seconds),
        args=[pool, settings],
        id="analyzer.tick",
        max_instances=1,
        coalesce=True,
        next_run_time=None,
    )
    return scheduler