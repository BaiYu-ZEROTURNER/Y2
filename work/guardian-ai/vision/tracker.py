"""目标跟踪：为 person 维持稳定 person_id 与轨迹（IoU 朴素匹配，无需训练）。

ByteTrack / DeepSORT 是赛题推荐方案；这里给出一个与 schema 兼容、可替换的轻量实现，
保证在无重依赖时也能跑通闭环，后续可换成 DeepSORT 而不改对外接口。
"""
from __future__ import annotations

from collections import defaultdict
from typing import List

from core.event import Detection


def _iou(a: List[float], b: List[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


class Tracker:
    def __init__(self, iou_thresh: float = 0.3, max_lost: int = 30):
        self.iou_thresh = iou_thresh
        self.max_lost = max_lost
        self._next_id = 1
        self._active: dict = {}          # track_id -> {"bbox", "lost"}
        self._trajectories: dict = defaultdict(list)

    def update(self, detections: List[Detection]) -> List[Detection]:
        """为 person 检测分配/维持 track_id，并维护轨迹；返回带 track_id 的检测。"""
        persons = [d for d in detections if d.cls == "person"]
        matched = set()
        out: List[Detection] = []

        # 1) 与已有轨迹做 IoU 匹配
        for d in persons:
            best_id, best_iou = -1, self.iou_thresh
            for tid, st in self._active.items():
                iou = _iou(d.bbox, st["bbox"])
                if iou > best_iou:
                    best_iou, best_id = iou, tid
            if best_id != -1:
                self._active[best_id] = {"bbox": d.bbox, "lost": 0}
                d.track_id = best_id
                matched.add(best_id)
                out.append(d)
            else:
                tid = self._next_id
                self._next_id += 1
                self._active[tid] = {"bbox": d.bbox, "lost": 0}
                d.track_id = tid
                out.append(d)

        # 2) 未匹配到的轨迹计为 lost，超阈值则删除
        for tid in list(self._active.keys()):
            if tid not in matched:
                self._active[tid]["lost"] += 1
                if self._active[tid]["lost"] > self.max_lost:
                    del self._active[tid]

        # 3) 包裹检测透传（不参与 person 跟踪）
        for d in detections:
            if d.cls == "package":
                out.append(d)

        # 4) 维护轨迹（取 bbox 中心）
        for d in out:
            if d.cls == "person":
                cx = (d.bbox[0] + d.bbox[2]) / 2
                cy = (d.bbox[1] + d.bbox[3]) / 2
                self._trajectories[d.track_id].append((cx, cy))
        return out

    def trajectory(self, track_id: int) -> List[tuple]:
        return list(self._trajectories.get(track_id, []))
