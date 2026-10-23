"""Работа с пулом соединений PostgreSQL.

Analyzer использует ``asyncpg`` напрямую, без ORM.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg

from .config import Settings


async def create_pool(settings: Settings) -> asyncpg.Pool:
    """Создаёт пул соединений к PostgreSQL.

    Args:
        settings: настройки с готовым ``database_url``.

    Returns:
        Готовый пул соединений.
    """
    return await asyncpg.create_pool(
        dsn=settings.database_url,
        min_size=1,
        max_size=4,
        command_timeout=30,
    )


@asynccontextmanager
async def acquire(pool: asyncpg.Pool) -> AsyncIterator[asyncpg.Connection]:
    """Контекстный менеджер: соединение + транзакция + actor.

    Один вызов = одна транзакция на один участок. Если внутри что-то
    упадёт — откатится всё целиком, не будет «полуоткрытых» отклонений.

    Перед началом транзакции выставляем ``app.actor='system'``: это
    читает триггер ``deviation_on_change`` и пишет в ``deviation_history``
    правильного автора. ``SET LOCAL`` действует только в рамках текущей
    транзакции и не утекает в другие соединения.

    Yields:
        Открытое соединение внутри активной транзакции.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("SET LOCAL app.actor = 'system'")
            yield conn