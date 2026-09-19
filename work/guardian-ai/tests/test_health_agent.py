"""Health Agent 行为护栏 —— 三种失效模式必须稳定、可观测。

三种模式（按优先级）：
  1) black_screen   黑屏（亮度 < 阈值）→ black_score
  2) obstructed     遮挡（边缘密度 < 阈值）→ occlusion_score
  3) frozen         冻结（与上一帧差 < 阈值）→ freeze_score
优先级：黑屏 → 遮挡 → 冻结，命中即返回，不继续判定。
"""
from __future__ import annotations

import pytest

from core.config_loader import load_risk_rules
from core.event import FrameStats
from agents.health_agent import HealthAgent


@pytest.fixture
def ha():
    return HealthAgent(load_risk_rules())


def test_normal_frame_full_score(ha):
    """正常画面：亮度高 + 边缘密度合理 + frame_diff 充足 → 接近满血。"""
    score, issues = ha.analyze(stats=FrameStats(
        brightness=120, edge_density=0.25, frame_diff=8
    ))
    assert score >= 96
    assert issues == []


def test_black_screen_priority(ha):
    """黑屏优先于遮挡 —— brightness 极低时直接报 black_screen。"""
    score, issues = ha.analyze(stats=FrameStats(
        brightness=2, edge_density=0.001, frame_diff=0.1
    ))
    assert "black_screen" in issues
    assert score == ha.rules["black_score"]


def test_obstruction(ha):
    """边缘密度过低 → 遮挡。"""
    score, issues = ha.analyze(stats=FrameStats(
        brightness=120, edge_density=0.01, frame_diff=5
    ))
    assert "obstructed" in issues
    assert score == ha.rules["occlusion_score"]


def test_frozen_only_after_two_frames(ha):
    """冻结至少需要两帧对比 —— 第一帧不应直接判定。"""
    f1 = FrameStats(brightness=120, edge_density=0.25, frame_diff=0.0)
    f2 = FrameStats(brightness=120, edge_density=0.25, frame_diff=0.1)
    # 第一帧
    s1, i1 = ha.analyze(stats=f1)
    assert "frozen" not in i1
    # 第二帧 diff 极低 → frozen
    s2, i2 = ha.analyze(stats=f2)
    assert "frozen" in i2
    assert s2 == ha.rules["freeze_score"]


def test_no_input_is_neutral(ha):
    """既无 frame 也无 stats → 返回中性分数（不误报）。"""
    score, issues = ha.analyze(frame=None, stats=None)
    assert score == 100
    assert issues == []


def test_stats_persistence_across_calls(ha):
    """agent 会把 prev stats 留在 self._prev；连续调用时 frozen 判定不丢。"""
    # 第一帧：普通
    ha.analyze(stats=FrameStats(brightness=120, edge_density=0.25, frame_diff=8))
    # 第二帧：frame_diff 极低 → frozen
    score, issues = ha.analyze(stats=FrameStats(
        brightness=120, edge_density=0.25, frame_diff=0.1
    ))
    assert "frozen" in issues


def test_health_score_range(ha):
    """任何输入下 score 都在 [0, 100]。"""
    for stats in [
        FrameStats(brightness=0, edge_density=0, frame_diff=0),
        FrameStats(brightness=300, edge_density=5, frame_diff=999),
        FrameStats(brightness=120, edge_density=0.25, frame_diff=8),
    ]:
        s, _ = ha.analyze(stats=stats)
        assert 0 <= s <= 100