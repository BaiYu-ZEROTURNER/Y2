# eufy Guardian AI

> Anker 黑客松 · 智能安防赛道 · 团队 Y²（2 人）
> **它知道什么时候该担心，也知道自己什么时候已经看不清了。**

摄像头行业现在的问题是"看得见但不会判断"：5 分钟弹 12 条提醒，真出事那条被淹了；
更糟的是摄像头自己被挡住、黑屏、离线了，用户根本不知道。

本项目在不动 eufy 硬件的前提下，在 HomeBase / App 上层加一层 Agent，做两件事：

| Agent | 判断什么 | 输出 |
|---|---|---|
| **Risk Agent** | 外面发生的事危不危险 | `risk_score` 0–100 + 逐条可解释原因 + 硬件动作 |
| **Health Agent** | 安防系统自己还可不可靠 | `health_score` 0–100 + 失效设备与受影响区域 |

---

## 一键运行

```bash
cd guardian-ai

# 核心链路只需要 PyYAML 一个依赖
pip install pyyaml

# 方式一：跑通四类场景，直接在终端看结果
python scripts/measure_scenarios.py

# 看某个场景的逐帧风险爬升轨迹（给演示页面做"逐帧播放"用）
python scripts/measure_scenarios.py --climb loiter

# 导出实测数字表 + 逐帧日志（联调排查用）
python scripts/measure_scenarios.py --json measure.json --log runs.jsonl

# A 把真实视频的统计数字写进 measurements.json（B 调权重的唯一输入）
python scripts/measure_real.py loiter --stay 75 --approaches 18 \
    --expected-risk high --notes "门口侧身徘徊约 70s"

# 方式二：启动演示页面（推荐，需要额外装 streamlit）
pip install streamlit
streamlit run app.py

# 方式三（零依赖兜底）：演示现场 streamlit 挂了立刻切这个
python -m app.cli loiter
python -m app.cli loiter --no-autoplay     # 一次性打印全部帧
python -m app.cli occlusion --speed 300    # 自定义播放速度
```

跑测试（80 条）：

```bash
cd guardian-ai
pip install pytest
python -m pytest -q
```

**没有摄像头、没有设备、没有 SDK 也能完整跑通** —— 系统默认走 `MockDevice`，
它按真实视频流的同构格式合成四类场景的逐帧输入。设备接通后只换输入源，不改任何业务代码。

---

## 目录结构

```
guardian-ai/
├─ app.py                    # 演示页面入口（Streamlit，逐帧播放版）
├─ app/cli.py                # 演示页面兜底入口（零依赖终端版）
├─ scripts/
│  ├─ measure_scenarios.py   # B 的工具：四场景实测数字表 + 逐帧轨迹
│  └─ measure_real.py        # A 的工具：真实视频数字回写到 measurements.json
├─ config/                   # 【B 专属】规则与场景配置
│  ├─ risk_rules.yaml        # 风险权重 + 阈值（现场调 Demo 只改这里）
│  └─ zones.json             # 门口 / 车库 / 后院 ROI + 门锁 door_roi
├─ adapters/                 # 【B 专属】设备接入
│  ├─ eufy_sdk.py            # 真实 SDK 适配（接口占位，未接通返回 not available）
│  └─ mock_device.py         # 四类场景合成输入 + 设备动作 mock
├─ vision/                   # 【A 专属】逐帧视觉事实，无状态
│  ├─ detector.py            # 人物 / 包裹检测 + bbox 归一化护栏
│  ├─ tracker.py             # person_id 维持 + 轨迹
│  └─ features.py            # ROI 归属、是否在门锁 ROI 内
├─ agents/
│  ├─ risk_agent.py          # 【B】规则式风险评分（递进停留 + 画面无人早退）
│  └─ health_agent.py        # 【A】遮挡 / 黑屏 / 冻结自检
├─ core/                     # 【B 专属】契约与引擎
│  ├─ event.py               # ★ 全系统唯一数据契约（SCHEMA_VERSION = 1）
│  ├─ event_log.py           # 逐帧 JSONL 日志（联调排查 / 现场黑匣子）
│  ├─ config_loader.py       # 加载 yaml / json，含 pyyaml 缺失兜底
│  ├─ context_engine.py      # 跨帧累计停留时长、靠近门锁次数（冷启动已修复）
│  ├─ decision_engine.py     # 风险 / 健康 → 硬件动作（健康异常不再输出 log）
│  └─ actuator.py            # actions[] → 真设备 / Mock 设备统一下发（三级链）
├─ data/demo/
│  ├─ scenarios.json         # 四类样例视频规格
│  └─ measurements.json      # A 真实视频数字回写（B 调权重的唯一输入）
└─ tests/                    # 80 条 pytest（含契约冻结护栏）
```

---

## 核心数据契约（F0 已冻结）

所有模块之间【只】通过这一份 JSON 交换数据。A 的页面禁止 `import vision/` 直接读内部变量。

```json
{
  "event_id": "evt_001", "timestamp": "2026-09-17T20:30:00",
  "person_id": 3, "identity": "unknown", "zone": "front_door",
  "stay_seconds": 95, "door_approaches": 3, "package_present": false,
  "risk_score": 85, "risk_reasons": ["unknown", "night", "long_stay", "long_stay_extra", "sensitive_roi", "repeat_approach"],
  "health_score": 96, "actions": ["ptz_track", "light_on", "record", "notify"]
}
```

