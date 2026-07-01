"""
CAN信号可视化 - 对解析后的信号数据进行图表展示
"""

import csv
import json
from collections import defaultdict
from typing import Dict, List, Optional


class SignalVisualizer:
    """生成信号数据的可视化数据"""

    def __init__(self, decoded_data: List[Dict]):
        """
        Args:
            decoded_data: can_parser.decode_with_dbc() 的输出
        """
        self.data = decoded_data
        self._signal_series = defaultdict(list)

    def extract_time_series(self, signal_name: str) -> Dict:
        """提取指定信号的时间序列数据"""
        timestamps = []
        values = []
        for item in self.data:
            if signal_name in item["signals"]:
                timestamps.append(item["timestamp"])
                values.append(item["signals"][signal_name])
        return {
            "signal_name": signal_name,
            "timestamps": timestamps,
            "values": values,
        }

    def extract_all_series(self) -> Dict[str, Dict]:
        """提取所有信号的时间序列"""
        result = {}
        # 收集所有信号名称
        all_signals = set()
        for item in self.data:
            all_signals.update(item["signals"].keys())

        for sig_name in sorted(all_signals):
            result[sig_name] = self.extract_time_series(sig_name)

        return result

    def get_signal_stats(self, signal_name: str) -> Dict:
        """获取信号统计信息（最大/最小/平均/变化率）"""
        series = self.extract_time_series(signal_name)
        values = series["values"]
        if not values:
            return {"error": "No data"}

        timestamps = series["timestamps"]
        return {
            "signal_name": signal_name,
            "min": min(values),
            "max": max(values),
            "avg": round(sum(values) / len(values), 3),
            "sample_count": len(values),
            "duration_seconds": round(timestamps[-1] - timestamps[0], 3) if len(timestamps) > 1 else 0,
            "change_rate": self._calc_change_rate(timestamps, values),
        }

    @staticmethod
    def _calc_change_rate(timestamps: List[float],
                          values: List[float]) -> float:
        """计算信号平均变化率"""
        if len(values) < 2:
            return 0.0
        total_change = sum(abs(values[i+1] - values[i])
                          for i in range(len(values)-1))
        duration = timestamps[-1] - timestamps[0]
        return round(total_change / duration, 3) if duration > 0 else 0.0

    def export_json(self, filepath: str):
        """导出时间序列为JSON"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.extract_all_series(), f, indent=2, ensure_ascii=False)

    def export_csv(self, filepath: str, signal_names: Optional[List[str]] = None):
        """导出指定信号为CSV"""
        names = signal_names or list(self.extract_all_series().keys())
        series_data = {n: self.extract_time_series(n) for n in names}

        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            header = ["Timestamp"] + names
            writer.writerow(header)

            # 统一时间轴（取所有信号的时间戳并集）
            all_ts = set()
            for s in series_data.values():
                all_ts.update(s["timestamps"])
            all_ts = sorted(all_ts)

            for ts in all_ts:
                row = [ts]
                for name in names:
                    sd = series_data[name]
                    if ts in sd["timestamps"]:
                        idx = sd["timestamps"].index(ts)
                        row.append(sd["values"][idx])
                    else:
                        row.append("")
                writer.writerow(row)

    def generate_report(self) -> str:
        """生成文本报告"""
        lines = [
            "=" * 60,
            "CAN Signal Analysis Report",
            "=" * 60,
            f"Total decoded messages: {len(self.data)}",
        ]

        all_series = self.extract_all_series()
        lines.append(f"Unique signals found: {len(all_series)}")
        lines.append("")

        for sig_name in sorted(all_series.keys()):
            stats = self.get_signal_stats(sig_name)
            lines.append(f"  [{sig_name}]")
            lines.append(f"    Min: {stats.get('min', 'N/A'):>10}  "
                         f"Max: {stats.get('max', 'N/A'):>10}  "
                         f"Avg: {stats.get('avg', 'N/A'):>10}")
            lines.append(f"    Samples: {stats.get('sample_count', 0)}  "
                         f"Duration: {stats.get('duration_seconds', 0)}s  "
                         f"Change Rate: {stats.get('change_rate', 0)}/s")
            lines.append("")

        return '\n'.join(lines)


def plot_signals(decoded_data: List[Dict],
                 signal_names: List[str],
                 output_path: str = "signal_plot.png"):
    """
    使用matplotlib绘制信号曲线（需要 pip install matplotlib）
    """
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Run: pip install matplotlib")
        return

    viz = SignalVisualizer(decoded_data)
    fig, axes = plt.subplots(len(signal_names), 1, figsize=(12, 3*len(signal_names)),
                              sharex=True)
    if len(signal_names) == 1:
        axes = [axes]

    for ax, sig_name in zip(axes, signal_names):
        series = viz.extract_time_series(sig_name)
        ax.plot(series["timestamps"], series["values"], linewidth=0.8)
        ax.set_ylabel(sig_name)
        ax.set_title(f"Signal: {sig_name}")
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Time (s)")
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    plt.close()
    print(f"Plot saved to: {output_path}")
