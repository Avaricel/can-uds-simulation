"""
DBC文件解析器 - 解析Vector DBC格式文件，提取报文和信号定义

DBC文件格式参考：Vector DBC File Format Specification
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class Signal:
    """CAN信号定义"""
    name: str                      # 信号名称
    start_bit: int                 # 起始位
    length: int                    # 位长度
    byte_order: str = "Intel"      # 字节序：Intel(Motorola LSB) / Motorola(MSB)
    value_type: str = "unsigned"   # 有符号/无符号
    factor: float = 1.0            # 缩放因子
    offset: float = 0.0            # 偏移量
    min_value: float = 0.0         # 最小值
    max_value: float = 0.0         # 最大值
    unit: str = ""                 # 单位 (km/h, rpm, V, etc.)
    comment: str = ""              # 注释
    receivers: List[str] = field(default_factory=list)  # 接收节点
    values: Dict[int, str] = field(default_factory=dict)  # 枚举值映射

    def decode(self, raw_value: int) -> float:
        """将原始值转换为物理值"""
        value = raw_value * self.factor + self.offset
        if self.value_type == "signed" and raw_value & (1 << (self.length - 1)):
            # 处理有符号数的符号扩展
            mask = (1 << self.length) - 1
            value = raw_value & mask
            if value & (1 << (self.length - 1)):
                value -= (1 << self.length)
            value = value * self.factor + self.offset
        return value

    def encode(self, physical_value: float) -> int:
        """将物理值编码为原始值"""
        return int((physical_value - self.offset) / self.factor)


@dataclass
class Message:
    """CAN报文定义"""
    can_id: int                    # CAN ID (十六进制)
    name: str                      # 报文名称
    dlc: int = 8                   # 数据长度
    sender: str = ""               # 发送节点
    cycle_time: int = 0            # 周期 (ms)
    comment: str = ""              # 注释
    signals: List[Signal] = field(default_factory=list)

    def get_signal(self, name: str) -> Optional[Signal]:
        """根据名称获取信号"""
        for sig in self.signals:
            if sig.name == name:
                return sig
        return None

    def decode_data(self, data: bytes) -> Dict[str, float]:
        """解码CAN数据帧，返回所有信号及其物理值"""
        results = {}
        for sig in self.signals:
            value = self._extract_signal_value(data, sig)
            results[sig.name] = sig.decode(value)
        return results

    @staticmethod
    def _extract_signal_value(data: bytes, signal: Signal) -> int:
        """从CAN数据中提取信号原始值"""
        start_bit = signal.start_bit
        length = signal.length

        value = 0
        bits_remaining = length

        while bits_remaining > 0:
            byte_idx = start_bit // 8
            bit_idx = start_bit % 8

            if byte_idx >= len(data):
                break

            bits_in_byte = min(8 - bit_idx, bits_remaining)
            mask = ((1 << bits_in_byte) - 1) << bit_idx
            byte_value = (data[byte_idx] & mask) >> bit_idx

            if signal.byte_order == "Motorola":
                value = (value << bits_in_byte) | byte_value
            else:
                value |= byte_value << (length - bits_remaining)

            bits_remaining -= bits_in_byte

            if signal.byte_order == "Intel":
                start_bit += bits_in_byte
            else:
                start_bit = (byte_idx + 1) * 8 + bit_idx

        return value


class DBCParser:
    """DBC文件解析器"""

    # 正则表达式模式
    RE_VERSION = re.compile(r'VERSION\s+"(.+)"')
    RE_BO = re.compile(r'BO_\s+(0x[0-9A-Fa-f]+|\d+)\s+(\w+)\s*:\s*(\d+)\s+(\w+)')
    RE_SG = re.compile(
        r'SG_\s+(\w+)\s*:?\s*(\d+)\|(\d+)@([01])([+-])\s+\(([\d.\-+eE]+),([\d.\-+eE]+)\)'
        r'\s+\[([\d.\-+eE]+)\|([\d.\-+eE]+)\]\s+"([^"]*)"\s+(.*)'
    )
    RE_SG_MUX = re.compile(r'SG_\s+(\w+)\s+(\w+)')
    RE_VAL = re.compile(r'VAL_\s+(0x[0-9A-Fa-f]+|\d+)\s+(\w+)\s+(.+)\s*;')
    RE_CM_BO = re.compile(r'CM_\s+BO_\s+(0x[0-9A-Fa-f]+|\d+)\s+"([^"]*)"')
    RE_CM_SG = re.compile(r'CM_\s+SG_\s+(0x[0-9A-Fa-f]+|\d+)\s+(\w+)\s+"([^"]*)"')
    RE_BA_DEF = re.compile(r'BA_DEF_\s+BO_\s+"([^"]+)"')
    RE_BA = re.compile(r'BA_\s+"([^"]*)"\s+BO_\s+(0x[0-9A-Fa-f]+|\d+)\s+(\d+)')

    def __init__(self):
        self.version: str = ""
        self.messages: Dict[int, Message] = {}
        self._current_message_id: Optional[int] = None

    def parse(self, filepath: str) -> Dict[int, Message]:
        """解析DBC文件，返回 {CAN_ID: Message} 字典"""
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('BA_ '):
                    self._parse_ba(line)
                    continue
                self._parse_line(line)
        return self.messages

    def parse_string(self, content: str) -> Dict[int, Message]:
        """解析DBC字符串内容"""
        for line in content.split('\n'):
            line = line.strip()
            if not line:
                continue
            self._parse_line(line)
        return self.messages

    def _parse_line(self, line: str):
        """解析单行"""
        # VERSION
        m = self.RE_VERSION.match(line)
        if m:
            self.version = m.group(1)
            return

        # BO_ (Message)
        m = self.RE_BO.match(line)
        if m:
            can_id = int(m.group(1), 0)
            name = m.group(2)
            dlc = int(m.group(3))
            sender = m.group(4)
            self.messages[can_id] = Message(
                can_id=can_id, name=name, dlc=dlc, sender=sender
            )
            self._current_message_id = can_id
            return

        # SG_ (Signal)
        m = self.RE_SG.match(line)
        if m and self._current_message_id is not None:
            name = m.group(1)
            start_bit = int(m.group(2))
            length = int(m.group(3))
            byte_order = "Motorola" if m.group(4) == '0' else "Intel"
            value_type = "signed" if m.group(5) == '-' else "unsigned"
            factor = float(m.group(6))
            offset = float(m.group(7))
            min_val = float(m.group(8))
            max_val = float(m.group(9))
            unit = m.group(10)
            receivers_str = m.group(11).strip()
            receivers = receivers_str.split(',') if receivers_str else []

            signal = Signal(
                name=name, start_bit=start_bit, length=length,
                byte_order=byte_order, value_type=value_type,
                factor=factor, offset=offset, min_value=min_val,
                max_value=max_val, unit=unit, receivers=receivers
            )
            self.messages[self._current_message_id].signals.append(signal)
            return

        # CM_ BO_
        m = self.RE_CM_BO.match(line)
        if m:
            can_id = int(m.group(1), 0)
            if can_id in self.messages:
                self.messages[can_id].comment = m.group(2)
            return

        # CM_ SG_
        m = self.RE_CM_SG.match(line)
        if m:
            can_id = int(m.group(1), 0)
            signal_name = m.group(2)
            comment = m.group(3)
            if can_id in self.messages:
                sig = self.messages[can_id].get_signal(signal_name)
                if sig:
                    sig.comment = comment
            return

        # VAL_ (Value table)
        m = self.RE_VAL.match(line)
        if m:
            can_id = int(m.group(1), 0)
            signal_name = m.group(2)
            value_pairs = m.group(3).strip()
            if can_id in self.messages:
                sig = self.messages[can_id].get_signal(signal_name)
                if sig:
                    pairs = re.findall(r'(\d+)\s+"([^"]*)"', value_pairs)
                    for val_str, val_name in pairs:
                        sig.values[int(val_str)] = val_name
            return

    def _parse_ba(self, line: str):
        """解析 BA_ 属性（如报文的周期时间）"""
        m = self.RE_BA.match(line)
        if m:
            attr_name = m.group(1)
            can_id = int(m.group(2), 0)
            value = int(m.group(3))
            if can_id in self.messages and 'Cycle' in attr_name:
                self.messages[can_id].cycle_time = value

    def get_messages_by_sender(self, sender: str) -> List[Message]:
        """按发送节点筛选报文"""
        return [m for m in self.messages.values() if m.sender == sender]

    def get_message_names(self) -> List[str]:
        """获取所有报文名称"""
        return [f"{m.can_id:#05x} ({m.name})" for m in self.messages.values()]

    def get_cycle_messages(self, min_cycle: int = 0) -> List[Message]:
        """获取周期报文（周期 >= min_cycle ms）"""
        return [m for m in self.messages.values()
                if m.cycle_time >= min_cycle and m.cycle_time > 0]

    def summary(self) -> str:
        """生成DBC摘要"""
        lines = [f"DBC Version: {self.version}",
                 f"Total Messages: {len(self.messages)}",
                 f"Total Signals: {sum(len(m.signals) for m in self.messages.values())}",
                 "-" * 50]
        for msg in self.messages.values():
            cycle_info = f", Cycle: {msg.cycle_time}ms" if msg.cycle_time else ""
            lines.append(f"  {msg.can_id:#05x} | {msg.name} | DLC:{msg.dlc}{cycle_info}")
            for sig in msg.signals:
                unit_str = f" [{sig.unit}]" if sig.unit else ""
                lines.append(f"    - {sig.name}: {sig.start_bit}|{sig.length}@{sig.byte_order[0]} "
                             f"({sig.factor},{sig.offset}){unit_str}")
        return '\n'.join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        parser = DBCParser()
        parser.parse(sys.argv[1])
        print(parser.summary())
    else:
        print("Usage: python dbc_parser.py <dbc_file>")
