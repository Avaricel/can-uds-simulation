"""
UDS 诊断服务客户端 (基于 python-can)

通过 CAN 总线发送 UDS (ISO 14229) 诊断请求, 支持:
  - 诊断会话控制 (0x10)
  - ECU 复位 (0x11)
  - 安全访问 Seed/Key (0x27)
  - 读取数据 (0x22)
  - 写入数据 (0x2E)
  - 读取 DTC (0x19)
  - 清除 DTC (0x14)
  - 例程控制 (0x31)
  - 请求下载/上传 (0x34/0x35)
  - 传输数据 (0x36)
  - Tester Present (0x3E)

Example:
    >>> mgr = CANBusManager(BusConfig(interface="virtual", channel="ch0"))
    >>> uds = UDSClient(mgr, ecu_id=0x7E0, resp_id=0x7E8)
    >>> mgr.connect()
    >>> uds.tester_present()
    >>> uds.change_session(0x02)  # 编程会话
    >>> dtcs = uds.read_dtc_by_status_mask(0x08)  # 已确认的DTC
"""

import time
import struct
from typing import Optional, List, Tuple, Dict, Any
from enum import IntEnum

try:
    import can
except ImportError:
    pass

from .bus_manager import CANBusManager


class UDSService(IntEnum):
    """ISO 14229-1 UDS 服务 ID"""
    DIAGNOSTIC_SESSION    = 0x10
    ECU_RESET             = 0x11
    SECURITY_ACCESS       = 0x27
    COMMUNICATION_CONTROL = 0x28
    READ_DATA_BY_ID       = 0x22
    READ_MEMORY_BY_ADDR   = 0x23
    READ_SCALING_DATA     = 0x24
    SECURITY_ACCESS_DATA  = 0x27  # 同 0x27
    DYNAMICALLY_DEFINE_ID = 0x2C
    WRITE_DATA_BY_ID      = 0x2E
    ROUTINE_CONTROL       = 0x31
    REQUEST_DOWNLOAD      = 0x34
    REQUEST_UPLOAD        = 0x35
    TRANSFER_DATA         = 0x36
    REQUEST_TRANSFER_EXIT = 0x37
    READ_DTC_INFO         = 0x19
    CLEAR_DTC             = 0x14
    TESTER_PRESENT        = 0x3E


class UDSSession(IntEnum):
    """诊断会话类型"""
    DEFAULT       = 0x01
    PROGRAMMING   = 0x02
    EXTENDED      = 0x03
    SAFETY_SYSTEM = 0x04


class UDSResponseCode(IntEnum):
    """UDS 否定响应码 (NRC)"""
    GENERAL_REJECT         = 0x10
    SERVICE_NOT_SUPPORTED  = 0x11
    SUBFUNC_NOT_SUPPORTED  = 0x12
    INCORRECT_LENGTH       = 0x13
    RESPONSE_TOO_LONG      = 0x14
    BUSY_REPEAT_REQUEST    = 0x21
    CONDITIONS_NOT_CORRECT = 0x22
    REQUEST_SEQUENCE_ERROR = 0x24
    NO_RESPONSE_FROM_SUBNET = 0x25
    REQUEST_OUT_OF_RANGE   = 0x31
    SECURITY_ACCESS_DENIED = 0x33
    INVALID_KEY            = 0x35
    EXCEEDED_NUMBER_OF_ATTEMPTS = 0x36
    UPLOAD_DOWNLOAD_NOT_ACCEPTED = 0x70
    TRANSFER_DATA_SUSPENDED = 0x71
    WRONG_BLOCK_SEQUENCE   = 0x73
    RESPONSE_PENDING       = 0x78


# ── 辅助: ISO-TP ─────────────────────────────────

