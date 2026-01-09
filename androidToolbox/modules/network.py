import tkinter as tk
from tkinter import ttk, scrolledtext
import threading
import re
from core.adb import ADBManager

class NetworkTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill='both', expand=True, padx=5, pady=5)
        self.running = False
        self._setup_ui()

    def _setup_ui(self):
        # 左侧：状态面板
        self.info_frame = ttk.LabelFrame(self, text="网络状态详情")
        self.info_frame.pack(side='left', fill='both', expand=True, padx=5)
        
        self.lbl_wifi = ttk.Label(self.info_frame, text="WiFi: ...", font=("Consolas", 10))
        self.lbl_wifi.pack(anchor='w', pady=5)
        
        self.lbl_mobile = ttk.Label(self.info_frame, text="Mobile: ...", font=("Consolas", 10))
        self.lbl_mobile.pack(anchor='w', pady=5)
        
        self.lbl_diag = ttk.Label(self.info_frame, text="诊断结果: ...", foreground="gray")
        self.lbl_diag.pack(anchor='w', pady=15)

        # 右侧：Ping 工具
        self.ping_frame = ttk.LabelFrame(self, text="连通性 (Ping)")
        self.ping_frame.pack(side='right', fill='y', padx=5)
        
        self.ping_log = scrolledtext.ScrolledText(self.ping_frame, width=35, height=10, font=("Consolas", 8))
        self.ping_log.pack(fill='both', expand=True)
        
        btn_frame = ttk.Frame(self.ping_frame)
        btn_frame.pack(fill='x')
        ttk.Button(btn_frame, text="Ping 百度", command=lambda: self.run_ping("www.baidu.com")).pack(side='left', fill='x', expand=True)
        ttk.Button(btn_frame, text="Ping 网关", command=lambda: self.run_ping("192.168.1.1")).pack(side='left', fill='x', expand=True)

    def start(self):
        self.running = True
        self._loop_data()

    def stop(self):
        self.running = False

    def _loop_data(self):
        if not self.running or not self.winfo_exists(): return
        
        # 1. 获取 WiFi
        wifi_out = ADBManager.run("shell dumpsys wifi | grep RSSI")
        rssi_match = re.search(r'RSSI:\s*(-?\d+)', wifi_out)
        rssi = int(rssi_match.group(1)) if rssi_match else -100
        
        # 2. 获取 移动网络
        tele_out = ADBManager.run("shell dumpsys telephony.registry")
        
        # 状态判断逻辑
        mob_txt = "未知/无SIM"
        diag_txt = "正常"
        diag_col = "green"
        
        is_5g = "nrState=CONNECTED" in tele_out or "CellSignalStrengthNr" in tele_out
        
        if is_5g:
            mob_txt = "5G (NR)"
            if "level=1" in tele_out or "level=0" in tele_out:
                diag_txt = "警告: 发现虚弱 5G 信号，建议强制切换 4G"
                diag_col = "red"
        elif "CellSignalStrengthLte" in tele_out:
            mob_txt = "4G (LTE)"
            
        # 更新 UI
        self.lbl_wifi.config(text=f"WiFi RSSI: {rssi} dBm")
        self.lbl_mobile.config(text=f"移动网络: {mob_txt}")
        self.lbl_diag.config(text=diag_txt, foreground=diag_col)
        
        self.after(3000, self._loop_data)

    def run_ping(self, target):
        def task():
            self.ping_log.insert(tk.END, f"\n--- Ping {target} ---\n")
            res = ADBManager.run(f"shell ping -c 3 -W 1 {target}")
            self.ping_log.insert(tk.END, res)
            self.ping_log.see(tk.END)
        threading.Thread(target=task).start()