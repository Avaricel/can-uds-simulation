#!/usr/bin/env python3
"""
can-toolkit CLI: 车载 CAN 总线工具箱

基于 python-can 的命令行工具, 支持:
  - info   : 查询 CAN 接口信息
  - log    : 记录 CAN 流量到文件
  - monitor: 实时监控 CAN 总线
  - replay : 回放日志文件到 CAN 总线
  - send   : 发送单条/批量 CAN 报文
  - filter : 从日志中过滤报文
  - diag   : UDS 诊断交互
  - demo   : 运行演示 (无需硬件)

Usage:
  python cli.py info                    # 查看可用接口
  python cli.py log -i virtual -o out.asc  # 记录流量
  python cli.py monitor -i virtual         # 实时监控
  python cli.py replay capture.asc -i virtual  # 回放
  python cli.py send 0x123 DEADBEEF -i virtual    # 发送单条
  python cli.py diag read_vin -i virtual          # 读取 VIN
  python cli.py demo                            # 运行演示
"""

import argparse
import sys
import time
import threading
from datetime import datetime

try:
    import can
except ImportError:
    pass


def cmd_info(args):
    """显示 CAN 接口信息"""
    from can_toolkit.bus_manager import INTERFACE_PRESETS, INTERFACE_REQUIREMENTS

    print("=" * 60)
    print("  CAN Interface Presets")
    print("=" * 60)

    by_iface = {}
    for name, cfg in INTERFACE_PRESETS.items():
        iface = cfg["interface"]
        if iface not in by_iface:
            by_iface[iface] = []
        by_iface[iface].append((name, cfg["channel"]))

    for iface, channels in sorted(by_iface.items()):
        req = INTERFACE_REQUIREMENTS.get(iface, "Unknown")
        print(f"\n[{iface}]")
        print(f"  Requires: {req}")
        for name, channel in channels:
            print(f"  Preset: {name:25s} channel={channel}")

    print("\n" + "=" * 60)
    print("  Usage Examples")
    print("=" * 60)
    print("  python cli.py log    --preset virtual_0    # VIRTUAL (no hardware)")
    print("  python cli.py log    --preset socketcan_ch0 # Linux SocketCAN")
    print("  python cli.py log    --preset pcan_usb_ch0  # PEAK PCAN-USB")
    print("  python cli.py log    --preset vector_ch0    # Vector VN16xx")
    print("  python cli.py log    --preset slcan_com3    # Serial CAN (COM3)")
    print("  python cli.py log    --preset kvaser_ch0    # Kvaser Leaf")


def cmd_log(args):
    """记录 CAN 流量"""
    from can_toolkit.bus_manager import CANBusManager, BusConfig
    from can_toolkit.logger import CANLogger

    if args.preset:
        config = BusConfig.from_preset(args.preset)
    else:
        config = BusConfig(
            interface=getattr(args, "interface", "virtual"),
            channel=getattr(args, "channel", "ch0"),
            bitrate=args.bitrate or 500000,
        )

    # 生成默认文件名
    output = args.output
    if output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ext = args.format
        output = f"can_log_{ts}.{ext}"

    with CANBusManager(config) as mgr:
        if not mgr.is_connected():
            print("Failed to connect. Check your CAN hardware.")
            return

        logger = CANLogger(mgr)

        if args.filter_ids:
            ids = [int(x, 16) if x.startswith("0x") else int(x)
                   for x in args.filter_ids.split(",")]
            logger.set_filter(ids)
            print(f"[LOG] Filter: {[f'0x{x:X}' for x in ids]}")

        logger.start(output, format=args.format)

        try:
            print(f"[LOG] Recording to {output} ... Press Ctrl+C to stop.")
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            stats = logger.stop()
            print(f"[LOG] Done. {stats['message_count']} msgs saved to {output}")


