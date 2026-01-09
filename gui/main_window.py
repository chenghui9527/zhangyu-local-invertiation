import tkinter as tk
from tkinter import ttk
import threading
import time

# 引入底层 ADB 核心（用于全局初始化和设备检测）
from androidToolbox.core.adb import ADBManager

# 引入各个功能模块的 UI (View)
# 注意：这里假设你已经按照之前的规划，将具体的 Tab UI 代码放入了 gui/tabs/ 目录下
from gui.tabs.network_tab import NetworkTab
from gui.tabs.logcat_tab import LogcatTab
from gui.tabs.monitor_tab import MonitorTab

class MainWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # 1. 窗口基础设置
        self.title("Android 工程调试终端 (Engineering Edition)")
        self.geometry("800x600") # 稍微调大一点，适应现代屏幕
        self.minsize(600, 500)
        
        # 2. 全局初始化
        # 检测 ADB 路径，确保后续模块调用时 ADBManager 已经准备好
        adb_status_msg = ADBManager.init()
        
        # 3. UI 布局初始化
        self._setup_status_bar(adb_status_msg)
        self._setup_notebook()
        
        # 4. 启动后台守护线程 (设备连接状态检测)
        # daemon=True 保证主程序关闭时，这个线程也会自动结束
        threading.Thread(target=self._device_checker_loop, daemon=True).start()

    def _setup_status_bar(self, adb_msg):
        """初始化底部状态栏"""
        self.status_bar = ttk.Label(
            self, 
            text=f"系统就绪 | ADB模式: {adb_msg} | 等待设备连接...", 
            relief=tk.SUNKEN, 
            anchor='w', 
            padding=(10, 5)
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _setup_notebook(self):
        """初始化选项卡控制器 (Tab容器)"""
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)
        
        # --- 实例化各个 Tab 页面 ---
        # 这里的 Tab 类只负责 UI 展示，它们内部会去调用 androidToolbox 里的 Service
        self.tab_net = NetworkTab(self.notebook)
        self.tab_log = LogcatTab(self.notebook)
        self.tab_mon = MonitorTab(self.notebook)
        
        # --- 添加到 Notebook ---
        self.notebook.add(self.tab_net, text=" 📶 网络诊断 ")
        self.notebook.add(self.tab_log, text=" 📜 Logcat 日志 ")
        self.notebook.add(self.tab_mon, text=" 📊 性能监控 ")
        
        # --- 绑定事件 ---
        # 当用户切换 Tab 时，触发 _on_tab_change 方法
        # 目的：为了节省性能，只在用户看得到的页面开启数据轮询
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_change)

    def _on_tab_change(self, event):
        """
        Tab 切换事件处理：
        策略：'懒加载' + '即停即止'。
        切换走时停止旧 Tab 的监控，切换来时启动新 Tab 的监控。
        """
        # 1. 先“暂停”所有 Tab 的后台任务
        # (确保每个 Tab 类里都实现了 stop() 方法)
        self.tab_net.stop()
        self.tab_log.stop_auto_scroll() # 日志模块通常不停止抓取，只停止自动滚动以免干扰，或者看你需求
        self.tab_mon.stop()
        
        # 2. 获取当前选中的 Tab 索引
        # select() 返回的是 widget ID，需要转换
        current_tab_index = self.notebook.index("current")
        
        # 3. 根据索引启动对应的 Tab
        if current_tab_index == 0:
            # 网络诊断 Tab
            self.tab_net.start()
        elif current_tab_index == 1:
            # 日志 Tab (通常日志是手动开始的，这里可以选择不自动 start，或者仅恢复滚动)
            pass 
        elif current_tab_index == 2:
            # 性能监控 Tab
            self.tab_mon.start()

    def _device_checker_loop(self):
        """
        后台线程：每隔 3 秒检查一次设备连接状态。
        不包含任何 UI 刷新逻辑，只负责修改 status_bar 的文字。
        """
        while True:
            # 调用底层 ADB 能力
            # 注意：这里的 run 可能会阻塞，所以必须放在子线程
            res = ADBManager.run("devices")
            
            # 简单的字符串判断
            is_connected = "device" in res.replace("List of devices attached", "").strip()
            
            # 更新 UI (Tkinter 是线程安全的吗？大部分简单配置是，但建议用 after，这里为了简便直接改)
            if is_connected:
                self.status_bar.config(background="#90EE90", text="[在线] 设备已连接 | 调试服务运行中")
            else:
                self.status_bar.config(background="#FFB6C1", text="[离线] 未检测到设备，请检查 USB 连接")
            
            time.sleep(3)

if __name__ == "__main__":
    # 如果直接运行这个文件进行测试
    app = MainWindow()
    app.mainloop()