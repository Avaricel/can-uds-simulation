"""
变速箱仿真模块 - 模拟挡位、变速箱油温

信号列表：
- GearPosition (enum)     : 挡位 (0=P, 1=R, 2=N, 3=D)
- GearShiftMode (enum)    : 换挡模式 (0=Normal, 1=Sport, 2=Eco)
- TransmissionOilTemp (°C) : 变速箱油温
- TorqueConverterSlip (%) : 液力变矩器滑差
"""

from typing import Dict

from .base import SignalGenerator, SignalSpec, VehicleState


TRANS_SPECS = {
    "GearPosition": SignalSpec(
        name="挡位", unit="",
        min_val=0, max_val=15, default_val=0,
        description="当前挡位: 0=P, 1=R, 2=N, 3=D"
    ),
    "GearShiftMode": SignalSpec(
        name="换挡模式", unit="",
        min_val=0, max_val=3, default_val=0,
        description="0=Normal, 1=Sport, 2=Eco"
    ),
    "TransOilTemp": SignalSpec(
        name="变速箱油温", unit="°C",
        min_val=-40, max_val=215, default_val=25,
        warning_max=120, critical_max=135,
        description="自动变速箱油温"
    ),
}


class TransmissionSimulator(SignalGenerator):
    """变速箱信号仿真器"""

    GEAR_NAMES = {0: "P", 1: "R", 2: "N", 3: "D"}
    MODE_NAMES = {0: "Normal", 1: "Sport", 2: "Eco"}

    def __init__(self, vehicle: VehicleState):
        super().__init__("Transmission")
        self.vehicle = vehicle
        self.specs = TRANS_SPECS
        self._trans_temp = 25.0
        self._current_gear = 3  # 默认D挡
        self._shift_mode = 0     # 默认Normal模式

    def set_gear(self, gear: int):
        """设置挡位 (0=P, 1=R, 2=N, 3=D)"""
        if gear in (0, 1, 2, 3):
            self._current_gear = gear
            self.vehicle.gear_position = gear

    def set_mode(self, mode: int):
        """设置换挡模式 (0=Normal, 1=Sport, 2=Eco)"""
        if mode in (0, 1, 2):
            self._shift_mode = mode

    def update(self, dt: float) -> Dict[str, float]:
        # 变速箱油温（随运行时间上升）
        if self.vehicle.engine_speed > 0:
            target_temp = 60 + self.vehicle.engine_speed / 8000 * 40
            self._trans_temp += (target_temp - self._trans_temp) * dt * 0.05
        else:
            # 自然冷却
            if self._trans_temp > self.vehicle.ambient_temp:
                self._trans_temp -= dt * 0.5

        # 车速不为0且挂入D挡才能行驶
        if self._current_gear == 3 and self.vehicle.accelerator_pct > 0:
            self.vehicle.gear_position = 3
        else:
            self.vehicle.gear_position = self._current_gear

        # 液力变矩器滑差（低速时滑差大）
        slip = 0
        if self.vehicle.engine_speed > 0 and self.vehicle.vehicle_speed < 10:
            slip = max(0, 100 - self.vehicle.vehicle_speed * 10)

        return {
            "GearPosition": self._current_gear,
            "GearShiftMode": self._shift_mode,
            "TransOilTemp": round(self._trans_temp, 1),
            "TorqueConverterSlip": round(slip, 1),
        }

    def reset(self):
        super().reset()
        self._trans_temp = 25.0
        self._current_gear = 3
        self._shift_mode = 0
