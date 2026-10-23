"""Агрегация сырых детекций в «картину за окно»."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from ..models import DetectionRow


def aggregate_max_per_class(
    detections: list[DetectionRow],
) -> dict[UUID, int]:
    """Считает максимум одновременного присутствия по каждому классу.

    Args:
        detections: плоский список детекций за окно.

    Returns:
        Словарь ``{equipment_class_id: max_count}``. Классы, которых
        не было, в словаре отсутствуют — вызывающий код должен
        использовать ``.get(class_id, 0)``.
    """
    per_frame: dict[tuple[UUID, UUID], int] = defaultdict(int)
    for d in detections:
        per_frame[(d.frame_id, d.equipment_class_id)] += 1

    max_per_class: dict[UUID, int] = defaultdict(int)
    for (_, class_id), cnt in per_frame.items():
        if cnt > max_per_class[class_id]:
            max_per_class[class_id] = cnt
    return dict(max_per_class)


def last_frame_by_camera(rows: list[tuple[UUID, datetime]]) -> dict[UUID, datetime]:
    """Собирает время последнего кадра по камерам."""
    result: dict[UUID, datetime] = {}
    for cam_id, ts in rows:
        prev = result.get(cam_id)
        if prev is None or ts > prev:
            result[cam_id] = ts
    return result