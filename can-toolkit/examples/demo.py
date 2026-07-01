"""
can-toolkit 使用示例

无需真实 CAN 硬件，使用 python-can 虚拟接口演示所有功能。
"""

import time
from can_toolkit import CANBusManager, CANLogger, CANMonitor, CANReplay, CANFilter
from can_toolkit.bus_manager import BusConfig


def demo_basic_connection():
    """示例1: 基本连接和收发"""
    print("=" * 50)
    print("  Demo 1: Basic Connection & Send/Receive")
    print("=" * 50)

    config = BusConfig(interface="virtual", channel="ch0", bitrate=500000)

    with CANBusManager(config) as bus:
        # 发送报文
        bus.send(can_id=0x123, data=bytes([0xDE, 0xAD, 0xBE, 0xEF]))
        print(f"  Sent: ID=0x123 DATA=DEADBEEF")

        # 接收报文 (virtual bus 可以收到自己发的)
        msg = bus.receive(timeout=1.0)
        if msg:
            data_hex = " ".join(f"{b:02X}" for b in msg.data)
            print(f"  Received: ID=0x{msg.arbitration_id:X} DATA={data_hex}")

        stats = bus.stats
        print(f"  Stats: TX={stats['tx_count']} RX={stats['rx_count']}")
    print()


def demo_logging():
    """示例2: 流量记录"""
    print("=" * 50)
    print("  Demo 2: CAN Traffic Logging (ASC/CSV/SQLite)")
    print("=" * 50)

    with CANBusManager(BusConfig(interface="virtual", channel="ch0")) as bus:
        logger = CANLogger(bus)

        # 记录到 ASC 格式 (Vector CANoe 兼容)
        logger.start("example.asc", format="asc")

        # 模拟发送一些报文
        messages = [
            (0x0C8, b"\x20\x03\x64\x00\x55\x00\x00\x00"),  # 仪表
            (0x130, b"\x00\x00\xFA\x00\x00\x00"),            # 灯光
            (0x152, b"\x00\x02\x00\x03"),                     # 挡位
            (0x7DF, b"\x02\x01\x0D\x00\x00\x00\x00\x00"),    # OBD
            (0x7E8, b"\x02\x41\x0D\x32\x00\x00\x00\x00"),    # OBD resp
        ]

        for can_id, data in messages:
            bus.send(can_id=can_id, data=data)
            time.sleep(0.1)

        stats = logger.stop()
        print(f"  Saved {stats['message_count']} msgs to example.asc")

        # 也可以用 CSV
        logger.start("example.csv", format="csv")
        for can_id, data in messages:
            bus.send(can_id=can_id, data=data)
            time.sleep(0.05)
        logger.stop()
        print(f"  Saved to example.csv")
    print()


def demo_monitoring():
    """示例3: 实时监控"""
    print("=" * 50)
    print("  Demo 3: Real-time CAN Monitor")
    print("=" * 50)

    with CANBusManager(BusConfig(interface="virtual", channel="ch0")) as bus:
        monitor = CANMonitor(bus)
        monitor.start(print_interval=0)  # 0 = 不自动打印

        # 模拟周期性报文
        for i in range(20):
            bus.send(can_id=0x0C8 if i % 2 == 0 else 0x130,
                     data=bytes([i % 256, 0x00, 0x64, 0x00, 0x55, 0x00, 0x00, 0x00]))
            time.sleep(0.02)

        monitor.stop()

        # 查看统计
        active = monitor.get_active_ids()
        print(f"  Active IDs: {[f'0x{x:X}' for x in active]}")
        for can_id in active:
            count = monitor.get_message_count(can_id)
            last = monitor.get_last_data(can_id)
            print(f"  0x{can_id:X}: {count:3d} msgs, last: {last.hex() if last else 'N/A'}")

        print(f"  Total: {monitor.get_total_count()} messages")
    print()


