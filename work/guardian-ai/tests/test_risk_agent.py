from agents.risk_agent import RiskAgent

ra = RiskAgent()


def test_family_low_risk():
    # 家人 + 白天 + 短停留 -> 负权，应为低风险
    score, reasons = ra.score({
        "identity": "family", "stay_seconds": 3, "door_approaches": 0,
        "package_present": False,
    }, hour=19)
    assert score < 30
    assert "known_member" in reasons


def test_stay_is_progressive():
    """停留必须两档递进加分，不能一次跳到高风险。

    这是现场演示观感的关键：风险分要"爬上去"。
    30s -> long_stay；60s -> 再叠 long_stay_extra。
    """
    base = {"identity": "unknown", "door_approaches": 0, "package_present": False}

    s_short, r_short = ra.score({**base, "stay_seconds": 10}, hour=14)
    s_mid, r_mid = ra.score({**base, "stay_seconds": 35}, hour=14)
    s_long, r_long = ra.score({**base, "stay_seconds": 65}, hour=14)

    assert "long_stay" not in r_short
    assert "long_stay" in r_mid and "long_stay_extra" not in r_mid
    assert "long_stay" in r_long and "long_stay_extra" in r_long
    # 三档分数严格递增，且中间档不直接进入高风险
    assert s_short < s_mid < s_long
    assert s_mid < 60


def test_delivery_is_discounted():
    # 快递身份应降权，即使门口有包裹也不升高风险
    score, reasons = ra.score({
        "identity": "delivery", "stay_seconds": 20, "door_approaches": 1,
        "package_present": True,
    }, hour=15)
    assert score < 30
    assert "delivery" in reasons


def test_sensitive_roi_and_repeat_are_separate_reasons():
    """进入敏感区域（+15）与反复靠近（+15）是两条独立规则，理由要能分开看到。"""
    once, r_once = ra.score({
        "identity": "unknown", "stay_seconds": 5, "door_approaches": 1,
        "package_present": False,
    }, hour=14)
    twice, r_twice = ra.score({
        "identity": "unknown", "stay_seconds": 5, "door_approaches": 2,
        "package_present": False,
    }, hour=14)
    assert "sensitive_roi" in r_once and "repeat_approach" not in r_once
    assert "sensitive_roi" in r_twice and "repeat_approach" in r_twice
    assert twice > once


def test_score_never_raises_on_missing_fields():
    """缺字段不能抛异常——真实链路里 context_engine 可能给不全。"""
    score, _ = ra.score({}, hour=20)
    assert 0 <= score <= 100


def test_loiter_high_risk():
    # 未知 + 夜间 + 停留95s + 靠近3次 -> 高风险
    score, reasons = ra.score({
        "identity": "unknown", "stay_seconds": 95, "door_approaches": 3,
        "package_present": False,
    }, hour=23)
    assert score >= 60
    for r in ("unknown", "night", "long_stay", "repeat_approach"):
        assert r in reasons


def test_unknown_day_short_medium():
    # 未知身份但白天短停留 -> 中等偏低，不触发高风险
    score, _ = ra.score({
        "identity": "unknown", "stay_seconds": 5, "door_approaches": 0,
        "package_present": False,
    }, hour=14)
    assert 0 < score < 60


def test_score_clamped():
    score, _ = ra.score({
        "identity": "unknown", "stay_seconds": 999, "door_approaches": 99,
        "package_present": True,
    }, hour=23)
    assert 0 <= score <= 100
