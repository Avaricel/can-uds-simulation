"""
CAN 总线连接管理器

基于 python-can 库，统一管理 CAN 总线连接。
支持多种硬件接口和虚拟接口，提供统一的收发 API。

支持的接口类型:
  - socketcan     (Linux SocketCAN, 最常用)
  - pcan          (PEAK CAN 适配器)
  - vector        (Vector VN16xx 系列)
  - slcan         (串口 CAN 适配器, 如 USB2CAN)
  - virtual       (虚拟接口, 用于测试和开发)
  - kvaser        (Kvaser 适配器)
  - serial        (串口接口)
  - pcan_usb      (PEAK USB 适配器别名)
"""

import time
import threading
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass, field

try:
    import can
    HAS_PYTHON_CAN = True
except ImportError:
    HAS_PYTHON_CAN = False


# 常用 CAN 接口配置参考
INTERFACE_PRESETS: Dict[str, Dict[str, Any]] = {
    "socketcan_ch0":    {"interface": "socketcan", "channel": "can0", "bitrate": 500000},
    "socketcan_ch1":    {"interface": "socketcan", "channel": "can1", "bitrate": 500000},
    "pcan_usb_ch0":     {"interface": "pcan", "channel": "PCAN_USBBUS1", "bitrate": 500000},
    "pcan_usb_ch1":     {"interface": "pcan", "channel": "PCAN_USBBUS2", "bitrate": 500000},
    "vector_ch0":       {"interface": "vector", "channel": 0, "app_name": "can-toolkit", "bitrate": 500000},
    "vector_ch1":       {"interface": "vector", "channel": 1, "app_name": "can-toolkit", "bitrate": 500000},
    "slcan_com3":       {"interface": "slcan", "channel": "COM3", "bitrate": 500000},
    "slcan_com4":       {"interface": "slcan", "channel": "COM4", "bitrate": 500000},
    "kvaser_ch0":       {"interface": "kvaser", "channel": 0, "bitrate": 500000},
    "virtual_0":        {"interface": "virtual", "channel": "ch0", "bitrate": 500000},
    "virtual_1":        {"interface": "virtual", "channel": "ch1", "bitrate": 500000},
}

# 各接口需要的 driver/依赖说明
INTERFACE_REQUIREMENTS: Dict[str, str] = {
    "socketcan": "Linux 内核 SocketCAN 支持 (无需额外驱动)",
    "pcan":      "PEAK PCAN-Basic API / pcan-driver",
    "vector":    "Vector XL Driver Library",
    "slcan":     "串口转 CAN 适配器 (如 USB2CAN, LAWAICAN)",
    "virtual":   "无 (内置于 python-can, 用于开发测试)",
    "kvaser":    "Kvaser CANlib SDK",
    "serial":    "串口适配器 (如 Systec)",
}