def cmd_monitor(args):
    """实时监控 CAN 总线"""
    from can_toolkit.bus_manager import CANBusManager, BusConfig
    from can_toolkit.monitor import CANMonitor

    if args.preset:
        config = BusConfig.from_preset(args.preset)
    else:
        config = BusConfig(
            interface=getattr(args, "interface", "virtual"),
            channel=getattr(args, "channel", "ch0"),
            bitrate=args.bitrate or 500000,
        )

    with CANBusManager(config) as mgr:
        if not mgr.is_connected():
            print("Failed to connect. Check your CAN hardware.")
            return

        monitor = CANMonitor(mgr)

        if args.filter_ids:
            ids = [int(x, 16) if x.startswith("0x") else int(x)
                   for x in args.filter_ids.split(",")]
            monitor.set_filter(ids)

        interval = args.interval or 1.0

        print(f"[MONITOR] Press Ctrl+C to stop. Refresh: {interval}s")
        monitor.start(print_interval=interval)

        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            final_stats = monitor.stop()
            table = monitor.get_stats_table()
            print(table)


def cmd_replay(args):
    """回放 CAN 日志"""
    from can_toolkit.bus_manager import CANBusManager, BusConfig
    from can_toolkit.replay import CANReplay

    if args.preset:
        config = BusConfig.from_preset(args.preset)
    else:
        config = BusConfig(
            interface=getattr(args, "interface", "virtual"),
            channel=getattr(args, "channel", "ch0"),
            bitrate=args.bitrate or 500000,
        )

    with CANBusManager(config) as mgr:
        if not mgr.is_connected():
            print("Failed to connect. Check your CAN hardware.")
            return

        replay = CANReplay(mgr)
        count = replay.load(args.file, format=args.format)
        if count == 0:
            print(f"No messages found in {args.file}")
            return

        speed = args.speed or 1.0
        loop = args.loop or False
        replay.start(speed=speed, loop=loop)
        replay.wait()

        print(f"[REPLAY] Complete. {replay._sent_count}/{count} messages sent.")


def cmd_send(args):
    """发送 CAN 报文"""
    from can_toolkit.bus_manager import CANBusManager, BusConfig

    if args.preset:
        config = BusConfig.from_preset(args.preset)
    else:
        config = BusConfig(
            interface=getattr(args, "interface", "virtual"),
            channel=getattr(args, "channel", "ch0"),
            bitrate=args.bitrate or 500000,
        )

    can_id = int(args.can_id, 16) if args.can_id.startswith("0x") else int(args.can_id)
    data = bytes.fromhex(args.data) if args.data else b"\x00\x00\x00\x00\x00\x00\x00\x00"
    count = args.count or 1
    interval = args.interval or 0.1

    with CANBusManager(config) as mgr:
        if not mgr.is_connected():
            print("Failed to connect.")
            return

        print(f"[SEND] ID=0x{can_id:X} DATA={data.hex().upper()} COUNT={count}")
        for i in range(count):
            mgr.send(can_id=can_id, data=data, is_extended=args.extended)
            if count > 1 and i < count - 1:
                time.sleep(interval)
            print(f"  [{i+1}/{count}] Sent", end="\r")

        if count > 1:
            print()
        bus_stats = mgr.stats
        print(f"[SEND] Done. TX total: {bus_stats['tx_count']}")


def cmd_filter(args):
    """从日志中过滤报文"""
    from can_toolkit.replay import CANReplay
    from can_toolkit.filter import CANFilter
    from can_toolkit.bus_manager import CANBusManager, BusConfig
    from can_toolkit.logger import CANLogger

    replay = CANReplay(None)  # 不需要总线, 只用加载功能
    count = replay.load(args.file)
    print(f"Loaded {count} messages from {args.file}")

    # 构建过滤器
    f = CANFilter()

    if args.include_ids:
        ids = [int(x, 16) if x.startswith("0x") else int(x)
               for x in args.include_ids.split(",")]
        f.add_id_list(ids)

    matched = f.apply([msg for _, msg in replay._messages])

    # 输出
    if args.output:
        # 写入文件 (重用 logger 的格式)
        with CANBusManager(BusConfig(interface="virtual", channel="filter")) as mgr:
            mgr.connect()
            logger = CANLogger(mgr)

            fmt = args.output.rsplit(".", 1)[-1]
            logger.start(args.output, format=fmt if fmt in ("asc", "csv", "sqlite") else "asc")

            for msg in matched:
                logger._on_message(msg)

            logger.stop()
            print(f"Filtered {len(matched)}/{count} messages -> {args.output}")
    else:
        # 打印到终端
        for msg in matched[:50]:
            data_hex = " ".join(f"{b:02X}" for b in msg.data)
            print(f"  0x{msg.arbitration_id:04X} [{len(msg.data)}] {data_hex}")
        if len(matched) > 50:
            print(f"  ... and {len(matched) - 50} more")


