"""Context Engine —— 聚合上下文。

职责（对应架构图 Context Engine 节点）：
- 调用 Health Agent 得到系统健康分（全局上下文）。
- 跨帧维护每个 person 的停留时长、靠近门锁次数（事件聚合）。
- 将视觉特征 + 健康上下文组装成 Event（风险分由 Risk Agent 后续填充）。
保持 schema 向后兼容：只产出 Event 结构，不附带模型内部对象。
"""
from __future__ import annotations

import time
from typing import List, Optional

from core.event import Event, FrameStats
from vision.features import FeatureExtractor
from agents.health_agent import HealthAgent


class ContextEngine:
    def __init__(self, zones: dict, health_agent: HealthAgent = None):
        self.fx = FeatureExtractor(zones)
        self.health = health_agent or HealthAgent()
        # track_id -> {"stay":秒, "in_door":bool, "approaches":int}
        self.state: dict = {}

    def reset(self):
        self.state.clear()
        self.health._prev = None

    def update(
        self,
        tracked: List,
        dt: float = 1.0,
        hour: int = 20,
        identity: str = "unknown",
        package_present: bool = False,
        frame=None,
        stats: FrameStats = None,
        scenario: str = "",
        camera_id: str = "cam_01",
    ) -> Event:
        h_score, issues = self.health.analyze(frame=frame, stats=stats)

        persons = [d for d in tracked if d.cls == "person"]
        present = set()
        for d in persons:
            present.add(d.track_id)
            st = self.state.get(d.track_id)
            in_door = self.fx.in_door_roi(d, self.fx.zone_of(d))
            if st is None:
                # 新轨迹的冷启动处理：只记录"此刻在不在 ROI 内"，不计数。
                # 原因：人物第一次出现时我们只观察到"他在那里"，并没有观察到"他走了进去"。
                # 若这里默认 in_door=False，第一帧必然被当成一次进入边沿，
                # 会让 door_approaches 虚高 1，并让演示开局就带着 sensitive_roi 加分。
                st = {"stay": 0.0, "in_door": in_door, "approaches": 0}
                self.state[d.track_id] = st
            else:
                if in_door and not st["in_door"]:
                    st["approaches"] += 1   # 真正观测到的"从外进入"边沿
                st["in_door"] = in_door
            st["stay"] += dt

        # 清理已离开的轨迹
        for tid in list(self.state):
            if tid not in present:
                del self.state[tid]

        ev = Event(
            camera_id=camera_id,
            scenario=scenario,
            health_score=h_score,
            health_issues=list(issues),
        )
        if persons:
            primary = persons[0]
            st = self.state[primary.track_id]
            ev.person_id = primary.track_id
            ev.identity = identity
            ev.zone = self.fx.zone_of(primary)
            ev.stay_seconds = int(st["stay"])
            ev.door_approaches = st["approaches"]
            ev.package_present = package_present
        else:
            ev.identity = identity
            ev.zone = "front_door"
            ev.package_present = package_present
        return ev
