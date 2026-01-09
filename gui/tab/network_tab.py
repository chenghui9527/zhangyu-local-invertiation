import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
# 引入业务服务
from androidToolbox.services.network_service import NetworkService

class NetworkTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill='both', expand=True, padx=5, pady=5)
        self.running = False
        self._setup_ui()

    def _setup_ui(self):
        # ... (UI 代码保持不变，省略 Label 创建过程) ...
        self.info_frame = ttk.LabelFrame(self, text="网络状态详情")
        self.info_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        self.lbl_wifi = ttk.Label(self.info_frame, text="WiFi: ...")
        self.lbl_wifi.pack(anchor='w', pady=5)
        
        self.lbl_mobile = ttk.Label(self.info_frame, text="Mobile: ...")
        self.lbl_mobile.pack(anchor='w', pady=5)
        
        self.lbl_diag = ttk.Label(self.info_frame, text="诊断: ...")
        self.lbl_diag.pack(anchor='w', pady=15)
        
        # Ping UI 部分...
        self.ping_frame = ttk.LabelFrame(self, text="连通性 (Ping)")
        self.ping_frame.pack(side='right', fill='y', padx=5)
        self.ping_log = scrolledtext.ScrolledText(self.ping_frame, width=35, height=10)
        self.ping_log.pack(fill='both', expand=True)
        
        ttk.Button(self.ping_frame, text="Ping Baidu", command=lambda: self.run_ping("www.baidu.com")).pack()

    def start(self):
        self.running = True
        self._refresh_ui_loop()

    def stop(self):
        self.running = False

    def _refresh_ui_loop(self):
        """UI 刷新循环：只负责拿数据和展示"""
        if not self.running or not self.winfo_exists(): return

        # === 核心变化：调用 Service 获取纯数据 ===
        status = NetworkService.analyze_network_status()
        
        # === 界面逻辑：根据数据决定显示什么颜色 ===
        # 1. WiFi
        self.lbl_wifi.config(text=f"WiFi RSSI: {status['wifi_rssi']} dBm")
        
        # 2. 移动网络
        mobile = status['mobile']
        self.lbl_mobile.config(text=f"移动网络: {mobile['type']}")
        
        # 3. 诊断信息
        if mobile['is_weak']:
            self.lbl_diag.config(text=f"诊断: {mobile['warning']}", foreground="red")
        else:
            self.lbl_diag.config(text="诊断: 网络状态正常", foreground="green")

        # 定时刷新
        self.after(3000, self._refresh_ui_loop)

    def run_ping(self, target):
        def task():
            self.ping_log.insert(tk.END, f"\n--- Ping {target} ---\n")
            # 调用 Service
            res = NetworkService.ping_target(target)
            self.ping_log.insert(tk.END, res)
            self.ping_log.see(tk.END)
        threading.Thread(target=task).start()