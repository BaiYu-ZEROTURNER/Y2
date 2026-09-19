#!/usr/bin/env python
"""实测数字表生成器 —— B 交给 A 的 F2 交接工具。

用途
----
跑完四类场景，输出一张"实测数字表"：
    场景 | 停留秒数 | 靠近门锁次数 | health_score | risk_score | 等级 | 动作 | 命中原因

这张表就是 A → B 的**唯一交接物**：A 不需要理解风险规则，只要把这张表填准；
B 不需要理解视觉，只按表里的数字调 config/risk_rules.yaml 的权重。

用法
----
    python scripts/measure_scenarios.py                  # 四场景汇总表
    python scripts/measure_scenarios.py --climb loiter    # 逐帧风险爬升（给 A 做逐帧播放用）
    python scripts/measure_scenarios.py --json out.json   # 导出成 JSON，A 填真实视频的数字后再交回

A 侧如何接入真实视频（不需要改本文件）
--------------------------------------
本脚本的输入由一个 frame source 生成，每帧是一个 dict，两种形态任选：

    # 形态 1（mock，当前默认）—— 直接给检测结果
    {"detections": [Detection...], "stats": FrameStats(...), "identity": "unknown",
     "package_present": False, "hour": 23, "scenario": "loiter"}

    # 形态 2（真实视频）—— 给原始帧，由 Detector / HealthAgent 自己算
    {"frame": <ndarray BGR>, "identity": "unknown",
     "package_present": False, "hour": 23, "scenario": "loiter"}

A 只要在 vision/ 里实现一个产出形态 2 的生成器，然后在 main() 里换掉 `mock_source`
即可。本文件与 core/、agents/ 都不需要改动。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, Iterator, List

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from adapters.mock_device import MockDevice                          # noqa: E402
from agents.health_agent import HealthAgent                          # noqa: E402
from agents.risk_agent import RiskAgent                              # noqa: E402
from core.config_loader import load_risk_rules, load_zones            # noqa: E402
from core.context_engine import ContextEngine                         # noqa: E402
from core.decision_engine import DecisionEngine                       # noqa: E402
from vision.detector import Detector                                  # noqa: E402
from vision.tracker import Tracker                                     # noqa: E402

SCENARIOS = ("family", "delivery", "loiter", "occlusion")
# 中文字幕：场景 -> 人类可读名称
SCENARIO_LABELS = {
    "family": "家人经过",
    "delivery": "快递送件",
    "loiter": "陌生人夜间徘徊",
    "occlusion": "镜头遮挡",
}


def mock_source(scenario: str) -> Iterator[Dict]:
    """默认输入源：MockDevice 合成帧（无设备也能跑通）。"""
    yield from MockDevice().scenario_frames(scenario)


def run_scenario(scenario: str, source=mock_source, collect_frames: bool = False,
                 logger=None):
    """跑完一个场景，返回 (最后一帧 Event, 逐帧记录列表)。

    逐帧记录每项为 dict：{frame_index, risk_score, risk_reasons, stay_seconds,
    door_approaches, health_score, actions}，用于演示"风险分爬升"。

    logger 传入 core/EventLogger 实例时，会把每帧 Event 追加写入 JSONL，供联调排查。
    """
    rules = load_risk_rules()
    zones = load_zones()

    detector = Detector()
    tracker = Tracker()
    health = HealthAgent(rules)
    context = ContextEngine(zones, health)
    risk = RiskAgent(rules)
    decision = DecisionEngine(rules)

    context.reset()
    last, trace = None, []

    for idx, fr in enumerate(source(scenario)):
        # ---- 输入源两种形态的自适应 ----
        if "detections" in fr:
            dets = detector.detect(injected=fr["detections"])
            stats = fr.get("stats")
        else:
            dets = detector.detect(frame=fr.get("frame"))
            stats, _ = HealthAgent.stats_from_frame(fr.get("frame"))

        tracked = tracker.update(dets)
        ev = context.update(
            tracked,
            dt=float(fr.get("dt", 1.0)),
            hour=fr.get("hour", 20),
            identity=fr.get("identity", "unknown"),
            package_present=fr.get("package_present", False),
            stats=stats,
            scenario=fr.get("scenario", scenario),
        )
        ev.risk_score, ev.risk_reasons = risk.score(ev.to_dict(), hour=fr.get("hour", 20))
        ev.actions = decision.decide(ev)
        last = ev

        if logger is not None:
            logger.log(ev, extra={"scenario": scenario, "frame_index": idx})

        if collect_frames:
            trace.append({
                "frame_index": idx,
                "risk_score": ev.risk_score,
                "risk_reasons": list(ev.risk_reasons),
                "stay_seconds": ev.stay_seconds,
                "door_approaches": ev.door_approaches,
                "health_score": ev.health_score,
                "health_issues": list(ev.health_issues),
                "actions": list(ev.actions),
            })

    return last, trace


def measure_all(logger=None) -> List[Dict]:
    """跑全部场景，返回实测数字表（list of dict）。"""
    rows = []
    for sc in SCENARIOS:
        ev, _ = run_scenario(sc, logger=logger)
        rows.append({
            "scenario": sc,
            "label": SCENARIO_LABELS.get(sc, sc),
            "stay_seconds": ev.stay_seconds,
            "door_approaches": ev.door_approaches,
            "package_present": ev.package_present,
            "health_score": ev.health_score,
            "health_issues": list(ev.health_issues),
            "risk_score": ev.risk_score,
            "risk_level": ev.risk_level,
            "risk_reasons": list(ev.risk_reasons),
            "actions": list(ev.actions),
        })
    return rows


def _width(text: str) -> int:
    """按终端显示宽度计算字符串宽度：CJK 字符占 2 列，其余占 1 列。

    直接用 %-8s 会因为中文是双宽字符而错位，A 读这张表会很痛苦。
    """
    return sum(2 if ord(ch) > 0x2E80 else 1 for ch in str(text))


def _pad(text: str, width: int, align: str = "left") -> str:
    text = str(text)
    pad = max(0, width - _width(text))
    if align == "right":
        return " " * pad + text
    return text + " " * pad


def print_table(rows: List[Dict]) -> None:
    cols = [
        ("场景", 10, "left"), ("说明", 18, "left"), ("停留s", 7, "right"),
        ("靠近次数", 9, "right"), ("健康分", 7, "right"), ("风险分", 7, "right"),
        ("等级", 7, "left"), ("动作", 0, "left"),
    ]

    def line(values):
        return " ".join(
            _pad(v, w, a) if w else str(v)
            for v, (_, w, a) in zip(values, cols)
        )

    header = line([c[0] for c in cols])
    print(header.rstrip())
    print("-" * (_width(header) + 4))

    for r in rows:
        print(line([
            r["scenario"], r["label"], r["stay_seconds"], r["door_approaches"],
            r["health_score"], r["risk_score"], r["risk_level"],
            ",".join(r["actions"]),
        ]).rstrip())

    print()
    for r in rows:
        print("  %s 风险原因: %s" % (
            _pad(r["scenario"], 10), ", ".join(r["risk_reasons"]) or "（无）"))
        if r["health_issues"]:
            print("  %s 健康异常: %s" % (
                _pad(r["scenario"], 10), ", ".join(r["health_issues"])))


def print_climb(scenario: str) -> None:
    """打印逐帧风险爬升轨迹 —— 直接给 A 做"逐帧播放"可视化用。"""
    ev, trace = run_scenario(scenario, collect_frames=True)
    print("场景 %s（%s）逐帧轨迹：%d 帧\n" % (
        scenario, SCENARIO_LABELS.get(scenario, scenario), len(trace)))

    cols = [("帧", 5, "right"), ("风险分", 8, "right"), ("停留s", 8, "right"),
            ("靠近次数", 9, "right"), ("健康分", 8, "right"),
            ("等级", 7, "left"), ("新增原因", 0, "left")]

    def line(values):
        return " ".join(
            _pad(v, w, a) if w else str(v)
            for v, (_, w, a) in zip(values, cols)
        )

    header = line([c[0] for c in cols])
    print(header.rstrip())
    print("-" * (_width(header) + 4))

    prev: List[str] = []
    for t in trace:
        new = [x for x in t["risk_reasons"] if x not in prev]
        prev = t["risk_reasons"]
        print(line([
            t["frame_index"], t["risk_score"], t["stay_seconds"],
            t["door_approaches"], t["health_score"],
            _level_of(t["risk_score"]), ",".join(new) or "-",
        ]).rstrip())


def _level_of(score: int) -> str:
    th = load_risk_rules()["thresholds"]
    if score >= th["medium"]:
        return "high"
    if score >= th["low"]:
        return "medium"
    return "low"


def main() -> int:
    ap = argparse.ArgumentParser(description="四类场景实测数字表生成器")
    ap.add_argument("--climb", metavar="SCENARIO", choices=SCENARIOS,
                    help="打印指定场景的逐帧风险爬升轨迹")
    ap.add_argument("--json", metavar="PATH", help="把实测数字表导出为 JSON")
    ap.add_argument("--log", metavar="PATH",
                    help="把每帧 Event 追加写入 JSONL 日志（联调排查用）")
    args = ap.parse_args()

    if args.climb:
        print_climb(args.climb)
        return 0

    if args.log:
        from core.event_log import EventLogger
        with EventLogger(args.log, run_id="measure") as logger:
            rows = measure_all(logger=logger)
        print("已写入逐帧日志：%s\n" % args.log)
    else:
        rows = measure_all()

    print_table(rows)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print("\n已导出：%s" % args.json)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
