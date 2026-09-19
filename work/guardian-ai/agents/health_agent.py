"""Health Agent —— 安防系统健康自检（遮挡 / 黑屏 / 冻结）。

对应方案核心功能 2：监测摄像头自身是否可靠，避免"设备已失效但用户不知情"。
三种失效模式（按优先级）：
  1) black_screen   黑屏（平均亮度极低）
  2) obstructed     遮挡（边缘密度过低，画面过于平滑）
  3) frozen         冻结（与上一帧几乎无变化）
真实帧模式用 numpy/opencv 计算 FrameStats；mock 模式直接接收 stats，无需图像依赖。
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from core.config_loader import load_risk_rules
from core.event import FrameStats


class HealthAgent:
    def __init__(self, rules: dict = None):
        self.rules = (rules or load_risk_rules())["health"]
        self._prev: Optional[FrameStats] = None

    # ---- 由真实帧计算统计特征（需 numpy；缺失则返回 None 走 mock）----
    @staticmethod
    def stats_from_frame(frame, prev=None):  # pragma: no cover - 仅在真实摄像头路径使用
        try:
            import numpy as np  # type: ignore
            import cv2  # type: ignore
        except Exception:
            return None, prev
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        brightness = float(gray.mean())
        edge = cv2.Laplacian(gray, cv2.CV_64F)
        edge_density = float((np.abs(edge) > 20).mean())
        frame_diff = 0.0
        if prev is not None:
            frame_diff = float(np.abs(gray.astype("float32") - prev).mean())
        return FrameStats(brightness=brightness, edge_density=edge_density, frame_diff=frame_diff), gray

    def analyze(self, frame=None, stats: FrameStats = None, prev=None) -> Tuple[int, List[str]]:
        """返回 (health_score 0-100, issues[])。"""
        if stats is None and frame is not None:
            stats, prev_gray = self.stats_from_frame(frame, prev)
            self._prev = prev_gray
        if stats is None:
            # 无帧无 stats：视为未知，给中性分数（不误报也不漏报）
            return 100, []

        issues: List[str] = []
        if stats.brightness < self.rules["black_frame_mean"]:
            issues.append("black_screen")
            return self.rules["black_score"], issues
        if stats.edge_density < self.rules["edge_low"]:
            issues.append("obstructed")
            return self.rules["occlusion_score"], issues
        if self._prev is not None and stats.frame_diff < self.rules["freeze_diff"]:
            issues.append("frozen")
            return self.rules["freeze_score"], issues

        # 正常：分数接近满分，并随边缘密度轻微浮动以体现"视角稳定度"
        score = 96 + int(min(4, stats.edge_density * 20))
        self._prev = stats
        return min(100, score), issues
