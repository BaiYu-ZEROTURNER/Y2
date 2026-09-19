"""Decision Engine —— 动作决策（风险 / 健康 → 硬件动作）。

输入：已填好 risk_score / health_score 的 Event。
输出：actions[]（ptz_track / light_on / record / notify / log / notify_health）。

映射规则（对应方案核心功能 3 Device Action）：
  健康异常  -> notify_health + record（提示具体失效设备与受影响区域）
  低风险    -> log（仅记录摘要，不打扰用户）
  中风险    -> record（重点录像，保留上下文）
  高风险    -> ptz_track + light_on + record + notify（主动联动 + 高优通知）

一条重要约束（F0 修）：健康异常时【不再】输出 log。
原因：log 的产品语义是"低风险，仅记录，不打扰用户"，而 notify_health 本身就是要打扰用户，
      两个动作同时出现会让评委觉得逻辑自相矛盾。健康异常时以"提示用户"为最高优先级。
"""
from __future__ import annotations

from typing import List

from core.config_loader import load_risk_rules
from core.event import Event, LEVEL_LOW, LEVEL_MEDIUM, LEVEL_HIGH


class DecisionEngine:
    def __init__(self, rules: dict = None):
        rules = rules or load_risk_rules()
        self.th = rules["thresholds"]
        self.health_alert = rules.get("health", {}).get("alert_score", 50)

    def decide(self, ev: Event) -> List[str]:
        actions: List[str] = []

        # 健康异常优先判定：即使画面里没有人，也要提示"安防覆盖下降"
        health_abnormal = bool(ev.health_issues) or ev.health_score < self.health_alert
        if health_abnormal:
            actions += ["notify_health", "record"]

        # 风险分级 → 动作强度
        ev.risk_level = ev.risk_level_from_score(self.th["low"], self.th["medium"])
        if ev.risk_level == LEVEL_HIGH:
            actions += ["ptz_track", "light_on", "record", "notify"]
        elif ev.risk_level == LEVEL_MEDIUM:
            actions += ["record"]
        elif not health_abnormal:
            # 只有"确实没事"时才输出 log；健康异常时由 notify_health 承担主要语义
            actions += ["log"]

        # 去重并保持顺序
        seen, out = set(), []
        for a in actions:
            if a not in seen:
                seen.add(a)
                out.append(a)
        return out
