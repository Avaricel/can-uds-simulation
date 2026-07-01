"""
CAN报文发送器 - 将仿真信号组装为CAN报文并输出

支持多种输出模式：
- text: 终端文本输出
- csv: CSV文件输出
- json: JSON文件输出
- can: 通过python-can发送到真实总线
"""

import json
import csv
import struct
import time
from typing import Dict, List, Optional, Callable, TextIO
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class CANMessageConfig:
    """CAN报文配置：定义每个CAN ID包含哪些信号"""
    can_id: int
    name: str
    cycle_ms: int = 100
    signals: List[str] = field(default_factory=list)
    signal_formats: Dict[str, str] = field(default_factory=dict)
    _packed: bytes = b""

    def pack(self, signal_values: Dict[str, float]) -> bytes:
        """将信号值打包为CAN数据帧"""
        data = bytearray(8)

        for sig_name, fmt in self.signal_formats.items():
            if sig_name in signal_values:
                value = signal_values[sig_name]
                offset, length, factor, byte_order = self._parse_format(fmt)

                # 编码为整数
                raw = int(value / factor)
                raw = max(0, min((1 << length) - 1, raw))

                # 按位写入
                for i in range(length):
                    bit_pos = offset + (length - 1 - i if byte_order == "Motorola" else i)
                    byte_idx = bit_pos // 8
                    bit_idx = bit_pos % 8
                    if byte_idx < 8:
                        if raw & (1 << i):
                            data[byte_idx] |= (1 << bit_idx)
                        else:
                            data[byte_idx] &= ~(1 << bit_idx)

        return bytes(data)

    @staticmethod
    def _parse_format(fmt: str) -> tuple:
        """解析信号格式: offset,length,factor,byteorder (如 "0,16,0.25,Intel")"""
        parts = fmt.split(",")
        if len(parts) < 4:
            return 0, 16, 1.0, "Intel"
        return int(parts[0]), int(parts[1]), float(parts[2]), parts[3].strip()


# 仪表域CAN报文布局定义
DASHBOARD_CAN_CONFIGS = [
    CANMessageConfig(
        can_id=0x0C8, name="IC_Dashboard", cycle_ms=10,
        signals=["EngineSpeed", "VehicleSpeed", "CoolantTemp", "FuelLevel"],
        signal_formats={
            "EngineSpeed": "0,16,0.25,Intel",
            "VehicleSpeed": "16,16,0.01,Intel",
            "CoolantTemp": "32,8,1,Intel",
            "FuelLevel": "40,8,0.4,Intel",
        }
    ),
    CANMessageConfig(
        can_id=0x130, name="IC_Lamps", cycle_ms=50,
        signals=["TurnSignal", "HighBeam", "LowBeam", "FogLight", "BrakeLight", "ParkingBrake"],
        signal_formats={
            "TurnSignal": "0,2,1,Intel",
            "HighBeam": "2,1,1,Intel",
            "LowBeam": "3,1,1,Intel",
            "FogLight": "4,1,1,Intel",
            "BrakeLight": "5,1,1,Intel",
            "ParkingBrake": "6,1,1,Intel",
        }
    ),
    CANMessageConfig(
        can_id=0x152, name="IC_GearInfo", cycle_ms=100,
        signals=["GearPosition", "GearShiftMode", "TransOilTemp"],
        signal_formats={
            "GearPosition": "0,4,1,Intel",
            "GearShiftMode": "4,2,1,Intel",
            "TransOilTemp": "16,8,1,Intel",
        }
    ),
    CANMessageConfig(
        can_id=0x1A4, name="IC_Doors", cycle_ms=200,
        signals=["DoorFL", "DoorFR", "DoorRL", "DoorRR", "Trunk", "Hood"],
        signal_formats={
            "DoorFL": "0,2,1,Intel",
            "DoorFR": "2,2,1,Intel",
            "DoorRL": "4,2,1,Intel",
            "DoorRR": "6,2,1,Intel",
            "Trunk": "8,2,1,Intel",
            "Hood": "10,2,1,Intel",
        }
    ),
    CANMessageConfig(
        can_id=0x236, name="IC_TPMS", cycle_ms=500,
        signals=["TPMS_FL", "TPMS_FR", "TPMS_RL", "TPMS_RR", "TPMS_Warning"],
        signal_formats={
            "TPMS_FL": "0,8,1,Intel",
            "TPMS_FR": "8,8,1,Intel",
            "TPMS_RL": "16,8,1,Intel",
            "TPMS_RR": "24,8,1,Intel",
            "TPMS_Warning": "32,1,1,Intel",
        }
    ),
]


