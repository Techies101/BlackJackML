"""
Renders the app's screens at 2x for the promo video (marketing/make_story.py).

Uses the real UI with example data (no capture, no casino footage):
    venv\\Scripts\\python marketing\\render_assets.py
Writes PNGs to marketing/assets/.
"""
import os
import sys

os.environ["QT_SCALE_FACTOR"] = "2"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "marketing", "assets")
os.makedirs(OUT, exist_ok=True)

from PySide6.QtCore import QObject, QRect, Signal  # noqa: E402
from PySide6.QtGui import QImage  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from core import settings as settings_store  # noqa: E402
from core.counter import ShoeCounter  # noqa: E402
from core.strategy import Strategy  # noqa: E402
from ui import theme  # noqa: E402
from ui.logs_window import LogsWindow  # noqa: E402
from ui.main_window import MainWindow  # noqa: E402


class DemoWorker(QObject):
    frame_ready = Signal(QImage)
    ready = Signal(str)
    failed = Signal(str)
    capturing = True
    fps = 38.0
    show_feed = False

    def set_capturing(self, on):
        self.capturing = on

    def set_zone(self, zone):
        pass


app = QApplication([])
theme.load_fonts()
app.setFont(theme.font(13))
app.setStyleSheet(theme.STYLESHEET)

settings = settings_store.load()
settings.update(feed_visible=False, shoe_decks=8, behind_cut=2.0)
counter = ShoeCounter()
window = MainWindow(DemoWorker(), counter, Strategy(), settings, LogsWindow(), "dxcam")
window.capture_rect = lambda: QRect(-5000, -5000, 10, 10)   # no overlap banner in the renders
window.show()
window.worker.ready.emit("TensorRT fp32")


def set_count(running, dealt, last="Q (−1) · YOLO + verifier agree"):
    counter.new_shoe()
    for _ in range(dealt - 1):
        counter.add_card("8", "8")
    counter.add_card("Q", last)
    counter.adjust(running + 1)


def set_hand(up, kind, value):
    tab = window.main_tab
    tab.type_seg.select(kind)
    tab._set_type(kind)
    tab.upcards.select(up)
    tab.values.select(value)
    tab.hand.update(up=up, val=value)


def save(name):
    window.refresh(force=True)
    app.processEvents()
    window.grab().save(os.path.join(OUT, name))
    print("saved", name)


window._select_tab(0)
set_count(0, 0)
window.main_tab.clear_hand()
save("main_idle.png")

set_count(2, 154)
set_hand("10", "hard", 15)
save("main_basic.png")

set_count(7, 258)
set_hand("3", "hard", 12)
save("main_deviation.png")

set_count(10, 264)
set_hand("A", "hard", 11)
save("main_insurance.png")

window._select_tab(1)
save("tab_basic.png")
window._select_tab(2)
save("tab_deviations.png")
window._select_tab(3)
save("tab_spread.png")
