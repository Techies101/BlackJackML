"""Main window: title bar, tabs, overlap warning, the four tab pages and the status bar."""
from PySide6.QtCore import QRect, QTimer, Qt
from PySide6.QtWidgets import QFrame, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from core import config, settings as settings_store
from core.logbus import log
from ui import theme as t
from ui.burn_popup import BurnPopup
from ui.chart_tab import ChartTab
from ui.main_tab import MainTab
from ui.region_picker import RegionPicker, screen_scale
from ui.spread_tab import SpreadTab
from ui.widgets import Badge, Button, Dot, Pill, TitleBar, hbox, install_screen_guard, label

WIDTH = 1120
COMPACT_WIDTH = 446   # Main tab with the live feed hidden: 12 + 420 + 12 + border
COMPACT_BODY_HEIGHT = 760   # the controls move under the left panel, so it needs a little more height
BODY_HEIGHT = 700
BANNER_HEIGHT = 36


class MainWindow(QWidget):

    def __init__(self, worker, counter, strategy, settings, logs_window, capture_method):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("21 Vision: AI Card Counter")
        self.worker, self.counter, self.strategy, self.settings = worker, counter, strategy, settings
        self.logs_window = logs_window
        self.capture_method = capture_method
        self.model_text = None
        self.ready = False
        self.warning_dismissed = False
        self.overlapping = set()

        frame = QFrame(self)
        frame.setObjectName("mainframe")
        frame.setStyleSheet(f"QFrame#mainframe {{ background: {t.WINDOW}; border: 1px solid {t.LINE_STRONG}; }}")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        root = QVBoxLayout(frame)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        self.setWindowIcon(t.app_icon())
        root.addWidget(TitleBar(self, "21 Vision: AI Card Counter", icon=t.app_icon()))
        root.addWidget(self._build_tabs())
        root.addWidget(self._build_banner())

        self.main_tab = MainTab(strategy)
        self.basic_tab = ChartTab(strategy, deviations=False)
        self.dev_tab = ChartTab(strategy, deviations=True)
        self.spread_tab = SpreadTab(settings)
        self.pages = QStackedWidget()
        self.pages.setFixedHeight(BODY_HEIGHT)
        for page in (self.main_tab, self.basic_tab, self.dev_tab, self.spread_tab):
            self.pages.addWidget(page)
        root.addWidget(self.pages)
        root.addWidget(self._build_status())

        self._connect()
        self._select_tab(0)
        self.set_feed_visible(settings.get("feed_visible", True), announce=False)

        self._screen_guard = install_screen_guard(self)
        self._save_timer = QTimer(self, singleShot=True, interval=800)
        self._save_timer.timeout.connect(self.save_settings)

        self._last_tc = None
        self._refresh_timer = QTimer(self, interval=100)
        self._refresh_timer.timeout.connect(self.refresh)
        self._refresh_timer.start()
        self.refresh()

    # ---------- building ----------

    def _build_tabs(self):
        bar = QFrame()
        bar.setObjectName("tabbar")
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"QFrame#tabbar {{ background: {t.CHROME}; border-bottom: 1px solid {t.LINE}; }}")
        self.tab_buttons = []
        items = []
        for i, name in enumerate(("Main", "Basic Strategy", "Deviations", "Bet Spread")):
            button = QPushButton(name.upper())
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFont(t.font(13, 600, spacing=0.06))
            button.setFixedHeight(38)
            button.clicked.connect(lambda _=False, i=i: self._select_tab(i))
            self.tab_buttons.append(button)
            items.append(button)
        self.area_button = Button("Capture area", height=24, size=12)
        self.area_button.setToolTip("Move the 640 × 640 area of the screen that is captured")
        self.area_button.clicked.connect(self.pick_capture_area)
        self.feed_button = Button("", height=24, size=12)
        self.feed_button.clicked.connect(lambda: self.set_feed_visible(not self.settings.get("feed_visible", True)))
        self.pill = Pill()
        right = hbox(self.feed_button, self.area_button, self.pill, spacing=8)
        bar.setLayout(hbox(*items, "stretch", right, spacing=0, margins=(8, 0, 8, 0)))
        return bar

    def _build_banner(self):
        self.banner = QFrame()
        self.banner.setObjectName("banner")
        self.banner.setFixedHeight(BANNER_HEIGHT)
        self.banner.setStyleSheet(f"QFrame#banner {{ background: {t.WARNING_BG}; border-bottom: 1px solid {t.WARNING}; }}")
        self.banner_text = label("", 13, 500, t.WARNING_TEXT)
        dismiss = QPushButton("Dismiss")
        dismiss.setCursor(Qt.CursorShape.PointingHandCursor)
        dismiss.setFont(t.font(12, 600))
        dismiss.setStyleSheet(f"QPushButton {{ color: {t.WARNING}; background: transparent; border: none; }}")
        dismiss.clicked.connect(self._dismiss_warning)
        self.banner.setLayout(hbox(Badge("WARNING", t.WINDOW, t.WARNING, t.WARNING, spacing=0.08), self.banner_text,
                                   "stretch", dismiss, spacing=10, margins=(14, 0, 14, 0)))
        self.banner.hide()
        return self.banner

    def _build_status(self):
        bar = QFrame()
        bar.setObjectName("statusbar")
        bar.setFixedHeight(24)
        bar.setStyleSheet(f"QFrame#statusbar {{ background: {t.CHROME}; border-top: 1px solid {t.LINE_SOFT}; }}")
        self.status_dot = Dot(t.TEXT_3)
        self.status_text = label("", 12, 400, t.TEXT_2)
        self.rules_text = label("8 decks · S17 · DAS · LS · Hi-Lo", 12, 400, t.TEXT_3)
        bar.setLayout(hbox(self.status_dot, self.status_text, "stretch", self.rules_text, spacing=7, margins=(12, 0, 12, 0)))
        return bar

    def _connect(self):
        m = self.main_tab
        m.set_shoe_inputs(self.settings["shoe_decks"], self.settings["behind_cut"])
        m.capture_toggled.connect(self.toggle_capture)
        m.new_shoe.connect(self.new_shoe)
        m.undo.connect(self.undo)
        m.adjust.connect(self.adjust)
        self.burn_popup = BurnPopup(self.counter)
        self.burn_popup.changed.connect(lambda: self.refresh(force=True))
        m.burn_clicked.connect(lambda: self.burn_popup.open_at(m.burn_button))
        m.feed.set_zone(self.settings["zone"])
        m.feed.zone_changed.connect(self.zone_changed)
        self.region_picker = RegionPicker()
        self.region_picker.applied.connect(self.capture_area_changed)
        m.shoe_changed.connect(self.shoe_changed)
        m.hand_changed.connect(lambda _: self.refresh(force=True))
        self.spread_tab.changed.connect(self.settings_changed)

        self.worker.frame_ready.connect(m.feed.set_image)
        self.worker.ready.connect(self.model_ready)
        self.worker.failed.connect(self.model_failed)

    # ---------- actions ----------

    def _select_tab(self, index):
        self.pages.setCurrentIndex(index)
        self._style_tabs()
        if hasattr(self, "banner"):
            self._resize()

    def compact(self):
        """Narrow window: feed hidden and the Main tab showing (other tabs need the full width)."""
        return not self.settings.get("feed_visible", True) and self.pages.currentIndex() == 0

    def _style_tabs(self):
        compact = self.compact()
        names = ("Main", "Basic", "Deviations", "Spread") if compact else ("Main", "Basic Strategy", "Deviations", "Bet Spread")
        for i, (button, name) in enumerate(zip(self.tab_buttons, names)):
            on = i == self.pages.currentIndex()
            button.setText(name.upper())
            button.setStyleSheet(
                f"QPushButton {{ color: {t.TEXT if on else t.TEXT_2}; background: transparent; border: none;"
                f" border-bottom: 2px solid {t.SELECT if on else 'transparent'}; padding: 0 {8 if compact else 16}px; }}"
                f"QPushButton:hover {{ color: {t.TEXT}; }}"
            )
        shown = self.settings.get("feed_visible", True)
        self.feed_button.setText("Feed" if compact else ("Hide feed" if shown else "Show feed"))
        self.feed_button.setToolTip("Hide the live feed (compact window, less work for the UI)" if shown
                                    else "Show the live feed")
        self.area_button.setText("Area" if compact else "Capture area")
        self.pill.setVisible(not compact)       # the status bar still shows the live dot and FPS
        self.rules_text.setVisible(not compact)

    def set_feed_visible(self, visible, announce=True):
        self.settings["feed_visible"] = visible
        self.worker.show_feed = visible
        self.main_tab.set_compact(not visible)
        if not visible:
            self.main_tab.feed.set_placeholder("FEED HIDDEN", "Counting continues in the background")
        elif not self.worker.capturing:
            self.main_tab.feed.set_placeholder("CAPTURE STOPPED", "Press Start capture to stream the 640 × 640 region")
        self._style_tabs()
        self._resize()
        if announce:
            log("SYSTEM", "Live feed shown." if visible else "Live feed hidden; counting continues.")
            self._save_timer.start()

    def model_ready(self, model_text):
        self.ready, self.model_text = True, model_text
        self.main_tab.feed.set_placeholder("CAPTURE STOPPED", "Press Start capture to stream the 640 × 640 region")
        self.refresh(force=True)

    def model_failed(self, error):
        self.main_tab.feed.set_placeholder("STARTUP FAILED", error[:90])
        self.status_text.setText(f"Startup failed: {error}")

    def toggle_capture(self):
        on = not self.worker.capturing
        self.worker.set_capturing(on)
        if not on:
            self.main_tab.feed.set_placeholder("CAPTURE STOPPED", "Press Start capture to stream the 640 × 640 region")
        log("SYSTEM", "Capture started." if on else "Capture stopped.")
        self.refresh(force=True)

    def new_shoe(self):
        self.counter.new_shoe()
        log("SYSTEM", "New shoe: count reset to 0.")
        self.refresh(force=True)

    def undo(self):
        undone = self.counter.undo()
        log("SYSTEM", f"Undid: {undone['text']}" if undone else "Nothing to undo.")
        if self.burn_popup.isVisible():
            self.burn_popup.refresh()
        self.refresh(force=True)

    def adjust(self, delta):
        self.counter.adjust(delta)
        log("SYSTEM", f"Running count corrected by {delta:+d}.")
        self.refresh(force=True)

    def shoe_changed(self, decks, behind):
        self.settings["shoe_decks"] = int(decks)
        self.settings["behind_cut"] = min(behind, decks - 0.5)
        self.spread_tab.shoe_updated()
        self.settings_changed()

    def zone_changed(self, zone):
        self.settings["zone"] = list(zone)
        self.worker.set_zone(zone)
        log("SYSTEM", f"Counting zone moved to x {zone[0]}–{zone[2]}, y {zone[1]}–{zone[3]}")
        self._save_timer.start()

    def pick_capture_area(self):
        left, top = self.settings["capture_region"]
        self.region_picker.open(left, top, tuple(self.settings["zone"]))

    def capture_area_changed(self, left, top):
        self.settings["capture_region"] = [left, top]
        self.worker.set_region(left, top)
        self._save_timer.start()
        self.check_overlap()

    def capture_rect(self):
        """Current capture area in Qt (logical) screen coordinates."""
        scale = screen_scale()
        left, top = self.settings["capture_region"]
        size = round(config.FRAME_SIZE / scale)
        return QRect(round(left / scale), round(top / scale), size, size)

    def settings_changed(self):
        self.main_tab.set_shoe_inputs(self.settings["shoe_decks"], self.settings["behind_cut"])
        self._save_timer.start()
        self.refresh(force=True)

    def save_settings(self):
        self.settings["window"] = [self.x(), self.y()]
        self.settings["logs_window"] = [self.logs_window.x(), self.logs_window.y()]
        self.settings["logs_size"] = [self.logs_window.width(), self.logs_window.height()]
        settings_store.save(self.settings)

    # ---------- periodic refresh ----------

    def refresh(self, force=False):
        snap = self.counter.snapshot(self.settings["shoe_decks"])
        self.main_tab.refresh(snap, self.settings)

        position = None
        h = self.main_tab.hand
        if h["up"] and h["val"] is not None:
            position = self.strategy.position(h["type"], h["val"], h["up"])
        key = (position and tuple(position.values()), snap["tc_int"], snap["running_count"] > 0, snap["running_count"] < 0)
        if force or key != self._last_tc:
            self._last_tc = key
            self.basic_tab.refresh(position, snap["tc_int"], snap["running_count"])
            self.dev_tab.refresh(position, snap["tc_int"], snap["running_count"])
            self.spread_tab.refresh_live(snap["tc_int"])

        capturing = self.worker.capturing
        self.main_tab.set_capture_state(capturing, self.ready)
        model = self.model_text or "loading model…"
        if capturing:
            self.pill.set_state("LIVE", t.PLUS, t.PLUS_BORDER)
            self.status_dot.set_color(t.PLUS)
            self.status_text.setText(f"{self.capture_method} · {model} · {self.worker.fps:.0f} FPS")
        else:
            self.pill.set_state("STOPPED" if self.ready else "LOADING", t.TEXT_3, t.LINE_STRONG)
            self.status_dot.set_color(t.TEXT_3)
            self.status_text.setText(f"Capture stopped · {self.capture_method} · {model}")

        self.check_overlap()

    # ---------- capture-area overlap ----------

    def check_overlap(self):
        if not self.isVisible():
            return  # position is not final until the window is shown

        now = set()
        capture = self.capture_rect()
        if self.frameGeometry().intersects(capture):
            now.add("Main window")
        if self.logs_window.isVisible() and self.logs_window.frameGeometry().intersects(capture):
            now.add("Program Logs window")

        for name in now - self.overlapping:
            log("WARNING", f"{name} overlaps the capture area")
        if now and not self.overlapping:
            self.warning_dismissed = False
        self.overlapping = now

        show = bool(now) and not self.warning_dismissed
        if show:
            self.banner_text.setText(f"{' and '.join(sorted(now))} overlaps the capture area; move it so the game is not covered.")
        if show == self.banner.isHidden():
            self.banner.setVisible(show)
            self._resize()

    def _dismiss_warning(self):
        self.warning_dismissed = True
        self.banner.hide()
        self._resize()

    def _resize(self):
        # title 32 + tabs 38 + body + status 24 + 1 px border top and bottom = 796 (832 with the banner)
        body = COMPACT_BODY_HEIGHT if self.compact() else BODY_HEIGHT
        self.pages.setFixedHeight(body)
        self.setFixedSize(COMPACT_WIDTH if self.compact() else WIDTH,
                          32 + 38 + body + 24 + 2 + (0 if self.banner.isHidden() else BANNER_HEIGHT))

    def moveEvent(self, event):
        self.check_overlap()
        self._screen_guard.start()
        self._save_timer.start()

    def closeEvent(self, event):
        self._refresh_timer.stop()
        self.save_settings()
        self.logs_window.close()
        event.accept()
