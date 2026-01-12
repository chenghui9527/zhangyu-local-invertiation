import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
from androidToolbox.services.logcat_service import LogcatService

# 内存溢出阈值（行数）
MAX_LOG_LINES = 50000
# UI最大保留行数
MAX_UI_LINES = 2000

class LogcatTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill='both', expand=True)
        # 初始化服务
        self.service = LogcatService()
        self._setup_ui()

    def _setup_ui(self):
        top_bar = ttk.Frame(self)
        top_bar.pack(fill='x')

        self.btn_start = ttk.Button(top_bar, text="开始", command=self.toggle)
        self.btn_start.pack(side='left', padx=5, pady=5)

        self.btn_export = ttk.Button(top_bar, text="导出TXT", command=self.export_logs)
        self.btn_export.pack(side='left', padx=5, pady=5)

        # 状态标签
        self.status_label = ttk.Label(top_bar, text="日志: 0 行")
        self.status_label.pack(side='left', padx=10)

        self.text_area = scrolledtext.ScrolledText(self)
        self.text_area.pack(fill='both', expand=True)

        # 配置颜色 tag
        self.text_area.tag_config("E", foreground="red")
        self.text_area.tag_config("W", foreground="orange")
        self.text_area.tag_config("I", foreground="green")

        # 绑定右键菜单
        self.text_area.bind("<Button-3>", self._show_context_menu)

        # 创建右键菜单
        self.context_menu = tk.Menu(self.text_area, tearoff=0)
        self.context_menu.add_command(label="复制", command=self._copy_text)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="清除日志", command=self.clear_logs)

        # 自动滚动控制
        self._auto_scroll = True
        # 服务端日志行数统计
        self._service_line_count = 0

    def stop(self):
        """停止监控（切换 Tab 时调用）"""
        self.service.stop_capture()
        self._auto_scroll = False
        if self.btn_start.cget('text') == "停止":
            self.btn_start.config(text="开始")

    def stop_auto_scroll(self):
        """停止自动滚动"""
        self._auto_scroll = False

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

        # 从 Service 批量获取数据
        new_logs = self.service.get_logs()
        for line in new_logs:
            tag = "I"
            if " E " in line: tag = "E"
            elif " W " in line: tag = "W"
            self.text_area.insert(tk.END, line, tag)
            self._service_line_count += 1

        # 自动清理旧日志（UI 保护逻辑）
        current_lines = int(self.text_area.index('end-1c').split('.')[0])
        if current_lines > MAX_UI_LINES:
            self.text_area.delete('1.0', f'{current_lines - MAX_UI_LINES + 100}.0')

        if self._auto_scroll:
            self.text_area.see(tk.END)
        self.text_area.config(state='disabled')

        # 更新状态栏
        self.status_label.config(text=f"日志: {self._service_line_count} 行")

        # 内存溢出风险检测
        risk_msg = self._check_memory_risk()
        if risk_msg:
            self.status_label.config(foreground="red")
            # 可选：弹出警告
            # self.after(0, lambda: messagebox.showwarning("内存风险", risk_msg))
        else:
            self.status_label.config(foreground="black")

        self.after(100, self._ui_update_loop)

    # ============ 右键菜单相关方法 ============

    def _show_context_menu(self, event):
        """显示右键菜单"""
        # 选中当前鼠标位置的单词
        self.text_area.tag_remove("sel", "1.0", tk.END)
        self.text_area.mark_set("insert", f"@{event.x},{event.y}")
        self.text_area.tag_add("sel", "insert wordstart", "insert wordend")
        self.context_menu.post(event.x_root, event.y_root)

    def _copy_text(self):
        """复制选中的文本"""
        try:
            selected = self.text_area.get(tk.SEL_FIRST, tk.SEL_LAST)
            self.clipboard_clear()
            self.clipboard_append(selected)
        except tk.TclError:
            pass

    # ============ 日志导出功能 ============

    def export_logs(self):
        """导出日志到TXT文件"""
        if self.text_area.get('1.0', tk.END).strip() == "":
            messagebox.showwarning("警告", "没有日志可导出")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
            title="导出日志"
        )

        if file_path:
            try:
                content = self.text_area.get('1.0', tk.END)
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("成功", f"日志已导出到:\n{file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"导出失败:\n{str(e)}")

    def clear_logs(self):
        """清除日志控制台"""
        self.text_area.config(state='normal')
        self.text_area.delete('1.0', tk.END)
        self.text_area.config(state='disabled')
        self._service_line_count = 0
        self.status_label.config(text="日志: 0 行")

    # ============ 内存溢出风险检测 ============

    def _check_memory_risk(self):
        """检查内存溢出风险并返回警告信息"""
        if self._service_line_count >= MAX_LOG_LINES:
            return f"警告: 日志数量已达 {self._service_line_count} 行，接近内存限制 ({MAX_LOG_LINES} 行)，建议清除或导出日志"
        return None