def _iso_tp_pack(can_id: int, data: bytes, flow_control_id: int,
                  padding: int = 0xAA) -> List[can.Message]:
    """ISO-TP (ISO 15765-2) 打包 CAN 消息"""
    data_len = len(data)
    messages = []

    if data_len <= 7:
        # 单帧: 高4位=0
        sf_data = bytes([data_len]) + data
        if len(sf_data) < 8:
            sf_data += bytes([padding] * (8 - len(sf_data)))
        messages.append(can.Message(
            arbitration_id=can_id, data=sf_data, is_extended_id=False
        ))
    else:
        # 首帧: 高4位=1, 低12位=总长度
        ff_data = bytes([0x10 | ((data_len >> 8) & 0x0F), data_len & 0xFF])
        ff_data += data[:6]
        if len(ff_data) < 8:
            ff_data += bytes([padding] * (8 - len(ff_data)))
        messages.append(can.Message(
            arbitration_id=can_id, data=ff_data, is_extended_id=False
        ))

        # 连续帧: 高4位=2, 低4位=SN(0-15)
        remaining = data[6:]
        sn = 1
        while remaining:
            cf_data = bytes([0x20 | (sn & 0x0F)])
            chunk = remaining[:7]
            cf_data += chunk
            if len(cf_data) < 8:
                cf_data += bytes([padding] * (8 - len(cf_data)))

            # 连续帧通常用不同的 ID (flow_control_id)
            messages.append(can.Message(
                arbitration_id=can_id, data=cf_data, is_extended_id=False
            ))
            remaining = remaining[7:]
            sn = (sn + 1) & 0x0F

    return messages


def _iso_tp_unpack(messages: List[can.Message]) -> Optional[bytes]:
    """ISO-TP 解包"""
    if not messages:
        return None

    result = bytearray()
    total_len = 0

    for i, msg in enumerate(messages):
        if msg.dlc == 0:
            continue
        first_byte = msg.data[0]
        pci_type = (first_byte >> 4) & 0x0F

        if pci_type == 0:  # 单帧
            length = first_byte & 0x0F
            result.extend(msg.data[1:1+length])
            break
        elif pci_type == 1:  # 首帧
            total_len = ((first_byte & 0x0F) << 8) | msg.data[1]
            result.extend(msg.data[2:])
        elif pci_type == 2:  # 连续帧
            sn = first_byte & 0x0F
            result.extend(msg.data[1:])

    if total_len > 0 and len(result) >= total_len:
        return bytes(result[:total_len])

    return bytes(result) if result else None


