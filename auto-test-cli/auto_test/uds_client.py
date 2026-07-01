"""
UDS诊断客户端 - ISO 14229 UDS协议实现

支持的服务：
- 0x10: Diagnostic Session Control (诊断会话控制)
- 0x11: ECU Reset (ECU复位)
- 0x22: Read Data By Identifier (读取数据)
- 0x27: Security Access (安全访问)
- 0x19: Read DTC Information (读取故障码)
- 0x14: Clear DTC (清除故障码)
- 0x31: Routine Control (例程控制)
- 0x3E: Tester Present (测试仪在线)
- 0x2E: Write Data By Identifier (写入数据)
"""

import time
import struct
from enum import IntEnum
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


class UDSService(IntEnum):
    """UDS服务ID"""
    DIAGNOSTIC_SESSION_CONTROL = 0x10
    ECU_RESET = 0x11
    SECURITY_ACCESS = 0x27
    READ_DATA_BY_ID = 0x22
    READ_MEMORY_BY_ADDRESS = 0x23
    READ_SCALING_BY_ID = 0x24
    CLEAR_DTC = 0x14
    READ_DTC = 0x19
    WRITE_DATA_BY_ID = 0x2E
    ROUTINE_CONTROL = 0x31
    TESTER_PRESENT = 0x3E
    CONTROL_DTC_SETTING = 0x85


class UDSSession(IntEnum):
    """诊断会话类型"""
    DEFAULT = 0x01
    PROGRAMMING = 0x02
    EXTENDED = 0x03
    SAFETY_SYSTEM = 0x04


class UDSResetType(IntEnum):
    """ECU复位类型"""
    HARD_RESET = 0x01
    KEY_OFF_ON = 0x02
    SOFT_RESET = 0x03


class UDSResponse(IntEnum):
    """UDS响应码"""
    POSITIVE = 0x40  # 正响应偏移
    NEGATIVE = 0x7F  # 负响应

    # NRC (Negative Response Codes)
    @dataclass
    class NRC:
        GENERAL_REJECT = 0x10
        SERVICE_NOT_SUPPORTED = 0x11
        SUB_FUNC_NOT_SUPPORTED = 0x12
        INCORRECT_MESSAGE_LENGTH = 0x13
        CONDITIONS_NOT_CORRECT = 0x22
        REQUEST_SEQUENCE_ERROR = 0x24
        REQUEST_OUT_OF_RANGE = 0x31
        SECURITY_ACCESS_DENIED = 0x33
        INVALID_KEY = 0x35
        EXCEED_NUMBER_OF_ATTEMPTS = 0x36
        REQUIRED_TIME_DELAY_NOT_EXPIRED = 0x37
        UPLOAD_DOWNLOAD_NOT_ACCEPTED = 0x70
        TRANSFER_DATA_SUSPENDED = 0x71
        GENERAL_PROGRAMMING_FAILURE = 0x72
        WRONG_BLOCK_SEQUENCE = 0x73


@dataclass
class UDSMessage:
    """UDS报文"""
    service_id: int
    sub_function: int = 0
    data: bytes = b""
    can_id_tester: int = 0x7E0  # 诊断仪CAN ID
    can_id_ecu: int = 0x7E8     # ECU响应CAN ID

    def to_bytes(self) -> bytes:
        """序列化为CAN数据"""
        payload = bytes([self.service_id])
        if self.sub_function:
            payload += bytes([self.sub_function])
        payload += self.data
        return payload[:8]  # CAN帧最多8字节

    @classmethod
    def from_bytes(cls, data: bytes,
                   can_id_tester: int = 0x7E0,
                   can_id_ecu: int = 0x7E8) -> "UDSMessage":
        """从CAN数据反序列化"""
        if len(data) < 1:
            raise ValueError("Empty UDS message")
        return cls(
            service_id=data[0],
            sub_function=data[1] if len(data) > 1 else 0,
            data=data[2:] if len(data) > 2 else b"",
            can_id_tester=can_id_tester,
            can_id_ecu=can_id_ecu,
        )


