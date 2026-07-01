# CAN Message Analyzer 🚗

车载CAN总线报文解析与分析工具 —— 纯Python实现，支持DBC文件解析、CAN日志分析、信号解码和数据可视化。

## 功能

- **DBC文件解析** — 完整解析Vector DBC格式，提取Message和Signal定义
- **CAN日志解析** — 支持CANoe ASC、candump等多种格式
- **信号解码** — 基于DBC将CAN原始数据解码为物理值
- **统计分析** — 帧率、周期诊断、CAN ID分布统计
- **信号可视化** — 提取时间序列，生成信号曲线图
- **数据导出** — CSV/JSON格式导出

## 快速开始

### 安装

```bash
git clone https://github.com/Avaricel/can-message-analyzer.git
cd can-message-analyzer
# 无需额外依赖即可使用核心功能
# 可选：pip install -r requirements.txt  (可视化需要matplotlib)
```

### 命令行使用

```bash
# 解析DBC文件
python cli.py dbc parse examples/cluster_demo.dbc

# 解析CAN日志并解码
python cli.py log parse your_can_log.asc --dbc examples/cluster_demo.dbc

# 统计分析
python cli.py log stats your_can_log.asc --dbc examples/cluster_demo.dbc

# 提取指定信号
python cli.py signal extract your_can_log.asc --dbc examples/cluster_demo.dbc -s EngineSpeed VehicleSpeed

# 绘制信号曲线
python cli.py signal plot your_can_log.asc --dbc examples/cluster_demo.dbc -s EngineSpeed VehicleSpeed -o plot.png

# 导出CSV
python cli.py log export your_can_log.asc -o output.csv
```

### Python API

```python
from can_analyzer.dbc_parser import DBCParser
from can_analyzer.can_parser import CANLogParser

# 1. 解析DBC
dbc = DBCParser()
dbc.parse("cluster.dbc")
print(dbc.summary())

# 2. 解析CAN日志
parser = CANLogParser(dbc)
parser.load_file("candump.log")

# 3. 解码信号
decoded = parser.decode_with_dbc()
for item in decoded[:5]:
    print(f"[{item['message_name']}] {item['signals']}")

# 4. 统计分析
stats = parser.get_statistics()
print(stats)
```

### 运行演示

```bash
python examples/demo.py
```

## 项目结构

```
can-message-analyzer/
├── can_analyzer/
│   ├── __init__.py          # 包初始化
│   ├── dbc_parser.py        # DBC文件解析器
│   ├── can_parser.py        # CAN日志解析器
│   └── visualizer.py        # 信号可视化
├── examples/
│   ├── cluster_demo.dbc     # 示例DBC文件（仪表域）
│   └── demo.py              # 完整演示脚本
├── cli.py                   # 命令行入口
├── requirements.txt
└── README.md
```

## 支持的CAN日志格式

| 格式 | 示例 | 状态 |
|------|------|------|
| CANoe ASCII (.asc) | `0.000 1 2F4 Rx d 8 00 00 ...` | ✅ 支持 |
| candump | `(0.001) can0 2F4#00000000` | ✅ 支持 |
| 简单格式 | `0.001 2F4 0000000000000000` | ✅ 支持 |

## DBC示例

项目附带了一个仪表域DBC文件 (`examples/cluster_demo.dbc`)，包含以下报文：

| CAN ID | 报文名称 | 典型信号 | 周期 |
|--------|---------|---------|------|
| 0x0C8 | IC_Dashboard | 发动机转速、车速、水温、油量 | 10ms |
| 0x130 | IC_Lamps | 转向灯、远光、近光、雾灯 | 50ms |
| 0x152 | IC_GearInfo | 挡位、变速箱油温 | 100ms |
| 0x1A4 | IC_Doors | 四门+后备箱+引擎盖状态 | - |
| 0x1F5 | IC_DiagResp | 诊断响应 | - |
| 0x236 | IC_TPMS | 胎压监测 | - |

## 技术栈

- Python 3.7+
- 纯标准库实现核心功能（无外部依赖）
- matplotlib（可选，用于绘图）

## 适用场景

- 车载测试工程师日常CAN日志分析
- 仪表/座舱域控制器信号验证
- 实车路试数据回放与分析
- CAN总线负载率评估
- 测试脚本开发（作为CAN数据处理基础库）

## License

MIT
