"""
Builds a 15 s, 1080 × 1920 Facebook Story promo (H.264 MP4) from the app's own renders and logo.

    venv\\Scripts\\python marketing\\render_assets.py          (once, or after UI changes)
    venv\\Scripts\\python marketing\\make_story.py [ffmpeg.exe]

Needs an ffmpeg executable: pass its path, or have `imageio-ffmpeg` importable.
Writes marketing/21vision_story.mp4.
"""
import math
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QRadialGradient  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui import theme as t  # noqa: E402

W, H, FPS, SECONDS = 1080, 1920, 30, 15.0
SAFE_TOP, SAFE_BOTTOM = 250, H - 250          # Facebook overlays the profile name and reply bar outside this
ASSETS = os.path.join(ROOT, "marketing", "assets")
OUT = os.path.join(ROOT, "marketing", "21vision_story.mp4")
PREVIEW_DIR = os.environ.get("STORY_PREVIEW_DIR")   # set to save a still every 0.5 s for review

CTA = "Message us to learn more"
FINE_PRINT = "21+ only · Play responsibly · Results are not guaranteed"


# ---------- easing / helpers ----------

def clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def ease(x):
    """Ease-out cubic on 0..1."""
    x = clamp(x)
    return 1 - (1 - x) ** 3


def progress(time, start, duration):
    return clamp((time - start) / duration)


def scene_alpha(time, start, end, fade=0.3):
    """Opacity of a scene: fades in at `start`, out at `end`."""
    return clamp(min((time - start) / fade, (end - time) / fade))


def font(size, weight=700, family=t.CONDENSED, spacing=0.0):
    f = t.font(size, weight, family, spacing)
    f.setFamilies([family, "Segoe UI Symbol", "Bahnschrift"])   # ♥ ♦ ♣ ♠ and ₱ come from Windows fonts
    return f


def text(p, rect, string, size, color, weight=700, family=t.CONDENSED, align=Qt.AlignmentFlag.AlignCenter, spacing=0.0):
    p.setFont(font(size, weight, family, spacing))
    p.setPen(QColor(color))
    p.drawText(rect, align, string)


def load(name):
    image = QImage(os.path.join(ASSETS, name))
    if image.isNull():
        sys.exit(f"Missing {name}: run marketing/render_assets.py first")
    return image