@dataclass
class BusConfig:
    """CAN 总线配置"""
    interface: str = "virtual"
    channel: str = "ch0"
    bitrate: int = 500000
    fd: bool = False          # 是否启用 CAN FD
    data_bitrate: int = 2000000  # CAN FD 数据段波特率

    # 扩展参数 (传递给 python-can)
    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_preset(cls, name: str) -> "BusConfig":
        """从预设名称创建配置"""
        if name in INTERFACE_PRESETS:
            preset = INTERFACE_PRESETS[name]
            return cls(
                interface=preset.get("interface", "virtual"),
                channel=preset.get("channel", "ch0"),
                bitrate=preset.get("bitrate", 500000),
                extra={k: v for k, v in preset.items()
                       if k not in ("interface", "channel", "bitrate")}
            )
        raise ValueError(f"Unknown preset: {name}. Available: {list(INTERFACE_PRESETS.keys())}")

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BusConfig":
        """从字典创建配置 (兼容 JSON/YAML 配置)"""
        return cls(
            interface=d.get("interface", "virtual"),
            channel=d.get("channel", "ch0"),
            bitrate=d.get("bitrate", 500000),
            fd=d.get("fd", False),
            data_bitrate=d.get("data_bitrate", 2000000),
            extra={k: v for k, v in d.items()
                   if k not in ("interface", "channel", "bitrate", "fd", "data_bitrate")}
        )

    def to_can_config(self) -> Dict[str, Any]:
        """转换为 python-can 的 Bus 构造参数"""
        if self.interface == "virtual":
            return {"interface": "virtual", "channel": self.channel, "bitrate": self.bitrate}
        elif self.interface == "socketcan":
            cfg = {"interface": "socketcan", "channel": self.channel}
            if self.fd:
                cfg["fd"] = True
                cfg["data_bitrate"] = self.data_bitrate
            return cfg
        elif self.interface == "pcan":
            return {"interface": "pcan", "channel": self.channel, "bitrate": self.bitrate}
        elif self.interface == "vector":
            return {
                "interface": "vector",
                "channel": self.channel,
                "bitrate": self.bitrate,
                "app_name": self.extra.get("app_name", "can-toolkit"),
            }
        elif self.interface == "slcan":
            return {
                "interface": "slcan",
                "channel": self.channel,
                "bitrate": self.bitrate,
            }
        elif self.interface == "kvaser":
            return {
                "interface": "kvaser",
                "channel": self.channel,
                "bitrate": self.bitrate,
            }
        else:
            # 通用构造
            return {
                "interface": self.interface,
                "channel": self.channel,
                "bitrate": self.bitrate,
                **self.extra,
            }


