"""Mock Device —— 无设备时的替代实现（P0 必备）。

按方案《需要自己录制的最小数据集》生成四类演示场景的逐帧输入：
  family    家人经过（正常速度，不停留）
  delivery  快递送件（手持包裹到门口，放下后离开）
  loiter    陌生人夜间徘徊（门口长时间停留 + 反复靠近门锁）
  occlusion 镜头遮挡（画面边缘密度骤降，Health Score 下降）
每帧产出与真实链路同构的结构：Detection 列表 + FrameStats + 场景元数据。
上层（app / 测试）消费方式与实际摄像头完全一致，设备接通后可零改动替换。

同时实现 ACTUATOR_REGISTRY 里的硬件动作（ptz_track / light_on / start_record），
这样 Actuator 调用时不走 fallback 而是真"成功"——演示观感更直接。
"""
from __future__ import annotations

from typing import Dict, Iterator, List

from core.event import Detection, FrameStats

# 门口 door_roi 内部的一个稳定点（归一化），用于"在门口"判定
_DOOR_IN = [0.50, 0.76]
_DOOR_OUT = [0.50, 0.55]   # 门口但不在门锁 ROI 内


def _person(bbox) -> Detection:
    return Detection(cls="person", bbox=list(bbox), confidence=0.9)


def _package(bbox) -> Detection:
    return Detection(cls="package", bbox=list(bbox), confidence=0.85)


class MockDevice:
    SCENARIOS = ("family", "delivery", "loiter", "occlusion")

    # ---- 设备联动（与 ACTUATOR_REGISTRY 对齐）----
    # 真实 SDK 接通时，调用同一组方法名即可零改动替换。
    def ptz_track(self, camera_id: str, target: Dict = None) -> bool:
        """模拟云台转动跟踪目标。返回是否成功。"""
        return True

    def light_on(self, camera_id: str) -> bool:
        return True

    def start_record(self, camera_id: str) -> bool:
        return True

    def is_available(self) -> bool:
        """Mock 始终可用——Actuator 会优先调用真设备，未接时切到 mock。"""
        return True

    def scenario_frames(self, name: str, fps: int = 1) -> Iterator[Dict]:
        name = name.lower()
        if name == "family":
            yield from self._family(fps)
        elif name == "delivery":
            yield from self._delivery(fps)
        elif name == "loiter":
            yield from self._loiter(fps)
        elif name == "occlusion":
            yield from self._occlusion(fps)
        else:
            raise ValueError(f"unknown scenario: {name}")

    # ---- 家人经过：第 2 帧出现在门口外，第 3 帧走过，之后离开 ----
    def _family(self, fps):
        meta = {"identity": "family", "package_present": False, "hour": 19, "scenario": "family"}
        for i in range(5):
            if i == 2:
                dets = [_person([0.45, 0.50, 0.55, 0.85])]
            else:
                dets = []
            yield {"detections": dets, "stats": FrameStats(brightness=120, edge_density=0.25, frame_diff=8), **meta}

    # ---- 快递送件：带包裹到门口，放下后离开，包裹遗留 ----
    def _delivery(self, fps):
        meta = {"identity": "delivery", "package_present": False, "hour": 15, "scenario": "delivery"}
        for i in range(6):
            if i in (1, 2):
                dets = [_person([0.46, 0.55, 0.56, 0.86]), _package([0.58, 0.78, 0.66, 0.90])]
            elif i >= 3:
                # 人离开，包裹遗留
                dets = [_package([0.58, 0.78, 0.66, 0.90])]
                meta = {**meta, "package_present": True}
            else:
                dets = []
            yield {"detections": dets, "stats": FrameStats(brightness=130, edge_density=0.22, frame_diff=7), **meta}

    # ---- 陌生人夜间徘徊：长时间停留 + 反复靠近门锁 ----
    def _loiter(self, fps):
        meta = {"identity": "unknown", "package_present": False, "hour": 23, "scenario": "loiter"}
        n = 70  # 演示时长（贴近方案示例 95s；> long_stay_seconds=60 才能触发 long_stay）
        # 在门锁 ROI 边界附近小幅摆动：in=ROI 内，out=ROI 上方（仍在门口区域）。
        # 两框 IoU 保持 >0.3，使朴素 IoU 跟踪器不丢 id，从而正确累计停留与靠近次数。
        for i in range(n):
            at_door = (i % 4) < 2
            if at_door:
                dets = [_person([0.45, 0.59, 0.55, 0.95])]   # 中心 (0.50,0.77) 在 door_roi 内
            else:
                dets = [_person([0.45, 0.44, 0.55, 0.80])]   # 中心 (0.50,0.62) 在门口但不在 door_roi
            yield {"detections": dets, "stats": FrameStats(brightness=30, edge_density=0.18, frame_diff=5), **meta}

    # ---- 镜头遮挡：画面边缘密度骤降，触发 obstructed ----
    def _occlusion(self, fps):
        meta = {"identity": "unknown", "package_present": False, "hour": 20, "scenario": "occlusion"}
        for i in range(6):
            # 第 2 帧起遮挡（边缘密度极低），模拟纸张/手掌遮镜头
            if i < 2:
                stats = FrameStats(brightness=120, edge_density=0.25, frame_diff=6)
            else:
                stats = FrameStats(brightness=110, edge_density=0.01, frame_diff=1.0)
            yield {"detections": [], "stats": stats, **meta}
