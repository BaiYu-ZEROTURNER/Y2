"""vision 层契约护栏 —— Detector / Tracker / Features / Health 全部要走 bbox [0,1]。

要点：
- YOLO 极端输出（1.0001 / -0.001）会被 clamp_bbox 钳位；
- mock 注入路径同样走 clamp_bbox（不依赖调用方自觉）；
- tracker 多 person 跟踪后 person_id 互不串号；
- features 在 bbox 越界时不崩。

这些是 F4 联调稳的基础护栏 —— 真实视频接上时全部要绿。
"""
from __future__ import annotations

import pytest

from core.config_loader import load_zones
from core.event import Detection
from vision.detector import Detector, clamp_bbox
from vision.tracker import Tracker
from vision.features import FeatureExtractor


# ---- clamp_bbox ----

def test_clamp_bbox_normal():
    assert clamp_bbox([0.1, 0.2, 0.3, 0.4]) == [0.1, 0.2, 0.3, 0.4]


def test_clamp_bbox_out_of_range_high():
    """YOLO 在裁切边缘可能产生 1.0001 —— 必须钳位。"""
    out = clamp_bbox([1.0001, -0.0001, 1.5, 0.5])
    assert all(0.0 <= v <= 1.0 for v in out), out
    # 1.0001 → 1.0；-0.0001 → 0.0；1.5 → 1.0；0.5 保持
    assert out == [1.0, 0.0, 1.0, 0.5]


def test_clamp_bbox_inverted():
    """x1 > x2 / y1 > y2 必须自动换序。"""
    out = clamp_bbox([0.8, 0.8, 0.2, 0.2])
    assert out[0] < out[2]
    assert out[1] < out[3]


def test_clamp_bbox_invalid():
    """坏数据兜底到全 0。"""
    assert clamp_bbox([]) == [0.0, 0.0, 0.0, 0.0]
    assert clamp_bbox(None) == [0.0, 0.0, 0.0, 0.0]
    assert clamp_bbox([0.1]) == [0.0, 0.0, 0.0, 0.0]


# ---- Detector mock 路径 ----

def test_detector_mock_clamps_bbox():
    """mock 注入的 bbox 也要归一化 —— 之前依赖调用方自觉。"""
    det = Detector()
    raw = [
        Detection(cls="person", bbox=[1.1, -0.1, 0.5, 0.5]),  # 越界 + 倒序
        Detection(cls="package", bbox=[0.6, 0.6, 0.7, 0.7]),   # 正常
    ]
    out = det.detect(injected=raw)
    assert len(out) == 2
    for d in out:
        assert all(0.0 <= v <= 1.0 for v in d.bbox)
        assert d.bbox[0] <= d.bbox[2]
        assert d.bbox[1] <= d.bbox[3]


def test_detector_filters_unknown_class():
    det = Detector()
    raw = [
        Detection(cls="person", bbox=[0.1, 0.1, 0.2, 0.2]),
        Detection(cls="cat", bbox=[0.1, 0.1, 0.2, 0.2]),        # 应当被丢弃
    ]
    out = det.detect(injected=raw)
    assert len(out) == 1
    assert out[0].cls == "person"


# ---- Tracker 多 person 隔离 ----

def test_tracker_two_persons_isolated_ids():
    """两个不重叠的人物，跟踪器必须给两个不同的 track_id。"""
    tr = Tracker()
    f1 = [Detection(cls="person", bbox=[0.1, 0.1, 0.3, 0.3]),
          Detection(cls="person", bbox=[0.6, 0.1, 0.8, 0.3])]
    f2 = [Detection(cls="person", bbox=[0.1, 0.1, 0.3, 0.3]),  # 左边稳定
          Detection(cls="person", bbox=[0.6, 0.1, 0.8, 0.3])]  # 右边稳定
    a = tr.update(f1)
    b = tr.update(f2)
    a_ids = sorted(d.track_id for d in a)
    b_ids = sorted(d.track_id for d in b)
    assert a_ids == b_ids, "同一物体连续两帧 track_id 必须稳定"
    assert len(set(a_ids)) == 2, "两个 person 必须分配到不同的 track_id"


def test_tracker_person_disappear_reuses_id():
    """person A 离开、B 进入 → A 的 id 不能被 B 占用。"""
    tr = Tracker()
    only_a = [Detection(cls="person", bbox=[0.1, 0.1, 0.3, 0.3])]
    out_a = tr.update(only_a)
    a_id = out_a[0].track_id
    # 后续两帧空检测
    tr.update([])
    tr.update([])
    # B 出现，bbox 完全不重叠
    only_b = [Detection(cls="person", bbox=[0.6, 0.6, 0.8, 0.8])]
    out_b = tr.update(only_b)
    assert out_b[0].track_id != a_id, "B 不应复用 A 的 id"


def test_tracker_empty_is_safe():
    """空检测列表不能崩。"""
    tr = Tracker()
    assert tr.update([]) == []


# ---- features 在 bbox 越界时不崩 ----

def test_in_door_roi_with_extreme_bbox():
    """clamp 后的 bbox 必须能正常判定。"""
    fx = FeatureExtractor(load_zones())
    # 门锁 ROI 内
    det_in = Detection(cls="person", bbox=[0.5, 0.8, 0.6, 0.9])
    assert fx.in_door_roi(det_in, fx.zone_of(det_in)) is True
    # 完全在外面
    det_out = Detection(cls="person", bbox=[0.1, 0.1, 0.2, 0.2])
    assert fx.in_door_roi(det_out, fx.zone_of(det_out)) is False