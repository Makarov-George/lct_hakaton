from __future__ import annotations

from uuid import uuid4

from analyzer.services.aggregation import aggregate_max_per_class


def _d(frame_id, class_id):
    from analyzer.models import DetectionRow
    from datetime import datetime, timezone
    return DetectionRow(
        frame_id=frame_id,
        camera_id=uuid4(),
        captured_at=datetime.now(timezone.utc),
        equipment_class_id=class_id,
    )


def test_single_object_on_many_frames_counts_as_one():
    fid1, fid2, fid3 = uuid4(), uuid4(), uuid4()
    cls = uuid4()
    rows = [_d(fid1, cls), _d(fid2, cls), _d(fid3, cls)]
    result = aggregate_max_per_class(rows)
    assert result == {cls: 1}


def test_max_count_on_any_frame_wins():
    cls = uuid4()
    f1, f2, f3 = uuid4(), uuid4(), uuid4()
    rows = [
        _d(f1, cls),
        _d(f2, cls), _d(f2, cls), _d(f2, cls),
        _d(f3, cls), _d(f3, cls),
    ]
    result = aggregate_max_per_class(rows)
    assert result == {cls: 3}


def test_two_classes_aggregated_independently():
    a, b = uuid4(), uuid4()
    f = uuid4()
    rows = [_d(f, a), _d(f, a), _d(f, b)]
    result = aggregate_max_per_class(rows)
    assert result == {a: 2, b: 1}