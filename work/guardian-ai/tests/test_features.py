import json
import os

from vision.features import FeatureExtractor, _point_in_polygon
from core.event import Detection

_ZONES = json.load(open(os.path.join(os.path.dirname(__file__), "..", "config", "zones.json"), encoding="utf-8"))
fx = FeatureExtractor(_ZONES)


def test_point_in_polygon():
    poly = [[0.3, 0.4], [0.7, 0.4], [0.7, 0.9], [0.3, 0.9]]
    assert _point_in_polygon([0.5, 0.6], poly) is True
    assert _point_in_polygon([0.05, 0.05], poly) is False


def test_zone_of_front_door():
    d = Detection("person", [0.5, 0.7, 0.55, 0.85])
    assert fx.zone_of(d) == "front_door"


def test_in_door_roi():
    d = Detection("person", [0.5, 0.75, 0.56, 0.84])  # 门锁 ROI 内部
    assert fx.in_door_roi(d, "front_door") is True
    d2 = Detection("person", [0.5, 0.5, 0.56, 0.6])    # 门口但不在门锁 ROI
    assert fx.in_door_roi(d2, "front_door") is False
