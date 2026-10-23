"""Доменные модели Analyzer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from uuid import UUID


@dataclass(frozen=True)
class Site:
    """Активный участок (``site.closed_at IS NULL``)."""

    id: UUID
    name: str


@dataclass(frozen=True)
class Camera:
    """Камера участка.

    Attributes:
        no_data_after_min: порог «молчания» в минутах. Если камера
            не присылала кадров дольше — это ``no_data``. ``None``
            означает, что проверка для этой камеры отключена.
    """

    id: UUID
    name: str
    no_data_after_min: int | None


@dataclass(frozen=True)
class PlanTask:
    """Этап плана на участке.

    Attributes:
        observable: контролируется ли вид работ по снимкам. Если нет —
            Analyzer не проверяет правила, а пишет ``not_observable``.
    """

    id: UUID
    site_id: UUID
    work_type_id: UUID
    work_type_name: str
    observable: bool
    start_date: date
    end_date: date


@dataclass(frozen=True)
class EffectiveRule:
    """Правило вида работ с учётом наследования.

    Результат SQL-функции ``effective_rules(work_type_id)``: для каждого
    класса техники возвращается ближайшее правило в дереве ``work_type``.

    Attributes:
        source_work_type_id: вид работ, где правило реально задано
            (может быть предком текущего).
        distance: на сколько уровней выше по дереву находится источник.
            ``0`` — правило задано на самом виде работ.
        kind: ``required`` / ``allowed`` / ``unexpected``.
        min_count: обязательное количество (только для ``required``).
    """

    rule_id: UUID
    source_work_type_id: UUID
    distance: int
    equipment_class_id: UUID
    kind: str
    min_count: int | None
    severity: str


@dataclass(frozen=True)
class DetectionRow:
    """Одна детекция на одном кадре.

    Это «сырая» строка из БД: один объект, найденный моделью на одном
    снимке. Агрегация в несколько объектов одного класса — уже задача
    :mod:`analyzer.services.aggregation`.
    """

    frame_id: UUID
    camera_id: UUID
    captured_at: datetime
    equipment_class_id: UUID


@dataclass(frozen=True)
class LastFrame:
    """Время последнего кадра с камеры (для проверки ``no_data``)."""

    camera_id: UUID
    last_at: datetime


@dataclass
class DeviationCandidate:
    """Кандидат на открытие/обновление отклонения.

    Ключ (``site_id, type, plan_task_id, rule_id, equipment_class_id,
    camera_id``) однозначно определяет открытое отклонение — ровно
    под уникальный индекс ``deviation_open_unique`` в схеме.
    """

    type: str
    severity: str
    message: str
    plan_task_id: UUID | None = None
    work_type_id: UUID | None = None
    rule_id: UUID | None = None
    equipment_class_id: UUID | None = None
    camera_id: UUID | None = None
    evidence_frame_ids: list[UUID] = field(default_factory=list)

    def key(self, site_id: UUID) -> tuple:
        """Уникальный ключ открытого отклонения.

        Порядок и состав полей должны совпадать с индексом
        ``deviation_open_unique``. Если менять — синхронизировать
        и там, и в :meth:`Repository.get_open_deviation`.
        """
        return (
            site_id,
            self.type,
            self.plan_task_id,
            self.rule_id,
            self.equipment_class_id,
            self.camera_id,
        )