def draw_image(p, image, x, y, width, source=None, opacity=1.0, radius=18, border=None):
    source = source or QRectF(0, 0, image.width(), image.height())
    height = width * source.height() / source.width()
    target = QRectF(x, y, width, height)
    p.save()
    p.setOpacity(p.opacity() * opacity)
    path = QPainterPath()
    path.addRoundedRect(target, radius, radius)
    p.setClipPath(path)
    p.drawImage(target, image, source)
    p.restore()
    if border:
        p.save()
        p.setOpacity(p.opacity() * opacity)
        p.setPen(QPen(QColor(border), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(target, radius, radius)
        p.restore()
    return target


def glow(p, center, radius, color, strength=90):
    grad = QRadialGradient(center, radius)
    c = QColor(color)
    c.setAlpha(strength)
    grad.setColorAt(0, c)
    c.setAlpha(0)
    grad.setColorAt(1, c)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(grad)
    p.drawEllipse(center, radius, radius)


def neon_rect(p, rect, color, width=5, radius=16, alpha=1.0):
    p.save()
    p.setOpacity(p.opacity() * alpha)
    for w, a in ((width + 14, 40), (width + 6, 90), (width, 255)):
        c = QColor(color)
        c.setAlpha(a)
        p.setPen(QPen(c, w))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(rect, radius, radius)
    p.restore()


def caption(p, string, y=SAFE_TOP + 40, size=74, color=t.TEXT, opacity=1.0):
    p.save()
    p.setOpacity(p.opacity() * opacity)
    text(p, QRectF(60, y, W - 120, 170), string, size, color, spacing=0.01)
    p.restore()


# ---------- scenes ----------

def draw_background(p, time):
    p.fillRect(0, 0, W, H, QColor(t.WINDOW))
    # slow drifting neon glows
    glow(p, QPointF(W * 0.2 + 60 * math.sin(time * 0.6), H * 0.28), 620, t.PLUS, 38)
    glow(p, QPointF(W * 0.85, H * 0.72 + 80 * math.cos(time * 0.5)), 700, t.DEVIATION, 34)
    # faint grid
    p.setPen(QPen(QColor(255, 255, 255, 10), 1))
    for x in range(0, W, 90):
        p.drawLine(x, 0, x, H)
    for y in range(0, H, 90):
        p.drawLine(0, y, W, y)


def scene_logo(p, time, a, logo):
    """0-2.2 s: logo lights up, name appears."""
    p.save()
    p.setOpacity(a)
    grow = ease(progress(time, 0.0, 0.9))
    size = 420 + 140 * grow
    glow(p, QPointF(W / 2, 760), 420 * grow + 1, t.PLUS, 110)
    p.drawImage(QRectF(W / 2 - size / 2, 760 - size / 2, size, size), logo)
    name = ease(progress(time, 0.7, 0.6))
    p.setOpacity(a * name)
    text(p, QRectF(0, 1080 + 40 * (1 - name), W, 180), "21 Vision", 150, t.TEXT, spacing=0.02)
    text(p, QRectF(0, 1250 + 40 * (1 - name), W, 90), "AI CARD COUNTER", 54, t.PLUS, 600, t.UI, spacing=0.18)
    p.restore()


CARDS = [("4", "♦", t.MINUS, "+1", t.PLUS), ("6", "♣", "#1B1F27", "+1", t.PLUS), ("9", "♥", t.MINUS, "0", t.TEXT)]


def draw_card(p, center, rank, suit, ink, tilt):
    p.save()
    p.translate(center)
    p.rotate(tilt)
    rect = QRectF(-150, -210, 300, 420)
    p.setPen(QPen(QColor("#D9DEE6"), 3))
    p.setBrush(QColor("#FBFBF8"))
    p.drawRoundedRect(rect, 22, 22)
    text(p, QRectF(-135, -200, 110, 110), rank, 96, ink, 700)
    text(p, QRectF(-135, -105, 110, 90), suit, 70, ink, 400, t.UI)
    text(p, QRectF(-100, -80, 200, 200), suit, 170, ink, 400, t.UI)
    p.restore()


def scene_counting(p, time, a):
    """2.0-5.4 s: cards drop into the neon counting zone, each tagged +1 / 0 / −1."""
    p.save()
    p.setOpacity(a)
    caption(p, "Counts every card, live")
    zone = QRectF(W / 2 - 250, 820, 500, 560)
    neon_rect(p, zone, "#FFE24A", 5, 26)
    text(p, QRectF(zone.x(), zone.bottom() + 20, zone.width(), 60), "COUNTING ZONE", 34, "#FFE24A", 700, t.UI, spacing=0.2)

    running = 0
    for i, (rank, suit, ink, tag, tag_color) in enumerate(CARDS):
        land = 2.35 + i * 0.95
        k = ease(progress(time, land - 0.45, 0.45))
        if k <= 0:
            continue
        leaving = ease(progress(time, land + 0.6, 0.35)) if i < len(CARDS) - 1 else 0.0
        x = W / 2 + leaving * 700
        y = 300 + (zone.center().y() - 300) * k
        draw_card(p, QPointF(x, y), rank, suit, ink, (1 - k) * -14 + leaving * 18)
        if time >= land:
            running += int(tag.replace("+", "")) if tag != "0" else 0
            pop = ease(progress(time, land, 0.25))
            badge = QRectF(x + 90, y - 250, 150 * pop + 1, 96 * pop + 1)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(tag_color))
            p.drawRoundedRect(badge, 18, 18)
            text(p, badge, tag, 70 * pop + 1, t.WINDOW)

    # running count readout
    label = QRectF(0, 1520, W, 70)
    text(p, label, "RUNNING COUNT", 38, t.TEXT_2, 600, t.UI, spacing=0.14)
    text(p, QRectF(0, 1580, W, 150), t.signed(running), 150, t.count_color(running))
    p.restore()


def scene_app(p, time, a, main_img):
    """5.2-8.6 s: the real app; highlights on the counts, then the bet."""
    p.save()
    p.setOpacity(a)
    caption(p, "Live count, true count & bet", size=68)
    slide = ease(progress(time, 5.2, 0.5))
    width = 800
    x = (W - width) / 2
    y = 470 + 120 * (1 - slide)
    top = QRectF(0, 0, main_img.width(), 1140)   # title bar to hand buttons; the advice gets its own scene
    frame = draw_image(p, main_img, x, y, width, source=top, radius=22, border=t.LINE_STRONG)
    s = width / main_img.width()          # asset pixels -> screen
    counts = QRectF(frame.x() + 26 * s, frame.y() + 162 * s, 842 * s, 284 * s)
    bet = QRectF(frame.x() + 572 * s, frame.y() + 170 * s, 290 * s, 270 * s)
    if time > 6.0:
        neon_rect(p, counts, t.PLUS, 5, 14, ease(progress(time, 6.0, 0.3)) * (1 - ease(progress(time, 7.1, 0.3))))
    if time > 7.2:
        neon_rect(p, bet, t.PLUS, 5, 14, ease(progress(time, 7.2, 0.3)))
        text(p, QRectF(0, frame.bottom() + 20, W, 90), "Bet suggestion from the true count", 44, t.PLUS, 600, t.UI)
    p.restore()


def scene_advice(p, time, a, basic_img, dev_img):
    """8.4-11.4 s: advice card switches from basic strategy to a deviation."""
    p.save()
    p.setOpacity(a)
    caption(p, "Basic strategy + deviations", size=68)
    advice = QRectF(22, 1152, 848, 412)          # advice panel in the 2x Main render
    hand = QRectF(22, 656, 848, 490)             # upcard + hand buttons
    width = 940
    x = (W - width) / 2
    swap = ease(progress(time, 9.7, 0.35))
    draw_image(p, basic_img, x, 470, width, source=hand, opacity=1 - swap, radius=18)
    draw_image(p, dev_img, x, 470, width, source=hand, opacity=swap, radius=18)
    y = 470 + width * hand.height() / hand.width() + 40
    draw_image(p, basic_img, x, y, width, source=advice, opacity=1 - swap, radius=18)
    draw_image(p, dev_img, x, y, width, source=advice, opacity=swap, radius=18)
    if swap > 0:
        text(p, QRectF(0, y + width * advice.height() / advice.width() + 30, W, 90),
             "Deviates when the true count says so", 44, t.DEVIATION, 600, t.UI)
    p.restore()


def scene_tools(p, time, a, charts_img, spread_img):
    """11.2-13.4 s: charts and the bet spread calculator."""
    p.save()
    p.setOpacity(a)
    caption(p, "Built-in charts & bet calculator", size=64)
    width = 960
    x = (W - width) / 2
    k1 = ease(progress(time, 11.3, 0.45))
    k2 = ease(progress(time, 11.8, 0.45))
    charts = QRectF(248, 525, 1726, 853)         # pair-splitting table with T,T indices in the 2x Deviations render
    spread = QRectF(0, 140, 2240, 1450)          # calculator panels + ramp + results
    draw_image(p, charts_img, x - 300 * (1 - k1), 470, width, source=charts, opacity=k1, border=t.LINE_STRONG)
    draw_image(p, spread_img, x + 300 * (1 - k2), 470 + width * charts.height() / charts.width() + 40, width,
               source=spread, opacity=k2, border=t.LINE_STRONG)
    p.restore()


def scene_end(p, time, a, logo):
    """13.2-15 s: logo, call to action, fine print."""
    p.save()
    p.setOpacity(a)
    k = ease(progress(time, 13.2, 0.6))
    glow(p, QPointF(W / 2, 700), 380 * k + 1, t.PLUS, 100)
    p.drawImage(QRectF(W / 2 - 200, 500, 400, 400), logo)
    text(p, QRectF(0, 940, W, 160), "21 Vision", 130, t.TEXT, spacing=0.02)
    text(p, QRectF(0, 1090, W, 80), "AI CARD COUNTER", 48, t.PLUS, 600, t.UI, spacing=0.18)
    pill = QRectF(W / 2 - 400, 1260, 800, 130)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(t.PLUS))
    p.drawRoundedRect(pill, 65, 65)
    text(p, pill, CTA, 52, t.WINDOW, 700, t.UI)
    text(p, QRectF(60, SAFE_BOTTOM - 110, W - 120, 60), FINE_PRINT, 32, t.TEXT_2, 500, t.UI)
    p.restore()


