import threading
import queue
from androidToolbox.core.adb import ADBManager

class LogcatService:
    def __init__(self):
        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        self.worker_thread = None

    def start_capture(self, filter_str=""):
        """启动日志抓取线程"""
        if self.is_running():
            return

        self.stop_event.clear()
        # 清除缓存
        ADBManager.run("logcat -c")
        
        # 启动后台线程
        self.worker_thread = threading.Thread(
            target=ADBManager.stream_logcat,
            args=(filter_str, self.stop_event, self.log_queue),
            daemon=True
        )
        self.worker_thread.start()

    def stop_capture(self):
        """停止日志抓取"""
        if self.is_running():
            self.stop_event.set()
            self.worker_thread.join(timeout=1)
            self.worker_thread = None

    def is_running(self):
        return self.worker_thread is not None and self.worker_thread.is_alive()

    def get_logs(self):
        """生成器：非阻塞地获取当前队列中的所有日志"""
        while not self.log_queue.empty():
            try:
                yield self.log_queue.get_nowait()
            except queue.Empty:
                break