#!/usr/bin/env python3
"""
Vehicle Signal Simulator CLI - 车辆信号仿真器

用法:
    # 运行默认仿真（终端显示）
    python cli.py run    # 默认5秒
    python cli.py run --duration 10 --rate 100

    # 输出到文件
    python cli.py run --output csv --file simulation.csv
    python cli.py run --output json --file simulation.json

    # 故障注入模式
    python cli.py fault --type tpms_low
    python cli.py fault --type door_open

    # 自定义驾驶场景
    python cli.py scenario --name warmup    # 暖机场景
    python cli.py scenario --name accel     # 加速场景
"""

import argparse
import time
import sys
import random

from simulator.base import VehicleState
from simulator.engine import EngineSimulator
from simulator.transmission import TransmissionSimulator
from simulator.body import BodySimulator
from simulator.can_emitter import (
    CANEmitter, TextOutput, CSVOutput, JSONOutput,
    DASHBOARD_CAN_CONFIGS
)


def run_demo_scenario(scenario_name: str, vehicle: VehicleState):
    """预定义的驾驶场景"""
    if scenario_name == "warmup":
        # 冷启动暖机场景
        vehicle.ambient_temp = 5.0  # 冬天
        vehicle.start_ignition()
        # 怠速暖机，不踩油门
        for _ in range(100):
            yield 0.1
            # 保持怠速

    elif scenario_name == "accel":
        # 加速场景：0-100km/h
        vehicle.start_ignition()
        vehicle.gear_position = 3  # D挡
        # 缓慢加速
        for i in range(200):
            vehicle.accelerator_pct = min(100, i * 1.5)
            vehicle.brake_pct = 0
            yield 0.05

        # 巡航
        for _ in range(100):
            vehicle.accelerator_pct = 20
            vehicle.brake_pct = 0
            yield 0.05

        # 减速到停车
        for i in range(100):
            vehicle.accelerator_pct = 0
            vehicle.brake_pct = min(100, i * 2)
            yield 0.05

    elif scenario_name == "city":
        # 城市工况：走走停停
        vehicle.start_ignition()
        vehicle.gear_position = 3
        for _ in range(5):
            # 加速到40km/h
            for i in range(40):
                vehicle.accelerator_pct = 30
                vehicle.brake_pct = 0
                yield 0.05
            # 减速停车
            for i in range(30):
                vehicle.accelerator_pct = 0
                vehicle.brake_pct = 40
                yield 0.05
            # 等待
            for _ in range(20):
                vehicle.accelerator_pct = 0
                vehicle.brake_pct = 20
                yield 0.05

    elif scenario_name == "highway":
        # 高速巡航：120km/h
        vehicle.start_ignition()
        vehicle.gear_position = 3
        # 加速
        for i in range(150):
            vehicle.accelerator_pct = min(80, i * 1)
            yield 0.05
        # 巡航
        for _ in range(300):
            vehicle.accelerator_pct = 25
            yield 0.05
        # 减速
        for i in range(100):
            vehicle.accelerator_pct = 0
            vehicle.brake_pct = min(80, i * 1.5)
            yield 0.05

    else:
        # 默认场景：简单驾驶循环
        vehicle.start_ignition()
        vehicle.gear_position = 3
        for _ in range(300):
            vehicle.accelerator_pct = random.randint(0, 50)
            yield 0.05


