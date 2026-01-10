import sys
import logging
import tkinter as tk
from gui.main_window import MainWindow
from androidToolbox.core.adb import ADBManager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def check_environment():
    """环境检查：Python版本、设备连接等"""
    # Python 版本检查
    if sys.version_info < (3, 12):
        logger.error(f"需要 Python 3.12+，当前版本: {sys.version}")
        sys.exit(1)
    logger.info(f"Python 版本: {sys.version.split()[0]}")


def init_adb():
    """ADB 初始化：检测路径并打印状态"""
    adb_source = ADBManager.init()
    logger.info(f"ADB 来源: {adb_source}")
    return adb_source


def setup_global_exception_handler():
    """全局异常捕获"""
    def handle_exception(exc_type, exc_value, exc_traceback):
        logger.error("未捕获的异常", exc_info=(exc_type, exc_value, exc_traceback))
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception


if __name__ == "__main__":
    # 1. 环境检查
    check_environment()

    # 2. 全局异常处理
    setup_global_exception_handler()

    # 3. ADB 初始化
    adb_source = init_adb()

    # 4. 启动 UI
    app = MainWindow()
    app.mainloop()