"""规则表一致性护栏（B 专属）。

背景：规则同时存在于两个地方——
  1) config/risk_rules.yaml              （现场调参用，B 手改）
  2) core/config_loader.py 的 _FALLBACK_RISK（pyyaml 缺失时的兜底）
两处如果不一致，会出现"现场改了 yaml 但没生效"或"没装 pyyaml 时分数不一样"的诡异现象。
本测试逐字段比对两处，只要漂移就红灯。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_loader import (          # noqa: E402
    load_risk_rules, load_zones, _FALLBACK_RISK,
)


def test_yaml_matches_fallback():
    """yaml 与内置兜底必须完全一致。"""
    assert load_risk_rules() == _FALLBACK_RISK


def test_weights_cover_all_reasons():
    """每个风险理由都要有对应权重，否则评分会静默丢分。"""
    w = load_risk_rules()["weights"]
    for key in ("unknown_identity", "night", "long_stay", "long_stay_extra",
                "sensitive_roi", "repeat_approach", "package_left",
                "known_member", "delivery_like"):
        assert key in w, f"缺少权重项：{key}"


def test_dead_config_removed():
    """thresholds.high 是历史死配置，DecisionEngine 从不读取，不应再出现。"""
    th = load_risk_rules()["thresholds"]
    assert set(th) == {"low", "medium"}
    assert th["low"] < th["medium"]


def test_thresholds_match_event_levels():
    """Event 内存兜底的分界必须和 yaml 一致，否则页面等级和分数会对不上。"""
    from core.event import Event
    th = load_risk_rules()["thresholds"]
    assert Event(risk_score=th["low"] - 1).risk_level_from_score(th["low"], th["medium"]) == "low"
    assert Event(risk_score=th["low"]).risk_level_from_score(th["low"], th["medium"]) == "medium"
    assert Event(risk_score=th["medium"]).risk_level_from_score(th["low"], th["medium"]) == "high"


def test_zones_have_front_door_and_door_roi():
    """A 的 ROI 归属依赖 zones.json，front_door 和 door_roi 必须存在。"""
    zones = load_zones()["zones"]
    assert "front_door" in zones
    assert len(zones["front_door"]["polygon"]) >= 3
    assert len(zones["front_door"]["door_roi"]) >= 3