def demo_replay():
    """示例4: 回放"""
    print("=" * 50)
    print("  Demo 4: Log Replay")
    print("=" * 50)

    # 先记录一些数据
    with CANBusManager(BusConfig(interface="virtual", channel="ch0")) as bus:
        logger = CANLogger(bus)
        logger.start("replay_demo.asc", format="asc")
        for i in range(10):
            bus.send(can_id=0x123, data=bytes([i, i+1, i+2, 0, 0, 0, 0, 0]))
            time.sleep(0.05)
        logger.stop()

    # 回放
    with CANBusManager(BusConfig(interface="virtual", channel="ch0")) as bus:
        replay = CANReplay(bus)
        count = replay.load("replay_demo.asc")
        print(f"  Loaded {count} messages")

        monitor = CANMonitor(bus)
        monitor.start(print_interval=0)

        replay.start(speed=10.0)  # 10x 加速
        replay.wait()

        monitor.stop()
        print(f"  Replayed: {replay._sent_count} msgs")
        print(f"  Monitor captured: {monitor.get_total_count()} msgs")
    print()


def demo_filtering():
    """示例5: 报文过滤"""
    print("=" * 50)
    print("  Demo 5: Message Filtering")
    print("=" * 50)

    # 构建过滤器: 匹配 UDS/OBD 诊断报文
    f = CANFilter(mode="or")
    f.add_id_mask(0x7E0, 0x7F0)  # 0x7E0-0x7EF
    f.add_id(0x7DF)              # OBD 广播

    # 测试数据
    test_msgs = [
        (0x7E0, b"\x02\x10\x03\x00\x00\x00\x00\x00"),  # 匹配: UDS req
        (0x7E8, b"\x02\x50\x03\x00\x32\x01\xF4\x00"),  # 匹配: UDS resp
        (0x0C8, b"\x20\x03\x64\x00\x55\x00\x00\x00"),  # 不匹配: 仪表
        (0x7DF, b"\x02\x01\x0D\x00\x00\x00\x00\x00"),  # 匹配: OBD req
        (0x123, b"\xDE\xAD\xBE\xEF\x00\x00\x00\x00"),  # 不匹配
    ]

    print(f"  Filter: {f.summary()}")
    for can_id, data in test_msgs:
        # 构造虚拟 Message 对象
        class FakeMsg:
            arbitration_id = can_id
            data = data
            is_extended_id = False
        msg = FakeMsg()
        matched = f.match(msg)
        mark = "[PASS]" if matched else "      "
        print(f"  {mark} 0x{can_id:04X} | {data[:6].hex().upper()}")
    print()


def demo_uds():
    """示例6: UDS 诊断"""
    print("=" * 50)
    print("  Demo 6: UDS Diagnostic (Simulated)")
    print("=" * 50)

    from can_toolkit.diagnostic import UDSClient, UDSSession

    with CANBusManager(BusConfig(interface="virtual", channel="ch0")) as bus:
        uds = UDSClient(bus, ecu_id=0x7E0, resp_id=0x7E8)

        # Tester Present
        print("  [ ] Tester Present...")
        print("      (Virtual bus -- needs real ECU for actual response)")
        print("      In real scenario: uds.tester_present() keeps session alive")

        # 会话控制
        print("  [ ] Session Control...")
        print("      python -c \"uds.change_session(UDSSession.EXTENDED)\"")

        # 安全访问
        print("  [ ] Security Access...")
        print("      1. seed = uds.security_access_request(level=1)")
        print("      2. key = uds.calculate_key_default(seed)")
        print("      3. uds.security_access_send_key(level=1, key)")

        # 读取 DTC
        print("  [ ] Read DTC...")
        print("      dtcs = uds.read_dtc_by_status_mask(0x08)")
        print("      for dtc in dtcs:")
        print("          print(dtc['code'], hex(dtc['status']))")

        print("\n  To test with real ECU:")
        print("  python cli.py diag read_vin --preset pcan_usb_ch0")
    print()


if __name__ == "__main__":
    demo_basic_connection()
    demo_logging()
    demo_monitoring()
    demo_replay()
    demo_filtering()
    demo_uds()
    print("All demos complete. No hardware required!")
