#!/usr/bin/env python3
"""
CAN Message Analyzer CLI - 车载CAN总线报文分析命令行工具

用法:
    # 解析DBC文件
    python cli.py dbc parse cluster.dbc

    # 解析CAN日志
    python cli.py log parse candump.log --dbc cluster.dbc

    # 分析CAN日志并输出统计
    python cli.py log stats candump.log --dbc cluster.dbc

    # 提取指定信号时间序列
    python cli.py signal extract candump.log --dbc cluster.dbc -s EngineSpeed VehicleSpeed

    # 生成信号图表
    python cli.py signal plot candump.log --dbc cluster.dbc -s EngineSpeed VehicleSpeed -o plot.png

    # 导出CSV
    python cli.py log export candump.log -o output.csv
"""

import argparse
import sys
from pathlib import Path

from can_analyzer.dbc_parser import DBCParser
from can_analyzer.can_parser import CANLogParser
from can_analyzer.visualizer import SignalVisualizer, plot_signals


def cmd_dbc_parse(args):
    """解析DBC文件"""
    parser = DBCParser()
    parser.parse(args.file)
    print(parser.summary())


def cmd_log_parse(args):
    """解析CAN日志"""
    dbc = None
    if args.dbc:
        dbc = DBCParser()
        dbc.parse(args.dbc)

    log_parser = CANLogParser(dbc)
    log_parser.load_file(args.file, fmt=args.format)

    if dbc:
        decoded = log_parser.decode_with_dbc()
        print(f"Total frames: {len(log_parser.frames)}")
        print(f"Decoded messages: {len(decoded)}")
        print(f"Decode ratio: {len(decoded)/len(log_parser.frames)*100:.1f}%")
        print()

        # 按Message分组显示
        from collections import defaultdict
        grouped = defaultdict(list)
        for d in decoded:
            grouped[d["message_name"]].append(d)

        for msg_name, items in sorted(grouped.items()):
            print(f"  [{msg_name}] ({len(items)} frames)")
            if items:
                print(f"    Signals: {', '.join(items[0]['signals'].keys())}")
                # 显示最后一条的数据
                last = items[-1]
                for sname, sval in last["signals"].items():
                    print(f"      {sname} = {sval}")
            print()
    else:
        print(f"Total frames: {len(log_parser.frames)}")
        print(f"Unique CAN IDs: {len(log_parser.get_statistics().get('can_id_breakdown', {}))}")
        print()
        stats = log_parser.get_statistics()
        for id_hex, info in stats.get("can_id_breakdown", {}).items():
            print(f"  {id_hex}: {info['count']} frames "
                  f"({info['percentage']}%, "
                  f"~{info['frequency_hz']:.1f} Hz)")


def cmd_log_stats(args):
    """分析CAN日志统计"""
    dbc = None
    if args.dbc:
        dbc = DBCParser()
        dbc.parse(args.dbc)

    log_parser = CANLogParser(dbc)
    log_parser.load_file(args.file, fmt=args.format)

    stats = log_parser.get_statistics()
    print(f"=== CAN Log Statistics ===")
    print(f"File: {args.file}")
    print(f"Total frames: {stats['total_frames']}")
    print(f"Duration: {stats['duration_seconds']}s")
    print(f"Unique CAN IDs: {stats['unique_can_ids']}")
    print(f"Average rate: {stats['avg_frames_per_second']} fps")
    print()
    print(f"{'CAN ID':>8} | {'Message Name':<25} | {'Count':>8} | {'Freq(Hz)':>8} | {'AvgInterval(ms)':>12}")
    print("-" * 80)

    for id_hex, info in sorted(stats.get("can_id_breakdown", {}).items(),
                                 key=lambda x: x[1]["count"], reverse=True):
        msg_name = info.get("message_name", "")[:25]
        print(f"{id_hex:>8} | {msg_name:<25} | {info['count']:>8} | "
              f"{info['frequency_hz']:>8.1f} | {info['avg_interval_ms']:>12.1f}")


