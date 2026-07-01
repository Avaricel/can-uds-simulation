#!/usr/bin/env python3
"""
Auto Test CLI - 车载测试自动化命令行工具

用法:
    # UDS诊断
    python cli.py uds session --type extended
    python cli.py uds read-dtc
    python cli.py uds read-data --did 0xF190
    python cli.py uds security-access
    python cli.py uds reset --type hard

    # 运行测试
    python cli.py test run
    python cli.py test run --suite dashboard --priority P0,P1
    python cli.py test run --tags regression

    # 生成报告
    python cli.py report generate results.json --format html --output report.html
"""

import argparse
import json
import sys

from auto_test.uds_client import (
    UDSClient, UDSSession, UDSResetType, StandardDID
)
from auto_test.test_runner import (
    TestRunner, TestSuite, TestCase, TestStep, TestStatus, TestPriority
)
from auto_test.report_generator import ReportGenerator


def cmd_uds_session(args):
    """切换诊断会话"""
    client = UDSClient(is_simulated=True)

    session_map = {
        "default": UDSSession.DEFAULT,
        "programming": UDSSession.PROGRAMMING,
        "extended": UDSSession.EXTENDED,
    }
    session = session_map.get(args.type, UDSSession.DEFAULT)

    resp = client.change_session(session)
    if resp.positive:
        print(f"[OK] 诊断会话切换成功: 0x{session.value:02X}")
        if resp.data:
            print(f"   P2 Timing: {resp.data.hex(' ')}")
    else:
        print(f"[FAIL] 切换失败: {resp.error_message}")


def cmd_uds_read_dtc(args):
    """读取DTC"""
    client = UDSClient(is_simulated=True)
    client.change_session(UDSSession.EXTENDED)

    # 添加模拟DTC
    client.add_sim_dtc("P0500", 0x2F)
    client.add_sim_dtc("U0121", 0x2F)
    client.add_sim_dtc("B1000", 0x0F)

    dtcs = client.read_dtc()
    if dtcs:
        print(f"[DTC] 故障码列表 ({len(dtcs)} 个):")
        for dtc in dtcs:
            print(f"   {dtc['code']} | Status: 0x{dtc['status']:02X} | {dtc['status_str']}")
    else:
        print("[OK] 无故障码")


def cmd_uds_read_data(args):
    """读取DID数据"""
    client = UDSClient(is_simulated=True)

    # 设置模拟数据
    client.set_sim_data(StandardDID.VIN, b"LSVAA4180E2123456")
    client.set_sim_data(StandardDID.SW_VERSION, b"SW_V4.2.1\x00\x00\x00")
    client.set_sim_data(StandardDID.ECU_SERIAL, b"ECU-2024-08876")

    did = int(args.did, 16) if args.did.startswith("0x") else int(args.did)
    resp = client.read_data_by_id(did)
    if resp.positive:
        hex_str = resp.data.hex(' ').upper() if resp.data else "(empty)"
        print(f"[OK] DID 0x{did:04X}: {hex_str}")
        if did == StandardDID.VIN:
            print(f"   解析: VIN = {resp.data.decode('ascii', errors='ignore')}")
        elif did == StandardDID.SW_VERSION:
            print(f"   解析: SW Version = {resp.data.decode('ascii', errors='ignore').strip()}")
    else:
        print(f"[FAIL] 读取失败: {resp.error_message}")


def cmd_uds_security(args):
    """安全访问"""
    client = UDSClient(is_simulated=True)
    success, msg = client.security_access()
    if success:
        print(f"🔓 {msg}")
    else:
        print(f"🔒 {msg}")


def cmd_uds_reset(args):
    """ECU复位"""
    client = UDSClient(is_simulated=True)
    reset_map = {
        "hard": UDSResetType.HARD_RESET,
        "key": UDSResetType.KEY_OFF_ON,
        "soft": UDSResetType.SOFT_RESET,
    }
    reset_type = reset_map.get(args.type, UDSResetType.HARD_RESET)
    resp = client.ecu_reset(reset_type)
    if resp.positive:
        print(f"[OK] ECU复位成功: {reset_type.name}")
    else:
        print(f"[FAIL] 复位失败: {resp.error_message}")


