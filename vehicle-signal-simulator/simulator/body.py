"""
车身模块 - 模拟灯光、门锁、胎压等信号

信号列表：
- LowBeam (bool)         : 近光灯
- HighBeam (bool)        : 远光灯
- TurnSignal (enum)      : 转向灯 (0=off, 1=left, 2=right, 3=hazard)
- FogLight (bool)        : 雾灯
- BrakeLight (bool)      : 刹车灯
- ParkingBrake (bool)    : 驻车制动
- DoorStatus (enum)      : 门状态 (各门独立)
- TPMS_Pressure (kPa)    : 胎压 (各轮独立)
- TPMS_Warning (bool)    : 胎压告警
- FuelLevel (%)          : 油量
- Odometer (km)          : 里程
- AmbientTemp (°C)       : 环境温度
"""

import random
from typing import Dict, Tuple

from .base import SignalGenerator, SignalSpec, VehicleState


BODY_SPECS = {
    "FuelLevel": SignalSpec(
        name="油量", unit="%",
        min_val=0, max_val=100, default_val=100,
        warning_min=15, critical_min=5,
        description="燃油液位百分比"
    ),
    "Odometer": SignalSpec(
        name="总里程", unit="km",
        min_val=0, max_val=999999, default_val=0,
        description="累计行驶里程"
    ),
    "AmbientTemp": SignalSpec(
        name="环境温度", unit="°C",
        min_val=-40, max_val=85, default_val=25,
        description="车外环境温度"
    ),
    "TPMS_FL": SignalSpec(
        name="左前胎压", unit="kPa",
        min_val=0, max_val=500, default_val=250,
        warning_min=200, critical_min=170, critical_max=350,
    ),
    "TPMS_FR": SignalSpec(
        name="右前胎压", unit="kPa",
        min_val=0, max_val=500, default_val=250,
        warning_min=200, critical_min=170, critical_max=350,
    ),
    "TPMS_RL": SignalSpec(
        name="左后胎压", unit="kPa",
        min_val=0, max_val=500, default_val=250,
        warning_min=200, critical_min=170, critical_max=350,
    ),
    "TPMS_RR": SignalSpec(
        name="右后胎压", unit="kPa",
        min_val=0, max_val=500, default_val=250,
        warning_min=200, critical_min=170, critical_max=350,
    ),
}


class BodySimulator(SignalGenerator):
    """车身信号仿真器"""

    TURN_NAMES = {0: "Off", 1: "Left", 2: "Right", 3: "Hazard"}
    DOOR_NAMES = {0: "Closed", 1: "Ajar", 2: "Open", 3: "Fault"}

    def __init__(self, vehicle: VehicleState):
        super().__init__("Body")
        self.vehicle = vehicle
        self.specs = BODY_SPECS

        # 胎压初始值（带微小差异）
        self._tpms = {
            "FL": 250 + random.gauss(0, 5),
            "FR": 250 + random.gauss(0, 5),
            "RL": 250 + random.gauss(0, 5),
            "RR": 250 + random.gauss(0, 5),
        }

    def toggle_low_beam(self):
        self.vehicle.low_beam = not self.vehicle.low_beam
        if self.vehicle.low_beam:
            self.vehicle.high_beam = False

    def toggle_high_beam(self):
        self.vehicle.high_beam = not self.vehicle.high_beam
        if self.vehicle.high_beam:
            self.vehicle.low_beam = True

    def set_turn_signal(self, state: int):
        """设置转向灯: 0=off, 1=left, 2=right, 3=hazard"""
        self.vehicle.turn_signal = state

    def toggle_handbrake(self):
        self.vehicle.handbrake = not self.vehicle.handbrake

    def set_door(self, door: str, status: int):
        """设置门状态: 0=closed, 1=ajar, 2=open"""
        if door in self.vehicle.door_status:
            self.vehicle.door_status[door] = status

    def set_tpms(self, wheel: str, pressure: float):
        """设置胎压"""
        if wheel in self._tpms:
            self._tpms[wheel] = pressure

    def update(self, dt: float) -> Dict[str, float]:
        # 油量消耗
        if self.vehicle.engine_speed > 0:
            # 怠速油耗 ~0.5L/h, 全油门 ~30L/h
            fuel_rate = (0.5 + self.vehicle.accelerator_pct / 100 * 29.5) / 3600
            self.vehicle.fuel_level = max(0, self.vehicle.fuel_level - fuel_rate * dt)
        self.vehicle.fuel_level = round(self.vehicle.fuel_level, 2)

        # 里程累计（车速>0时）
        if self.vehicle.vehicle_speed > 0:
            self.vehicle.odometer += self.vehicle.vehicle_speed * dt / 3600
        self.vehicle.odometer = round(self.vehicle.odometer, 1)

        # 胎压随温度微调
        for wheel in self._tpms:
            self._tpms[wheel] += random.gauss(0, 0.01)
            self._tpms[wheel] = max(0, min(500, self._tpms[wheel]))

        # 刹车灯（刹车踏板>5%时亮）
        brake_light = self.vehicle.brake_pct > 5

        return {
            "LowBeam": int(self.vehicle.low_beam),
            "HighBeam": int(self.vehicle.high_beam),
            "TurnSignal": self.vehicle.turn_signal,
            "FogLight": 0,
            "BrakeLight": int(brake_light),
            "ParkingBrake": int(self.vehicle.handbrake),
            "DoorFL": self.vehicle.door_status["FL"],
            "DoorFR": self.vehicle.door_status["FR"],
            "DoorRL": self.vehicle.door_status["RL"],
            "DoorRR": self.vehicle.door_status["RR"],
            "Trunk": self.vehicle.door_status["trunk"],
            "Hood": self.vehicle.door_status["hood"],
            "TPMS_FL": round(self._tpms["FL"], 1),
            "TPMS_FR": round(self._tpms["FR"], 1),
            "TPMS_RL": round(self._tpms["RL"], 1),
            "TPMS_RR": round(self._tpms["RR"], 1),
            "TPMS_Warning": int(any(p < 200 for p in self._tpms.values())),
            "FuelLevel": self.vehicle.fuel_level,
            "Odometer": self.vehicle.odometer,
            "AmbientTemp": round(self.vehicle.ambient_temp, 1),
        }

    def inject_fault(self, fault_type: str):
        """注入故障（用于故障注入测试）"""
        if fault_type == "tpms_low":
            self._tpms["FL"] = 150  # 左前轮胎压低
        elif fault_type == "tpms_high":
            self._tpms["RR"] = 380  # 右后轮胎压高
        elif fault_type == "door_open":
            self.vehicle.door_status["FL"] = 2
        elif fault_type == "fuel_low":
            self.vehicle.fuel_level = 8
        elif fault_type == "all_normal":
            self._tpms = {k: 250 for k in self._tpms}
            self.vehicle.fuel_level = 80
            for d in self.vehicle.door_status:
                self.vehicle.door_status[d] = 0

    def reset(self):
        super().reset()
        self._tpms = {k: 250 + random.gauss(0, 5) for k in self._tpms}
