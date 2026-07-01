# Auto Test CLI 🔧

车载测试自动化命令行工具 — 集成UDS诊断、CAN监控、测试用例管理与HTML报告生成。

## 功能模块

### 1. UDS诊断 (ISO 14229)
- ✅ 诊断会话控制 (0x10)
- ✅ ECU复位 (0x11)  
- ✅ 安全访问 (0x27) — Seed/Key流程
- ✅ 按DID读取数据 (0x22)
- ✅ DTC读取与清除 (0x19/0x14)
- ✅ 例程控制 (0x31)
- ✅ Tester Present (0x3E)
- 内置模拟ECU，无需真实硬件即可练习

### 2. 测试用例管理
- 用例定义（ID/步骤/标签/优先级）
- 测试套件组织
- 自动执行与结果收集
- 优先级/标签过滤

### 3. 报告生成
- 纯文本报告
- HTML可视化报告（含通过率仪表盘）
- JSON结果导出

### 4. CAN总线监控
- 报文超时检测
- 周期抖动分析
- 总线负载率估算
- 实时告警回调

## 快速开始

```bash
git clone https://github.com/Avaricel/auto-test-cli.git
cd auto-test-cli

# 直接运行演示（会自动执行演示测试套件）
python cli.py
```

## 命令参考

### UDS诊断

```bash
# 切换诊断会话
python cli.py uds session --type extended

# 读取故障码
python cli.py uds read-dtc

# 读取ECU数据（VIN、软件版本等）
python cli.py uds read-data --did 0xF190

# 安全访问
python cli.py uds security-access

# ECU复位
python cli.py uds reset --type hard
```

### 测试执行

```bash
# 运行所有测试
python cli.py test run

# 按优先级运行
python cli.py test run --priority P0,P1

# 按标签运行
python cli.py test run --tags dashboard

# 指定输出文件
python cli.py test run -o my_results.json
```

### 报告生成

```bash
# 文本报告
python cli.py report generate test_results.json --format text

# HTML报告
python cli.py report generate test_results.json --format html -o report.html
```

## Python API

```python
from auto_test.uds_client import UDSClient, UDSSession, StandardDID
from auto_test.test_runner import TestRunner, TestSuite, TestCase, TestPriority
from auto_test.report_generator import ReportGenerator

# UDS诊断
client = UDSClient(is_simulated=True)
resp = client.change_session(UDSSession.EXTENDED)
print(resp)

# 读取VIN
resp = client.read_data_by_id(StandardDID.VIN)

# 读取DTC
dtcs = client.read_dtc()
for dtc in dtcs:
    print(f"{dtc['code']}: {dtc['status_str']}")

# 创建测试用例
case = TestCase(
    id="TC_DEMO_001",
    name="示例测试",
    priority=TestPriority.P0,
    tags=["demo", "regression"],
)

def my_test(case):
    assert 2 + 2 == 4, "Math is broken!"

case.test_function = my_test

suite = TestSuite(name="演示套件")
suite.add_case(case)

runner = TestRunner("Demo Runner")
runner.add_suite(suite)
results = runner.run_all()
print(f"通过率: {results['pass_rate']}%")
```

## 项目结构

```
auto-test-cli/
├── auto_test/
│   ├── __init__.py           # 包初始化
│   ├── uds_client.py         # UDS诊断协议实现
│   ├── can_monitor.py        # CAN总线实时监控
│   ├── test_runner.py        # 测试执行引擎
│   └── report_generator.py   # HTML/Text报告生成
├── tests/                    # 单元测试
├── cli.py                    # 命令行入口
├── requirements.txt
└── README.md
```

## 演示功能

直接运行 `python cli.py` 将自动执行以下演示套件：

| 套件 | 用例 | 说明 |
|------|------|------|
| 仪表盘显示测试 | TC_IC_001 | 车速信号显示验证 |
| 仪表盘显示测试 | TC_IC_002 | 告警灯显示验证 |
| UDS诊断测试 | TC_UDS_001 | 诊断会话切换测试 |
| UDS诊断测试 | TC_UDS_002 | DTC读取与清除测试 |

## 适用场景

- 座舱域/仪表域自动化测试
- UDS诊断协议学习与实践
- 测试用例管理与执行
- CI/CD流水线中的自动化测试集成（生成JSON结果 → Jenkins解析）
- 台架测试脚本开发

## 技术栈

- Python 3.7+
- 纯标准库实现（无外部依赖）
- 内置模拟ECU，学习零成本

## License

MIT