def create_demo_tests() -> TestRunner:
    """创建演示测试用例集"""
    runner = TestRunner("IC Dashboard Test Runner")

    # ===== 套件1: 仪表盘显示测试 =====
    suite_dashboard = TestSuite(
        name="仪表盘显示测试",
        description="验证仪表盘信号显示功能",
        tags=["dashboard", "regression"],
    )

    # 用例1: 车速信号
    case_speed = TestCase(
        id="TC_IC_001",
        name="车速信号显示验证",
        description="验证仪表盘车速信号接收与显示正确性",
        category="仪表",
        priority=TestPriority.P0,
        tags=["dashboard", "signal"],
        preconditions="CAN总线正常，仪表上电",
    )
    case_speed.steps = [
        TestStep("1", "发送车速信号 0km/h", "仪表显示 0 km/h"),
        TestStep("2", "发送车速信号 60km/h", "仪表显示 60 km/h"),
        TestStep("3", "发送车速信号 120km/h", "仪表显示 120 km/h"),
    ]

    def test_speed_display(case):
        for step in case.steps:
            step.status = TestStatus.PASS
            step.actual = step.expected

    case_speed.test_function = test_speed_display
    suite_dashboard.add_case(case_speed)

    # 用例2: 告警灯
    case_warning = TestCase(
        id="TC_IC_002",
        name="告警灯显示验证",
        description="验证各告警灯的点亮和熄灭逻辑",
        category="仪表",
        priority=TestPriority.P1,
        tags=["dashboard", "warning"],
    )
    case_warning.steps = [
        TestStep("1", "发送发动机故障信号", "发动机故障灯点亮"),
        TestStep("2", "发送ABS故障信号", "ABS故障灯点亮"),
        TestStep("3", "清除所有故障信号", "所有告警灯熄灭"),
    ]

    def test_warning_lamps(case):
        for step in case.steps:
            step.status = TestStatus.PASS
            step.actual = step.expected

    case_warning.test_function = test_warning_lamps
    suite_dashboard.add_case(case_warning)

    runner.add_suite(suite_dashboard)

    # ===== 套件2: UDS诊断测试 =====
    suite_uds = TestSuite(
        name="UDS诊断测试",
        description="验证UDS诊断服务功能",
        tags=["uds", "diagnostic"],
    )

    case_session = TestCase(
        id="TC_UDS_001",
        name="诊断会话切换测试",
        description="验证默认/扩展/编程会话切换功能",
        category="UDS诊断",
        priority=TestPriority.P1,
        tags=["uds", "session"],
    )

    def test_session_switch(case):
        client = UDSClient(is_simulated=True)
        # 测试默认会话
        resp = client.change_session(UDSSession.DEFAULT)
        assert resp.positive, f"Default session failed: {resp.error_message}"

        # 测试扩展会话
        resp = client.change_session(UDSSession.EXTENDED)
        assert resp.positive, f"Extended session failed: {resp.error_message}"

        # 测试编程会话
        resp = client.change_session(UDSSession.PROGRAMMING)
        assert resp.positive, f"Programming session failed: {resp.error_message}"

    case_session.test_function = test_session_switch
    suite_uds.add_case(case_session)

    case_dtc = TestCase(
        id="TC_UDS_002",
        name="DTC读取与清除测试",
        description="验证故障码读取和清除功能",
        category="UDS诊断",
        priority=TestPriority.P1,
        tags=["uds", "dtc"],
    )

    def test_dtc_operations(case):
        client = UDSClient(is_simulated=True)
        client.add_sim_dtc("P0500")
        dtcs = client.read_dtc()
        assert len(dtcs) > 0, "No DTCs found when expected"
        resp = client.clear_dtc()
        assert resp.positive, f"Clear DTC failed: {resp.error_message}"

    case_dtc.test_function = test_dtc_operations
    suite_uds.add_case(case_dtc)

    runner.add_suite(suite_uds)

    return runner


