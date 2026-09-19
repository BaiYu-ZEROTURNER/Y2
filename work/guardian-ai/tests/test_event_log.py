"""Event 日志的回归护栏（F1，联调期基石）。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.event import Event, SCHEMA_VERSION          # noqa: E402
from core.event_log import EventLogger                 # noqa: E402


def test_logger_disabled_when_no_path():
    """默认必须关闭——否则测试和普通运行会到处撒文件。"""
    lg = EventLogger()
    lg.log(Event(risk_score=88))          # 不应抛异常
    lg.close()


def test_logger_writes_schema_fields_only(tmp_path):
    p = str(tmp_path / "run.jsonl")
    with EventLogger(p, run_id="t1") as lg:
        lg.log(Event(person_id=3, risk_score=85, risk_reasons=["unknown"]),
               extra={"scenario": "loiter", "frame_index": 7})

    recs = EventLogger.read(p)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["schema_version"] == SCHEMA_VERSION
    assert rec["run_id"] == "t1"
    assert rec["ext"] == {"scenario": "loiter", "frame_index": 7}
    # 只写 schema 字段，不写内部扩展字段（保证日志与页面/测试三处一致）
    assert set(rec["event"]) == set(Event.SCHEMA_FIELDS)
    assert rec["event"]["risk_score"] == 85


def test_logger_appends_multiple_lines(tmp_path):
    p = str(tmp_path / "run.jsonl")
    with EventLogger(p) as lg:
        for i in range(5):
            lg.log(Event(person_id=i))
    assert len(EventLogger.read(p)) == 5
    # 每行都是合法 JSON
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            json.loads(line)


def test_read_missing_file_returns_empty():
    assert EventLogger.read("definitely_not_here.jsonl") == []


def test_measure_script_can_write_log(tmp_path):
    """measure_scenarios.py --log 必须能跑通，F4 靠它记录稳定性。"""
    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
    import measure_scenarios as ms

    p = str(tmp_path / "runs.jsonl")
    with EventLogger(p) as lg:
        rows = ms.measure_all(logger=lg)

    assert len(rows) == 4
    recs = EventLogger.read(p)
    # 4 个场景的帧数：family 5 + delivery 6 + loiter 70 + occlusion 6
    assert len(recs) == 5 + 6 + 70 + 6
    assert {r["ext"]["scenario"] for r in recs} == set(ms.SCENARIOS)
