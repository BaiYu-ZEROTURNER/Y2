from vision.tracker import Tracker
from core.event import Detection


def test_stable_id_across_frames():
    tr = Tracker()
    b = [0.45, 0.5, 0.55, 0.85]
    d1 = tr.update([Detection("person", b)])[0]
    d2 = tr.update([Detection("person", [0.46, 0.5, 0.56, 0.85])])[0]
    assert d1.track_id == d2.track_id
    assert d1.track_id != -1


def test_new_id_for_far_object():
    tr = Tracker()
    a = tr.update([Detection("person", [0.1, 0.5, 0.2, 0.85])])[0]
    b = tr.update([Detection("person", [0.8, 0.5, 0.9, 0.85])])[0]
    assert a.track_id != b.track_id


def test_trajectory_recorded():
    tr = Tracker()
    for _ in range(3):
        tr.update([Detection("person", [0.5, 0.5, 0.6, 0.85])])
    tid = tr.update([Detection("person", [0.5, 0.5, 0.6, 0.85])])[0].track_id
    assert len(tr.trajectory(tid)) >= 1
