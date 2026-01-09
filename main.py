import tkinter as tk
from gui.main_window import MainWindow
from androidToolbox.core.adb import ADBManager

if __name__ == "__main__":
    # 1. 全局初始化 (如果需要)
    ADBManager.init()
    
    # 2. 启动 UI
    app = MainWindow()
    app.mainloop()