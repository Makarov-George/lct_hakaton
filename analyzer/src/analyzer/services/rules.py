"""Проверка правил и камер — чистые функции без БД."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ..models import (
    Camera,
    DeviationCandidate,
    EffectiveRule,
    PlanTask,
)
from .grace import in_arrival_grace, in_departure_grace


def check_no_data(
    camera: Camera,
    last_frame_at: datetime | None,
    as_of: datetime,
) -> DeviationCandidate | None:
    """Проверяет, не замолчала ли камера.

    Args:
        camera: модель камеры; ``no_data_after_min=None`` отключает проверку.
        last_frame_at: время последнего кадра с камеры (``None``, если
            кадров не было вообще).
        as_of: момент анализа.

    Returns:
        Кандидат ``no_data`` или ``None``, если всё в порядке.
    """
    threshold = camera.no_data_after_min
    if threshold is None or threshold <= 0:
        return None
    if last_frame_at is None:
        return DeviationCandidate(
            type="no_data",
            camera_id=camera.id,
            severity="warning",
            message=f"Камера «{camera.name}»: нет ни одного снимка",
        )
    delta_min = (as_of - last_frame_at).total_seconds() / 60.0
    if delta_min > threshold:
        return DeviationCandidate(
            type="no_data",
            camera_id=camera.id,
            severity="warning",
            message=(
                f"Камера «{camera.name}»: нет данных "
                f"{int(delta_min)} мин (порог {threshold})"
            ),
        )
    return None


def check_task_rules(
    task: PlanTask,
    rules: list[EffectiveRule],
    observed: dict[UUID, int],
    as_of: datetime,
    arrival_minutes: int,
    departure_minutes: int,
    prev_task_equipment: set[UUID],
) -> list[DeviationCandidate]:
    """Проверяет все правила одного этапа.

    Args:
        task: этап плана.
        rules: действующие правила с учётом наследования.
        observed: ``{equipment_class_id: count}`` из агрегации.
        as_of: момент анализа.
        arrival_minutes: окно прощения для въезда техники.
        departure_minutes: окно прощения для выезда техники.
        prev_task_equipment: классы, «привязанные» к недавно
            закончившимся этапам (для departure grace).

    Returns:
        Список кандидатов на открытие/обновление. Может быть пустым.
    """
    if not task.observable:
        return [
            DeviationCandidate(
                type="not_observable",
                plan_task_id=task.id,
                work_type_id=task.work_type_id,
                severity="info",
                message=f"Вид работ «{task.work_type_name}» не контролируется по снимкам",
            )
        ]

    result: list[DeviationCandidate] = []
    arrival_grace = in_arrival_grace(as_of, task, arrival_minutes)

    for rule in rules:
        count = observed.get(rule.equipment_class_id, 0)

        if rule.kind == "required":
            min_count = rule.min_count or 1
            if count < min_count:
                if arrival_grace:
                    continue
                result.append(
                    DeviationCandidate(
                        type="missing_required",
                        plan_task_id=task.id,
                        work_type_id=task.work_type_id,
                        rule_id=rule.rule_id,
                        equipment_class_id=rule.equipment_class_id,
                        severity=rule.severity,
                        message=(
                            f"Этап «{task.work_type_name}»: "
                            f"не хватает техники (нужно {min_count}, видно {count})"
                        ),
                    )
                )
        elif rule.kind == "unexpected":
            if count > 0:
                if in_departure_grace(
                    as_of, task, rule.equipment_class_id,
                    prev_task_equipment, departure_minutes,
                ):
                    continue
                result.append(
                    DeviationCandidate(
                        type="unexpected_equipment",
                        plan_task_id=task.id,
                        work_type_id=task.work_type_id,
                        rule_id=rule.rule_id,
                        equipment_class_id=rule.equipment_class_id,
                        severity=rule.severity,
                        message=(
                            f"Этап «{task.work_type_name}»: "
                            f"обнаружена недопустимая техника ({count})"
                        ),
                    )
                )
    return result