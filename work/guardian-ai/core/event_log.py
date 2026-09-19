"""Event 日志（JSONL）—— 联调期与演示现场的"黑匣子"。

为什么需要
----------
1. F4 联调稳 要求"四场景各连跑 3 次并记录成功率"，没有结构化日志就只能靠肉眼看屏幕。
2. 演示现场一旦翻车，日志是唯一能事后定位的证据（哪一帧分数不对、哪个字段丢了）。
3. app.py 的动作日志区可以直接读这个文件，A 不需要自己造轮子。

设计约束
--------
- 只写 Event 的 schema 字段（复用 event.to_dict(schema_only=True)），
  保证日志格式和页面展示、测试断言三处永远一致。
- 默认关闭（path=None），避免测试和普通运行时产生垃圾文件。
- 追加写，一行一个 JSON，方便 grep / 直接丢给 AI 分析。
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

from core.event import Event, SCHEMA_VERSION


class EventLogger:
    """把 Event 追加写入 JSONL 文件。path=None 时静默关闭（no-op）。"""

    def __init__(self, path: Optional[str] = None, run_id: str = ""):
        self.path = path
        self.run_id = run_id
        if path:
            # 目录不存在时自动创建：现场临时指定一个日志路径不该报错中断演示
            parent = os.path.dirname(os.path.abspath(path))
            os.makedirs(parent, exist_ok=True)
        self._fh = open(path, "w", encoding="utf-8") if path else None

    # ---- 上下文管理器：with EventLogger(p) as log: ... 自动关闭 ----
    def __enter__(self) -> "EventLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def log(self, ev: Event, extra: Optional[dict] = None) -> None:
        """写一条事件记录。extra 用于挂场景名、帧序号等联调信息。"""
        if not self._fh:
            return
        rec = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "event": ev.to_dict(schema_only=True),
            "ext": extra or {},
        }
        self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self._fh.flush()   # 演示现场可能随时中断，宁可慢一点也不要丢数据

    @staticmethod
    def read(path: str) -> List[dict]:
        """读回日志（供测试与 A 的页面使用）。"""
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]
