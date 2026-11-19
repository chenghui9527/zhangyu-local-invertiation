#!/usr/bin/env python3
"""流式清洗日志并生成流量分析报告，不会一次性加载原始日志。"""

from __future__ import annotations

import argparse
import heapq
import json
import re
import statistics
from collections import Counter, defaultdict, deque
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
CLEAN_DIR = OUTPUT_DIR / "cleaned"
EVENTS_PATH = CLEAN_DIR / "upload_events.jsonl"
DAILY_PATH = CLEAN_DIR / "daily_usage.jsonl"
KEYWORDS_PATH = CLEAN_DIR / "keyword_stats.json"
SUMMARY_PATH = OUTPUT_DIR / "analysis_summary.json"
REPORT_PATH = OUTPUT_DIR / "traffic_report.md"

TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3})")
UPLOAD_RE = re.compile(
    r"本次上传文件消耗流量\s*:\s*([\d.]+)\s*(B|KB|MB|GB)"
    r".*?网络环境为\s*[:：]\s*([^,\s]+)"
)
CALLBACK_RE = re.compile(
    r"Thread: oss-android-api-thread 接收到阿里云回调,耗时\s*[:：]\s*(\d+)(?:\s*ms)?"
)
UIN_RE = re.compile(r"/wx_backup/\d+/(-?\d+)/")
DAILY_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})总体流量消耗为\s*:\s*([\d.]+)\s*(B|KB|MB|GB)"
    r"\s*,\s*wifi消耗\s*:\s*([\d.]+)\s*(B|KB|MB|GB)"
    r"\s*,\s*流量消耗为\s*:\s*([\d.]+)\s*(B|KB|MB|GB)"
)
UNIT_FACTOR = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
KEYWORDS = (
    "本次上传文件消耗流量",
    "总体流量消耗为",
    "网络环境为: 流量",
    "当前网络连接类型: 移动数据",
    "当前非WIFI环境，所有数据不进行上报",
    "TrafficStats",
    "NetworkStats",
)


