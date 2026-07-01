"""
信号基类 - 所有仿真信号的基础模型
"""

import math
import time
import random
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class SignalSpec:
    """信号规格定义"""
    name: str
    unit: str = ""
    min_val: float = 0.0
    max_val: float = 100.0
    default_val: float = 0.0
    description: str = ""
    # 报警阈值
    warning_min: Optional[float] = None
    warning_max: Optional[float] = None
    critical_min: Optional[float] = None
    critical_max: Optional[float] = None

    def clamp(self, value: float) -> float:
        """将值限制在有效范围内"""
        return max(self.min_val, min(self.max_val, value))

    def check_alarm(self, value: float) -> str:
        """检查是否触发报警: "normal" | "warning" | "critical" """
        if self.critical_min is not None and value < self.critical_min:
            return "critical"
        if self.critical_max is not None and value > self.critical_max:
            return "critical"
        if self.warning_min is not None and value < self.warning_min:
            return "warning"
        if self.warning_max is not None and value > self.warning_max:
            return "warning"
        return "normal"


class SignalGenerator(ABC):
    """信号生成器基类"""

    def __init__(self, name: str):
        self.name = name
        self._time = 0.0
        self._dt = 0.01  # 默认10ms步进

    @abstractmethod
    def update(self, dt: float) -> Dict[str, float]:
        """更新信号，返回 {信号名: 值} 字典"""
        pass

    def step(self, dt: float = 0.01) -> Dict[str, float]:
        """单步执行"""
        self._dt = dt
        self._time += dt
        return self.update(dt)

    def reset(self):
        """重置状态"""
        self._time = 0.0


class VehicleState:
    """全局车辆状态"""
    def __init__(self):
        self.ignition = False          # 点火状态
        self.engine_running = False    # 发动机运行
        self.gear_position = 0         # 挡位: 0=P, 1=R, 2=N, 3=D
        self.vehicle_speed = 0.0       # 车速 (km/h)
        self.engine_speed = 0.0        # 发动机转速 (rpm)
        self.accelerator_pct = 0.0     # 油门踏板 (%)
        self.brake_pct = 0.0           # 刹车踏板 (%)
        self.steering_angle = 0.0      # 方向盘转角 (度)
        self.ambient_temp = 25.0       # 环境温度 (degC)
        self.battery_voltage = 12.6    # 电池电压 (V)
        self.odometer = 50000.0        # 里程 (km)
        self.fuel_level = 80.0         # 油量 (%)
        self.low_beam = False
        self.high_beam = False
        self.turn_signal = 0           # 0=off, 1=left, 2=right, 3=hazard
        self.handbrake = True
        self.door_status = {           # 0=closed, 1=ajar, 2=open
            "FL": 0, "FR": 0, "RL": 0, "RR": 0,
            "trunk": 0, "hood": 0,
        }

    def start_ignition(self):
        self.ignition = True
        self.engine_speed = 800  # 怠速

    def stop_ignition(self):
        self.ignition = False
        self.engine_running = False
        self.engine_speed = 0
        self.vehicle_speed = 0
