"""配置加载器：读取 risk_rules.yaml 与 zones.json。

优先使用 PyYAML；若运行环境未安装 pyyaml，则回退到内置默认权重，保证 demo 与测试仍可运行。
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

# config_loader.py 位于 core/，配置文件位于 ../config/
_CONFIG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "config")
_RISK_PATH = os.path.join(_CONFIG_DIR, "risk_rules.yaml")
_ZONES_PATH = os.path.join(_CONFIG_DIR, "zones.json")

# pyyaml 缺失时的内置兜底。
# 重要：这里必须与 config/risk_rules.yaml 保持完全一致。
# tests/test_config_loader.py 会逐字段比对，不一致就红灯，防止两处规则漂移。
_FALLBACK_RISK: Dict[str, Any] = {
    "version": 2,
    "max_score": 100,
    "thresholds": {"low": 30, "medium": 60},
    "time": {"night_start": 22, "night_end": 6},
    "params": {
        "stay_long_seconds": 30,
        "stay_very_long_seconds": 60,
        "sensitive_roi_min": 1,
        "repeat_approach_min": 2,
    },
    "weights": {
        "unknown_identity": 20,
        "night": 15,
        "long_stay": 10,
        "long_stay_extra": 10,
        "sensitive_roi": 15,
        "repeat_approach": 15,
        "package_left": 10,
        "known_member": -20,
        "delivery_like": -20,
    },
    "health": {
        "black_frame_mean": 12,
        "edge_low": 0.04,
        "freeze_diff": 2.0,
        "occlusion_score": 40,
        "black_score": 10,
        "freeze_score": 30,
        "alert_score": 50,
    },
}


def load_risk_rules(path: str = _RISK_PATH) -> Dict[str, Any]:
    """加载风险规则。找不到文件或 pyyaml 缺失时回退到内置默认。"""
    try:
        import yaml  # type: ignore
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return dict(_FALLBACK_RISK)


def load_zones(path: str = _ZONES_PATH) -> Dict[str, Any]:
    """加载场景区域配置。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # 兜底：仅含 front_door，保证 demo/测试可跑
        return {"zones": {"front_door": {
            "label": "门口",
            "polygon": [[0.30, 0.42], [0.70, 0.42], [0.74, 0.95], [0.26, 0.95]],
            "door_roi": [[0.42, 0.68], [0.58, 0.68], [0.58, 0.86], [0.42, 0.86]],
        }}}
