# can-toolkit

基于 **python-can** 的车载 CAN 总线工具集。支持多种 CAN 硬件接口，提供流量记录、实时监控、日志回放、报文过滤、UDS 诊断等完整功能。

## 为什么用 python-can？

`python-can` 是 Python 生态中最成熟的 CAN 总线库，统一封装了 SocketCAN、PCAN、Vector、Kvaser、slcan 等所有主流 CAN 硬件接口。一次编写，到处运行。

```
your code
    |
 python-can (统一 API)
    |
 +--+--+--+--+--+--+
 |  |  |  |  |  |  |
SC PC VK SL KV VI ...
(SocketCAN / PCAN / Vector / SLCAN / Kvaser / Virtual)
```

## 快速开始

```bash
# 安装
pip install python-can

# 运行演示（无需硬件）
python cli.py demo
```

## 功能概览

| 命令 | 功能 | 示例 |
|------|------|------|
| `info` | 查看可用 CAN 接口 | `python cli.py info` |
| `log` | 记录 CAN 流量 (ASC/CSV/SQLite) | `python cli.py log --preset virtual_0 -o capture.asc` |
| `monitor` | 实时监控 CAN 总线 | `python cli.py monitor --preset virtual_0` |
| `replay` | 回放日志到 CAN 总线 | `python cli.py replay capture.asc --speed 2.0` |
| `send` | 发送 CAN 报文 | `python cli.py send 0x123 DEADBEEF` |
| `filter` | 过滤日志中的报文 | `python cli.py filter capture.asc --include-ids 0x7E0,0x7E8` |
| `diag` | UDS 诊断 | `python cli.py diag read_vin --preset pcan_usb_ch0` |
| `demo` | 运行完整演示 | `python cli.py demo` |

## 支持的 CAN 硬件

| 接口 | 预设 | 驱动需求 |
|------|------|---------|
| Virtual (开发测试) | `virtual_0` | 无 (python-can 内置) |
| Linux SocketCAN | `socketcan_ch0` | 内核 SocketCAN 支持 |
| PEAK PCAN-USB | `pcan_usb_ch0` | PCAN-Basic API |
| Vector VN16xx | `vector_ch0` | Vector XL Driver |
| Serial CAN (USB2CAN) | `slcan_com3` | 串口驱动 |
| Kvaser Leaf | `kvaser_ch0` | Kvaser CANlib |

## Python API 示例

```python
from can_toolkit import CANBusManager, CANLogger, CANMonitor, CANFilter
from can_toolkit.bus_manager import BusConfig

# 连接总线
config = BusConfig(interface="virtual", channel="ch0", bitrate=500000)
bus = CANBusManager(config)
bus.connect()

# 发送
bus.send(can_id=0x123, data=bytes([0xDE, 0xAD, 0xBE, 0xEF]))

# 记录
logger = CANLogger(bus)
logger.start("capture.asc", format="asc")
# ... traffic ...
logger.stop()

# 监控
monitor = CANMonitor(bus)
monitor.start()
# ...
stats = monitor.stop()
print(monitor.get_stats_table())

bus.disconnect()
```

## 架构

```
can-toolkit/
  can_toolkit/
    bus_manager.py    CAN 总线连接管理 (python-can 封装)
    logger.py         CAN 流量记录 (ASC/CSV/SQLite/BLF)
    monitor.py        CAN 实时监控 (统计 + 终端展示)
    replay.py         CAN 日志回放
    filter.py         CAN 报文过滤 (ID掩码/数据匹配/黑白名单)
    diagnostic.py     UDS 诊断服务 (ISO 14229 + ISO-TP)
  cli.py              命令行工具 (argparse)
  examples/
    demo.py           完整 API 使用示例
```

## 与车载面试的关系

本项目展示了：

- **python-can 库的实际应用** — Python 与 CAN 总线交互的标准方式
- **CAN 总线协议理解** — ID 分配、DLC、扩展帧、周期率
- **ISO-TP 多帧传输** — 首帧/连续帧/流控制机制
- **UDS 诊断协议** — 10/11/14/19/22/27/2E/31/34/36/37/3E 服务
- **日志文件标准** — ASC (CANoe 兼容)、SQLite (可查询)
- **自动化测试集成** — 可用于 CI/CD 的 CAN 测试工具链

## License

MIT
