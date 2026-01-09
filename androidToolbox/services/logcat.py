import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import queue
from datetime import datetime
from core.adb import ADBManager

class LogcatTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill='both', expand=True)
        self.log_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.capturing = False
        self._setup_ui()

    def _setup_ui(self):
        # 工具栏
        bar = ttk.Frame(self)
        bar.pack(fill='x', padx=5, pady=5)
        
        self.btn_action = ttk.Button(bar, text="开始抓取", command=self.toggle_capture)
        self.btn_action.pack(side='left')
        
        ttk.Button(bar, text="清空", command=self.clear_log).pack(side='left', padx=5)
        ttk.Button(bar, text="导出", command=self.export_log).pack(side='left')
        
        ttk.Label(bar, text=" grep: ").pack(side='left')
        self.entry_filter = ttk.Entry(bar, width=15)
        self.entry_filter.pack(side='left')

        # 日志区
        self.text_area = scrolledtext.ScrolledText(self, font=("Consolas", 9), state='disabled')
        self.text_area.pack(fill='both', expand=True, padx=5, pady=5)
        self.text_area.tag_config("E", foreground="red")
        self.text_area.tag_config("W", foreground="#FFA500")
        self.text_area.tag_config("D", foreground="blue")

    def toggle_capture(self):
        if not self.capturing:
            self.capturing = True
            self.btn_action.config(text="停止抓取")
            self.stop_event.clear()
            ADBManager.run("logcat -c") # 清除缓存
            
            filter_str = self.entry_filter.get().strip()
            threading.Thread(target=ADBManager.stream_logcat, 
                             args=(filter_str, self.stop_event, self.log_queue),
                             daemon=True).start()
            self._update_loop()
        else:
            self.capturing = False
            self.btn_action.config(text="开始抓取")
            self.stop_event.set()

    def _update_loop(self):
        if not self.capturing: return
        
        self.text_area.config(state='normal')
        while not self.log_queue.empty():
            try:
                line = self.log_queue.get_nowait()
                tag = "I"
                if " E " in line or " E/" in line: tag = "E"
                elif " W " in line or " W/" in line: tag = "W"
                elif " D " in line or " D/" in line: tag = "D"
                self.text_area.insert(tk.END, line, tag)
            except queue.Empty:
                break
        
        # 限制行数防止卡顿
        if int(self.text_area.index('end-1c').split('.')[0]) > 2000:
            self.text_area.delete('1.0', '200.0')
            
        self.text_area.see(tk.END)
        self.text_area.config(state='disabled')
        self.after(100, self._update_loop)

    def clear_log(self):
        self.text_area.config(state='normal')
        self.text_area.delete('1.0', tk.END)
        self.text_area.config(state='disabled')

    def export_log(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"log_{datetime.now().strftime('%H%M%S')}.txt"
        )
        if filename:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(self.text_area.get("1.0", tk.END))