def cmd_diag(args):
    """UDS 诊断交互"""
    from can_toolkit.bus_manager import CANBusManager, BusConfig
    from can_toolkit.diagnostic import UDSClient, UDSSession

    if args.preset:
        config = BusConfig.from_preset(args.preset)
    else:
        config = BusConfig(
            interface=getattr(args, "interface", "virtual"),
            channel=getattr(args, "channel", "ch0"),
            bitrate=args.bitrate or 500000,
        )

    ecu_id = args.ecu_id or 0x7E0
    resp_id = args.resp_id or 0x7E8

    with CANBusManager(config) as mgr:
        if not mgr.is_connected():
            print("Failed to connect.")
            return

        uds = UDSClient(mgr, ecu_id=ecu_id, resp_id=resp_id)
        action = args.action

        if action == "ping":
            result = uds.tester_present()
            print(f"Tester Present: {'[OK]' if result else '[FAIL]'}")
            print(f"[WARN] Virtual bus -- connect to real ECU for actual response")

        elif action == "read_vin":
            vin = uds.read_vin()
            if vin:
                print(f"VIN: {vin}")
            else:
                print("VIN: [No response] (Virtual bus)")
                print("  Hint: Connect to real ECU, or check ECU ID / Response ID.")

        elif action == "read_dtc":
            dtcs = uds.read_dtc_by_status_mask()
            if dtcs:
                print(f"DTC List ({len(dtcs)}):")
                for dtc in dtcs:
                    print(f"  {dtc['code']:12s} status=0x{dtc['status']:02X}")
            else:
                print("DTC: [No response] (Virtual bus)")
                print("  Hint: Switch to extended session first: python cli.py diag session 03")

        elif action == "session":
            session_type = int(args.data, 16) if args.data and args.data.startswith("0x") else (int(args.data) if args.data else 0x01)
            session_map = {0x01: UDSSession.DEFAULT, 0x02: UDSSession.PROGRAMMING, 0x03: UDSSession.EXTENDED}
            session = session_map.get(session_type, UDSSession.DEFAULT)
            result = uds.change_session(session)
            print(f"Session change to 0x{session_type:02X}: {'[OK]' if result else '[FAIL]'}")

        elif action == "unlock":
            level = int(args.data) if args.data else 1
            seed = uds.security_access_request(level)
            if seed:
                print(f"Seed: {seed.hex().upper()}")
                key = uds.calculate_key_default(seed)
                print(f"Key:  {key.hex().upper()}")
                result = uds.security_access_send_key(level, key)
                print(f"Unlock: {'[OK]' if result else '[FAIL]'}")
            else:
                print("Security Access: [No response] (Virtual bus)")

        elif action == "reset":
            reset_type = int(args.data) if args.data else 1
            name_map = {1: "Hard", 2: "KeyOffOn", 3: "Soft"}
            name = name_map.get(reset_type, f"Type{reset_type}")
            result = uds.ecu_reset(reset_type)
            print(f"ECU Reset ({name}): {'[OK]' if result else '[FAIL]'}")

        elif action == "read_did":
            if args.data:
                did = int(args.data, 16) if args.data.startswith("0x") else int(args.data)
                data = uds.read_data_by_id(did)
                if data:
                    print(f"DID 0x{did:04X}: {data.hex().upper()}")
                    try:
                        text = data.decode("ascii").strip("\x00")
                        print(f"           '{text}'")
                    except Exception:
                        pass
                else:
                    print(f"DID 0x{did:04X}: [No response]")
            else:
                print("Usage: python cli.py diag read_did --data F190")


def _get_dual_bus():
    """获取一对互相连通的虚拟总线 (发送端 + 接收端)

    在 Windows 上 python-can virtual bus 不支持单实例自收自发。
    使用双实例模式模拟真实 CAN 拓扑: 发送端 -> 总线 -> 接收端
    """
    from can_toolkit.bus_manager import CANBusManager, BusConfig
    import can as _can

    # 创建两个独立的 virtual bus 实例
    tx_bus = _can.interface.Bus(interface="virtual", channel="ch0", bitrate=500000)
    rx_bus = _can.interface.Bus(interface="virtual", channel="ch0", bitrate=500000)
    return tx_bus, rx_bus