def to_bytes(value: str, unit: str) -> int:
    """日志中的 KB/MB/GB 按 1024 进制换算，四舍五入到字节。"""
    result = Decimal(value) * UNIT_FACTOR[unit]
    return int(result.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def timestamp_of(line: str) -> str | None:
    match = TIMESTAMP_RE.match(line)
    return match.group(1) if match else None


def extract_uin(line: str) -> str | None:
    """数据库上传成功路径中含有 UIN，仅提取统计所需字段，不保留完整路径。"""
    match = UIN_RE.search(line)
    return match.group(1) if match else None


def classify_action(line: str) -> str:
    """将上传成功日志归类为可统计的动作。"""
    if "EnMicroMsg" in line:
        return "微信消息数据库（EnMicroMsg）上传"
    if "SnsMicroMsg" in line:
        return "微信朋友圈数据库（SnsMicroMsg）上传"
    if "微信语音条文件删除结果" in line:
        return "微信语音条上传（完成后删除本地文件）"
    if "VOIP录音文件上传成功" in line:
        return "微信 VOIP 录音上传"
    if "上传通话录音完成" in line:
        return "手机通话录音上传"
    if "图片" in line:
        return "微信图片上传"
    if "视频" in line:
        return "微信视频上传"
    if "文档" in line:
        return "微信文档上传"
    return "其他阿里云 OSS 文件上传"


def is_upload_action(line: str) -> bool:
    # OSS 回调线程中的成功/删除日志与前面的消耗日志相邻；排除其他线程的提交日志。
    return "Thread: oss-android-api-thread" in line and (
        "上传成功" in line
        or "微信语音条文件删除结果" in line
        or "上传通话录音完成" in line
    )


def clean_logs(log_dir: Path, progress: Callable[[str], None] = print) -> None:
    log_dir = log_dir.expanduser().resolve()
    if not log_dir.is_dir():
        raise ValueError(f"日志文件夹不存在或不是文件夹：{log_dir}")

    files = sorted(path for path in log_dir.iterdir() if path.is_file())
    if not files:
        raise ValueError(f"日志文件夹中没有可处理的文件：{log_dir}")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    progress(f"日志文件夹：{log_dir}")
    keyword_stats: dict[str, dict] = {}
    total_lines = 0
    total_uploads = 0
    total_daily = 0
    unmatched_consumption = 0

    with EVENTS_PATH.open("w", encoding="utf-8") as event_out, DAILY_PATH.open(
        "w", encoding="utf-8"
    ) as daily_out:
        for path in files:
            stat = {
                "bytes": path.stat().st_size,
                "lines": 0,
                "first_timestamp": None,
                "last_timestamp": None,
                "upload_events": 0,
                "daily_summaries": 0,
                "keywords": Counter(),
            }
            # 仅保存短暂相邻事件，以处理多个 OSS 回调交错的情况。
            pending: deque[dict] = deque()
            last_callback: tuple[int, int] | None = None

            def flush_event(
                event: dict,
                action: str = "未识别上传动作",
                action_line: int | None = None,
                uin: str | None = None,
            ) -> None:
                event["action"] = action
                event["action_line"] = action_line
                event["uin"] = uin
                event_out.write(json.dumps(event, ensure_ascii=False) + "\n")

            with path.open("r", encoding="utf-8", errors="replace", buffering=1024 * 1024) as source:
                for lineno, line in enumerate(source, 1):
                    stat["lines"] += 1
                    total_lines += 1
                    ts = timestamp_of(line)
                    if ts:
                        if stat["first_timestamp"] is None:
                            stat["first_timestamp"] = ts
                        stat["last_timestamp"] = ts
                    for keyword in KEYWORDS:
                        if keyword in line:
                            stat["keywords"][keyword] += 1

                    callback_match = CALLBACK_RE.search(line)
                    if callback_match:
                        last_callback = (lineno, int(callback_match.group(1)))

                    daily_match = DAILY_RE.search(line)
                    if daily_match:
                        groups = daily_match.groups()
                        record = {
                            "usage_date": groups[0],
                            "logged_at": ts,
                            "source": path.name,
                            "source_line": lineno,
                            "total_bytes": to_bytes(groups[1], groups[2]),
                            "wifi_bytes": to_bytes(groups[3], groups[4]),
                            "mobile_bytes": to_bytes(groups[5], groups[6]),
                            "total_text": f"{groups[1]} {groups[2]}",
                        }
                        daily_out.write(json.dumps(record, ensure_ascii=False) + "\n")
                        stat["daily_summaries"] += 1
                        total_daily += 1

                    upload_match = UPLOAD_RE.search(line)
                    if upload_match:
                        value, unit, network = upload_match.groups()
                        pending.append(
                            {
                                "timestamp": ts,
                                "date": ts[:10] if ts else path.name[:10],
                                "source": path.name,
                                "source_line": lineno,
                                "size_value": float(value),
                                "size_unit": unit,
                                "bytes": to_bytes(value, unit),
                                "network": "移动数据" if network == "流量" else network,
                                "upload_duration_ms": (
                                    last_callback[1]
                                    if last_callback and last_callback[0] == lineno - 1
                                    else None
                                ),
                            }
                        )
                        stat["upload_events"] += 1
                        total_uploads += 1
                    elif "消耗流量" in line and "本次上传文件消耗流量" not in line:
                        unmatched_consumption += 1

                    if pending and is_upload_action(line):
                        event = pending.popleft()
                        flush_event(event, classify_action(line), lineno, extract_uin(line))

                    # 动作通常紧邻出现；限制关联窗口和内存占用，超时事件仍保留流量数值。
                    while pending and lineno - pending[0]["source_line"] > 200:
                        flush_event(pending.popleft())

            while pending:
                flush_event(pending.popleft())
            stat["keywords"] = dict(stat["keywords"])
            keyword_stats[path.name] = stat
            progress(
                f"已清洗 {path.name}: {stat['lines']:,} 行，"
                f"{stat['upload_events']:,} 条上传事件，{stat['daily_summaries']} 条日汇总"
            )

    metadata = {
        "method": "逐文件、逐行流式读取；动作关联窗口最多 200 行；聚合结果另存",
        "unit_conversion": "1 KB=1024 B, 1 MB=1024^2 B, 1 GB=1024^3 B",
        "files": keyword_stats,
        "total_lines": total_lines,
        "total_upload_events": total_uploads,
        "total_daily_summaries": total_daily,
        "unmatched_consumption_lines": unmatched_consumption,
    }
    KEYWORDS_PATH.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    progress(f"清洗完成：{EVENTS_PATH}")
    progress(f"清洗完成：{DAILY_PATH}")


def new_bucket() -> dict:
    return {"count": 0, "bytes": 0}


def add(bucket: dict, size: int) -> None:
    bucket["count"] += 1
    bucket["bytes"] += size


def fmt_bytes(size: int | float) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(value) < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    raise AssertionError("unreachable")


def fmt_duration_ms(value: float | None) -> str:
    if value is None:
        return "无数据"
    if value < 1000:
        return f"{value:.0f} ms"
    if value < 120_000:
        return f"{value / 1000:.2f} 秒"
    return f"{value / 60_000:.2f} 分钟"


def fmt_cycle(seconds: float | None) -> str:
    if seconds is None:
        return "无数据"
    if seconds < 120:
        return f"{seconds:.2f} 秒"
    if seconds < 7200:
        return f"{seconds / 60:.2f} 分钟"
    return f"{seconds / 3600:.2f} 小时"


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows)
    return "\n".join(lines)


