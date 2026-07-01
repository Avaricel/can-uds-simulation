"""
CAN总线监控模块 - 实时监控CAN报文，检测异常
"""

import time
import threading
from collections import defaultdict, deque
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum


class CANMonitorState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


@dataclass
class CANMonitorConfig:
    """CAN监控配置"""
    # 报文超时检测 (ms)
    message_timeout_ms: float = 1000.0
    # 周期抖动容忍度 (百分比)
    cycle_jitter_tolerance: float = 0.2  # ±20%
    # 总线负载告警阈值 (百分比)
    bus_load_warning_pct: float = 60.0
    bus_load_critical_pct: float = 80.0
    # 错误帧告警阈值 (每秒)
    error_frames_per_sec_warn: float = 10
    # 存储最近N秒的心跳记录
    heartbeat_window_seconds: float = 5.0
    # 自动检测周期报文的最小采样数
    min_samples_for_cycle_detect: int = 5


@dataclass
class CANMonitorAlert:
    """CAN监控告警"""
    level: str  # info | warning | critical
    category: str  # timeout | cycle | bus_load | error_frame
    can_id: int = 0
    message: str = ""
    timestamp: float = 0.0
    details: Dict = field(default_factory=dict)


class CANMonitor:
    """
    CAN总线实时监控器

    功能：
    - 报文超时检测
    - 周期报文抖动检测
    - 总线负载率监控
    - 错误帧统计
    - 可自定义告警回调
    """

    def __init__(self, config: Optional[CANMonitorConfig] = None):
        self.config = config or CANMonitorConfig()
        self.state = CANMonitorState.STOPPED

        # 报文追踪
        self._last_seen: Dict[int, float] = {}         # CAN ID -> 最后看到的时间
        self._msg_timestamps: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=100)
        )
        self._expected_cycles: Dict[int, float] = {}   # CAN ID -> 期望周期(ms)

        # 统计
        self._total_frames = 0
        self._error_frames = 0
        self._start_time = 0.0
        self._bus_load_samples: deque = deque(maxlen=100)

        # 告警
        self.alerts: deque = deque(maxlen=200)
        self._alert_callbacks: List[Callable] = []
        self._alert_counts: Dict[str, int] = defaultdict(int)

        # 线程安全
        self._lock = threading.Lock()

        # 监控周期报文的ID集合
        self._cyclic_ids: Set[int] = set()

    def start(self):
        """启动监控"""
        self.state = CANMonitorState.RUNNING
        self._start_time = time.time()

    def stop(self):
        """停止监控"""
        self.state = CANMonitorState.STOPPED

    def pause(self):
        """暂停监控"""
        self.state = CANMonitorState.PAUSED

    def resume(self):
        """恢复监控"""
        self.state = CANMonitorState.RUNNING

    def add_callback(self, callback: Callable):
        """添加告警回调函数"""
        self._alert_callbacks.append(callback)

    def set_expected_cycle(self, can_id: int, cycle_ms: float):
        """设置期望周期"""
        self._expected_cycles[can_id] = cycle_ms
        self._cyclic_ids.add(can_id)

    def feed(self, can_id: int, data: bytes,
             timestamp: Optional[float] = None,
             is_error: bool = False):
        """喂入一帧CAN报文"""
        if self.state != CANMonitorState.RUNNING:
            return

        ts = timestamp or time.time()

        with self._lock:
            self._total_frames += 1
            if is_error:
                self._error_frames += 1

            # 记录时间戳
            self._last_seen[can_id] = ts
            self._msg_timestamps[can_id].append(ts)

            # 周期检测
            if can_id in self._cyclic_ids:
                self._check_cycle_jitter(can_id, ts)

        # 总线负载估算（简化：基于帧率）
        self._bus_load_samples.append(ts)

    def check_timeouts(self, current_time: Optional[float] = None):
        """检查报文超时"""
        ts = current_time or time.time()

        with self._lock:
            for can_id, last_seen in list(self._last_seen.items()):
                timeout = self.config.message_timeout_ms

                # 如果设定了期望周期，使用3倍期望周期作为超时阈值
                if can_id in self._expected_cycles:
                    timeout = max(timeout, self._expected_cycles[can_id] * 3)

                elapsed = (ts - last_seen) * 1000
                if elapsed > timeout:
                    level = "critical" if elapsed > timeout * 2 else "warning"
                    self._add_alert(CANMonitorAlert(
                        level=level,
                        category="timeout",
                        can_id=can_id,
                        message=(f"CAN ID 0x{can_id:03X} 超时: "
                                 f"{elapsed:.0f}ms (阈值: {timeout:.0f}ms)"),
                        timestamp=ts,
                        details={"elapsed_ms": elapsed, "threshold_ms": timeout}
                    ))

    def check_bus_load(self):
        """检查总线负载"""
        if len(self._bus_load_samples) < 2:
            return

        ts = time.time()
        # 计算最近1秒内的帧率
        recent = [s for s in self._bus_load_samples if ts - s <= 1.0]
        fps = len(recent)

        # 假设平均帧长度约120位（含填充位），500kbps总线
        # 简化负载计算
        bits_per_frame = 120
        bus_speed = 500000  # 500kbps
        load_pct = (fps * bits_per_frame) / bus_speed * 100

        if load_pct > self.config.bus_load_critical_pct:
            self._add_alert(CANMonitorAlert(
                level="critical", category="bus_load",
                message=f"总线负载严重过高: {load_pct:.1f}%",
                timestamp=ts,
                details={"load_pct": load_pct, "fps": fps}
            ))
        elif load_pct > self.config.bus_load_warning_pct:
            self._add_alert(CANMonitorAlert(
                level="warning", category="bus_load",
                message=f"总线负载偏高: {load_pct:.1f}%",
                timestamp=ts,
                details={"load_pct": load_pct, "fps": fps}
            ))

    def check_error_rate(self):
        """检查错误帧率"""
        if self._start_time == 0:
            return
        elapsed = time.time() - self._start_time
        if elapsed < 1:
            return

        error_rate = self._error_frames / elapsed
        if error_rate > self.config.error_frames_per_sec_warn:
            self._add_alert(CANMonitorAlert(
                level="warning", category="error_frame",
                message=f"错误帧率偏高: {error_rate:.1f} frames/s",
                timestamp=time.time(),
                details={"error_rate": error_rate}
            ))

    def _check_cycle_jitter(self, can_id: int, current_ts: float):
        """检查周期报文的抖动"""
        timestamps = self._msg_timestamps[can_id]
        if len(timestamps) < self.config.min_samples_for_cycle_detect:
            return

        expected = self._expected_cycles[can_id]
        # 计算实际周期
        intervals = [(timestamps[i+1] - timestamps[i]) * 1000
                     for i in range(len(timestamps)-2, len(timestamps)-1)]

        if intervals:
            actual = intervals[-1]
            deviation = abs(actual - expected) / expected

            if deviation > self.config.cycle_jitter_tolerance:
                self._add_alert(CANMonitorAlert(
                    level="warning",
                    category="cycle",
                    can_id=can_id,
                    message=(f"CAN ID 0x{can_id:03X} 周期抖动: "
                             f"{actual:.1f}ms (期望: {expected:.0f}ms, "
                             f"偏差: {deviation*100:.1f}%)"),
                    timestamp=current_ts,
                    details={
                        "actual_ms": actual,
                        "expected_ms": expected,
                        "deviation_pct": deviation * 100
                    }
                ))

    def _add_alert(self, alert: CANMonitorAlert):
        """添加告警"""
        self.alerts.append(alert)
        self._alert_counts[alert.category] += 1

        # 触发回调
        for cb in self._alert_callbacks:
            try:
                cb(alert)
            except Exception:
                pass

    def get_statistics(self) -> Dict:
        """获取监控统计"""
        with self._lock:
            elapsed = time.time() - self._start_time if self._start_time else 0
            return {
                "state": self.state.value,
                "total_frames": self._total_frames,
                "error_frames": self._error_frames,
                "monitored_ids": len(self._last_seen),
                "cyclic_ids_monitored": len(self._cyclic_ids),
                "runtime_seconds": round(elapsed, 1),
                "avg_fps": round(self._total_frames / elapsed, 1) if elapsed > 0 else 0,
                "alert_counts": dict(self._alert_counts),
                "recent_alerts": [
                    {"level": a.level, "category": a.category,
                     "message": a.message, "can_id_hex": f"0x{a.can_id:03X}"}
                    for a in list(self.alerts)[-5:]
                ],
            }

    def get_recent_alerts(self, n: int = 20,
                          min_level: str = "warning") -> List[CANMonitorAlert]:
        """获取最近告警"""
        levels = {"info": 0, "warning": 1, "critical": 2}
        min_lvl = levels.get(min_level, 0)
        return [a for a in list(self.alerts)[-n:] if levels.get(a.level, 0) >= min_lvl]

    def clear_alerts(self):
        """清除所有告警"""
        with self._lock:
            self.alerts.clear()
            self._alert_counts.clear()
