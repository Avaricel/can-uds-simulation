"""
测试执行引擎 - 用例管理、自动化执行、结果收集
"""

import time
import json
import traceback
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime


class TestStatus(Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP = "SKIP"
    PENDING = "PENDING"
    RUNNING = "RUNNING"


class TestPriority(Enum):
    P0 = "P0"  # 最高优先级
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


@dataclass
class TestStep:
    """测试步骤"""
    name: str
    action: str = ""
    expected: str = ""  # 期望结果
    status: TestStatus = TestStatus.PENDING
    actual: str = ""     # 实际结果
    duration_ms: float = 0.0
    logs: List[str] = field(default_factory=list)


@dataclass
class TestCase:
    """测试用例定义"""
    id: str                              # 用例编号（如 TC_IC_001）
    name: str                            # 用例名称
    description: str = ""                # 用例描述
    category: str = ""                   # 分类（仪表、语音、蓝牙等）
    priority: TestPriority = TestPriority.P2
    preconditions: str = ""              # 前置条件
    test_function: Optional[Callable] = None  # 测试函数
    steps: List[TestStep] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    timeout: float = 30.0                # 超时时间（秒）

    # 执行结果
    status: TestStatus = TestStatus.PENDING
    start_time: float = 0.0
    end_time: float = 0.0
    error_message: str = ""

    @property
    def duration_ms(self) -> float:
        """执行耗时（毫秒）"""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time) * 1000
        return 0.0


@dataclass
class TestSuite:
    """测试套件"""
    name: str
    description: str = ""
    cases: List[TestCase] = field(default_factory=list)
    setup: Optional[Callable] = None
    teardown: Optional[Callable] = None
    tags: List[str] = field(default_factory=list)

    # 执行统计
    start_time: float = 0.0
    end_time: float = 0.0

    def add_case(self, case: TestCase):
        self.cases.append(case)

    def get_results(self) -> Dict:
        """获取测试结果统计"""
        total = len(self.cases)
        passed = sum(1 for c in self.cases if c.status == TestStatus.PASS)
        failed = sum(1 for c in self.cases if c.status == TestStatus.FAIL)
        errors = sum(1 for c in self.cases if c.status == TestStatus.ERROR)
        skipped = sum(1 for c in self.cases if c.status == TestStatus.SKIP)
        duration = (self.end_time - self.start_time) * 1000 if self.end_time else 0

        return {
            "suite_name": self.name,
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "skipped": skipped,
            "pass_rate": round(passed / total * 100, 1) if total > 0 else 0,
            "duration_ms": round(duration, 1),
            "cases": [
                {
                    "id": c.id,
                    "name": c.name,
                    "status": c.status.value,
                    "duration_ms": round(c.duration_ms, 1),
                    "error": c.error_message,
                }
                for c in self.cases
            ],
        }


