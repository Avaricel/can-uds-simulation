"""
发动机仿真模块 - 模拟发动机转速、水温、油压等信号

信号列表：
- EngineSpeed (rpm)        : 发动机转速
- CoolantTemp (degC)       : 冷却液温度
- EngineOilPressure (kPa)  : 机油压力
- IntakeAirTemp (degC)     : 进气温度
- ThrottlePosition (%)     : 节气门开度
- EngineLoad (%)           : 发动机负荷
- FuelConsumption (L/100km): 瞬时油耗
- BatteryVoltage (V)       : 蓄电池电压
"""

import math
import random
from typing import Dict

from .base import SignalGenerator, SignalSpec, VehicleState


# 信号规格
ENGINE_SPECS = {
    "EngineSpeed": SignalSpec(
        name="发动机转速", unit="rpm",
        min_val=0, max_val=8000, default_val=0,
        warning_max=5000, critical_max=6500,
        description="曲轴转速"
    ),
    "CoolantTemp": SignalSpec(
        name="冷却液温度", unit="°C",
        min_val=-40, max_val=215, default_val=25,
        warning_min=50, warning_max=105, critical_max=115,
        description="发动机冷却液温度"
    ),
    "EngineOilPressure": SignalSpec(
        name="机油压力", unit="kPa",
        min_val=0, max_val=700, default_val=0,
        warning_min=100, critical_min=50, critical_max=650,
        description="发动机机油压力"
    ),
    "IntakeAirTemp": SignalSpec(
        name="进气温度", unit="°C",
        min_val=-40, max_val=130, default_val=25,
        warning_max=80,
        description="进气歧管空气温度"
    ),
    "ThrottlePosition": SignalSpec(
        name="节气门开度", unit="%",
        min_val=0, max_val=100, default_val=0,
        description="电子节气门开度"
    ),
    "EngineLoad": SignalSpec(
        name="发动机负荷", unit="%",
        min_val=0, max_val=100, default_val=0,
        description="计算发动机负荷"
    ),
    "BatteryVoltage": SignalSpec(
        name="蓄电池电压", unit="V",
        min_val=0, max_val=16, default_val=12.6,
        warning_min=11.5, critical_min=10.5, critical_max=15.5,
        description="蓄电池端电压"
    ),
}


class EngineSimulator(SignalGenerator):
    """发动机信号仿真器"""

    def __init__(self, vehicle: VehicleState):
        super().__init__("Engine")
        self.vehicle = vehicle
        self.specs = ENGINE_SPECS

        # 内部状态
        self._coolant_temp = 25.0       # 当前水温
        self._oil_pressure = 0.0        # 当前油压
        self._warmup_progress = 0.0     # 暖机进度 0-1
        self._noise_seed = random.random()

    def update(self, dt: float) -> Dict[str, float]:
        if not self.vehicle.ignition:
            return self._engine_off_signals(dt)

        # 暖机过程
        self._warmup_progress = min(1.0, self._warmup_progress + dt / 180.0)  # 3分钟暖机

        # 目标转速：怠速800rpm + 油门影响
        target_rpm = 800 + self.vehicle.accelerator_pct * 55  # 最高约6300rpm
        target_rpm += random.gauss(0, 15)  # 自然波动

        # 转速平滑过渡
        current_rpm = self.vehicle.engine_speed
        smooth_rpm = current_rpm + (target_rpm - current_rpm) * min(1.0, dt * 10)
        self.vehicle.engine_speed = smooth_rpm

        # 冷却液温度（随暖机上升）
        target_coolant = 25 + (90 - 25) * self._warmup_progress
        target_coolant += smooth_rpm / 8000 * 15  # 高转速时温度更高
        self._coolant_temp += (target_coolant - self._coolant_temp) * dt * 0.5
        self._coolant_temp += random.gauss(0, 0.3)

        # 机油压力（随转速上升）
        if self.vehicle.engine_running or self.vehicle.accelerator_pct > 0:
            target_oil = 100 + smooth_rpm / 8000 * 400
            target_oil *= 1.0 + (1.0 - self._warmup_progress) * 0.3  # 冷车油压略高
        else:
            target_oil = 0
        self._oil_pressure += (target_oil - self._oil_pressure) * dt * 0.3

        # 节气门开度 ≈ 油门踏板
        throttle = self.vehicle.accelerator_pct + random.gauss(0, 1)

        # 发动机负荷 (简化模型)
        load = self.vehicle.accelerator_pct * 0.8 + random.gauss(0, 2)
        load = max(0, min(100, load))

        # 进气温度 ≈ 环境温度 + 发动机热辐射
        intake_temp = self.vehicle.ambient_temp + smooth_rpm / 8000 * 30
        intake_temp += random.gauss(0, 0.5)

        # 电池电压（运行中约14V，熄火12.6V）
        battery = 13.8 + random.gauss(0, 0.2)

        return {
            "EngineSpeed": round(smooth_rpm, 1),
            "CoolantTemp": round(self._coolant_temp, 1),
            "EngineOilPressure": round(self._oil_pressure, 1),
            "IntakeAirTemp": round(intake_temp, 1),
            "ThrottlePosition": round(throttle, 1),
            "EngineLoad": round(load, 1),
            "BatteryVoltage": round(battery, 2),
        }

    def _engine_off_signals(self, dt: float) -> Dict[str, float]:
        """发动机关闭时的信号值"""
        # 自然冷却
        if self._coolant_temp > self.vehicle.ambient_temp:
            self._coolant_temp -= dt * 2  # 缓慢降温
        self._oil_pressure = max(0, self._oil_pressure - dt * 200)
        self._warmup_progress = max(0, self._warmup_progress - dt / 600)
        self.vehicle.engine_speed = 0

        return {
            "EngineSpeed": 0,
            "CoolantTemp": round(self._coolant_temp, 1),
            "EngineOilPressure": 0,
            "IntakeAirTemp": round(self.vehicle.ambient_temp, 1),
            "ThrottlePosition": 0,
            "EngineLoad": 0,
            "BatteryVoltage": round(12.4 + random.gauss(0, 0.1), 2),
        }

    def reset(self):
        super().reset()
        self._coolant_temp = 25.0
        self._oil_pressure = 0.0
        self._warmup_progress = 0.0
