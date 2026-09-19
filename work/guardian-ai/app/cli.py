"""零依赖终端演示 —— streamlit 挂了立刻切这个。

运行：
    python -m app.cli                       # 默认 loiter 场景
    python -m app.cli loiter                # 指定场景
    python -m app.cli loiter --speed 300    # 自定义速度（ms/帧）

输出格式（每帧）：
    [frame 003/060] loiter hour=22
    ┌─────────────────────────────────┐
    │ person#1 · stay=12s · approaches=2│
    │ Risk  🟨 ███░░░░░░░  35/100 (medium)
    │       原因: unknown
    │ Health 🟩 █████████░  99/100
    ├─────────────────────────────────┤
    │ 动作: ✓ log (0.3ms)
    └─────────────────────────────────┘

"""
from __future__ import annotations

import argparse
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.config_loader import load_risk_rules, load_zones                # noqa: E402
from core.context_engine import ContextEngine                             # noqa: E402
from core.decision_engine import DecisionEngine                           # noqa: E402
from core.actuator import Actuator                                        # noqa: E402
from agents.risk_agent import RiskAgent                                   # noqa: E402
from agents.health_agent import HealthAgent                               # noqa: E402
from vision.detector import Detector                                      # noqa: E402
from vision.tracker import Tracker                                        # noqa: E402
from adapters.mock_device import MockDevice                               # noqa: E402

SCENARIOS = ("family", "delivery", "loiter", "occlusion")
LABELS = {
    "family":    "家人经过",
    "delivery":  "快递送件",
    "loiter":    "夜间徘徊",
    "occlusion": "镜头遮挡",
}


def _bar(score: int, width: int = 10) -> str:
    """把 0-100 分转成 '███░░░' 形式的进度条。"""
    filled = max(0, min(width, score * width // 100))
    return "█" * filled + "░" * (width - filled)


def _icon(score: int, kind: str = "risk") -> str:
    if kind == "risk":
        return "🟥" if score >= 60 else "🟨" if score >= 30 else "🟩"
    return "🟥" if score < 60 else "🟨" if score < 90 else "🟩"


def _render(ev, idx: int, total: int, scenario: str) -> str:
    """渲染一帧到可打印字符串。"""
    head = f"[frame {idx + 1:03d}/{total:03d}] {scenario} ({LABELS.get(scenario)})"
    person = f"person#{ev.person_id}" if ev.person_id != -1 else "（无人）"
    health_note = ""
    if ev.health_issues:
        health_note = f"  ⚠ {','.join(ev.health_issues)}"

    lines = [
        head,
        "┌─────────────────────────────────┐",
        f"│ {person} · stay={ev.stay_seconds}s · approaches={ev.door_approaches}".ljust(34) + "│",
        f"│ Risk   {_icon(ev.risk_score, 'risk')} {_bar(ev.risk_score)} {ev.risk_score:>3}/100 ({ev.risk_level})".ljust(34) + "│",
        f"│         原因: {','.join(ev.risk_reasons) or '-'}".ljust(34) + "│",
        f"│ Health {_icon(ev.health_score, 'health')} {_bar(ev.health_score)} {ev.health_score:>3}/100{health_note}".ljust(34) + "│",
    ]
    if ev.actuator_log:
        actions = ", ".join(
            ("✓" if e.get("ok") else "✗") + e["action"]
            for e in ev.actuator_log     # 显示本帧全部下发动作
        )
        lines.append(f"│ 动作: {actions}".ljust(34) + "│")
    lines.append("└─────────────────────────────────┘")
    return "\n".join(lines)


def run_cli(scenario: str = "loiter", speed_ms: int = 400, autoplay: bool = True):
    rules = load_risk_rules()
    zones = load_zones()
    pipe = {
        "detector": Detector(),
        "tracker": Tracker(),
        "health": HealthAgent(rules),
        "context": ContextEngine(zones, HealthAgent(rules)),
        "risk": RiskAgent(rules),
        "decision": DecisionEngine(rules),
        "actuator": Actuator(),
        "mock": MockDevice(),
    }
    pipe["context"].reset()
    trace = []
    for fr in pipe["mock"].scenario_frames(scenario):
        dets = pipe["detector"].detect(injected=fr["detections"])
        tracked = pipe["tracker"].update(dets)
        ev = pipe["context"].update(
            tracked, dt=1.0, hour=fr["hour"], identity=fr["identity"],
            package_present=fr["package_present"], stats=fr["stats"], scenario=fr["scenario"],
        )
        ev.risk_score, ev.risk_reasons = pipe["risk"].score(ev.to_dict(), hour=fr["hour"])
        ev.actions = pipe["decision"].decide(ev)
        pipe["actuator"].call(ev, ev.actions)
        trace.append(ev)

    if not autoplay:
        for i, ev in enumerate(trace):
            print(_render(ev, i, len(trace), scenario))
            print()
        return

    # 清屏逐帧
    for i, ev in enumerate(trace):
        os.system("cls" if os.name == "nt" else "clear")
        print(_render(ev, i, len(trace), scenario))
        print(f"\n[Ctrl+C 退出 · 自动播放 {speed_ms}ms/帧 · "
              f"共 {len(trace)} 帧]")
        if i < len(trace) - 1:
            time.sleep(speed_ms / 1000)


def main():
    ap = argparse.ArgumentParser(description="eufy Guardian AI 终端版演示")
    ap.add_argument("scenario", nargs="?", default="loiter", choices=SCENARIOS,
                    help="演示场景")
    ap.add_argument("--speed", type=int, default=400,
                    help="播放速度（毫秒/帧），仅自动播放生效")
    ap.add_argument("--no-autoplay", action="store_true",
                    help="关闭自动播放，一次性打印全部帧")
    args = ap.parse_args()
    try:
        run_cli(args.scenario, args.speed, autoplay=not args.no_autoplay)
    except KeyboardInterrupt:
        print("\n（已退出）")


if __name__ == "__main__":
    main()