规则：
1. `SCHEMA_FIELDS` 里的 12 个字段**禁止改名、删除、改语义**。
2. 只允许**新增带默认值的可选字段**，且必须放在 `SCHEMA_FIELDS` 之外（旧消费方不用改）。
3. 改动必须同步 `SCHEMA_VERSION` 并在 `tests/test_event.py` 补测试。

---

## 协作规则（两个人不撞车的机制）

| 规则 | 内容 |
|---|---|
| **一个文件一个 owner** | A 只写 `vision/`、`agents/health_agent.py`、`app.py`；B 只写 `core/`、`agents/risk_agent.py`、`adapters/`、`config/` |
| **契约先冻结** | `event.py` + `risk_rules.yaml` + `zones.json` 由 B 定稿，要改先说一句话 |
| **视觉层无状态** | `vision/` 只说"这一帧看到什么"；累计（停留秒数、靠近次数）由 `core/context_engine.py` 做 |
| **数值只有 B 能改** | A 只提交"实测数字 → 期望风险等级"的表，不提具体权重 |
| **页面只读 schema** | 页面要显示新字段，先由 B 加进 `event.py`，A 再显示 |

---

## 演示双入口（现场防翻车）

演示页面顶部保留两个模式：

- **真实设备模式** —— 走 `EufySDKAdapter`，`is_available()` 为真时使用
- **Mock 演示模式** —— 走 `MockDevice`，用预录视频或合成帧复现同一套输入

真实设备一旦掉线，3 秒内切到 Mock 模式继续演示，不需要重启。

---

## 风险 / 健康判定规则

风险分由 `config/risk_rules.yaml` 的权重相加后 clamp 到 0–100，**每一项都对应一个可念出来的原因**：

| 条件 | 加分 | reason |
|---|---|---|
| 身份未知 | +20 | `unknown` |
| 夜间（22:00–06:00） | +15 | `night` |
| 停留 > 30s | +10 | `long_stay` |
| 停留 > 60s（第二档，递进） | +10 | `long_stay_extra` |
| 进入门锁 ROI | +15 | `sensitive_roi` |
| 靠近门锁 ≥ 2 次 | +15 | `repeat_approach` |
| 包裹遗留且身份异常 | +10 | `package_left` |
| 已知成员 / 家人 | −20 | `known_member` |
| 快递送件 | −20 | `delivery` |

分档：`< 30` 低风险（仅记录）· `30–59` 中风险（重点录像）· `≥ 60` 高风险（PTZ + 开灯 + 录像 + 通知）

> 停留采用**两档递进**而不是一次跳高分——这样演示时风险分是"爬上去"的，观感完全不一样。

健康分从 100 开始按异常扣分：遮挡 → 40，冻结 → 30，黑屏 → 10。
低于 `alert_score`（50）时 `DecisionEngine` 判为"安防覆盖下降"，输出 `notify_health + record`，
并且**不再输出 `log`**（log 的语义是"不打扰用户"，与健康告警冲突）。

---

## 当前进度

- [x] **F0 冻结契约** —— `event.py` / `risk_rules.yaml` / 规则表与说明书对齐 / git 仓库 / 本 README
- [x] **F1 输入通（B 侧）** —— `context_engine` 跨帧累计 + 冷启动修复 + `measure_scenarios.py` + JSONL 日志
- [x] **F2 判断通（B 侧）** —— actions 契约化 + 递进式停留 + 画面无人早退 + 阈值 yaml 化
- [x] **F3 页面通（B 侧）** —— `Actuator` 把 actions 真接到设备（真 → mock → fallback 三级链）
- [x] **F4 联调稳（B 侧）** —— 异常兜底全集（空帧 / 缺字段 / SDK 超时 / bbox 越界 / 设备抛错隔离）
- [x] **F5 冻结演练（B 侧）** —— 架构图 + 3 分钟讲稿 + 创新点话术（见 `docs/`）
- [x] **F1 输入通（A 侧）** —— `detector` YOLO 路径 + mock 路径 都走 `clamp_bbox` 归一化护栏
- [x] **F3 页面通（A 侧）** —— `app.py` 逐帧播放（Streamlit + 终端兜底双入口）
- [x] **F4 联调稳（A 侧）** —— `tracker` 多 person 隔离 / `health_agent` 三种失效模式稳定 / `measure_real.py` 回写 schema
- [ ] **F2 判断通（A 侧）** —— A 录真实视频，填 `data/demo/measurements.json`；B 再调权重

---

## A/B 实时交接物

| 从谁 | 交给谁 | 交接物 | 状态 |
|---|---|---|---|
| B | A | Event schema v1（12 字段冻结） | ✅ 已交 |
| B | A | `risk_rules.yaml` 规则表定稿 | ✅ 已交 |
| B | A | `scripts/measure_scenarios.py` 实测数字表生成器 | ✅ 已交 |
| B | A | `Actuator` actions 全语义 + `actuator_log` 字段 | ✅ 已交 |
| A | B | `data/demo/measurements.json` 真实视频数字 | ⏳ A 录后回写 |
| A | B | `detector` 输出 bbox 归一化护栏已加，真实视频接上后填测量表 | 🟡 待真实视频 |

> **重要约束**：A 的真实数字没回来之前，B 不调 `risk_rules.yaml`。\
> 全部用 MockDevice 合成值做演示数字，演示可立即开跑；真实视频接上后只换输入源。
