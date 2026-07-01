"""
测试报告生成器 - 生成HTML/Text格式的测试报告
"""

import json
from datetime import datetime
from typing import Dict, List, Optional


class ReportGenerator:
    """测试报告生成器"""

    def __init__(self, results: Dict):
        self.results = results
        self.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def to_text(self) -> str:
        """生成纯文本报告"""
        lines = [
            "=" * 70,
            f"  车载自动化测试报告 - AUTO TEST REPORT",
            "=" * 70,
            f"  生成时间: {self.generated_at}",
            f"  测试运行器: {self.results.get('runner_name', 'N/A')}",
            "",
            f"  总计: {self.results['total_cases']} 用例",
            f"  通过: {self.results['total_passed']} (绿色)",
            f"  通过率: {self.results['pass_rate']}%",
            f"  总耗时: {self.results['duration_seconds']}s",
            "",
            "-" * 70,
        ]

        for suite in self.results.get("suites", []):
            lines.extend([
                f"",
                f"  [{suite['suite_name']}]",
                f"    用例数: {suite['total']}",
                f"    通过: {suite['passed']}  |  失败: {suite['failed']}  |  "
                f"错误: {suite['errors']}  |  跳过: {suite['skipped']}",
                f"    通过率: {suite['pass_rate']}%  |  耗时: {suite['duration_ms']:.0f}ms",
                "",
                f"  {'用例编号':<15} {'用例名称':<30} {'状态':<10} {'耗时(ms)'}",
                f"  {'-'*15} {'-'*30} {'-'*10} {'-'*10}",
            ])

            for case in suite.get("cases", []):
                status = case["status"]
                lines.append(
                    f"  {case['id']:<15} {case['name'][:28]:<30} "
                    f"{status:<10} {case['duration_ms']:.0f}"
                )

            lines.append("")

        # 失败用例汇总
        failed_cases = []
        for suite in self.results.get("suites", []):
            for case in suite.get("cases", []):
                if case["status"] in ("FAIL", "ERROR"):
                    failed_cases.append((suite["suite_name"], case))

        if failed_cases:
            lines.extend([
                "=" * 70,
                "  失败/错误用例汇总",
                "=" * 70,
            ])
            for suite_name, case in failed_cases:
                lines.extend([
                    f"  [{case['status']}] {suite_name} / {case['id']}: {case['name']}",
                ])
                if case.get("error"):
                    lines.append(f"    错误: {case['error']}")
                    lines.append("")

        lines.extend([
            "",
            "=" * 70,
            "  报告结束",
            "=" * 70,
        ])

        return '\n'.join(lines)

    def to_html(self, title: str = "车载自动化测试报告") -> str:
        """生成HTML报告"""
        total = self.results.get("total_cases", 0)
        passed = self.results.get("total_passed", 0)
        pass_rate = self.results.get("pass_rate", 0)
        duration = self.results.get("duration_seconds", 0)

        # 生成套件表格
        suite_rows = ""
        for suite in self.results.get("suites", []):
            for case in suite.get("cases", []):
                status_color = {
                    "PASS": "#52c41a", "FAIL": "#ff4d4f",
                    "ERROR": "#fa8c16", "SKIP": "#999999",
                    "PENDING": "#d9d9d9",
                }
                color = status_color.get(case["status"], "#000")
                suite_rows += f"""
                <tr>
                    <td>{case['id']}</td>
                    <td>{case['name']}</td>
                    <td>{suite['suite_name']}</td>
                    <td style="color:{color};font-weight:bold">{case['status']}</td>
                    <td>{case['duration_ms']:.0f}</td>
                </tr>"""

        html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: 'Microsoft YaHei', Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .header {{ background: linear-gradient(135deg, #1a1a2e, #16213e); color: white; padding: 30px; border-radius: 10px 10px 0 0; }}
        .header h1 {{ font-size: 24px; margin-bottom: 10px; }}
        .header p {{ opacity: 0.7; font-size: 14px; }}
        .summary {{ display: flex; gap: 20px; padding: 20px; background: white; flex-wrap: wrap; }}
        .stat-card {{ flex: 1; min-width: 120px; text-align: center; padding: 15px; border-radius: 8px; background: #fafafa; }}
        .stat-card .value {{ font-size: 28px; font-weight: bold; }}
        .stat-card .label {{ font-size: 12px; color: #666; margin-top: 5px; }}
        .stat-card.pass {{ border-left: 4px solid #52c41a; }}
        .stat-card.fail {{ border-left: 4px solid #ff4d4f; }}
        .stat-card.rate {{ border-left: 4px solid #1890ff; }}
        .table-container {{ background: white; padding: 20px; border-radius: 0 0 10px 10px; }}
        table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        th {{ background: #fafafa; padding: 12px 10px; text-align: left; border-bottom: 2px solid #e8e8e8; font-weight: 600; }}
        td {{ padding: 10px; border-bottom: 1px solid #f0f0f0; }}
        tr:hover {{ background: #fafafa; }}
        .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <p>生成时间: {self.generated_at}</p>
        </div>
        <div class="summary">
            <div class="stat-card">
                <div class="value">{total}</div>
                <div class="label">总用例数</div>
            </div>
            <div class="stat-card pass">
                <div class="value" style="color:#52c41a">{passed}</div>
                <div class="label">通过</div>
            </div>
            <div class="stat-card fail">
                <div class="value" style="color:#ff4d4f">{total - passed}</div>
                <div class="label">未通过</div>
            </div>
            <div class="stat-card rate">
                <div class="value" style="color:#1890ff">{pass_rate}%</div>
                <div class="label">通过率</div>
            </div>
            <div class="stat-card">
                <div class="value">{duration}s</div>
                <div class="label">总耗时</div>
            </div>
        </div>
        <div class="table-container">
            <table>
                <thead>
                    <tr>
                        <th>用例编号</th>
                        <th>用例名称</th>
                        <th>测试套件</th>
                        <th>状态</th>
                        <th>耗时(ms)</th>
                    </tr>
                </thead>
                <tbody>
                    {suite_rows}
                </tbody>
            </table>
        </div>
        <div class="footer">
            Generated by Auto Test CLI | {self.generated_at}
        </div>
    </div>
</body>
</html>"""
        return html

    def save_text(self, filepath: str):
        """保存为文本报告"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.to_text())
        print(f"Text report saved to: {filepath}")

    def save_html(self, filepath: str):
        """保存为HTML报告"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(self.to_html())
        print(f"HTML report saved to: {filepath}")

    def print_summary(self):
        """打印摘要到控制台"""
        print(self.to_text())
