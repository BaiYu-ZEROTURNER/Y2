"""Event 数据结构 —— 全系统唯一的数据交换契约（F0 已冻结）。

任何模块（vision / agents / core / adapters / app）都只能通过这个结构交换数据。
字段严格对齐《两人十天分工与资源数据 AI 工作流说明书》中定义的固定 Event JSON：
{
  "event_id": "evt_001",
  "timestamp": "2026-09-xxT20:30:00",
  "person_id": 3,
  "identity": "unknown",
  "zone": "front_door",
  "stay_seconds": 95,
  "door_approaches": 3,
  "package_present": false,
  "risk_score": 88,
  "risk_reasons": ["night", "long_stay", "repeat_approach"],
  "health_score": 96,
  "actions": ["ptz_track", "light_on", "record", "notify"]
}

======================= 契约冻结声明（F0，所有人必须遵守）=======================
1. 本文件归 B（张陈宇）所有；除 B 以外任何人不得修改本文件。
2. SCHEMA_FIELDS 里的 12 个字段【禁止改名、禁止删除、禁止改变语义或单位】。
3. 只允许【新增带默认值的可选字段】，且必须放在 SCHEMA_FIELDS 之外，
   这样旧消费方（app.py / 报表 / 已有测试）不改一行也能继续跑。
4. A（杨婧兰）需要页面展示新字段时，走一句话申请：字段名 + 含义 + 单位。
   B 加进本文件后 A 才显示。禁止在 app.py 里绕过 schema 直接读 vision/ 内部变量。
5. 任何改动都要同步 SCHEMA_VERSION，并在 tests/test_event.py 补一条测试。
===========================================================================
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional


# 数据契约版本号。SCHEMA_FIELDS 有任何变动（新增也算）就必须 +1。
SCHEMA_VERSION = 1

# 风险等级常量。数值分界来自 config/risk_rules.yaml 的 thresholds（low / medium）。
LEVEL_LOW = "low"
LEVEL_MEDIUM = "medium"
LEVEL_HIGH = "high"


@dataclass
class Event:
    # ---- 固定 schema 字段（禁止改名/删除）----
    event_id: str = field(default_factory=lambda: "evt_" + uuid.uuid4().hex[:8])
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    person_id: int = -1
    identity: str = "unknown"            # unknown | known | family | delivery
    zone: str = "front_door"
    stay_seconds: int = 0
    door_approaches: int = 0
    package_present: bool = False
    risk_score: int = 0                  # 0-100
    risk_reasons: List[str] = field(default_factory=list)
    health_score: int = 100              # 0-100
    actions: List[str] = field(default_factory=list)

    # ---- 可选扩展字段（向后兼容，新增不影响旧消费方）----
    camera_id: str = "cam_01"
    scenario: str = ""                   # 仅 demo 用：family / delivery / loiter / occlusion
    confidence: float = 0.0
    health_issues: List[str] = field(default_factory=list)
    risk_level: str = LEVEL_LOW
    # B -> A 页面"动作日志区"取数点：每次 actions 实际下发到设备的结果
    actuator_log: List[dict] = field(default_factory=list)

    # schema 核心字段白名单，用于校验 / 序列化
    SCHEMA_FIELDS = (
        "event_id", "timestamp", "person_id", "identity", "zone",
        "stay_seconds", "door_approaches", "package_present",
        "risk_score", "risk_reasons", "health_score", "actions",
    )

    def to_dict(self, schema_only: bool = False) -> dict:
        """序列化为 dict。schema_only=True 时只保留固定 JSON 字段。"""
        d = asdict(self)
        if schema_only:
            return {k: d[k] for k in self.SCHEMA_FIELDS}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Event":
        """从 dict 构造，忽略未知字段以保持向后兼容。"""
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})

    def risk_level_from_score(self, low: int = 30, medium: int = 60) -> str:
        if self.risk_score >= medium:
            return LEVEL_HIGH
        if self.risk_score >= low:
            return LEVEL_MEDIUM
        return LEVEL_LOW

    def validate(self) -> List[str]:
        """返回校验错误列表（空列表表示通过）。"""
        errs: List[str] = []
        if not (0 <= self.risk_score <= 100):
            errs.append(f"risk_score out of range: {self.risk_score}")
        if not (0 <= self.health_score <= 100):
            errs.append(f"health_score out of range: {self.health_score}")
        if self.stay_seconds < 0:
            errs.append(f"stay_seconds negative: {self.stay_seconds}")
        if self.door_approaches < 0:
            errs.append(f"door_approaches negative: {self.door_approaches}")
        if self.identity not in ("unknown", "known", "family", "delivery"):
            errs.append(f"unknown identity value: {self.identity}")
        return errs


# ---- 视觉中间结构（vision 层内部，不经 Event 跨层）----

@dataclass
class Detection:
    """单帧检测结果。bbox 为归一化坐标 [x1, y1, x2, y2]，范围 0-1。"""
    cls: str                     # person | package
    bbox: List[float]
    confidence: float = 0.0
    track_id: int = -1           # 由 tracker 回填


@dataclass
class FrameStats:
    """Health Agent 所需的帧统计特征，可由真实帧计算或 mock 直接提供。"""
    brightness: float = 0.0      # 0-255 平均亮度
    edge_density: float = 0.0    # 0-1 边缘密度（越低越可能被遮挡）
    frame_diff: float = 0.0      # 与上一帧的平均像素差（越低越可能冻结）
