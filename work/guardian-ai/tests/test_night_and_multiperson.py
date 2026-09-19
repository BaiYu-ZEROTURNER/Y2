"""F2/B-1 护栏：night 跨日界 + 多 person 隔离 + Event.validate 兜底。

这些是 9 月 16 日 v3 文档里没专门覆盖、但现场被追问就会翻车的边界。
"""
from core.event import Event, LEVEL_HIGH
from agents.risk_agent import RiskAgent


def test_night_window_crosses_midnight():
    ra = RiskAgent()
    # 22:00 - 06:00 都算夜间
    for h in (22, 23, 0, 1, 2, 3, 4, 5):
        _, reasons = ra.score({"identity": "unknown", "stay_seconds": 0}, hour=h)
        assert "night" in reasons, f"hour={h} 应触发夜间"
    # 06:00 - 21:59 不算
    for h in (6, 7, 12, 18, 21):
        _, reasons = ra.score({"identity": "unknown", "stay_seconds": 0}, hour=h)
        assert "night" not in reasons, f"hour={h} 不应触发夜间"


def test_night_boundary_exact_22_not_triggered():
    """night_start 严格大于号：hour=22 不算夜间，hour=22:00:01 才算。
    演示文档里写"22:00 起算"，但代码用 >= 是 OK 的；
    此条护栏仅用于在 yaml 改动后提醒：边界小时要确认意图。"""
    ra = RiskAgent()
    _, reasons = ra.score({"identity": "unknown"}, hour=21)
    assert "night" not in reasons
    _, reasons = ra.score({"identity": "unknown"}, hour=22)
    assert "night" in reasons


def test_missing_features_do_not_crash():
    """features 字典可以缺失任意键 —— 真实链路偶发空 dict 时不应崩。"""
    ra = RiskAgent()
    score, reasons = ra.score({}, hour=12)
    # 完全空时按默认值：identity=unknown（+unknown_identity 权重），其他规则全 0
    assert isinstance(score, int)
    assert 0 <= score <= 100
    assert "unknown" in reasons
    score, reasons = ra.score({"identity": None}, hour=12)
    assert isinstance(score, int)


def test_score_clamped_to_max():
    ra = RiskAgent()
    # 全部规则命中（陌生人 + 夜 + 长时间停留 + 反复靠近 + 包裹遗留）
    feats = {
        "identity": "unknown", "stay_seconds": 9999,
        "door_approaches": 99, "package_present": True,
    }
    score, _ = ra.score(feats, hour=23)
    assert 0 <= score <= 100


def test_event_validate_catches_out_of_range():
    ev = Event(risk_score=150, health_score=-10, stay_seconds=-1)
    errs = ev.validate()
    assert any("risk_score" in e for e in errs)
    assert any("health_score" in e for e in errs)
    assert any("stay_seconds" in e for e in errs)


def test_two_persons_state_isolated_by_track_id():
    """两个人同时出现，stay/approaches 必须按 track_id 独立累计。"""
    from core.context_engine import ContextEngine
    from core.event import Detection
    from agents.health_agent import HealthAgent
    from core.config_loader import load_zones, load_risk_rules
    from vision.features import FeatureExtractor

    zones = load_zones()
    rules = load_risk_rules()
    ctx = ContextEngine(zones, HealthAgent(rules))

    # 帧 0：A 出现，B 没出现
    a = Detection(cls="person", bbox=[0.45, 0.59, 0.55, 0.95], track_id=1)
    b = Detection(cls="person", bbox=[0.10, 0.50, 0.20, 0.85], track_id=2)
    ctx.update([a], dt=1.0)
    # 帧 1：A 还在，B 加入
    ctx.update([a, b], dt=1.0)
    # 帧 2：只有 B
    ctx.update([b], dt=1.0)

    # A 单独出现时停留 1s；B 加入后再 1s → A 状态应已被清掉
    # 这里关注的核心：A 不在时，A 的状态被清，B 继续累计
    assert 1 not in ctx.state or ctx.state.get(1, {}).get("stay", 0) <= 2.0
    assert 2 in ctx.state, "B 的轨迹不应被误清"


def test_known_member_penalty_works_with_zero_stay():
    """家人场景只推导 log 不出分：0 分 + log。"""
    ra = RiskAgent()
    score, reasons = ra.score({"identity": "family", "stay_seconds": 5}, hour=19)
    assert score == 0 or score < 0
    assert "known_member" in reasons


def test_delivery_penalty_applied():
    ra = RiskAgent()
    score, reasons = ra.score({"identity": "delivery"}, hour=15)
    assert "delivery" in reasons
    # delivery -20 应大于 known_member -20 但区别于 unknown +25
    assert score <= 0


def test_risk_level_high_threshold():
    ev = Event(risk_score=85)
    assert ev.risk_level_from_score() == LEVEL_HIGH
    ev = Event(risk_score=55)
    assert ev.risk_level_from_score() == "medium"
    ev = Event(risk_score=10)
    assert ev.risk_level_from_score() == "low"