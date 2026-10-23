"""Главный сценарий анализа одного участка.

1. Загружает активные этапы и камеры участка.
2. Тянет детекции за окно и агрегирует их по классам.
3. Проверяет ``no_data`` по каждой активной камере.
4. Проверяет правила для каждого этапа.
5. Делает upsert отклонений и закрывает устаревшие.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

from ..config import AnalyzerConfig
from ..models import DeviationCandidate
from ..repositories import Repository
from .aggregation import aggregate_max_per_class
from .deviation import upsert_candidates
from .rules import check_no_data, check_task_rules

log = logging.getLogger(__name__)


class SiteAnalyzer:
    """Анализ одного участка на конкретный момент времени."""

    def __init__(
        self,
        conn: asyncpg.Connection,
        config: AnalyzerConfig,
        as_of: datetime | None = None,
    ) -> None:
        """
        Args:
            conn: соединение внутри активной транзакции.
            config: настройки Analyzer (окно, grace, пороги).
            as_of: момент анализа. ``None`` — «сейчас, UTC».
                Параметр существует для тестов и пересчёта задним
                числом.
        """
        self.repo = Repository(conn)
        self.config = config
        self.as_of = as_of or datetime.now(timezone.utc)

    async def analyze(self, site_id: UUID) -> None:
        """Основной проход по участку.

        Args:
            site_id: идентификатор участка.
        """
        window_from = self.as_of - timedelta(minutes=self.config.analysis_window_minutes)

        tasks = await self.repo.active_plan_tasks(site_id, self.as_of.date())
        cameras = await self.repo.list_active_cameras(site_id)

        detections = await self.repo.detections_window(
            site_id=site_id,
            window_from=window_from,
            window_to=self.as_of,
            min_confidence=self.config.min_confidence,
        )
        observed = aggregate_max_per_class(detections)

        last_frames_rows = await self.repo.last_frame_by_camera(site_id)
        last_frame = {r.camera_id: r.last_at for r in last_frames_rows}

        candidates: list[DeviationCandidate] = []

        # Камеры, которые давно не присылали данных.
        for cam in cameras:
            cand = check_no_data(cam, last_frame.get(cam.id), self.as_of)
            if cand is not None:
                candidates.append(cand)

        # Есть техника, но нет активных этапов — это тоже отклонение.
        if not tasks and any(observed.values()):
            candidates.append(
                DeviationCandidate(
                    type="unplanned_activity",
                    severity="warning",
                    message="На участке есть техника, но нет активных этапов",
                )
            )

        # Классы техники, которые «принадлежат» недавно закончившимся этапам.
        prev_equipment = await self._equipment_of_recently_ended_tasks(site_id, tasks)

        # Правила по каждому активному этапу.
        for task in tasks:
            rules = await self.repo.effective_rules(task.work_type_id)
            candidates.extend(
                check_task_rules(
                    task=task,
                    rules=rules,
                    observed=observed,
                    as_of=self.as_of,
                    arrival_minutes=self.config.grace.arrival_minutes,
                    departure_minutes=self.config.grace.departure_minutes,
                    prev_task_equipment=prev_equipment,
                )
            )

        # Upsert и закрытие всего, что не попало в текущий проход.
        keys = await upsert_candidates(self.repo, site_id, candidates, self.as_of)
        closed = await self.repo.close_deviations_not_in(site_id, keys, self.as_of)

        log.info(
            "analyze site=%s tasks=%d detections=%d candidates=%d closed=%d",
            site_id, len(tasks), len(detections), len(candidates), closed,
        )

    async def _equipment_of_recently_ended_tasks(
        self,
        site_id: UUID,
        current_tasks: list,
    ) -> set[UUID]:
        """Классы техники, «привязанные» к недавно закончившимся этапам.

        ``current_tasks`` параметр пока не используется, но оставлен
        в сигнатуре: в следующей итерации здесь появится логика
        «техника, которая нужна и на текущем этапе тоже, не считается
        уезжающей».
        """
        if self.config.grace.departure_minutes <= 0:
            return set()
        earliest = self.as_of - timedelta(minutes=self.config.grace.departure_minutes)
        return await self.repo.equipment_classes_for_recent_tasks(
            site_id=site_id,
            since=earliest,
            until=self.as_of,
        )