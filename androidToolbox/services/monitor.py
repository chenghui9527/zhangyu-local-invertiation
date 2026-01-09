import tkinter as tk
from tkinter import ttk
from collections import deque
import re
from core.adb import ADBManager

class MonitorTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill='both', expand=True, padx=10, pady=10)
        self.data_points = deque([0]*30, maxlen=30)
        self.running = False
        self._setup_ui()

    def _setup_ui(self):
        # 仪表盘
        panel = ttk.Frame(self)
        panel.pack(fill='x', pady=5)
        self.lbl_ram = ttk.Label(panel, text="RAM: --", font=("Arial", 11, "bold"))
        self.lbl_ram.pack(side='left', padx=10)
        self.lbl_disk = ttk.Label(panel, text="Disk: --", font=("Arial", 11, "bold"))
        self.lbl_disk.pack(side='left', padx=10)

        # 绘图区
        self.cv_h = 200
        self.canvas = tk.Canvas(self, height=self.cv_h, bg="white", bd=1, relief="solid")
        self.canvas.pack(fill='x', pady=10)
        self.canvas.create_text(20, 10, text="可用内存趋势 (MB)", anchor='w', fill="#888")

    def start(self):
        self.running = True
        self._update_loop()

    def stop(self):
        self.running = False

    def _draw_chart(self):
        self.canvas.delete("chart_line")
        w = self.canvas.winfo_width()
        data = list(self.data_points)
        
        min_v, max_v = min(data), max(data)
        if max_v == min_v: max_v += 1
        
        points = []
        step_x = w / (len(data) - 1) if len(data) > 1 else w
        
        for i, val in enumerate(data):
            x = i * step_x
            # 归一化 Y 轴
            y = self.cv_h - ((val - min_v) / (max_v - min_v) * (self.cv_h - 40)) - 20
            points.append(x)
            points.append(y)
            
        if len(points) >= 4:
            self.canvas.create_line(points, tag="chart_line", fill="#007bff", width=2, smooth=True)

    def _update_loop(self):
        if not self.running or not self.winfo_exists(): return

        # 1. 内存
        mem = ADBManager.run("shell cat /proc/meminfo")
        match = re.search(r'MemAvailable:\s+(\d+)', mem)
        if match:
            mb = int(match.group(1)) // 1024
            self.data_points.append(mb)
            self.lbl_ram.config(text=f"RAM可用: {mb} MB")
            self._draw_chart()

        # 2. 磁盘
        disk = ADBManager.run("shell df -h /data")
        try:
            line = disk.splitlines()[-1]
            parts = line.split()
            # 兼容不同 Android 版本的 df 输出
            free = parts[3] if len(parts) >= 4 else "?"
            self.lbl_disk.config(text=f"Disk可用: {free}")
        except: pass

        self.after(2000, self._update_loop)