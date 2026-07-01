"""
CAN 流量记录器

将 CAN 总线报文实时记录到文件，支持多种格式:
  - ASC  (Vector CANoe ASCII 格式, 行业标准)
  - CSV  (通用表格格式)
  - SQLite (结构化数据库, 便于查询分析)
  - BLF  (Vector 二进制格式, 通过 python-can 原生支持)

Example:
    >>> mgr = CANBusManager(BusConfig(interface="virtual", channel="ch0"))
    >>> logger = CANLogger(mgr)
    >>> mgr.connect()
    >>> logger.start("output.asc", format="asc")
    >>> # ... CAN traffic flows ...
    >>> logger.stop()
"""

import csv
import os
import sqlite3
import time
import threading
from typing import Optional, Dict, Any, List
from datetime import datetime

try:
    import can
except ImportError:
    pass

from .bus_manager import CANBusManager


class ASCWriter:
    """Vector ASC 格式写入器 (CANoe 兼容)"""

    def __init__(self, filepath: str):
        self._file = open(filepath, "w", encoding="utf-8", newline="\r\n")
        self._start_time: Optional[float] = None
        self._msg_count = 0

        # ASC 文件头
        now = datetime.now()
        self._file.write("date {} {}\n".format(
            now.strftime("%a %b %d %H:%M:%S"),
            now.strftime("%Y")
        ))
        self._file.write("base hex  timestamps absolute\n")
        self._file.write("internal events logged\n")

    def write(self, msg: can.Message) -> None:
        """写入一条 CAN 报文"""
        if self._start_time is None:
            self._start_time = msg.timestamp

        ts = msg.timestamp - self._start_time
        can_id = msg.arbitration_id
        dlc = msg.dlc if msg.dlc else len(msg.data)
        data_hex = " ".join(f"{b:02X}" for b in msg.data)

        ext = "x" if msg.is_extended_id else " "
        line = f"{ts:12.6f} 1  {can_id:>8X}{ext} Rx d {dlc} {data_hex}\n"
        self._file.write(line)
        self._msg_count += 1

    def close(self):
        self._file.close()


class CSVWriter:
    """CSV 格式写入器"""

    COLUMNS = ["timestamp", "can_id", "is_extended", "dlc", "data_hex",
               "data_bin", "channel"]

    def __init__(self, filepath: str):
        self._file = open(filepath, "w", encoding="utf-8", newline="")
        self._writer = csv.writer(self._file)
        self._writer.writerow(self.COLUMNS)
        self._start_time: Optional[float] = None
        self._msg_count = 0

    def write(self, msg: can.Message) -> None:
        if self._start_time is None:
            self._start_time = msg.timestamp

        ts = msg.timestamp - self._start_time
        data_hex = " ".join(f"{b:02X}" for b in msg.data)
        data_bin = "".join(f"{b:08b}" for b in msg.data)

        self._writer.writerow([
            f"{ts:.6f}",
            f"0x{msg.arbitration_id:X}",
            int(msg.is_extended_id),
            len(msg.data),
            data_hex,
            data_bin,
            msg.channel if msg.channel is not None else "",
        ])
        self._msg_count += 1

    def close(self):
        self._file.close()


