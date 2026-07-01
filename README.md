# CAN UDS ECU Simulation

基于 CAPL (CAN Access Programming Language) 实现的 UDS (Unified Diagnostic Services) ECU 仿真节点，用于 CANoe 环境下的车载诊断协议测试。

## 功能概述

### 支持的 UDS 服务

| 服务ID | 服务名称 | 说明 |
|--------|---------|------|
| 0x10 | 诊断会话控制 | 支持默认/扩展/编程会话切换 |
| 0x11 | ECU 复位 | 支持硬复位/软复位 |
| 0x14 | 清除诊断信息 | 支持清除所有 DTC（需安全解锁） |
| 0x19 | 读取 DTC 信息 | 支持按状态掩码报告 DTC 数量/列表 |
| 0x22 | 按标识符读数据 | 支持 F18C（序列号）、F190（VIN）读取 |
| 0x27 | 安全访问 | Seed/Key 安全解锁机制 |
| 0x28 | 通信控制 | 禁止/恢复报文收发（需安全解锁） |
| 0x2E | 按标识符写数据 | 支持 VIN/序列号写入（需安全解锁） |
| 0x31 | 例程控制 | 支持 0x0203 硬件自检例程（需安全解锁） |
| 0x34 | 请求下载 | 支持内存下载请求（需安全解锁） |
| 0x36 | 传输数据 | 支持分块数据传输（需安全解锁） |
| 0x37 | 请求退出传输 | 结束传输会话（需安全解锁） |
| 0x3E | Tester Present | 会话保活 |

### 核心特性

- **ISO-TP 多帧传输**：支持超过 7 字节的 UDS 消息通过多帧协议传输
- **安全访问控制**：Seed/Key 机制保护敏感服务（14/2E/28/31/34/36/37）
- **VIN 写入支持**：支持 17 字节 ASCII 和 34 字节 HEX 文本两种格式
- **DTC 管理**：预置 3 个故障码（P0420/B0341/C0121），支持状态掩码筛选
- **会话超时**：默认 5 秒超时自动回退到默认会话
- **通信控制**：支持 28 服务禁止/恢复通信

## 项目结构

```
can-uds-simulation/
├── README.md
└── capl/
    └── uds_ecu_simulation.can    # CAPL 源码
```

## 使用方式

1. 在 CANoe 中创建新工程
2. 导入 `capl/uds_ecu_simulation.can` 作为仿真节点
3. 配置节点 ID: ECU=0x601, 诊断仪=0x701
4. 运行仿真，使用诊断仪发送 UDS 请求进行测试

## 技术栈

- **语言**: CAPL (CAN Access Programming Language)
- **协议**: CAN/CAN FD, ISO-TP (ISO 15765-2), UDS (ISO 14229)
- **工具链**: Vector CANoe

## 面试相关

本项目展示了以下车载测试核心能力：

- UDS 诊断协议理解（10/11/14/19/22/27/28/2E/31/34/36/37/3E）
- ISO-TP 多帧传输（首帧/连续帧/流控制）
- CAN 总线通信原理
- 安全访问 Seed/Key 机制
- DTC 故障码管理
- Vector CANoe/CAPL 开发经验