def cmd_test_run(args):
    """运行测试"""
    runner = create_demo_tests()

    filters = {}
    if args.priority:
        filters["filter_priority"] = [
            TestPriority(p.strip()) for p in args.priority.split(",")
        ]
    if args.tags:
        filters["filter_tags"] = args.tags.split(",")

    results = runner.run_all(**filters)

    # 保存结果
    output = args.output or "test_results.json"
    runner.export_results_json(output, results)

    # 从0到9生成简单摘要
    print(f"\n{'='*60}")
    total = results["total_cases"]
    passed = results["total_passed"]
    print(f"Total: {total} | Passed: {passed} | "
          f"Rate: {results['pass_rate']}%")


def cmd_report_generate(args):
    """生成测试报告"""
    with open(args.input, 'r', encoding='utf-8') as f:
        results = json.load(f)

    gen = ReportGenerator(results)

    if args.format == "text":
        print(gen.to_text())
    elif args.format == "html":
        output = args.output or "test_report.html"
        gen.save_html(output)
    else:
        gen.print_summary()


def main():
    parser = argparse.ArgumentParser(
        description="Auto Test CLI - 车载测试自动化命令行工具"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # === uds 子命令 ===
    uds = subparsers.add_parser("uds", help="UDS诊断操作")
    uds_sub = uds.add_subparsers(dest="uds_cmd")

    # session
    uds_sess = uds_sub.add_parser("session", help="切换诊断会话")
    uds_sess.add_argument("--type", choices=["default", "extended", "programming"],
                          default="default", help="会话类型")
    uds_sess.set_defaults(func=cmd_uds_session)

    # read-dtc
    uds_dtc = uds_sub.add_parser("read-dtc", help="读取故障码")
    uds_dtc.set_defaults(func=cmd_uds_read_dtc)

    # read-data
    uds_data = uds_sub.add_parser("read-data", help="按DID读取数据")
    uds_data.add_argument("--did", required=True, help="数据标识符（如0xF190）")
    uds_data.set_defaults(func=cmd_uds_read_data)

    # security
    uds_sec = uds_sub.add_parser("security-access", help="安全访问")
    uds_sec.set_defaults(func=cmd_uds_security)

    # reset
    uds_res = uds_sub.add_parser("reset", help="ECU复位")
    uds_res.add_argument("--type", choices=["hard", "key", "soft"],
                         default="hard", help="复位类型")
    uds_res.set_defaults(func=cmd_uds_reset)

    # === test 子命令 ===
    test = subparsers.add_parser("test", help="测试执行")
    test_sub = test.add_subparsers(dest="test_cmd")

    test_run = test_sub.add_parser("run", help="运行测试")
    test_run.add_argument("--priority", help="优先级过滤 (如 P0,P1)")
    test_run.add_argument("--tags", help="标签过滤 (如 dashboard,uds)")
    test_run.add_argument("-o", "--output", default="test_results.json",
                          help="结果输出文件")
    test_run.set_defaults(func=cmd_test_run)

    # === report 子命令 ===
    report = subparsers.add_parser("report", help="报告生成")
    report_sub = report.add_subparsers(dest="report_cmd")

    rep_gen = report_sub.add_parser("generate", help="生成测试报告")
    rep_gen.add_argument("input", help="测试结果JSON文件")
    rep_gen.add_argument("--format", choices=["text", "html"],
                         default="text", help="报告格式")
    rep_gen.add_argument("-o", "--output", help="输出文件")
    rep_gen.set_defaults(func=cmd_report_generate)

    args = parser.parse_args()

    if hasattr(args, "func"):
        args.func(args)
    else:
        # 无参数时运行演示
        if not args.command:
            print("=" * 60)
            print("  Auto Test CLI - 车载测试自动化工具演示")
            print("=" * 60)
            print("\n[CAR] 运行演示测试套件...")
            cmd_test_run(argparse.Namespace(
                test_cmd="run", priority=None, tags=None,
                output="test_results.json"
            ))
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
