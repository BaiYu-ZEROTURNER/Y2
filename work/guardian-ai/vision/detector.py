"""人物 / 包裹检测。

设计原则（来自方案：AI-first，成熟模型直接推理不训练）：
- 真实模式：YOLO / RT-DETR 推理（opencv + ultralytics 可选，懒加载）。
- Mock 模式：由上游 MockDevice 直接提供检测结果，本类仅做格式归一化。
- 输出统一为 Detection（bbox 归一化 [x1,y1,x2,y2]），不向下游暴露具体模型细节。

【A 侧改造】新增 _clamp_bbox 与 normalize：
- bbox 一律钳位到 [0,1]，并保证 x1<=x2、y1<=y2（防 YOLO 极端输出把下游画崩）
- mock 注入路径同样归一化（之前依赖调用方自觉）
"""

from __future__ import annotations

from typing import List

from core.event import Detection

try:
    import numpy as np  # type: ignore
except Exception:  # pragma: no cover
    np = None


def clamp_bbox(bbox) -> List[float]:
    """bbox 钳位到 [0,1] 且保证 x1<=x2、y1<=y2。

    真实 YOLO 在边缘裁切 / 反归一化误差时可能产生 1.0001 / -0.001 等值，
    context_engine / features 都假设 [0,1]，超出则越界异常或误判。
    """
    if not bbox or len(bbox) != 4:
        return [0.0, 0.0, 0.0, 0.0]
    x1, y1, x2, y2 = (float(v) for v in bbox)
    x1 = max(0.0, min(1.0, x1))
    x2 = max(0.0, min(1.0, x2))
    y1 = max(0.0, min(1.0, y1))
    y2 = max(0.0, min(1.0, y2))
    if x2 < x1:
        x1, x2 = x2, x1
    if y2 < y1:
        y1, y2 = y2, y1
    return [x1, y1, x2, y2]


class Detector:
    """检测器的统一接口。frame 为 None 时视为 mock 模式（detections 由外部注入）。"""

    def __init__(self, model_path: str = "yolov8n.pt", device: str = "cpu"):
        self.model_path = model_path
        self.device = device
        self._model = None

    def _load_model(self):
        if self._model is not None:
            return self._model
        # 真实推理路径：ultralytics YOLO。缺失依赖时保持 None（mock 模式）。
        try:
            from ultralytics import YOLO  # type: ignore
            self._model = YOLO(self.model_path)
        except Exception:
            self._model = False
        return self._model

    def detect(self, frame=None, injected: List[Detection] = None) -> List[Detection]:
        """返回当前帧的检测结果。

        - injected 非空：mock 模式，直接返回（仅做 cls 校验 + bbox 归一化）。
        - 否则若模型可用：对 frame 推理并转为 Detection。
        - 否则：返回空列表（无设备/无模型的安全兜底）。
        """
        if injected is not None:
            outs = []
            for d in injected:
                if d.cls not in ("person", "package"):
                    continue
                outs.append(Detection(
                    cls=d.cls,
                    bbox=clamp_bbox(d.bbox),
                    confidence=float(d.confidence),
                ))
            return outs

        model = self._load_model()
        if model is False or frame is None or np is None:
            return []

        results = model(frame, verbose=False)[0]
        outs: List[Detection] = []
        for box in results.boxes:
            cls_name = results.names[int(box.cls)].lower()
            if cls_name not in ("person", "package"):
                continue
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0].tolist())
            h, w = frame.shape[:2]
            outs.append(Detection(
                cls=cls_name,
                bbox=clamp_bbox([x1 / w, y1 / h, x2 / w, y2 / h]),
                confidence=float(box.conf),
            ))
        return outs
