# 交接卡 · B → A

> 更新时间：F0 + F1（B 侧）已完成
> 当前 tag：`v0.1.1-f1b` · 测试 46 条全绿

---

## 一、你可以直接开始的东西

拉下代码后先跑一遍，确认你那边环境对得上：

```bash
git clone <仓库地址> && cd AnkerHackathon/guardian-ai
pip install pyyaml pytest
python -m pytest -q                       # 应该看到 46 passed
python scripts/measure_scenarios.py       # 应该看到四场景数字表
```

如果这两条都过，说明你的环境和契约是一致的，可以开工。

---

## 二、B 已经交给你什么（3 件）

### 1. 冻结的数据契约 —— `core/event.py`

**这是你和 B 之间唯一的管道。** 12 个字段已经冻结，禁止改名/删除：

```json
{
  "event_id": "...", "timestamp": "...", "person_id": 3, "identity": "unknown",
  "zone": "front_door", "stay_seconds": 95, "door_approaches": 3,
  "package_present": false, "risk_score": 85,
  "risk_reasons": ["unknown","night","long_stay","long_stay_extra","sensitive_roi","repeat_approach"],
  "health_score": 96, "actions": ["ptz_track","light_on","record","notify"]
}
```

- 你的 `app.py` **只读这个结构**，禁止 `import vision/` 直接读内部变量。
- 要展示新字段？告诉我「字段名 + 含义 + 单位」，我加进 `event.py` 后你再显示。
- 已有 `SCHEMA_VERSION = 1`，并且有一条测试盯着这 12 个字段，谁改谁红灯。

### 2. 定稿的规则表 —— `config/risk_rules.yaml`

风险分怎么来的、每项加多少分、阈值是多少，全在这一个文件里。
**你不用改它，也不能改它** —— 现场调参是我的活。

### 3. 交接工具 —— `scripts/measure_scenarios.py`

这是你要用的东西：

```bash
python scripts/measure_scenarios.py                  # 四场景汇总表
python scripts/measure_scenarios.py --climb loiter   # 逐帧风险爬升轨迹 ← 做逐帧播放用这个
python scripts/measure_scenarios.py --json m.json    # 导出成 JSON，填完交回给 B
```

当前 mock 模式跑出来的基准值（你接真实视频后要能对上同一个量级）：

| 场景 | 停留s | 靠近次数 | 健康分 | 风险分 | 等级 | 动作 |
|---|---|---|---|---|---|---|
| family 家人经过 | 0 | 0 | 100 | 0 | low | log |
| delivery 快递送件 | 0 | 0 | 100 | 0 | low | log |
| loiter 陌生人夜间徘徊 | 70 | 17 | 99 | **85** | **high** | ptz_track, light_on, record, notify |
| occlusion 镜头遮挡 | 0 | 0 | **40** | 20 | low | notify_health, record |

loiter 的风险分爬升轨迹是**五个台阶**，这是演示的核心画面：

```
帧 0   35  medium  unknown, night
帧 4   50  medium  + sensitive_roi
帧 8   65  high    + repeat_approach
帧 29  75  high    + long_stay
帧 59  85  high    + long_stay_extra
```

---

## 三、现在轮到你的两件事（F1-A 和 F2 的输入）

### 任务 1：detector 接真实视频（F1 的 A 侧）

**你负责的边界**：`vision/detector.py`、`vision/tracker.py`、`vision/features.py`、`agents/health_agent.py`

**验收标准**（可量化，达不到就告诉我，我改方案）：

| 项 | 标准 |
|---|---|
| bbox | 归一化到 `[0,1]`，格式 `[x1,y1,x2,y2]` |
| 检出率 | 一条真实视频能稳定检出 person |
| person_id | 同一个人 30 帧内 `person_id` 不跳变 |
| ROI 归属 | 人站在门口时 `zone_of()` 返回 `front_door`，不是 `outside` |
| 遮挡检测 | 遮挡视频 3 帧内 `health_score` 从 ~100 掉到 40 |

**如果 tracking 不稳**：直接告诉我，我们把最终 Demo 收窄成"固定单人场景"，不要硬撑——
这是方案里已经写好的降级路径。

### 任务 2：交回实测数字表（F2 的输入）

用真实视频跑：

```bash
python scripts/measure_scenarios.py --json measure_real.json
```

然后把这几个数字发我，**只要数字，不要改我的 yaml**：

```
场景 | 停留秒数 | 靠近门锁次数 | health_score
家人经过  | ? | ? | ?
快递送件  | ? | ? | ?
夜间徘徊  | ? | ? | ?
镜头遮挡  | ? | ? | ?
```

我拿到这张表才能调 `risk_rules.yaml` 的权重。**这是 F2 的唯一入口**，没有它我这边的调参就是瞎猜。

---

## 四、你那边的两件事我会配合

1. **app.py 改逐帧播放** —— 需要我在 `event.py` 加字段的话提前说。
   逐帧数据可以这样拿：
   ```python
   import measure_scenarios as ms
   ev, trace = ms.run_scenario("loiter", collect_frames=True)
   # trace 是逐帧列表，每项含 frame_index / risk_score / risk_reasons /
   # stay_seconds / door_approaches / health_score / actions
   ```

2. **动作日志区** —— 我在 `core/event_log.py` 做了 JSONL 日志，你可以直接读：
   ```python
   from core.event_log import EventLogger
   for rec in EventLogger.read("runs.jsonl"):
       print(rec["event"]["actions"], rec["ext"]["scenario"])
   ```

---

## 五、边界（避免我们又撞车）

| 你能改 | 你不能改 |
|---|---|
| `vision/*` | `core/*`（含 `event.py`、`risk_rules.yaml` 的加载逻辑） |
| `agents/health_agent.py` | `agents/risk_agent.py` |
| `app.py` | `adapters/*` |
| `data/demo/*` | `config/*`（含 `risk_rules.yaml` 与 `zones.json`） |

`vision/` 只输出**这一帧看到什么**（Detection / FrameStats）；
"人待了多久""靠近了几次"这类**累计**是 `core/context_engine.py` 的活，归我。

---

## 六、如果卡住

先跑 `python scripts/measure_scenarios.py --climb loiter`，
它能把每一帧的 `stay_seconds` / `door_approaches` / `risk_score` / 命中的原因全打出来。
用这个对齐你的视觉输出，比对着文档猜快得多。