class CANBusManager:
    """
    CAN 总线管理器

    封装 python-can 的 Bus 对象，提供:
      - 自动连接/重连
      - 同步/异步收发
      - 消息回调机制
      - 总线统计

    Example:
        >>> mgr = CANBusManager(BusConfig(interface="virtual", channel="ch0"))
        >>> mgr.connect()
        >>> mgr.send(can_id=0x123, data=[0x01, 0x02, 0x03])
        >>> msg = mgr.receive(timeout=1.0)
        >>> mgr.disconnect()
    """

    def __init__(self, config: BusConfig):
        if not HAS_PYTHON_CAN:
            raise ImportError(
                "python-can is required. Install: pip install python-can"
            )

        self.config = config
        self._bus: Optional[can.Bus] = None
        self._running = False
        self._callbacks: List[Callable[[can.Message], None]] = []
        self._recv_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # 统计
        self._tx_count: int = 0
        self._rx_count: int = 0
        self._error_count: int = 0
        self._start_time: float = 0.0

    # ── 连接管理 ──────────────────────────────────

    def connect(self) -> bool:
        """建立 CAN 总线连接"""
        if self._bus is not None:
            return True

        try:
            can_cfg = self.config.to_can_config()
            self._bus = can.interface.Bus(**can_cfg)
            self._start_time = time.time()
            print(f"[BUS] Connected: {self.config.interface}:{self.config.channel} "
                  f"@ {self.config.bitrate//1000}kbps")
            return True
        except Exception as e:
            print(f"[BUS] Connection failed: {e}")
            print(f"[BUS] HINT: {INTERFACE_REQUIREMENTS.get(self.config.interface, 'Unknown interface')}")
            return False

    def disconnect(self):
        """断开 CAN 总线连接"""
        self.stop_listening()

        with self._lock:
            if self._bus is not None:
                try:
                    self._bus.shutdown()
                except Exception:
                    pass
                self._bus = None

        elapsed = time.time() - self._start_time
        print(f"[BUS] Disconnected. TX={self._tx_count} RX={self._rx_count} "
              f"Errors={self._error_count} Uptime={elapsed:.1f}s")

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._bus is not None

    # ── 发送 ──────────────────────────────────────

    def send(self, can_id: int, data: bytes, is_extended: bool = False,
             is_fd: bool = False, is_remote: bool = False) -> bool:
        """发送 CAN 报文

        Args:
            can_id: CAN ID (标准帧 0x000-0x7FF, 扩展帧 0x00000000-0x1FFFFFFF)
            data: 数据负载 (0-8 字节 for CAN, 0-64 字节 for CAN FD)
            is_extended: 是否扩展帧
            is_fd: 是否 CAN FD 帧
            is_remote: 是否远程帧
        """
        if self._bus is None:
            print("[BUS] Not connected. Call connect() first.")
            return False

        try:
            msg = can.Message(
                arbitration_id=can_id,
                data=data,
                is_extended_id=is_extended,
                is_fd=is_fd,
                is_remote_frame=is_remote,
            )
            self._bus.send(msg)
            self._tx_count += 1

            # 同时注入 virtual bus (方便在同一进程内测试收发)
            return True
        except can.CanError as e:
            self._error_count += 1
            print(f"[BUS] Send error (ID=0x{can_id:X}): {e}")
            return False

    def send_periodic(self, can_id: int, data: bytes, period: float,
                      duration: Optional[float] = None):
        """
        周期性发送 CAN 报文

        Args:
            can_id: CAN ID
            data: 数据负载
            period: 发送周期 (秒)
            duration: 发送时长 (秒), None 表示无限

        Returns:
            周期性任务对象 (用于 stop), 或 None
        """
        if self._bus is None:
            print("[BUS] Not connected. Call connect() first.")
            return None

        msg = can.Message(arbitration_id=can_id, data=data)

        if duration is not None:
            task = self._bus.send_periodic(msg, period, duration)
        else:
            task = self._bus.send_periodic(msg, period)

        return task

    # ── 接收 ──────────────────────────────────────

    def receive(self, timeout: float = 1.0) -> Optional[can.Message]:
        """同步接收一条 CAN 报文"""
        if self._bus is None:
            return None

        try:
            msg = self._bus.recv(timeout=timeout)
            if msg is not None:
                self._rx_count += 1
            return msg
        except can.CanError as e:
            self._error_count += 1
            print(f"[BUS] Receive error: {e}")
            return None

    def add_callback(self, callback: Callable[[can.Message], None]):
        """注册消息回调"""
        self._callbacks.append(callback)

    def remove_callback(self, callback: Callable[[can.Message], None]):
        """移除消息回调"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    def start_listening(self):
        """启动异步监听 (后台线程)"""
        if self._running:
            return

        self._running = True
        self._recv_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._recv_thread.start()

    def stop_listening(self):
        """停止异步监听"""
        self._running = False
        if self._recv_thread is not None:
            self._recv_thread.join(timeout=2.0)
            self._recv_thread = None

    def _listen_loop(self):
        """监听循环 (后台线程)"""
        while self._running and self._bus is not None:
            try:
                msg = self._bus.recv(timeout=0.1)
                if msg is not None:
                    self._rx_count += 1
                    for cb in self._callbacks:
                        try:
                            cb(msg)
                        except Exception as e:
                            print(f"[BUS] Callback error: {e}")
            except can.CanError as e:
                self._error_count += 1
                print(f"[BUS] Listen error: {e}")
            except Exception:
                pass

    # ── 统计 ──────────────────────────────────────

    @property
    def stats(self) -> Dict[str, Any]:
        """获取总线统计信息"""
        elapsed = time.time() - self._start_time if self._start_time > 0 else 0
        return {
            "interface": self.config.interface,
            "channel": self.config.channel,
            "bitrate": self.config.bitrate,
            "connected": self.is_connected(),
            "tx_count": self._tx_count,
            "rx_count": self._rx_count,
            "error_count": self._error_count,
            "uptime_seconds": round(elapsed, 1),
            "rx_rate": round(self._rx_count / elapsed, 1) if elapsed > 0 else 0,
            "tx_rate": round(self._tx_count / elapsed, 1) if elapsed > 0 else 0,
        }

    # ── Context Manager ───────────────────────────

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()
