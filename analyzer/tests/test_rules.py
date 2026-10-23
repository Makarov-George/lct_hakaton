from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from analyzer.models import EffectiveRule
from analyzer.services.rules import check_no_data, check_task_rules


def _rule(kind, min_count=None, severity="warning", class_id=None):
    return EffectiveRule(
        rule_id=uuid4(),
        source_work_type_id=uuid4(),
        distance=0,
        equipment_class_id=class_id or uuid4(),
        kind=kind,
        min_count=min_count,
        severity=severity,
    )


def test_not_observable_produces_info(plan_task, as_of):
    task = plan_task.__class__(
        id=plan_task.id, site_id=plan_task.site_id,
        work_type_id=plan_task.work_type_id,
        work_type_name=plan_task.work_type_name,
        observable=False,
        start_date=plan_task.start_date,
        end_date=plan_task.end_date,
    )
    result = check_task_rules(
        task=task, rules=[], observed={}, as_of=as_of,
        arrival_minutes=0, departure_minutes=0, prev_task_equipment=set(),
    )
    assert len(result) == 1
    assert result[0].type == "not_observable"
    assert result[0].severity == "info"


def test_missing_required(plan_task, as_of):
    rule = _rule("required", min_count=2)
    result = check_task_rules(
        task=plan_task, rules=[rule], observed={}, as_of=as_of,
        arrival_minutes=0, departure_minutes=0, prev_task_equipment=set(),
    )
    assert len(result) == 1
    assert result[0].type == "missing_required"


def test_unexpected_equipment(plan_task, as_of):
    rule = _rule("unexpected")
    result = check_task_rules(
        task=plan_task, rules=[rule],
        observed={rule.equipment_class_id: 1},
        as_of=as_of, arrival_minutes=0, departure_minutes=0,
        prev_task_equipment=set(),
    )
    assert len(result) == 1
    assert result[0].type == "unexpected_equipment"


def test_arrival_grace_suppresses_missing(plan_task):
    from datetime import date
    from zoneinfo import ZoneInfo

    MSK = ZoneInfo("Europe/Moscow")

    task = plan_task.__class__(
        id=plan_task.id, site_id=plan_task.site_id,
        work_type_id=plan_task.work_type_id,
        work_type_name=plan_task.work_type_name,
        observable=True,
        start_date=date(2026, 1, 5),
        end_date=date(2026, 1, 15),
    )
    # as_of через 10 минут после начала дня — попадаем в grace 60 мин
    as_of = datetime(2026, 1, 5, 0, 10, tzinfo=MSK)
    rule = _rule("required", min_count=1)
    result = check_task_rules(
        task=task, rules=[rule], observed={}, as_of=as_of,
        arrival_minutes=60, departure_minutes=0, prev_task_equipment=set(),
    )
    assert result == []


def test_no_data_fires_after_threshold(camera, as_of):
    from datetime import timedelta
    last_at = as_of - timedelta(minutes=45)
    cand = check_no_data(camera, last_at, as_of)
    assert cand is not None
    assert cand.type == "no_data"
    assert cand.camera_id == camera.id


def test_no_data_does_not_fire_below_threshold(camera, as_of):
    from datetime import timedelta
    last_at = as_of - timedelta(minutes=5)
    assert check_no_data(camera, last_at, as_of) is None