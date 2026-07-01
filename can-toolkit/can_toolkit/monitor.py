"""
CAN 总线实时监控器

终端实时显示 CAN 总线报文、信号变化、总线负载。
支持彩色输出、过滤、统计汇总。

Example:
    >>> mgr = CANBusManager(BusConfig(interface="virtual", channel="ch0"))
    >>> monitor = CANMonitor(mgr)
    >>> mgr.connect()
    >>> monitor.start()
    >>> # ... monitor in real-time ...
    >>> monitor.stop()
"""

import threading
import time
from typing import Optional, List, Dict, Any, Set
from collections import defaultdict
from dataclasses import dataclass, field

try:
    import can
except ImportError:
    pass

from .bus_manager import CANBusManager


@dataclass
class MessageStats:
    """单个 CAN ID 的统计"""
    can_id: int
    count: int = 0
    last_data: bytes = b""
    first_seen: float = 0.0
    last_seen: float = 0.0
    period_min: float = float("inf")
    period_max: float = 0.0
    period_avg: float = 0.0
    _periods: List[float] = field(default_factory=list)
    _prev_ts: float = 0.0

    def update(self, data: bytes, timestamp: float):
        if self.count == 0:
            self.first_seen = timestamp
            self._prev_ts = timestamp
        else:
            period = timestamp - self._prev_ts
            self._periods.append(period)
            self.period_min = min(self.period_min, period)
            self.period_max = max(self.period_max, period)
            self.period_avg = sum(self._periods[-20:]) / min(len(self._periods), 20)
            self._prev_ts = timestamp

        self.count += 1
        self.last_data = bytes(data)
        self.last_seen = timestamp

    @property
    def period_ms(self) -> float:
        return self.period_avg * 1000 if self.period_avg > 0 else 0


class CANMonitor:
    """
    CAN 总线实时监控器

    Example:
        >>> mgr = CANBusManager(BusConfig(interface="virtual", channel="ch0"))
        >>> mon = CANMonitor(mgr)
        >>> mgr.connect()
        >>> mon.start()
        >>> # 一段时间后...
        >>> table = mon.get_stats_table()
        >>> print(table)
        >>> mon.stop()
    """

    def __init__(self, bus_manager: CANBusManager):
        self._bus = bus_manager
        self._stats: Dict[int, MessageStats] = {}
        self._lock = threading.Lock()
        self._running = False
        self._print_thread: Optional[threading.Thread] = None
        self._filter_ids: Optional[Set[int]] = None
        self._print_interval: float = 1.0  # 打印间隔 (秒)

    def set_filter(self, can_ids: Optional[List[int]] = None):
        """设置监控过滤"""
        self._filter_ids = set(can_ids) if can_ids else None

    def start(self, print_interval: float = 1.0):
        """启动监控

        Args:
            print_interval: 统计打印间隔 (秒), 0 表示不打印
        """
        if self._running:
            return

        self._running = True
        self._print_interval = print_interval
        self._bus.add_callback(self._on_message)

        if print_interval > 0:
            self._print_thread = threading.Thread(target=self._print_loop, daemon=True)
            self._print_thread.start()

    def stop(self) -> Dict[int, MessageStats]:
        """停止监控, 返回统计结果"""
        self._running = False
        self._bus.remove_callback(self._on_message)

        if self._print_thread is not None:
            self._print_thread.join(timeout=2.0)

        return dict(self._stats)

    def _on_message(self, msg: can.Message):
        """消息回调"""
        if self._filter_ids is not None:
            if msg.arbitration_id not in self._filter_ids:
                return

        with self._lock:
            can_id = msg.arbitration_id
            if can_id not in self._stats:
                self._stats[can_id] = MessageStats(can_id=can_id)

            self._stats[can_id].update(
                data=msg.data,
                timestamp=msg.timestamp
            )

    def _print_loop(self):
        """定期打印统计"""
        while self._running:
            time.sleep(self._print_interval)
            if not self._running:
                break
            table = self.get_stats_table(top_n=20)
            print("\n" + table)

    def get_active_ids(self) -> List[int]:
        """获取当前活跃的 CAN ID 列表"""
        with self._lock:
            return sorted(self._stats.keys())

    def get_message_count(self, can_id: int) -> int:
        """获取指定 CAN ID 的报文数"""
        with self._lock:
            stat = self._stats.get(can_id)
            return stat.count if stat else 0

    def get_last_data(self, can_id: int) -> Optional[bytes]:
        """获取指定 CAN ID 的最后一条数据"""
        with self._lock:
            stat = self._stats.get(can_id)
            return bytes(stat.last_data) if stat else None

    def get_total_count(self) -> int:
        """获取总报文数"""
        with self._lock:
            return sum(s.count for s in self._stats.values())

    def get_stats_table(self, top_n: int = 30) -> str:
        """生成统计表格 (纯文本)"""
        with self._lock:
            sorted_stats = sorted(
                self._stats.items(),
                key=lambda x: x[1].count,
                reverse=True
            )[:top_n]

        if not sorted_stats:
            return "No CAN messages received."

        lines = [
            "=" * 95,
            f"{'CAN ID':>8} | {'Count':>8} | {'Period(ms)':>11} | {'Last Data':>32} | {'Description':20}",
            "-" * 95,
        ]

        for can_id, stat in sorted_stats:
            data_hex = " ".join(f"{b:02X}" for b in stat.last_data[:8])
            desc = _describe_can_id(can_id)
            period = f"{stat.period_ms:.1f}" if stat.period_ms > 0 else "---"
            lines.append(
                f"0x{can_id:>06X} | {stat.count:>8} | {period:>10}ms | "
                f"{data_hex:<32} | {desc[:20]}"
            )

        lines.append("-" * 95)
        total = sum(s.count for _, s in sorted_stats)
        unique = len(sorted_stats)
        lines.append(f"Total: {total} messages from {unique} unique CAN IDs")
        lines.append("=" * 95)

        return "\n".join(lines)

    def get_json_stats(self) -> Dict[str, Any]:
        """导出 JSON 格式的统计"""
        with self._lock:
            result = {
                "total_messages": sum(s.count for s in self._stats.values()),
                "unique_ids": len(self._stats),
                "messages": []
            }
            for can_id, stat in sorted(self._stats.items()):
                result["messages"].append({
                    "can_id": f"0x{can_id:X}",
                    "decimal_id": can_id,
                    "count": stat.count,
                    "period_ms": round(stat.period_ms, 1),
                    "last_data_hex": " ".join(f"{b:02X}" for b in stat.last_data),
                })
            return result

    def reset(self):
        """重置统计"""
        with self._lock:
            self._stats.clear()


