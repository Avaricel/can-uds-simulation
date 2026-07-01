#!/usr/bin/env python3
"""
Demo: 完整的车辆信号仿真演示

展示：
1. 发动机启动 → 暖机 → 怠速
2. 城市工况驾驶循环
3. 故障注入（胎压低、车门未关、低油量）
4. 多种输出格式（终端文本/CSV/JSON）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulator.base import VehicleState
from simulator.engine import EngineSimulator, ENGINE_SPECS
from simulator.transmission import TransmissionSimulator
from simulator.body import BodySimulator
from simulator.can_emitter import CANEmitter, TextOutput, CSVOutput


def demo_basic():
    """基础演示：启动 → 暖机 → 怠速 → 加速"""
    print("=" * 60)
    print("  Demo 1: 发动机启动 & 暖机 & 加速")
    print("=" * 60)

    vehicle = VehicleState()
    vehicle.ambient_temp = 10.0

    engine = EngineSimulator(vehicle)
    trans = TransmissionSimulator(vehicle)
    body_sim = BodySimulator(vehicle)

    emitter = CANEmitter(output=TextOutput(show_signals=True))
    emitter.start()

    dt = 0.1  # 100ms步进
    total_time = 0.0

    # Phase 1: 点火
    print("\n--- [Phase 1] IGNITION ON ---")
    vehicle.start_ignition()
    for _ in range(10):
        signals = gather_signals(engine, trans, body_sim, vehicle, dt)
        emitter.emit(signals, dt)
        total_time += dt

    # Phase 2: 怠速暖机 (10秒)
    print(f"\n--- [Phase 2] IDLE WARM-UP ---")
    for _ in range(100):
        signals = gather_signals(engine, trans, body_sim, vehicle, dt)
        emitter.emit(signals, dt)
        total_time += dt

    # Phase 3: 挂D挡，缓慢加速
    print(f"\n--- [Phase 3] ACCELERATION ---")
    trans.set_gear(3)  # D挡
    for i in range(80):
        vehicle.accelerator_pct = min(100, i * 2)
        vehicle.vehicle_speed += 1.0 * dt * 3.6  # 简单加速
        signals = gather_signals(engine, trans, body_sim, vehicle, dt)
        emitter.emit(signals, dt)
        total_time += dt

    # Phase 4: 停车熄火
    print(f"\n--- [Phase 4] STOP ---")
    vehicle.accelerator_pct = 0
    for i in range(30):
        vehicle.vehicle_speed = max(0, vehicle.vehicle_speed - 5 * dt * 3.6)
        signals = gather_signals(engine, trans, body_sim, vehicle, dt)
        emitter.emit(signals, dt)
        total_time += dt

    vehicle.stop_ignition()
    for _ in range(10):
        signals = gather_signals(engine, trans, body_sim, vehicle, dt)
        emitter.emit(signals, dt)

    emitter.stop()
    print(f"\n[OK] Demo 1 complete. Total frames: {emitter.total_frames}")


def demo_fault_injection():
    """演示故障注入"""
    print("\n" + "=" * 60)
    print("  Demo 2: 故障注入测试")
    print("=" * 60)

    vehicle = VehicleState()
    vehicle.start_ignition()

    body_sim = BodySimulator(vehicle)

    # 正常状态
    print("\n--- Normal state ---")
    for _ in range(5):
        body_sim.update(0.1)

    # 注入低胎压故障
    print("\n--- Inject: TPMS Low (FL tire burst) ---")
    body_sim.inject_fault("tpms_low")
    signals = body_sim.update(0.1)
    print(f"   TPMS_FL: {signals['TPMS_FL']:.1f} kPa  "
          f"(Warning: {signals['TPMS_Warning']})")

    # 恢复
    body_sim.inject_fault("all_normal")
    signals = body_sim.update(0.1)
    print(f"\n--- Recovered ---")
    print(f"   TPMS_FL: {signals['TPMS_FL']:.1f} kPa")

    # 车门未关
    print(f"\n--- Inject: Door Open ---")
    body_sim.inject_fault("door_open")
    signals = body_sim.update(0.1)
    print(f"   DoorFL: {signals['DoorFL']}")

    print("\n[OK] Demo 2 complete.")


def demo_csv_export():
    """演示CSV导出"""
    print("\n" + "=" * 60)
    print("  Demo 3: CSV数据导出")
    print("=" * 60)

    vehicle = VehicleState()
    vehicle.start_ignition()
    vehicle.gear_position = 3

    engine = EngineSimulator(vehicle)
    trans = TransmissionSimulator(vehicle)
    body_sim = BodySimulator(vehicle)

    out_path = "examples/exported_signals.csv"
    emitter = CANEmitter(output=CSVOutput(out_path))
    emitter.start()

    dt = 0.05
    for i in range(60):  # 3秒数据
        vehicle.accelerator_pct = 30
        vehicle.vehicle_speed = min(60, vehicle.vehicle_speed + 1 * dt * 3.6)
        signals = gather_signals(engine, trans, body_sim, vehicle, dt)
        emitter.emit(signals, dt)

    emitter.stop()
    print(f"[OK] Exported {emitter.total_frames} frames to {out_path}")


def gather_signals(engine, trans, body_sim, vehicle, dt):
    """汇聚所有仿真模块的信号"""
    signals = {}
    signals.update(engine.update(dt))
    signals.update(trans.update(dt))
    signals.update(body_sim.update(dt))
    signals["VehicleSpeed"] = round(vehicle.vehicle_speed, 1)
    return signals


if __name__ == "__main__":
    demo_basic()
    demo_fault_injection()
    demo_csv_export()

    print("\n" + "=" * 60)
    print("  All demos complete!")
    print("=" * 60)
