import pytest
from core.event import (
    Event, Detection, FrameStats, SCHEMA_VERSION,
    LEVEL_LOW, LEVEL_MEDIUM, LEVEL_HIGH,
)


def test_schema_version_and_frozen_fields():
    """契约冻结护栏：SCHEMA_FIELDS 是不可变的 12 个字段。

    如果有人（包括 AI）想删字段或改名，这条测试会立刻红灯。
    新增可选字段不在此列，但需要同步 SCHEMA_VERSION。
    """
    assert SCHEMA_VERSION == 1
    assert len(Event.SCHEMA_FIELDS) == 12
    assert Event.SCHEMA_FIELDS == (
        "event_id", "timestamp", "person_id", "identity", "zone",
        "stay_seconds", "door_approaches", "package_present",
        "risk_score", "risk_reasons", "health_score", "actions",
    )


def test_event_schema_roundtrip():
    ev = Event(person_id=3, identity="unknown", zone="front_door",
               stay_seconds=95, door_approaches=3, risk_score=88,
               risk_reasons=["night", "long_stay"], health_score=96,
               actions=["ptz_track", "light_on"])
    d = ev.to_dict(schema_only=True)
    # 固定字段齐全
    for k in Event.SCHEMA_FIELDS:
        assert k in d
    ev2 = Event.from_dict(d)
    assert ev2.person_id == 3 and ev2.risk_score == 88
    # 未知字段被忽略（向后兼容）
    ev3 = Event.from_dict({**d, "future_field": 123})
    assert not hasattr(ev3, "future_field") or getattr(ev3, "future_field", None) is None


def test_event_validate():
    assert Event(risk_score=50).validate() == []
    assert Event(risk_score=150).validate()  # out of range
    assert Event(stay_seconds=-1).validate()
    assert Event(identity="ghost").validate()


def test_risk_level_from_score():
    assert Event(risk_score=10).risk_level_from_score() == LEVEL_LOW
    assert Event(risk_score=45).risk_level_from_score() == LEVEL_MEDIUM
    assert Event(risk_score=88).risk_level_from_score() == LEVEL_HIGH
