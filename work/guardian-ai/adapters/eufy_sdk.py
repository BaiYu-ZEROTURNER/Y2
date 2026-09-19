"""eufy SDK 适配器 —— 真实设备接入点。

方案要求：真实设备动作统一走 SDK Adapter，与 Risk/Health/Decision 逻辑解耦。
本文件定义统一接口；真实 SDK（HomeBase / eufy Security Open API）接通时在此实现，
未接通时 is_available() 返回 False，上层 Actuator 自动切到 MockDevice。

=========================== 真实接入清单（F5 已确认）===========================
1. eufy Security Open API（OAuth2 + REST）
   - 文档入口: https://github.com/home-assistant/core/tree/dev/homeassistant/components/eufy
   - 设备发现: GET /devices  -> 需要 P-SN-Device 列表（camera_id / model）
   - 实时视频: WS /resource/{device_sn}/livestream  -> 拉 H.264 帧
   - PTZ 控制: POST /resource/{device_sn}/ptz?action={track,preset}  -> 需要目标 bbox
   - 开关灯:   POST /resource/{device_sn}/light?state={on,off}
   - 录像开关: POST /resource/{device_sn}/record?state={start,stop}

2. 接入步骤（接入时按此顺序，每步 ≤ 4 小时）
   a. 申请 eufy Security Open API 的 Client ID / Secret
   b. 实现 connect()：OAuth2 token 刷新循环 + 设备列表拉取
   c. 实现 get_video_stream()：WS 拉流 → 帧解码 → 转 BGR numpy
   d. 实现三个动作方法 ptz_track / light_on / start_record
      这三个方法名是【硬约定】，Actuator 直接 get_attr 调用，不能改名
   e. is_available() 在 token 有效期内返回 True；过期返回 False，触发 fallback

3. 真实设备接通后只需要替换这一个文件，core/ 与 vision/ 零改动
=============================================================================
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional


class EufySDKAdapter:
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self._connected = False
        self._token = None
        self._devices: List[Dict] = []

    def is_available(self) -> bool:
        """真实 SDK 是否可用。token 有效 + 至少一个在线摄像头时返回 True。"""
        return self._connected

    def connect(self) -> bool:
        """建立与 eufy Cloud 的会话。真实实现填入 OAuth / token。"""
        # TODO(real): OAuth2 授权 + GET /devices → self._devices
        # 参考 eufy Security Open API 文档
        raise NotImplementedError("真实 eufy SDK 未接入，请使用 MockDevice 运行 demo")

    def get_video_stream(self, camera_id: str = "cam_01") -> Iterator:
        """WS 拉流 → 逐帧 BGR numpy。"""
        # TODO(real): websockets 拉 /livestream → cv2.VideoCapture 或自定义解码
        raise NotImplementedError("真实 eufy SDK 未接入")

    def get_device_events(self) -> List[Dict]:
        """返回 motion / doorbell / device_status 事件。"""
        # TODO(real): 订阅 eufy 推送 / 轮询 GET /events
        raise NotImplementedError("真实 eufy SDK 未接入")

    def get_device_status(self, camera_id: str = "cam_01") -> Dict:
        """返回 online / battery / wifi_rssi，供 Health Agent 使用。"""
        # TODO(real): GET /devices/{device_sn}/status
        raise NotImplementedError("真实 eufy SDK 未接入")

    # ---- 设备联动动作（方法名是 Actuator 的硬约定，禁止改名）----
    def ptz_track(self, camera_id: str, target: Dict) -> bool:
        # TODO(real): POST /resource/{sn}/ptz?action=track&bbox=...
        raise NotImplementedError("ptz_track 未接入真实设备")

    def light_on(self, camera_id: str) -> bool:
        # TODO(real): POST /resource/{sn}/light?state=on
        raise NotImplementedError("light_on 未接入真实设备")

    def start_record(self, camera_id: str) -> bool:
        # TODO(real): POST /resource/{sn}/record?state=start
        raise NotImplementedError("record 未接入真实设备")