def cmd_run(args):
    """运行仿真"""
    vehicle = VehicleState()

    # 创建仿真模块
    engine = EngineSimulator(vehicle)
    trans = TransmissionSimulator(vehicle)
    body_sim = BodySimulator(vehicle)

    # 设置输出
    if args.output == "csv":
        out = CSVOutput(args.file or "simulation.csv")
    elif args.output == "json":
        out = JSONOutput(args.file or "simulation.json")
    else:
        out = TextOutput(
            show_signals=not args.raw,
        )

    emitter = CANEmitter(output=out)
    emitter.start()

    dt = 1.0 / args.rate
    total_steps = int(args.duration / dt)
    elapsed = 0.0

    print(f"Vehicle Signal Simulator")
    print(f"   Scenario: {args.scenario}")
    print(f"   Duration: {args.duration}s @ {args.rate}Hz")
    print(f"   Output: {args.output}")
    print("-" * 60)

    scenario = run_demo_scenario(args.scenario, vehicle)

    for _ in range(total_steps):
        # 驱动场景迭代器
        try:
            next(scenario)
        except StopIteration:
            pass

        # 更新车速（简化物理模型）
        if vehicle.gear_position == 3 and vehicle.accelerator_pct > 0:
            # 加速
            accel = vehicle.accelerator_pct * 0.3  # 简化
            vehicle.vehicle_speed += accel * dt * 3.6  # m/s^2 -> km/h 增量
            vehicle.vehicle_speed = min(200, vehicle.vehicle_speed)
        elif vehicle.brake_pct > 0 or vehicle.accelerator_pct == 0:
            # 减速
            decel = max(vehicle.brake_pct * 0.2, 5)  # 最小阻力减速
            vehicle.vehicle_speed = max(0,
                vehicle.vehicle_speed - decel * dt * 3.6)

        # 更新各模块信号
        signals = {}
        signals.update(engine.update(dt))
        signals.update(trans.update(dt))
        signals.update(body_sim.update(dt))
        signals["VehicleSpeed"] = round(vehicle.vehicle_speed, 1)

        # 注入故障（如果有）
        if args.fault:
            body_sim.inject_fault(args.fault)

        # 发送CAN报文
        emitter.emit(signals, dt)

        elapsed += dt
        if elapsed >= args.duration:
            break

    emitter.stop()

    # 输出统计
    print(f"\n[STATS] Simulation Summary:")
    print(f"   Total CAN frames: {emitter.total_frames}")
    print(f"   Duration: {elapsed:.1f}s")
    if isinstance(out, (CSVOutput, JSONOutput)):
        print(f"   Output saved to: {args.file}")


def cmd_fault(args):
    """故障注入"""
    vehicle = VehicleState()
    body_sim = BodySimulator(vehicle)

    print(f"[WARN] Fault Injection: {args.type}")

    # 执行几步仿真
    for _ in range(10):
        body_sim.update(0.1)

    # 注入故障
    body_sim.inject_fault(args.type)

    # 读取故障后的状态
    signals = body_sim.update(0.1)

    if args.type == "tpms_low":
        print(f"   TPMS_FL: {signals.get('TPMS_FL')} kPa")
        print(f"   TPMS_Warning: {signals.get('TPMS_Warning')}")
    elif args.type == "door_open":
        print(f"   DoorFL: {signals.get('DoorFL')}")
    elif args.type == "fuel_low":
        print(f"   FuelLevel: {signals.get('FuelLevel')}%")

    print(f"\n[OK] Fault injected successfully. All affected signals:")
    for k, v in signals.items():
        print(f"   {k}: {v}")


def main():
    parser = argparse.ArgumentParser(
        description="Vehicle Signal Simulator - 车载信号仿真工具"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # run 子命令
    run_parser = subparsers.add_parser("run", help="运行仿真")
    run_parser.add_argument("--duration", "-d", type=float, default=10.0,
                            help="仿真时长（秒）")
    run_parser.add_argument("--rate", "-r", type=int, default=100,
                            help="仿真频率（Hz）")
    run_parser.add_argument("--scenario", "-s",
                            choices=["default", "warmup", "accel", "city", "highway"],
                            default="default", help="驾驶场景")
    run_parser.add_argument("--output", "-o",
                            choices=["text", "csv", "json"],
                            default="text", help="输出模式")
    run_parser.add_argument("--file", "-f",
                            help="输出文件路径（csv/json模式）")
    run_parser.add_argument("--fault", choices=["tpms_low", "tpms_high", "door_open", "fuel_low"],
                            help="注入故障类型")
    run_parser.add_argument("--raw", action="store_true",
                            help="仅显示原始CAN数据")
    run_parser.set_defaults(func=cmd_run)

    # fault 子命令
    fault_parser = subparsers.add_parser("fault", help="故障注入测试")
    fault_parser.add_argument("--type", "-t", required=True,
                              choices=["tpms_low", "tpms_high", "door_open", "fuel_low", "all_normal"],
                              help="故障类型")
    fault_parser.set_defaults(func=cmd_fault)

    # scenario 子命令
    scenario_parser = subparsers.add_parser("scenario", help="场景描述")
    scenario_parser.add_argument("--name", "-n",
                                 choices=["warmup", "accel", "city", "highway"],
                                 default="accel", help="场景名称")
    scenario_parser.set_defaults(func=lambda a: print(
        f"场景: {a.name}\n"
        f"用法: python cli.py run --scenario {a.name}"
    ))

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        # 默认：运行演示
        print("=" * 60)
        print("  Vehicle Signal Simulator - 车辆信号仿真器")
        print("=" * 60)
        print()
        print("运行默认场景（10秒，城市工况）...")
        print()
        cmd_run(argparse.Namespace(
            command="run", duration=5, rate=50, scenario="default",
            output="text", file=None, fault=None, raw=False,
        ))


if __name__ == "__main__":
    main()
