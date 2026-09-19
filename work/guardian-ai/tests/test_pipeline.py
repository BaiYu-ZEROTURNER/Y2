"""端到端链路测试：MockDevice -> Detector -> Tracker -> ContextEngine -> Risk/Decision。

验证四类场景在无摄像头/SDK 下也能产出符合方案预期的风险/健康结果。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config_loader import load_risk_rules, load_zones          # noqa: E402
from core.context_engine import ContextEngine                       # noqa: E402
from core.decision_engine import DecisionEngine                     # noqa: E402
from agents.risk_agent import RiskAgent                             # noqa: E402
from agents.health_agent import HealthAgent                         # noqa: E402
from vision.detector import Detector                                # noqa: E402
from vision.tracker import Tracker                                   # noqa: E402
from adapters.mock_device import MockDevice                         # noqa: E402


def _build():
    rules = load_risk_rules()
    zones = load_zones()
    return {
        "detector": Detector(), "tracker": Tracker(),
        "context": ContextEngine(zones, HealthAgent(rules)),
        "risk": RiskAgent(rules), "decision": DecisionEngine(rules),
        "mock": MockDevice(),
    }


def _run(p, scenario):
    p["context"].reset()
    last = None
    for fr in p["mock"].scenario_frames(scenario):
        dets = p["detector"].detect(injected=fr["detections"])
        tracked = p["tracker"].update(dets)
        ev = p["context"].update(
            tracked, dt=1.0, hour=fr["hour"], identity=fr["identity"],
            package_present=fr["package_present"], stats=fr["stats"], scenario=fr["scenario"],
        )
        ev.risk_score, ev.risk_reasons = p["risk"].score(ev.to_dict(), hour=fr["hour"])
        ev.actions = p["decision"].decide(ev)
        last = ev
    return last


def test_family_low():
    ev = _run(_build(), "family")
    assert ev.risk_level in ("low", "medium")
    assert "notify" not in ev.actions


def test_loiter_high():
    ev = _run(_build(), "loiter")
    assert ev.risk_level == "high"
    assert "ptz_track" in ev.actions and "notify" in ev.actions


def test_occlusion_health():
    ev = _run(_build(), "occlusion")
    assert ev.health_issues and "obstructed" in ev.health_issues
    assert ev.health_score <= 40
    assert "notify_health" in ev.actions


def test_event_schema_valid():
    ev = _run(_build(), "delivery")
    assert ev.validate() == []
    # 固定字段全部存在
    for k in ev.SCHEMA_FIELDS:
        assert k in ev.to_dict(schema_only=True)