# ---------- render ----------

def main():
    app = QApplication([])
    t.load_fonts()
    logo = QImage(os.path.join(ROOT, "ui", "icons", "21vision-512.png"))
    main_img, basic_img = load("main_deviation.png"), load("main_basic.png")
    charts_img, spread_img = load("tab_deviations.png"), load("tab_spread.png")

    ffmpeg = sys.argv[1] if len(sys.argv) > 1 else None
    if ffmpeg is None:
        import imageio_ffmpeg
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

    encoder = subprocess.Popen(
        [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
         "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", OUT],
        stdin=subprocess.PIPE,
    )

    frames = int(SECONDS * FPS)
    for i in range(frames):
        time = i / FPS
        image = QImage(W, H, QImage.Format.Format_RGB888)
        p = QPainter(image)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
                         | QPainter.RenderHint.TextAntialiasing)
        draw_background(p, time)
        for start, end, draw in (
            (0.0, 2.2, lambda a: scene_logo(p, time, a, logo)),
            (2.0, 5.4, lambda a: scene_counting(p, time, a)),
            (5.2, 8.6, lambda a: scene_app(p, time, a, main_img)),
            (8.4, 11.4, lambda a: scene_advice(p, time, a, basic_img, main_img)),
            (11.2, 13.4, lambda a: scene_tools(p, time, a, charts_img, spread_img)),
            (13.2, 15.3, lambda a: scene_end(p, time, a, logo)),
        ):
            alpha = scene_alpha(time, start, end) if start > 0 else clamp((end - time) / 0.3)
            if alpha > 0:
                draw(alpha)
        p.end()
        encoder.stdin.write(bytes(image.constBits())[: W * H * 3])
        if PREVIEW_DIR and i % 15 == 0:
            image.save(os.path.join(PREVIEW_DIR, f"{i / FPS:04.1f}s.png"))

    encoder.stdin.close()
    encoder.wait()
    print(f"wrote {OUT} ({frames} frames, {SECONDS:.0f} s, {W}x{H})")


if __name__ == "__main__":
    main()
