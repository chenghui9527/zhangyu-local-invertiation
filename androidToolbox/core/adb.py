import os
import subprocess
import threading

class ADBManager:
    # 自动检测当前目录下是否有 adb，没有则尝试系统变量
    _ADB_PATH = "adb"
    
    @classmethod
    def init(cls):
        """初始化：检测 ADB 路径"""
        # 获取 main.py 所在的根目录
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # 假设 adb 在 assets 目录下，或者项目根目录下
        bundled_adb = os.path.join(base_dir, "assets", "adb.exe" if os.name == 'nt' else "adb")
        
        if os.path.exists(bundled_adb):
            cls._ADB_PATH = bundled_adb
            return "Bundled (内置)"
        
        # 也可以检测根目录
        root_adb = os.path.join(base_dir, "adb.exe" if os.name == 'nt' else "adb")
        if os.path.exists(root_adb):
            cls._ADB_PATH = root_adb
            return "Root Path (根目录)"
            
        return "System Path (环境变量)"

    @classmethod
    def run(cls, cmd, timeout=5):
        """执行简单的 ADB 命令并返回字符串结果"""
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            
            full_cmd = f'"{cls._ADB_PATH}" {cmd}'
            result = subprocess.run(
                full_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=timeout,
                startupinfo=startupinfo
            )
            return result.stdout.strip()
        except Exception as e:
            return f"Error: {str(e)}"

    @classmethod
    def stream_logcat(cls, filter_str, stop_event, data_queue):
        """流式执行 Logcat (运行在子线程)"""
        full_cmd = f'"{cls._ADB_PATH}" logcat -v time'
        process = None
        try:
            startupinfo = None
            if os.name == 'nt':
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

            process = subprocess.Popen(
                full_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                startupinfo=startupinfo
            )
            
            while not stop_event.is_set():
                line = process.stdout.readline()
                if not line:
                    break
                if filter_str and filter_str not in line:
                    continue
                data_queue.put(line)
        except Exception:
            pass
        finally:
            if process:
                process.terminate()