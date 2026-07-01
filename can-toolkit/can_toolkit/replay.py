"""
CAN 报文回放器

从日志文件读取 CAN 报文并重新发送到总线。
支持 ASC/CSV/SQLite 格式的输入, 支持加速/减速/循环回放。

Example:
    >>> mgr = CANBusManager(BusConfig(interface="virtual", channel="ch1"))
    >>> replay = CANReplay(mgr)
    >>> mgr.connect()
    >>> replay.load("capture.asc")
    >>> replay.start(speed=1.0)  # 1x 原速回放
    >>> replay.wait()  # 等待回放完成
"""

import csv
import sqlite3
import time
import threading
from typing import Optional, List, Dict, Any, Tuple

try:
    import can
except ImportError:
    pass

from .bus_manager import CANBusManager


class CANReplay:
    """
    CAN 报文回放器

    支持的日志格式:
      - ASC (Vector ASCII)
      - CSV (can-toolkit CSV)
      - SQLite (can-toolkit SQLite)

    Example:
        >>> mgr = CANBusManager(BusConfig(interface="virtual", channel="ch0"))
        >>> replay = CANReplay(mgr)
        >>> mgr.connect()
        >>> replay.load("capture.asc")
        >>> replay.start(speed=2.0, loop=True)
        >>> replay.wait()
    """

    def __init__(self, bus_manager: CANBusManager):
        self._bus = bus_manager
        self._messages: List[Tuple[float, can.Message]] = []  # (timestamp, message)
        self._running = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._speed: float = 1.0
        self._loop: bool = False
        self._sent_count: int = 0
        self._total_count: int = 0

        # 进度回调
        self._progress_callback: Optional[callable] = None

    # ── 加载 ──────────────────────────────────────

    def load(self, filepath: str, format: Optional[str] = None) -> int:
        """加载日志文件

        Args:
            filepath: 日志文件路径
            format: 格式 (asc/csv/sqlite), None 则从后缀名推断

        Returns:
            加载的报文数量
        """
        if format is None:
            ext = filepath.rsplit(".", 1)[-1].lower()
            format = ext

        self._messages.clear()

        if format == "asc":
            self._messages = self._load_asc(filepath)
        elif format == "csv":
            self._messages = self._load_csv(filepath)
        elif format == "sqlite":
            self._messages = self._load_sqlite(filepath)
        else:
            raise ValueError(f"Unsupported format: {format}")

        self._total_count = len(self._messages)
        print(f"[REPLAY] Loaded {self._total_count} messages from {filepath}")
        return self._total_count

    def _load_asc(self, filepath: str) -> List[Tuple[float, can.Message]]:
        """加载 ASC 文件"""
        messages = []
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("date ") or line.startswith("base "):
                    continue
                if line.startswith("internal ") or line.startswith("Begin "):
                    continue

                parts = line.split()
                if len(parts) < 5:
                    continue

                try:
                    ts = float(parts[0])
                    # parts[1] = channel
                    can_id_str = parts[2]
                    # parts[3] = Rx/Tx, parts[4] = d
                    dlc = int(parts[5]) if len(parts) > 5 else 0
                    data_hex = parts[6:6+dlc] if len(parts) > 6 else []

                    is_extended = "x" in can_id_str
                    can_id = int(can_id_str.rstrip("xX "), 16)
                    data = bytes(int(h, 16) for h in data_hex)

                    msg = can.Message(
                        timestamp=ts,
                        arbitration_id=can_id,
                        data=data,
                        is_extended_id=is_extended,
                    )
                    messages.append((ts, msg))
                except (ValueError, IndexError):
                    continue

        return sorted(messages, key=lambda x: x[0])

    def _load_csv(self, filepath: str) -> List[Tuple[float, can.Message]]:
        """加载 CSV 文件"""
        messages = []
        with open(filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    ts = float(row.get("timestamp", 0))
                    can_id = int(row["can_id"], 16)
                    data_hex = row.get("data_hex", "")
                    data = bytes(int(h, 16) for h in data_hex.split())
                    is_ext = bool(int(row.get("is_extended", 0)))

                    msg = can.Message(
                        timestamp=ts,
                        arbitration_id=can_id,
                        data=data,
                        is_extended_id=is_ext,
                    )
                    messages.append((ts, msg))
                except (ValueError, KeyError):
                    continue

        return sorted(messages, key=lambda x: x[0])

    def _load_sqlite(self, filepath: str) -> List[Tuple[float, can.Message]]:
        """加载 SQLite 文件"""
        messages = []
        conn = sqlite3.connect(filepath)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT rel_timestamp, can_id, is_extended, data "
            "FROM can_messages ORDER BY timestamp ASC"
        )
        for row in cursor.fetchall():
            ts, can_id, is_ext, data = row
            msg = can.Message(
                timestamp=ts,
                arbitration_id=can_id,
                data=data,
                is_extended_id=bool(is_ext),
            )
            messages.append((ts, msg))
        conn.close()
        return messages

    # ── 回放控制 ──────────────────────────────────

    def start(self, speed: float = 1.0, loop: bool = False):
        """开始回放

        Args:
            speed: 回放速度倍数 (1.0=原速, 2.0=2倍速, 0.5=半速)
            loop: 是否循环回放
        """
        if not self._messages:
            print("[REPLAY] No messages loaded. Call load() first.")
            return

        self._speed = speed
        self._loop = loop
        self._running = True
        self._paused = False
        self._sent_count = 0

        self._thread = threading.Thread(target=self._replay_loop, daemon=True)
        self._thread.start()
        print(f"[REPLAY] Started: {self._total_count} msgs, {speed}x speed"
              + (", looping" if loop else ""))

    def stop(self):
        """停止回放"""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        print(f"[REPLAY] Stopped. Sent: {self._sent_count}/{self._total_count}")

    def pause(self):
        """暂停回放"""
        self._paused = True
        print("[REPLAY] Paused")

    def resume(self):
        """恢复回放"""
        self._paused = False
        print("[REPLAY] Resumed")

    def wait(self):
        """等待回放完成 (阻塞)"""
        if self._thread is not None:
            self._thread.join()

    def set_progress_callback(self, callback: callable):
        """设置进度回调"""
        self._progress_callback = callback

    def _replay_loop(self):
        """回放主循环"""
        base_time = self._messages[0][0] if self._messages else 0
        start_wall = time.time()

        while self._running:
            last_send_wall = time.time()

            for ts, msg in self._messages:
                if not self._running:
                    break

                # 暂停处理
                while self._paused and self._running:
                    time.sleep(0.1)

                # 计算目标发送时间
                target_wall = start_wall + (ts - base_time) / self._speed
                sleep_time = target_wall - time.time()

                if sleep_time > 0:
                    time.sleep(sleep_time)

                try:
                    self._bus.send(
                        can_id=msg.arbitration_id,
                        data=msg.data,
                        is_extended=msg.is_extended_id,
                    )
                    self._sent_count += 1
                except Exception as e:
                    print(f"[REPLAY] Send error: {e}")

            # 进度回调
            if self._progress_callback:
                try:
                    self._progress_callback(self._sent_count, self._total_count)
                except Exception:
                    pass

            # 循环
            if not self._loop:
                break
            start_wall = time.time()

        self._running = False
        print(f"[REPLAY] Finished. {self._sent_count} messages sent.")

    @property
    def progress(self) -> float:
        """回放进度 (0.0 ~ 1.0)"""
        if self._total_count == 0:
            return 0.0
        return self._sent_count / self._total_count

    @property
    def is_running(self) -> bool:
        return self._running