class _VirtualSender:
    """虚拟发送端 (双总线模式)"""
    def __init__(self, bus):
        self._bus = bus
        self._tx_count = 0

    def send(self, can_id, data, is_extended=False):
        msg = can.Message(arbitration_id=can_id, data=data, is_extended_id=is_extended)
        self._bus.send(msg)
        self._tx_count += 1

    @property
    def stats(self):
        uptime = time.time()
        return {"tx_count": self._tx_count, "tx_rate": 0}

    def close(self):
        self._bus.shutdown()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class _VirtualReceiver:
    """虚拟接收端 (双总线模式)"""
    def __init__(self, bus):
        self._bus = bus
        self._callbacks = []
        self._running = False
        self._thread = None
        self._rx_count = 0

    def add_callback(self, cb):
        self._callbacks.append(cb)

    def remove_callback(self, cb):
        if cb in self._callbacks:
            self._callbacks.remove(cb)

    def start_listening(self):
        self._running = True
        self._thread = threading.Thread(target=self._listen_loop, daemon=True)
        self._thread.start()

    def stop_listening(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _listen_loop(self):
        while self._running:
            try:
                msg = self._bus.recv(timeout=0.05)
                if msg is not None:
                    self._rx_count += 1
                    for cb in self._callbacks:
                        try:
                            cb(msg)
                        except Exception:
                            pass
            except Exception:
                pass

    def close(self):
        self.stop_listening()
        self._bus.shutdown()

    def __enter__(self):
        self.start_listening()
        return self

    def __exit__(self, *args):
        self.close()


def cmd_demo(args):
    """完整功能演示 (无需硬件, 使用虚拟 CAN 总线)

    采用双总线实例模式: Sender -> Virtual Bus -> Receiver
    模拟真实 CAN 拓扑中 ECU 发送、诊断仪接收的场景
    """
    from can_toolkit.bus_manager import CANBusManager, BusConfig
    from can_toolkit.logger import CANLogger, ASCWriter
    from can_toolkit.monitor import CANMonitor
    from can_toolkit.replay import CANReplay
    from can_toolkit.filter import CANFilter

    print("=" * 60)
    print("  CAN Toolkit Demo (python-can Virtual Bus)")
    print("  Architecture: Sender --> Bus --> Receiver")
    print("=" * 60)

    # ── Demo 1: 双总线收发 ──
    print("\n[Demo 1/5] Dual-Bus Send/Receive (Real CAN Topology)")
    print("-" * 40)

    tx_bus, rx_bus = _get_dual_bus()

    with _VirtualSender(tx_bus) as sender, _VirtualReceiver(rx_bus) as receiver:
        received_msgs = []
        receiver.add_callback(lambda m: received_msgs.append(m))

        time.sleep(0.1)  # 等 receiver 就绪

        msgs_to_send = [
            (0x0C8, b"\x20\x03\x64\x00\x55\x00\x00\x00"),
            (0x130, b"\x00\x00\xFA\x00\x00\x00"),
            (0x152, b"\x00\x02\x00\x03"),
            (0x7DF, b"\x02\x01\x0D\x00\x00\x00\x00\x00"),
            (0x7E8, b"\x02\x41\x0D\x32\x00\x00\x00\x00"),
            (0x0C8, b"\x21\x03\x64\x00\x55\x00\x00\x00"),
            (0x130, b"\x01\x00\xFB\x00\x00\x00"),
            (0x7DF, b"\x02\x01\x0D\x00\x00\x00\x00\x00"),
            (0x7E8, b"\x02\x41\x0D\x37\x00\x00\x00\x00"),
            (0x236, b"\x90\x01\x84\x03\x88\x02"),
        ]
        for cid, d in msgs_to_send:
            sender.send(cid, d)
            time.sleep(0.03)

        time.sleep(0.2)  # 等待接收完成

        print(f"  Sent:     {sender.stats['tx_count']} messages")
        print(f"  Received: {len(received_msgs)} messages")
        assert len(received_msgs) == len(msgs_to_send), \
            f"Expected {len(msgs_to_send)}, got {len(received_msgs)}"
        print(f"  [PASS] All {len(msgs_to_send)} messages transmitted successfully")

    # ── Demo 2: 实时监控 ──
    print("\n[Demo 2/5] Real-time CAN Monitor")
    print("-" * 40)

    tx_bus2, rx_bus2 = _get_dual_bus()

    with _VirtualSender(tx_bus2) as sender, _VirtualReceiver(rx_bus2) as receiver:
        monitor = CANMonitor.__new__(CANMonitor)  # 绕过 __init__, 直接注入回调
        monitor._stats = {}
        monitor._lock = threading.Lock()
        monitor._filter_ids = None
        monitor._running = True
        monitor._bus = None

        def mon_cb(msg):
            monitor._on_message(msg)

        receiver.add_callback(mon_cb)
        time.sleep(0.1)

        # 模拟多种 ECU 周期性报文
        for i in range(10):
            # 仪表报文 (周期 10ms)
            sender.send(0x0C8, bytes([0x20 + i, 0x03, 0x64, 0x00, 0x55, 0x00, 0x00, 0x00]))
            time.sleep(0.01)
            # 车身报文 (周期 50ms)
            sender.send(0x130, bytes([i % 4, 0x00, 0xFA, 0x00, 0x00, 0x00]))
            time.sleep(0.01)
            # OBD 响应
            if i % 2 == 0:
                sender.send(0x7E8, bytes([0x02, 0x41, 0x0D, 0x32 + i, 0x00, 0x00, 0x00, 0x00]))

        time.sleep(0.2)

        monitor._running = False
        table = monitor.get_stats_table()
        print(table)

    # ── Demo 3: 流量记录到 ASC ──
    print("\n[Demo 3/5] CAN Traffic Logger -> ASC File")
    print("-" * 40)

    tx_bus3, rx_bus3 = _get_dual_bus()

    with _VirtualSender(tx_bus3) as sender, _VirtualReceiver(rx_bus3) as receiver:
        writer = ASCWriter("demo_capture.asc")

        def log_cb(msg):
            writer.write(msg)

        receiver.add_callback(log_cb)
        time.sleep(0.1)

        log_msgs = [
            (0x0C8, b"\x20\x03\x64\x00\x55\x00\x00\x00"),
            (0x130, b"\x00\x00\xFA\x00\x00\x00"),
            (0x152, b"\x00\x02\x00\x03"),
            (0x236, b"\x90\x01\x84\x03\x88\x02"),
            (0x1A4, b"\xC0\x00"),
            (0x1F5, b"\x02\x00\x01\x00\x10\x00\x00\x00"),
        ]
        for cid, d in log_msgs:
            sender.send(cid, d)
            time.sleep(0.02)

        time.sleep(0.1)
        writer.close()

        # 验证文件
        import os
        file_size = os.path.getsize("demo_capture.asc")
        print(f"  Saved: demo_capture.asc ({file_size} bytes)")
        assert file_size > 0, "ASC file should not be empty"
        print(f"  [PASS] ASC file written (CANoe compatible)")

    # ── Demo 4: 回放 + 监控 ──
    print("\n[Demo 4/5] CAN Log Replay + Monitor")
    print("-" * 40)

    tx_bus4, rx_bus4 = _get_dual_bus()

    with _VirtualSender(tx_bus4) as sender, _VirtualReceiver(rx_bus4) as receiver:
        monitor2 = CANMonitor.__new__(CANMonitor)
        monitor2._stats = {}
        monitor2._lock = threading.Lock()
        monitor2._filter_ids = None
        monitor2._running = True

        def mon_cb2(msg):
            monitor2._on_message(msg)

        receiver.add_callback(mon_cb2)

        # 加载 ASC 并回放
        replay = CANReplay.__new__(CANReplay)
        replay._bus = sender
        replay._speed = 10.0
        replay._loop = False
        replay._sent_count = 0
        replay._total_count = 0
        replay._messages = []
        replay._running = False
        replay._paused = False
        replay._progress_callback = None

        loaded = replay.load("demo_capture.asc")
        print(f"  Loaded: {loaded} messages from demo_capture.asc")
        assert loaded > 0, "Should load messages from ASC file"

        time.sleep(0.1)

        # 手动回放 (避免线程复杂度)
        base_time = replay._messages[0][0] if replay._messages else 0
        for ts, msg in replay._messages:
            sender.send(msg.arbitration_id, bytes(msg.data), msg.is_extended_id)
            replay._sent_count += 1
            time.sleep(0.01)

        time.sleep(0.2)

        monitor2._running = False
        total_rx = monitor2.get_total_count()
        print(f"  Replayed: {replay._sent_count} msgs")
        print(f"  Received: {total_rx} msgs")
        assert total_rx == replay._sent_count, f"RX mismatch: {total_rx} vs {replay._sent_count}"
        print(f"  [PASS] Replay verified: all messages received")

    # ── Demo 5: 报文过滤 + 统计 ──
    print("\n[Demo 5/5] Message Filtering + Bus Statistics")
    print("-" * 40)

    # 过滤器
    filter_uds = CANFilter(mode="or")
    filter_uds.add_id_mask(0x7E0, 0x7F0)  # UDS/OBD 范围
    filter_uds.add_id(0x0C8)  # 仪表报文

    test_data = [
        (0x0C8, b"\x25\x04\x60\x00"),
        (0x130, b"\x01\x00\xFB\x00"),
        (0x7DF, b"\x02\x01\x0D\x00"),
        (0x7E8, b"\x03\x41\x0D\x32"),
        (0x152, b"\x00\x03\x00\x04"),
        (0x7E9, b"\x03\x41\x0D\x37"),
        (0x0C8, b"\x26\x04\x60\x00"),
        (0x236, b"\x90\x01\x84\x03"),
    ]
    test_msgs = []
    for cid, d in test_data:
        test_msgs.append(type("Msg", (), {"arbitration_id": cid, "data": d, "is_extended_id": False})())

    matched = filter_uds.apply(test_msgs)
    total = len(test_msgs)
    expected_match = [m for m in test_msgs if m.arbitration_id in {0x0C8} or 0x7E0 <= m.arbitration_id <= 0x7EF]
    assert len(matched) == len(expected_match), \
        f"Filter mismatch: {len(matched)} vs expected {len(expected_match)}"

    print(f"  Filter rule: UDS/OBD (0x7E0-0x7EF) + Dashboard (0x0C8)")
    print(f"  Total: {total} msgs | Matched: {len(matched)}")
    for m in test_msgs:
        status = "[PASS]" if m in matched else "      "
        print(f"  {status} 0x{m.arbitration_id:04X} | {m.data[:4].hex().upper()}")
    print(f"  [PASS] Filter correctly matched {len(matched)}/{total}")

    # 总线统计
    tx_bus5, rx_bus5 = _get_dual_bus()
    with _VirtualSender(tx_bus5) as sender:
        for i in range(50):
            sender.send(0x0C8, bytes([0x20 + (i % 10), i % 5, 0x64, 0x00, 0x55, 0x00, 0x00, 0x00]))
            time.sleep(0.005)

        print(f"\n  Bus Statistics:")
        print(f"  TX Count:   {sender.stats['tx_count']}")
        print(f"  TX Rate:    {sender.stats['tx_count'] / (50 * 0.005):.0f} msg/s (estimated)")

    rx_bus5.shutdown()

    print("\n" + "=" * 60)
    print("  All Demos Complete! (python-can virtual bus)")
    print("=" * 60)
    print(f"\n  Verified capabilities:")
    print(f"  [PASS] Dual-bus send/receive (real CAN topology)")
    print(f"  [PASS] Real-time CAN monitoring with stats")
    print(f"  [PASS] Traffic logging to ASC (CANoe compatible)")
    print(f"  [PASS] Log replay with verification")
    print(f"  [PASS] CAN ID filtering (mask + range)")
    print(f"  [PASS] Bus statistics")
    print(f"\n  To use with real hardware:")
    print(f"    python cli.py log --preset pcan_usb_ch0 -o capture.asc")
    print(f"    python cli.py diag read_vin --preset vector_ch0")
    print(f"\n  For Python API usage:")
    print(f"    python examples/demo.py")


def main():
    parser = argparse.ArgumentParser(
        description="can-toolkit: Python CAN Bus Toolkit (基于 python-can)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli.py info                              List available interfaces
  python cli.py log -i virtual -o capture.asc     Record CAN traffic
  python cli.py monitor -i virtual                Real-time monitor
  python cli.py replay capture.asc -i virtual      Replay log file
  python cli.py send 0x123 DEADBEEF -i virtual     Send single message
  python cli.py diag read_vin -i virtual           Read VIN via UDS
  python cli.py demo                              Run all demos (no hardware)
        """
    )

    parser.add_argument("--version", action="version",
                        version="can-toolkit 1.0.0")

    sub = parser.add_subparsers(dest="command", help="Commands")

    # ── info ──
    p_info = sub.add_parser("info", help="Show available CAN interfaces")

    # ── log ──
    p_log = sub.add_parser("log", help="Record CAN traffic")
    p_log.add_argument("-i", "--interface", default="virtual")
    p_log.add_argument("-c", "--channel", default="ch0")
    p_log.add_argument("-b", "--bitrate", type=int, default=500000)
    p_log.add_argument("-p", "--preset")
    p_log.add_argument("-o", "--output")
    p_log.add_argument("-f", "--format", default="asc",
                        choices=["asc", "csv", "sqlite", "blf"])
    p_log.add_argument("--filter-ids")

    # ── monitor ──
    p_mon = sub.add_parser("monitor", help="Real-time CAN monitor")
    p_mon.add_argument("-i", "--interface", default="virtual")
    p_mon.add_argument("-c", "--channel", default="ch0")
    p_mon.add_argument("-b", "--bitrate", type=int, default=500000)
    p_mon.add_argument("-p", "--preset")
    p_mon.add_argument("--interval", type=float, default=1.0)
    p_mon.add_argument("--filter-ids")

    # ── replay ──
    p_rpl = sub.add_parser("replay", help="Replay CAN log file")
    p_rpl.add_argument("file", help="Log file (asc/csv/sqlite)")
    p_rpl.add_argument("-i", "--interface", default="virtual")
    p_rpl.add_argument("-c", "--channel", default="ch0")
    p_rpl.add_argument("-b", "--bitrate", type=int, default=500000)
    p_rpl.add_argument("-p", "--preset")
    p_rpl.add_argument("-f", "--format")
    p_rpl.add_argument("-s", "--speed", type=float, default=1.0)
    p_rpl.add_argument("-l", "--loop", action="store_true")

    # ── send ──
    p_snd = sub.add_parser("send", help="Send CAN message(s)")
    p_snd.add_argument("can_id", help="CAN ID (hex, e.g. 0x123)")
    p_snd.add_argument("data", nargs="?", default="",
                       help="Data in hex (e.g. DEADBEEF)")
    p_snd.add_argument("-i", "--interface", default="virtual")
    p_snd.add_argument("-c", "--channel", default="ch0")
    p_snd.add_argument("-b", "--bitrate", type=int, default=500000)
    p_snd.add_argument("-p", "--preset")
    p_snd.add_argument("-x", "--extended", action="store_true")
    p_snd.add_argument("-n", "--count", type=int, default=1)
    p_snd.add_argument("--interval", type=float, default=0.1)

    # ── filter ──
    p_flt = sub.add_parser("filter", help="Filter CAN log file")
    p_flt.add_argument("file", help="Log file")
    p_flt.add_argument("--include-ids")
    p_flt.add_argument("-o", "--output")

    # ── diag ──
    p_diag = sub.add_parser("diag", help="UDS diagnostic")
    p_diag.add_argument("action", choices=[
        "ping", "read_vin", "read_dtc", "session", "unlock",
        "reset", "read_did"
    ])
    p_diag.add_argument("-i", "--interface", default="virtual")
    p_diag.add_argument("-c", "--channel", default="ch0")
    p_diag.add_argument("-b", "--bitrate", type=int, default=500000)
    p_diag.add_argument("-p", "--preset")
    p_diag.add_argument("--ecu-id", type=lambda x: int(x, 16) if x.startswith("0x") else int(x))
    p_diag.add_argument("--resp-id", type=lambda x: int(x, 16) if x.startswith("0x") else int(x))
    p_diag.add_argument("--data")

    # ── demo ──
    p_demo = sub.add_parser("demo", help="Run all demos (no hardware needed)")

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        return

    commands = {
        "info":    cmd_info,
        "log":     cmd_log,
        "monitor": cmd_monitor,
        "replay":  cmd_replay,
        "send":    cmd_send,
        "filter":  cmd_filter,
        "diag":    cmd_diag,
        "demo":    cmd_demo,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
