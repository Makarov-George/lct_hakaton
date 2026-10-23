"""Управление жизненным циклом отклонений."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ..models import DeviationCandidate
from ..repositories import Repository


async def upsert_candidates(
    repo: Repository,
    site_id: UUID,
    candidates: list[DeviationCandidate],
    now: datetime,
) -> set[tuple]:
    """Создаёт или обновляет отклонения по списку кандидатов.

    Args:
        repo: репозиторий в текущей транзакции.
        site_id: участок (часть ключа).
        candidates: список кандидатов из ``rules.check_*``.
        now: момент анализа; используется как ``last_seen_at``.

    Returns:
        Множество ключей всех обработанных кандидатов. Analyzer
        передаст его в ``close_deviations_not_in``, чтобы закрыть
        всё, что не попало в текущий проход.
    """
    keys: set[tuple] = set()
    for cand in candidates:
        key = cand.key(site_id)
        keys.add(key)

        existing = await repo.get_open_deviation(site_id, key)
        if existing is not None:
            # Отклонение уже открыто — просто «освежаем» его.
            await repo.update_deviation(
                deviation_id=existing["id"],
                severity=cand.severity,
                message=cand.message,
                now=now,
            )
            deviation_id = existing["id"]
        else:
            deviation_id = await repo.insert_deviation(
                site_id=site_id,
                type_=cand.type,
                severity=cand.severity,
                message=cand.message,
                now=now,
                plan_task_id=cand.plan_task_id,
                work_type_id=cand.work_type_id,
                rule_id=cand.rule_id,
                equipment_class_id=cand.equipment_class_id,
                camera_id=cand.camera_id,
            )
        await repo.attach_evidence(deviation_id, cand.evidence_frame_ids)
    return keys