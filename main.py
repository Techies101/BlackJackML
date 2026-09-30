"""
21 Vision: AI Card Counter: live Hi-Lo card counter.

Opens the always-on-top main window (Main · Basic Strategy · Deviations · Bet Spread)
and the Program Logs window. The capture pipeline runs on a background thread
(core/pipeline.py); press Start capture once the model has loaded.
"""
import signal
import sys

from core import config

try:
    import dxcam
except ImportError:
    dxcam = None


def start_dxcam(region):
    """Start dxcam capture, or return None so the pipeline falls back to mss.

    Must run before torch/ultralytics is imported: on Intel + NVIDIA laptops,
    Windows refuses Desktop Duplication in a process that has initialised CUDA.
    """
    if dxcam is None:
        return None

    r = region
    try:
        camera = dxcam.create(output_color="BGR")
        camera.start(region=(r["left"], r["top"], r["left"] + r["width"], r["top"] + r["height"]),
                     target_fps=60, video_mode=True)
        return camera
    except Exception as e:
        print(f"[WARNING] dxcam failed ({e}); falling back to mss.")
        return None


def main():
    from core import settings as settings_store   # no torch here, so safe before dxcam

    settings = settings_store.load()
    left, top = settings["capture_region"]
    region = {**config.CAPTURE_REGION, "left": left, "top": top}
    camera = start_dxcam(region)

    # Imported after dxcam has started (see start_dxcam); none of these load torch at import time
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from core.counter import ShoeCounter
    from core.logbus import bus, log
    from core.pipeline import CaptureWorker
    from core.strategy import Strategy
    from ui import theme
    from ui.logs_window import LogsWindow
    from ui.main_window import MainWindow
    from ui.widgets import keep_on_screen

    # Own taskbar identity, so Windows shows the 21 Vision icon instead of Python's; and above-normal priority,
    # so a screen recorder or the browser can't starve the capture loop (stalls made it miss cards)
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("21Vision.AICardCounter")
        ABOVE_NORMAL_PRIORITY_CLASS = 0x8000
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(), ABOVE_NORMAL_PRIORITY_CLASS)
    except (AttributeError, OSError):
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("21 Vision: AI Card Counter")
    # Ctrl+C in the terminal closes the app (the 100 ms UI timer lets Python see the signal). Queued, because
    # app.quit() is ignored if Ctrl+C arrives during start-up, before the event loop is running.
    signal.signal(signal.SIGINT, lambda *_: QTimer.singleShot(0, app.quit))
    theme.load_fonts()
    app.setFont(theme.font(13))
    app.setStyleSheet(theme.STYLESHEET)
    app.setWindowIcon(theme.app_icon())

    counter = ShoeCounter()
    worker = CaptureWorker(camera, counter, region, settings["zone"])
    capture_method = "dxcam" if camera is not None else "mss"

    logs = LogsWindow()
    bus.message.connect(logs.append)
    window = MainWindow(worker, counter, Strategy(), settings, logs, capture_method)

    # Default placement: right of the capture area (the window may run off the right edge)
    right_of_capture = left + config.CAPTURE_REGION["width"] + 10
    window.move(*settings.get("window", [right_of_capture, 10]))
    logs.resize(*settings.get("logs_size", [520, 260]))
    logs.move(*settings.get("logs_window", [window.x(), window.y() + window.height() + 8]))
    window.show()
    logs.show()
    keep_on_screen(window)   # a saved position can leave the title bar off-screen
    keep_on_screen(logs)
    app.aboutToQuit.connect(window.save_settings)   # also when quitting via Ctrl+C

    log("SYSTEM", f"Screen capture: {capture_method} · Loading YOLO model…")
    worker.start()

    try:
        return app.exec()
    finally:
        worker.stop()
        if camera is not None:
            camera.stop()


if __name__ == "__main__":
    sys.exit(main())