class SQLiteWriter:
    """SQLite 写入器 (结构化存储, 支持 SQL 查询)"""

    def __init__(self, filepath: str):
        self._conn = sqlite3.connect(filepath)
        self._cursor = self._conn.cursor()
        self._msg_count = 0

        self._cursor.execute("""
            CREATE TABLE IF NOT EXISTS can_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                rel_timestamp REAL NOT NULL,
                can_id INTEGER NOT NULL,
                is_extended INTEGER DEFAULT 0,
                dlc INTEGER NOT NULL,
                data BLOB NOT NULL,
                data_hex TEXT NOT NULL,
                channel TEXT DEFAULT ''
            )
        """)
        self._cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_can_id ON can_messages(can_id)
        """)
        self._cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON can_messages(timestamp)
        """)
        self._conn.commit()
        self._start_time: Optional[float] = None

    def write(self, msg: can.Message) -> None:
        if self._start_time is None:
            self._start_time = msg.timestamp

        rel_ts = msg.timestamp - self._start_time
        data_hex = " ".join(f"{b:02X}" for b in msg.data)

        self._cursor.execute("""
            INSERT INTO can_messages
            (timestamp, rel_timestamp, can_id, is_extended, dlc, data, data_hex, channel)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            msg.timestamp,
            rel_ts,
            msg.arbitration_id,
            int(msg.is_extended_id),
            len(msg.data),
            bytes(msg.data),
            data_hex,
            msg.channel if msg.channel is not None else "",
        ))
        self._msg_count += 1

        # 每 100 条提交一次，平衡性能和可靠性
        if self._msg_count % 100 == 0:
            self._conn.commit()

    def close(self):
        self._conn.commit()
        self._conn.close()


class CANLogger:
    """
    CAN 流量记录器

    支持格式:
      - asc:    Vector CANoe ASCII 格式 (行业标准)
      - csv:    通用 CSV 表格
      - sqlite: SQLite 结构化数据库
      - blf:    Vector BLF 二进制格式 (python-can 原生)

    Example:
        >>> mgr = CANBusManager(BusConfig(interface="virtual", channel="ch0"))
        >>> logger = CANLogger(mgr)
        >>> mgr.connect()
        >>> logger.start("capture.asc", format="asc")
        >>> # ... capture ...
        >>> stats = logger.stop()
        >>> print(f"Recorded {stats['message_count']} messages")
    """

    def __init__(self, bus_manager: CANBusManager):
        self._bus = bus_manager
        self._writer = None
        self._format: str = ""
        self._running = False
        self._lock = threading.Lock()

        # 统计
        self._msg_count = 0
        self._filter_ids: Optional[List[int]] = None  # 只记录指定 ID

    def set_filter(self, can_ids: List[int]):
        """设置记录过滤 (只记录指定 CAN ID 的报文)"""
        self._filter_ids = set(can_ids) if can_ids else None

    def start(self, filepath: str, format: str = "asc") -> bool:
        """开始记录

        Args:
            filepath: 输出文件路径
            format: 输出格式 (asc / csv / sqlite / blf)
        """
        if self._running:
            print("[LOG] Already recording. Stop first.")
            return False

        # 确保目录存在
        os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)

        self._format = format.lower()

        if self._format == "asc":
            self._writer = ASCWriter(filepath)
        elif self._format == "csv":
            self._writer = CSVWriter(filepath)
        elif self._format == "sqlite":
            self._writer = SQLiteWriter(filepath)
        elif self._format == "blf":
            # python-can 原生 BLF 支持
            self._writer = can.BLFWriter(filepath)
        else:
            print(f"[LOG] Unsupported format: {format}. Use asc/csv/sqlite/blf")
            return False

        self._msg_count = 0
        self._running = True

        # 注册回调
        self._bus.add_callback(self._on_message)

        print(f"[LOG] Recording started -> {filepath} ({self._format.upper()})")
        return True

    def stop(self) -> Dict[str, Any]:
        """停止记录, 返回统计信息"""
        if not self._running:
            return {"message_count": 0}

        self._running = False
        self._bus.remove_callback(self._on_message)

        if self._writer:
            self._writer.close()
            self._writer = None

        stats = {
            "message_count": self._msg_count,
            "format": self._format,
        }
        print(f"[LOG] Recording stopped. Total: {self._msg_count} messages")
        return stats

    def _on_message(self, msg: can.Message):
        """消息回调"""
        if not self._running or self._writer is None:
            return

        # 过滤
        if self._filter_ids is not None:
            if msg.arbitration_id not in self._filter_ids:
                return

        try:
            self._writer.write(msg)
            self._msg_count += 1
        except Exception as e:
            print(f"[LOG] Write error: {e}")

    @property
    def is_recording(self) -> bool:
        return self._running

    @property
    def message_count(self) -> int:
        return self._msg_count
