"""
CAN报文解析器 - 支持多种CAN日志格式的解析和信号解码
"""

import re
from typing import Dict, Generator, List, Optional, Tuple
from datetime import datetime
from collections import defaultdict

from .dbc_parser import DBCParser, Message


class CANFrame:
    """单帧CAN报文"""

    def __init__(self, timestamp: float, can_id: int, data: bytes,
                 interface: str = "", direction: str = "Rx"):
        self.timestamp = timestamp
        self.can_id = can_id
        self.data = data
        self.length = len(data)
        self.interface = interface
        self.direction = direction

    def __repr__(self):
        hex_data = ' '.join(f'{b:02X}' for b in self.data)
        return (f"CANFrame(ts={self.timestamp:.6f}, id={self.can_id:#05x}, "
                f"dlc={self.length}, data=[{hex_data}], dir={self.direction})")

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "can_id": self.can_id,
            "can_id_hex": f"0x{self.can_id:03X}",
            "data": list(self.data),
            "data_hex": ' '.join(f'{b:02X}' for b in self.data),
            "length": self.length,
            "interface": self.interface,
            "direction": self.direction,
        }


class CANLogParser:
    """CAN日志解析器 - 支持多种格式"""

    # 常见CANoe ASCII日志格式： 0.000000 1  2F4        Rx   d 8 00 00 00 00 00 00 00 00
    RE_CANOE_ASC = re.compile(
        r'^\s*([\d.]+)\s+\d+\s+([0-9A-Fa-f]+)\s+(Rx|Tx)\s+d\s+(\d+)\s+([0-9A-Fa-f\s]+)$'
    )

    # 通用CAN日志格式： (000.001234) can0 2F4#0000000000000000
    RE_CANDUMP = re.compile(
        r'\(([\d.]+)\)\s+(\w+)\s+([0-9A-Fa-f]+)#([0-9A-Fa-f]+)'
    )

    # Vector BLF / ASC 简化解析
    RE_GENERIC_CAN = re.compile(
        r'([\d.]+)\s+([0-9A-Fa-f]+)\s+([0-9A-Fa-f\s]+)'
    )

    FORMAT_AUTO = "auto"
    FORMAT_CANOE_ASC = "canoe_asc"
    FORMAT_CANDUMP = "candump"
    FORMAT_CSV = "csv"

    def __init__(self, dbc_parser: Optional[DBCParser] = None):
        self.dbc = dbc_parser
        self.frames: List[CANFrame] = []
        self._stats = defaultdict(int)

    def load_file(self, filepath: str,
                  fmt: str = FORMAT_AUTO,
                  encoding: str = 'utf-8') -> List[CANFrame]:
        """加载CAN日志文件"""
        self.frames = []
        self._stats.clear()

        with open(filepath, 'r', encoding=encoding, errors='ignore') as f:
            for line in f:
                frame = self._parse_line(line.strip(), fmt)
                if frame:
                    self.frames.append(frame)
                    self._stats[frame.can_id] += 1

        return self.frames

    def load_string(self, content: str, fmt: str = FORMAT_AUTO) -> List[CANFrame]:
        """从字符串解析CAN日志"""
        self.frames = []
        for line in content.split('\n'):
            frame = self._parse_line(line.strip(), fmt)
            if frame:
                self.frames.append(frame)
                self._stats[frame.can_id] += 1
        return self.frames

    def load_from_list(self, raw_frames: List[Tuple[float, int, bytes]]) -> List[CANFrame]:
        """从原始数据列表加载"""
        self.frames = []
        for ts, can_id, data in raw_frames:
            frame = CANFrame(ts, can_id, data)
            self.frames.append(frame)
            self._stats[can_id] += 1
        return self.frames

    def _parse_line(self, line: str, fmt: str) -> Optional[CANFrame]:
        """解析单行"""
        if not line or line.startswith(';') or line.startswith('//'):
            return None

        # CANoe ASC格式
        m = self.RE_CANOE_ASC.match(line)
        if m:
            ts = float(m.group(1))
            can_id = int(m.group(2), 16)
            direction = m.group(3)
            dlc = int(m.group(4))
            hex_data = m.group(5).strip()
            data = bytes.fromhex(hex_data)
            return CANFrame(ts, can_id, data[:dlc], direction=direction)

        # candump格式
        m = self.RE_CANDUMP.match(line)
        if m:
            ts = float(m.group(1))
            interface = m.group(2)
            can_id = int(m.group(3), 16)
            hex_data = m.group(4)
            data = bytes.fromhex(hex_data)
            return CANFrame(ts, can_id, data[:8], interface=interface)

        # 简单格式：时间戳 ID 十六进制数据
        parts = line.split()
        if len(parts) >= 3:
            try:
                ts = float(parts[0])
                can_id = int(parts[1], 16)
                hex_str = ''.join(parts[2:])
                data = bytes.fromhex(hex_str)
                return CANFrame(ts, can_id, data[:8])
            except (ValueError, IndexError):
                pass

        return None

    def decode_with_dbc(self) -> List[Dict]:
        """使用DBC解码所有报文，返回信号值列表"""
        if not self.dbc:
            return []
        results = []
        for frame in self.frames:
            msg = self.dbc.messages.get(frame.can_id)
            if msg:
                decoded = {
                    "timestamp": frame.timestamp,
                    "can_id": frame.can_id,
                    "can_id_hex": f"0x{frame.can_id:03X}",
                    "message_name": msg.name,
                    "signals": msg.decode_data(frame.data),
                    "raw_data": ' '.join(f'{b:02X}' for b in frame.data),
                }
                results.append(decoded)
        return results

    def filter_by_id(self, can_id: int) -> List[CANFrame]:
        """按CAN ID过滤"""
        return [f for f in self.frames if f.can_id == can_id]

    def filter_by_ids(self, can_ids: List[int]) -> List[CANFrame]:
        """按多个CAN ID过滤"""
        id_set = set(can_ids)
        return [f for f in self.frames if f.can_id in id_set]

    def filter_by_time(self, start: float, end: float) -> List[CANFrame]:
        """按时间范围过滤"""
        return [f for f in self.frames if start <= f.timestamp <= end]

    def get_statistics(self) -> Dict:
        """获取统计信息"""
        if not self.frames:
            return {}

        total = len(self.frames)
        times = [f.timestamp for f in self.frames]
        duration = times[-1] - times[0] if len(times) > 1 else 0

        # 按CAN ID分组统计
        id_stats = {}
        for can_id, count in sorted(self._stats.items(),
                                     key=lambda x: x[1], reverse=True):
            frames = self.filter_by_id(can_id)
            avg_interval = 0
            if len(frames) > 1:
                intervals = [frames[i+1].timestamp - frames[i].timestamp
                           for i in range(len(frames)-1)]
                avg_interval = sum(intervals) / len(intervals) * 1000  # ms

            msg_name = ""
            if self.dbc and can_id in self.dbc.messages:
                msg_name = self.dbc.messages[can_id].name

            id_stats[f"0x{can_id:03X}"] = {
                "count": count,
                "message_name": msg_name,
                "frequency_hz": count / duration if duration > 0 else 0,
                "avg_interval_ms": round(avg_interval, 2),
                "percentage": round(count / total * 100, 1),
            }

        return {
            "total_frames": total,
            "duration_seconds": round(duration, 3),
            "unique_can_ids": len(self._stats),
            "avg_frames_per_second": round(total / duration, 1) if duration > 0 else 0,
            "can_id_breakdown": id_stats,
        }

    def export_csv(self, filepath: str):
        """导出为CSV"""
        import csv
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Timestamp", "CAN_ID", "DLC", "Data", "Direction"])
            for frame in self.frames:
                writer.writerow([
                    f"{frame.timestamp:.6f}",
                    f"0x{frame.can_id:03X}",
                    frame.length,
                    ' '.join(f'{b:02X}' for b in frame.data),
                    frame.direction
                ])

    def get_unique_cycles(self, can_id: int) -> List[float]:
        """获取指定CAN ID报文的周期时间(ms)列表"""
        frames = self.filter_by_id(can_id)
        if len(frames) < 2:
            return []
        return [(frames[i+1].timestamp - frames[i].timestamp) * 1000
                for i in range(len(frames)-1)]
