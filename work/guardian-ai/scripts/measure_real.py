"""A 的实测数字回写工具 —— 把真实视频的统计数字写进 measurements.json。

A 录完真实视频后，跑完一条就把数字填到 data/demo/measurements.json：
  python scripts/measure_real.py --scenario loiter \\
      --stay 75 --approaches 18 --health 97 \\
      --notes "门口侧身徘徊约 70s，三次接近门锁 ROI"

这份 JSON 是 B 调 risk_rules.yaml 的唯一输入。禁止直接改 yaml 试错。

字段定义（与 core/event.py 的 12 字段契约对齐）：
  scenario              family | delivery | loiter | occlusion
  video_path            相对或绝对路径（A 录的视频文件）
  fps                   帧率，建议 1-5
  total_frames          总帧数
  person_present        视频全程是否出现人物
  stay_seconds          单 person 最大停留时长（秒）
  door_approaches       进入门锁 ROI 次数（去抖后）
  package_present       是否有遗留包裹
  health_score          视频末帧健康分（健康异常场景填）
  health_issues         健康异常类型列表
  expected_risk_level   low | medium | high（demo 时希望系统给出）
  notes                 A 备注（影响权重的特殊情况）

测过的 → 填一项；没测过的 → 留 null 等待补录。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_PATH = os.path.join(ROOT, "data", "demo", "measurements.json")

SCENARIOS = ("family", "delivery", "loiter", "occlusion")
EXPECTED_LEVELS = ("low", "medium", "high", "health")


def _load(path: str) -> Dict:
    if not os.path.exists(path):
        return {"version": 1, "measurements": []}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: str, data: Dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _new_entry(scenario: str, args) -> Dict[str, Any]:
    return {
        "scenario": scenario,
        "video_path": args.video_path or "",
        "fps": args.fps,
        "total_frames": args.total_frames,
        "person_present": args.person_present,
        "stay_seconds": args.stay,
        "door_approaches": args.approaches,
        "package_present": args.package_present,
        "health_score": args.health,
        "health_issues": [x.strip() for x in (args.health_issues or "").split(",") if x.strip()],
        "expected_risk_level": args.expected_risk,
        "notes": args.notes or "",
        "recorded_at": datetime.now().isoformat(timespec="seconds"),
        "recorded_by": "A",
    }


def _show_diff(prev: Dict, new: Dict) -> None:
    """打印与上次同场景记录的差异（A 多次录相同场景时方便看变化）。"""
    keys = ("stay_seconds", "door_approaches", "health_score",
            "package_present", "expected_risk_level")
    print(f"\n  与上一次的差异（{prev.get('recorded_at')}）：")
    for k in keys:
        if prev.get(k) != new.get(k):
            print(f"    {k}: {prev.get(k)} → {new.get(k)}")


def main() -> int:
    ap = argparse.ArgumentParser(description="A 真实视频实测数字回写")
    ap.add_argument("scenario", choices=SCENARIOS, help="场景 id")
    ap.add_argument("--video-path", help="视频文件路径")
    ap.add_argument("--fps", type=int, default=1, help="视频帧率")
    ap.add_argument("--total-frames", type=int, default=0)
    ap.add_argument("--person-present", choices=("yes", "no"), default="yes")
    ap.add_argument("--stay", type=int, default=0, help="最大停留秒数")
    ap.add_argument("--approaches", type=int, default=0, help="进入门锁 ROI 次数")
    ap.add_argument("--package-present", choices=("yes", "no"), default="no")
    ap.add_argument("--health", type=int, default=100, help="视频末帧健康分 0-100")
    ap.add_argument("--health-issues", help="健康异常，逗号分隔，如 black_screen,obstructed")
    ap.add_argument("--expected-risk", choices=EXPECTED_LEVELS, default="low",
                    help="demo 时希望系统给出的风险等级")
    ap.add_argument("--notes", help="备注（影响权重的特殊情况）")
    ap.add_argument("--path", default=DEFAULT_PATH,
                    help="measurements.json 路径（默认 data/demo/measurements.json）")
    args = ap.parse_args()

    args.person_present = args.person_present == "yes"
    args.package_present = args.package_present == "yes"

    if not (0 <= args.health <= 100):
        print("error: --health must be 0-100", file=sys.stderr)
        return 1

    data = _load(args.path)
    new_entry = _new_entry(args.scenario, args)
    same_scenario = [m for m in data["measurements"] if m["scenario"] == args.scenario]
    if same_scenario:
        prev = same_scenario[-1]
        _show_diff(prev, new_entry)

    data["measurements"].append(new_entry)
    _save(args.path, data)

    print(f"\n✓ 已写入 {args.path}")
    print(f"  场景={new_entry['scenario']} stay={new_entry['stay_seconds']}s "
          f"approaches={new_entry['door_approaches']} "
          f"health={new_entry['health_score']} "
          f"expected={new_entry['expected_risk_level']}")
    print(f"\nB 可以看这份 JSON 调 risk_rules.yaml（{len(data['measurements'])} 条记录）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())