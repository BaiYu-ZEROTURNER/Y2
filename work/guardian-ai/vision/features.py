"""视觉特征提取：ROI 归属、停留时长、靠近门锁次数、包裹存在。

输入：带 track_id 的检测（来自 tracker）+ 区域配置 + 时间戳序列。
输出：结构化特征 dict，供 Risk Agent 评分、Context Engine 聚合。
坐标均为归一化 0-1；点在多边形内用射线法判断。
"""
from __future__ import annotations

from typing import Dict, List

from core.event import Detection


def _point_in_polygon(pt: List[float], poly: List[List[float]]) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi) + xi):
            inside = not inside
        j = i
    return inside


def _center(det: Detection) -> List[float]:
    """返回 bbox 中心点（归一化）。

    bbox 形状异常时兜底到 (0, 0)：
    - 长度 < 4 → 视为无效，回到画面左上
    - 任意值 < 0 / > 1 → clamp 到 [0, 1]（避免多边形判定跑飞）
    """
    bb = det.bbox or [0, 0, 0, 0]
    if len(bb) < 4:
        return [0.0, 0.0]
    x1, y1, x2, y2 = bb[:4]
    cx = max(0.0, min(1.0, (x1 + x2) / 2))
    cy = max(0.0, min(1.0, (y1 + y2) / 2))
    return [cx, cy]


class FeatureExtractor:
    def __init__(self, zones: Dict):
        self.zones = zones.get("zones", zones)

    def zone_of(self, det: Detection) -> str:
        c = _center(det)
        for name, z in self.zones.items():
            if _point_in_polygon(c, z.get("polygon", [])):
                return name
        return "outside"

    def in_door_roi(self, det: Detection, zone_name: str) -> bool:
        z = self.zones.get(zone_name, {})
        return _point_in_polygon(_center(det), z.get("door_roi", []))

    def extract(
        self,
        tracked: List[Detection],
        stay_seconds: int,
        door_approaches: int,
        package_present: bool,
        identity: str = "unknown",
        zone_override: str = None,
    ) -> Dict:
        """聚合单事件特征。停留/靠近次数由 Context Engine 跨帧累计后传入。"""
        person = next((d for d in tracked if d.cls == "person"), None)
        zone = zone_override or (self.zone_of(person) if person else "front_door")
        return {
            "person_id": person.track_id if person else -1,
            "identity": identity,
            "zone": zone,
            "stay_seconds": stay_seconds,
            "door_approaches": door_approaches,
            "package_present": package_present,
        }
