"""
CAN 报文过滤器

提供灵活的 CAN 报文过滤规则, 支持:
  - ID 范围过滤
  - ID 掩码过滤 (硬件风格)
  - 数据内容匹配
  - 组合过滤 (AND/OR)

Example:
    >>> f = CANFilter()
    >>> f.add_id_mask(can_id=0x600, mask=0x7F0)  # 0x600-0x60F
    >>> f.add_data_match(offset=0, value=0x02)   # 第1字节=0x02
    >>> if f.match(msg):
    ...     print("matched!")
"""

from typing import List, Set, Optional, Callable, Tuple


class CANFilter:
    """
    CAN 报文过滤器

    支持多种过滤规则组合:

    Example:
        >>> f = CANFilter()
        >>> # ID 过滤: 只接收 0x100-0x1FF
        >>> f.add_id_range(0x100, 0x1FF)
        >>> # 掩码过滤: 只接收 0x7E8-0x7EF (UDS 响应)
        >>> f.add_id_mask(0x7E8, 0x7F0)
        >>> # 数据匹配: 第1字节=0x10 (首帧)
        >>> f.add_data_match(offset=0, value=0x10)
        >>> msg = can.Message(arbitration_id=0x7E8, data=[0x10, 0x0E, ...])
        >>> f.match(msg)  # True
    """

    def __init__(self, mode: str = "or"):
        """
        Args:
            mode: "or" 任意规则匹配即通过, "and" 所有规则都满足才通过
        """
        self.mode = mode.lower()  # "or" | "and"
        self._rules: List[Callable[[object], bool]] = []
        self._id_whitelist: Optional[Set[int]] = None
        self._id_blacklist: Optional[Set[int]] = None

    # ── ID 规则 ──────────────────────────────────

    def add_id(self, can_id: int):
        """精确 ID 匹配"""
        self._rules.append(lambda msg: msg.arbitration_id == can_id)
        return self

    def add_id_list(self, can_ids: List[int]):
        """ID 列表匹配"""
        ids = set(can_ids)
        self._rules.append(lambda msg: msg.arbitration_id in ids)
        return self

    def add_id_range(self, min_id: int, max_id: int):
        """ID 范围匹配 [min_id, max_id]"""
        self._rules.append(
            lambda msg, lo=min_id, hi=max_id: lo <= msg.arbitration_id <= hi
        )
        return self

    def add_id_mask(self, can_id: int, mask: int):
        """ID 掩码匹配 (硬件风格)

        Example:
            f.add_id_mask(0x600, 0x7F0)
            # 匹配 0x600-0x60F (低 4 位任意, 高 8 位固定)
        """
        expected = can_id & mask
        self._rules.append(
            lambda msg, e=expected, m=mask: (msg.arbitration_id & m) == e
        )
        return self

    def add_id_above(self, threshold: int):
        """ID >= threshold"""
        self._rules.append(lambda msg, t=threshold: msg.arbitration_id >= t)
        return self

    def add_id_below(self, threshold: int):
        """ID <= threshold"""
        self._rules.append(lambda msg, t=threshold: msg.arbitration_id <= t)
        return self

    # ── 数据规则 ──────────────────────────────────

    def add_data_match(self, offset: int, value: int, mask: int = 0xFF):
        """数据字节匹配

        Args:
            offset: 字节偏移 (0-based)
            value: 期望值
            mask: 掩码 (默认完整匹配)
        """
        self._rules.append(
            lambda msg, o=offset, v=value, m=mask:
                len(msg.data) > o and (msg.data[o] & m) == (v & m)
        )
        return self

    def add_data_prefix(self, prefix: bytes):
        """数据前缀匹配 (message 以 prefix 开头)"""
        self._rules.append(
            lambda msg, p=prefix: bytes(msg.data[:len(p)]) == p
        )
        return self

    def add_data_length(self, min_len: int, max_len: Optional[int] = None):
        """数据长度过滤"""
        if max_len is None:
            max_len = min_len
        self._rules.append(
            lambda msg, lo=min_len, hi=max_len: lo <= len(msg.data) <= hi
        )
        return self

    def add_data_contains(self, pattern: bytes):
        """数据包含指定字节序列"""
        self._rules.append(
            lambda msg, p=pattern: p in bytes(msg.data)
        )
        return self

    # ── 扩展规则 ──────────────────────────────────

    def add_extended_only(self):
        """只匹配扩展帧"""
        self._rules.append(lambda msg: msg.is_extended_id)
        return self

    def add_standard_only(self):
        """只匹配标准帧"""
        self._rules.append(lambda msg: not msg.is_extended_id)
        return self

    def add_custom(self, func: Callable[[object], bool], name: str = ""):
        """添加自定义过滤函数"""
        self._rules.append(func)
        return self

    # ── 黑白名单 ──────────────────────────────────

    def set_whitelist(self, can_ids: List[int]):
        """设置白名单 (仅通过指定 ID)"""
        self._id_whitelist = set(can_ids)

    def set_blacklist(self, can_ids: List[int]):
        """设置黑名单 (排除指定 ID)"""
        self._id_blacklist = set(can_ids)

    # ── 匹配 ──────────────────────────────────────

    def match(self, msg) -> bool:
        """判断报文是否通过过滤

        Args:
            msg: can.Message 对象或任何有 arbitration_id/data 的对象
        """
        # 黑白名单优先
        if self._id_whitelist is not None:
            if msg.arbitration_id not in self._id_whitelist:
                return False

        if self._id_blacklist is not None:
            if msg.arbitration_id in self._id_blacklist:
                return False

        if not self._rules:
            return True

        if self.mode == "and":
            return all(rule(msg) for rule in self._rules)
        else:  # "or"
            return any(rule(msg) for rule in self._rules)

    def apply(self, messages: list) -> list:
        """对消息列表应用过滤, 返回匹配的消息"""
        return [msg for msg in messages if self.match(msg)]

    def clear(self):
        """清除所有规则"""
        self._rules.clear()
        self._id_whitelist = None
        self._id_blacklist = None

    def summary(self) -> str:
        """规则摘要"""
        return f"CANFilter(mode={self.mode}, rules={len(self._rules)}, "
        f"whitelist={len(self._id_whitelist) if self._id_whitelist else 0}, "
        f"blacklist={len(self._id_blacklist) if self._id_blacklist else 0})"


# ── 常用预设过滤器 ──────────────────────────────

def create_uds_filter(ecu_id: int = 0x7E8) -> CANFilter:
    """UDS 诊断报文过滤器 (0x7E0-0x7EF)"""
    f = CANFilter(mode="or")
    f.add_id_mask(0x7E0, 0x7F0)  # 功能寻址
    f.add_id(ecu_id)              # 物理寻址响应
    return f


def create_powertrain_filter() -> CANFilter:
    """动力域报文过滤器 (0x100-0x3FF)"""
    f = CANFilter()
    f.add_id_range(0x100, 0x3FF)
    return f


def create_body_filter() -> CANFilter:
    """车身/舒适域报文过滤器 (0x400-0x5FF)"""
    f = CANFilter()
    f.add_id_range(0x400, 0x5FF)
    return f


def create_first_frame_filter() -> CANFilter:
    """ISO-TP 首帧过滤器 (数据第1字节高4位=0x1)"""
    f = CANFilter()
    f.add_data_match(offset=0, value=0x10, mask=0xF0)
    return f


def create_error_frame_filter() -> CANFilter:
    """错误帧过滤器 (ID >= 0x800 的扩展帧近似错误帧)"""
    f = CANFilter()
    f.add_id_above(0x800)
    f.add_extended_only()
    return f
