import tkinter as tk
from tkinter import ttk
import threading
import time

# 导入我们的模块
from core.adb import ADBManager
from modules.network import NetworkTab
from modules.logcat import LogcatTab
from modules.monitor import MonitorTab

class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Android 工程调试终端 (Engineering Edition)")
        self.geometry("650x500")
        
        # 1. 初始化 ADB
        adb_status = ADBManager.init()
        
        # 2. 底部状态栏
        self.status_bar = ttk.Label(self, text=f"ADB模式: {adb_status} | 检查连接...", 
                                  relief=tk.SUNKEN, anchor='w', padding=5)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # 3. 选项卡控制器
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True)
        
        # 4. 加载模块
        self.tab_net = NetworkTab(self.notebook)
        self.tab_log = LogcatTab(self.notebook)
        self.tab_mon = MonitorTab(self.notebook)
        
        self.notebook.add(self.tab_net, text=" 📶 网络诊断 ")
        self.notebook.add(self.tab_log, text=" 📜 Logcat日志 ")
        self.notebook.add(self.tab_mon, text=" 📊 性能监控 ")
        
        # 5. 事件绑定：切换 Tab 时才启动对应的监控，节省资源
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)
        
        # 6. 后台设备检测线程
        threading.Thread(target=self._device_checker, daemon=True).start()

    def _on_tab_change(self, event):
        # 先暂停所有
        self.tab_net.stop()
        self.tab_mon.stop()
        
        # 获取当前选中的 Tab 索引
        idx = self.notebook.index("current")
        
        # 按需启动
        if idx == 0:
            self.tab_net.start()
        elif idx == 2:
            self.tab_mon.start()

    def _device_checker(self):
        """后台持续检测设备连接状态"""
        while True:
            res = ADBManager.run("devices")
            if "device" in res.replace("List of devices attached", "").strip():
                self.status_bar.config(background="#98fb98", text="[在线] 设备已连接")
            else:
                self.status_bar.config(background="#ffb6c1", text="[离线] 未检测到设备")
            time.sleep(3)

if __name__ == "__main__":
    app = MainApp()
    app.mainloop()