"""Streamlit 演示入口 —— 逐帧播放版。

运行：
    cd guardian-ai
    pip install streamlit
    streamlit run app.py

双入口设计：
- 主入口（本文件）：streamlit 页面，评委看着舒服，逐帧播放 + 风险条 + 动作日志
- 兜底入口：python -m app.cli（零依赖，streamlit 挂了立刻切）

数据契约：A 禁止 import vision/ 内部变量，只能消费 Event JSON；
所有新展示字段先经 B 加进 core/event.py。
"""
from __future__ import annotations

import os
import sys

import streamlit as st

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.config_loader import load_risk_rules, load_zones          # noqa: E402
from core.context_engine import ContextEngine                       # noqa: E402
from core.decision_engine import DecisionEngine                     # noqa: E402
from core.actuator import Actuator                                  # noqa: E402
from agents.risk_agent import RiskAgent                             # noqa: E402
from agents.health_agent import HealthAgent                         # noqa: E402
from vision.detector import Detector                                # noqa: E402
from vision.tracker import Tracker                                  # noqa: E402
from adapters.mock_device import MockDevice                         # noqa: E402


SCENARIO_LABELS = {
    "family":    "① 家人经过（低风险）",
    "delivery":  "② 快递送件（低风险）",
    "loiter":    "③ 陌生人夜间徘徊（高风险）",
    "occlusion": "④ 镜头遮挡（健康异常）",
}
SCENARIOS = list(SCENARIO_LABELS.keys())


def build_pipeline():
    rules = load_risk_rules()
    zones = load_zones()
    return {
        "rules": rules,
        "zones": zones,
        "detector": Detector(),
        "tracker": Tracker(),
        "health": HealthAgent(rules),
        "context": ContextEngine(zones, HealthAgent(rules)),
        "risk": RiskAgent(rules),
        "decision": DecisionEngine(rules),
        "actuator": Actuator(),          # 三级链：真设备 → MockDevice → fallback
        "mock": MockDevice(),
    }


def run_trace(p, scenario: str):
    """跑完整场景，返回每帧的 Event 列表（轨迹）。

    每帧都做 risk / decision / actuator 三步，actuator 写入 ev.actuator_log，
    演示页面"动作日志区"取数点。
    """
    p["context"].reset()
    trace: list = []
    for fr in p["mock"].scenario_frames(scenario):
        dets = p["detector"].detect(injected=fr["detections"])
        tracked = p["tracker"].update(dets)
        ev = p["context"].update(
            tracked,
            dt=1.0,
            hour=fr["hour"],
            identity=fr["identity"],
            package_present=fr["package_present"],
            stats=fr["stats"],
            scenario=fr["scenario"],
        )
        ev.risk_score, ev.risk_reasons = p["risk"].score(ev.to_dict(), hour=fr["hour"])
        ev.actions = p["decision"].decide(ev)
        # Actuator 把下发结果写回 ev.actuator_log（页面"动作日志区"取数）
        p["actuator"].call(ev, ev.actions)
        trace.append(ev)
    return trace


def _render_frame_visual(ev, scenario: str) -> str:
    """把当前帧渲染成 ASCII 画面（终端友好的视觉占位）。

    真实视频接入后，这里替换为 cv2 缩略图 / st.image(numpy_array)。
    """
    # 健康异常 → 显示黑屏/遮挡图示
    if "black_screen" in ev.health_issues:
        return "┌──────────────┐\n│■■■■■■■■■■■■■■│\n│■■ 黑 屏 ■■│\n│■■■■■■■■■■■■■■│\n└──────────────┘"
    if "obstructed" in ev.health_issues:
        return "┌──────────────┐\n│░░░░░░░░░░░░░░│\n│░░ 遮 挡 ░░│\n│░░░░░░░░░░░░░░│\n└──────────────┘"
    # 正常帧：用 person_id / stay_seconds 体现当前状态
    person = f"person#{ev.person_id}" if ev.person_id != -1 else "（无人）"
    return (
        f"┌──────────────┐\n"
        f"│   画面 · {scenario:11s}│\n"
        f"│  {person:14s}│\n"
        f"│  stay={ev.stay_seconds:>4}s       │\n"
        f"│  approaches={ev.door_approaches:>2}    │\n"
        f"└──────────────┘"
    )


def _risk_bar(score: int) -> str:
    """返回风险条可视化字符串。"""
    filled = score // 10
    empty = 10 - filled
    color = "🟥" if score >= 60 else "🟨" if score >= 30 else "🟩"
    return f"{color} {'█' * filled}{'░' * empty} {score}/100"


def _health_bar(score: int) -> str:
    filled = score // 10
    empty = 10 - filled
    color = "🟥" if score < 60 else "🟨" if score < 90 else "🟩"
    return f"{color} {'█' * filled}{'░' * empty} {score}/100"


