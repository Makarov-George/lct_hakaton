from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from analyzer.models import Camera, DetectionRow, PlanTask


@pytest.fixture
def site_id():
    return uuid4()


@pytest.fixture
def camera(site_id):
    return Camera(id=uuid4(), name="cam-1", no_data_after_min=30)


@pytest.fixture
def plan_task(site_id):
    from datetime import date
    return PlanTask(
        id=uuid4(),
        site_id=site_id,
        work_type_id=uuid4(),
        work_type_name="Устройство фундамента",
        observable=True,
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 15),
    )


@pytest.fixture
def frame_id():
    return uuid4()


@pytest.fixture
def class_id():
    return uuid4()


@pytest.fixture
def as_of():
    return datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)