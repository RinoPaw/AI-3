# main.py
import sys

from boot_timing import boot_log

boot_log("Python started")

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

boot_log("PySide6 imported")

from main_window import MainWindow
from config import logger
from set_logger import delete_old_log_files

boot_log("Application modules imported")

def main():
    delete_old_log_files('logs')
    logger.info("Starting application")
    app = QApplication(sys.argv)
    app.setFont(QFont("Arial", 20))
    boot_log("QApplication created")

    # 根据主屏幕计算窗口尺寸
    screen = QApplication.primaryScreen()
    screen_geometry = screen.geometry()
    screen_width = screen_geometry.width()
    screen_height = screen_geometry.height()
    window_size = (screen_width, screen_height)
    logger.info(f"WINDOW_SIZE: {window_size}")
    # 创建并显示主窗口
    window = MainWindow(window_size)
    boot_log("MainWindow created")
    window.show()
    boot_log("Window shown")
    sys.exit(app.exec())
if __name__ == "__main__":
    main()
