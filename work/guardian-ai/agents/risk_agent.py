"""Risk Agent —— 规则式事件风险判断（可解释、不依赖大模型）。

输入：结构化事件特征（来自 core/context_engine.py 聚合后的 Event，或 mock 注入）。
输出：(risk_score 0-100, risk_reasons[])。

设计要点：
- 全部规则来自 config/risk_rules.yaml，改 yaml 就能现场调 Demo，不动本文件。
- 每一条命中都会在 risk_reasons 里留下一个字符串，
  所以评委追问"为什么是 85 分"时可以直接逐条念出来。
- 停留时长采用【递进式】加分：>30s 加第一档，>60s 再加第二档。
  这样演示时风险分是"爬上去"的，而不是一帧从 0 跳到高分——
  这一点直接影响现场观感，改动前请先确认。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from core.config_loader import load_risk_rules

# 已知身份：这些身份不按"陌生人"计分，并触发降权规则
_KNOWN_IDENTITIES = ("known", "family")
_DELIVERY_IDENTITIES = ("delivery",)


class RiskAgent:
    def __init__(self, rules: Dict = None):
        self.rules = rules or load_risk_rules()
        self.w = self.rules["weights"]
        p = self.rules["params"]
        self.stay_long = p["stay_long_seconds"]
        self.stay_very_long = p["stay_very_long_seconds"]
        self.roi_min = p["sensitive_roi_min"]
        self.repeat_n = p["repeat_approach_min"]
        self.max_score = self.rules.get("max_score", 100)
        t = self.rules["time"]
        self.night_start, self.night_end = t["night_start"], t["night_end"]

    def _is_night(self, hour: int) -> bool:
        return hour >= self.night_start or hour < self.night_end

    def score(self, features: Dict, hour: int = 20) -> Tuple[int, List[str]]:
        """对单条事件特征评分。

        features 需要包含（缺失按默认值处理，不会抛异常）：
            person_id, identity, stay_seconds, door_approaches, package_present
        hour 用于夜间判定（demo 可注入，真实链路取当前系统时间）。

        边界：当 features 显式标注 person_id == -1（画面无人）时，身份 / 停留 / 靠近
        三类规则全部不命中 —— 把"画面消失"与"陌生人进入"区分清楚，避免 health 异常
        期间 risk_score 被人为抬高。
        """
        score = 0
        reasons: List[str] = []

        # ---- 边界：画面无人 ----
        # person_id 显式为 -1 才早退；不传 / 传 0 / 传正整数都视为"画面有人但未明确身份"
        if "person_id" in features and features["person_id"] == -1:
            return 0, []

        # ---- 规则 1：身份 ----
        identity = features.get("identity", "unknown")
        if identity == "unknown":
            score += self.w["unknown_identity"]
            reasons.append("unknown")
        elif identity in _DELIVERY_IDENTITIES:
            score += self.w["delivery_like"]
            reasons.append("delivery")
        elif identity in _KNOWN_IDENTITIES:
            score += self.w["known_member"]
            reasons.append("known_member")

        # ---- 规则 2：夜间 ----
        if self._is_night(hour):
            score += self.w["night"]
            reasons.append("night")

        # ---- 规则 3：停留时长（两档递进）----
        stay = features.get("stay_seconds", 0) or 0
        if stay >= self.stay_long:
            score += self.w["long_stay"]
            reasons.append("long_stay")
        if stay >= self.stay_very_long:
            score += self.w["long_stay_extra"]
            reasons.append("long_stay_extra")

        # ---- 规则 4：进入敏感区域（门锁 ROI）----
        approaches = features.get("door_approaches", 0) or 0
        if approaches >= self.roi_min:
            score += self.w["sensitive_roi"]
            reasons.append("sensitive_roi")

        # ---- 规则 5：反复靠近门锁 ----
        if approaches >= self.repeat_n:
            score += self.w["repeat_approach"]
            reasons.append("repeat_approach")

        # ---- 规则 6：门口有包裹且身份异常（疑似遗留 / 异常投递）----
        if features.get("package_present") and identity not in (
            _DELIVERY_IDENTITIES + _KNOWN_IDENTITIES
        ):
            score += self.w["package_left"]
            reasons.append("package_left")

        score = max(0, min(self.max_score, score))
        return int(score), reasons
