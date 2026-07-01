# Vehicle Signal Simulator 🚗

车辆信号仿真器 — 模拟发动机、变速箱、车身等ECU信号，通过虚拟CAN总线输出，支持多种驾驶场景和故障注入。

## 功能

- **发动机仿真** — 转速、水温、机油压力、进气温度、节气门开度、油耗
- **变速箱仿真** — 挡位切换、换挡模式、变速箱油温
- **车身仿真** — 灯光系统、车门状态、胎压监测(TPMS)、油量、里程
- **驾驶场景** — 冷启动暖机、城市工况、高速巡航、0-100加速
- **故障注入** — 模拟胎压低、车门未关、低油量等故障
- **CAN输出** — 信号按DBC定义打包为CAN报文，支持文本/CSV/JSON输出

## 快速开始

```bash
git clone https://github.com/Avaricel/vehicle-signal-simulator.git
cd vehicle-signal-simulator

# 直接运行（5秒默认演示）
python cli.py

# 运行演示脚本（3个完整演示）
python examples/demo.py
```

## 命令行

### 运行仿真

```bash
# 默认场景，终端显示 (5秒, 50Hz)
python cli.py run

# 冷启动暖机场景 (10秒)
python cli.py run --scenario warmup --duration 10

# 城市工况 (20秒)
python cli.py run --scenario city --duration 20

# 高速巡航，导出CSV
python cli.py run --scenario highway --duration 15 --output csv --file highway.csv

# 导出JSON（可用于后续分析）
python cli.py run --scenario accel --output json --file accel_data.json

# 注入故障
python cli.py run --fault tpms_low
```

### 故障注入

```bash
# 胎压低告警
python cli.py fault --type tpms_low

# 车门未关
python cli.py fault --type door_open

# 低油量
python cli.py fault --type fuel_low

# 恢复正常
python cli.py fault --type all_normal
```

## 仿真信号一览

### 发动机 (0x0C8 - 10ms周期)

| 信号 | 单位 | 范围 | 说明 |
|------|------|------|------|
| EngineSpeed | rpm | 0-8000 | 发动机转速，怠速800rpm |
| CoolantTemp | °C | -40~215 | 冷却液温度，含暖机过程 |
| EngineOilPressure | kPa | 0-700 | 随转速和温度变化 |
| IntakeAirTemp | °C | -40~130 | 随发动机热辐射上升 |
| ThrottlePosition | % | 0-100 | 节气门开度 |

### 变速箱 (0x152 - 100ms周期)

| 信号 | 值 | 说明 |
|------|-----|------|
| GearPosition | 0=P,1=R,2=N,3=D | 挡位 |
| GearShiftMode | 0=Normal,1=Sport,2=Eco | 换挡模式 |
| TransOilTemp | °C | 变速箱油温 |

### 车身 (0x1A4/0x236 - 200ms/500ms)

| 信号 | 说明 |
|------|------|
| DoorFL/FR/RL/RR | 四门状态 |
| TurnSignal | 转向灯 |
| TPMS_FL/FR/RL/RR | 四轮胎压 |
| FuelLevel/Odometer | 油量/里程 |

## Python API

```python
from simulator.base import VehicleState
from simulator.engine import EngineSimulator
from simulator.transmission import TransmissionSimulator
from simulator.body import BodySimulator
from simulator.can_emitter import CANEmitter, TextOutput

# 创建车辆状态
vehicle = VehicleState()
vehicle.start_ignition()

# 创建仿真模块
engine = EngineSimulator(vehicle)
trans = TransmissionSimulator(vehicle)
body = BodySimulator(vehicle)

# 创建CAN发送器
emitter = CANEmitter(output=TextOutput())
emitter.start()

# 仿真循环
dt = 0.01  # 10ms步进
for _ in range(1000):  # 10秒
    signals = {}
    signals.update(engine.update(dt))
    signals.update(trans.update(dt))
    signals.update(body.update(dt))
    signals["VehicleSpeed"] = vehicle.vehicle_speed
    emitter.emit(signals, dt)

emitter.stop()
```

## 项目结构

```
vehicle-signal-simulator/
├── simulator/
│   ├── __init__.py       # 包初始化
│   ├── base.py           # 信号基类 & 车辆状态
│   ├── engine.py         # 发动机仿真
│   ├── transmission.py   # 变速箱仿真
│   ├── body.py           # 车身仿真
│   └── can_emitter.py    # CAN报文发送器
├── examples/
│   └── demo.py           # 完整演示脚本
├── cli.py                # 命令行入口
├── requirements.txt
└── README.md
```

## 适用场景

- 仪表/座舱域控制器台架测试（无需实车）
- CAN信号验证与DBC调试
- HIL台架仿真数据源
- 车载测试学员练习（了解CAN报文结构）
- 故障注入与异常场景覆盖

## 技术栈

- Python 3.7+
- 纯标准库，零依赖
- 模块化设计，易于扩展新ECU

## 扩展指南

添加新ECU只需三步：

```python
# 1. 创建仿真模块
class ADASSimulator(SignalGenerator):
    def update(self, dt):
        return {"ACC_Status": 1, "LDW_Warning": 0}

# 2. 定义CAN配置
ADAS_CONFIG = CANMessageConfig(
    can_id=0x300, name="ADAS_Status", cycle_ms=100,
    signals=["ACC_Status", "LDW_Warning"],
    signal_formats={...}
)

# 3. 添加到emitter
emitter = CANEmitter(configs=DASHBOARD_CAN_CONFIGS + [ADAS_CONFIG])
```

## License

MIT
