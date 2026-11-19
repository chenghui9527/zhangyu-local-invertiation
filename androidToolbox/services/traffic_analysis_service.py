"""本地流量分析业务服务：校验日志并直接调用分析函数。"""

from __future__ import annotations

import threading
import traceback
from pathlib import Path
from queue import Empty, Queue

from logAnlyse.traffic_analysis import REPORT_PATH, analyze, clean_logs


class TrafficAnalysisService:
    """在后台线程中执行流量分析，并通过队列提供实时执行信息。"""

    TEXT_SAMPLE_BYTES = 8192

    def __init__(self) -> None:
        self._events: Queue[tuple[str, str]] = Queue()
        self._worker: threading.Thread | None = None
        self._lock = threading.Lock()

    @classmethod
    def validate_log_dir(cls, dir_path: str | Path) -> Path:
        """校验目录只包含文本文件，返回可传给分析函数的日志目录。"""
        if not str(dir_path).strip():
            raise ValueError("请先选择日志文件夹")

        log_dir = Path(dir_path).expanduser().resolve()
        if not log_dir.is_dir():
            raise ValueError(f"所选日志文件夹不存在：{log_dir}")

        try:
            entries = sorted(log_dir.iterdir(), key=lambda path: path.name.casefold())
        except OSError as exc:
            raise ValueError(f"无法读取日志文件夹：{exc}") from exc

        invalid_entries = []
        file_count = 0
        for entry in entries:
            if not entry.is_file():
                invalid_entries.append(f"{entry.name}（文件夹或其他非文件项）")
                continue
            file_count += 1
            if not cls._is_text_file(entry):
                invalid_entries.append(f"{entry.name}（非文本文件）")

        if invalid_entries:
            shown = "、".join(invalid_entries[:5])
            if len(invalid_entries) > 5:
                shown += f" 等 {len(invalid_entries)} 项"
            raise ValueError(
                "日志文件夹只能包含文本文件，不能包含二进制文件或子文件夹。"
                f"\n发现：{shown}"
            )
        if file_count == 0:
            raise ValueError(f"日志文件夹中没有可处理的文本文件：{log_dir}")

        return log_dir

    @classmethod
    def _is_text_file(cls, file_path: Path) -> bool:
        """按文件内容判断文本，不依赖扩展名，并兼容 UTF-8、GBK 等编码。"""
        try:
            with file_path.open("rb") as source:
                sample = source.read(cls.TEXT_SAMPLE_BYTES)
        except OSError as exc:
            raise ValueError(f"无法读取文件 {file_path.name}：{exc}") from exc

        if not sample:
            return True
        if b"\x00" in sample:
            return False

        allowed_controls = {7, 8, 9, 10, 11, 12, 13, 27}
        binary_controls = sum(
            (byte < 32 and byte not in allowed_controls) or byte == 127
            for byte in sample
        )
        return binary_controls / len(sample) < 0.3

    def start(self, log_dir: str | Path) -> None:
        """在后台线程中依次调用 ``clean_logs`` 和 ``analyze``。"""
        resolved_log_dir = Path(log_dir).expanduser().resolve()
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                raise RuntimeError("流量分析正在执行，请勿重复启动")

            while not self._events.empty():
                try:
                    self._events.get_nowait()
                except Empty:
                    break

            self._worker = threading.Thread(
                target=self._run_analysis,
                args=(resolved_log_dir,),
                daemon=True,
                name="traffic-analysis",
            )
            self._worker.start()

    def _run_analysis(self, log_dir: Path) -> None:
        try:
            clean_logs(log_dir, progress=self._report_progress)
            analyze(progress=self._report_progress)
            if not REPORT_PATH.is_file():
                self._events.put(("error", f"分析已结束，但未找到报告：{REPORT_PATH}"))
            else:
                self._events.put(("success", str(REPORT_PATH)))
        except Exception as exc:
            self._events.put(("output", traceback.format_exc().rstrip()))
            self._events.put(("error", f"分析失败：{exc}"))
        finally:
            with self._lock:
                if self._worker is threading.current_thread():
                    self._worker = None

    def _report_progress(self, message: str) -> None:
        self._events.put(("output", message))

    def get_events(self) -> list[tuple[str, str]]:
        """取出当前所有待展示事件，仅供 UI 线程调用。"""
        events = []
        while True:
            try:
                events.append(self._events.get_nowait())
            except Empty:
                return events