def _render_action_log(trace, upto: int):
    """渲染动作日志区（到当前帧为止）。"""
    items = []
    for i, ev in enumerate(trace[: upto + 1]):
        if not ev.actuator_log:
            continue
        for entry in ev.actuator_log:
            tag = "✓" if entry.get("ok") else "✗"
            fb = " [fallback]" if entry.get("fallback_used") else ""
            ms = entry.get("elapsed_ms", 0)
            items.append(
                f"`frame {i}` `{tag}` **{entry['action']}**{fb} ({ms:.0f}ms)"
            )
    if not items:
        return "（暂无动作下发）"
    return "\n\n".join(items[-20:])      # 只显示最近 20 条


def main():
    st.set_page_config(page_title="eufy Guardian AI", layout="wide")
    st.title("🐝 eufy Guardian AI · 智能安防演示")
    st.caption("Risk Agent（事件风险理解） · Health Agent（安防健康自检） · Device Action（设备联动）")

    # ---- 侧栏：场景 + 播放控制 ----
    scenario = st.sidebar.selectbox(
        "选择演示场景", SCENARIOS, format_func=lambda s: SCENARIO_LABELS[s]
    )
    autoplay = st.sidebar.toggle("▶ 自动播放", value=False)
    speed_ms = st.sidebar.slider("播放速度 (ms/帧)", 100, 1500, 500, 100)

    if "pipe" not in st.session_state:
        st.session_state.pipe = build_pipeline()
    if "trace" not in st.session_state or st.session_state.get("scenario") != scenario:
        st.session_state.scenario = scenario
        st.session_state.trace = run_trace(st.session_state.pipe, scenario)

    p = st.session_state.pipe
    trace = st.session_state.trace
    n = len(trace)

    # frame 滑块（受 autoplay 驱动）
    if autoplay:
        # 用一个 key 让 Streamlit 每次重渲染都能自增
        if "frame_idx" not in st.session_state:
            st.session_state.frame_idx = 0
        st.session_state.frame_idx = (st.session_state.frame_idx + 1) % n
        idx = st.session_state.frame_idx
        st.sidebar.progress((idx + 1) / n, text=f"frame {idx + 1}/{n}")
        # 用 st_autorefresh 触发下一帧重渲（需额外包；缺失则降级到 slider）
        try:
            from streamlit_autorefresh import st_autorefresh  # type: ignore
            st_autorefresh(interval=speed_ms, key="autoplay")
        except Exception:
            st.sidebar.caption("安装 streamlit-autorefresh 启用自动播放")
    else:
        idx = st.sidebar.slider("播放帧", 0, n - 1, 0, 1)
        st.session_state.frame_idx = idx
        st.sidebar.progress((idx + 1) / n, text=f"frame {idx + 1}/{n}")

    ev = trace[idx]

    # ---- 主区：4 列 ----
    col_visual, col_score, col_reason, col_action = st.columns([2, 2, 2, 3])

    with col_visual:
        st.subheader("📷 当前画面")
        st.code(_render_frame_visual(ev, scenario), language=None)
        st.caption(f"frame {idx + 1} / {n} · hour={ev.scenario or scenario}")

    with col_score:
        st.subheader("📊 评分")
        st.markdown(f"**Risk** {_risk_bar(ev.risk_score)}")
        st.caption(f"Level: `{ev.risk_level}`")
        st.markdown(f"**Health** {_health_bar(ev.health_score)}")
        if ev.health_issues:
            st.error(f"健康异常: {', '.join(ev.health_issues)}")

    with col_reason:
        st.subheader("🔍 原因")
        if ev.risk_reasons:
            chips = " ".join(f"`{r}`" for r in ev.risk_reasons)
            st.markdown(f"**Risk reasons**: {chips}")
        else:
            st.markdown("**Risk reasons**: —")
        if ev.health_issues:
            st.markdown(f"**Health issues**: {' '.join(f'`{h}`' for h in ev.health_issues)}")
        st.markdown(
            f"**Person**: `{ev.identity}` · stay `{ev.stay_seconds}s` · "
            f"approaches `{ev.door_approaches}`"
        )

    with col_action:
        st.subheader("⚙ 动作日志（到目前为止）")
        st.markdown(_render_action_log(trace, idx))

    # ---- 底部：完整 Event JSON（schema_only）----
    st.divider()
    st.subheader("Event JSON（数据契约核心 12 字段）")
    st.json(ev.to_dict(schema_only=True))
    with st.expander("完整 Event（含 actuator_log / health_issues 等扩展字段）"):
        st.json(ev.to_dict())


if __name__ == "__main__":
    main()