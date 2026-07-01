#!/usr/bin/env python3
"""
Demo: 演示 CAN Message Analyzer 的完整工作流程
"""
import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from can_analyzer.dbc_parser import DBCParser
from can_analyzer.can_parser import CANLogParser, CANFrame
from can_analyzer.visualizer import SignalVisualizer, plot_signals


def generate_demo_log():
    """生成模拟的CAN日志数据"""
    import math
    frames = []
    ts = 0.0
    # 模拟10秒数据
    while ts < 10.0:
        # 仪表报文 0x0C8 (10ms周期)
        rpm = int(800 + 300 * math.sin(ts * 2))  # 模拟发动机转速波动
        speed = int(ts * 5)  # 逐渐加速
        coolant = int(85 + 5 * math.sin(ts * 0.5))
        fuel = max(0, 100 - ts * 2)  # 油量缓慢下降
        data_0C8 = bytes([
            rpm & 0xFF, (rpm >> 8) & 0xFF,
            speed & 0xFF, (speed >> 8) & 0xFF,
            coolant,
            int(fuel),
            (int(ts * 100) >> 16) & 0xFF,
            (int(ts * 100) >> 8) & 0xFF,
        ])
        frames.append((ts, 0x0C8, data_0C8))

        # 灯光报文 0x130 (50ms周期, 每5次发一次)
        if int(ts * 100) % 5 == 0:
            turn = 1 if speed > 20 else 0
            data_130 = bytes([turn, 0, 0, 0, 0, 0])
            frames.append((ts, 0x130, data_130))

        # 挡位报文 0x152 (100ms周期)
        if int(ts * 100) % 10 == 0:
            gear = 3 if speed > 0 else 0  # D档或P档
            data_152 = bytes([gear, 0, 0, 0])
            frames.append((ts, 0x152, data_152))

        ts += 0.01  # 10ms步进

    return frames


def main():
    print("=" * 60)
    print("CAN Message Analyzer - 完整演示")
    print("=" * 60)

    # 1. 解析DBC
    print("\n[Step 1] 解析DBC文件...")
    dbc_path = os.path.join(os.path.dirname(__file__), "cluster_demo.dbc")
    dbc = DBCParser()
    dbc.parse(dbc_path)
    print(dbc.summary())

    # 2. 解析CAN日志
    print("\n[Step 2] 生成并解析CAN日志...")
    raw_frames = generate_demo_log()
    parser = CANLogParser(dbc)
    parser.load_from_list(raw_frames)
    print(f"  总帧数: {len(parser.frames)}")
    print(f"  前5帧:")
    for frame in parser.frames[:5]:
        print(f"    {frame}")

    # 3. 用DBC解码
    print("\n[Step 3] DBC解码信号...")
    decoded = parser.decode_with_dbc()
    print(f"  解码成功: {len(decoded)} 条")
    if decoded:
        print(f"  最后一条解码结果:")
        last = decoded[-1]
        print(f"    报文: {last['message_name']}")
        print(f"    原始数据: {last['raw_data']}")
        for sig_name, sig_val in last['signals'].items():
            print(f"      {sig_name} = {sig_val}")

    # 4. 统计
    print("\n[Step 4] 统计分析...")
    stats = parser.get_statistics()
    print(f"  总帧数: {stats['total_frames']}")
    print(f"  时长: {stats['duration_seconds']:.3f}s")
    print(f"  平均速率: {stats['avg_frames_per_second']:.1f} fps")

    # 5. 信号可视化
    print("\n[Step 5] 信号数据提取...")
    viz = SignalVisualizer(decoded)
    for sig_name in ["EngineSpeed", "VehicleSpeed", "CoolantTemp", "FuelLevel"]:
        series = viz.extract_time_series(sig_name)
        if series["values"]:
            print(f"  {sig_name}: {len(series['values'])} samples")

    # 6. 生成报告
    print("\n[Step 6] 生成分析报告...")
    report = viz.generate_report()
    print(report)

    # 7. 尝试绘图（如果安装了matplotlib）
    print("\n[Step 7] 绘制信号曲线...")
    try:
        plot_signals(decoded, ["EngineSpeed", "VehicleSpeed"],
                     "examples/demo_plot.png")
    except Exception as e:
        print(f"  绘图跳过 (需要 matplotlib): {e}")

    print("\n演示完成!")


if __name__ == "__main__":
    main()
