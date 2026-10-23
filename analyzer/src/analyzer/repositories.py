"""Все SQL-запросы Analyzer.

Репозиторий привязан к конкретному соединению и предполагает, что
вызывается внутри транзакции :func:`analyzer.db.acquire`.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

import asyncpg

from .models import (
    Camera,
    DetectionRow,
    EffectiveRule,
    LastFrame,
    PlanTask,
    Site,
)


class Repository:
    """Обёртка над соединением с методами под задачи Analyzer."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn

    # Участки и камеры

    async def list_active_sites(self) -> list[Site]:
        """Возвращает все незакрытые участки."""
        rows = await self.conn.fetch(
            "SELECT id, name FROM site WHERE closed_at IS NULL ORDER BY created_at"
        )
        return [Site(id=r["id"], name=r["name"]) for r in rows]

    async def get_site(self, site_id: UUID) -> Site | None:
        """Возвращает участок, если он существует и не закрыт."""
        row = await self.conn.fetchrow(
            "SELECT id, name FROM site WHERE id = $1 AND closed_at IS NULL", site_id
        )
        return Site(id=row["id"], name=row["name"]) if row else None

    async def list_active_cameras(self, site_id: UUID) -> list[Camera]:
        """Активные камеры участка."""
        rows = await self.conn.fetch(
            """
            SELECT id, name, no_data_after_min
            FROM camera
            WHERE site_id = $1 AND closed_at IS NULL
            ORDER BY name
            """,
            site_id,
        )
        return [
            Camera(id=r["id"], name=r["name"], no_data_after_min=r["no_data_after_min"])
            for r in rows
        ]

    # Этапы плана

    async def active_plan_tasks(self, site_id: UUID, on_date: date) -> list[PlanTask]:
        """Активные на дату этапы участка."""
        rows = await self.conn.fetch(
            """
            SELECT t.id, t.site_id, t.work_type_id, t.start_date, t.end_date,
                   w.name AS work_type_name, w.observable
            FROM active_plan_tasks($1, $2) AS t
            JOIN work_type w ON w.id = t.work_type_id
            """,
            site_id,
            on_date,
        )
        return [
            PlanTask(
                id=r["id"],
                site_id=r["site_id"],
                work_type_id=r["work_type_id"],
                work_type_name=r["work_type_name"],
                observable=r["observable"],
                start_date=r["start_date"],
                end_date=r["end_date"],
            )
            for r in rows
        ]

    # Правила

    async def effective_rules(self, work_type_id: UUID) -> list[EffectiveRule]:
        """Действующие правила вида работ с учётом наследования."""
        rows = await self.conn.fetch(
            """
            SELECT rule_id, source_work_type_id, distance,
                   equipment_class_id, kind, min_count, severity
            FROM effective_rules($1)
            """,
            work_type_id,
        )
        return [
            EffectiveRule(
                rule_id=r["rule_id"],
                source_work_type_id=r["source_work_type_id"],
                distance=r["distance"],
                equipment_class_id=r["equipment_class_id"],
                kind=r["kind"],
                min_count=r["min_count"],
                severity=r["severity"],
            )
            for r in rows
        ]

    async def equipment_classes_for_recent_tasks(
        self,
        site_id: UUID,
        since: datetime,
        until: datetime,
    ) -> set[UUID]:
        """Классы техники, «привязанные» к недавно закончившимся этапам.

        Нужно для departure grace: если этап закончился в интервале
        ``[since, until]``, его техника (required/allowed) ещё имеет
        право находиться на площадке — её не считаем ``unexpected``.

        Днём окончания считаем конец суток ``end_date``: пока в схеме
        нет ``end_at timestamptz``, точнее не получится. Уточнение
        запроса — задача следующей итерации.
        """
        rows = await self.conn.fetch(
            """
            SELECT DISTINCT er.equipment_class_id
            FROM plan_task pt
            CROSS JOIN LATERAL effective_rules(pt.work_type_id) AS er
            WHERE pt.site_id = $1
              AND pt.closed_at IS NULL
              AND (pt.end_date + interval '1 day')::timestamptz > $2
              AND (pt.end_date + interval '1 day')::timestamptz <= $3
              AND er.kind IN ('required', 'allowed')
            """,
            site_id,
            since,
            until,
        )
        return {r["equipment_class_id"] for r in rows}

    # Детекции

    async def detections_window(
        self,
        site_id: UUID,
        window_from: datetime,
        window_to: datetime,
        min_confidence: float,
    ) -> list[DetectionRow]:
        """Детекции техники за окно [window_from, window_to)."""
        rows = await self.conn.fetch(
            """
            SELECT f.id AS frame_id,
                   f.camera_id,
                   f.captured_at,
                   ec.id AS equipment_class_id
            FROM frame f
            JOIN detection_report dr ON dr.frame_id = f.id AND dr.status = 'ok'
            JOIN detection d ON d.report_id = dr.id
            JOIN equipment_class ec ON ec.code = d.equipment_class_code
            WHERE f.site_id = $1
              AND f.captured_at >= $2
              AND f.captured_at < $3
              AND d.confidence >= $4
            """,
            site_id,
            window_from,
            window_to,
            min_confidence,
        )
        return [
            DetectionRow(
                frame_id=r["frame_id"],
                camera_id=r["camera_id"],
                captured_at=r["captured_at"],
                equipment_class_id=r["equipment_class_id"],
            )
            for r in rows
        ]

    async def last_frame_by_camera(self, site_id: UUID) -> list[LastFrame]:
        """Время последнего кадра по каждой камере участка."""
        rows = await self.conn.fetch(
            """
            SELECT camera_id, MAX(captured_at) AS last_at
            FROM frame
            WHERE site_id = $1
            GROUP BY camera_id
            """,
            site_id,
        )
        return [
            LastFrame(camera_id=r["camera_id"], last_at=r["last_at"]) for r in rows
        ]

    # Отклонения

    async def get_open_deviation(
        self, site_id: UUID, key: tuple
    ) -> asyncpg.Record | None:
        """Находит открытое отклонение по ключу или возвращает ``None``.

        Сравнение через ``IS NOT DISTINCT FROM`` — потому что в ключе
        может быть ``NULL`` (например, ``rule_id`` у ``no_data``), а
        обычное ``=`` с ``NULL`` даёт ``NULL``, а не ``TRUE``.
        """
        _, dev_type, plan_task_id, rule_id, equipment_class_id, camera_id = key
        return await self.conn.fetchrow(
            """
            SELECT id, hits, severity, status
            FROM deviation
            WHERE site_id = $1
              AND type = $2
              AND plan_task_id IS NOT DISTINCT FROM $3
              AND rule_id IS NOT DISTINCT FROM $4
              AND equipment_class_id IS NOT DISTINCT FROM $5
              AND camera_id IS NOT DISTINCT FROM $6
              AND status IN ('open', 'acknowledged')
            FOR UPDATE
            """,
            site_id,
            dev_type,
            plan_task_id,
            rule_id,
            equipment_class_id,
            camera_id,
        )

    async def insert_deviation(
        self,
        site_id: UUID,
        type_: str,
        severity: str,
        message: str,
        now: datetime,
        plan_task_id: UUID | None,
        work_type_id: UUID | None,
        rule_id: UUID | None,
        equipment_class_id: UUID | None,
        camera_id: UUID | None,
    ) -> UUID:
        """Создаёт новое отклонение и возвращает его id."""
        return await self.conn.fetchval(
            """
            INSERT INTO deviation (
                site_id, type, plan_task_id, work_type_id, rule_id,
                equipment_class_id, camera_id, severity, status, message,
                hits, first_seen_at, last_seen_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, 'open', $9,
                1, $10, $10
            )
            RETURNING id
            """,
            site_id,
            type_,
            plan_task_id,
            work_type_id,
            rule_id,
            equipment_class_id,
            camera_id,
            severity,
            message,
            now,
        )

    async def update_deviation(
        self,
        deviation_id: UUID,
        severity: str,
        message: str,
        now: datetime,
    ) -> None:
        """Обновляет «живое» отклонение.

        Смена severity разрешена, чтобы в будущем можно было
        эскалировать (info → warning → critical) по мере накопления hits.
        """
        await self.conn.execute(
            """
            UPDATE deviation
            SET hits = hits + 1,
                last_seen_at = $2,
                severity = $3,
                message = $4
            WHERE id = $1
            """,
            deviation_id,
            now,
            severity,
            message,
        )

    async def close_deviations_not_in(
        self,
        site_id: UUID,
        keep_keys: set[tuple],
        now: datetime,
    ) -> int:
        """Закрывает открытые отклонения, которых нет в keep_keys.

        Returns:
            Количество закрытых отклонений (для логов и метрик).
        """
        rows = await self.conn.fetch(
            """
            SELECT id, type, plan_task_id, rule_id, equipment_class_id, camera_id
            FROM deviation
            WHERE site_id = $1 AND status IN ('open', 'acknowledged')
            FOR UPDATE
            """,
            site_id,
        )
        to_close: list[UUID] = []
        for r in rows:
            key = (
                site_id,
                r["type"],
                r["plan_task_id"],
                r["rule_id"],
                r["equipment_class_id"],
                r["camera_id"],
            )
            if key not in keep_keys:
                to_close.append(r["id"])
        if not to_close:
            return 0
        await self.conn.execute(
            """
            UPDATE deviation
            SET status = 'resolved',
                closed_at = $2,
                closed_by = 'system',
                close_reason = 'condition_cleared'
            WHERE id = ANY($1::uuid[])
            """,
            to_close,
            now,
        )
        return len(to_close)

    # Evidence

    async def attach_evidence(
        self,
        deviation_id: UUID,
        frame_ids: list[UUID],
        role: str = "violation",
    ) -> None:
        """Привязывает кадры к отклонению.

        ``ON CONFLICT DO NOTHING`` — потому что при повторных проходах
        один и тот же кадр может прийти второй раз. PK у таблицы
        ``(deviation_id, frame_id)``.
        """
        if not frame_ids:
            return
        await self.conn.executemany(
            """
            INSERT INTO deviation_evidence (deviation_id, frame_id, role)
            VALUES ($1, $2, $3)
            ON CONFLICT DO NOTHING
            """,
            [(deviation_id, fid, role) for fid in frame_ids],
        )