class UDSClient:
    """
    UDS 诊断客户端

    通过 CAN 总线与目标 ECU 进行 UDS 诊断通信。

    Example:
        >>> mgr = CANBusManager(BusConfig(interface="virtual", channel="ch0"))
        >>> uds = UDSClient(mgr, ecu_id=0x7E0, resp_id=0x7E8)
        >>> mgr.connect()
        >>>
        >>> # 切换扩展会话
        >>> uds.change_session(UDSSession.EXTENDED)
        >>>
        >>> # 安全访问解锁 (level 1)
        >>> seed = uds.security_access_request(1)
        >>> key = uds.calculate_key_default(seed)
        >>> uds.security_access_send_key(1, key)
        >>>
        >>> # 读取 VIN
        >>> vin = uds.read_data_by_id(0xF190)
        >>>
        >>> # 读取 DTC
        >>> dtcs = uds.read_dtc_by_status_mask(0x08)
    """

    # 默认超时 (秒)
    DEFAULT_TIMEOUT = 2.0
    # ISO-TP 连续帧间隔 (秒)
    CF_INTERVAL = 0.01

    def __init__(self, bus_manager: CANBusManager,
                 ecu_id: int = 0x7E0,
                 resp_id: int = 0x7E8,
                 use_extended: bool = False,
                 use_iso_tp: bool = True):
        """
        Args:
            bus_manager: CAN 总线管理器
            ecu_id: ECU 物理寻址 ID (诊断仪发送用)
            resp_id: ECU 响应 ID (诊断仪接收用)
            use_extended: 是否使用扩展帧
            use_iso_tp: 是否使用 ISO-TP 多帧
        """
        self._bus = bus_manager
        self.ecu_id = ecu_id
        self.resp_id = resp_id
        self.use_extended = use_extended
        self.use_iso_tp = use_iso_tp
        self.timeout = self.DEFAULT_TIMEOUT
        self._padding_byte = 0xAA

    # ── 基础收发 ─────────────────────────────────

    def send_raw(self, data: bytes, can_id: Optional[int] = None) -> bool:
        """发送原始 CAN 数据"""
        target_id = can_id if can_id is not None else self.ecu_id
        return self._bus.send(
            can_id=target_id,
            data=data,
            is_extended=self.use_extended,
        )

    def send_request(self, service: UDSService, sub_function: int = 0,
                     data: bytes = b"") -> Optional[List[bytes]]:
        """发送 UDS 请求并等待响应

        Args:
            service: UDS 服务 ID
            sub_function: 子功能 (0=不发送子功能)
            data: 附加数据

        Returns:
            响应数据列表 (多帧时返回多帧数据)
        """
        # 构建请求
        if sub_function:
            req_data = bytes([service.value, sub_function]) + data
        else:
            req_data = bytes([service.value]) + data

        # 通过 ISO-TP 发送
        if self.use_iso_tp and len(req_data) > 7:
            msgs = _iso_tp_pack(self.ecu_id, req_data,
                                self.resp_id, self._padding_byte)
            for msg in msgs:
                self._bus.send(
                    can_id=msg.arbitration_id,
                    data=msg.data,
                    is_extended=msg.is_extended_id,
                )
                if len(msgs) > 1:
                    time.sleep(self.CF_INTERVAL)
        else:
            # 填充到 8 字节
            padded = req_data.ljust(8, bytes([self._padding_byte]))
            self._bus.send(
                can_id=self.ecu_id,
                data=padded,
                is_extended=self.use_extended,
            )

        # 等待单帧响应 (简化: 不实现 ISO-TP 接收的流控)
        return self._wait_response(self.timeout)

    def _wait_response(self, timeout: float) -> Optional[List[bytes]]:
        """等待并解析响应"""
        deadline = time.time() + timeout
        responses: List[can.Message] = []

        while time.time() < deadline:
            msg = self._bus.receive(timeout=min(0.1, deadline - time.time()))
            if msg is None:
                break

            if msg.arbitration_id == self.resp_id:
                responses.append(msg)

                # 检查是否完整
                if len(responses) == 1:
                    first_byte = msg.data[0]
                    pci_type = (first_byte >> 4) & 0x0F
                    if pci_type == 0:  # 单帧
                        return [bytes(msg.data)]
                    elif pci_type == 1:  # 首帧 -> 继续等待连续帧
                        continue
                else:
                    # 多个连续帧
                    return [bytes(r.data) for r in responses]

            time.sleep(0.01)

        return [bytes(r.data) for r in responses] if responses else None

    def _parse_uds_response(self, frames: Optional[List[bytes]]
                            ) -> Tuple[bool, bytes, int]:
        """解析 UDS 响应

        Returns:
            (is_positive, data, nrc)
        """
        if frames is None or len(frames) == 0:
            return False, b"", 0xFF  # 无响应

        # 合并 ISO-TP 帧
        if self.use_iso_tp and len(frames) > 1:
            msgs = []
            for data in frames:
                msgs.append(can.Message(arbitration_id=self.resp_id, data=data))
            payload = _iso_tp_unpack(msgs)
        else:
            payload = frames[0]

        if not payload or len(payload) < 1:
            return False, b"", 0xFF

        first_byte = payload[0]

        if first_byte == 0x7F:
            # 否定响应
            if len(payload) >= 3:
                return False, payload, payload[2]
            return False, payload, 0xFF
        else:
            # 肯定响应: SID + 0x40
            return True, payload, 0

    # ── UDS 服务 ──────────────────────────────────

    def tester_present(self, suppress_response: bool = False) -> bool:
        """Tester Present (0x3E) - 会话保活

        Args:
            suppress_response: 是否抑制响应
        """
        sub = 0x80 if suppress_response else 0x00
        frames = self.send_request(UDSService.TESTER_PRESENT, sub)
        pos, _, _ = self._parse_uds_response(frames)
        return pos

    def change_session(self, session: UDSSession) -> bool:
        """切换诊断会话 (0x10)

        Args:
            session: 目标会话类型
        """
        frames = self.send_request(
            UDSService.DIAGNOSTIC_SESSION, session.value
        )
        pos, data, nrc = self._parse_uds_response(frames)
        if pos:
            return True
        # 常见情况: 编程会话可能不被支持 (NRC 0x12)
        return False

    def ecu_reset(self, reset_type: int = 1) -> bool:
        """ECU 复位 (0x11)

        Args:
            reset_type: 1=硬复位, 2=点火复位, 3=软复位
        """
        frames = self.send_request(UDSService.ECU_RESET, reset_type)
        pos, _, _ = self._parse_uds_response(frames)
        return pos

    def read_data_by_id(self, did: int) -> Optional[bytes]:
        """按标识符读取数据 (0x22)

        Args:
            did: 数据标识符 (如 0xF190=VIN, 0xF18C=序列号)

        Returns:
            原始数据, None=失败
        """
        did_bytes = struct.pack(">H", did)
        frames = self.send_request(
            UDSService.READ_DATA_BY_ID, 0, did_bytes
        )
        pos, data, nrc = self._parse_uds_response(frames)
        if pos and len(data) > 3:
            return data[3:]  # [0x62, didH, didL, ...]
        return None

    def write_data_by_id(self, did: int, value: bytes) -> bool:
        """按标识符写入数据 (0x2E)

        Args:
            did: 数据标识符
            value: 写入值
        """
        did_bytes = struct.pack(">H", did)
        frames = self.send_request(
            UDSService.WRITE_DATA_BY_ID, 0, did_bytes + value
        )
        pos, _, _ = self._parse_uds_response(frames)
        return pos

    # ── 安全访问 ─────────────────────────────────

    def security_access_request(self, level: int = 1) -> Optional[bytes]:
        """请求 Seed (0x27)

        Args:
            level: 安全等级 (1/3/5...)

        Returns:
            Seed 值, None=失败
        """
        frames = self.send_request(
            UDSService.SECURITY_ACCESS, level
        )
        pos, data, nrc = self._parse_uds_response(frames)
        if pos and len(data) > 3:
            return data[3:]  # [0x67, level, seed...]
        return None

    def security_access_send_key(self, level: int, key: bytes) -> bool:
        """发送 Key (0x27)

        Args:
            level: 安全等级
            key: 计算出的密钥
        """
        req_data = bytes([level + 1]) + key
        frames = self.send_request(
            UDSService.SECURITY_ACCESS, 0, req_data
        )
        pos, _, _ = self._parse_uds_response(frames)
        return pos

    @staticmethod
    def calculate_key_default(seed: bytes) -> bytes:
        """默认 Key 计算算法 (示例)

        常见算法: key = seed 按位取反 + 1
        实际项目中应根据具体 ECU 的算法实现。

        Args:
            seed: 从 ECU 获取的 Seed

        Returns:
            计算出的 Key
        """
        # 示例算法: 字节反转 (很多低安全等级 ECU 用这个)
        key = bytearray()
        for b in seed:
            key.append((~b) & 0xFF)
        return bytes(key)

    # ── DTC 诊断 ─────────────────────────────────

    def read_dtc_by_status_mask(self, status_mask: int = 0x08) -> List[Dict[str, Any]]:
        """按状态掩码读取 DTC (0x19 0x02)

        Args:
            status_mask: DTC 状态掩码
                0x01 = testFailed
                0x02 = testFailedThisOperationCycle
                0x04 = pendingDTC
                0x08 = confirmedDTC (常用)
                0x10 = testNotCompletedSinceLastClear
                0x20 = testFailedSinceLastClear
                0x40 = testNotCompletedThisOperationCycle
                0x80 = warningIndicatorRequested

        Returns:
            DTC 列表: [{"code": "P0420", "status": 0x08}, ...]
        """
        frames = self.send_request(
            UDSService.READ_DTC_INFO, 0x02, bytes([status_mask])
        )
        pos, data, nrc = self._parse_uds_response(frames)

        dtcs = []
        if pos and len(data) > 3:
            # 解析: [0x59, 0x02, DTCStatusAvailabilityMask, DTC1[3], status1, ...]
            payload = data[3:]
            i = 0
            while i + 3 < len(payload):
                dtc_bytes = payload[i:i+3]
                status = payload[i+3] if i+3 < len(payload) else 0x00

                # DTC 编码: 高2bits=category, 剩余=code
                dtc_high = (dtc_bytes[0] >> 6) & 0x03
                category_map = {0: "P", 1: "C", 2: "B", 3: "U"}
                category = category_map.get(dtc_high, "?")

                code_num = ((dtc_bytes[0] & 0x3F) << 8) | dtc_bytes[1]
                code = f"{category}{code_num:04d}"
                if dtc_bytes[2] != 0xFF:
                    code += f"_{dtc_bytes[2]:02X}"

                dtcs.append({"code": code, "status": status, "raw": dtc_bytes})
                i += 4

        return dtcs

    def read_dtc_count(self, status_mask: int = 0xFF) -> int:
        """读取 DTC 数量 (0x19 0x01)"""
        frames = self.send_request(
            UDSService.READ_DTC_INFO, 0x01, bytes([status_mask])
        )
        pos, data, nrc = self._parse_uds_response(frames)
        if pos and len(data) >= 5:
            return (data[3] << 8) | data[4]
        return 0

    def clear_dtc(self, group: int = 0xFFFFFF) -> bool:
        """清除 DTC (0x14)

        Args:
            group: DTC 组 (0xFFFFFF=所有, 0x000000=动力总成, 0x400000=车身, 0xC00000=底盘)
        """
        group_bytes = struct.pack(">I", group)[1:]  # 3 bytes
        frames = self.send_request(UDSService.CLEAR_DTC, 0, group_bytes)
        pos, _, _ = self._parse_uds_response(frames)
        return pos

    # ── 例程控制 ─────────────────────────────────

    def routine_control(self, routine_id: int, sub_type: int = 1,
                        data: bytes = b"") -> Optional[Dict[str, Any]]:
        """例程控制 (0x31)

        Args:
            routine_id: 例程 ID (如 0x0202=检查编程依赖, 0xFF00=擦除内存)
            sub_type: 1=启动, 2=停止, 3=请求结果
            data: 附加参数

        Returns:
            {"success": True, "data": b"...", "routine_id": 0x0202}
        """
        rid_bytes = struct.pack(">H", routine_id)
        req_data = bytes([sub_type]) + rid_bytes + data
        frames = self.send_request(UDSService.ROUTINE_CONTROL, 0, req_data)
        pos, data, nrc = self._parse_uds_response(frames)

        if pos:
            return {
                "success": True,
                "data": data[4:] if len(data) > 4 else b"",
                "routine_id": routine_id,
            }
        return {"success": False, "nrc": nrc, "routine_id": routine_id}

    # ── 下载/上传 ────────────────────────────────

    def request_download(self, address: int, size: int,
                         compression: int = 0x00,
                         encryption: int = 0x00) -> Optional[int]:
        """请求下载 (0x34)

        Args:
            address: 目标内存地址
            size: 数据大小
            compression: 压缩方式
            encryption: 加密方式

        Returns:
            每个数据块的最大大小, None=失败
        """
        dfi = 0x00  # Data Format Identifier (addressAndLengthFormatIdentifier)
        # 4字节地址 + 4字节长度
        addr_bytes = struct.pack(">I", address)
        size_bytes = struct.pack(">I", size)
        req_data = bytes([dfi, compression, encryption]) + addr_bytes + size_bytes

        frames = self.send_request(UDSService.REQUEST_DOWNLOAD, 0, req_data)
        pos, data, nrc = self._parse_uds_response(frames)

        if pos and len(data) > 3:
            # 响应: [0x74, lengthFormat, maxBlockLength]
            if len(data) >= 5:
                return struct.unpack(">H", data[3:5])[0]
            return data[3]
        return None

    def transfer_data(self, block_counter: int, data: bytes) -> bool:
        """传输数据 (0x36)"""
        req_data = bytes([block_counter]) + data
        frames = self.send_request(UDSService.TRANSFER_DATA, 0, req_data)
        pos, _, _ = self._parse_uds_response(frames)
        return pos

    def request_transfer_exit(self) -> bool:
        """退出传输 (0x37)"""
        frames = self.send_request(UDSService.REQUEST_TRANSFER_EXIT)
        pos, _, _ = self._parse_uds_response(frames)
        return pos

    def download_file(self, address: int, data: bytes,
                      block_size: int = 128) -> bool:
        """完整文件下载流程

        Args:
            address: 目标地址
            data: 文件数据
            block_size: 每块大小
        """
        # 1. 请求下载
        max_block = self.request_download(address, len(data))
        if max_block is None:
            print("[UDS] Download request rejected.")
            return False

        # 2. 分块传输
        block_counter = 1
        total = len(data)
        sent = 0

        while sent < total:
            chunk = data[sent:sent + min(block_size, max_block or block_size)]
            if not self.transfer_data(block_counter, chunk):
                print(f"[UDS] Transfer failed at block {block_counter}")
                return False
            sent += len(chunk)
            block_counter = (block_counter % 255) + 1

        # 3. 退出传输
        self.request_transfer_exit()
        return True

    # ── 快捷方法 ─────────────────────────────────

    def read_vin(self) -> Optional[str]:
        """读取 VIN (DID 0xF190)"""
        data = self.read_data_by_id(0xF190)
        if data:
            return data.decode("ascii", errors="replace").strip("\x00")
        return None

    def read_serial_number(self) -> Optional[str]:
        """读取序列号 (DID 0xF18C)"""
        data = self.read_data_by_id(0xF18C)
        if data:
            return data.decode("ascii", errors="replace").strip("\x00")
        return None

    def read_ecu_software_version(self) -> Optional[str]:
        """读取 ECU 软件版本 (DID 0xF188/F189)"""
        data = self.read_data_by_id(0xF188)
        if data:
            return data.decode("ascii", errors="replace").strip("\x00")
        return None
