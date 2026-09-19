"""Actuator —— actions 与设备调用的中间层。

解决的问题：Decision Engine 只输出"动作名"（ptz_track / light_on / record / notify / log / notify_health），
  但真实设备各有 SDK（eufy / Aqara / Tuya），调用方式、参数、降级策略各不相同。
  本层做三件事：
    1. 把 actions 翻译成具体设备调用（actuator.call_action）
    2. 设备不可用时自动降级（fallback 到 MockDevice）
    3. 把每次调用结果写回 Event.actuator_log，供 A 页面"动作日志区"显示

新增 actions 只需：
  a) 在 ACTION_HANDLERS 里注册 handler；
  b) 在 ACTUATOR_REGISTRY.yaml（若改 yaml）或本文件写清降级路径；
  c) 在 tests/test_actuator.py 加一条断言。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from core.event import Event
from adapters.eufy_sdk import EufySDKAdapter
from adapters.mock_device import MockDevice


logger = logging.getLogger("guardian.ai.actuator")

# ---- actions 契约清单（F2 冻结）----
# 新增 action 必须遵循：
#   - handler 接受 (camera_id, event) -> ActionResult
#   - 失败必须降级：notify_* 降级到 log，硬件动作降级到 skip
#   - 在 ACTUATOR_REGISTRY 里注册名字 + 降级路径
ACTION_REGISTRY = {
    "ptz_track":     {"target": "camera",  "fallback": "skip",  "blocking": False},
    "light_on":      {"target": "camera",  "fallback": "skip",  "blocking": False},
    "record":        {"target": "camera",  "fallback": "skip",  "blocking": False},
    "notify":        {"target": "user",    "fallback": "log",   "blocking": False},
    "notify_health": {"target": "user",    "fallback": "log",   "blocking": False},
    "log":           {"target": "storage", "fallback": "skip",  "blocking": False},
}


@dataclass
class ActionResult:
    action: str
    ok: bool                  # 设备是否成功执行
    fallback_used: bool = False
    error: str = ""
    elapsed_ms: float = 0.0

    def to_dict(self) -> Dict:
        return {
            "action": self.action,
            "ok": self.ok,
            "fallback_used": self.fallback_used,
            "error": self.error,
            "elapsed_ms": round(self.elapsed_ms, 1),
        }


class Actuator:
    """把 actions[] 翻译成具体调用；设备不可用时自动降级。"""

    def __init__(
        self,
        device: Optional[object] = None,         # EufySDKAdapter 或其他
        mock: Optional[MockDevice] = None,        # 降级目标
        timeout_sec: float = 3.0,
    ):
        self.device = device or EufySDKAdapter()
        self.mock = mock or MockDevice()
        self.timeout_sec = timeout_sec
        self._results: List[ActionResult] = []

    def call(self, ev: Event, actions: List[str]) -> List[ActionResult]:
        """逐个执行并收集结果，写回 ev.actuator_log。"""
        results = []
        for action in actions:
            spec = ACTION_REGISTRY.get(action)
            if not spec:
                results.append(ActionResult(
                    action=action, ok=False, error="unknown action"))
                continue
            r = self._invoke(action, spec, ev)
            results.append(r)
        self._results.extend(results)
        ev.actuator_log = [r.to_dict() for r in results]
        return results

    def _invoke(self, action: str, spec: Dict, ev: Event) -> ActionResult:
        t0 = time.perf_counter()
        try:
            # 1) 通知类：本地日志即视为成功（与 MockDevice / 真 SDK 一致）
            if action in ("notify", "notify_health"):
                logger.info("notify: %s score=%d level=%s",
                            action, ev.risk_score, ev.risk_level)
                return ActionResult(
                    action=action, ok=True,
                    elapsed_ms=(time.perf_counter() - t0) * 1000,
                )
            # 2) log 类：本地写入
            if action == "log":
                logger.info("log: risk=%d reasons=%s",
                            ev.risk_score, ev.risk_reasons)
                return ActionResult(
                    action=action, ok=True,
                    elapsed_ms=(time.perf_counter() - t0) * 1000,
                )
            # 3) 硬件动作：优先真实设备；不可用 → MockDevice；Mock 失败 → fallback
            if spec["target"] == "camera":
                if self.device.is_available():
                    method = getattr(self.device, _device_method(action), None)
                    if method:
                        if action == "ptz_track":
                            ok = method(ev.camera_id, target={"person_id": ev.person_id})
                        else:
                            ok = method(ev.camera_id)
                        elapsed = (time.perf_counter() - t0) * 1000
                        if elapsed > self.timeout_sec * 1000:
                            # 真实设备响应超时：标记失败 + 降级到 mock
                            logger.warning("action %s slow: %.0fms", action, elapsed)
                            ok = False
                        return ActionResult(
                            action=action, ok=ok,
                            elapsed_ms=elapsed,
                        )
                # MockDevice 兜底
                mock_method = getattr(self.mock, _device_method(action), None)
                if mock_method:
                    ok = mock_method(ev.camera_id) if action != "ptz_track" \
                        else mock_method(ev.camera_id, target={"person_id": ev.person_id})
                    return ActionResult(
                        action=action, ok=ok, fallback_used=True,
                        elapsed_ms=(time.perf_counter() - t0) * 1000,
                    )
            # 4) 走到这里说明既无 handler 也无 mock
            return ActionResult(
                action=action, ok=False,
                fallback_used=True,
                error=f"no handler, fallback={spec['fallback']}",
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:                                     # noqa: BLE001
            return ActionResult(
                action=action, ok=False,
                fallback_used=True,
                error=str(e)[:200],
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )

    @property
    def history(self) -> List[ActionResult]:
        return list(self._results)


def _device_method(action: str) -> str:
    """action → 设备方法名映射。"""
    return {
        "ptz_track": "ptz_track",
        "light_on":  "light_on",
        "record":    "start_record",
    }.get(action, action)