class TestRunner:
    """测试运行器"""

    def __init__(self, name: str = "Auto Test Runner"):
        self.name = name
        self.suites: List[TestSuite] = []
        self._hooks_before_suite: List[Callable] = []
        self._hooks_after_suite: List[Callable] = []
        self._hooks_before_case: List[Callable] = []
        self._hooks_after_case: List[Callable] = []

    def add_suite(self, suite: TestSuite):
        self.suites.append(suite)

    def add_global_hook(self, hook_type: str, callback: Callable):
        """添加全局钩子"""
        hook_map = {
            "before_suite": self._hooks_before_suite,
            "after_suite": self._hooks_after_suite,
            "before_case": self._hooks_before_case,
            "after_case": self._hooks_after_case,
        }
        if hook_type in hook_map:
            hook_map[hook_type].append(callback)

    def run_all(self, filter_tags: Optional[List[str]] = None,
                filter_priority: Optional[List[TestPriority]] = None) -> Dict:
        """执行所有测试套件"""
        start_time = time.time()
        suite_results = []
        total_cases = 0
        total_passed = 0

        for suite in self.suites:
            # 标签过滤
            if filter_tags:
                suite_tags = set(suite.tags)
                if not suite_tags.intersection(filter_tags):
                    continue

            result = self._run_suite(suite, filter_tags, filter_priority)
            suite_results.append(result)
            total_cases += result["total"]
            total_passed += result["passed"]

        elapsed = time.time() - start_time

        return {
            "runner_name": self.name,
            "total_suites": len(suite_results),
            "total_cases": total_cases,
            "total_passed": total_passed,
            "pass_rate": round(total_passed / total_cases * 100, 1) if total_cases > 0 else 0,
            "duration_seconds": round(elapsed, 2),
            "suites": suite_results,
        }

    def _run_suite(self, suite: TestSuite,
                   filter_tags: Optional[List[str]] = None,
                   filter_priority: Optional[List[TestPriority]] = None) -> Dict:
        """执行单个测试套件"""
        print(f"\n{'='*60}")
        print(f"Test Suite: {suite.name}")
        print(f"{'='*60}")

        # Before suite hooks
        for hook in self._hooks_before_suite:
            hook(suite)

        # Setup
        if suite.setup:
            try:
                suite.setup()
            except Exception as e:
                print(f"  [ERROR] Suite setup failed: {e}")
                for case in suite.cases:
                    if case.status == TestStatus.PENDING:
                        case.status = TestStatus.ERROR
                        case.error_message = str(e)
                return suite.get_results()

        suite.start_time = time.time()

        # 执行用例
        for case in suite.cases:
            # 过滤
            if filter_priority and case.priority not in filter_priority:
                case.status = TestStatus.SKIP
                continue
            if filter_tags:
                case_tags = set(case.tags)
                if not case_tags.intersection(filter_tags):
                    case.status = TestStatus.SKIP
                    continue

            self._run_case(case)

        suite.end_time = time.time()

        # Teardown
        if suite.teardown:
            try:
                suite.teardown()
            except Exception as e:
                print(f"  [ERROR] Suite teardown failed: {e}")

        # After suite hooks
        for hook in self._hooks_after_suite:
            hook(suite)

        result = suite.get_results()
        print(f"\n  Results: {result['passed']}/{result['total']} "
              f"passed ({result['pass_rate']}%)")
        return result

    def _run_case(self, case: TestCase):
        """执行单个测试用例"""
        case.status = TestStatus.RUNNING
        case.start_time = time.time()

        print(f"\n  [{case.status.value}] {case.id}: {case.name}")

        # Before case hooks
        for hook in self._hooks_before_case:
            hook(case)

        try:
            if case.test_function:
                # 执行测试函数
                import platform
                if platform.system() == "Windows":
                    case.test_function(case)
                else:
                    # Unix/Mac: 支持超时信号
                    import signal
                    def timeout_handler(signum, frame):
                        raise TimeoutError(f"Test timed out after {case.timeout}s")
                    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                    try:
                        signal.alarm(int(case.timeout))
                        case.test_function(case)
                    finally:
                        signal.alarm(0)
                        signal.signal(signal.SIGALRM, old_handler)
            else:
                # 无测试函数，检查步骤
                for step in case.steps:
                    step.status = TestStatus.PASS

            case.status = TestStatus.PASS

        except TimeoutError as e:
            case.status = TestStatus.ERROR
            case.error_message = f"Timeout: {e}"
            print(f"    [ERROR] {case.error_message}")

        except AssertionError as e:
            case.status = TestStatus.FAIL
            case.error_message = str(e)
            print(f"    [FAIL] {case.error_message}")

        except Exception as e:
            case.status = TestStatus.ERROR
            case.error_message = f"{type(e).__name__}: {e}"
            print(f"    [ERROR] {case.error_message}")
            traceback.print_exc()

        case.end_time = time.time()
        print(f"    [{case.status.value}] Duration: {case.duration_ms:.0f}ms")

        # After case hooks
        for hook in self._hooks_after_case:
            hook(case)

    def export_results_json(self, filepath: str, results: Dict):
        """导出结果为JSON"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"Results exported to: {filepath}")
