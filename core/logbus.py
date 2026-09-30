"""Program log: printed to the console and forwarded to the Program Logs window."""
import time

from PySide6.QtCore import QObject, Signal


class LogBus(QObject):
    # time, level (SYSTEM / DECISION / WARNING / ERROR), message
    message = Signal(str, str, str)


bus = LogBus()


def log(level, text):
    stamp = time.strftime("%H:%M:%S")
    try:
        print(f"{stamp} [{level}] {text}", flush=True)
    except UnicodeEncodeError:
        print(f"{stamp} [{level}] {text.encode('ascii', 'replace').decode()}", flush=True)
    # Qt queues this across threads, so the capture thread can log safely
    bus.message.emit(stamp, level, text)
