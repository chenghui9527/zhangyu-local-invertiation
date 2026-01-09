import tkinter as tk
from tkinter import ttk, scrolledtext
# 引入业务服务
from androidToolbox.services.logcat_service import LogcatService

class LogcatTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill='both', expand=True)
        # 初始化服务
        self.service = LogcatService()
        self._setup_ui()

    def _setup_ui(self):
        # ... (省略 Button 和 ScrolledText 创建代码) ...
        top_bar = ttk.Frame(self)
        top_bar.pack(fill='x')
        self.btn_start = ttk.Button(top_bar, text="开始", command=self.toggle)
        self.btn_start.pack(side='left')
        self.text_area = scrolledtext.ScrolledText(self)
        self.text_area.pack(fill='both', expand=True)
        
        # 配置颜色 tag
        self.text_area.tag_config("E", foreground="red")
        # ...

    def toggle(self):
        if not self.service.is_running():
            self.service.start_capture()
            self.btn_start.config(text="停止")
            self._ui_update_loop()
        else:
            self.service.stop_capture()
            self.btn_start.config(text="开始")

    def _ui_update_loop(self):
        if not self.service.is_running(): return

        self.text_area.config(state='normal')
        
        # === 核心变化：从 Service 批量获取数据 ===
        # UI 不再关心 Queue 怎么运作，只管“拿日志”
        for line in self.service.get_logs():
            tag = "I"
            if " E " in line: tag = "E"
            elif " W " in line: tag = "W"
            self.text_area.insert(tk.END, line, tag)

        # 自动清理旧日志（纯 UI 保护逻辑）
        if int(self.text_area.index('end-1c').split('.')[0]) > 2000:
            self.text_area.delete('1.0', '200.0')

        self.text_area.see(tk.END)
        self.text_area.config(state='disabled')
        
        self.after(100, self._ui_update_loop)