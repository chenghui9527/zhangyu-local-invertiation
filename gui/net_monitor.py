import tkinter as tk
from tkinter import ttk
import subprocess
import re
import time
import threading

class NetworkMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Android 网络质量实时诊断工具")
        self.root.geometry("450x450")
        self.root.resizable(False, False)

        # 样式设置
        style = ttk.Style()
        style.configure("Big.TLabel", font=("Helvetica", 12, "bold"))
        style.configure("Status.TLabel", font=("Helvetica", 10))
        style.configure("Alert.TLabel", foreground="red", font=("Helvetica", 11, "bold"))
        style.configure("Good.TLabel", foreground="green", font=("Helvetica", 11, "bold"))

        # --- UI 布局 ---
        
        # 1. 设备状态区
        frame_device = ttk.LabelFrame(root, text="设备连接状态", padding=10)
        frame_device.pack(fill="x", padx=10, pady=5)
        self.lbl_device = ttk.Label(frame_device, text="正在检测设备...", style="Status.TLabel")
        self.lbl_device.pack(anchor="w")

        # 2. WiFi 监控区
        frame_wifi = ttk.LabelFrame(root, text="WiFi 状态", padding=10)
        frame_wifi.pack(fill="x", padx=10, pady=5)
        self.lbl_wifi_rssi = ttk.Label(frame_wifi, text="RSSI: --", style="Status.TLabel")
        self.lbl_wifi_rssi.pack(anchor="w")
        self.lbl_wifi_status = ttk.Label(frame_wifi, text="等待数据...", style="Status.TLabel")
        self.lbl_wifi_status.pack(anchor="w")

        # 3. 移动数据监控区 (重点)
        frame_mobile = ttk.LabelFrame(root, text="移动数据 (4G/5G) 状态", padding=10)
        frame_mobile.pack(fill="x", padx=10, pady=5)
        self.lbl_mobile_type = ttk.Label(frame_mobile, text="网络类型: --", style="Status.TLabel")
        self.lbl_mobile_type.pack(anchor="w")
        self.lbl_mobile_level = ttk.Label(frame_mobile, text="信号等级 (Level): --", style="Status.TLabel")
        self.lbl_mobile_level.pack(anchor="w")
        self.lbl_mobile_detail = ttk.Label(frame_mobile, text="信号强度 (dBm): --", style="Status.TLabel")
        self.lbl_mobile_detail.pack(anchor="w")

        # 4. 诊断结论区
        frame_diag = ttk.LabelFrame(root, text="诊断结论", padding=10)
        frame_diag.pack(fill="x", padx=10, pady=10)
        self.lbl_diag = ttk.Label(frame_diag, text="初始化中...", style="Status.TLabel", wraplength=400)
        self.lbl_diag.pack(anchor="w")

        # 底部控制
        self.btn_refresh = ttk.Button(root, text="手动刷新", command=self.refresh_data)
        self.btn_refresh.pack(pady=5)
        
        # 自动刷新开关
        self.auto_refresh = True
        self.schedule_refresh()

    def run_adb_cmd(self, cmd):
        """执行ADB命令并返回结果"""
        try:
            # 使用 shell=True 可能会有窗口闪烁，这里使用 startupinfo 隐藏窗口 (Windows only)
            startupinfo = None
            if hasattr(subprocess, 'STARTUPINFO'):
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            result = subprocess.run(
                f"adb {cmd}", 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                shell=True, 
                text=True,
                encoding='utf-8', # 根据系统可能需要改为 gbk
                errors='ignore',
                startupinfo=startupinfo
            )
            return result.stdout
        except Exception as e:
            return ""

    def parse_wifi(self):
        """解析 WiFi 信号"""
        output = self.run_adb_cmd("shell dumpsys wifi")
        # 匹配 RSSI: -XX
        match = re.search(r'RSSI:\s*(-?\d+)', output)
        if match:
            rssi = int(match.group(1))
            return rssi
        return None

    def parse_mobile(self):
        """解析移动网络信号，核心逻辑"""
        # 只获取 telephony.registry 的相关部分，减少数据量
        output = self.run_adb_cmd("shell dumpsys telephony.registry")
        
        info = {
            "type": "未知",
            "level": -1,
            "dbm": 0,
            "is_nr": False
        }

        # 简单的状态机逻辑来判断主网络
        # 1. 检查是否连接了 5G (NR)
        # 注意：不同手机输出格式略有不同，这里适配你日志中的格式
        # mNr=CellSignalStrengthNr:{ ... level = 1 ... }
        
        nr_match = re.search(r'mNr=CellSignalStrengthNr:.*?level\s*=\s*(\d+).*?ssRsrp\s*=\s*(-?\d+)', output, re.DOTALL)
        lte_match = re.search(r'mLte=CellSignalStrengthLte:.*?rssi\s*=\s*(-?\d+).*?level\s*=\s*(\d+)', output, re.DOTALL)

        # 检查 displayInfo 或者是 mServiceState 来确定到底是谁在生效
        # 这里简化逻辑：如果有 5G 信号读数且 level > 0，优先展示 5G，否则展示 4G
        
        if nr_match:
            nr_level = int(nr_match.group(1))
            nr_rsrp = int(nr_match.group(2))
            
            # 只有当 5G 有效（非最大值占位符）时才算
            if nr_rsrp < 0 and nr_rsrp > -140: 
                info["type"] = "5G (NR)"
                info["level"] = nr_level
                info["dbm"] = nr_rsrp
                info["is_nr"] = True
                return info

        if lte_match:
            lte_rssi = int(lte_match.group(1))
            lte_level = int(lte_match.group(2))
            # 过滤无效值
            if lte_rssi < 0:
                info["type"] = "4G (LTE)"
                info["level"] = lte_level
                info["dbm"] = lte_rssi
                return info

        return info

    def refresh_data(self):
        """执行数据刷新任务"""
        threading.Thread(target=self._refresh_logic).start()

    def _refresh_logic(self):
        # 1. 检查连接
        devices = self.run_adb_cmd("devices")
        if "device" not in devices.replace("List of devices attached", "").strip():
            self.update_ui_device("未连接设备", False)
            return
        else:
            self.update_ui_device("设备已连接", True)

        # 2. 获取 WiFi
        rssi = self.parse_wifi()
        
        # 3. 获取 移动网络
        mobile_info = self.parse_mobile()

        # 更新 UI (必须在主线程)
        self.root.after(0, lambda: self.update_ui_data(rssi, mobile_info))

    def update_ui_device(self, text, is_connected):
        color = "green" if is_connected else "red"
        self.lbl_device.config(text=text, foreground=color)

    def update_ui_data(self, wifi_rssi, mobile_info):
        # --- WiFi 逻辑 ---
        if wifi_rssi is not None:
            self.lbl_wifi_rssi.config(text=f"RSSI: {wifi_rssi} dBm")
            if wifi_rssi < -70:
                self.lbl_wifi_status.config(text="⚠️ 信号弱 (丢包风险高)", style="Alert.TLabel")
            elif wifi_rssi < -50:
                 self.lbl_wifi_status.config(text="信号良好", style="Status.TLabel")
            else:
                 self.lbl_wifi_status.config(text="信号极佳", style="Good.TLabel")
        else:
            self.lbl_wifi_rssi.config(text="RSSI: -- (未连接WiFi或关闭)")
            self.lbl_wifi_status.config(text="", style="Status.TLabel")

        # --- 移动网络逻辑 ---
        diag_msg = "网络状态正常。"
        diag_style = "Good.TLabel"

        if mobile_info['level'] != -1:
            self.lbl_mobile_type.config(text=f"网络类型: {mobile_info['type']}")
            self.lbl_mobile_level.config(text=f"信号等级: {mobile_info['level']} / 4")
            self.lbl_mobile_detail.config(text=f"信号强度: {mobile_info['dbm']} dBm")
            
            # --- 诊断核心逻辑 ---
            # 1. 虚假 5G 检测
            if mobile_info['is_nr']: 
                if mobile_info['level'] <= 1 or mobile_info['dbm'] < -105:
                    diag_msg = "🔴 严重警告：检测到“虚弱 5G”！\n虽然显示 5G，但信号极差。会导致 HTTP 请求超时。\n👉 建议：请立即在设置中关闭 5G 开关。"
                    diag_style = "Alert.TLabel"
                elif mobile_info['level'] <= 2:
                    diag_msg = "⚠️ 警告：5G 信号一般，可能出现波动。"
                    diag_style = "Alert.TLabel"
            
            # 2. 4G 弱网检测
            elif mobile_info['type'] == "4G (LTE)" and mobile_info['level'] <= 1:
                diag_msg = "⚠️ 警告：4G 信号微弱，请移动到开阔地带。"
                diag_style = "Alert.TLabel"
                
        else:
            self.lbl_mobile_type.config(text="网络类型: 未知/无SIM卡")
            self.lbl_mobile_level.config(text="--")
            self.lbl_mobile_detail.config(text="--")
            if wifi_rssi is None:
                diag_msg = "🔴 无网络连接：WiFi 和 移动数据均未连接。"
                diag_style = "Alert.TLabel"

        self.lbl_diag.config(text=diag_msg, style=diag_style)

    def schedule_refresh(self):
        if self.auto_refresh:
            self.refresh_data()
            # 每 3 秒刷新一次
            self.root.after(3000, self.schedule_refresh)

if __name__ == "__main__":
    root = tk.Tk()
    app = NetworkMonitorApp(root)
    root.mainloop()