@dataclass
class UDSResponseData:
    """UDS响应数据"""
    positive: bool
    service_id: int
    response_code: int = 0
    data: bytes = b""
    raw_bytes: bytes = b""
    error_message: str = ""

    def __str__(self):
        if self.positive:
            return (f"UDS Positive Response: Service 0x{self.service_id:02X}, "
                    f"Data: {self.data.hex().upper() if self.data else 'None'}")
        else:
            return (f"UDS Negative Response: Service 0x{self.service_id:02X}, "
                    f"NRC: 0x{self.response_code:02X} ({self.error_message})")


class UDSClient:
    """
    UDS诊断客户端

    使用方式：
        client = UDSClient(can_id_tester=0x7E0, can_id_ecu=0x7E8)
        # 连接后调用send_request
    """

    NRC_MESSAGES = {
        0x10: "General Reject",
        0x11: "Service Not Supported",
        0x12: "Sub-Function Not Supported",
        0x13: "Incorrect Message Length",
        0x22: "Conditions Not Correct",
        0x24: "Request Sequence Error",
        0x31: "Request Out Of Range",
        0x33: "Security Access Denied",
        0x35: "Invalid Key",
        0x36: "Exceed Number Of Attempts",
        0x37: "Required Time Delay Not Expired",
        0x70: "Upload/Download Not Accepted",
        0x72: "General Programming Failure",
    }

    def __init__(self, can_id_tester: int = 0x7E0,
                 can_id_ecu: int = 0x7E8,
                 is_simulated: bool = True):
        self.can_id_tester = can_id_tester
        self.can_id_ecu = can_id_ecu
        self.is_simulated = is_simulated
        self._session = UDSSession.DEFAULT
        self._security_unlocked = False
        self._sequence_number = 0

        # 模拟数据存储 (用于演示/测试)
        self._sim_data: Dict[int, bytes] = {}
        self._sim_dtc: List[Dict] = []
        self._sim_callback = None

    def set_sim_callback(self, callback):
        """设置模拟模式下的回调函数"""
        self._sim_callback = callback

    def send_request(self, service: UDSService,
                     sub_function: int = 0,
                     data: bytes = b"",
                     timeout: float = 1.0) -> UDSResponseData:
        """发送UDS请求并获取响应"""
        msg = UDSMessage(
            service_id=service.value,
            sub_function=sub_function,
            data=data,
            can_id_tester=self.can_id_tester,
            can_id_ecu=self.can_id_ecu,
        )

        request_bytes = msg.to_bytes()

        if self.is_simulated:
            response = self._simulate_response(service, sub_function, data)
        else:
            response = self._send_can(request_bytes, timeout)

        return response

    def _simulate_response(self, service: UDSService,
                           sub_function: int,
                           data: bytes) -> UDSResponseData:
        """模拟ECU响应"""
        if self._sim_callback:
            return self._sim_callback(service, sub_function, data)

        # 默认模拟逻辑
        if service == UDSService.DIAGNOSTIC_SESSION_CONTROL:
            session_map = {0x01: UDSSession.DEFAULT, 0x02: UDSSession.PROGRAMMING,
                          0x03: UDSSession.EXTENDED}
            if sub_function in session_map:
                self._session = session_map[sub_function]
                return UDSResponseData(
                    positive=True,
                    service_id=service.value,
                    response_code=sub_function,
                    data=bytes([0x00, 0x32, 0x01, 0xF4])  # P2 timing
                )
            return UDSResponseData(positive=False, service_id=service.value,
                                   response_code=0x12, error_message="Sub-Function Not Supported")

        elif service == UDSService.ECU_RESET:
            if sub_function == UDSResetType.HARD_RESET:
                return UDSResponseData(positive=True, service_id=service.value,
                                       response_code=sub_function)
            return UDSResponseData(positive=False, service_id=service.value,
                                   response_code=0x12)

        elif service == UDSService.READ_DATA_BY_ID:
            did = struct.unpack(">H", data[:2])[0]
            if did in self._sim_data:
                return UDSResponseData(positive=True, service_id=service.value,
                                       data=self._sim_data[did])
            return UDSResponseData(positive=False, service_id=service.value,
                                   response_code=0x31, error_message="Request Out Of Range")

        elif service == UDSService.SECURITY_ACCESS:
            if sub_function == 0x01:  # Request Seed
                seed = bytes([0x01, 0x02, 0x03, 0x04])
                return UDSResponseData(positive=True, service_id=service.value,
                                       response_code=sub_function, data=seed)
            elif sub_function == 0x02:  # Send Key
                expected = bytes([0x10, 0x20, 0x30, 0x40])
                if data == expected:
                    self._security_unlocked = True
                    return UDSResponseData(positive=True, service_id=service.value,
                                           response_code=sub_function)
                return UDSResponseData(positive=False, service_id=service.value,
                                       response_code=0x35, error_message="Invalid Key")

        elif service == UDSService.READ_DTC:
            # 构造模拟DTC报告数据格式
            dtc_data = bytes([0x59, 0x02, 0xFF])  # report header
            for dtc_info in self._sim_dtc[:10]:
                # dtc_info: {"raw": bytes(3)} or {"code": "P0500", "status": 0x2F}
                if "raw" in dtc_info:
                    dtc_data += dtc_info["raw"]
                else:
                    # 从 DTC code 构造原始字节
                    raw = self._dtc_code_to_bytes(dtc_info["code"], dtc_info.get("status", 0x2F))
                    dtc_data += raw
            return UDSResponseData(positive=True, service_id=service.value, data=dtc_data)

        elif service == UDSService.CLEAR_DTC:
            self._sim_dtc.clear()
            return UDSResponseData(positive=True, service_id=service.value)

        elif service == UDSService.ROUTINE_CONTROL:
            return UDSResponseData(positive=True, service_id=service.value,
                                   response_code=sub_function)

        elif service == UDSService.TESTER_PRESENT:
            return UDSResponseData(positive=True, service_id=service.value,
                                   response_code=0x00)

        return UDSResponseData(positive=False, service_id=service.value,
                               response_code=0x11, error_message="Service Not Supported")

    def _send_can(self, data: bytes, timeout: float) -> UDSResponseData:
        """通过真实CAN总线发送（需要接入CAN硬件时实现）"""
        # 预留接口 — 接入python-can后实现
        # import can
        # bus = can.interface.Bus(channel='can0', bustype='socketcan')
        # msg = can.Message(arbitration_id=self.can_id_tester, data=data, is_extended_id=False)
        # bus.send(msg)
        # response = bus.recv(timeout=timeout)
        raise NotImplementedError("Real CAN hardware not connected. Use is_simulated=True")

    # === 高级API ===

    def change_session(self, session: UDSSession) -> UDSResponseData:
        """切换诊断会话"""
        return self.send_request(UDSService.DIAGNOSTIC_SESSION_CONTROL,
                                 sub_function=session.value)

    def ecu_reset(self, reset_type: UDSResetType = UDSResetType.HARD_RESET) -> UDSResponseData:
        """ECU复位"""
        return self.send_request(UDSService.ECU_RESET,
                                 sub_function=reset_type.value)

    def read_data_by_id(self, did: int) -> UDSResponseData:
        """按标识符读取数据"""
        data = struct.pack(">H", did)
        return self.send_request(UDSService.READ_DATA_BY_ID, data=data)

    def write_data_by_id(self, did: int, value: bytes) -> UDSResponseData:
        """按标识符写入数据"""
        data = struct.pack(">H", did) + value
        return self.send_request(UDSService.WRITE_DATA_BY_ID, data=data)

    def security_access(self, seed_calculator=None) -> Tuple[bool, str]:
        """安全访问流程"""
        # Step 1: Request Seed
        resp = self.send_request(UDSService.SECURITY_ACCESS, sub_function=0x01)
        if not resp.positive:
            return False, f"Request Seed Failed: {resp.error_message}"

        seed = resp.data
        # Step 2: Calculate Key (简单异或示例，实际使用ECU特定算法)
        if seed_calculator:
            key = seed_calculator(seed)
        else:
            key = bytes([b ^ 0xFF for b in seed])

        resp = self.send_request(UDSService.SECURITY_ACCESS,
                                 sub_function=0x02, data=key)
        if resp.positive:
            self._security_unlocked = True
            return True, "Security Access Granted"
        return False, f"Send Key Failed: {resp.error_message}"

    def read_dtc(self) -> List[Dict]:
        """读取故障码"""
        resp = self.send_request(UDSService.READ_DTC, sub_function=0x02)
        if not resp.positive:
            return []
        # 解析DTC报告
        dtcs = []
        data = resp.data[3:]  # 跳过报告头
        i = 0
        while i + 3 <= len(data):
            dtc_bytes = data[i:i+3]
            status = data[i+2]
            dtc_code = (f"{(dtc_bytes[0] >> 2) & 0x03:x}{dtc_bytes[0] & 0x03:x}"
                        f"{dtc_bytes[1]:02X}{dtc_bytes[2]:02X}")
            dtcs.append({
                "code": dtc_code.upper(),
                "status": status,
                "status_str": self._parse_dtc_status(status),
            })
            i += 3
        return dtcs

    def clear_dtc(self) -> UDSResponseData:
        """清除故障码"""
        return self.send_request(UDSService.CLEAR_DTC, sub_function=0xFF)

    def tester_present(self) -> UDSResponseData:
        """测试仪在线保活"""
        return self.send_request(UDSService.TESTER_PRESENT, sub_function=0x00)

    def routine_control(self, routine_id: int,
                        control_type: int = 0x01) -> UDSResponseData:
        """例程控制"""
        data = struct.pack(">H", routine_id)
        return self.send_request(UDSService.ROUTINE_CONTROL,
                                 sub_function=control_type, data=data)

    @staticmethod
    def _parse_dtc_status(status: int) -> str:
        """解析DTC状态字节"""
        descriptions = []
        if status & 0x01: descriptions.append("TEST_FAILED")
        if status & 0x02: descriptions.append("TEST_FAILED_THIS_OPERATION_CYCLE")
        if status & 0x04: descriptions.append("PENDING_DTC")
        if status & 0x08: descriptions.append("CONFIRMED_DTC")
        if status & 0x10: descriptions.append("TEST_NOT_COMPLETED_SINCE_LAST_CLEAR")
        if status & 0x20: descriptions.append("TEST_FAILED_SINCE_LAST_CLEAR")
        if status & 0x40: descriptions.append("TEST_NOT_COMPLETED_THIS_OPERATION_CYCLE")
        if status & 0x80: descriptions.append("WARNING_INDICATOR_REQUESTED")
        return " | ".join(descriptions) if descriptions else "NO_FLAG"

    def set_sim_data(self, did: int, value: bytes):
        """设置模拟数据"""
        self._sim_data[did] = value

    def add_sim_dtc(self, code: str = "P0500", status: int = 0x2F):
        """添加模拟DTC"""
        self._sim_dtc.append({"code": code, "status": status})

    @staticmethod
    def _dtc_code_to_bytes(code: str, status: int = 0x2F) -> bytes:
        """将DTC码 (如P0500) 转换为3字节UDS DTC格式"""
        category_map = {'P': 0, 'C': 1, 'B': 2, 'U': 3}
        cat = category_map.get(code[0].upper(), 0)
        digits = code[1:].strip()
        if len(digits) >= 4:
            d1 = int(digits[0])
            d2 = int(digits[1])
            d3 = int(digits[2]) if len(digits) > 2 else 0
            d4 = int(digits[3]) if len(digits) > 3 else 0
            high_byte = (cat << 6) | (d1 << 4) | d2
            mid_byte = (d3 << 4) | d4
            return bytes([high_byte, mid_byte, status])
        return bytes([0, 0, status])


# === 常用DID定义（参考ISO 14229-1） ===

class StandardDID:
    """常用标准DID"""
    VIN = 0xF190              # 车辆识别码
    ECU_SERIAL = 0xF18C        # ECU序列号
    SW_VERSION = 0xF18A        # 软件版本号
    HW_VERSION = 0xF193        # 硬件版本号
    BOOT_SW_VERSION = 0xF18B   # Bootloader版本
    SUPPLIER_ID = 0xF18E       # 供应商ID
    SYSTEM_NAME = 0xF197       # 系统名称
    ECU_MANUFACTURE_DATE = 0xF199  # ECU生产日期