def _describe_can_id(can_id: int) -> str:
    """根据 CAN ID 推测报文类型 (辅助标注)"""
    descriptions = {
        # 常见 CAN ID 范围
    }
    # PGN 估算 (J1939)
    if 0x0CF00400 <= can_id <= 0x0CF004FF:
        return "EEC1 (Engine)"
    if 0x0CF00300 <= can_id <= 0x0CF003FF:
        return "EEC2 (Engine)"
    if 0x18FEF100 <= can_id <= 0x18FEF1FF:
        return "TSC1 (Torque)"
    if 0x18F00100 <= can_id <= 0x18F001FF:
        return "CCVS (Cruise)"
    if 0x18F00900 <= can_id <= 0x18F009FF:
        return "VEP1 (Vehicle)"
    if 0x18F00500 <= can_id <= 0x18F005FF:
        return "AMC (Speed)"
    if 0x18FEBF00 <= can_id <= 0x18FEBFFF:
        return "ETC1 (Trans)"
    # UDS 请求/响应
    if 0x700 <= can_id <= 0x7FF:
        return f"UDS (Diag ID=0x{can_id:X})"
    # OBD
    if can_id == 0x7DF:
        return "OBD Request"
    if can_id == 0x7E8:
        return "OBD Resp ECU#1"
    if can_id == 0x7E9:
        return "OBD Resp ECU#2"
    # 网络管理
    if 0x400 <= can_id <= 0x5FF:
        return "NM (Network Mgmt)"
    # 常规范围
    if can_id < 0x100:
        return "High-Priority"
    if can_id < 0x300:
        return "System/Body"
    if can_id < 0x500:
        return "Powertrain"
    if can_id < 0x600:
        return "Body/Comfort"
    if can_id < 0x700:
        return "Infotainment"
    return ""