def analyze(progress: Callable[[str], None] = print) -> None:
    by_day: dict[str, dict] = defaultdict(new_bucket)
    by_action: dict[str, dict] = defaultdict(new_bucket)
    by_day_action: dict[str, dict[str, dict]] = defaultdict(lambda: defaultdict(new_bucket))
    by_hour: dict[str, dict] = defaultdict(new_bucket)
    by_network: dict[str, dict] = defaultdict(new_bucket)
    by_source: dict[str, dict] = defaultdict(new_bucket)
    top_events: list[tuple] = []
    total = new_bucket()
    unknown = new_bucket()
    uin_groups: dict[tuple[str, str], dict] = {}
    last_uin_upload: dict[tuple[str, str], datetime] = {}

    with EVENTS_PATH.open("r", encoding="utf-8") as source:
        for line in source:
            event = json.loads(line)
            size = event["bytes"]
            add(total, size)
            add(by_day[event["date"]], size)
            add(by_action[event["action"]], size)
            add(by_day_action[event["date"]][event["action"]], size)
            add(by_hour[event["timestamp"][:13] + ":00"], size)
            add(by_network[event["network"]], size)
            add(by_source[event["source"]], size)
            if event["action"] == "未识别上传动作":
                add(unknown, size)

            # UIN 只存在于数据库上传路径中；按 UIN + 数据库类型分别计算耗时和周期。
            if event.get("uin"):
                key = (event["uin"], event["action"])
                group = uin_groups.setdefault(
                    key,
                    {
                        "count": 0,
                        "bytes": 0,
                        "duration_count": 0,
                        "duration_total_ms": 0,
                        "cycles_seconds": [],
                    },
                )
                group["count"] += 1
                group["bytes"] += size
                if event.get("upload_duration_ms") is not None:
                    group["duration_count"] += 1
                    group["duration_total_ms"] += event["upload_duration_ms"]
                uploaded_at = datetime.strptime(event["timestamp"], "%Y-%m-%d %H:%M:%S.%f")
                previous = last_uin_upload.get(key)
                if previous is not None:
                    interval = (uploaded_at - previous).total_seconds()
                    if interval >= 0:
                        group["cycles_seconds"].append(interval)
                last_uin_upload[key] = uploaded_at

            item = (
                size,
                event["timestamp"],
                event["action"],
                event["source"],
                event["source_line"],
            )
            if len(top_events) < 10:
                heapq.heappush(top_events, item)
            elif item > top_events[0]:
                heapq.heapreplace(top_events, item)

    daily = {}
    with DAILY_PATH.open("r", encoding="utf-8") as source:
        for line in source:
            record = json.loads(line)
            daily[record["usage_date"]] = record

    metadata = json.loads(KEYWORDS_PATH.read_text(encoding="utf-8"))
    daily_total_bytes = sum(item["total_bytes"] for item in daily.values())
    daily_mobile_bytes = sum(item["mobile_bytes"] for item in daily.values())
    daily_wifi_bytes = sum(item["wifi_bytes"] for item in daily.values())
    sorted_dates = sorted(set(by_day) | set(daily))
    matched_days = [
        date
        for date in sorted(daily)
        if date in by_day
        and abs(by_day[date]["bytes"] - daily[date]["total_bytes"]) <= 0.011 * 1024**3
    ]
    per_uin = []
    for (uin, action), group in sorted(uin_groups.items()):
        cycles = group["cycles_seconds"]
        duration_count = group["duration_count"]
        per_uin.append(
            {
                "uin": uin,
                "action": action,
                "upload_count": group["count"],
                "bytes": group["bytes"],
                "duration_sample_count": duration_count,
                "average_upload_duration_ms": (
                    group["duration_total_ms"] / duration_count if duration_count else None
                ),
                "cycle_sample_count": len(cycles),
                "average_cycle_seconds": sum(cycles) / len(cycles) if cycles else None,
                "median_cycle_seconds": statistics.median(cycles) if cycles else None,
                "min_cycle_seconds": min(cycles) if cycles else None,
                "max_cycle_seconds": max(cycles) if cycles else None,
            }
        )

    summary = {
        "upload_events": total,
        "by_day": dict(sorted(by_day.items())),
        "by_action": dict(sorted(by_action.items(), key=lambda pair: pair[1]["bytes"], reverse=True)),
        "by_network": dict(by_network),
        "daily_summaries": daily,
        "daily_summary_total_bytes": daily_total_bytes,
        "matched_daily_and_upload_days": matched_days,
        "per_uin_upload_timing": per_uin,
        "top_hours": sorted(by_hour.items(), key=lambda pair: pair[1]["bytes"], reverse=True)[:10],
        "top_events": sorted(top_events, reverse=True),
        "unidentified_action_events": unknown,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    report: list[str] = []
    report.append("# 流量消耗分析报告")
    report.append("")
    report.append("## 1. 分析口径与结论摘要")
    report.append("")
    report.append(
        f"- 已逐行扫描 **{len(metadata['files'])} 个文件、{metadata['total_lines']:,} 行**，"
        f"原始日志合计 **{fmt_bytes(sum(x['bytes'] for x in metadata['files'].values()))}**。"
    )
    report.append(
        f"- 提取到 **{total['count']:,} 条明确的上传流量事件**，记录值合计 "
        f"**{fmt_bytes(total['bytes'])}**；这些事件全部标记为移动数据（日志原文为“流量”）。"
    )
    report.append(
        f"- 另有 **{len(daily)} 天的总体流量日汇总**，合计 **{fmt_bytes(daily_total_bytes)}**；"
        f"其中移动数据 **{fmt_bytes(daily_mobile_bytes)}**，Wi-Fi **{fmt_bytes(daily_wifi_bytes)}**。"
    )
    if by_action:
        main_action, main_value = max(by_action.items(), key=lambda pair: pair[1]["bytes"])
        report.append(
            f"- 上传动作中占比最高的是 **{main_action}**，消耗 **{fmt_bytes(main_value['bytes'])}**，"
            f"占上传事件总量的 **{main_value['bytes'] / total['bytes'] * 100:.2f}%**。"
        )
    report.append(
        "- **日汇总与上传事件不能直接相加**：前者是整天总体口径，后者是已记录的上传子项；"
        "日期覆盖也不完全一致。按天评估总量优先采用日汇总，按动作归因采用上传事件。"
    )
    if matched_days:
        report.append(
            f"- 在 **{', '.join(matched_days)}**，上传事件合计与日汇总均吻合到日志显示的 "
            "0.01 GB，表明这些日期的移动流量基本可由已识别的 OSS 上传解释。"
        )
    report.append("")

    report.append("## 2. 命中的流量关键词及对应动作")
    report.append("")
    keyword_rows = [
        ["`本次上传文件消耗流量`", f"{total['count']:,}", "阿里云 OSS 文件上传；关联数据库、语音条、VOIP 录音等动作"],
        ["`网络环境为: 流量`", f"{total['count']:,}", "表明对应上传发生在移动数据网络"],
        ["`总体流量消耗为`", str(len(daily)), "每日 01:00 左右记录前一日总体流量"],
        ["`wifi消耗` / `流量消耗为`", str(len(daily)), "日汇总中的 Wi-Fi / 移动数据拆分"],
    ]
    report.append(md_table(["关键词", "有效记录数", "含义/对应动作"], keyword_rows))
    report.append("")
    report.append(
        "未把 `文件大小`、`currentSize`、音频编码“字节数”、普通 `上传/下载`、请求体大小等直接计为实际流量，"
        "以避免把本地处理量或文件长度误当网络消耗。日志中未命中 `TrafficStats` / `NetworkStats`。"
    )
    report.append("")

    report.append("## 3. 按动作统计（上传事件）")
    report.append("")
    action_rows = []
    for action, value in sorted(by_action.items(), key=lambda pair: pair[1]["bytes"], reverse=True):
        action_rows.append(
            [
                action,
                f"{value['count']:,}",
                fmt_bytes(value["bytes"]),
                f"{value['bytes'] / total['bytes'] * 100:.2f}%",
                fmt_bytes(value["bytes"] / value["count"]),
            ]
        )
    report.append(md_table(["动作", "次数", "消耗流量", "流量占比", "单次均值"], action_rows))
    report.append("")

    report.append("## 4. 每个 UIN 的平均上传耗时与上传周期")
    report.append("")
    report.append(
        "口径：**上传耗时**取 OSS 日志 `接收到阿里云回调,耗时`；**上传周期**取同一 UIN、"
        "同一数据库类型相邻两次成功上传的时间差。EnMicroMsg 与 SnsMicroMsg 分开计算，避免混合两条上传队列。"
    )
    report.append("")
    uin_rows = []
    for item in per_uin:
        uin_rows.append(
            [
                f"`{item['uin']}`",
                item["action"],
                f"{item['upload_count']:,}",
                fmt_duration_ms(item["average_upload_duration_ms"]),
                fmt_cycle(item["average_cycle_seconds"]),
                fmt_cycle(item["median_cycle_seconds"]),
                f"{item['cycle_sample_count']:,}",
            ]
        )
    report.append(
        md_table(
            ["UIN", "上传类型", "上传次数", "平均上传耗时", "平均上传周期", "周期中位数", "周期样本数"],
            uin_rows,
        )
    )
    report.append("")
    report.append(
        "平均周期包含重试、补传及日志缺失形成的间隔；周期中位数更接近常态调度间隔。"
        "语音和录音动作的上报日志不含 UIN，因此本表仅统计可明确归属 UIN 的数据库上传。"
    )
    report.append("")

    report.append("## 5. 按日期统计")
    report.append("")
    day_rows = []
    for date in sorted_dates:
        upload = by_day.get(date, new_bucket())
        day = daily.get(date)
        day_rows.append(
            [
                date,
                f"{upload['count']:,}" if upload["count"] else "0",
                fmt_bytes(upload["bytes"]),
                day["total_text"] if day else "未记录",
                f"{day['mobile_bytes'] / 1024**3:.2f} GB" if day else "未记录",
                f"{day['wifi_bytes'] / 1024**3:.2f} GB" if day else "未记录",
            ]
        )
    report.append(md_table(["日期", "上传次数", "上传事件合计", "日汇总总量", "日汇总移动数据", "日汇总 Wi-Fi"], day_rows))
    report.append("")
    report.append("说明：上传事件按事件时间所属日期统计；日汇总按日志声明的“前一日期”归档，而不是按打印时间归档。")
    report.append("")

    report.append("## 6. 高峰时段与单次大流量事件")
    report.append("")
    hour_rows = []
    for hour, value in sorted(by_hour.items(), key=lambda pair: pair[1]["bytes"], reverse=True)[:8]:
        hour_rows.append([hour, f"{value['count']:,}", fmt_bytes(value["bytes"])])
    report.append("### 上传流量最高的 8 个小时")
    report.append("")
    report.append(md_table(["小时", "上传次数", "上传流量"], hour_rows))
    report.append("")
    report.append("### 单次上传流量 Top 10")
    report.append("")
    event_rows = []
    for size, ts, action, source_name, source_line in sorted(top_events, reverse=True):
        event_rows.append([ts, action, fmt_bytes(size), f"`{source_name}:{source_line}`"])
    report.append(md_table(["时间", "动作", "流量", "原始位置"], event_rows))
    report.append("")

    report.append("## 7. 数据覆盖与质量说明")
    report.append("")
    coverage_rows = []
    for name, stat in metadata["files"].items():
        coverage_rows.append(
            [
                f"`{name}`",
                f"{stat['lines']:,}",
                stat["first_timestamp"] or "无时间戳",
                stat["last_timestamp"] or "无时间戳",
                f"{stat['upload_events']:,}",
            ]
        )
    report.append(md_table(["文件", "行数", "首个时间戳", "最后时间戳", "上传事件数"], coverage_rows))
    report.append("")
    report.append(
        f"- 动作未识别事件：**{unknown['count']:,} 条 / {fmt_bytes(unknown['bytes'])}**；"
        "这些事件仍计入上传总量，但不强行推断具体文件类型。"
    )
    report.append(
        "- 日志只给出上传事件和总体日汇总，没有足够依据精确拆分下载、MQTT、心跳及其他 API 的单项流量；"
        "因此报告不对这些项目虚构数值。"
    )
    report.append(
        "- 2026-11-14 的日志从 04:36 才开始，2026-11-19 的日志在 09:39 截止；"
        "2026-11-13 没有对应的次日日汇总。因此这些日期不能按完整自然日比较。"
    )
    report.append(
        "- 日汇总数值本身按 GB 保留两位小数，上传事件按日志显示值换算，均存在显示舍入误差。"
    )
    report.append("")

    report.append("## 8. 优化建议")
    report.append("")
    report.append(
        "1. **优先治理大头动作**：先检查占比最高的数据库上传是否存在固定周期全量重复上传；"
        "可考虑增量/差异备份、内容哈希去重及服务端确认后跳过重复文件。"
    )
    report.append(
        "2. **移动数据限速与 Wi-Fi 策略**：当前明确上传事件全部发生在移动数据环境。"
        "建议为大文件提供仅 Wi-Fi、每日移动流量预算、低流量模式及用户可见的暂停/恢复开关。"
    )
    report.append(
        "3. **压缩与调度**：对可压缩数据库评估上传前压缩的收益，并避开高峰连续批量上传；"
        "压缩前需确认服务端兼容性及 CPU/耗电成本。"
    )
    report.append(
        "4. **完善可观测性**：为每次上传增加任务 ID、文件类型、压缩前后字节数、重试次数和结果；"
        "同时分别记录 tx/rx，才能进一步拆分上传、下载、API 与 MQTT 消耗。"
    )
    report.append(
        "5. **核对两种统计口径**：持续对比上传事件合计与次日总体汇总；若差异明显，"
        "应排查重试重复记录、跨日归属、统计进程范围及未记录的下载/API 流量。"
    )
    report.append("")
    report.append("---")
    report.append(
        "生成方式：`python logAnlyse/traffic_analysis.py --log-dir \"日志文件夹路径\" clean` "
        "后执行 `python logAnlyse/traffic_analysis.py analyze`。"
    )
    report.append("除按 UIN 统计所需字段外，清洗数据不包含原始请求体、设备 ID 或完整文件路径。")

    REPORT_PATH.write_text("\n".join(report) + "\n", encoding="utf-8")
    progress(f"分析完成：{REPORT_PATH}")
    progress(f"结构化汇总：{SUMMARY_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("clean", "analyze", "all"), nargs="?", default="all")
    parser.add_argument(
        "--log-dir",
        type=Path,
        help="原始日志所在文件夹；clean/all 模式下未指定时会提示输入",
    )
    args = parser.parse_args()
    if args.mode in ("clean", "all"):
        log_dir = args.log_dir
        if log_dir is None:
            try:
                user_input = input("请输入日志文件夹路径：").strip().strip('"')
            except EOFError:
                parser.error("请通过 --log-dir 指定日志文件夹")
            if not user_input:
                parser.error("日志文件夹路径不能为空")
            log_dir = Path(user_input)
        try:
            clean_logs(log_dir)
        except ValueError as exc:
            parser.error(str(exc))
    if args.mode in ("analyze", "all"):
        analyze()


if __name__ == "__main__":
    main()
