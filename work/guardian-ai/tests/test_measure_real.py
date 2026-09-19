"""measure_real.py 的最小契约护栏 —— 防止 schema 被改坏。

A 的真实视频数字必须按这个 schema 写，measure_real.py 自带验证；
B 调权重时只信任这份 JSON。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest


REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
SCRIPT = os.path.join(REPO, "scripts", "measure_real.py")
MEASUREMENTS = os.path.join(REPO, "data", "demo", "measurements.json")


def test_measure_real_writes_valid_json(tmp_path):
    """跑一次 measure_real.py，校验写出的 JSON 符合 schema。"""
    out_path = tmp_path / "measurements.json"
    subprocess.run([
        PY, SCRIPT, "loiter",
        "--video-path", "videos/loiter_01.mp4",
        "--stay", "75", "--approaches", "18",
        "--health", "97",
        "--expected-risk", "high",
        "--notes", "门口侧身徘徊约 70s",
        "--path", str(out_path),
    ], check=True)

    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert len(data["measurements"]) == 1
    m = data["measurements"][0]
    # 必备字段
    required = {
        "scenario", "video_path", "fps", "total_frames",
        "person_present", "stay_seconds", "door_approaches",
        "package_present", "health_score", "health_issues",
        "expected_risk_level", "notes", "recorded_at", "recorded_by",
    }
    assert required.issubset(m.keys()), f"缺少字段: {required - m.keys()}"
    assert m["scenario"] == "loiter"
    assert m["stay_seconds"] == 75
    assert m["door_approaches"] == 18
    assert m["expected_risk_level"] == "high"
    assert m["recorded_by"] == "A"
    assert isinstance(m["health_issues"], list)


def test_health_must_be_in_range():
    """--health 越界时脚本应主动拒绝（演示护栏）。"""
    r = subprocess.run([
        PY, SCRIPT, "loiter", "--health", "150",
    ], capture_output=True, text=True)
    assert r.returncode != 0


def test_multiple_records_coexist(tmp_path):
    """同一场景多次记录都能累积，不互相覆盖。"""
    out_path = tmp_path / "measurements.json"
    for i in range(3):
        subprocess.run([
            PY, SCRIPT, "loiter",
            "--stay", str(60 + i * 5),
            "--approaches", str(10 + i),
            "--path", str(out_path),
        ], check=True)
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert len(data["measurements"]) == 3


def test_real_measurements_file_or_clean(tmp_path):
    """data/demo/measurements.json 要么不存在，要么符合 schema。"""
    if not os.path.exists(MEASUREMENTS):
        return  # 没录过，正常
    with open(MEASUREMENTS, encoding="utf-8") as f:
        data = json.load(f)
    assert "measurements" in data
    for m in data["measurements"]:
        assert "scenario" in m
        assert "expected_risk_level" in m