def cmd_signal_extract(args):
    """提取指定信号"""
    dbc = DBCParser()
    dbc.parse(args.dbc)
    log_parser = CANLogParser(dbc)
    log_parser.load_file(args.file)

    decoded = log_parser.decode_with_dbc()
    viz = SignalVisualizer(decoded)

    for sig_name in args.signals:
        series = viz.extract_time_series(sig_name)
        if series["values"]:
            stats = viz.get_signal_stats(sig_name)
            print(f"\n[{sig_name}]")
            print(f"  Samples: {stats['sample_count']}")
            print(f"  Min: {stats['min']:.3f}  Max: {stats['max']:.3f}  "
                  f"Avg: {stats['avg']:.3f}")
            print(f"  Duration: {stats['duration_seconds']:.3f}s")
            if args.verbose:
                print(f"  Time series:")
                for ts, val in zip(series["timestamps"][:20], series["values"][:20]):
                    print(f"    {ts:.6f}: {val:.3f}")
                if len(series["timestamps"]) > 20:
                    print(f"    ... ({len(series['timestamps']) - 20} more)")
        else:
            print(f"[{sig_name}] No data found")


def cmd_signal_plot(args):
    """绘制信号曲线"""
    dbc = DBCParser()
    dbc.parse(args.dbc)
    log_parser = CANLogParser(dbc)
    log_parser.load_file(args.file)

    decoded = log_parser.decode_with_dbc()
    plot_signals(decoded, args.signals, args.output)


def cmd_log_export(args):
    """导出为CSV"""
    log_parser = CANLogParser()
    log_parser.load_file(args.file)
    log_parser.export_csv(args.output)
    print(f"Exported {len(log_parser.frames)} frames to {args.output}")


def main():
    parser = argparse.ArgumentParser(
        description="CAN Message Analyzer - 车载CAN总线报文分析工具"
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # dbc 子命令
    dbc_parser = subparsers.add_parser("dbc", help="DBC文件操作")
    dbc_sub = dbc_parser.add_subparsers(dest="dbc_cmd")
    dbc_parse = dbc_sub.add_parser("parse", help="解析DBC文件")
    dbc_parse.add_argument("file", help="DBC文件路径")

    # log 子命令
    log_parser = subparsers.add_parser("log", help="CAN日志操作")
    log_sub = log_parser.add_subparsers(dest="log_cmd")

    log_parse = log_sub.add_parser("parse", help="解析CAN日志")
    log_parse.add_argument("file", help="CAN日志文件路径")
    log_parse.add_argument("--dbc", help="DBC文件路径（用于信号解码）")
    log_parse.add_argument("--format", default="auto",
                           choices=["auto", "canoe_asc", "candump", "csv"],
                           help="日志格式（默认自动检测）")

    log_stats = log_sub.add_parser("stats", help="分析日志统计")
    log_stats.add_argument("file", help="CAN日志文件路径")
    log_stats.add_argument("--dbc", help="DBC文件路径")

    log_export = log_sub.add_parser("export", help="导出为CSV")
    log_export.add_argument("file", help="CAN日志文件路径")
    log_export.add_argument("-o", "--output", default="output.csv",
                            help="输出文件路径")

    # signal 子命令
    sig_parser = subparsers.add_parser("signal", help="信号分析")
    sig_sub = sig_parser.add_subparsers(dest="sig_cmd")

    sig_extract = sig_sub.add_parser("extract", help="提取信号时间序列")
    sig_extract.add_argument("file", help="CAN日志文件路径")
    sig_extract.add_argument("--dbc", required=True, help="DBC文件路径")
    sig_extract.add_argument("-s", "--signals", nargs="+", required=True,
                             help="信号名称（多个用空格分隔）")
    sig_extract.add_argument("--verbose", "-v", action="store_true",
                             help="显示详细时间序列")

    sig_plot = sig_sub.add_parser("plot", help="绘制信号曲线")
    sig_plot.add_argument("file", help="CAN日志文件路径")
    sig_plot.add_argument("--dbc", required=True, help="DBC文件路径")
    sig_plot.add_argument("-s", "--signals", nargs="+", required=True,
                          help="信号名称（多个用空格分隔）")
    sig_plot.add_argument("-o", "--output", default="signal_plot.png",
                          help="输出图片路径")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # 路由命令
    command_map = {
        ("dbc", "parse"): cmd_dbc_parse,
        ("log", "parse"): cmd_log_parse,
        ("log", "stats"): cmd_log_stats,
        ("log", "export"): cmd_log_export,
        ("signal", "extract"): cmd_signal_extract,
        ("signal", "plot"): cmd_signal_plot,
    }

    sub_cmd = getattr(args, f"{args.command}_cmd", None)
    key = (args.command, sub_cmd)
    if key in command_map:
        command_map[key](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
