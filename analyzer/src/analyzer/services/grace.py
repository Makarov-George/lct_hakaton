"""Grace-периоды на перегонку техники.

Ограничение MVP: в ``plan_task`` хранятся только ``start_date`` и
``end_date`` (тип ``date``). Поэтому «начало этапа» — это полночь
соответствующего дня по Москве. Когда схема получит ``start_at`` и
``end_at timestamptz``, эти функции нужно будет заменить на работу
с точным временем — интерфейс останется тем же.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..models import PlanTask


MSK = ZoneInfo("Europe/Moscow")


def start_of_day_msk(d: date) -> datetime:
    """Полночь указанной даты по Москве."""
    return datetime.combine(d, time.min, tzinfo=MSK)


def end_of_day_msk(d: date) -> datetime:
    """Последняя секунда указанной даты по Москве."""
    return datetime.combine(d, time.max, tzinfo=MSK)


def in_arrival_grace(
    as_of: datetime,
    task: PlanTask,
    arrival_minutes: int,
) -> bool:
    """Попадаем ли в окно «техника ещё может не приехать».

    Args:
        as_of: момент анализа.
        task: этап, который только что начался.
        arrival_minutes: длительность окна в минутах.

    Returns:
        ``True``, если с начала этапа прошло меньше ``arrival_minutes``.
        В этом случае ``missing_required`` не создаём.
    """
    if arrival_minutes <= 0:
        return False
    task_start = start_of_day_msk(task.start_date).astimezone(as_of.tzinfo)
    return task_start <= as_of < task_start + timedelta(minutes=arrival_minutes)


def in_departure_grace(
    as_of: datetime,
    task: PlanTask,
    equipment_class_id,
    prev_task_equipment: set,
    departure_minutes: int,
) -> bool:
    """Попадаем ли в окно «техника ещё может уезжать».

    Args:
        as_of: момент анализа.
        task: текущий этап (тот, для которого нашли «лишнюю» технику).
        equipment_class_id: класс, который сейчас видим на площадке.
        prev_task_equipment: классы предыдущих этапов.
        departure_minutes: длительность окна.

    Returns:
        ``True``, если мы всё ещё готовы прощать уезжающую технику.
    """
    if departure_minutes <= 0:
        return False
    if equipment_class_id not in prev_task_equipment:
        return False
    task_start = start_of_day_msk(task.start_date).astimezone(as_of.tzinfo)
    return task_start <= as_of < task_start + timedelta(minutes=departure_minutes)