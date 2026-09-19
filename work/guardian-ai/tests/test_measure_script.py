"""实测数字表生成器的回归护栏（F1）。

measure_scenarios.py 是 B 交给 A 的交接工具，也是演示数据的唯一来源。
它一旦坏了，A 拿不到数字、页面没数据、演示直接失败。所以必须有测试兜住。
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (_ROOT, os.path.join(_ROOT, "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import measure_scenarios as ms   # noqa: E402


def test_measure_all_covers_four_scenarios():
    rows = ms.measure_all()
    assert [r["scenario"] for r in rows] == list(ms.SCENARIOS)


def test_measure_rows_have_handoff_fields():
    """A 只认这几个字段，缺一个就没法填表。"""
    required = ("scenario", "stay_seconds", "door_approaches",
                "health_score", "risk_score", "risk_level", "actions", "risk_reasons")
    for r in ms.measure_all():
        for k in required:
            assert k in r, f"{r['scenario']} 缺少交接字段：{k}"


def test_scenario_expectations_hold():
    """四类场景必须落在方案预期的档位——这是验收标准，不是参考值。"""
    by = {r["scenario"]: r for r in ms.measure_all()}

    assert by["family"]["risk_level"] == "low"
    assert by["family"]["stay_seconds"] == 0

    assert by["delivery"]["risk_level"] == "low"

    assert by["loiter"]["risk_level"] == "high"
    assert "ptz_track" in by["loiter"]["actions"]
    assert "notify" in by["loiter"]["actions"]
    assert by["loiter"]["stay_seconds"] > 30

    assert by["occlusion"]["health_issues"] == ["obstructed"]
    assert by["occlusion"]["health_score"] <= 40
    assert "notify_health" in by["occlusion"]["actions"]


def test_loiter_risk_climbs_over_time():
    """风险分必须是"爬"上去的，不能第一帧就顶格。

    这条直接决定演示观感：评委要看到分数逐级跃迁、原因逐条点亮。
    预期轨迹（loiter，70 帧）：
        35（unknown+night）-> 50（+sensitive_roi）-> 65（+repeat_approach）
        -> 75（+long_stay）-> 85（+long_stay_extra）
    """
    _, trace = ms.run_scenario("loiter", collect_frames=True)
    assert len(trace) > 10
    scores = [t["risk_score"] for t in trace]

    # 开局不能直接是高风险
    assert scores[0] < 60, "开局就是高风险，看不到爬升过程"
    # 终局必须是高风险
    assert scores[-1] >= 60
    # 分数只能上升（累计逻辑不稳定会出现回落，那说明跟踪丢 id 了）
    assert scores == sorted(scores), "风险分出现回落，说明累计逻辑不稳定"
    # 至少 4 个不同的台阶，才叫"看得见的爬升"
    assert len(set(scores)) >= 4, f"台阶太少：{sorted(set(scores))}"
    # 必须完成"中风险 -> 高风险"的跨越
    assert min(scores) < 60 and max(scores) >= 60
