# 车载测试项目集

车载测试方向的技术项目集合，涵盖 CAPL UDS 仿真、Python CAN 报文分析、自动化测试框架、车辆信号仿真。

---

## 项目列表

### 1. [capl/](./capl/) — CAN UDS ECU 仿真 (CAPL)

基于 CAPL 实现的 UDS 诊断协议 ECU 仿真节点，用于 CANoe 环境。

| 技术 | 内容 |
|------|------|
| 语言 | CAPL |
| 协议 | CAN, ISO-TP, UDS (ISO 14229) |
| 工具 | Vector CANoe |
| 代码量 | 1467 行 |

**核心能力**: UDS 12 项服务实现、ISO-TP 多帧传输、Seed/Key 安全访问、DTC 管理

---

### 2. [can-message-analyzer/](./can-message-analyzer/) — CAN 报文解析与分析 (Python)

Python 实现的 CAN 报文解析工具，支持 DBC 文件解析、CAN 日志解码、信号可视化。

| 技术 | 内容 |
|------|------|
| 语言 | Python 3 |
| 核心能力 | DBC 解析、Intel/Motorola 位序、信号值提取、图表输出 |
| 代码量 | 1259 行 |

```bash
# 快速体验
cd can-message-analyzer
python examples/demo.py
```

---

### 3. [auto-test-cli/](./auto-test-cli/) — 车载测试自动化 CLI (Python)

车载测试命令行工具，集成 UDS 诊断、CAN 监控、测试用例管理、HTML 报告生成。

| 技术 | 内容 |
|------|------|
| 语言 | Python 3 |
| 核心能力 | UDS 诊断客户端、DTC 读写、测试用例编排、HTML 测试报告 |
| 代码量 | 1755 行 |

```bash
# 运行演示
cd auto-test-cli
python cli.py
```

---

### 4. [vehicle-signal-simulator/](./vehicle-signal-simulator/) — 车辆信号仿真器 (Python)

模拟发动机、变速箱、车身等 ECU 信号并通过 CAN 输出，支持故障注入。

| 技术 | 内容 |
|------|------|
| 语言 | Python 3 |
| 核心能力 | 发动机/变速箱/车身信号模型、CAN 帧封装、故障注入、日志导出 |
| 代码量 | 1430 行 |

```bash
# 运行仿真
cd vehicle-signal-simulator
python cli.py run --duration 5 --rate 50
```

---

## 技术栈总览

| 技术领域 | 涉及内容 |
|----------|---------|
| 编程语言 | Python, CAPL |
| 车载协议 | CAN/CAN FD, ISO-TP, UDS (ISO 14229) |
| 工具链 | Vector CANoe, DBC |
| 测试方法 | 自动化测试、测试用例管理、测试报告生成 |
| 仿真 | ECU 仿真、信号建模、故障注入 |

---

## 面试价值

四个项目覆盖车载测试面试中经常被问到的核心领域：

- CAN 总线通信原理 + DBC 信号解析
- UDS 诊断协议 (10/11/14/19/22/27/28/2E/31/34/36/37/3E)
- ISO-TP 多帧传输机制
- 安全访问 Seed/Key 流程
- 自动化测试框架设计
- Python 在车载测试中的应用
- 信号仿真与故障注入
