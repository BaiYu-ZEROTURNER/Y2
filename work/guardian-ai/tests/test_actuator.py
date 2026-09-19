"""Actuator 单元测试。

覆盖：
  - ACTION_REGISTRY 与 decision_engine 输出对齐
  - 真实设备不可用时自动降级
  - notify / log 写本地即可视为成功
  - 异常设备（method 抛错）不会让上层崩
  - call 把结果写回 ev.actuator_log（页面"动作日志区"取数点）
"""
from core.actuator import Actuator, ACTION_REGISTRY
from core.event import Event
from core.decision_engine import DecisionEngine


def test_registry_matches_decision_outputs():
    """ACTION_REGISTRY 必须覆盖 decision_engine 全部输出，否则调用会卡在 unknown。"""
    de = DecisionEngine()
    actions_emitted = set()
    for ev in (
        Event(risk_score=10),                                  # log
        Event(risk_score=45),                                  # record
        Event(risk_score=85),                                  # ptz/light/record/notify
        Event(risk_score=0, health_issues=["obstructed"]),     # notify_health/record
    ):
        actions_emitted.update(de.decide(ev))
    missing = actions_emitted - ACTION_REGISTRY.keys()
    assert not missing, f"decision_engine 输出未在 ACTION_REGISTRY 注册: {missing}"


def test_notify_succeeds_without_device():
    ac = Actuator()
    res = ac.call(Event(risk_score=88), ["notify"])
    assert res[0].ok is True
    assert res[0].fallback_used is False


def test_ptz_uses_mock_when_no_device():
    """真设备不可用时 → 调用 MockDevice → 演示观感上"动作已执行"。"""
    ac = Actuator()
    res = ac.call(Event(risk_score=88, camera_id="cam_01"), ["ptz_track"])
    assert res[0].ok is True
    assert res[0].fallback_used is True   # 但标注为"走了 mock"


def test_event_log_written():
    ev = Event(risk_score=88)
    ac = Actuator()
    ac.call(ev, ["record", "notify"])
    assert len(ev.actuator_log) == 2
    assert {r["action"] for r in ev.actuator_log} == {"record", "notify"}


def test_unknown_action_marked_failed():
    ac = Actuator()
    res = ac.call(Event(), ["non_existent_action"])
    assert res[0].ok is False
    assert "unknown action" in res[0].error


def test_device_exception_isolated():
    """单个 action 抛异常不能影响后续 action；真设备抛错时 fallback 到 mock。"""

    class BoomDevice:
        def is_available(self):  return True
        def light_on(self, *_): raise RuntimeError("sdk down")

    ac = Actuator(device=BoomDevice())
    res = ac.call(Event(camera_id="cam_01"), ["light_on", "log"])
    # light_on 真设备抛错 → Actuator 把它当成 ok=False 并尝试 MockDevice → Mock 成功
    # （这里 ok 视真设备是否返回 True 决定；本测试只断言不崩、log 仍成功）
    assert res[1].ok is True           # log 仍成功


def test_slow_device_marks_timeout():
    """真实设备响应 > timeout_sec 时标记失败（演示现场设备万一掉链子不卡死）。"""
    import time as _t

    class SlowDevice:
        def is_available(self): return True
        def light_on(self, *_):
            _t.sleep(0.4)            # 模拟慢响应
            return True

    ac = Actuator(device=SlowDevice(), timeout_sec=0.1)
    res = ac.call(Event(camera_id="cam_01"), ["light_on"])
    assert res[0].ok is False         # 因超时被判失败
    assert res[0].elapsed_ms >= 100


def test_invalid_bbox_does_not_crash_features():
    """bbox 越界 / 形状异常不应让 ROI 判定崩。"""
    from vision.features import FeatureExtractor
    from core.config_loader import load_zones
    from core.event import Detection

    fx = FeatureExtractor(load_zones())
    # 极端 bbox
    for bb in ([-1, -1, 0.5, 0.5], [1.5, 0, 2, 1], [0], [0, 0, 0, 0]):
        d = Detection(cls="person", bbox=bb, track_id=1)
        z = fx.zone_of(d)            # 不抛异常即可
        assert isinstance(z, str)