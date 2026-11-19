"""本地流量分析标签页。"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk

from androidToolbox.services.traffic_analysis_service import TrafficAnalysisService


class TrafficAnalysisTab(ttk.Frame):
    """选择日志目录、展示分析过程并打开生成的 Markdown 报告。"""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.pack(fill="both", expand=True, padx=5, pady=5)

        self.service = TrafficAnalysisService()
        self.selected_dir: Path | None = None
        self.report_path: Path | None = None
        self._running = False
        self.path_var = tk.StringVar(value="未选择日志文件夹")
        self.status_var = tk.StringVar(value="请选择只包含文本日志文件的文件夹")

        self._setup_ui()
        self.after(100, self._poll_events)

    def _setup_ui(self) -> None:
        dir_frame = ttk.LabelFrame(self, text="日志文件夹", padding=8)
        dir_frame.pack(fill="x", padx=5, pady=(5, 8))

        ttk.Label(
            dir_frame,
            text="选择整个日志文件夹，将分析其中全部文本文件（不限制扩展名，不允许二进制文件或子文件夹）",
        ).pack(anchor="w", pady=(0, 6))

        path_row = ttk.Frame(dir_frame)
        path_row.pack(fill="x")
        ttk.Entry(path_row, textvariable=self.path_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=(0, 6)
        )
        self.btn_choose = ttk.Button(path_row, text="选择日志文件夹", command=self.select_directory)
        self.btn_choose.pack(side="left", padx=(0, 6))
        self.btn_start = ttk.Button(path_row, text="开始分析", command=self.start_analysis)
        self.btn_start.pack(side="left", padx=(0, 6))
        self.btn_open = ttk.Button(
            path_row, text="打开报告", command=self.open_report, state="disabled"
        )
        self.btn_open.pack(side="left")

        status_row = ttk.Frame(self)
        status_row.pack(fill="x", padx=8, pady=(0, 5))
        self.status_label = ttk.Label(status_row, textvariable=self.status_var)
        self.status_label.pack(side="left", fill="x", expand=True)
        self.progress = ttk.Progressbar(status_row, mode="indeterminate", length=140)
        self.progress.pack(side="right", padx=(8, 0))

        process_frame = ttk.LabelFrame(self, text="执行过程", padding=5)
        process_frame.pack(fill="both", expand=True, padx=5, pady=(0, 5))
        self.output = scrolledtext.ScrolledText(
            process_frame,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
        )
        self.output.pack(fill="both", expand=True)

    def select_directory(self) -> None:
        if self._running:
            return

        dir_path = filedialog.askdirectory(parent=self, title="选择日志文件夹")
        if not dir_path:
            return

        try:
            log_dir = self.service.validate_log_dir(dir_path)
        except ValueError as exc:
            messagebox.showwarning("日志文件夹不符合要求", str(exc), parent=self)
            return

        self.selected_dir = log_dir
        self.report_path = None
        self.path_var.set(str(self.selected_dir))
        self.status_var.set("日志校验通过，点击“开始分析”")
        self.status_label.config(foreground="black")
        self.btn_open.config(state="disabled")

    def start_analysis(self) -> None:
        if self._running:
            return
        if self.selected_dir is None:
            messagebox.showwarning("未选择日志", "请先选择日志文件夹", parent=self)
            return

        try:
            # 点击开始时重新校验，避免选择后目录内容发生变化。
            log_dir = self.service.validate_log_dir(self.selected_dir)
        except ValueError as exc:
            messagebox.showwarning("日志文件夹不符合要求", str(exc), parent=self)
            return

        self._clear_output()
        self._append_output(f"日志文件夹：{log_dir}")
        self._append_output("正在调用日志清洗与流量分析函数，请等待……")
        self.report_path = None
        self.btn_open.config(state="disabled")
        self._set_running(True)
        self.status_var.set("正在清洗日志并生成分析报告……")
        self.status_label.config(foreground="black")

        try:
            self.service.start(log_dir)
        except RuntimeError as exc:
            self._set_running(False)
            self.status_var.set("启动失败")
            messagebox.showerror("无法启动分析", str(exc), parent=self)

    def _poll_events(self) -> None:
        if not self.winfo_exists():
            return

        for event, message in self.service.get_events():
            if event == "output":
                self._append_output(message)
            elif event == "success":
                self._analysis_succeeded(Path(message))
            elif event == "error":
                self._analysis_failed(message)

        self.after(100, self._poll_events)

    def _analysis_succeeded(self, report_path: Path) -> None:
        self._set_running(False)
        self.report_path = report_path
        self.btn_open.config(state="normal")
        self._append_output(f"报告已生成：{report_path}")
        self.status_var.set("分析完成，正在打开 Markdown 报告……")
        self.status_label.config(foreground="green")

        try:
            self._open_with_default_app(report_path)
        except OSError as exc:
            self.status_var.set("分析完成，但无法自动打开报告，请点击“打开报告”重试")
            messagebox.showwarning(
                "报告已生成", f"报告位于：\n{report_path}\n\n自动打开失败：{exc}", parent=self
            )
        else:
            self.status_var.set("分析完成，报告已打开")

    def _analysis_failed(self, message: str) -> None:
        self._set_running(False)
        self._append_output(f"错误：{message}")
        self.status_var.set("分析失败，请查看执行过程")
        self.status_label.config(foreground="red")
        messagebox.showerror("流量分析失败", message, parent=self)

    def _set_running(self, running: bool) -> None:
        self._running = running
        state = "disabled" if running else "normal"
        self.btn_choose.config(state=state)
        self.btn_start.config(state=state)
        if running:
            self.progress.start(12)
        else:
            self.progress.stop()

    def _append_output(self, message: str) -> None:
        self.output.config(state="normal")
        self.output.insert(tk.END, message + "\n")
        self.output.see(tk.END)
        self.output.config(state="disabled")

    def _clear_output(self) -> None:
        self.output.config(state="normal")
        self.output.delete("1.0", tk.END)
        self.output.config(state="disabled")

    def open_report(self) -> None:
        if self.report_path is None or not self.report_path.is_file():
            messagebox.showwarning("报告不存在", "请先完成一次流量分析", parent=self)
            return
        try:
            self._open_with_default_app(self.report_path)
        except OSError as exc:
            messagebox.showerror("无法打开报告", str(exc), parent=self)

    @staticmethod
    def _open_with_default_app(report_path: Path) -> None:
        """使用当前系统默认的 Markdown 关联程序打开报告。"""
        if sys.platform == "win32":
            os.startfile(str(report_path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(report_path)])
        else:
            subprocess.Popen(
                ["xdg-open", str(report_path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