class OutputInterface(ABC):
    """输出接口基类"""
    @abstractmethod
    def write(self, timestamp: float, can_id: int, data: bytes, signals: Dict):
        pass

    @abstractmethod
    def close(self):
        pass


class TextOutput(OutputInterface):
    """终端文本输出"""
    def __init__(self, show_signals: bool = True):
        self.show_signals = show_signals

    def write(self, timestamp: float, can_id: int, data: bytes, signals: Dict):
        hex_data = ' '.join(f'{b:02X}' for b in data)
        line = f"[{timestamp:10.3f}] {can_id:#05x}  {hex_data}"
        if self.show_signals and signals:
            sig_str = '  '.join(f'{k}={v}' for k, v in signals.items())
            line += f"  |  {sig_str}"
        print(line)

    def close(self):
        pass


class CSVOutput(OutputInterface):
    """CSV文件输出"""
    def __init__(self, filepath: str):
        self.file = open(filepath, 'w', newline='', encoding='utf-8')
        self.writer = csv.writer(self.file)
        self.writer.writerow(["Timestamp", "CAN_ID", "Data", "Signals"])

    def write(self, timestamp: float, can_id: int, data: bytes, signals: Dict):
        hex_data = ' '.join(f'{b:02X}' for b in data)
        sig_str = json.dumps(signals, ensure_ascii=False)
        self.writer.writerow([f"{timestamp:.3f}", f"0x{can_id:03X}", hex_data, sig_str])

    def close(self):
        self.file.close()


class JSONOutput(OutputInterface):
    """JSON文件输出"""
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.records = []

    def write(self, timestamp: float, can_id: int, data: bytes, signals: Dict):
        self.records.append({
            "timestamp": round(timestamp, 3),
            "can_id": can_id,
            "can_id_hex": f"0x{can_id:03X}",
            "data": ' '.join(f'{b:02X}' for b in data),
            "signals": signals,
        })

    def close(self):
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.records, f, indent=2, ensure_ascii=False)
        print(f"Exported {len(self.records)} frames to {self.filepath}")


class CANEmitter:
    """
    CAN报文发送器

    用法:
        emitter = CANEmitter(output=TextOutput())
        emitter.start()

        # 循环发送
        while running:
            all_signals = {
                **engine.update(dt),
                **trans.update(dt),
                **body.update(dt),
            }
            emitter.emit(all_signals, dt)
    """

    def __init__(self, output: OutputInterface = None,
                 configs: List[CANMessageConfig] = None):
        self.configs = configs or DASHBOARD_CAN_CONFIGS
        self.output = output or TextOutput()
        self._timers: Dict[int, float] = {}  # can_id -> 距离下次发送的时间
        self._total_frames = 0
        self._start_time = 0.0

    def start(self):
        self._start_time = time.time()
        self._timers = {cfg.can_id: 0.0 for cfg in self.configs}

    def emit(self, signal_values: Dict[str, float], dt: float):
        """发送一轮CAN报文"""
        for cfg in self.configs:
            self._timers[cfg.can_id] -= dt
            if self._timers[cfg.can_id] <= 0:
                # 发送
                data = cfg.pack(signal_values)
                signals = {s: signal_values[s] for s in cfg.signals
                          if s in signal_values}

                elapsed = time.time() - self._start_time
                self.output.write(elapsed, cfg.can_id, data, signals)

                self._total_frames += 1
                self._timers[cfg.can_id] += cfg.cycle_ms / 1000.0

    def stop(self):
        self.output.close()

    @property
    def total_frames(self) -> int:
        return self._total_frames
