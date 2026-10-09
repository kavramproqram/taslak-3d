#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MKJ Küp Çizim — Minecraft tarzı, sınırsıza yakın 3B küp çizim aracı
(PyQt5 + PyOpenGL).

KONTROLLER
  Sol tık / sürükle ... çiz (Ctrl basılıyken sil)
  Orta tuş sürükle .... döndür
  Shift + orta sürükle  kaydır (pan)
  Tekerlek ............ yakınlaş / uzaklaş
  Sağ tık ............. oluşturulmuş küplerin listesi
  Ctrl+Z / Ctrl+Y ..... geri al / yinele
  1 / 2 / 3 ........... Çiz / Sil / Boya aracı
  Home ................ kamerayı sıfırla

Yerleşik 3B şekiller:
  Küp, Silindir, Koni, Küre, Piramit.
  Dışarıdan nesne/mesh aktarımı yoktur.

Dosya biçimi: .mkj  (JSON, küpler + yerleşik temel şekiller)
"""
import os
import sys
import math
import json
import base64
import random
import uuid
import ctypes
import traceback
import zlib
import time
import re

_qpa = os.environ.get("QT_QPA_PLATFORM", "").lower()
if _qpa.startswith("xcb") or (not _qpa and os.environ.get("XDG_SESSION_TYPE", "").lower() != "wayland"):
    os.environ.setdefault("PYOPENGL_PLATFORM", "glx")

import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame,
    QDialog, QSlider, QLabel, QPushButton, QFileDialog, QMessageBox,
    QShortcut, QLineEdit, QMenu, QWidgetAction, QScrollArea, QOpenGLWidget,
    QCheckBox, QSizePolicy, QListWidget, QDoubleSpinBox, QFormLayout,
    QSpinBox, QComboBox
)
from PyQt5.QtGui import (
    QColor, QPainter, QPen, QImage, QKeySequence, QCursor, QIcon, QPixmap,
    QPolygonF, QBrush, QTransform, QSurfaceFormat, QPalette
)
from PyQt5.QtCore import (
    Qt, QPoint, QRect, QPointF, QByteArray, pyqtSignal, QTimer, QBuffer,
    QIODevice
)
from PyQt5.QtSvg import QSvgRenderer
from OpenGL import GL as gl

APP_NAME = "MKJ Küp Çizim"
CFG_DIR = os.path.join(os.path.expanduser("~"), ".config", "mkj-kup-cizim")
LIB_PATH = os.path.join(CFG_DIR, "kupler.json")
SETTINGS_PATH = os.path.join(CFG_DIR, "ayarlar.json")

TILE = 16
ATLAS = 2048
TPR = ATLAS // TILE
MAX_SLOTS = (TPR * TPR) // 6
CHUNK_BITS = 4

MENU_STYLE = ("QMenu { background-color: #333; color: white; border: 1px solid #555; } "
              "QMenu::item:selected { background-color: #555; } "
              "QMenu::item:disabled { color: #999; }")


# ----------------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------------
def create_svg_icon(svg_content, size=24, color="#eee"):
    modified = svg_content.replace('stroke="#eee"', f'stroke="{color}"').replace('fill="#eee"', f'fill="{color}"')
    renderer = QSvgRenderer(QByteArray(modified.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)


SVG_UNDO_ICON = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 19C15.866 19 19 15.866 19 12C19 8.13401 15.866 5 12 5C8.13401 5 5 8.13401 5 12C5 13.7909 5.70014 15.4293 6.84594 16.6386L5 18M5 18H9M5 18V14" stroke="#eee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
SVG_REDO_ICON = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M12 5C8.13401 5 5 8.13401 5 12C5 15.866 8.13401 19 12 19C15.866 19 19 15.866 19 12C19 10.2091 18.2999 8.57074 17.1541 7.3614L19 6M19 6H15M19 6V10" stroke="#eee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>"""
SVG_SAVE_ICON = """<svg width="24" height="24" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M17 3H5C3.89 3 3 3.9 3 5V19C3 20.1 3.89 21 5 21H19C20.1 21 21 20.1 21 19V7L17 3ZM12 17C10.34 17 9 15.66 9 14C9 12.34 10.34 11 12 11C13.66 11 15 12.34 15 14C15 15.66 13.66 17 12 17Z" stroke="#eee" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>"""


def btn_style(active=False, font=14):
    bg = "#555" if active else "transparent"
    hover = "#666" if active else "#444"
    return f"""
        QPushButton {{
            background-color: {bg};
            color: white;
            font-size: {font}px;
            font-weight: bold;
            border: 2px solid #555;
            border-radius: 8px;
            padding: 5px;
        }}
        QPushButton:hover {{
            background-color: {hover};
        }}
        QPushButton:pressed {{
            background-color: #777;
        }}
        QPushButton::menu-indicator {{
            image: none;
        }}
    """


# ----------------------------------------------------------------------------
# Karıştırma
# ----------------------------------------------------------------------------
MIX_MODES = [
    ("Random (Rastgele)", "random"),
    ("Sequential (Sıralı)", "sequential"),
    ("Gradient (Açısal)", "gradient"),
    ("Smooth (Pürüzsüz)", "smooth"),
    ("Harman (Doku)", "harman"),
    ("Gradyan Geçiş (Yumuşak)", "gradient_soft"),
    ("Mermer Efekti (Marble)", "marble"),
    ("Renk Serpiştirme (Splatter)", "splatter"),
    ("Dalgalı (Wave)", "wave"),
    ("Piksel Gürültüsü (Pixel)", "pixel"),
    ("Sünger (Sponge)", "sponge"),
    ("Dairesel (Radial)", "radial"),
    ("Puslu (Mist)", "mist"),
]
MIX_SHORT = {k: l.split(" (")[0] for l, k in MIX_MODES}


def mix_select(n, mode, x, y, step, angle, seq=0):
    if n <= 1:
        return 0, 0, 0.0

    def blend(p):
        s = max(0.0, min(1.0, p)) * (n - 1)
        i = int(s)
        return i, min(n - 1, i + 1), s - i

    if mode in ("random", "pixel"):
        i = random.randrange(n)
        return i, i, 0.0
    if mode == "sequential":
        i = int(seq) % n
        return i, i, 0.0
    if mode == "gradient":
        a = math.radians(angle)
        i = int(abs(x * math.cos(a) + y * math.sin(a)) / 100.0) % n
        return i, i, 0.0
    if mode == "smooth":
        pos = step / 200.0
        i = int(pos) % n
        return i, (i + 1) % n, pos - int(pos)
    if mode == "harman":
        f = 0.15
        nz = (math.sin(x * f) + math.cos(y * f) + math.sin((x + y) * f * 0.5)) / 3.0
        return blend((nz + 1.0) / 2.0 + random.uniform(-0.05, 0.05))
    if mode == "gradient_soft":
        return blend((step / 500.0) % 1.0)
    if mode == "marble":
        nz = math.sin(x * 0.03 + math.cos(y * 0.03)) + math.sin(y * 0.015)
        return blend((nz + 2.0) / 4.0)
    if mode == "splatter":
        i = random.randrange(n) if random.random() > 0.8 else 0
        return i, i, 0.0
    if mode == "wave":
        return blend((math.sin(step * 0.05) + 1.0) / 2.0)
    if mode == "sponge":
        i = ((int(x / 15) * 73856093) ^ (int(y / 15) * 19349663)) % n
        return i, i, 0.0
    if mode == "radial":
        return blend((math.hypot(x, y) / 300.0) % 1.0)
    if mode == "mist":
        nz = (math.sin(x * 0.08) * math.cos(y * 0.08) + 1.0) / 2.0 + random.uniform(-0.1, 0.1)
        return blend(nz)
    return 0, 0, 0.0


# ----------------------------------------------------------------------------
# Renk seçici bileşenleri
# ----------------------------------------------------------------------------
class ColorHistoryStrip(QWidget):
    colorSelected = pyqtSignal(object, object)

    def __init__(self, colors, parent=None):
        super().__init__(parent)
        self.colors = colors
        self.square_size = 24
        self.spacing = 6
        self.margin = 5
        self.cols_per_row = 4
        num_rows = max(1, (len(colors) + self.cols_per_row - 1) // self.cols_per_row)
        total_width = self.margin * 2 + self.cols_per_row * (self.square_size + self.spacing)
        total_height = self.margin * 2 + num_rows * (self.square_size + self.spacing)
        self.setFixedSize(max(150, total_width), total_height)
        self.setCursor(Qt.PointingHandCursor)
        self.hovered_index = -1
        self.is_pressed = False
        self.setMouseTracking(True)

    def _rect(self, i):
        row, col = divmod(i, self.cols_per_row)
        x = self.margin + col * (self.square_size + self.spacing)
        y = self.margin + row * (self.square_size + self.spacing)
        return QRect(x, y, self.square_size, self.square_size)

    def _index_at(self, pos):
        for i in range(len(self.colors)):
            if self._rect(i).contains(pos):
                return i
        return -1

    def leaveEvent(self, event):
        self.hovered_index = -1
        self.is_pressed = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self.underMouse():
            painter.fillRect(self.rect(), QColor(60, 60, 60))
        for i, color in enumerate(self.colors):
            painter.setBrush(QBrush(color))
            if i == self.hovered_index:
                painter.setPen(QPen(Qt.white, 2))
                if self.is_pressed:
                    painter.setBrush(QBrush(color.darker(120)))
            else:
                painter.setPen(QPen(Qt.gray, 1))
            painter.drawRoundedRect(self._rect(i), 4, 4)

    def mouseMoveEvent(self, event):
        old = self.hovered_index
        self.hovered_index = self._index_at(event.pos())
        if old != self.hovered_index:
            self.update()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            idx = self._index_at(event.pos())
            if idx >= 0:
                self.is_pressed = True
                self.update()
                self.colorSelected.emit(self.colors[idx], None)
            elif len(self.colors) == 1:
                self.colorSelected.emit(self.colors[0], None)
            else:
                self.colorSelected.emit(None, self.colors)
        elif event.button() == Qt.RightButton:
            self.showContextMenu(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.is_pressed = False
            self.update()
        super().mouseReleaseEvent(event)

    def showContextMenu(self, pos):
        idx = self._index_at(pos)
        if idx != -1:
            color = self.colors[idx]
            menu = QMenu(self)
            menu.setStyleSheet(MENU_STYLE)
            copy_hex = menu.addAction(f"Hex kopyala: {color.name().upper()}")
            if menu.exec_(self.mapToGlobal(pos)) == copy_hex:
                QApplication.clipboard().setText(color.name().upper())


class CircleBrightnessDialog(QDialog):
    def __init__(self, initialColor=QColor("white"), parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.hueSatDiameter = 150
        self.radius = self.hueSatDiameter // 2
        hF, sF, vF, _ = initialColor.getHsvF()
        self.h = max(0.0, hF) * 360.0
        self.s = sF
        self.v = vF
        self.setFixedSize(280, 280)

        self.colorWheel = QImage(self.hueSatDiameter, self.hueSatDiameter, QImage.Format_ARGB32)
        self._generateColorWheel()

        self.slider = QSlider(Qt.Vertical, self)
        self.slider.setRange(0, 100)
        self.slider.setValue(int(self.v * 100))
        self.slider.setGeometry(self.hueSatDiameter + 20, 10, 20, self.hueSatDiameter)
        self.slider.valueChanged.connect(self.onValueChanged)
        self._updateSliderStyle()

        self.preview_label = QLabel(self)
        self.preview_label.setGeometry(self.hueSatDiameter + 50, 35, 40, 40)
        self._updatePreviewColor()

        self.brightness_label = QLabel(self)
        self.brightness_label.setStyleSheet("color: white; background: transparent;")
        self.brightness_label.setGeometry(self.hueSatDiameter + 50, 10, 40, 20)
        self.brightness_label.setText(f"{int(self.v * 100)}%")

        self.hex_input = QLineEdit(self)
        self.hex_input.setGeometry(10, self.hueSatDiameter + 25, 105, 25)
        self.hex_input.setStyleSheet("""
            QLineEdit { background-color: #000000; color: #FFFFFF; border: 1px solid #444444; border-radius: 4px; padding: 2px 5px; font-family: Consolas, Monaco, monospace; font-size: 12px; }
            QLineEdit:focus { border: 1px solid #00FF00; }
        """)
        self.hex_input.setMaxLength(6)
        self.hex_input.setPlaceholderText("Hex Kodu")
        self.hex_input.textChanged.connect(self.onHexTextChanged)
        self.hex_input.returnPressed.connect(self.onHexEnterPressed)

        self.hex_ok_btn = QPushButton("OK", self)
        self.hex_ok_btn.setGeometry(120, self.hueSatDiameter + 25, 40, 25)
        self.hex_ok_btn.setStyleSheet("""
            QPushButton { background-color: #222; color: #FFFFFF; border: 1px solid #444; border-radius: 4px; font-family: Consolas, Monaco, monospace; font-size: 11px; font-weight: bold; }
            QPushButton:hover { background-color: #4CAF50; border: 1px solid #4CAF50; }
            QPushButton:pressed { background-color: #388E3C; }
        """)
        self.hex_ok_btn.clicked.connect(self.onHexEnterPressed)

        self.hex_label = QLabel(self)
        self.hex_label.setGeometry(165, self.hueSatDiameter + 25, 105, 25)
        self.hex_label.setStyleSheet("""
            QLabel { background-color: #000000; color: #FFFFFF; border: 1px solid #444444; border-radius: 4px; padding: 2px 5px; font-family: Consolas, Monaco, monospace; font-size: 12px; }
        """)
        self.hex_label.setAlignment(Qt.AlignCenter)

        self.done_btn = QPushButton("Tamam", self)
        self.done_btn.setGeometry(10, 225, 260, 32)
        self.done_btn.setStyleSheet("""
            QPushButton { background-color: #2e7d32; color: white; border: 1px solid #4CAF50; border-radius: 6px; font-size: 13px; font-weight: bold; }
            QPushButton:hover { background-color: #388E3C; }
        """)
        self.done_btn.clicked.connect(self.accept)

        self._updateHexFromColor()

    def _updateHexFromColor(self):
        color = QColor.fromHsvF(self.h / 360.0, self.s, self.v)
        hex_code = color.name().upper()[1:]
        self.hex_label.setText("#" + hex_code)
        self.hex_input.setText(hex_code)
        self._updateSliderStyle()
        self._updatePreviewColor()

    def _updateSliderStyle(self):
        hue_hex = QColor.fromHsvF(self.h / 360.0, 1.0, 1.0).name()
        self.slider.setStyleSheet(f"""
            QSlider::groove:vertical {{ border: none; width: 4px; background: qlineargradient(x1:0, y1:1, x2:0, y2:0, stop:0 #000000, stop:0.5 {hue_hex}, stop:1 #FFFFFF); margin: 0px; }}
            QSlider::handle:vertical {{ background: {hue_hex}; border: 2px solid #FFFFFF; width: 12px; height: 12px; margin: -6px 0; border-radius: 6px; }}
            QSlider::handle:vertical:hover {{ background: #FFFFFF; border: 2px solid {hue_hex}; }}
        """)

    def _updatePreviewColor(self):
        c = QColor.fromHsvF(self.h / 360.0, self.s, self.v)
        self.preview_label.setStyleSheet(
            f"QLabel {{ background-color: {c.name()}; border: 2px solid #FFFFFF; border-radius: 4px; }}")

    def onHexTextChanged(self, text):
        self.hex_input.blockSignals(True)
        clean = "".join(c for c in text.upper() if c in "0123456789ABCDEF")
        if clean != text:
            cursor = self.hex_input.cursorPosition()
            self.hex_input.setText(clean)
            self.hex_input.setCursorPosition(cursor)
        self.hex_input.blockSignals(False)

    def _applyHex(self, hex_text):
        color = QColor("#" + hex_text)
        if color.isValid():
            hF, sF, vF, _ = color.getHsvF()
            self.h = max(0.0, hF) * 360.0
            self.s = sF
            self.v = vF
            self.slider.blockSignals(True)
            self.slider.setValue(int(self.v * 100))
            self.slider.blockSignals(False)
            self.brightness_label.setText(f"{int(self.v * 100)}%")
            self.hex_input.blockSignals(True)
            self.hex_input.setText(hex_text.upper())
            self.hex_input.blockSignals(False)
            self.hex_label.setText("#" + hex_text.upper())
            self._updateSliderStyle()
            self._updatePreviewColor()
            self.update()

    def onHexEnterPressed(self):
        hex_text = self.hex_input.text().strip()
        if len(hex_text) == 6:
            self._applyHex(hex_text)

    def _handleCtrlV(self):
        text = QApplication.clipboard().text().strip().replace("#", "").upper()
        clean = "".join(c for c in text if c in "0123456789ABCDEF")
        if len(clean) == 6:
            self._applyHex(clean)

    def keyPressEvent(self, event):
        if event.modifiers() == Qt.ControlModifier and event.key() == Qt.Key_V:
            self._handleCtrlV()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.accept()
            return
        super().keyPressEvent(event)

    def _generateColorWheel(self):
        center = self.radius
        for y in range(self.hueSatDiameter):
            for x in range(self.hueSatDiameter):
                dx, dy = x - center, y - center
                r = math.sqrt(dx * dx + dy * dy)
                if r <= self.radius:
                    hue = (math.degrees(math.atan2(dy, dx)) + 360) % 360
                    self.colorWheel.setPixelColor(x, y, QColor.fromHsvF(hue / 360.0, r / self.radius, 1.0))
                else:
                    self.colorWheel.setPixelColor(x, y, QColor(0, 0, 0, 0))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30, 220))
        cx, cy = 10, 10
        painter.drawImage(cx, cy, self.colorWheel)
        hue_rad = math.radians(self.h)
        sat_r = self.s * self.radius
        sx = cx + self.radius + sat_r * math.cos(hue_rad)
        sy = cy + self.radius + sat_r * math.sin(hue_rad)
        painter.setPen(QPen(Qt.black, 2))
        painter.setBrush(Qt.white)
        painter.drawEllipse(QPoint(int(sx), int(sy)), 5, 5)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._pickHueSat(event.pos()):
                self.accept()
            else:
                self.update()
        else:
            self.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            if self._pickHueSat(event.pos()):
                self.update()

    def _pickHueSat(self, pos):
        x, y = pos.x() - 10, pos.y() - 10
        if 0 <= x < self.hueSatDiameter and 0 <= y < self.hueSatDiameter:
            dx, dy = x - self.radius, y - self.radius
            r = math.sqrt(dx * dx + dy * dy)
            if r <= self.radius:
                self.h = (math.degrees(math.atan2(dy, dx)) + 360) % 360
                self.s = r / self.radius
                self._updateHexFromColor()
                return True
        return False

    def onValueChanged(self, val):
        self.v = val / 100.0
        self.brightness_label.setText(f"{val}%")
        self._updateHexFromColor()
        self.update()

    def getSelectedColor(self):
        return QColor.fromHsvF(self.h / 360.0, self.s, self.v)


# ----------------------------------------------------------------------------
# Küp modeli
# ----------------------------------------------------------------------------
FACE_N = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
FACE_V = np.array([
    [(1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)],
    [(0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)],
    [(0, 1, 1), (1, 1, 1), (1, 1, 0), (0, 1, 0)],
    [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1)],
    [(0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)],
    [(1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)],
], dtype=np.float64)
FACE_UV = np.array([(0, 1), (1, 1), (1, 0), (0, 0)], dtype=np.float64)
FACE_SHADE = np.array([0.8, 0.8, 1.0, 0.5, 0.65, 0.65], dtype=np.float64)


def img_to_b64(img):
    img = img.convertToFormat(QImage.Format_RGBA8888)
    return base64.b64encode(img.constBits().asstring(img.sizeInBytes())).decode("ascii")


def b64_to_img(s):
    raw = base64.b64decode(s)
    if len(raw) != TILE * TILE * 4:
        raise ValueError("bozuk küp verisi")
    return QImage(raw, TILE, TILE, TILE * 4, QImage.Format_RGBA8888).copy()


def solid_image(color):
    img = QImage(TILE, TILE, QImage.Format_RGBA8888)
    img.fill(QColor(color))
    return img


class Cube:
    def __init__(self, cid, name, faces):
        self.id = cid
        self.name = name
        self.faces = faces

    @staticmethod
    def solid(cid, name, color):
        return Cube(cid, name, [solid_image(color) for _ in range(6)])

    def copy_faces(self):
        return [f.copy() for f in self.faces]

    def to_json(self):
        return {"name": self.name, "faces": [img_to_b64(f) for f in self.faces]}

    @staticmethod
    def from_json(cid, d):
        faces = [b64_to_img(s) for s in d["faces"]]
        if len(faces) != 6:
            raise ValueError("küp 6 yüzlü olmalı")
        return Cube(cid, str(d.get("name", "Küp")), faces)

    def same_as(self, other):
        return all(a == b for a, b in zip(self.faces, other.faces))


def iso_cube_pixmap(faces, size):
    """Statik izometrik küçük resim (liste için)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.SmoothPixmapTransform, False)
    a = size * 0.45
    h = a * 1.118
    cx = size / 2.0
    ty = (size - (a + h)) / 2.0
    e1 = (a, a / 2.0)
    e2 = (-a, a / 2.0)

    def face(img, ox, oy, u, v, dark):
        p.setTransform(QTransform(u[0] / TILE, u[1] / TILE, v[0] / TILE, v[1] / TILE, ox, oy))
        p.drawImage(0, 0, img)
        p.resetTransform()
        if dark:
            poly = QPolygonF([QPointF(ox, oy), QPointF(ox + u[0], oy + u[1]),
                              QPointF(ox + u[0] + v[0], oy + u[1] + v[1]), QPointF(ox + v[0], oy + v[1])])
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, dark))
            p.drawPolygon(poly)

    face(faces[2], cx, ty, e1, e2, 0)
    face(faces[4], cx + e2[0], ty + e2[1], e1, (0, h), 89)
    face(faces[0], cx + e1[0] + e2[0], ty + e1[1] + e2[1], (-e2[0], -e2[1]), (0, h), 51)
    pts = [(cx, ty), (cx + a, ty + a / 2), (cx + a, ty + a / 2 + h), (cx, ty + a + h),
           (cx - a, ty + a / 2 + h), (cx - a, ty + a / 2)]
    p.setPen(QPen(QColor(255, 255, 255, 90), 1))
    p.setBrush(Qt.NoBrush)
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in pts]))
    p.end()
    return pm


def mesh_thumb(obj, size):
    """İçe aktarılan mesh için küçük önizleme (basit projeksiyon + materyal/renk)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    if not obj.parts:
        p.end()
        return pm
    tris = []
    total = 0
    for part in obj.parts:
        arr = part.get("arr")
        if arr is None or len(arr) < 3:
            continue
        mi = int(part.get("material", 0))
        if 0 <= mi < len(obj.materials):
            mat = obj.materials[mi]
            if not mat.base_image.isNull():
                color = mat.base_image.pixelColor(mat.base_image.width() // 2, mat.base_image.height() // 2)
            else:
                color = mat.color()
        else:
            color = QColor("#888888")
        step = max(1, len(arr) // 3000)
        for i in range(0, len(arr) - 2, 3 * step):
            tri = arr[i:i+3, 0:3]
            if len(tri) < 3:
                continue
            pts = []
            depths = []
            for x, y, z in tri:
                xx = (float(x) - float(z)) * 0.7071
                yy = float(y) - (float(x) + float(z)) * 0.42
                zz = float(x) + float(y) + float(z)
                pts.append((xx, yy))
                depths.append(zz)
            tris.append((sum(depths) / 3.0, pts, QColor(color)))
            total += 1
            if total >= 3000:
                break
        if total >= 3000:
            break
    if not tris:
        p.end()
        return pm
    xs = [q[0] for _, pts, _ in tris for q in pts]
    ys = [q[1] for _, pts, _ in tris for q in pts]
    span = max(max(xs)-min(xs), max(ys)-min(ys), 1e-6)
    sc = (size - 8) / span
    ox = size * 0.5 - ((min(xs)+max(xs))*0.5)*sc
    oy = size * 0.5 - ((min(ys)+max(ys))*0.5)*sc
    for _, pts, color in sorted(tris, key=lambda q: q[0], reverse=True):
        poly = QPolygonF([QPointF(x*sc+ox, y*sc+oy) for x, y in pts])
        shade = max(45, min(255, int((color.red()+color.green()+color.blue())/3*0.82)))
        c = QColor(min(255, int(color.red()*0.82+shade*0.18)),
                   min(255, int(color.green()*0.82+shade*0.18)),
                   min(255, int(color.blue()*0.82+shade*0.18)),
                   color.alpha())
        p.setBrush(c)
        p.setPen(QPen(QColor(255, 255, 255, 70), 0.6))
        p.drawPolygon(poly)
    p.end()
    return pm


def ray_triangle(o, d, a, b, c, maxdist=float("inf")):
    e1 = b - a
    e2 = c - a
    h = np.cross(d, e2)
    det = float(np.dot(e1, h))
    if -1e-9 < det < 1e-9:
        return None
    inv = 1.0 / det
    s = o - a
    u = float(np.dot(s, h)) * inv
    if u < 0.0 or u > 1.0:
        return None
    q = np.cross(s, e1)
    v = float(np.dot(d, q)) * inv
    if v < 0.0 or u + v > 1.0:
        return None
    t = float(np.dot(e2, q)) * inv
    if t <= 1e-6 or t > maxdist:
        return None
    return t, u, v


def euler_mesh_matrix(position, rotation, scale):
    rx, ry, rz = [math.radians(float(v)) for v in rotation]
    sx, cx = math.sin(rx), math.cos(rx)
    sy, cy = math.sin(ry), math.cos(ry)
    sz, cz = math.sin(rz), math.cos(rz)
    Rz = np.array([[cz,-sz,0,0],[sz,cz,0,0],[0,0,1,0],[0,0,0,1]], dtype=np.float64)
    Rx = np.array([[1,0,0,0],[0,cx,-sx,0],[0,sx,cx,0],[0,0,0,1]], dtype=np.float64)
    Ry = np.array([[cy,0,sy,0],[0,1,0,0],[-sy,0,cy,0],[0,0,0,1]], dtype=np.float64)
    S = np.diag([float(scale[0]), float(scale[1]), float(scale[2]), 1.0])
    T = np.eye(4, dtype=np.float64)
    T[:3,3] = np.asarray(position, dtype=np.float64)
    return T @ Ry @ Rx @ Rz @ S


# ----------------------------------------------------------------------------
# Geometri yardımcıları (UV üretimi, kenarlar, ışın testleri)
# ----------------------------------------------------------------------------
def compute_tangents(pos, nrm, uv):
    """pos/nrm: (3T,3), uv: (3T,2) -> (3T,4) teğet (xyz + el yönü)."""
    T_ = len(pos) // 3
    if T_ == 0:
        return np.zeros((0, 4), np.float32)
    P = pos.reshape(T_, 3, 3).astype(np.float64)
    UV = uv.reshape(T_, 3, 2).astype(np.float64)
    N0 = nrm.reshape(T_, 3, 3)[:, 0].astype(np.float64)
    e1 = P[:, 1] - P[:, 0]
    e2 = P[:, 2] - P[:, 0]
    d1 = UV[:, 1] - UV[:, 0]
    d2 = UV[:, 2] - UV[:, 0]
    den = d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0]
    ok = np.abs(den) > 1e-12
    inv = np.zeros(T_)
    inv[ok] = 1.0 / den[ok]
    T = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) * inv[:, None]
    B = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) * inv[:, None]
    fb = np.zeros((T_, 3))
    use_x = np.abs(N0[:, 0]) < 0.9
    fb[use_x, 0] = 1.0
    fb[~use_x, 2] = 1.0
    T = np.where(ok[:, None], T, fb)
    hand = np.where((np.cross(N0, T) * B).sum(axis=1) < 0, -1.0, 1.0)
    hand = np.where(ok, hand, 1.0)
    out = np.concatenate([T, hand[:, None]], axis=1)
    out = np.nan_to_num(out, nan=0.0, posinf=0.0, neginf=0.0)
    return np.repeat(out, 3, axis=0).astype(np.float32)


def _components(n, a, b):
    if n == 0:
        return np.zeros(0, np.int64), 0
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(a)):
        ra, rb = find(int(a[i])), find(int(b[i]))
        if ra != rb:
            parent[rb] = ra
    roots = {}
    labels = np.empty(n, np.int64)
    for i in range(n):
        r = find(i)
        if r not in roots:
            roots[r] = len(roots)
        labels[i] = roots[r]
    return labels, len(roots)


def auto_unwrap(tri_pos, margin=2.5 / 1024.0):
    """Basit kutu-projeksiyonu + ada paketleme ile UV üretir.
    tri_pos: (3T, 3) üçgen köşeleri. Dönüş: (3T, 2) UV."""
    if len(tri_pos) == 0:
        return np.zeros((0, 2), np.float64)
    T_ = len(tri_pos) // 3
    P = tri_pos.reshape(T_, 3, 3)
    # Her üçgen için normal
    e1 = P[:, 1] - P[:, 0]
    e2 = P[:, 2] - P[:, 0]
    nrm = np.cross(e1, e2)
    ln = np.linalg.norm(nrm, axis=1)
    ln[ln < 1e-12] = 1.0
    nrm = nrm / ln[:, None]
    # En baskın eksen: kutu projeksiyonu
    ax = np.argmax(np.abs(nrm), axis=1)
    # Her üçgen için düzlemsel 2D koordinatlar
    uvs = np.zeros((T_, 3, 2), np.float64)
    signs = np.sign(nrm[np.arange(T_), ax])
    for i in range(T_):
        a = ax[i]
        if a == 0:
            u = P[i, :, 1] * signs[i]
            v = P[i, :, 2]
        elif a == 1:
            u = P[i, :, 0]
            v = P[i, :, 2] * signs[i]
        else:
            u = P[i, :, 0] * signs[i]
            v = P[i, :, 1]
        uvs[i, :, 0] = u
        uvs[i, :, 1] = v
    # Ada gruplaması: aynı yönde ve paylaşılan kenarlara sahip üçgenler
    edge_map = {}
    for ti in range(T_):
        for k in range(3):
            a = tuple(np.round(P[ti, k, :], 5))
            b = tuple(np.round(P[ti, (k + 1) % 3, :], 5))
            key = tuple(sorted([a, b]))
            edge_map.setdefault(key, []).append(ti)
    ea, eb = [], []
    for key, tris in edge_map.items():
        if len(tris) > 1:
            for i in range(len(tris)):
                for j in range(i + 1, len(tris)):
                    if ax[tris[i]] == ax[tris[j]]:
                        ea.append(tris[i])
                        eb.append(tris[j])
    labels, ncomp = _components(T_, ea, eb)
    # Ada bazlı bounding box ve paketleme (basit ızgara)
    islands = {}
    for ti in range(T_):
        islands.setdefault(int(labels[ti]), []).append(ti)
    # Paketleme: her adayı kareye sığdır
    items = []
    for isl, tris in islands.items():
        us = uvs[tris][:, :, 0]
        vs = uvs[tris][:, :, 1]
        umin, umax = float(us.min()), float(us.max())
        vmin, vmax = float(vs.min()), float(vs.max())
        w = max(umax - umin, 1e-6)
        h = max(vmax - vmin, 1e-6)
        items.append([isl, tris, umin, vmin, w, h])
    # Genişliğe göre azalan sırala, shelf paketleme
    items.sort(key=lambda q: q[4], reverse=True)
    total_area = sum(q[4] * q[5] for q in items)
    scale = 1.0 / math.sqrt(total_area) if total_area > 0 else 1.0
    # Basit bisection
    def pack(sc):
        x = y = margin
        row_h = 0.0
        placements = {}
        for isl, tris, umin, vmin, w, h in items:
            ww, hh = w * sc, h * sc
            if x + ww > 1.0 - margin:
                x = margin
                y += row_h + margin
                row_h = 0.0
            if y + hh > 1.0 - margin:
                return None
            placements[isl] = (x, y, umin, vmin, sc)
            x += ww + margin
            row_h = max(row_h, hh)
        return placements

    lo, hi = 0.0, 4.0
    best = pack(scale)
    for _ in range(40):
        mid = (lo + hi) * 0.5
        r = pack(mid)
        if r is not None:
            best = r
            lo = mid
        else:
            hi = mid
    if best is None:
        best = pack(scale * 0.2) or {}
    out = np.zeros((T_, 3, 2), np.float64)
    for isl, tris in islands.items():
        pl = best.get(isl)
        if pl is None:
            continue
        ox, oy, umin, vmin, sc = pl
        for ti in tris:
            out[ti, :, 0] = (uvs[ti, :, 0] - umin) * sc + ox
            out[ti, :, 1] = (uvs[ti, :, 1] - vmin) * sc + oy
    return out.reshape(-1, 2)


def uv_report(uv, grid=512, density=4.0):
    """UV sorun tespiti: taşma, dejenere, üst üste binme oranı."""
    rep = {"tris": len(uv) // 3, "has_uv": len(uv) > 0,
           "out_of_range": 0.0, "degenerate": 0.0, "overlap": 0.0, "text": ""}
    if len(uv) == 0:
        return rep
    T_ = len(uv) // 3
    UV = uv.reshape(T_, 3, 2)
    oor = 0
    degen = 0
    area = 0.0
    for i in range(T_):
        a, b, c = UV[i, 0], UV[i, 1], UV[i, 2]
        if min(a[0], b[0], c[0]) < -0.001 or max(a[0], b[0], c[0]) > 1.001 \
                or min(a[1], b[1], c[1]) < -0.001 or max(a[1], b[1], c[1]) > 1.001:
            oor += 1
        ar = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) * 0.5
        if ar < 1e-9:
            degen += 1
        else:
            area += ar
    rep["out_of_range"] = oor / T_
    rep["degenerate"] = degen / T_
    # Basit çakışma tespiti: UV düzleminde piksel örneklemesi
    if area > 0.001:
        G = grid
        grid_cnt = np.zeros((G, G), np.int32)
        samples = 0
        sample_cap = 200000
        for i in range(T_):
            a, b, c = UV[i, 0], UV[i, 1], UV[i, 2]
            ax = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) * 0.5
            if ax < 1e-9:
                continue
            n = int(max(4, min(64, density * ax * G * G / max(area, 1e-6))))
            samples += n
            if samples > sample_cap:
                break
            for _ in range(n):
                r1, r2 = random.random(), random.random()
                if r1 + r2 > 1.0:
                    r1, r2 = 1.0 - r1, 1.0 - r2
                u = a[0] + (b[0] - a[0]) * r1 + (c[0] - a[0]) * r2
                v = a[1] + (b[1] - a[1]) * r1 + (c[1] - a[1]) * r2
                xi = int(u * (G - 1))
                yi = int(v * (G - 1))
                if 0 <= xi < G and 0 <= yi < G:
                    grid_cnt[yi, xi] += 1
        used = np.count_nonzero(grid_cnt)
        covered = grid_cnt.sum()
        if used > 0 and covered > used:
            rep["overlap"] = float((covered - used) / covered)
    msg = []
    if rep["out_of_range"] > 0.001:
        msg.append(f"UV 0-1 alanı dışına taşıyor (%{int(rep['out_of_range']*100)})")
    if rep["overlap"] > 0.15:
        msg.append(f"UV parçaları üst üste biniyor (%{int(rep['overlap']*100)})")
    if rep["degenerate"] > 0.15:
        msg.append(f"Bozuk (sıfır alanlı) UV üçgeni çok (%{int(rep['degenerate']*100)})")
    rep["text"] = " · ".join(msg)
    return rep


def feature_edges(tri_pos, angle_deg=30.0, max_edges=400000):
    """Üçgen listesinden kenar çizgileri (keskin kenarlar + sınır kenarları) çıkarır.
    tri_pos: (3T,3). Dönüş: (N,2,3) segment listesi."""
    if len(tri_pos) == 0:
        return np.zeros((0, 2, 3), np.float32)
    T_ = len(tri_pos) // 3
    P = tri_pos.reshape(T_, 3, 3)
    e1 = P[:, 1] - P[:, 0]
    e2 = P[:, 2] - P[:, 0]
    nrm = np.cross(e1, e2)
    ln = np.linalg.norm(nrm, axis=1)
    ln[ln < 1e-12] = 1.0
    nrm = nrm / ln[:, None]
    thresh = math.cos(math.radians(angle_deg))
    edge_faces = {}
    for ti in range(T_):
        for k in range(3):
            a = tuple(np.round(P[ti, k, :], 5))
            b = tuple(np.round(P[ti, (k + 1) % 3, :], 5))
            if a == b:
                continue
            key = tuple(sorted([a, b]))
            edge_faces.setdefault(key, []).append(ti)
    out = []
    for key, faces in edge_faces.items():
        if len(faces) == 1:
            out.append((np.array(key[0]), np.array(key[1])))
        elif len(faces) == 2:
            dot = float(np.dot(nrm[faces[0]], nrm[faces[1]]))
            if dot < thresh:
                out.append((np.array(key[0]), np.array(key[1])))
        if len(out) >= max_edges:
            break
    if not out:
        return np.zeros((0, 2, 3), np.float32)
    arr = np.zeros((len(out), 2, 3), np.float32)
    for i, (a, b) in enumerate(out):
        arr[i, 0] = a
        arr[i, 1] = b
    return arr


def ray_aabb(ro, rd, lo, hi):
    """Kiriş-AABB kesişimi. (tmin, tmax) veya None."""
    tmin = -float("inf")
    tmax = float("inf")
    for i in range(3):
        if abs(rd[i]) < 1e-12:
            if ro[i] < lo[i] or ro[i] > hi[i]:
                return None
        else:
            inv = 1.0 / rd[i]
            t1 = (lo[i] - ro[i]) * inv
            t2 = (hi[i] - ro[i]) * inv
            if t1 > t2:
                t1, t2 = t2, t1
            tmin = max(tmin, t1)
            tmax = min(tmax, t2)
            if tmin > tmax:
                return None
    return tmin, tmax


def ray_triangles(ro, rd, A, E1, E2, tmax=float("inf"), chunk=200000):
    """Vektörel Möller-Trumbore. Dönüş: (idx, t, u, v) en yakın isabet veya None.
    A: (T,3), E1/E2: (T,3)."""
    T_ = len(A)
    if T_ == 0:
        return None
    best = None
    for start in range(0, T_, chunk):
        a = A[start:start + chunk]
        e1 = E1[start:start + chunk]
        e2 = E2[start:start + chunk]
        h = np.cross(rd[None, :], e2)
        det = np.einsum("ij,ij->i", e1, h)
        mask = np.abs(det) > 1e-12
        if not np.any(mask):
            continue
        inv = np.zeros_like(det)
        inv[mask] = 1.0 / det[mask]
        s = ro[None, :] - a
        u = np.einsum("ij,ij->i", s, h) * inv
        mask &= (u >= 0.0) & (u <= 1.0)
        if not np.any(mask):
            continue
        q = np.cross(s, e1)
        v = np.einsum("ij,ij->i", rd[None, :], q) * inv
        mask &= (v >= 0.0) & (u + v <= 1.0)
        if not np.any(mask):
            continue
        t = np.einsum("ij,ij->i", e2, q) * inv
        mask &= (t > 1e-6) & (t < tmax)
        if not np.any(mask):
            continue
        idxs = np.nonzero(mask)[0]
        ti = idxs[np.argmin(t[idxs])]
        if best is None or t[ti] < best[1]:
            best = (start + int(ti), float(t[ti]), float(u[ti]), float(v[ti]))
    return best




class PrimitiveMaterial:
    """Yüzey grubu: yalnızca adı + UV boya tuvali."""
    NEUTRAL = (0.72, 0.72, 0.72, 1.0)

    def __init__(self, d=None):
        d = d or {}
        self.name = str(d.get("name", "Materyal"))
        self.base_color = list(d.get("base_color", list(self.NEUTRAL)))
        self.metallic = 0.0
        self.roughness = 0.55
        self.alpha = 1.0
        self.ior = 1.5
        self.emission = [0.0, 0.0, 0.0, 1.0]
        self.emission_strength = 0.0
        self.coat_weight = 0.0
        self.transmission = 0.0
        self.base_image = QImage()
        self.normal_image = QImage()
        self.base_gl = None
        self.base_dirty = True
        self.base_full_upload = True
        self.rev = 0
        # Paint: tam çözünürlük tuval boyutu
        self.paint_w = 1024
        self.paint_h = 1024

    def color(self):
        return QColor.fromRgbF(*self.base_color[:3])

    def ensure_canvas(self, color=None):
        """UV boya tuvali yoksa oluştur; düz renk ile doldur."""
        if not self.base_image.isNull():
            return
        w = max(64, int(self.paint_w))
        h = max(64, int(self.paint_h))
        self.base_image = QImage(w, h, QImage.Format_RGBA8888)
        if color is None:
            color = QColor.fromRgbF(*self.base_color[:3])
        self.base_image.fill(color)
        # base_color shader'da tekrar çarpılmasın: shader'da 1,1,1 ile başlat
        self.base_color = [1.0, 1.0, 1.0, 1.0]
        self.base_dirty = True
        self.base_full_upload = True

    def reset_paint(self):
        if self.base_gl:
            GL_GARBAGE["textures"].append(int(self.base_gl))
            self.base_gl = None
        self.base_image = QImage()
        self.base_dirty = True
        self.base_full_upload = True

    @staticmethod
    def _image_b64(img):
        if img.isNull():
            return None
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        if not img.save(buf, "PNG"):
            return None
        return base64.b64encode(zlib.compress(bytes(buf.data()), 6)).decode("ascii")

    @staticmethod
    def _load_image(s):
        if not s:
            return QImage()
        try:
            return QImage.fromData(zlib.decompress(base64.b64decode(s)), "PNG")
        except Exception:
            return QImage()

    def to_json(self):
        return {
            "name": self.name,
            "base_color": list(self.base_color),
            "base_image": self._image_b64(self.base_image),
        }

    @staticmethod
    def from_json(d):
        m = PrimitiveMaterial(d)
        m.base_image = PrimitiveMaterial._load_image(d.get("base_image"))
        m.base_dirty = True
        m.base_full_upload = True
        return m


def _b64_array(a):
    if a is None or len(a) == 0:
        return None
    raw = np.ascontiguousarray(a, dtype=np.float32).tobytes()
    return base64.b64encode(zlib.compress(raw, 6)).decode("ascii")


def _unb64_array(s, cols):
    if not s:
        return np.zeros((0, cols), np.float32)
    raw = zlib.decompress(base64.b64decode(s))
    return np.frombuffer(raw, dtype=np.float32).reshape((-1, cols)).copy()


class PrimitiveMesh:
    # pos3 + normal3 + uv2 + tangent3 + hand1 = 12
    STRIDE = 12

    def __init__(self, name, parts, materials, source=""):
        self.id = uuid.uuid4().hex[:12]
        self.name = str(name or "Yerleşik Şekil")
        self.source = str(source or "")
        self.primitive_type = ""
        if self.source.startswith("builtin:"):
            self.primitive_type = self.source.split(":", 1)[1].strip()
        self.parts = parts          # [{"material":int, "arr":(N,12), "vbo":None, "count":N,
                                    #   "_tri_a":(T,3), "_tri_e1","_tri_e2","_edges_gl":None,
                                    #   "edges": (E,2,3)}]
        self.materials = materials
        self.position = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        self.rotation = np.array([0.0, 0.0, 0.0], dtype=np.float64)
        self.scale = np.array([1.0, 1.0, 1.0], dtype=np.float64)
        self.generated_uv = False
        self.visible = True
        self._bounds()
        self._tri_cache = None
        self._inst_cache = None

    def _bounds(self):
        all_pos = [p["arr"][:, 0:3] for p in self.parts if len(p.get("arr", [])) > 0]
        if not all_pos:
            self.bounds_min = np.zeros(3)
            self.bounds_max = np.zeros(3)
            return
        pos = np.concatenate(all_pos, axis=0)
        self.bounds_min = pos.min(axis=0)
        self.bounds_max = pos.max(axis=0)

    def _recalc_bounds(self):
        self._bounds()
        self._tri_cache = None
        self._inst_cache = None

    def center_and_ground(self):
        """Geometriyi X/Z merkezli ve Y=0 tabanlı yerel uzaya taşır."""
        if not self.parts:
            self.position[:] = 0.0
            return
        shift = np.array([
            (self.bounds_min[0] + self.bounds_max[0]) * 0.5,
            self.bounds_min[1],
            (self.bounds_min[2] + self.bounds_max[2]) * 0.5,
        ], dtype=np.float64)
        sf = shift.astype(np.float32)
        for part in self.parts:
            arr = part.get("arr")
            if arr is not None and len(arr):
                arr[:, 0:3] -= sf
            edges = part.get("edges")
            if edges is not None and len(edges):
                part["edges"] = edges - sf
            part["vbo"] = None
            part["edges_vbo"] = None
        self.position[:] = 0.0
        self._recalc_bounds()

    def release_gl(self):
        for part in self.parts:
            buf = part.get("vbo")
            if buf:
                GL_GARBAGE["buffers"].append(int(buf))
                part["vbo"] = None
            ebuf = part.get("edges_vbo")
            if ebuf:
                GL_GARBAGE["buffers"].append(int(ebuf))
                part["edges_vbo"] = None
        for m in self.materials:
            if m.base_gl:
                GL_GARBAGE["textures"].append(int(m.base_gl))
                m.base_gl = None

    def tri_data(self):
        """Her parça için (A, E1, E2) dizileri döndürür. Cache'lenir."""
        if self._tri_cache is not None:
            return self._tri_cache
        out = []
        for part in self.parts:
            arr = part["arr"]
            if len(arr) < 3:
                out.append(None)
                continue
            T_ = len(arr) // 3
            P = arr[:, 0:3].reshape(T_, 3, 3).astype(np.float64)
            A = P[:, 0]
            E1 = P[:, 1] - P[:, 0]
            E2 = P[:, 2] - P[:, 0]
            out.append((A, E1, E2))
        self._tri_cache = out
        return out

    def instance_arrays(self):
        """Yerleşik örnekler için (T_global,3) köşe konumları (dünya uzayı)."""
        if self._inst_cache is not None:
            return self._inst_cache
        pos, nrm, uv, tan = [], [], [], []
        for part in self.parts:
            arr = part["arr"]
            if len(arr) == 0:
                continue
            pos.append(arr[:, 0:3]); nrm.append(arr[:, 3:6])
            uv.append(arr[:, 6:8]); tan.append(arr[:, 8:12])
        if not pos:
            self._inst_cache = (np.zeros((0, 3)), np.zeros((0, 3)), np.zeros((0, 2)), np.zeros((0, 4)))
            return self._inst_cache
        self._inst_cache = (np.concatenate(pos), np.concatenate(nrm),
                            np.concatenate(uv), np.concatenate(tan))
        return self._inst_cache

    def regenerate_uv(self, margin=2.5 / 1024.0):
        """Yüzeyler için yeni UV üretir (yüzey boyamayı düzeltmek için)."""
        for part in self.parts:
            arr = part["arr"]
            if len(arr) == 0:
                continue
            T_ = len(arr) // 3
            pos = arr[:, 0:3].astype(np.float64)
            nrm = arr[:, 3:6].astype(np.float64)
            new_uv = auto_unwrap(pos, margin=margin)
            arr[:, 6:8] = new_uv.astype(np.float32)
            tangent = compute_tangents(pos.astype(np.float32), nrm.astype(np.float32),
                                       new_uv.astype(np.float32))
            if len(tangent) == len(arr):
                arr[:, 8:12] = tangent
            if part.get("vbo"):
                GL_GARBAGE["buffers"].append(int(part["vbo"]))
            part["vbo"] = None  # yeniden yükleme
        self._tri_cache = None
        for m in self.materials:
            m.base_dirty = True
            m.base_full_upload = True

    def to_json(self):
        out = {
            "id": self.id,
            "name": self.name,
            "source": self.source,
            "primitive_type": self.primitive_type,
            "position": self.position.tolist(),
            "rotation": self.rotation.tolist(),
            "scale": self.scale.tolist(),
            "generated_uv": self.generated_uv,
            "visible": self.visible,
            "materials": [m.to_json() for m in self.materials],
            "parts": [],
        }
        for part in self.parts:
            pd = {
                "material": int(part["material"]),
                "count": int(len(part["arr"])),
                "data": _b64_array(part["arr"]),
            }
            edges = part.get("edges")
            if edges is not None and len(edges):
                pd["edges"] = _b64_array(edges.reshape(-1, 3))
                pd["edge_count"] = int(len(edges))
            out["parts"].append(pd)
        return out

    @staticmethod
    def from_json(d):
        mats = [PrimitiveMaterial.from_json(x) for x in d.get("materials", [])]
        parts = []
        generated_any_uv = False
        for p in d.get("parts", []):
            arr = _unb64_array(p.get("data"), PrimitiveMesh.STRIDE)
            if len(arr) >= 3:
                arr = arr[:(len(arr) // 3) * 3].copy()
                pos = arr[:, 0:3].astype(np.float32)
                uv = arr[:, 6:8].astype(np.float32)
                finite = bool(np.isfinite(uv).all())
                in_range = bool(finite and float(np.min(uv)) >= -1e-5 and float(np.max(uv)) <= 1.00001)
                tri_uv = uv.reshape(-1, 3, 2)
                uv_area = np.abs((tri_uv[:,1,0]-tri_uv[:,0,0])*(tri_uv[:,2,1]-tri_uv[:,0,1]) -
                                 (tri_uv[:,1,1]-tri_uv[:,0,1])*(tri_uv[:,2,0]-tri_uv[:,0,0])) * 0.5
                mostly_degenerate = (len(uv_area) > 0 and float(np.mean(uv_area < 1e-10)) > 0.20)
                if (not finite) or (not in_range and not mostly_degenerate) or mostly_degenerate:
                    new_uv = auto_unwrap(pos)
                    arr[:, 6:8] = new_uv.astype(np.float32)
                    tan = compute_tangents(pos, arr[:, 3:6].astype(np.float32), arr[:, 6:8].astype(np.float32))
                    if len(tan) == len(arr):
                        arr[:, 8:12] = tan
                    generated_any_uv = True
            part = {"material": int(p.get("material", 0)), "arr": arr,
                    "vbo": None, "count": len(arr)}
            if p.get("edges"):
                ed = _unb64_array(p["edges"], 3)
                usable = (len(ed) // 2) * 2
                if usable:
                    part["edges"] = ed[:usable].reshape((-1, 2, 3)).astype(np.float32)
            parts.append(part)
        obj = PrimitiveMesh(d.get("name", "Yerleşik Şekil"), parts, mats, d.get("source", ""))
        obj.id = str(d.get("id") or obj.id)
        obj.primitive_type = str(d.get("primitive_type") or obj.primitive_type or "")
        obj.position = np.array(d.get("position", [0, 0, 0]), dtype=np.float64)
        obj.rotation = np.array(d.get("rotation", [0, 0, 0]), dtype=np.float64)
        obj.scale = np.array(d.get("scale", [1, 1, 1]), dtype=np.float64)
        obj.generated_uv = bool(d.get("generated_uv", False)) or generated_any_uv
        obj.visible = bool(d.get("visible", True))
        obj._recalc_bounds()
        return obj


# ----------------------------------------------------------------------------
# Yerleşik temel şekiller
# ----------------------------------------------------------------------------
BUILTIN_PRIMITIVES = (
    ("cube", "Küp"),
    ("cylinder", "Silindir"),
    ("cone", "Koni"),
    ("sphere", "Küre"),
    ("pyramid", "Piramit"),
)
BUILTIN_COLORS = {
    "cube": "#d0d0d0",
    "cylinder": "#6fa8dc",
    "cone": "#e69138",
    "sphere": "#93c47d",
    "pyramid": "#c27ba0",
}


def _primitive_part(pos, normals, uv, material_index=0):
    pos = np.asarray(pos, dtype=np.float32).reshape(-1, 3)
    normals = np.asarray(normals, dtype=np.float32).reshape(-1, 3)
    uv = np.asarray(uv, dtype=np.float32).reshape(-1, 2)
    if not (len(pos) == len(normals) == len(uv)) or len(pos) < 3:
        raise ValueError("Geçersiz temel şekil yüzeyi")
    tan = compute_tangents(pos, normals, uv)
    arr = np.concatenate([pos, normals, uv, tan], axis=1).astype(np.float32)
    return {
        "material": int(material_index),
        "arr": arr,
        "vbo": None,
        "edges_vbo": None,
        "count": len(arr),
        "edges": feature_edges(pos),
    }


def _add_tri(positions, normals, uvs, a, b, c, normal, ua, ub, uc):
    positions.extend([a, b, c])
    normals.extend([normal, normal, normal])
    uvs.extend([ua, ub, uc])


def _cube_geometry():
    faces = [
        # normal, corners, uv corners
        ((1,0,0), [(0.5,0,0),(0.5,0,1),(0.5,1,1),(0.5,1,0)]),
        ((-1,0,0), [(-0.5,0,1),(-0.5,0,0),(-0.5,1,0),(-0.5,1,1)]),
        ((0,1,0), [(-0.5,1,1),(0.5,1,1),(0.5,1,0),(-0.5,1,0)]),
        ((0,-1,0), [(-0.5,0,0),(0.5,0,0),(0.5,0,1),(-0.5,0,1)]),
        ((0,0,1), [(-0.5,0,1),(0.5,0,1),(0.5,1,1),(-0.5,1,1)]),
        ((0,0,-1), [(0.5,0,0),(-0.5,0,0),(-0.5,1,0),(0.5,1,0)]),
    ]
    parts = []
    for normal, q in faces:
        p, n, u = [], [], []
        _add_tri(p,n,u,q[0],q[1],q[2],normal,(0,1),(1,1),(1,0))
        _add_tri(p,n,u,q[0],q[2],q[3],normal,(0,1),(1,0),(0,0))
        parts.append((p,n,u))
    return parts, 6


def _cylinder_geometry(segments=32):
    segments = max(8, int(segments))
    side_p, side_n, side_u = [], [], []
    top_p, top_n, top_u = [], [], []
    bot_p, bot_n, bot_u = [], [], []
    r, h = 0.5, 1.0
    for i in range(segments):
        j = (i + 1) % segments
        a0 = 2*math.pi*i/segments
        a1 = 2*math.pi*j/segments
        x0,z0 = r*math.cos(a0), r*math.sin(a0)
        x1,z1 = r*math.cos(a1), r*math.sin(a1)
        n0 = (math.cos(a0), 0, math.sin(a0))
        n1 = (math.cos(a1), 0, math.sin(a1))
        u0, u1 = i/segments, j/segments
        _add_tri(side_p,side_n,side_u,(x0,0,z0),(x1,0,z1),(x1,h,z1),n0,(u0,0),(u1,0),(u1,1))
        side_n[-3] = n0; side_n[-2] = n1; side_n[-1] = n1
        _add_tri(side_p,side_n,side_u,(x0,0,z0),(x1,h,z1),(x0,h,z0),n0,(u0,0),(u1,1),(u0,1))
        side_n[-3] = n0; side_n[-2] = n1; side_n[-1] = n0
        # top cap
        ct=(0,h,0)
        _add_tri(top_p,top_n,top_u,ct,(x1,h,z1),(x0,h,z0),(0,1,0),(0.5,0.5),(0.5+x1,0.5+z1),(0.5+x0,0.5+z0))
        # bottom cap (reverse winding)
        cb=(0,0,0)
        _add_tri(bot_p,bot_n,bot_u,cb,(x0,0,z0),(x1,0,z1),(0,-1,0),(0.5,0.5),(0.5+x0,0.5+z0),(0.5+x1,0.5+z1))
    return [(side_p,side_n,side_u),(top_p,top_n,top_u),(bot_p,bot_n,bot_u)], 3


def _cone_geometry(segments=32):
    segments = max(8, int(segments))
    side_p, side_n, side_u = [], [], []
    bot_p, bot_n, bot_u = [], [], []
    r, h = 0.5, 1.0
    slope = r / h
    for i in range(segments):
        j=(i+1)%segments
        a0=2*math.pi*i/segments; a1=2*math.pi*j/segments
        x0,z0=r*math.cos(a0),r*math.sin(a0)
        x1,z1=r*math.cos(a1),r*math.sin(a1)
        n0=np.array([math.cos(a0),slope,math.sin(a0)],dtype=np.float64); n0/=np.linalg.norm(n0)
        n1=np.array([math.cos(a1),slope,math.sin(a1)],dtype=np.float64); n1/=np.linalg.norm(n1)
        apex=(0,h,0)
        _add_tri(side_p,side_n,side_u,(x0,0,z0),(x1,0,z1),apex,tuple(n0),(i/segments,0),(j/segments,0.0),(0.5,1.0))
        side_n[-3]=tuple(n0); side_n[-2]=tuple(n1); side_n[-1]=tuple((n0+n1)/max(np.linalg.norm(n0+n1),1e-9))
        cb=(0,0,0)
        _add_tri(bot_p,bot_n,bot_u,cb,(x1,0,z1),(x0,0,z0),(0,-1,0),(0.5,0.5),(0.5+x1,0.5+z1),(0.5+x0,0.5+z0))
    return [(side_p,side_n,side_u),(bot_p,bot_n,bot_u)], 2


def _sphere_geometry(segments=32, rings=18):
    segments=max(12,int(segments)); rings=max(8,int(rings))
    p,n,u=[],[],[]
    r=0.5; cy=0.5
    for iy in range(rings):
        v0=iy/rings; v1=(iy+1)/rings
        phi0=math.pi*v0; phi1=math.pi*v1
        for ix in range(segments):
            j=(ix+1)%segments
            u0=ix/segments; u1=j/segments
            def vtx(phi, uu):
                x=math.sin(phi)*math.cos(uu*2*math.pi)
                y=math.cos(phi)
                z=math.sin(phi)*math.sin(uu*2*math.pi)
                return np.array([r*x, cy+r*y, r*z],dtype=np.float64), np.array([x,y,z],dtype=np.float64)
            a,na=vtx(phi0,u0); b,nb=vtx(phi0,u1); c,nc=vtx(phi1,u1); d,nd=vtx(phi1,u0)
            _add_tri(p,n,u,a,b,c,na,(u0,1-v0),(u1,1-v0),(u1,1-v1)); n[-2]=nb; n[-1]=nc
            _add_tri(p,n,u,a,c,d,na,(u0,1-v0),(u1,1-v1),(u0,1-v1)); n[-2]=nc; n[-1]=nd
    return [(p,n,u)], 1


def _pyramid_geometry():
    p,n,u=[],[],[]
    apex=(0,1,0)
    quads=[
        ((0,1,0), [(-0.5,0,-0.5),(0.5,0,-0.5),(0.5,1 and 0,-0.5)]),
    ]
    # Four sloped triangular sides, each with correct face normal.
    sides=[
        ((0.5,0,-0.5),(0.5,0,0.5),apex),
        ((0.5,0,0.5),(-0.5,0,0.5),apex),
        ((-0.5,0,0.5),(-0.5,0,-0.5),apex),
        ((-0.5,0,-0.5),(0.5,0,-0.5),apex),
    ]
    for a,b,c in sides:
        nn=np.cross(np.asarray(b)-a,np.asarray(c)-a); nn/=max(np.linalg.norm(nn),1e-9)
        _add_tri(p,n,u,a,b,c,tuple(nn),(0,0),(1,0),(0.5,1))
    # square base
    a,b,c,d=(-0.5,0,-0.5),(0.5,0,-0.5),(0.5,0,0.5),(-0.5,0,0.5)
    _add_tri(p,n,u,a,c,b,(0,-1,0),(0,0),(1,1),(1,0))
    _add_tri(p,n,u,a,d,c,(0,-1,0),(0,0),(0,1),(1,1))
    return [(p,n,u)], 1


def create_builtin_primitive(kind, name=None, color=None, segments=32):
    kind = str(kind).lower().strip()
    names = dict(BUILTIN_PRIMITIVES)
    if kind not in names:
        raise ValueError("Bilinmeyen temel şekil: %s" % kind)
    if kind == "cube":
        raw_parts, mat_count = _cube_geometry()
    elif kind == "cylinder":
        raw_parts, mat_count = _cylinder_geometry(segments)
    elif kind == "cone":
        raw_parts, mat_count = _cone_geometry(segments)
    elif kind == "sphere":
        raw_parts, mat_count = _sphere_geometry(segments, max(8, segments//2))
    else:
        raw_parts, mat_count = _pyramid_geometry()
    base = QColor(color or BUILTIN_COLORS.get(kind, '#ffffff'))
    materials=[]
    for i in range(mat_count):
        m=PrimitiveMaterial({"name": f"{names[kind]} yüzey {i+1}", "base_color": [base.redF(),base.greenF(),base.blueF(),1.0]})
        materials.append(m)
    parts=[]
    for i,(pp,nn,uu) in enumerate(raw_parts):
        parts.append(_primitive_part(pp,nn,uu,i))
    obj=PrimitiveMesh(name or names[kind], parts, materials, source="builtin:%s"%kind)
    obj.primitive_type=kind
    obj.center_and_ground()
    return obj



# ----------------------------------------------------------------------------
# Sahne
# ----------------------------------------------------------------------------
def ckey(c):
    return (c[0] >> CHUNK_BITS, c[1] >> CHUNK_BITS, c[2] >> CHUNK_BITS)


class ChunkMesh:
    __slots__ = ("arr", "count", "vbo", "upload")

    def __init__(self):
        self.arr = None
        self.count = 0
        self.vbo = None
        self.upload = False


class Scene:
    def __init__(self):
        self.world = {}
        self.chunk_cells = {}
        self.meshes = {}
        self.dirty = set()
        self.dead_vbos = []
        self.cubes = {}
        self.primitive_objects = {}
        self.object_instances = {}
        self.object_instance_cells = {}
        self.inst_rev = 0
        self.slots = {}
        self.next_slot = 0
        self.atlas = QImage(ATLAS, ATLAS, QImage.Format_RGBA8888)
        self.atlas.fill(QColor(0, 0, 0, 0))
        self.atlas_rows = 0
        self.atlas_dirty = True
        self.border = True

    def register_cube(self, cube):
        if cube.id not in self.slots:
            if self.next_slot >= MAX_SLOTS:
                raise RuntimeError("Küp sınırına ulaşıldı.")
            self.slots[cube.id] = self.next_slot
            self.next_slot += 1
        self.cubes[cube.id] = cube
        self._write_tiles(cube)

    def _bake(self, face):
        if not self.border:
            return face
        img = face.copy()
        edge = set()
        for i in range(TILE):
            edge.update([(i, 0), (i, TILE - 1), (0, i), (TILE - 1, i)])
        for x, y in edge:
            c = img.pixelColor(x, y)
            img.setPixelColor(x, y, QColor(int(c.red() * 0.78), int(c.green() * 0.78), int(c.blue() * 0.78), 255))
        return img

    def _write_tiles(self, cube):
        base = self.slots[cube.id] * 6
        p = QPainter(self.atlas)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        for f in range(6):
            t = base + f
            p.drawImage((t % TPR) * TILE, (t // TPR) * TILE, self._bake(cube.faces[f]))
        p.end()
        self.atlas_rows = max(self.atlas_rows, ((base + 5) // TPR + 1) * TILE)
        self.atlas_dirty = True

    def set_border(self, flag):
        self.border = flag
        for c in self.cubes.values():
            self._write_tiles(c)

    def _mark(self, c):
        x, y, z = c
        self.dirty.add(ckey(c))
        for dx, dy, dz in FACE_N:
            self.dirty.add(ckey((x + dx, y + dy, z + dz)))

    def put(self, c, bid):
        old = self.world.get(c)
        if old == bid:
            return old
        self.world[c] = bid
        self.chunk_cells.setdefault(ckey(c), set()).add(c)
        self._mark(c)
        return old

    def remove(self, c):
        old = self.world.pop(c, None)
        if old is None:
            return None
        k = ckey(c)
        s = self.chunk_cells.get(k)
        if s is not None:
            s.discard(c)
            if not s:
                del self.chunk_cells[k]
        self._mark(c)
        return old

    def clear_primitives(self):
        for obj in list(self.primitive_objects.values()):
            obj.release_gl()
        self.primitive_objects.clear()
        self.clear_object_instances()

    def clear_object_instances(self):
        self.object_instances.clear()
        self.object_instance_cells.clear()
        self.inst_rev += 1

    def add_primitive(self, obj):
        old = self.primitive_objects.get(obj.id)
        if old is not None and old is not obj:
            old.release_gl()
        self.primitive_objects[obj.id] = obj

    def remove_primitive(self, oid):
        obj = self.primitive_objects.pop(oid, None)
        if obj is not None:
            obj.release_gl()
        dead = [iid for iid, ins in self.object_instances.items() if ins.get("asset") == oid]
        for iid in dead:
            cell = tuple(self.object_instances[iid].get("cell", (0, 0, 0)))
            self.object_instance_cells.pop((oid, cell), None)
            self.object_instances.pop(iid, None)
        self.inst_rev += 1
        return True

    def add_object_instance(self, asset_id, cell, rotation=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)):
        cell = tuple(int(v) for v in cell)
        key = (asset_id, cell)
        old = self.object_instance_cells.get(key)
        if old:
            return old
        iid = uuid.uuid4().hex[:12]
        obj = self.primitive_objects.get(asset_id)
        pos = instance_position_for_cell(obj, cell, rotation, scale) if obj is not None else np.array([cell[0] + 0.5, cell[1], cell[2] + 0.5], dtype=np.float64)
        self.object_instances[iid] = {
            "id": iid, "asset": asset_id, "cell": list(cell),
            "position": [float(v) for v in pos],
            "rotation": [float(v) for v in rotation],
            "scale": [float(v) for v in scale],
            "hidden": False,
        }
        self.object_instance_cells[key] = iid
        self.inst_rev += 1
        return iid

    def remove_object_instance(self, iid):
        ins = self.object_instances.pop(iid, None)
        if ins:
            self.object_instance_cells.pop((ins.get("asset"), tuple(ins.get("cell", (0, 0, 0)))), None)
        self.inst_rev += 1
        return ins

    def object_instance_exists(self, asset_id, cell):
        return (asset_id, tuple(int(v) for v in cell)) in self.object_instance_cells

    def clear_world(self):
        self.dirty.update(self.meshes.keys())
        self.world.clear()
        self.chunk_cells.clear()

    def load_blocks(self, items):
        for c, bid in items:
            self.world[c] = bid
            self.chunk_cells.setdefault(ckey(c), set()).add(c)
        self.dirty.update(self.chunk_cells.keys())

    def rebuild_dirty(self):
        for k in self.dirty:
            cells = self.chunk_cells.get(k)
            m = self.meshes.get(k)
            if not cells:
                if m is not None:
                    if m.vbo:
                        self.dead_vbos.append(m.vbo)
                    del self.meshes[k]
                continue
            if m is None:
                m = ChunkMesh()
                self.meshes[k] = m
            m.arr = self._build(cells)
            m.count = len(m.arr)
            m.upload = True
        self.dirty.clear()

    def _build(self, cells):
        world, slots = self.world, self.slots
        rec = []
        for c in cells:
            x, y, z = c
            base = slots[world[c]] * 6
            for f in range(6):
                nx, ny, nz = FACE_N[f]
                if (x + nx, y + ny, z + nz) in world:
                    continue
                rec.append((x, y, z, f, base + f))
        if not rec:
            return np.zeros((0, 8), np.float32)
        a = np.array(rec, dtype=np.float64)
        n = len(a)
        f = a[:, 3].astype(np.int32)
        t = a[:, 4].astype(np.int32)
        pos = a[:, None, 0:3] + FACE_V[f]
        ox = ((t % TPR) * TILE).astype(np.float64)
        oy = ((t // TPR) * TILE).astype(np.float64)
        e = 0.02
        u = (ox[:, None] + e + FACE_UV[None, :, 0] * (TILE - 2 * e)) / ATLAS
        v = (oy[:, None] + e + FACE_UV[None, :, 1] * (TILE - 2 * e)) / ATLAS
        sh = np.repeat(FACE_SHADE[f][:, None], 4, axis=1)
        out = np.empty((n, 4, 8), np.float32)
        out[:, :, 0:3] = pos
        out[:, :, 3] = u
        out[:, :, 4] = v
        out[:, :, 5] = sh
        out[:, :, 6] = sh
        out[:, :, 7] = sh
        return out.reshape(-1, 8)


# OpenGL kaynakları (buffer / doku) bağlam dışındayken serbest bırakma kuyruğu.
GL_GARBAGE = {"buffers": [], "textures": []}


def gl_release(buf=None, tex=None):
    if buf:
        GL_GARBAGE["buffers"].append(int(buf))
    if tex:
        GL_GARBAGE["textures"].append(int(tex))


# ----------------------------------------------------------------------------
# Matematik
# ----------------------------------------------------------------------------
def perspective(fovy_deg, aspect, near, far):
    f = 1.0 / math.tan(math.radians(fovy_deg) / 2.0)
    m = np.zeros((4, 4))
    m[0, 0] = f / aspect
    m[1, 1] = f
    m[2, 2] = (far + near) / (near - far)
    m[2, 3] = 2.0 * far * near / (near - far)
    m[3, 2] = -1.0
    return m


def look_at(eye, target, up):
    f = target - eye
    f = f / np.linalg.norm(f)
    s = np.cross(f, up)
    s = s / np.linalg.norm(s)
    u = np.cross(s, f)
    m = np.eye(4)
    m[0, :3], m[1, :3], m[2, :3] = s, u, -f
    m[0, 3], m[1, 3], m[2, 3] = -np.dot(s, eye), -np.dot(u, eye), np.dot(f, eye)
    return m


def raycast_blocks(world, o, d, maxdist):
    if not world:
        return None
    ox, oy, oz = float(o[0]), float(o[1]), float(o[2])
    dx, dy, dz = float(d[0]), float(d[1]), float(d[2])
    x, y, z = math.floor(ox), math.floor(oy), math.floor(oz)
    inf = float("inf")
    sx, sy, sz = (1 if dx > 0 else -1), (1 if dy > 0 else -1), (1 if dz > 0 else -1)
    tdx = abs(1.0 / dx) if dx else inf
    tdy = abs(1.0 / dy) if dy else inf
    tdz = abs(1.0 / dz) if dz else inf
    tmx = ((x + 1 - ox) / dx if dx > 0 else (ox - x) / -dx) if dx else inf
    tmy = ((y + 1 - oy) / dy if dy > 0 else (oy - y) / -dy) if dy else inf
    tmz = ((z + 1 - oz) / dz if dz > 0 else (oz - z) / -dz) if dz else inf
    t = 0.0
    nrm = (0, 0, 0)
    first = True
    while t <= maxdist:
        if not first and (x, y, z) in world:
            return (x, y, z), nrm, t
        first = False
        if tmx < tmy and tmx < tmz:
            x += sx
            t = tmx
            tmx += tdx
            nrm = (-sx, 0, 0)
        elif tmy < tmz:
            y += sy
            t = tmy
            tmy += tdy
            nrm = (0, -sy, 0)
        else:
            z += sz
            t = tmz
            tmz += tdz
            nrm = (0, 0, -sz)
    return None


def plane_uv(cell, axis):
    if axis == 0:
        return cell[1], cell[2]
    if axis == 1:
        return cell[0], cell[2]
    return cell[0], cell[1]


# ----------------------------------------------------------------------------
# 3B görünüm
# ----------------------------------------------------------------------------
class Viewport(QOpenGLWidget):
    MAX_INSTANCES = 20000

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.yaw, self.pitch, self.dist = 0.8, 0.55, 16.0
        self.target = np.array([0.5, 0.5, 0.5])
        self.fov = 60.0
        self.tex = None
        self.mesh_program = None
        self._uloc = {}
        self.stroke = None
        self.cam = None
        self.cam_last = None
        self.hover = None
        self.show_grid = True
        self._hover_skip_until = 0.0
        self._last_err = ""
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.CrossCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    # -- kamera
    def reset_camera(self):
        self.yaw, self.pitch, self.dist = 0.8, 0.55, 16.0
        self.target = np.array([0.5, 0.5, 0.5])
        self.update()

    def get_camera(self):
        return {"yaw": self.yaw, "pitch": self.pitch, "dist": self.dist,
                "target": [float(v) for v in self.target]}

    def set_camera(self, d):
        try:
            self.yaw = float(d["yaw"]); self.pitch = float(d["pitch"]); self.dist = float(d["dist"])
            self.target = np.array([float(v) for v in d["target"]])
        except Exception:
            self.reset_camera()
        self.update()

    def eye(self):
        cp = math.cos(self.pitch)
        return self.target + self.dist * np.array([cp * math.sin(self.yaw), math.sin(self.pitch),
                                                    cp * math.cos(self.yaw)])

    def matrices(self):
        w, h = max(1, self.width()), max(1, self.height())
        near = max(0.05, self.dist * 0.02)
        far = max(4000.0, self.dist * 100.0)
        return perspective(self.fov, w / h, near, far), look_at(self.eye(), self.target, np.array([0.0, 1.0, 0.0]))

    def ray(self, px, py):
        P, V = self.matrices()
        inv = np.linalg.inv(P @ V)
        x = 2.0 * px / max(1, self.width()) - 1.0
        y = 1.0 - 2.0 * py / max(1, self.height())
        a = inv @ np.array([x, y, -1.0, 1.0])
        b = inv @ np.array([x, y, 1.0, 1.0])
        a, b = a[:3] / a[3], b[:3] / b[3]
        d = b - a
        d = d / np.linalg.norm(d)
        return self.eye(), d

    def _maxdist(self):
        return min(max(self.dist * 3.0, 200.0), 2500.0)

    def _object_transform(self, obj_or_instance):
        if isinstance(obj_or_instance, PrimitiveMesh):
            return euler_mesh_matrix(obj_or_instance.position, obj_or_instance.rotation, obj_or_instance.scale)
        return euler_mesh_matrix(obj_or_instance.get("position", [0, 0, 0]),
                                 obj_or_instance.get("rotation", [0, 0, 0]),
                                 obj_or_instance.get("scale", [1, 1, 1]))

    def _instance_positions(self, asset_id):
        """Asset için yerleşik örneklerin pozisyonları (offline liste)."""
        sc = self.win.scene
        positions = []
        rot_scale = []
        for ins in sc.object_instances.values():
            if ins.get("asset") != asset_id:
                continue
            p = ins.get("position", [0, 0, 0])
            positions.append([float(p[0]), float(p[1]), float(p[2])])
            r = ins.get("rotation", [0, 0, 0])
            s = ins.get("scale", [1, 1, 1])
            if abs(float(r[0])) + abs(float(r[1])) + abs(float(r[2])) < 1e-6 and \
               abs(float(s[0]) - 1.0) + abs(float(s[1]) - 1.0) + abs(float(s[2]) - 1.0) < 1e-6:
                rot_scale.append(None)
            else:
                rot_scale.append(euler_mesh_matrix(p, r, s))
        return positions, rot_scale

    def raycast_primitives(self, px, py, include_asset=True):
        """İlk temel şekil üçgenini bulur.
        Dönüş: (asset_id, instance_id, mat_index, part_index, tri_offset, uv, t_world, wp, M)
        """
        o, d = self.ray(px, py)
        sc = self.win.scene
        best = None
        maxd = self._maxdist()

        def hit_local(obj, M, asset_id, instance_id):
            nonlocal best
            try:
                inv = np.linalg.inv(M)
            except np.linalg.LinAlgError:
                return
            ro4 = inv @ np.array([o[0], o[1], o[2], 1.0], dtype=np.float64)
            rd4 = inv @ np.array([d[0], d[1], d[2], 0.0], dtype=np.float64)
            ro = ro4[:3]
            rd = rd4[:3]
            n = np.linalg.norm(rd)
            if n < 1e-12:
                return
            rd /= n
            # AABB erken çıkış
            bb = ray_aabb(ro, rd, obj.bounds_min - 1e-4, obj.bounds_max + 1e-4)
            if bb is None:
                return
            tris = obj.tri_data()
            for pi, part in enumerate(obj.parts):
                td = tris[pi]
                if td is None:
                    continue
                A, E1, E2 = td
                r = ray_triangles(ro, rd, A, E1, E2, tmax=maxd)
                if r is None:
                    continue
                idx, t, u, v = r
                # dünya isabet
                lp = ro + rd * t
                wp4 = M @ np.array([lp[0], lp[1], lp[2], 1.0])
                wt = float(np.linalg.norm(wp4[:3] - o))
                if best is not None and wt >= best[6]:
                    continue
                arr = part["arr"]
                base = idx * 3
                uv0 = arr[base, 6:8]; uv1 = arr[base + 1, 6:8]; uv2 = arr[base + 2, 6:8]
                uv = uv0 * (1.0 - u - v) + uv1 * u + uv2 * v
                best = (asset_id, instance_id, int(part["material"]), pi, idx,
                        uv.astype(np.float64), wt, wp4[:3].astype(np.float64), M)
                return

        # Asset ana kopyası
        if include_asset:
            for oid, obj in sc.primitive_objects.items():
                if not obj.visible:
                    continue
                M = self._object_transform(obj)
                hit_local(obj, M, oid, None)

        # Yerleşik örnekler
        for iid, ins in sc.object_instances.items():
            asset_id = ins.get("asset")
            obj = sc.primitive_objects.get(asset_id)
            if obj is None or not obj.visible:
                continue
            M = self._object_transform(ins)
            # hızlı merkez testi
            p = np.array(ins.get("position", [0, 0, 0]), dtype=np.float64)
            dvec = p - o
            if np.dot(dvec, d) < -1.0:
                continue
            hit_local(obj, M, asset_id, iid)
        return best

    def raycast_mesh_only(self, px, py):
        """Yalnızca mesh (asset + instance) isabeti."""
        return self.raycast_primitives(px, py, include_asset=True)

    def pick_place(self, px, py):
        o, d = self.ray(px, py)
        hit = raycast_blocks(self.win.scene.world, o, d, self._maxdist())
        tb = hit[2] if hit else float("inf")
        tg = float("inf")
        if abs(d[1]) > 1e-9:
            t = -o[1] / d[1]
            if t > 0:
                tg = t
        if hit and tb <= tg:
            cell, n, _ = hit
            axis = 0 if n[0] else (1 if n[1] else 2)
            return (cell[0] + n[0], cell[1] + n[1], cell[2] + n[2]), axis
        if tg < 4000.0:
            p = o + d * tg
            return (int(math.floor(p[0])), 0 if o[1] >= 0 else -1, int(math.floor(p[2]))), 1
        p = o + d * self.dist
        axis = int(np.argmax(np.abs(d)))
        return tuple(int(math.floor(v)) for v in p), axis

    def pick_hit(self, px, py):
        o, d = self.ray(px, py)
        return raycast_blocks(self.win.scene.world, o, d, self._maxdist())

    def plane_cell(self, px, py, axis, layer):
        o, d = self.ray(px, py)
        if abs(d[axis]) < 1e-9:
            return None
        t = (layer + 0.5 - o[axis]) / d[axis]
        if t <= 0 or t > 8000.0:
            return None
        p = o + d * t
        c = [int(math.floor(p[0])), int(math.floor(p[1])), int(math.floor(p[2]))]
        c[axis] = layer
        return tuple(c)

    # -- çizim vuruşu
    def begin_stroke(self, pos, mode):
        # *** KRİTİK DÜZELTME: object_paints bir SÖZLÜK olmalı, liste değil. ***
        self.stroke = {
            "mode": mode,
            "changes": [],        # [ ("block", cell, old, new) | ("objadd", ins) | ("objdel", ins) ]
            "object_paints": {},  # {(asset_id, mat_index): (before_image, before_color)}
            "axis": None, "layer": 0,
            "last": None, "seq": 0, "path": 0.0, "lastpos": pos,
        }
        self.hover = None
        try:
            self.stroke_to(pos, first=True)
        except Exception:
            traceback.print_exc()
            self.stroke = None

    def end_stroke(self):
        s = self.stroke
        if not s:
            return
        self.stroke = None
        actions = list(s["changes"])
        for key, snap in s.get("object_paints", {}).items():
            oid, mi = key
            obj = self.win.scene.primitive_objects.get(oid)
            if obj is None or not (0 <= mi < len(obj.materials)):
                continue
            before_img, before_color = snap
            mat = obj.materials[mi]
            after_img = mat.base_image.copy() if not mat.base_image.isNull() else QImage()
            after_color = list(mat.base_color)
            actions.append(("objpaint", oid, int(mi), before_img, before_color, after_img, after_color))
        self.win.push_undo(actions)

    def _place(self, cell, axis):
        s = self.stroke
        sc = self.win.scene
        u, v = plane_uv(cell, axis)
        s["path"] += 16.0
        bid = self.win.pick_brush_id(u, v, s["path"], s["seq"])
        s["seq"] += 1
        if self.win.is_object_ref(bid):
            oid = self.win.ref_asset_id(bid)
            self._place_primitive_brush(cell, axis, oid)
            return
        if cell in sc.world:
            return
        sc.put(cell, bid)
        s["changes"].append(("block", cell, None, bid))

    def _place_primitive_brush(self, cell, axis, asset_id):
        sc = self.win.scene
        if asset_id not in sc.primitive_objects:
            return False
        if len(sc.object_instances) >= self.MAX_INSTANCES:
            return False
        if sc.object_instance_exists(asset_id, cell):
            return False
        iid = sc.add_object_instance(asset_id, cell)
        if iid:
            ins = dict(sc.object_instances.get(iid, {}))
            self.stroke["changes"].append(("objadd", ins))
            return True
        return False

    def stroke_to(self, pos, first=False):
        s = self.stroke
        if not s:
            return
        x, y = pos.x(), pos.y()
        if s["mode"] == "draw":
            if first:
                cell, axis = self.pick_place(x, y)
                s["axis"], s["layer"] = axis, cell[axis]
                self._place(cell, axis)
                s["last"] = cell
            else:
                a, layer = s["axis"], s["layer"]
                c = self.plane_cell(x, y, a, layer)
                last = s["last"]
                if c is None or c == last:
                    return
                i, j = [k for k in range(3) if k != a]
                n = min(max(abs(c[i] - last[i]), abs(c[j] - last[j])), 4000)
                if n == 0:
                    return
                for k in range(1, n + 1):
                    t = k / n
                    cc = [0, 0, 0]
                    cc[a] = layer
                    cc[i] = int(round(last[i] + (c[i] - last[i]) * t))
                    cc[j] = int(round(last[j] + (c[j] - last[j]) * t))
                    self._place(tuple(cc), a)
                s["last"] = c
        else:
            lp = s["lastpos"]
            dist = math.hypot(x - lp.x(), y - lp.y())
            steps = 1 if first else max(1, min(64, int(dist / 5)))
            for k in range(1, steps + 1):
                t = k / steps
                px = lp.x() + (x - lp.x()) * t if not first else x
                py = lp.y() + (y - lp.y()) * t if not first else y
                self._hit_apply(px, py)
            s["lastpos"] = pos

    def _hit_apply(self, px, py):
        s = self.stroke
        if not s:
            return
        sc = self.win.scene
        mesh_hit = None
        if s["mode"] in ("paint", "erase"):
            mesh_hit = self.raycast_primitives(px, py)

        # Boya: mesh öncelikli
        if s["mode"] == "paint" and mesh_hit is not None:
            self._paint_primitive_at(mesh_hit)
            self.win.on_world_changed(False)
            return

        # Sil: mesh yüzeyine isabet ederse yerleşik örneği kaldır
        if s["mode"] == "erase" and mesh_hit is not None:
            iid = mesh_hit[1]
            if iid:
                removed = sc.remove_object_instance(iid)
                if removed:
                    s["changes"].append(("objdel", removed))
                self.win.on_world_changed(False)
                return
            # Asset ana kopyası silinemez; küp moduna geç.
        hit = self.pick_hit(px, py)
        if not hit:
            return
        cell, n, _ = hit
        if s["mode"] == "erase":
            old = sc.remove(cell)
            if old is not None:
                s["changes"].append(("block", cell, old, None))
        else:
            axis = 0 if n[0] else (1 if n[1] else 2)
            u, v = plane_uv(cell, axis)
            s["path"] += 16.0
            bid = self.win.pick_brush_id(u, v, s["path"], s["seq"])
            s["seq"] += 1
            if self.win.is_object_ref(bid):
                self._place_primitive_brush((cell[0] + n[0], cell[1] + n[1], cell[2] + n[2]),
                                        axis, self.win.ref_asset_id(bid))
            else:
                old = sc.world.get(cell)
                if old is not None and old != bid:
                    sc.put(cell, bid)
                    s["changes"].append(("block", cell, old, bid))
        self.win.on_world_changed(False)

    def _paint_primitive_at(self, hit):
        asset_id, instance_id, mat_index, _, _, uv, _, wp, M = hit
        obj = self.win.scene.primitive_objects.get(asset_id)
        if obj is None or not obj.materials:
            return False
        mi = min(max(int(mat_index), 0), len(obj.materials) - 1)
        mat = obj.materials[mi]
        key = (asset_id, mi)
        if key not in self.stroke["object_paints"]:
            self.stroke["object_paints"][key] = (mat.base_image.copy(), list(mat.base_color))
        # Tuval yoksa oluştur (aktif fırça rengiyle)
        if mat.base_image.isNull():
            mat.ensure_canvas(color=self.win.brush_color())
        w, h = mat.base_image.width(), mat.base_image.height()
        x = int(max(0, min(w - 1, round(float(uv[0]) * (w - 1)))))
        y = int(max(0, min(h - 1, round((1.0 - float(uv[1])) * (h - 1)))))
        # Fırça yarıçapı: dünya fırça boyutundan tuval ölçeğine dönüştür
        brush_world = max(0.05, self.win.brush_size)
        obj_scale = float(np.mean(np.abs([M[0, 0], M[1, 1], M[2, 2]])))
        px_per_world = 1.0 / max(1e-6, obj_scale)
        # Yaklaşık ölçek: mesh bbox -> tuval
        bbox = float(np.max(obj.bounds_max - obj.bounds_min)) * obj_scale
        if bbox > 1e-6:
            px_per_world = w / bbox
        radius = max(2, int(brush_world * px_per_world))
        painter = QPainter(mat.base_image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
        painter.setPen(Qt.NoPen)
        c = self.win.brush_color()
        a = int(max(0, min(255, self.win.brush_alpha * 255)))
        c.setAlpha(a)
        painter.setBrush(c)
        painter.drawEllipse(QPoint(x, y), radius, radius)
        painter.end()
        mat.base_dirty = True
        mat.rev += 1
        self.win.modified = True
        self.win.update_title()
        self.win.update_status()
        return True

    def update_hover(self, pos, ctrl):
        mode = "erase" if ctrl else self.win.tool
        self.hover = None
        tnow = time.time()
        if tnow < self._hover_skip_until and mode == "draw":
            return
        if mode in ("paint", "erase"):
            mesh_hit = self.raycast_primitives(pos.x(), pos.y())
            if mode == "paint" and mesh_hit:
                _, _, _, _, _, _, _, wp, M = mesh_hit
                nrm = self._world_normal(mesh_hit)
                r = max(0.05, self.win.brush_size)
                self.hover = (("ring", wp, nrm, r), (1.0, 0.85, 0.2, 1.0))
                self.win.set_cursor_info("mesh yüzeyi")
                self.update()
                return
        if mode == "draw":
            cell, axis = self.pick_place(pos.x(), pos.y())
            if any(self.win.is_object_ref(x) for x in self.win.brush_ids):
                lo = np.array(cell, dtype=np.float64) - 0.5
                self.hover = (("box", lo, lo + 1.0), (0.35, 1.0, 0.35, 1.0))
            elif cell not in self.win.scene.world:
                self.hover = (("cell", cell), (0.35, 1.0, 0.35, 1.0))
        else:
            hit = self.pick_hit(pos.x(), pos.y())
            if hit:
                self.hover = (("cell", hit[0]), (1.0, 0.3, 0.3, 1.0) if mode == "erase" else (1.0, 0.85, 0.2, 1.0))
        self.win.set_cursor_info(self.hover[0][1] if self.hover and self.hover[0][0] == "cell" else None)
        self.update()

    def _world_normal(self, hit):
        """İsabet edilen mesh yüzeyinin dünya normali."""
        asset_id, instance_id, mi, pi, idx, uv, t, wp, M = hit
        obj = self.win.scene.primitive_objects.get(asset_id)
        if obj is None or pi >= len(obj.parts):
            return np.array([0.0, 1.0, 0.0])
        arr = obj.parts[pi]["arr"]
        base = idx * 3
        n_local = arr[base, 3:6].astype(np.float64)
        try:
            inv = np.linalg.inv(M)
            N = inv[:3, :3].T @ n_local
            ln = np.linalg.norm(N)
            if ln > 1e-9:
                N = N / ln
            return N
        except Exception:
            return np.array([0.0, 1.0, 0.0])

    # -- olaylar
    def mousePressEvent(self, e):
        self.setFocus()
        b = e.button()
        if b == Qt.LeftButton:
            mode = "erase" if (e.modifiers() & Qt.ControlModifier) else self.win.tool
            self.begin_stroke(e.pos(), mode)
            self.win.on_world_changed(False)
            self.update()
        elif b == Qt.MiddleButton:
            self.cam = True
            self.cam_last = e.pos()
        elif b == Qt.RightButton:
            self.win.show_cube_menu(e.globalPos())

    def mouseMoveEvent(self, e):
        pos = e.pos()
        if self.cam:
            dx, dy = pos.x() - self.cam_last.x(), pos.y() - self.cam_last.y()
            self.cam_last = pos
            if e.modifiers() & Qt.ShiftModifier:
                eye = self.eye()
                f = self.target - eye
                f = f / np.linalg.norm(f)
                right = np.cross(f, np.array([0.0, 1.0, 0.0]))
                right = right / np.linalg.norm(right)
                upv = np.cross(right, f)
                s = 2.0 * self.dist * math.tan(math.radians(self.fov) / 2.0) / max(1, self.height())
                self.target = self.target + (-right * dx + upv * dy) * s
            else:
                self.yaw -= dx * 0.009
                self.pitch = max(-1.5, min(1.5, self.pitch + dy * 0.009))
            self.update()
            return
        if self.stroke:
            try:
                self.stroke_to(pos)
            except Exception:
                traceback.print_exc()
                # Bozuk stroke kalmasın
                try:
                    self.end_stroke()
                except Exception:
                    self.stroke = None
            self.win.on_world_changed(False)
            self.update()
            return
        self.update_hover(pos, bool(e.modifiers() & Qt.ControlModifier))

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.stroke:
            self.end_stroke()
            self.update_hover(e.pos(), bool(e.modifiers() & Qt.ControlModifier))
        elif e.button() == Qt.MiddleButton:
            self.cam = None

    def leaveEvent(self, e):
        self.hover = None
        self.win.set_cursor_info(None)
        self.update()

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        self.dist = min(8000.0, max(0.6, self.dist * (0.88 ** (d / 120.0))))
        self.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Home:
            self.reset_camera()
        else:
            super().keyPressEvent(e)

    # -- OpenGL
    def initializeGL(self):
        self.tex = int(gl.glGenTextures(1))
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.tex)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_NEAREST)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_CLAMP_TO_EDGE)
        gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_CLAMP_TO_EDGE)
        gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
        gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, ATLAS, ATLAS, 0, gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, None)
        sc = self.win.scene
        sc.atlas_dirty = True
        sc.dead_vbos.clear()
        for m in sc.meshes.values():
            m.vbo = None
            m.upload = True
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_CULL_FACE)
        gl.glCullFace(gl.GL_BACK)
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        try:
            self.mesh_program = self._create_mesh_program()
            self._uloc = {}
            if self.mesh_program:
                names = ("u_base_color", "u_has_base_tex", "u_base_tex",
                         "u_metallic", "u_roughness", "u_ior", "u_alpha",
                         "u_emission", "u_emission_strength",
                         "u_coat_weight", "u_transmission",
                         "u_light_pos", "u_fill_pos", "u_instance_offset")
                self._uloc = {n: gl.glGetUniformLocation(self.mesh_program, n) for n in names}
        except Exception:
            self.mesh_program = None
            traceback.print_exc()

    def _compile_shader(self, kind, source):
        shader = gl.glCreateShader(kind)
        gl.glShaderSource(shader, source)
        gl.glCompileShader(shader)
        if not gl.glGetShaderiv(shader, gl.GL_COMPILE_STATUS):
            raise RuntimeError(str(gl.glGetShaderInfoLog(shader)))
        return shader

    def _create_mesh_program(self):
        if not hasattr(gl, "GL_VERTEX_SHADER"):
            return None
        vs = """#version 120
attribute vec3 a_pos;
attribute vec3 a_normal;
attribute vec2 a_uv;
attribute vec4 a_tangent;
uniform vec3 u_instance_offset;
varying vec3 v_pos;
varying vec3 v_normal;
varying vec2 v_uv;
void main(){
    vec3 p = a_pos + u_instance_offset;
    vec4 ep = gl_ModelViewMatrix * vec4(p, 1.0);
    v_pos = ep.xyz;
    v_normal = normalize(gl_NormalMatrix * a_normal);
    v_uv = a_uv;
    gl_Position = gl_ProjectionMatrix * ep;
}"""
        fs = """#version 120
uniform vec4 u_base_color;
uniform sampler2D u_base_tex;
uniform int u_has_base_tex;
uniform float u_metallic;
uniform float u_roughness;
uniform float u_ior;
uniform float u_alpha;
uniform vec3 u_emission;
uniform float u_emission_strength;
uniform float u_coat_weight;
uniform float u_transmission;
uniform vec3 u_light_pos;
uniform vec3 u_fill_pos;
varying vec3 v_pos;
varying vec3 v_normal;
varying vec2 v_uv;
void main(){
    vec4 texc = vec4(1.0);
    if(u_has_base_tex == 1) texc = texture2D(u_base_tex, v_uv);
    vec4 bc = texc * u_base_color;
    float alpha = clamp(bc.a * u_alpha, 0.0, 1.0);
    if(alpha < 0.01) discard;
    vec3 N = normalize(v_normal);
    vec3 V = normalize(-v_pos);
    float rough = clamp(u_roughness, 0.04, 1.0);
    float shin = mix(160.0, 6.0, rough);
    vec3 F0 = mix(vec3(0.04), bc.rgb, clamp(u_metallic, 0.0, 1.0));
    vec3 outc = bc.rgb * 0.10;
    vec3 L = normalize(u_light_pos - v_pos);
    float ndl = max(dot(N,L),0.0);
    vec3 H = normalize(L+V);
    float spec = pow(max(dot(N,H),0.0),shin);
    outc += bc.rgb * (1.0-u_metallic) * ndl * 0.85;
    outc += F0 * spec * (0.35 + 0.65*ndl);
    vec3 LF = normalize(u_fill_pos - v_pos);
    outc += bc.rgb * (1.0-u_metallic) * max(dot(N,LF),0.0) * 0.30;
    outc += u_emission * u_emission_strength;
    outc += F0 * 0.04 * u_coat_weight;
    gl_FragColor = vec4(clamp(outc,0.0,1.0), alpha);
}"""
        v = self._compile_shader(gl.GL_VERTEX_SHADER, vs)
        f = self._compile_shader(gl.GL_FRAGMENT_SHADER, fs)
        program = gl.glCreateProgram()
        gl.glAttachShader(program, v)
        gl.glAttachShader(program, f)
        gl.glBindAttribLocation(program, 0, "a_pos")
        gl.glBindAttribLocation(program, 1, "a_normal")
        gl.glBindAttribLocation(program, 2, "a_uv")
        gl.glBindAttribLocation(program, 3, "a_tangent")
        gl.glLinkProgram(program)
        if not gl.glGetProgramiv(program, gl.GL_LINK_STATUS):
            raise RuntimeError(str(gl.glGetProgramInfoLog(program)))
        gl.glDeleteShader(v)
        gl.glDeleteShader(f)
        return program

    def _upload_qimage_texture(self, img, old=None, full=True):
        if img.isNull():
            return old
        im = img.convertToFormat(QImage.Format_RGBA8888)
        raw = im.constBits().asstring(im.sizeInBytes())
        if old is None:
            tex = int(gl.glGenTextures(1))
            gl.glBindTexture(gl.GL_TEXTURE_2D, tex)
            gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MIN_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_MAG_FILTER, gl.GL_LINEAR)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_S, gl.GL_REPEAT)
            gl.glTexParameteri(gl.GL_TEXTURE_2D, gl.GL_TEXTURE_WRAP_T, gl.GL_REPEAT)
            gl.glTexImage2D(gl.GL_TEXTURE_2D, 0, gl.GL_RGBA, im.width(), im.height(), 0,
                            gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, raw)
            return tex
        else:
            gl.glBindTexture(gl.GL_TEXTURE_2D, old)
            gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
            gl.glTexSubImage2D(gl.GL_TEXTURE_2D, 0, 0, 0, im.width(), im.height(),
                               gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, raw)
            return old

    def _upload_imported(self):
        # Ölü kaynakları serbest bırak
        if GL_GARBAGE["buffers"]:
            try:
                gl.glDeleteBuffers(len(GL_GARBAGE["buffers"]), GL_GARBAGE["buffers"])
            except Exception:
                pass
            GL_GARBAGE["buffers"].clear()
        if GL_GARBAGE["textures"]:
            try:
                gl.glDeleteTextures(GL_GARBAGE["textures"])
            except Exception:
                pass
            GL_GARBAGE["textures"].clear()

        for obj in self.win.scene.primitive_objects.values():
            for part in obj.parts:
                if part.get("vbo") is None:
                    part["vbo"] = int(gl.glGenBuffers(1))
                    arr = np.ascontiguousarray(part["arr"], dtype=np.float32)
                    gl.glBindBuffer(gl.GL_ARRAY_BUFFER, part["vbo"])
                    gl.glBufferData(gl.GL_ARRAY_BUFFER, arr.nbytes, arr, gl.GL_STATIC_DRAW)
                ebuf = part.get("edges_vbo")
                edges = part.get("edges")
                if ebuf is None and edges is not None and len(edges):
                    ebuf = int(gl.glGenBuffers(1))
                    earr = np.ascontiguousarray(edges.reshape(-1, 3), dtype=np.float32)
                    gl.glBindBuffer(gl.GL_ARRAY_BUFFER, ebuf)
                    gl.glBufferData(gl.GL_ARRAY_BUFFER, earr.nbytes, earr, gl.GL_STATIC_DRAW)
                    part["edges_vbo"] = ebuf
            for mat in obj.materials:
                if mat.base_dirty:
                    if mat.base_gl is None:
                        mat.base_gl = self._upload_qimage_texture(mat.base_image, None)
                    else:
                        mat.base_gl = self._upload_qimage_texture(mat.base_image, mat.base_gl)
                    mat.base_dirty = False
                    mat.base_full_upload = False
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)

    def _draw_primitives(self):
        if not self.mesh_program:
            return
        sc = self.win.scene
        if not sc.primitive_objects:
            return
        self._upload_imported()
        program = self.mesh_program
        gl.glUseProgram(program)
        loc = self._uloc
        gl.glEnable(gl.GL_DEPTH_TEST)
        gl.glEnable(gl.GL_BLEND)
        gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
        gl.glUniform3f(loc["u_light_pos"], 3.5, 7.0, 5.0)
        gl.glUniform3f(loc["u_fill_pos"], -4.0, 2.0, -3.0)

        def bind_and_draw(obj, M, offset_world=None):
            gl.glPushMatrix()
            gl.glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
            for part in obj.parts:
                mi = min(max(int(part.get("material", 0)), 0), max(0, len(obj.materials) - 1))
                mat = obj.materials[mi] if obj.materials else PrimitiveMaterial()
                bc = (mat.base_color + [1.0] * 4)[:4]
                em = (mat.emission + [0.0] * 4)[:4]
                gl.glUniform4f(loc["u_base_color"], *[float(v) for v in bc])
                gl.glUniform1f(loc["u_metallic"], float(mat.metallic))
                gl.glUniform1f(loc["u_roughness"], float(mat.roughness))
                gl.glUniform1f(loc["u_ior"], float(mat.ior))
                gl.glUniform1f(loc["u_alpha"], float(mat.alpha))
                gl.glUniform3f(loc["u_emission"], float(em[0]), float(em[1]), float(em[2]))
                gl.glUniform1f(loc["u_emission_strength"], float(mat.emission_strength))
                gl.glUniform1f(loc["u_coat_weight"], float(mat.coat_weight))
                gl.glUniform1f(loc["u_transmission"], float(mat.transmission))
                has_base = 1 if mat.base_gl else 0
                gl.glUniform1i(loc["u_has_base_tex"], has_base)
                if has_base:
                    gl.glActiveTexture(gl.GL_TEXTURE0)
                    gl.glBindTexture(gl.GL_TEXTURE_2D, mat.base_gl)
                    gl.glUniform1i(loc["u_base_tex"], 0)
                gl.glBindBuffer(gl.GL_ARRAY_BUFFER, part["vbo"])
                stride = PrimitiveMesh.STRIDE * 4
                gl.glEnableVertexAttribArray(0)
                gl.glEnableVertexAttribArray(1)
                gl.glEnableVertexAttribArray(2)
                gl.glEnableVertexAttribArray(3)
                gl.glVertexAttribPointer(0, 3, gl.GL_FLOAT, gl.GL_FALSE, stride, ctypes.c_void_p(0))
                gl.glVertexAttribPointer(1, 3, gl.GL_FLOAT, gl.GL_FALSE, stride, ctypes.c_void_p(12))
                gl.glVertexAttribPointer(2, 2, gl.GL_FLOAT, gl.GL_FALSE, stride, ctypes.c_void_p(24))
                gl.glVertexAttribPointer(3, 4, gl.GL_FLOAT, gl.GL_FALSE, stride, ctypes.c_void_p(32))
                gl.glDrawArrays(gl.GL_TRIANGLES, 0, int(part["count"]))
                gl.glDisableVertexAttribArray(3)
                gl.glDisableVertexAttribArray(2)
                gl.glDisableVertexAttribArray(1)
                gl.glDisableVertexAttribArray(0)
            gl.glPopMatrix()

        # Asset ana kopyası (orijinde)
        for oid, obj in sc.primitive_objects.items():
            if not obj.visible:
                continue
            M = self._object_transform(obj)
            gl.glUniform3f(loc["u_instance_offset"], 0.0, 0.0, 0.0)
            bind_and_draw(obj, M)

        # Yerleşik örnekler: instans offset uniform ile
        max_inst = self.MAX_INSTANCES
        drawn = 0
        for iid, ins in sc.object_instances.items():
            if drawn >= max_inst:
                break
            asset_id = ins.get("asset")
            obj = sc.primitive_objects.get(asset_id)
            if obj is None or not obj.visible:
                continue
            M = euler_mesh_matrix([0.0, 0.0, 0.0], ins.get("rotation", [0, 0, 0]), ins.get("scale", [1, 1, 1]))
            p = ins.get("position", [0, 0, 0])
            gl.glUniform3f(loc["u_instance_offset"], float(p[0]), float(p[1]), float(p[2]))
            bind_and_draw(obj, M)
            drawn += 1

        # Kenar çizgileri (tüm asset ve instancelar için)
        gl.glUseProgram(0)
        gl.glDisable(gl.GL_TEXTURE_2D)
        gl.glColor4f(0.0, 0.0, 0.0, 0.55)
        gl.glLineWidth(1.0)
        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)

        def draw_edges(obj, M):
            gl.glPushMatrix()
            gl.glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
            for part in obj.parts:
                ebuf = part.get("edges_vbo")
                edges = part.get("edges")
                if not ebuf or edges is None or len(edges) == 0:
                    continue
                gl.glBindBuffer(gl.GL_ARRAY_BUFFER, ebuf)
                gl.glVertexPointer(3, gl.GL_FLOAT, 0, ctypes.c_void_p(0))
                gl.glDrawArrays(gl.GL_LINES, 0, int(len(edges) * 2))
            gl.glPopMatrix()

        for oid, obj in sc.primitive_objects.items():
            if not obj.visible:
                continue
            M = self._object_transform(obj)
            draw_edges(obj, M)
        for iid, ins in sc.object_instances.items():
            obj = sc.primitive_objects.get(ins.get("asset"))
            if obj is None or not obj.visible:
                continue
            M = self._object_transform(ins)
            draw_edges(obj, M)
        gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glActiveTexture(gl.GL_TEXTURE0)
        gl.glBindTexture(gl.GL_TEXTURE_2D, 0)

    def paintGL(self):
        try:
            self._paint()
        except Exception:
            err = traceback.format_exc()
            if err != self._last_err:
                self._last_err = err
                traceback.print_exc()

    def _upload(self):
        sc = self.win.scene
        if sc.atlas_dirty and self.tex:
            rows = max(TILE, sc.atlas_rows)
            data = np.frombuffer(sc.atlas.constBits().asstring(rows * ATLAS * 4), dtype=np.uint8)
            gl.glBindTexture(gl.GL_TEXTURE_2D, self.tex)
            gl.glPixelStorei(gl.GL_UNPACK_ALIGNMENT, 1)
            gl.glTexSubImage2D(gl.GL_TEXTURE_2D, 0, 0, 0, ATLAS, rows,
                               gl.GL_RGBA, gl.GL_UNSIGNED_BYTE, data)
            sc.atlas_dirty = False
        if sc.dead_vbos:
            for v in sc.dead_vbos:
                try:
                    gl.glDeleteBuffers(1, [int(v)])
                except Exception:
                    pass
            sc.dead_vbos.clear()
        for m in sc.meshes.values():
            if m.upload:
                if m.vbo is None:
                    m.vbo = int(gl.glGenBuffers(1))
                if m.count:
                    gl.glBindBuffer(gl.GL_ARRAY_BUFFER, m.vbo)
                    gl.glBufferData(gl.GL_ARRAY_BUFFER, m.arr.nbytes, m.arr, gl.GL_STATIC_DRAW)
                m.upload = False
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)

    def _grid(self):
        d = self.dist
        step = 1 if d < 40 else (8 if d < 320 else 64)
        half = int(min(max(d * 1.6, 24.0), 600.0) // step) * step
        cx = int(round(self.target[0] / step)) * step
        cz = int(round(self.target[2] / step)) * step
        xs = np.arange(cx - half, cx + half + 1, step, dtype=np.float32)
        zs = np.arange(cz - half, cz + half + 1, step, dtype=np.float32)
        a = np.zeros((len(xs), 2, 3), np.float32)
        a[:, :, 0] = xs[:, None]
        a[:, 0, 2] = zs[0]
        a[:, 1, 2] = zs[-1]
        b = np.zeros((len(zs), 2, 3), np.float32)
        b[:, :, 2] = zs[:, None]
        b[:, 0, 0] = xs[0]
        b[:, 1, 0] = xs[-1]
        return np.ascontiguousarray(np.concatenate([a.reshape(-1, 3), b.reshape(-1, 3)])), half

    def _lines(self, arr, color, width=1.0):
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glColor4f(*color)
        gl.glLineWidth(width)
        gl.glVertexPointer(3, gl.GL_FLOAT, 0, arr)
        gl.glDrawArrays(gl.GL_LINES, 0, len(arr))

    def _outline(self, cell, color):
        x, y, z = cell
        e = 0.004
        lo = (x - e, y - e, z - e)
        hi = (x + 1 + e, y + 1 + e, z + 1 + e)
        c = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], lo[1], hi[2]), (lo[0], lo[1], hi[2]),
             (lo[0], hi[1], lo[2]), (hi[0], hi[1], lo[2]), (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2])]
        ed = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        arr = np.array([c[i] for pair in ed for i in pair], dtype=np.float32)
        self._lines(arr, color, 2.5)

    def _outline_box(self, lo, hi, color):
        c = [(lo[0], lo[1], lo[2]), (hi[0], lo[1], lo[2]), (hi[0], lo[1], hi[2]), (lo[0], lo[1], hi[2]),
             (lo[0], hi[1], lo[2]), (hi[0], hi[1], lo[2]), (hi[0], hi[1], hi[2]), (lo[0], hi[1], hi[2])]
        ed = [(0, 1), (1, 2), (2, 3), (3, 0), (4, 5), (5, 6), (6, 7), (7, 4), (0, 4), (1, 5), (2, 6), (3, 7)]
        arr = np.array([c[i] for pair in ed for i in pair], dtype=np.float32)
        self._lines(arr, color, 2.0)

    def _paint(self):
        sc = self.win.scene
        dpr = self.devicePixelRatioF()
        gl.glViewport(0, 0, int(self.width() * dpr), int(self.height() * dpr))
        gl.glClearColor(0.2, 0.2, 0.2, 1.0)
        gl.glClear(gl.GL_COLOR_BUFFER_BIT | gl.GL_DEPTH_BUFFER_BIT)
        sc.rebuild_dirty()
        self._upload()
        P, V = self.matrices()
        gl.glMatrixMode(gl.GL_PROJECTION)
        gl.glLoadMatrixf(np.ascontiguousarray(P.T, dtype=np.float32))
        gl.glMatrixMode(gl.GL_MODELVIEW)
        gl.glLoadMatrixf(np.ascontiguousarray(V.T, dtype=np.float32))
        gl.glEnable(gl.GL_DEPTH_TEST)

        # küpler
        gl.glEnable(gl.GL_TEXTURE_2D)
        gl.glBindTexture(gl.GL_TEXTURE_2D, self.tex)
        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
        gl.glEnableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glEnableClientState(gl.GL_COLOR_ARRAY)
        for m in sc.meshes.values():
            if not m.count or not m.vbo:
                continue
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, m.vbo)
            gl.glVertexPointer(3, gl.GL_FLOAT, 32, ctypes.c_void_p(0))
            gl.glTexCoordPointer(2, gl.GL_FLOAT, 32, ctypes.c_void_p(12))
            gl.glColorPointer(3, gl.GL_FLOAT, 32, ctypes.c_void_p(20))
            gl.glDrawArrays(gl.GL_QUADS, 0, m.count)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glDisableClientState(gl.GL_COLOR_ARRAY)
        gl.glDisableClientState(gl.GL_TEXTURE_COORD_ARRAY)
        gl.glDisable(gl.GL_TEXTURE_2D)

        # temel şekil nesneleri
        self._draw_primitives()

        # zemin ızgarası
        gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
        grid, half = self._grid()
        self._lines(grid, (1.0, 1.0, 1.0, 0.10))
        ax = np.array([(-half, 0, 0), (half, 0, 0)], dtype=np.float32)
        az = np.array([(0, 0, -half), (0, 0, half)], dtype=np.float32)
        self._lines(ax, (1.0, 0.3, 0.3, 0.55), 1.5)
        self._lines(az, (0.35, 0.5, 1.0, 0.55), 1.5)

        if self.hover:
            kind, color = self.hover
            if kind[0] == "cell":
                self._outline(kind[1], color)
            elif kind[0] == "box":
                self._outline_box(kind[1], kind[2], color)
            elif kind[0] == "ring":
                wp = kind[1]
                nrm = kind[2]
                r = kind[3]
                self._draw_brush_ring(wp, nrm, r, color)
        gl.glDisableClientState(gl.GL_VERTEX_ARRAY)

    def _draw_brush_ring(self, wp, nrm, r, color):
        n = np.asarray(nrm, dtype=np.float64)
        ln = np.linalg.norm(n)
        if ln < 1e-9:
            return
        n /= ln
        up = np.array([0.0, 1.0, 0.0])
        if abs(np.dot(n, up)) > 0.9:
            up = np.array([1.0, 0.0, 0.0])
        t1 = np.cross(up, n)
        t1 /= max(1e-9, np.linalg.norm(t1))
        t2 = np.cross(n, t1)
        segs = 32
        pts = []
        for i in range(segs + 1):
            a = 2.0 * math.pi * i / segs
            p = wp + (t1 * math.cos(a) + t2 * math.sin(a)) * r * 1.02 + n * 0.005
            pts.append(p)
        arr = np.array(pts, dtype=np.float32)
        gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
        gl.glColor4f(*color)
        gl.glLineWidth(2.0)
        gl.glVertexPointer(3, gl.GL_FLOAT, 0, arr)
        gl.glDrawArrays(gl.GL_LINE_STRIP, 0, len(arr))


# ----------------------------------------------------------------------------
# Küp listesi bileşeni
# ----------------------------------------------------------------------------
class CubeListWidget(QWidget):
    picked = pyqtSignal(str, bool)
    context = pyqtSignal(str, QPoint)

    def __init__(self, win, cols=0, size=40, parent=None):
        super().__init__(parent)
        self.win, self.cols, self.size = win, cols, size
        self.gap, self.pad = 4, 4
        self.hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.refresh()

    def refresh(self):
        n = len(self.win.order)
        c = max(1, n) if self.cols == 0 else self.cols
        rows = 1 if self.cols == 0 else max(1, -(-n // self.cols))
        cell = self.size + self.gap
        self.setFixedSize(self.pad * 2 + c * cell, self.pad * 2 + rows * cell)
        self.update()

    def _rect(self, i):
        cell = self.size + self.gap
        col, row = (i, 0) if self.cols == 0 else (i % self.cols, i // self.cols)
        return QRect(self.pad + col * cell, self.pad + row * cell, self.size, self.size)

    def _index_at(self, pos):
        for i in range(len(self.win.order)):
            if self._rect(i).contains(pos):
                return i
        return -1

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), QColor("#262626"))
        brush = self.win.brush_ids
        for i, cid in enumerate(self.win.order):
            r = self._rect(i)
            if i == self.hover:
                p.setBrush(QColor("#444"))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(r, 6, 6)
            if cid in brush:
                p.setBrush(Qt.NoBrush)
                p.setPen(QPen(QColor("#ffffff") if cid == brush[0] else QColor("#4fa3ff"), 2))
                p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 6, 6)
            pm = self.win.thumb(cid, self.size - 6)
            p.drawPixmap(r.x() + 3, r.y() + 3, pm)

    def mouseMoveEvent(self, e):
        i = self._index_at(e.pos())
        if i != self.hover:
            self.hover = i
            self.setToolTip(self.win.brush_name(self.win.order[i]) if i >= 0 else "")
            self.update()

    def leaveEvent(self, e):
        self.hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._index_at(e.pos())
        if i < 0:
            return
        cid = self.win.order[i]
        if e.button() == Qt.LeftButton:
            self.picked.emit(cid, bool(e.modifiers() & Qt.ControlModifier))
        elif e.button() == Qt.RightButton:
            self.context.emit(cid, e.globalPos())

    def wheelEvent(self, e):
        p = self.parentWidget()
        while p is not None and not isinstance(p, QScrollArea):
            p = p.parentWidget()
        if p is not None:
            bar = p.horizontalScrollBar() if self.cols == 0 else p.verticalScrollBar()
            bar.setValue(bar.value() - e.angleDelta().y())
        e.accept()


class AngleButton(QPushButton):
    wheel = pyqtSignal(int)

    def wheelEvent(self, e):
        self.wheel.emit(15 if e.angleDelta().y() > 0 else -15)
        e.accept()


# ----------------------------------------------------------------------------
# Döndürülebilir küp önizleme widget'ı
# ----------------------------------------------------------------------------
def _uv_face_corners(idx):
    """idx: 0..5 -> üçgen sırası (piksel UV uzayı, sol-üst = 0,0)."""
    # Her yüz için iki üçgen: (u,v) köşeleri
    corners = [
        # +X
        [(1, 1), (1, 0), (1, 0), (1, 0), (1, 1), (1, 1)],
    ]
    return corners


class RotatableCubePreview(QWidget):
    """Güvenli 3B küp önizlemesi.

    Görünür yüzler ortografik olarak izdüşürülür. Her yüz paralelkenar olduğu için
    QTransform ile basit affine doku eşleme kullanılır; Qt projektif dönüşümüne bağımlı değildir.
    """
    facePicked = pyqtSignal(int)

    FACE_DEFS = [
        (0, [(0.5, -0.5, 0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (0.5, 0.5, 0.5)]),
        (1, [(-0.5, -0.5, -0.5), (-0.5, -0.5, 0.5), (-0.5, 0.5, 0.5), (-0.5, 0.5, -0.5)]),
        (2, [(-0.5, 0.5, 0.5), (0.5, 0.5, 0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5)]),
        (3, [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, -0.5, 0.5), (-0.5, -0.5, 0.5)]),
        (4, [(-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]),
        (5, [(0.5, -0.5, -0.5), (-0.5, -0.5, -0.5), (-0.5, 0.5, -0.5), (0.5, 0.5, -0.5)]),
    ]

    def __init__(self, faces, parent=None):
        super().__init__(parent)
        self.faces = list(faces) if faces else [solid_image('#ffffff') for _ in range(6)]
        self.yaw = 35.0
        self.pitch = 25.0
        self.zoom = 1.0
        self.last = None
        self._drag = False
        self.setMinimumSize(180, 180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.OpenHandCursor)
        self.setMouseTracking(True)

    def set_faces(self, faces):
        self.faces = list(faces) if faces else [solid_image('#ffffff') for _ in range(6)]
        self.update()

    def wheelEvent(self, e):
        steps = e.angleDelta().y() / 120.0
        self.zoom = max(0.35, min(4.0, self.zoom * (1.15 ** steps)))
        self.update()
        e.accept()

    def mousePressEvent(self, e):
        if e.button() == Qt.MiddleButton:
            # Orta tuş: önizlemeyi döndür
            self.last = e.pos()
            self.setCursor(Qt.ClosedHandCursor)
            e.accept()
        elif e.button() == Qt.LeftButton:
            # Sol tık: yüz seç (döndürme yok)
            fi = self._hit_face_at(e.pos())
            if fi >= 0:
                self.facePicked.emit(fi)
            e.accept()
        else:
            e.ignore()

    def mouseMoveEvent(self, e):
        if self.last is None:
            e.ignore()
            return
        dx = e.pos().x() - self.last.x()
        dy = e.pos().y() - self.last.y()
        self.yaw = (self.yaw + dx * 0.7) % 360.0
        self.pitch = max(-89.0, min(89.0, self.pitch + dy * 0.7))
        self.last = e.pos()
        self.update()
        e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MiddleButton:
            self.last = None
            self.setCursor(Qt.OpenHandCursor)
            e.accept()
        else:
            e.ignore()

    def _rotation(self):
        yaw = math.radians(self.yaw)
        pitch = math.radians(self.pitch)
        cy, sy = math.cos(yaw), math.sin(yaw)
        cx, sx = math.cos(pitch), math.sin(pitch)
        ry = np.array([[cy, 0.0, sy], [0.0, 1.0, 0.0], [-sy, 0.0, cy]], dtype=np.float64)
        rx = np.array([[1.0, 0.0, 0.0], [0.0, cx, -sx], [0.0, sx, cx]], dtype=np.float64)
        return ry @ rx

    def _project(self, v, w, h):
        q = self._rotation() @ np.asarray(v, dtype=np.float64)
        scale = min(w, h) * 0.36 * self.zoom
        return (w * 0.5 + q[0] * scale, h * 0.5 - q[1] * scale, q[2])

    @staticmethod
    def _path_for_polygon(pts):
        from PyQt5.QtGui import QPainterPath
        path = QPainterPath()
        path.moveTo(pts[0])
        for pt in pts[1:]:
            path.lineTo(pt)
        path.closeSubpath()
        return path

    def _draw_face(self, painter, fi, pts):
        if not 0 <= fi < len(self.faces):
            return
        img = self.faces[fi]
        if img is None or img.isNull() or len(pts) != 4:
            return
        p0 = QPointF(pts[0][0], pts[0][1])
        p1 = QPointF(pts[1][0], pts[1][1])
        p3 = QPointF(pts[3][0], pts[3][1])
        du = QPointF(p1.x() - p0.x(), p1.y() - p0.y())
        dv = QPointF(p3.x() - p0.x(), p3.y() - p0.y())
        if abs(du.x() * dv.y() - du.y() * dv.x()) < 1e-5:
            return
        tr = QTransform(
            du.x() / TILE, du.y() / TILE,
            dv.x() / TILE, dv.y() / TILE,
            p0.x(), p0.y()
        )
        poly = QPolygonF([QPointF(x, y) for x, y, _ in pts])
        painter.save()
        try:
            painter.setClipPath(self._path_for_polygon(poly))
            painter.setTransform(tr, True)
            painter.setRenderHint(QPainter.SmoothPixmapTransform, False)
            painter.drawImage(0, 0, img)
        finally:
            painter.restore()
        # Side shading gives a stable 3D read without relying on OpenGL.
        shade_alpha = (fi in (0, 1, 3, 5)) * 55 + (fi == 4) * 20
        if shade_alpha:
            painter.save()
            try:
                painter.setPen(Qt.NoPen)
                painter.setBrush(QColor(0, 0, 0, int(shade_alpha)))
                painter.drawPolygon(poly)
            finally:
                painter.restore()
        painter.setPen(QPen(QColor(0, 0, 0, 110), 1.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawPolygon(poly)

    def _visible_faces(self, w, h):
        out = []
        for fi, verts in self.FACE_DEFS:
            pts = [self._project(v, w, h) for v in verts]
            zavg = sum(p[2] for p in pts) / 4.0
            out.append((zavg, fi, pts))
        out.sort(key=lambda x: x[0])
        return out

    def _hit_face_at(self, pos):
        candidates = []
        for zavg, fi, pts in self._visible_faces(self.width(), self.height()):
            if zavg < -0.02:
                continue
            poly = QPolygonF([QPointF(x, y) for x, y, _ in pts])
            if poly.containsPoint(pos, Qt.OddEvenFill):
                candidates.append((zavg, fi))
        if not candidates:
            return -1
        return max(candidates, key=lambda x: x[0])[1]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        try:
            painter.fillRect(self.rect(), QColor('#202020'))
            faces = self._visible_faces(self.width(), self.height())
            for zavg, fi, pts in faces:
                # Back-facing polygons are still used as depth context, but only
                # visible faces receive their texture; this avoids reversed texturing.
                if zavg >= -0.18:
                    self._draw_face(painter, fi, pts)
                else:
                    poly = QPolygonF([QPointF(x, y) for x, y, _ in pts])
                    painter.setPen(QPen(QColor(0, 0, 0, 70), 1))
                    painter.setBrush(QColor(35, 35, 35))
                    painter.drawPolygon(poly)
            painter.setPen(QPen(QColor(255, 255, 255, 70), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 6, 6)
        finally:
            painter.end()


# ----------------------------------------------------------------------------
# Küp editörü
# ----------------------------------------------------------------------------
class PixelCanvas(QWidget):
    CELL = 22

    def __init__(self, dlg):
        super().__init__()
        self.dlg = dlg
        self.last = None
        self.setFixedSize(TILE * self.CELL, TILE * self.CELL)
        self.setCursor(Qt.CrossCursor)

    def _cell(self, pos):
        x, y = pos.x() // self.CELL, pos.y() // self.CELL
        if 0 <= x < TILE and 0 <= y < TILE:
            return x, y
        return None

    def paintEvent(self, e):
        p = QPainter(self)
        p.drawImage(QRect(0, 0, self.width(), self.height()), self.dlg.faces[self.dlg.cur_face])
        p.setPen(QPen(QColor(0, 0, 0, 70), 1))
        for i in range(TILE + 1):
            p.drawLine(i * self.CELL, 0, i * self.CELL, self.height())
            p.drawLine(0, i * self.CELL, self.width(), i * self.CELL)

    @staticmethod
    def _line(a, b):
        x0, y0 = a
        x1, y1 = b
        dx, dy = abs(x1 - x0), abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        while True:
            yield x0, y0
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy

    def mousePressEvent(self, e):
        c = self._cell(e.pos())
        if c is None:
            return
        if e.button() == Qt.LeftButton:
            if self.dlg.tool == "fill":
                self.dlg.flood(*c)
            else:
                self.dlg.begin_stroke()
                self.dlg.apply_pixel(*c)
                self.last = c
        elif e.button() == Qt.RightButton:
            self.dlg.eyedrop(*c)
        self.update()

    def mouseMoveEvent(self, e):
        if (e.buttons() & Qt.LeftButton) and self.dlg.tool == "pen" and self.last is not None:
            c = self._cell(e.pos())
            if c is not None and c != self.last:
                for x, y in self._line(self.last, c):
                    self.dlg.apply_pixel(x, y)
                self.last = c
                self.update()

    def mouseReleaseEvent(self, e):
        self.last = None


class CubeEditorDialog(QDialog):
    FACE_BUTTONS = [(2, "Üst"), (4, "Ön"), (0, "Sağ"), (5, "Arka"), (1, "Sol"), (3, "Alt")]

    def __init__(self, win, faces, name, editing, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Küp Editörü")
        self.win = win
        self.faces = faces
        self.editing = editing
        self.as_new = False
        self.name = name
        self.cur_face = 2
        self.tool = "pen"
        self.mix_colors = [QColor(c) for c in win.mix_colors]
        self.mix_history = [[QColor(c) for c in h] for h in win.mix_history]
        self.pen_color = QColor(self.mix_colors[0])
        self.mix_mode = win.ed_mix_mode
        self.mix_angle = win.ed_mix_angle
        self.seq = 0
        self.step = 0.0

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        root.addLayout(left, 0)
        self.canvas = PixelCanvas(self)
        left.addWidget(self.canvas, 0, Qt.AlignTop)

        side = QVBoxLayout()
        root.addLayout(side, 1)

        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("Küp adı")
        side.addWidget(self.name_edit)

        # Döndürülebilir önizleme
        self.preview = RotatableCubePreview(self.faces)
        self.preview.facePicked.connect(self.set_face)
        self.preview.setMinimumHeight(240)
        side.addWidget(self.preview, 1)
        hint = QLabel("Orta tuşla sürükleyerek döndürün · tekerlek: yakınlaş · yüz seçmek için sol tık")
        hint.setStyleSheet("color:#aaa; font-size: 11px;")
        side.addWidget(hint)

        grid = QGridLayout()
        self.face_btns = {}
        for k, (fi, label) in enumerate(self.FACE_BUTTONS):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setFocusPolicy(Qt.NoFocus)
            b.setStyleSheet(btn_style(False, 13))
            b.clicked.connect(lambda _c, f=fi: self.set_face(f))
            grid.addWidget(b, k // 3, k % 3)
            self.face_btns[fi] = b
        side.addLayout(grid)
        self.all_faces = QCheckBox("Tüm yüzlere aynı anda boya")
        side.addWidget(self.all_faces)

        row = QHBoxLayout()
        self.color_button = QPushButton()
        self.color_button.setStyleSheet(btn_style(False, 13))
        self.color_menu = QMenu(self)
        self.color_menu.setStyleSheet(MENU_STYLE)
        self.color_button.setMenu(self.color_menu)
        row.addWidget(self.color_button)
        self.mix_button = QPushButton()
        self.mix_button.setStyleSheet(btn_style(False, 13))
        self.mix_button.clicked.connect(self.show_mix_menu)
        row.addWidget(self.mix_button)
        side.addLayout(row)

        row = QHBoxLayout()
        self.angle_button = AngleButton()
        self.angle_button.setStyleSheet(btn_style(False, 13))
        self.angle_button.clicked.connect(lambda: self.change_angle(15))
        self.angle_button.wheel.connect(self.change_angle)
        row.addWidget(self.angle_button)
        self.pen_btn = QPushButton("Kalem")
        self.fill_btn = QPushButton("Dolgu")
        for b, t in ((self.pen_btn, "pen"), (self.fill_btn, "fill")):
            b.setFocusPolicy(Qt.NoFocus)
            b.clicked.connect(lambda _c, tt=t: self.set_tool(tt))
            row.addWidget(b)
        side.addLayout(row)

        row = QHBoxLayout()
        fill_all = QPushButton("Yüzü Doldur")
        fill_all.clicked.connect(self.fill_face)
        copy_all = QPushButton("Yüzü Hepsine Kopyala")
        copy_all.clicked.connect(self.copy_face_to_all)
        for b in (fill_all, copy_all):
            b.setStyleSheet(btn_style(False, 12))
            b.setFocusPolicy(Qt.NoFocus)
            row.addWidget(b)
        side.addLayout(row)

        row = QHBoxLayout()
        ok = QPushButton("Kaydet" if editing else "Listeye Ekle")
        ok.clicked.connect(self._ok)
        row.addWidget(ok)
        if editing:
            new = QPushButton("Yeni Küp Olarak Ekle")
            new.clicked.connect(self._ok_new)
            row.addWidget(new)
        cancel = QPushButton("İptal")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        side.addLayout(row)

        self.set_face(2)
        self.set_tool("pen")
        self.update_color_menu()
        self.update_labels()
        self.refresh_preview()

    def set_face(self, f):
        self.cur_face = f
        for fi, b in self.face_btns.items():
            b.setChecked(fi == f)
            b.setStyleSheet(btn_style(fi == f, 13))
        self.canvas.update()

    def set_tool(self, t):
        self.tool = t
        self.pen_btn.setStyleSheet(btn_style(t == "pen", 13))
        self.fill_btn.setStyleSheet(btn_style(t == "fill", 13))

    def update_labels(self):
        self.color_button.setText(f"Renk ({len(self.mix_colors)})")
        self.mix_button.setText(f"Karışım: {MIX_SHORT.get(self.mix_mode, '')}")
        self.angle_button.setText(f"Açı {self.mix_angle}°")
        sw = QPixmap(14, 14)
        sw.fill(self.pen_color)
        self.color_button.setIcon(QIcon(sw))

    def refresh_preview(self):
        self.preview.set_faces(self.faces)
        self.canvas.update()

    def change_angle(self, d):
        self.mix_angle = (self.mix_angle + d) % 360
        self.update_labels()

    def target_faces(self):
        return range(6) if self.all_faces.isChecked() else [self.cur_face]

    def mix_color(self, x, y):
        cols = self.mix_colors
        i, j, fr = mix_select(len(cols), self.mix_mode, x * 16, y * 16, self.step, self.mix_angle, self.seq)
        self.seq += 1
        self.step += 16.0
        a, b = cols[i], cols[j]
        if i == j or fr <= 0:
            return QColor(a)
        return QColor(int(a.red() + (b.red() - a.red()) * fr),
                      int(a.green() + (b.green() - a.green()) * fr),
                      int(a.blue() + (b.blue() - a.blue()) * fr))

    def begin_stroke(self):
        self.step = 0.0

    def apply_pixel(self, x, y):
        col = self.mix_color(x, y)
        for f in self.target_faces():
            self.faces[f].setPixelColor(x, y, col)
        self.refresh_preview()

    def eyedrop(self, x, y):
        c = self.faces[self.cur_face].pixelColor(x, y)
        c.setAlpha(255)
        self.pen_color = QColor(c)
        self.mix_colors = [QColor(c)]
        self.update_labels()

    def flood(self, x, y):
        img = self.faces[self.cur_face]
        target = img.pixel(x, y)
        seen, stack = set(), [(x, y)]
        self.begin_stroke()
        while stack:
            cx, cy = stack.pop()
            if (cx, cy) in seen or not (0 <= cx < TILE and 0 <= cy < TILE) or img.pixel(cx, cy) != target:
                continue
            seen.add((cx, cy))
            stack.extend([(cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)])
        for cx, cy in sorted(seen):
            self.apply_pixel(cx, cy)
        self.refresh_preview()

    def fill_face(self):
        self.begin_stroke()
        for y in range(TILE):
            for x in range(TILE):
                self.apply_pixel(x, y)
        self.refresh_preview()

    def copy_face_to_all(self):
        src = self.faces[self.cur_face]
        for f in range(6):
            if f != self.cur_face:
                self.faces[f] = src.copy()
        self.refresh_preview()

    def _push_history(self):
        h = [QColor(c) for c in self.mix_colors]
        if not self.mix_history or [c.name() for c in self.mix_history[-1]] != [c.name() for c in h]:
            self.mix_history.append(h)
            if len(self.mix_history) > 24:
                self.mix_history.pop(0)

    def change_color(self):
        dlg = CircleBrightnessDialog(initialColor=self.pen_color, parent=self)
        dlg.move(self.color_button.mapToGlobal(QPoint(0, self.color_button.height())))
        if dlg.exec_():
            sel = dlg.getSelectedColor()
            self.pen_color = sel
            self.mix_colors = [sel]
            self._push_history()
            self.update_color_menu()
            self.update_labels()

    def add_color_to_mix(self):
        dlg = CircleBrightnessDialog(initialColor=self.pen_color, parent=self)
        dlg.move(self.color_button.mapToGlobal(QPoint(0, self.color_button.height())))
        if dlg.exec_():
            sel = dlg.getSelectedColor()
            if len(self.mix_colors) >= 6:
                self.mix_colors.pop(0)
            self.mix_colors.append(sel)
            self.pen_color = sel
            self._push_history()
            self.update_color_menu()
            self.update_labels()

    def update_color_menu(self):
        m = self.color_menu
        m.clear()
        m.addAction("Tek Renk Seç").triggered.connect(self.change_color)
        m.addAction("Karışıma Renk Ekle (+)").triggered.connect(self.add_color_to_mix)
        m.addSeparator()
        wa = QWidgetAction(m)
        lab = QLabel("  Renk Geçmişi:", m)
        lab.setStyleSheet("color: #aaa; font-weight: bold; padding: 2px 5px;")
        wa.setDefaultWidget(lab)
        m.addAction(wa)
        for colors in reversed(self.mix_history):
            wa = QWidgetAction(m)
            strip = ColorHistoryStrip(colors)
            strip.colorSelected.connect(self.on_history_selected)
            wa.setDefaultWidget(strip)
            m.addAction(wa)

    def on_history_selected(self, single, mix):
        if single:
            self.pen_color = QColor(single)
            self.mix_colors = [QColor(single)]
        elif mix:
            self.mix_colors = [QColor(c) for c in mix]
            self.pen_color = QColor(mix[0])
        self.color_menu.close()
        self.update_labels()

    def show_mix_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        menu.addAction("--- Karışım Modları ---").setEnabled(False)
        for label, key in MIX_MODES:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.mix_mode == key)
            act.triggered.connect(lambda _c, k=key: self._set_mix_mode(k))
        menu.addSeparator()
        menu.addAction(f"--- Aktif Karışım Renkleri ({len(self.mix_colors)}) ---").setEnabled(False)
        wa = QWidgetAction(menu)
        strip = ColorHistoryStrip(self.mix_colors)
        strip.colorSelected.connect(self.on_history_selected)
        wa.setDefaultWidget(strip)
        menu.addAction(wa)
        menu.exec_(self.mix_button.mapToGlobal(QPoint(0, self.mix_button.height())))

    def _set_mix_mode(self, k):
        self.mix_mode = k
        self.update_labels()

    def _ok(self):
        self.name = self.name_edit.text().strip() or "Küp"
        self.accept()

    def _ok_new(self):
        self.as_new = True
        self._ok()

    def done(self, r):
        self.win.mix_colors = [QColor(c) for c in self.mix_colors]
        self.win.mix_history = self.mix_history
        self.win.ed_mix_mode = self.mix_mode
        self.win.ed_mix_angle = self.mix_angle
        super().done(r)


class PrimitiveCreateDialog(QDialog):
    """Yeni yerleşik temel şekil oluşturma penceresi."""
    def __init__(self, win, default_kind="cube", parent=None):
        super().__init__(parent)
        self.win = win
        self.setWindowTitle("Yeni Temel Şekil")
        self.resize(420, 250)
        root = QVBoxLayout(self)

        form = QFormLayout()
        self.kind_box = QComboBox()
        self.kind_box.addItem("Küp", "cube")
        self.kind_box.addItem("Silindir", "cylinder")
        self.kind_box.addItem("Koni", "cone")
        self.kind_box.addItem("Küre", "sphere")
        self.kind_box.addItem("Piramit", "pyramid")
        for i in range(self.kind_box.count()):
            if self.kind_box.itemData(i) == default_kind:
                self.kind_box.setCurrentIndex(i)
                break
        form.addRow("Şekil:", self.kind_box)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Örn. Mavi Silindir")
        form.addRow("Ad:", self.name_edit)

        self.segments = QSpinBox()
        self.segments.setRange(8, 64)
        self.segments.setValue(32)
        self.segments.setSingleStep(4)
        form.addRow("Yuvarlaklık:", self.segments)
        root.addLayout(form)

        row = QHBoxLayout()
        row.addWidget(QLabel("Renk:"))
        self.color = QColor(BUILTIN_COLORS.get(default_kind, '#ffffff'))
        self.color_button = QPushButton()
        self.color_button.clicked.connect(self.pick_color)
        row.addWidget(self.color_button, 1)
        root.addLayout(row)
        self._update_color_button()

        hint = QLabel("Şekil sahneye eklendikten sonra liste üzerinden seçilip istediğiniz yere yerleştirilebilir.\nS ile ölçekleyebilir, R ile döndürebilir, Boya aracıyla yüzeyini renklendirebilirsiniz.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#aaa; padding:6px;")
        root.addWidget(hint)

        buttons = QHBoxLayout()
        ok = QPushButton("Oluştur")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("İptal")
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1); buttons.addWidget(ok); buttons.addWidget(cancel)
        root.addLayout(buttons)

    def _update_color_button(self):
        pm = QPixmap(18,18)
        pm.fill(self.color)
        self.color_button.setIcon(QIcon(pm))
        self.color_button.setText(self.color.name().upper())
        self.color_button.setStyleSheet(f"QPushButton {{ background:{self.color.name()}; color:{'#000' if self.color.lightness()>150 else '#fff'}; border:1px solid #666; border-radius:6px; padding:5px; }}")

    def pick_color(self):
        dlg = CircleBrightnessDialog(self.color, self)
        dlg.move(self.color_button.mapToGlobal(QPoint(0, self.color_button.height())))
        if dlg.exec_():
            self.color = dlg.getSelectedColor()
            self._update_color_button()

    def values(self):
        kind = self.kind_box.currentData()
        default_name = dict(BUILTIN_PRIMITIVES)[kind]
        return kind, (self.name_edit.text().strip() or default_name), self.color, int(self.segments.value())


class PrimitiveObjectDialog(QDialog):
    """temel şekil ayarları — sadece geometri/UV yönetimi ve boya tuvali."""
    def __init__(self, win, obj, parent=None):
        super().__init__(parent)
        self.win, self.obj = win, obj
        self.setWindowTitle(f"Temel Şekil — {obj.name}")
        self.resize(560, 480)
        root = QVBoxLayout(self)

        row = QHBoxLayout()
        row.addWidget(QLabel("Ad:"))
        self.object_name = QLineEdit(obj.name)
        row.addWidget(self.object_name, 1)
        self.visible = QCheckBox("Görünür")
        self.visible.setChecked(obj.visible)
        row.addWidget(self.visible)
        root.addLayout(row)

        self.color_button = QPushButton("Seçili yüzey rengini değiştir")
        self.color_button.clicked.connect(self.choose_material_color)
        root.addWidget(self.color_button)

        self.material_list = QListWidget()
        for mat in obj.materials:
            tex = " · tuval" if not mat.base_image.isNull() else ""
            self.material_list.addItem(f"◆ {mat.name}{tex}")
        root.addWidget(self.material_list, 1)

        info = QLabel(
            "Bu nesne uygulamanın yerleşik temel şeklidir.\n"
            "Rengini seçebilir, yüzey tuvali oluşturabilir ve Boya aracıyla doğrudan yüzey üzerinde çalışabilirsiniz."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color:#bbb; background:#1e1e1e; padding:8px; border-radius:4px;")
        root.addWidget(info)

        row = QHBoxLayout()
        pick = QPushButton("Seçili yuva rengini boya ile doldur")
        pick.clicked.connect(self.fill_with_brush)
        row.addWidget(pick)
        reset = QPushButton("Seçili yuvanın tuvalini temizle")
        reset.clicked.connect(self.reset_canvas)
        row.addWidget(reset)
        regen = QPushButton("UV'yi yeniden üret")
        regen.clicked.connect(self.regen_uv)
        row.addWidget(regen)
        root.addLayout(row)

        self.uv_info = QLabel("")
        self.uv_info.setWordWrap(True)
        self.uv_info.setStyleSheet("color:#aaa; font-size: 11px;")
        root.addWidget(self.uv_info)
        self.material_list.currentRowChanged.connect(self.update_uv_info)
        if obj.materials:
            self.material_list.setCurrentRow(0)

        row = QHBoxLayout()
        ok = QPushButton("Tamam")
        ok.clicked.connect(self._accept)
        cancel = QPushButton("İptal")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        root.addLayout(row)

    def choose_material_color(self):
        mi = self._current_mi()
        if mi < 0 or mi >= len(self.obj.materials):
            return
        mat = self.obj.materials[mi]
        initial = mat.base_image.pixelColor(mat.base_image.width() // 2, mat.base_image.height() // 2) if not mat.base_image.isNull() else mat.color()
        dlg = CircleBrightnessDialog(initial, self)
        dlg.move(self.color_button.mapToGlobal(QPoint(0, self.color_button.height())))
        if dlg.exec_():
            c = dlg.getSelectedColor()
            mat.base_image = QImage(mat.paint_w, mat.paint_h, QImage.Format_RGBA8888)
            mat.base_image.fill(c)
            mat.base_color = [1.0,1.0,1.0,1.0]
            mat.base_dirty = True
            mat.base_full_upload = True
            mat.rev += 1
            item = self.material_list.item(mi)
            if item:
                item.setText(f"◆ {mat.name} · {c.name().upper()}")
            self.obj.release_gl()
            self.win.invalidate_thumb(self.win.object_ref(self.obj.id))
            self.win.modified = True
            self.win.viewport.update()

    def _current_mi(self):
        return self.material_list.currentRow()

    def update_uv_info(self, idx):
        if idx < 0 or idx >= len(self.obj.parts):
            self.uv_info.setText("")
            return
        part = self.obj.parts[idx]
        arr = part["arr"]
        if len(arr) == 0:
            self.uv_info.setText("Boş yuva.")
            return
        uv = arr[:, 6:8]
        rep = uv_report(uv, grid=256, density=2.0)
        self.uv_info.setText(
            f"Yuva '{self.obj.materials[idx].name}': "
            f"{rep['tris']} üçgen · "
            f"taşma %{int(rep['out_of_range']*100)} · "
            f"çakışma %{int(rep['overlap']*100)}"
            + (" · " + rep['text'] if rep['text'] else "")
        )

    def fill_with_brush(self):
        mi = self._current_mi()
        if mi < 0 or mi >= len(self.obj.materials):
            return
        mat = self.obj.materials[mi]
        mat.paint_w = mat.paint_w or 1024
        mat.paint_h = mat.paint_h or 1024
        mat.base_image = QImage(mat.paint_w, mat.paint_h, QImage.Format_RGBA8888)
        c = self.win.brush_color()
        mat.base_image.fill(c)
        mat.base_color = [1.0, 1.0, 1.0, 1.0]
        mat.base_dirty = True
        mat.rev += 1
        self.material_list.item(mi).setText(f"◆ {mat.name} · tuval") if self.material_list.item(mi) else None
        self.obj.release_gl()
        self.win.modified = True
        self.win.viewport.update()

    def reset_canvas(self):
        mi = self._current_mi()
        if mi < 0 or mi >= len(self.obj.materials):
            return
        mat = self.obj.materials[mi]
        mat.reset_paint()
        self.material_list.item(mi).setText(f"◆ {mat.name}") if self.material_list.item(mi) else None
        self.win.modified = True
        self.win.viewport.update()

    def regen_uv(self):
        r = QMessageBox.question(
            self, APP_NAME,
            "UV'ler yeniden üretilecek. Mevcut boya tuvali yeni UV'ye uymayacağı için temizlenir.\n\n"
            "Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if r != QMessageBox.Yes:
            return
        self.obj.regenerate_uv()
        for i, mat in enumerate(self.obj.materials):
            mat.reset_paint()
            self.material_list.item(i).setText(f"◆ {mat.name}") if self.material_list.item(i) else None
        self.obj.generated_uv = True
        self.win.modified = True
        self.update_uv_info(self._current_mi())
        self.win.viewport.update()

    def _accept(self):
        self.obj.name = self.object_name.text().strip() or self.obj.name
        self.obj.visible = self.visible.isChecked()
        self.win.modified = True
        self.win.viewport.update()
        self.accept()


# ----------------------------------------------------------------------------
# Ana pencere
# ----------------------------------------------------------------------------
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1320, 820)
        self.scene = Scene()
        self.order = []
        self.brush_ids = []
        self.thumbs = {}
        self.tool = "draw"
        self.mix_mode = "random"
        self.mix_angle = 0
        self.mix_colors = [QColor("#ffffff")]
        self.mix_history = [[QColor("#ffffff")]]
        self.ed_mix_mode = "random"
        self.ed_mix_angle = 0
        self.undo_stack, self.redo_stack = [], []
        self.current_path = None
        self.modified = False
        self.last_dir = os.path.expanduser("~")
        self.cursor_cell = None
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(400)
        self.save_timer.timeout.connect(self.save_library)
        # Boya aracı ayarları
        self.brush_size = 0.5
        self.brush_alpha = 0.8

        self.load_library()
        self._build_ui()
        self.refresh_lists()
        self.set_tool("draw")
        self.update_title()
        self.update_status()

        for seq, fn in (("Ctrl+Z", self.undo), ("Ctrl+Y", self.redo), ("Ctrl+Shift+Z", self.redo),
                        ("Ctrl+S", self.save), ("Ctrl+Shift+S", self.save_as), ("Ctrl+O", self.open_file),
                        ("Ctrl+N", self.new_file), ("1", lambda: self.set_tool("draw")),
                        ("2", lambda: self.set_tool("erase")), ("3", lambda: self.set_tool("paint"))):
            QShortcut(QKeySequence(seq), self, activated=fn)

    # -- arayüz
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        bar = QFrame()
        bar.setObjectName("topbar")
        bar.setStyleSheet("#topbar { background-color: #222; border-bottom: 1px solid #111; }")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(6)

        def mk(text, style=14):
            b = QPushButton(text)
            b.setStyleSheet(btn_style(False, style))
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            return b

        self.file_button = mk("Dosya")
        fm = QMenu(self)
        fm.setStyleSheet(MENU_STYLE)
        fm.addAction("Yeni\tCtrl+N").triggered.connect(self.new_file)
        fm.addAction("Aç...\tCtrl+O").triggered.connect(self.open_file)
        fm.addAction("Kaydet\tCtrl+S").triggered.connect(self.save)
        fm.addAction("Farklı Kaydet...\tCtrl+Shift+S").triggered.connect(self.save_as)
        fm.addSeparator()
        self.border_action = fm.addAction("Küp kenar çizgileri")
        self.border_action.setCheckable(True)
        self.border_action.setChecked(True)
        self.border_action.toggled.connect(self.toggle_border)
        fm.addSeparator()
        fm.addAction("◈ Temel Şekiller").triggered.connect(self.show_primitive_menu)
        self.file_button.setMenu(fm)
        h.addWidget(self.file_button)

        self.save_button = mk("")
        self.save_button.setIcon(create_svg_icon(SVG_SAVE_ICON, 20))
        self.save_button.setToolTip("Kaydet (Ctrl+S)")
        self.save_button.clicked.connect(self.save)
        h.addWidget(self.save_button)
        self.undo_button = mk("")
        self.undo_button.setIcon(create_svg_icon(SVG_UNDO_ICON, 20))
        self.undo_button.setToolTip("Geri al (Ctrl+Z)")
        self.undo_button.clicked.connect(self.undo)
        h.addWidget(self.undo_button)
        self.redo_button = mk("")
        self.redo_button.setIcon(create_svg_icon(SVG_REDO_ICON, 20))
        self.redo_button.setToolTip("Yinele (Ctrl+Y)")
        self.redo_button.clicked.connect(self.redo)
        h.addWidget(self.redo_button)

        self.tool_buttons = {}
        for key, label, tip in (
            ("draw", "Çiz [1]", "Çiz (1)"),
            ("erase", "Sil [2]", "Sil (2) — Ctrl+Sol tık da siler"),
            ("paint", "Boya [3]", "Boya (3) — temel şekil yüzeyini UV üzerinden boyar (1/2/3)")
        ):
            b = mk(label)
            b.setToolTip(tip)
            b.clicked.connect(lambda _c, k=key: self.set_tool(k))
            h.addWidget(b)
            self.tool_buttons[key] = b

        self.editor_button = mk("Küp Editörü")
        self.editor_button.clicked.connect(lambda: self.open_editor(None))
        h.addWidget(self.editor_button)

        self.mix_button = mk("")
        self.mix_button.setToolTip("Birden fazla küp seçiliyse (Ctrl+tık) karışım modu")
        self.mix_button.clicked.connect(self.show_mix_menu)
        h.addWidget(self.mix_button)
        self.angle_button = AngleButton("")
        self.angle_button.setStyleSheet(btn_style(False, 14))
        self.angle_button.setFocusPolicy(Qt.NoFocus)
        self.angle_button.setToolTip("Açısal karışım açısı")
        self.angle_button.clicked.connect(lambda: self.change_angle(15))
        self.angle_button.wheel.connect(self.change_angle)
        h.addWidget(self.angle_button)

        self.objects_button = mk("Şekiller")
        self.objects_button.setToolTip("Küp, silindir, koni, küre ve piramit")
        self.objects_button.clicked.connect(self.show_primitive_menu)
        h.addWidget(self.objects_button)

        self.all_button = mk("☰")
        self.all_button.setToolTip("Tüm küp ve temel şekil fırçalarının listesi")
        self.all_button.clicked.connect(lambda: self.show_cube_menu(QCursor.pos()))
        h.addWidget(self.all_button)

        self.strip = CubeListWidget(self, cols=0, size=44)
        self.strip.picked.connect(self.select_cube)
        self.strip.context.connect(self.cube_context_menu)
        self.strip_area = QScrollArea()
        self.strip_area.setWidget(self.strip)
        self.strip_area.setWidgetResizable(False)
        self.strip_area.setFrameShape(QFrame.NoFrame)
        self.strip_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.strip_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.strip_area.setFixedHeight(self.strip.height() + 2)
        self.strip_area.setStyleSheet("QScrollArea { background-color: #262626; border-radius: 6px; }")
        h.addWidget(self.strip_area, 1)
        root.addWidget(bar)

        # Boya ayarları çubuğu (sadece boya aracı seçilince görünür)
        self.paint_bar = QFrame()
        self.paint_bar.setObjectName("paintbar")
        self.paint_bar.setStyleSheet("#paintbar { background-color: #1c1c1c; border-bottom: 1px solid #111; }")
        pb = QHBoxLayout(self.paint_bar)
        pb.setContentsMargins(10, 4, 10, 4)
        pb.setSpacing(8)
        pb.addWidget(QLabel("Fırça boyutu:"))
        self.brush_size_spin = QDoubleSpinBox()
        self.brush_size_spin.setRange(0.05, 20.0)
        self.brush_size_spin.setSingleStep(0.1)
        self.brush_size_spin.setValue(self.brush_size)
        self.brush_size_spin.valueChanged.connect(self._on_brush_size)
        pb.addWidget(self.brush_size_spin)
        pb.addWidget(QLabel("Opaklık:"))
        self.brush_alpha_spin = QDoubleSpinBox()
        self.brush_alpha_spin.setRange(0.05, 1.0)
        self.brush_alpha_spin.setSingleStep(0.05)
        self.brush_alpha_spin.setValue(self.brush_alpha)
        self.brush_alpha_spin.valueChanged.connect(self._on_brush_alpha)
        pb.addWidget(self.brush_alpha_spin)
        pb.addStretch(1)
        self.paint_hint = QLabel("Temel şekil yüzeyine doğrudan boya. Küp yüzüne dokunursa küp rengi değişir.")
        self.paint_hint.setStyleSheet("color:#888;")
        pb.addWidget(self.paint_hint)
        root.addWidget(self.paint_bar)
        self.paint_bar.setVisible(False)

        self.viewport = Viewport(self)
        root.addWidget(self.viewport, 1)

        sb = QFrame()
        sb.setStyleSheet("QFrame { background-color: #222; } QLabel { color: #bbb; font-size: 12px; }")
        sh = QHBoxLayout(sb)
        sh.setContentsMargins(10, 3, 10, 3)
        hint = QLabel("Sol: çiz/yerleştir/boya · Ctrl+Sol: sil · Orta: döndür · Shift+Orta: kaydır · Tekerlek: zoom · Sağ: liste")
        self.info_label = QLabel("")
        sh.addWidget(hint, 1)
        sh.addWidget(self.info_label)
        root.addWidget(sb)
        self.update_mix_labels()

    def _on_brush_size(self, v):
        self.brush_size = float(v)

    def _on_brush_alpha(self, v):
        self.brush_alpha = float(v)

    def set_tool(self, t):
        self.tool = t
        for k, b in self.tool_buttons.items():
            b.setStyleSheet(btn_style(k == t, 14))
        self.paint_bar.setVisible(t == "paint")
        if hasattr(self, "viewport"):
            self.viewport.hover = None
            self.viewport.update()

    def update_mix_labels(self):
        self.mix_button.setText(f"Karışım: {MIX_SHORT.get(self.mix_mode, '')}")
        self.angle_button.setText(f"Açı {self.mix_angle}°")

    def change_angle(self, d):
        self.mix_angle = (self.mix_angle + d) % 360
        self.update_mix_labels()

    def show_mix_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        menu.addAction("--- Karışım Modları ---").setEnabled(False)
        for label, key in MIX_MODES:
            act = menu.addAction(label)
            act.setCheckable(True)
            act.setChecked(self.mix_mode == key)
            act.triggered.connect(lambda _c, k=key: self._set_mix_mode(k))
        menu.addSeparator()
        menu.addAction(f"Karışımdaki küp sayısı: {len(self.brush_ids)}  (Ctrl+tık ile ekle/çıkar)").setEnabled(False)
        menu.exec_(self.mix_button.mapToGlobal(QPoint(0, self.mix_button.height())))

    def _set_mix_mode(self, k):
        self.mix_mode = k
        self.update_mix_labels()

    def toggle_border(self, flag):
        self.scene.set_border(flag)
        self.viewport.update()

    # -- varlık kitaplığı
    def is_object_ref(self, ref):
        return isinstance(ref, str) and ref.startswith("o:")

    def ref_asset_id(self, ref):
        return ref[2:] if self.is_object_ref(ref) else ref

    def object_ref(self, oid):
        return "o:" + str(oid)

    def load_library(self):
        order = []
        try:
            with open(LIB_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            object_records = {str(x.get("id")): x for x in data.get("objects", []) if x.get("primitive_type")}
            for cid in data.get("order", []):
                if isinstance(cid, str) and cid.startswith("o:"):
                    oid = cid[2:]
                    od = object_records.get(str(oid))
                    if od is not None:
                        try:
                            obj = PrimitiveMesh.from_json(od)
                            if obj.primitive_type:
                                self.scene.add_primitive(obj)
                                order.append(self.object_ref(obj.id))
                        except Exception:
                            traceback.print_exc()
                else:
                    try:
                        cube = Cube.from_json(cid, data["cubes"][cid])
                        self.scene.register_cube(cube)
                        order.append(cid)
                    except Exception:
                        continue
            for od in object_records.values():
                try:
                    obj = PrimitiveMesh.from_json(od)
                    if not obj.primitive_type:
                        continue
                    self.scene.add_primitive(obj)
                    ref = self.object_ref(obj.id)
                    if ref not in order:
                        order.append(ref)
                except Exception:
                    traceback.print_exc()
            pal = []
            for lst in data.get("palette", []):
                cols = [QColor(c) for c in lst if QColor(c).isValid()]
                if cols:
                    pal.append(cols)
            if pal:
                self.mix_history = pal
                self.mix_colors = [QColor(c) for c in pal[-1]]
        except Exception:
            pass
        if not any(ref for ref in order if not self.is_object_ref(ref)):
            for cid, name, col in (("siyah", "Siyah", "#000000"), ("beyaz", "Beyaz", "#ffffff")):
                if cid not in self.scene.cubes:
                    self.scene.register_cube(Cube.solid(cid, name, col))
                if cid not in order:
                    order.append(cid)
        # Daima uygulamanın yerleşik temel şekilleri olsun.
        existing = {getattr(obj, "primitive_type", ""): obj for obj in self.scene.primitive_objects.values()}
        for kind, label in BUILTIN_PRIMITIVES:
            obj = existing.get(kind)
            if obj is None:
                obj = create_builtin_primitive(kind, label, BUILTIN_COLORS[kind], 32)
                self.scene.add_primitive(obj)
            ref = self.object_ref(obj.id)
            if ref not in order:
                order.append(ref)
        self.order = order
        self.brush_ids = [order[0]] if order else []

    def save_library(self):
        try:
            os.makedirs(CFG_DIR, exist_ok=True)
            data = {
                "order": list(self.order),
                "cubes": {cid: self.scene.cubes[cid].to_json() for cid in self.order if not self.is_object_ref(cid) and cid in self.scene.cubes},
                "objects": [obj.to_json() for obj in self.scene.primitive_objects.values() if getattr(obj, "primitive_type", "")],
                "palette": [[c.name() for c in lst] for lst in self.mix_history[-24:]],
            }
            tmp = LIB_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, LIB_PATH)
        except Exception:
            traceback.print_exc()

    def schedule_save(self):
        self.save_timer.start()

    def brush_name(self, ref):
        if self.is_object_ref(ref):
            obj = self.scene.primitive_objects.get(self.ref_asset_id(ref))
            return "◈ " + obj.name if obj else "Nesne"
        c = self.scene.cubes.get(ref)
        return c.name if c else ""

    def cube_name(self, cid):
        return self.brush_name(cid)

    def thumb(self, ref, size):
        key = (ref, size)
        pm = self.thumbs.get(key)
        if pm is not None:
            return pm
        if self.is_object_ref(ref):
            obj = self.scene.primitive_objects.get(self.ref_asset_id(ref))
            pm = mesh_thumb(obj, size) if obj else QPixmap(size, size)
        else:
            pm = iso_cube_pixmap(self.scene.cubes[ref].faces, size)
        self.thumbs[key] = pm
        return pm

    def invalidate_thumb(self, ref):
        self.thumbs = {k: v for k, v in self.thumbs.items() if k[0] != ref}

    def refresh_lists(self):
        self.strip.refresh()
        self.strip_area.horizontalScrollBar().setValue(0)

    def select_cube(self, ref, additive=False):
        if self.is_object_ref(ref):
            if self.ref_asset_id(ref) not in self.scene.primitive_objects:
                return
        elif ref not in self.scene.cubes:
            return
        if additive:
            if ref in self.brush_ids:
                if len(self.brush_ids) > 1:
                    self.brush_ids.remove(ref)
            else:
                self.brush_ids.append(ref)
        else:
            self.brush_ids = [ref]
        rest = [x for x in self.order if x not in self.brush_ids]
        self.order = list(self.brush_ids) + rest
        self.refresh_lists()
        self.update_status()
        self.schedule_save()

    def brush_color(self):
        if not self.brush_ids:
            return QColor("#ffffff")
        ref = self.brush_ids[0]
        if self.is_object_ref(ref):
            obj = self.scene.primitive_objects.get(self.ref_asset_id(ref))
            if obj and obj.materials:
                mat = obj.materials[0]
                if not mat.base_image.isNull():
                    return mat.base_image.pixelColor(mat.base_image.width() // 2, mat.base_image.height() // 2)
                return QColor(mat.color())
            return QColor("#ffffff")
        cube = self.scene.cubes.get(ref)
        if cube is None:
            return QColor("#ffffff")
        rs = gs = bs = aa = 0.0
        for face in cube.faces:
            c = face.pixelColor(TILE // 2, TILE // 2)
            rs += c.red(); gs += c.green(); bs += c.blue(); aa += c.alpha()
        n = max(1, len(cube.faces))
        return QColor(int(rs / n), int(gs / n), int(bs / n), int(aa / n))

    def pick_brush_id(self, u, v, step, seq):
        ids = self.brush_ids
        if len(ids) == 1:
            return ids[0]
        i, j, fr = mix_select(len(ids), self.mix_mode, u * 16, v * 16, step, self.mix_angle, seq)
        return ids[j if fr >= 0.5 else i]

    def show_cube_menu(self, gpos):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        menu.addAction("--- Küpler + Temel Şekiller (Ctrl+tık: karışıma ekle) ---").setEnabled(False)
        lw = CubeListWidget(self, cols=6, size=44)
        area = QScrollArea()
        area.setWidget(lw)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setFixedSize(lw.width() + 16, min(lw.height() + 4, 340))

        def picked(ref, ctrl):
            self.select_cube(ref, ctrl)
            lw.refresh()
            if not ctrl:
                menu.close()

        lw.picked.connect(picked)
        lw.context.connect(lambda ref, pos: (menu.close(), self.cube_context_menu(ref, pos)))
        wa = QWidgetAction(menu)
        wa.setDefaultWidget(area)
        menu.addAction(wa)
        menu.addSeparator()
        menu.addAction("＋ Yeni küp (Küp Editörü)").triggered.connect(lambda: self.open_editor(None))
        menu.exec_(gpos)

    def cube_context_menu(self, ref, gpos):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        if self.is_object_ref(ref):
            oid = self.ref_asset_id(ref)
            a_edit = menu.addAction("Renk / yüzey ayarları")
            a_copy = menu.addAction("Şekli kopyala")
            a_frame = menu.addAction("Sahneyi çerçevele")
            a_del = menu.addAction("Listeden kaldır")
            act = menu.exec_(gpos)
            if act == a_edit:
                self.edit_primitive(oid)
            elif act == a_copy:
                self._duplicate_primitive_asset(oid)
            elif act == a_frame:
                self._frame_primitives(oid)
            elif act == a_del:
                self._delete_primitive(oid)
            return
        a_edit = menu.addAction("Düzenle")
        a_copy = menu.addAction("Kopyala")
        a_del = menu.addAction("Listeden kaldır")
        act = menu.exec_(gpos)
        if act == a_edit:
            self.open_editor(ref)
        elif act == a_copy:
            src = self.scene.cubes[ref]
            new = Cube(uuid.uuid4().hex[:12], src.name + " kopya", src.copy_faces())
            self.add_cube(new)
        elif act == a_del:
            if len(self.order) <= 1:
                QMessageBox.information(self, APP_NAME, "Listede en az bir küp/nesne kalmalı.")
                return
            self.order.remove(ref)
            self.brush_ids = [b for b in self.brush_ids if b != ref] or [self.order[0]]
            self.refresh_lists()
            self.schedule_save()

    def _replay_action_undo(self, action, undo=True):
        kind = action[0]
        if kind == "block":
            _, cell, old, new = action
            if undo:
                if old is None:
                    self.scene.remove(cell)
                else:
                    self.scene.put(cell, old)
            else:
                if new is None:
                    self.scene.remove(cell)
                else:
                    self.scene.put(cell, new)
        elif kind == "objadd":
            _, ins = action
            iid = ins.get("id")
            if undo:
                self.scene.remove_object_instance(iid)
            else:
                asset = ins.get("asset")
                cell = tuple(ins.get("cell", (0, 0, 0)))
                self.scene.object_instances[iid] = dict(ins)
                self.scene.object_instance_cells[(asset, cell)] = iid
                self.scene.inst_rev += 1
        elif kind == "objdel":
            _, ins = action
            if undo:
                asset = ins.get("asset")
                cell = tuple(ins.get("cell", (0, 0, 0)))
                iid = self.scene.add_object_instance(asset, cell,
                                                    ins.get("rotation", [0, 0, 0]),
                                                    ins.get("scale", [1, 1, 1]))
                if iid != ins.get("id"):
                    self.scene.object_instances.pop(iid, None)
                    self.scene.object_instances[ins["id"]] = dict(ins)
                    self.scene.object_instance_cells[(asset, cell)] = ins["id"]
            else:
                self.scene.remove_object_instance(ins.get("id"))
        elif kind == "objpaint":
            _, oid, mi, before_img, before_color, after_img, after_color = action
            obj = self.scene.primitive_objects.get(oid)
            if obj and 0 <= mi < len(obj.materials):
                mat = obj.materials[mi]
                mat.base_image = before_img.copy() if undo else after_img.copy()
                mat.base_color = list(before_color if undo else after_color)
                mat.base_dirty = True
                mat.base_full_upload = True
                mat.rev += 1

    def open_editor(self, cid):
        if cid:
            cube = self.scene.cubes[cid]
            faces, name, editing = cube.copy_faces(), cube.name, True
        else:
            base = self.scene.cubes[self.brush_ids[0]] if not self.is_object_ref(self.brush_ids[0]) else \
                   self.scene.cubes[next(c for c in self.order if not self.is_object_ref(c))]
            faces, name, editing = base.copy_faces(), f"Küp {len(self.order) + 1}", False
        dlg = CubeEditorDialog(self, faces, name, editing, parent=self)
        ok = dlg.exec_() == QDialog.Accepted
        self.schedule_save()
        if not ok:
            return
        if editing and not dlg.as_new:
            cube.faces, cube.name = dlg.faces, dlg.name
            self.scene.register_cube(cube)
            self.invalidate_thumb(cube.id)
            if cube.id not in self.order:
                self.order.insert(0, cube.id)
            self.select_cube(cube.id)
            self.viewport.update()
        else:
            self.add_cube(Cube(uuid.uuid4().hex[:12], dlg.name, dlg.faces))

    def show_primitive_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)
        menu.addAction("--- Yerleşik Temel Şekiller ---").setEnabled(False)
        items = [
            (obj.id, obj) for obj in self.scene.primitive_objects.values()
            if getattr(obj, "primitive_type", "")
        ]
        if not items:
            a = menu.addAction("Temel şekil yok")
            a.setEnabled(False)
        else:
            for oid, obj in items:
                sub = menu.addMenu(f"◈ {obj.name}")
                sub.addAction("Fırça olarak seç").triggered.connect(lambda _c, x=oid: self.select_cube(self.object_ref(x)))
                sub.addAction("Renk / yüzey ayarları...").triggered.connect(lambda _c, x=oid: self.edit_primitive(x))
                sub.addAction("Sahneyi çerçevele").triggered.connect(lambda _c, x=oid: self._frame_primitives(x))
                sub.addAction("Şekli kopyala").triggered.connect(lambda _c, x=oid: self._duplicate_primitive_asset(x))
                sub.addAction("Listeden kaldır").triggered.connect(lambda _c, x=oid: self._delete_primitive(x))
        menu.addSeparator()
        menu.addAction("＋ Yeni temel şekil...").triggered.connect(self.new_primitive)
        menu.exec_(QCursor.pos())

    def new_primitive(self):
        dlg = PrimitiveCreateDialog(self, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        kind, name, color, segments = dlg.values()
        obj = create_builtin_primitive(kind, name, color.name(), segments)
        self.scene.add_primitive(obj)
        ref = self.object_ref(obj.id)
        self.order.insert(0, ref)
        self.select_cube(ref)
        self.modified = True
        self.update_title(); self.update_status(); self.refresh_lists(); self.viewport.update(); self.schedule_save()

    def _duplicate_primitive_asset(self, oid):
        obj = self.scene.primitive_objects.get(oid)
        if obj is None:
            return
        clone = PrimitiveMesh.from_json(obj.to_json())
        clone.id = uuid.uuid4().hex[:12]
        clone.name = obj.name + " kopya"
        self.scene.add_primitive(clone)
        ref = self.object_ref(clone.id)
        self.order.insert(0, ref)
        self.select_cube(ref)
        self.modified = True
        self.update_title(); self.update_status(); self.refresh_lists(); self.viewport.update(); self.schedule_save()

    def edit_primitive(self, oid):
        obj = self.scene.primitive_objects.get(oid)
        if obj is None:
            return
        dlg = PrimitiveObjectDialog(self, obj, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            self.invalidate_thumb(self.object_ref(obj.id))
            self.refresh_lists()
            self.schedule_save()
            self.update_title()
            self.update_status()
            self.viewport.update()

    def _recenter_primitive(self, oid):
        obj = self.scene.primitive_objects.get(oid)
        if obj:
            obj.center_and_ground()
            self.modified = True
            self.update_title(); self.update_status(); self.viewport.update()
            self._frame_primitives(oid)

    def _delete_primitive(self, oid):
        if oid not in self.scene.primitive_objects:
            return
        self.scene.remove_primitive(oid)
        ref = self.object_ref(oid)
        if ref in self.order:
            self.order.remove(ref)
        self.brush_ids = [b for b in self.brush_ids if b != ref]
        if not self.brush_ids and self.order:
            self.brush_ids = [self.order[0]]
        self.modified = True
        self.refresh_lists()
        self.update_title(); self.update_status(); self.viewport.update(); self.schedule_save()

    def _delete_all_primitives(self):
        kinds = [oid for oid, obj in self.scene.primitive_objects.items() if getattr(obj, "primitive_type", "")]
        if not kinds:
            return
        r = QMessageBox.question(self, APP_NAME, "Yerleşik temel şekillerin tamamı silinsin mi?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        for oid in kinds:
            self.scene.remove_primitive(oid)
        self.order = [x for x in self.order if not self.is_object_ref(x)]
        if not self.brush_ids or self.is_object_ref(self.brush_ids[0]):
            self.brush_ids = [self.order[0]] if self.order else []
        self.modified = True
        self.refresh_lists(); self.update_title(); self.update_status(); self.viewport.update(); self.schedule_save()

    def _frame_primitives(self, oid=None):
        """Seçili yerleşik şekli veya yerleşik şekillerin sahnedeki örneklerini kadraja al."""
        targets = []
        if oid and oid in self.scene.primitive_objects:
            targets = [ins for ins in self.scene.object_instances.values()
                       if ins.get("asset") == oid and not ins.get("hidden", False)]
            if not targets:
                obj = self.scene.primitive_objects.get(oid)
                if obj is not None:
                    lo, hi = obj.bounds_min + obj.position, obj.bounds_max + obj.position
                else:
                    return
                size = float(max(hi - lo))
                self.viewport.target = (lo + hi) * 0.5
                self.viewport.dist = max(2.5, min(8000.0, size * 2.8))
                self.viewport.update()
                return
        else:
            targets = [ins for ins in self.scene.object_instances.values()
                       if not ins.get("hidden", False)
                       and ins.get("asset") in self.scene.primitive_objects]
        if not targets:
            return
        bounds = []
        for ins in targets:
            try:
                b = self._instance_bounds(ins)
            except Exception:
                b = None
            if b is not None:
                bounds.append(b)
        if not bounds:
            return
        lo = np.min(np.asarray([b[0] for b in bounds], dtype=np.float64), axis=0)
        hi = np.max(np.asarray([b[1] for b in bounds], dtype=np.float64), axis=0)
        size = float(max(hi - lo))
        self.viewport.target = (lo + hi) * 0.5
        self.viewport.dist = max(2.5, min(8000.0, max(size, 0.5) * 2.8))
        self.viewport.update()

    # -- geri al / yinele
    def push_undo(self, changes):
        if not changes:
            return
        self.undo_stack.append(changes)
        if len(self.undo_stack) > 300:
            self.undo_stack.pop(0)
        self.redo_stack.clear()
        self.on_world_changed()

    def undo(self):
        if not self.undo_stack:
            return
        ch = self.undo_stack.pop()
        for action in reversed(ch):
            try:
                self._replay_action_undo(action, undo=True)
            except Exception:
                traceback.print_exc()
        self.redo_stack.append(ch)
        self.on_world_changed()
        self.viewport.update()

    def redo(self):
        if not self.redo_stack:
            return
        ch = self.redo_stack.pop()
        for action in ch:
            try:
                self._replay_action_undo(action, undo=False)
            except Exception:
                traceback.print_exc()
        self.undo_stack.append(ch)
        self.on_world_changed()
        self.viewport.update()

    def on_world_changed(self, final=True):
        if not self.modified:
            self.modified = True
            self.update_title()
        self.update_status()
        self.schedule_save()

    def set_cursor_info(self, cell):
        self.cursor_cell = cell
        self.update_status()

    def update_status(self):
        cell = f"{self.cursor_cell[0]}, {self.cursor_cell[1]}, {self.cursor_cell[2]}" if self.cursor_cell else "-"
        name = self.brush_name(self.brush_ids[0]) if self.brush_ids else ""
        extra = f" +{len(self.brush_ids) - 1}" if len(self.brush_ids) > 1 else ""
        instances = len(self.scene.object_instances)
        self.info_label.setText(
            f"Fırça: {name}{extra}   |   Küp: {len(self.scene.world)}   |   "
            f"Temel şekil: {len(self.scene.primitive_objects)}   |   "
            f"Yerleşik örnek: {instances}   |   İmleç: {cell}")

    def update_title(self):
        name = os.path.basename(self.current_path) if self.current_path else "Adsız"
        self.setWindowTitle(f"{'*' if self.modified else ''}{name} — {APP_NAME}")

    # -- dosya (.mkj)
    def confirm_discard(self):
        if not self.modified:
            return True
        r = QMessageBox.question(
            self, APP_NAME, "Değişiklikler kaydedilsin mi?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save)
        if r == QMessageBox.Save:
            return self.save()
        return r == QMessageBox.Discard

    def new_file(self):
        if not self.confirm_discard():
            return
        self.scene.clear_world()
        self.scene.clear_object_instances()
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.current_path = None
        self.modified = False
        self.viewport.reset_camera()
        self.update_title()
        self.update_status()
        self.viewport.update()

    def save(self):
        if not self.current_path:
            return self.save_as()
        return self._save_to(self.current_path)

    def save_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Kaydet", self.last_dir, "Küp Çizim (*.mkj)")
        if not path:
            return False
        if not path.lower().endswith(".mkj"):
            path += ".mkj"
        return self._save_to(path)

    def _save_to(self, path):
        try:
            used = sorted(set(self.scene.world.values()))
            idx = {cid: i for i, cid in enumerate(used)}
            flat = []
            for (x, y, z), bid in self.scene.world.items():
                flat.extend((int(x), int(y), int(z), idx[bid]))
            data = {
                "format": "mkj",
                "version": 4,
                "camera": self.viewport.get_camera(),
                "cube_ids": used,
                "cubes": {cid: self.scene.cubes[cid].to_json() for cid in used},
                "blocks": flat,
                "objects": [obj.to_json() for obj in self.scene.primitive_objects.values()
                            if getattr(obj, "primitive_type", "")],
                "object_instances": [dict(v) for v in self.scene.object_instances.values()
                                     if v.get("asset") in self.scene.primitive_objects],
            }
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
            os.replace(tmp, path)
        except Exception as e:
            try:
                tmp = path + ".tmp"
                if os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass
            QMessageBox.critical(self, APP_NAME, f"Kaydedilemedi:\n{e}")
            traceback.print_exc()
            return False
        self.current_path = path
        self.last_dir = os.path.dirname(path)
        self.modified = False
        self.update_title()
        return True

    def open_file(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Aç", self.last_dir,
            "Küp Çizim (*.mkj);;Tüm dosyalar (*)")
        if path:
            self.load_path(path)

    def load_path(self, path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            ids = list(data.get("cube_ids", []))
            remap = []
            for cid in ids:
                cube = Cube.from_json(cid, data["cubes"][cid])
                ex = self.scene.cubes.get(cid)
                if ex is None:
                    self.scene.register_cube(cube)
                    use = cid
                elif ex.same_as(cube):
                    use = cid
                else:
                    use = uuid.uuid4().hex[:12]
                    cube.id = use
                    self.scene.register_cube(cube)
                if use not in self.order:
                    self.order.append(use)
                remap.append(use)
            flat = list(data.get("blocks", []))
            items = []
            for i in range(0, len(flat) - 3, 4):
                try:
                    block_index = int(flat[i + 3])
                    if 0 <= block_index < len(remap):
                        items.append(((int(flat[i]), int(flat[i + 1]), int(flat[i + 2])), remap[block_index]))
                except Exception:
                    continue
        except Exception as e:
            QMessageBox.critical(self, APP_NAME, f"Dosya açılamadı:\n{e}")
            traceback.print_exc()
            return

        self.scene.clear_world()
        self.scene.clear_object_instances()
        self.scene.load_blocks(items)

        # Dosyadaki yerleşik şekiller mevcut kütüphaneye eklenir; dış kaynaklar yok sayılır.
        for od in data.get("objects", []):
            try:
                if not od.get("primitive_type"):
                    continue
                obj = PrimitiveMesh.from_json(od)
                if not obj.primitive_type:
                    continue
                obj.center_and_ground()
                self.scene.add_primitive(obj)
                ref = self.object_ref(obj.id)
                if ref not in self.order:
                    self.order.insert(0, ref)
            except Exception:
                traceback.print_exc()

        for ins in data.get("object_instances", []):
            try:
                iid = str(ins.get("id") or uuid.uuid4().hex[:12])
                asset = str(ins.get("asset"))
                cell = tuple(int(v) for v in ins.get("cell", [0, 0, 0]))
                if asset in self.scene.primitive_objects and not self.scene.object_instance_exists(asset, cell):
                    obj = self.scene.primitive_objects[asset]
                    position = list(ins.get(
                        "position",
                        instance_position_for_cell(
                            obj, cell,
                            ins.get("rotation", [0, 0, 0]),
                            ins.get("scale", [1, 1, 1])).tolist()))
                    self.scene.object_instances[iid] = {
                        "id": iid,
                        "asset": asset,
                        "cell": list(cell),
                        "position": [float(v) for v in position],
                        "rotation": [float(v) for v in ins.get("rotation", [0, 0, 0])],
                        "scale": [max(0.05, float(v)) for v in ins.get("scale", [1, 1, 1])],
                        "hidden": bool(ins.get("hidden", False)),
                    }
                    self.scene.object_instance_cells[(asset, cell)] = iid
                    self.scene.inst_rev += 1
            except Exception:
                traceback.print_exc()

        self.undo_stack.clear()
        self.redo_stack.clear()
        self.viewport.set_camera(data.get("camera", {}))
        self.current_path = path
        self.last_dir = os.path.dirname(path)
        self.modified = False
        self.brush_ids = [b for b in self.brush_ids if b in self.order]
        if not self.brush_ids and self.order:
            self.brush_ids = [self.order[0]]
        self.refresh_lists()
        self.update_title()
        self.update_status()
        self.viewport.update()

    def closeEvent(self, e):
        if not self.confirm_discard():
            e.ignore()
            return
        self.save_timer.stop()
        self.save_library()
        e.accept()

    def frame_selected(self):
        return self._frame_selected()

    def add_cube(self, cube):
        self.scene.register_cube(cube)
        self.invalidate_thumb(cube.id)
        self.order.insert(0, cube.id)
        self.select_cube(cube.id)
        self.modified = True
        self.update_title()
        self.viewport.update()



# ----------------------------------------------------------------------------
# Yerleşik şekil yerleşimi / transform yardımcıları
# ----------------------------------------------------------------------------
def rotation3_from_euler(rotation):
    rx, ry, rz = [math.radians(float(v)) for v in rotation]
    sx, cx = math.sin(rx), math.cos(rx)
    sy, cy = math.sin(ry), math.cos(ry)
    sz, cz = math.sin(rz), math.cos(rz)
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float64)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float64)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float64)
    return Ry @ Rx @ Rz


def axis_angle_matrix(axis, angle):
    axis = np.asarray(axis, dtype=np.float64)
    axis /= max(1e-12, np.linalg.norm(axis))
    x, y, z = axis
    c, s = math.cos(angle), math.sin(angle)
    C = 1.0 - c
    return np.array([
        [c + x*x*C, x*y*C - z*s, x*z*C + y*s],
        [y*x*C + z*s, c + y*y*C, y*z*C - x*s],
        [z*x*C - y*s, z*y*C + x*s, c + z*z*C]], dtype=np.float64)


def transformed_aabb(lo, hi, position, rotation, scale):
    lo = np.asarray(lo, dtype=np.float64); hi = np.asarray(hi, dtype=np.float64)
    pos = np.asarray(position, dtype=np.float64)
    sc = np.asarray(scale, dtype=np.float64)
    R = rotation3_from_euler(rotation)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], dtype=np.float64)
    pts = (corners * sc[None, :]) @ R.T + pos[None, :]
    return pts.min(axis=0), pts.max(axis=0)


def aabb_overlap(lo1, hi1, lo2, hi2, eps=1e-4):
    return bool(np.all(np.asarray(lo1) < np.asarray(hi2) - eps) and np.all(np.asarray(lo2) < np.asarray(hi1) - eps))


def aabb_hits_world(world, lo, hi, eps=1e-5):
    lo = np.asarray(lo, dtype=np.float64); hi = np.asarray(hi, dtype=np.float64)
    x0, y0, z0 = np.floor(lo - eps).astype(int)
    x1, y1, z1 = np.ceil(hi + eps).astype(int)
    for y in range(y0, y1 + 1):
        for z in range(z0, z1 + 1):
            for x in range(x0, x1 + 1):
                c = (x, y, z)
                if c in world:
                    clo = np.array(c, dtype=np.float64); chi = clo + 1.0
                    if aabb_overlap(lo, hi, clo, chi, eps=eps):
                        return True
    return False


def instance_position_for_cell(obj, cell, rotation=(0, 0, 0), scale=(1, 1, 1)):
    """Normalized mesh için karo hücresinin merkezini kullan; geniş nesneyi merkeze hizala."""
    cell = np.asarray(cell, dtype=np.float64)
    base = np.array([cell[0] + 0.5, cell[1], cell[2] + 0.5], dtype=np.float64)
    if obj is None:
        return base
    lo, hi = transformed_aabb(obj.bounds_min, obj.bounds_max, [0, 0, 0], rotation, scale)
    footprint_center = np.array([(lo[0] + hi[0]) * 0.5, lo[1], (lo[2] + hi[2]) * 0.5])
    return base - footprint_center


def instance_cell_from_state(state):
    p = state.get("position", [0, 0, 0])
    return (int(math.floor(float(p[0]))), int(math.floor(float(p[1]))), int(math.floor(float(p[2]))))


def _vp_object_transform(self, obj_or_instance):
    if isinstance(obj_or_instance, PrimitiveMesh):
        return euler_mesh_matrix(obj_or_instance.position, obj_or_instance.rotation, obj_or_instance.scale)
    return euler_mesh_matrix(obj_or_instance.get("position", [0, 0, 0]),
                             obj_or_instance.get("rotation", [0, 0, 0]),
                             obj_or_instance.get("scale", [1, 1, 1]))


def _vp_raycast_primitives(self, px, py, include_asset=False):
    """Yalnızca gerçek yerleşmiş instance'ları tarar; bütün mesh parçalarını test eder."""
    o, d = self.ray(px, py)
    sc = self.win.scene
    best = None
    maxd = self._maxdist()

    for iid, ins in sc.object_instances.items():
        if ins.get("hidden", False):
            continue
        asset_id = ins.get("asset")
        obj = sc.primitive_objects.get(asset_id)
        if obj is None or not obj.visible:
            continue
        M = self._object_transform(ins)
        try:
            inv = np.linalg.inv(M)
        except np.linalg.LinAlgError:
            continue
        ro4 = inv @ np.array([o[0], o[1], o[2], 1.0], dtype=np.float64)
        rd4 = inv @ np.array([d[0], d[1], d[2], 0.0], dtype=np.float64)
        ro = ro4[:3]; rd = rd4[:3]
        n = np.linalg.norm(rd)
        if n < 1e-12:
            continue
        rd /= n
        if ray_aabb(ro, rd, obj.bounds_min - 1e-5, obj.bounds_max + 1e-5) is None:
            continue
        tris = obj.tri_data()
        local_best = None
        for pi, td in enumerate(tris):
            if td is None:
                continue
            r = ray_triangles(ro, rd, td[0], td[1], td[2], tmax=maxd)
            if r is not None and (local_best is None or r[1] < local_best[1]):
                local_best = (pi, r[0], r[1], r[2], r[3])
        if local_best is None:
            continue
        pi, idx, t, u, v = local_best
        lp = ro + rd * t
        wp4 = M @ np.array([lp[0], lp[1], lp[2], 1.0])
        wt = float(np.linalg.norm(wp4[:3] - o))
        if best is not None and wt >= best[6]:
            continue
        arr = obj.parts[pi]["arr"]
        base = idx * 3
        uv = arr[base, 6:8] * (1.0 - u - v) + arr[base + 1, 6:8] * u + arr[base + 2, 6:8] * v
        best = (asset_id, iid, int(obj.parts[pi].get("material", 0)), pi, idx,
                uv.astype(np.float64), wt, wp4[:3].astype(np.float64), M)
    return best


def _vp_draw_primitives(self):
    """Mesh renderer: kaynak asset kökte çizilmez, yalnızca gerçek instance'lar çizilir."""
    if not self.mesh_program:
        return
    sc = self.win.scene
    if not sc.primitive_objects:
        return
    self._upload_imported()
    program = self.mesh_program
    gl.glUseProgram(program)
    loc = self._uloc
    gl.glEnable(gl.GL_DEPTH_TEST)
    gl.glEnable(gl.GL_BLEND)
    gl.glBlendFunc(gl.GL_SRC_ALPHA, gl.GL_ONE_MINUS_SRC_ALPHA)
    gl.glEnable(gl.GL_CULL_FACE)
    gl.glFrontFace(gl.GL_CCW)
    gl.glCullFace(gl.GL_BACK)
    gl.glUniform3f(loc["u_light_pos"], 3.5, 7.0, 5.0)
    gl.glUniform3f(loc["u_fill_pos"], -4.0, 2.0, -3.0)
    gl.glUniform3f(loc["u_instance_offset"], 0.0, 0.0, 0.0)

    def bind_and_draw(obj, M):
        gl.glPushMatrix()
        gl.glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
        for part in obj.parts:
            if not part.get("vbo") or int(part.get("count", 0)) <= 0:
                continue
            mi = min(max(int(part.get("material", 0)), 0), max(0, len(obj.materials) - 1))
            mat = obj.materials[mi] if obj.materials else PrimitiveMaterial()
            bc = (mat.base_color + [1.0] * 4)[:4]
            em = (mat.emission + [0.0] * 4)[:4]
            gl.glUniform4f(loc["u_base_color"], *[float(v) for v in bc])
            gl.glUniform1f(loc["u_metallic"], float(mat.metallic))
            gl.glUniform1f(loc["u_roughness"], float(mat.roughness))
            gl.glUniform1f(loc["u_ior"], float(mat.ior))
            gl.glUniform1f(loc["u_alpha"], 1.0)
            gl.glUniform3f(loc["u_emission"], float(em[0]), float(em[1]), float(em[2]))
            gl.glUniform1f(loc["u_emission_strength"], float(mat.emission_strength))
            gl.glUniform1f(loc["u_coat_weight"], float(mat.coat_weight))
            gl.glUniform1f(loc["u_transmission"], float(mat.transmission))
            has_base = 1 if mat.base_gl else 0
            gl.glUniform1i(loc["u_has_base_tex"], has_base)
            if has_base:
                gl.glActiveTexture(gl.GL_TEXTURE0)
                gl.glBindTexture(gl.GL_TEXTURE_2D, int(mat.base_gl))
                gl.glUniform1i(loc["u_base_tex"], 0)
            gl.glBindBuffer(gl.GL_ARRAY_BUFFER, part["vbo"])
            stride = PrimitiveMesh.STRIDE * 4
            for idx, size, off in ((0,3,0),(1,3,12),(2,2,24),(3,4,32)):
                gl.glEnableVertexAttribArray(idx)
                gl.glVertexAttribPointer(idx, size, gl.GL_FLOAT, gl.GL_FALSE, stride, ctypes.c_void_p(off))
            gl.glDrawArrays(gl.GL_TRIANGLES, 0, int(part["count"]))
            for idx in (3,2,1,0):
                gl.glDisableVertexAttribArray(idx)
        gl.glPopMatrix()

    for iid, ins in sc.object_instances.items():
        if ins.get("hidden", False):
            continue
        obj = sc.primitive_objects.get(ins.get("asset"))
        if obj is None or not obj.visible:
            continue
        bind_and_draw(obj, self._object_transform(ins))

    # Opaque edge pass + selected bounding boxes.
    gl.glUseProgram(0)
    gl.glDisable(gl.GL_TEXTURE_2D)
    gl.glDisable(gl.GL_BLEND)
    gl.glColor4f(0.0, 0.0, 0.0, 0.65)
    gl.glLineWidth(1.0)
    gl.glEnableClientState(gl.GL_VERTEX_ARRAY)
    for iid, ins in sc.object_instances.items():
        if ins.get("hidden", False):
            continue
        obj = sc.primitive_objects.get(ins.get("asset"))
        if obj is None or not obj.visible:
            continue
        M = self._object_transform(ins)
        gl.glPushMatrix()
        gl.glMultMatrixf(np.ascontiguousarray(M.T, dtype=np.float32))
        for part in obj.parts:
            ebuf, edges = part.get("edges_vbo"), part.get("edges")
            if ebuf and edges is not None and len(edges):
                gl.glBindBuffer(gl.GL_ARRAY_BUFFER, ebuf)
                gl.glVertexPointer(3, gl.GL_FLOAT, 0, ctypes.c_void_p(0))
                gl.glDrawArrays(gl.GL_LINES, 0, int(len(edges)*2))
        gl.glPopMatrix()

        if iid in getattr(self.win, "selected_instances", []):
            lo, hi = transformed_aabb(obj.bounds_min, obj.bounds_max,
                                      ins.get("position", [0,0,0]), ins.get("rotation", [0,0,0]), ins.get("scale", [1,1,1]))
            self._outline_box(lo, hi, (1.0, 0.65, 0.08, 1.0))
    gl.glDisableClientState(gl.GL_VERTEX_ARRAY)
    gl.glBindBuffer(gl.GL_ARRAY_BUFFER, 0)
    gl.glEnable(gl.GL_BLEND)
    gl.glUseProgram(0)


def _vp_hit_instance(self, px, py):
    return self.raycast_primitives(px, py)


def _mw_snapshot(self, ids=None):
    ids = list(self.selected_instances if ids is None else ids)
    out = {}
    for iid in ids:
        ins = self.scene.object_instances.get(iid)
        if ins:
            out[iid] = {"id": str(iid), "asset": str(ins.get("asset")),
                        "cell": list(ins.get("cell", [0,0,0])),
                        "position": [float(v) for v in ins.get("position", [0,0,0])],
                        "rotation": [float(v) for v in ins.get("rotation", [0,0,0])],
                        "scale": [float(v) for v in ins.get("scale", [1,1,1])],
                        "hidden": bool(ins.get("hidden", False))}
    return out


def _mw_restore_states(self, states):
    for iid, st in states.items():
        self.scene.object_instances.pop(iid, None)
        self.scene.restore_object_instance(st)


def _mw_validate_states(self, states, ignore_ids=()):
    ids = set(states) | set(ignore_ids)
    vals = list(states.items())
    # Dünya voxel çarpışması
    for iid, st in vals:
        obj = self.scene.primitive_objects.get(st.get("asset"))
        if obj is None:
            return False
        lo, hi = transformed_aabb(obj.bounds_min, obj.bounds_max, st["position"], st["rotation"], st["scale"])
        if aabb_hits_world(self.scene.world, lo, hi):
            return False
        for oid, other in self.scene.object_instances.items():
            if oid in ids or other.get("hidden", False):
                continue
            ob = self.scene.primitive_objects.get(other.get("asset"))
            if ob is None:
                continue
            olo, ohi = transformed_aabb(ob.bounds_min, ob.bounds_max,
                                        other.get("position", [0,0,0]), other.get("rotation", [0,0,0]), other.get("scale", [1,1,1]))
            if aabb_overlap(lo, hi, olo, ohi):
                return False
    for i in range(len(vals)):
        iid, st = vals[i]
        a = self.scene.primitive_objects.get(st.get("asset"))
        if a is None: continue
        alo, ahi = transformed_aabb(a.bounds_min, a.bounds_max, st["position"], st["rotation"], st["scale"])
        for j in range(i+1, len(vals)):
            jid, st2 = vals[j]
            b = self.scene.primitive_objects.get(st2.get("asset"))
            if b is None: continue
            blo, bhi = transformed_aabb(b.bounds_min, b.bounds_max, st2["position"], st2["rotation"], st2["scale"])
            if aabb_overlap(alo, ahi, blo, bhi):
                return False
    return True


def _mw_select_instance(self, iid, additive=False):
    if iid not in self.scene.object_instances:
        return
    if additive:
        if iid in self.selected_instances:
            self.selected_instances.remove(iid)
        else:
            self.selected_instances.append(iid)
    else:
        self.selected_instances = [iid]
    self.set_tool("select")
    self.update_status(); self.viewport.update()


def _mw_select_all(self):
    self.selected_instances = [iid for iid, ins in self.scene.object_instances.items()
                               if not ins.get("hidden", False) and self.scene.primitive_objects.get(ins.get("asset")) is not None]
    self.set_tool("select")
    self.update_status(); self.viewport.update()


def _mw_deselect_all(self):
    self.selected_instances.clear()
    self.transform_state = None
    self.update_status(); self.viewport.update()


def _mw_hide_selected(self):
    changed=[]
    for iid in list(self.selected_instances):
        ins=self.scene.object_instances.get(iid)
        if ins and not ins.get("hidden",False):
            changed.append(dict(ins)); ins["hidden"]=True
    if changed:
        self.scene.inst_rev += 1; self.modified=True
        self.update_title(); self.update_status(); self.schedule_save(); self.viewport.update()


def _mw_unhide_all(self):
    changed=False
    for ins in self.scene.object_instances.values():
        if ins.get("hidden",False): ins["hidden"]=False; changed=True
    for obj in self.scene.primitive_objects.values():
        if not obj.visible: obj.visible=True; changed=True
    if changed:
        self.scene.inst_rev += 1; self.modified=True
        self.update_title(); self.update_status(); self.schedule_save(); self.viewport.update()


def _mw_delete_selected(self):
    if not self.selected_instances:
        return
    changes=[]
    for iid in list(self.selected_instances):
        ins=self.scene.remove_object_instance(iid)
        if ins: changes.append(("objdel", dict(ins)))
    self.selected_instances.clear()
    if changes:
        self.push_undo(changes); self.modified=True
    self.update_title(); self.update_status(); self.schedule_save(); self.viewport.update()


def _mw_instance_bounds(self, ins):
    obj=self.scene.primitive_objects.get(ins.get("asset"))
    if obj is None: return None
    return transformed_aabb(obj.bounds_min,obj.bounds_max,ins.get("position",[0,0,0]),ins.get("rotation",[0,0,0]),ins.get("scale",[1,1,1]))


def _mw_frame_selected(self):
    bounds=[b for iid in self.selected_instances for b in [self._instance_bounds(self.scene.object_instances.get(iid))] if b is not None]
    if not bounds:
        self._frame_primitives(); return
    lo=np.min(np.array([b[0] for b in bounds]),axis=0); hi=np.max(np.array([b[1] for b in bounds]),axis=0)
    self.viewport.target=(lo+hi)*0.5
    size=max(0.5,float(np.max(hi-lo)))
    self.viewport.dist=max(1.5,min(8000.0,size*2.6)); self.viewport.update()


def _mw_transform_begin(self, mode):
    if not self.selected_instances: return
    if self.transform_state is not None: self.finish_transform(True)
    self.set_tool(mode)
    start=self.viewport.mapFromGlobal(QCursor.pos())
    start=QPoint(max(0,min(self.viewport.width()-1,start.x())),max(0,min(self.viewport.height()-1,start.y())))
    before=self._snapshot_instance_states()
    self.transform_state={"mode":mode,"axis":None,"start":start,"before":before,"last":{k:dict(v) for k,v in before.items()}}
    self.viewport.setFocus(); self.set_cursor_info(f"{mode.upper()}: X/Y/Z · LMB/Enter onay · Esc/RMB iptal")
    self.viewport.update()


def _mw_pivot(states):
    if not states: return np.zeros(3,dtype=np.float64)
    return np.mean(np.array([s["position"] for s in states.values()],dtype=np.float64),axis=0)


def _mw_preview(self, states, mode, axis, dx, dy, fine=False):
    pivot=_mw_pivot(states)
    f=self.viewport.target-self.viewport.eye(); f/=max(1e-9,np.linalg.norm(f))
    right=np.cross(f,np.array([0.0,1.0,0.0])); right/=max(1e-9,np.linalg.norm(right))
    up=np.cross(right,f)
    pxw=2.0*self.viewport.dist*math.tan(math.radians(self.viewport.fov)/2.0)/max(1,self.viewport.height())
    changed={}
    if mode=="move":
        if axis is None:
            d=(right*dx-up*dy)*pxw; step=0.25 if fine else 1.0; d=np.round(d/step)*step
        else:
            av=np.eye(3)[axis]; p0=self._project_world(pivot); p1=self._project_world(pivot+av)
            if p0 is None or p1 is None or np.dot(p1-p0,p1-p0)<1e-8: d=np.zeros(3)
            else:
                val=float(np.dot(np.array([dx,dy]),p1-p0)/np.dot(p1-p0,p1-p0)); step=0.25 if fine else 1.0
                d=av*(round(val/step)*step)
        for iid,st in states.items():
            ns=dict(st); ns["position"]=(np.asarray(st["position"])+d).tolist(); ns["cell"]=list(instance_cell_from_state(ns)); changed[iid]=ns
    elif mode=="rotate":
        ax_i=1 if axis is None else axis; ang=dx*(0.5 if not fine else 0.1); step=15.0 if not fine else 1.0; ang=round(ang/step)*step
        R=axis_angle_matrix(np.eye(3)[ax_i],math.radians(ang))
        for iid,st in states.items():
            ns=dict(st); pp=np.asarray(st["position"])-pivot; ns["position"]=(pivot+R@pp).tolist()
            rr=np.asarray(st["rotation"],dtype=np.float64); rr[ax_i]+=ang; ns["rotation"]=rr.tolist(); ns["cell"]=list(instance_cell_from_state(ns)); changed[iid]=ns
    else:
        amt=max(0.05,1.0+dx*(0.01 if not fine else 0.002)); step=0.1 if not fine else 0.02; amt=max(0.05,round(amt/step)*step)
        for iid,st in states.items():
            ns=dict(st); pp=np.asarray(st["position"])-pivot; sc=np.asarray(st["scale"],dtype=np.float64)
            fac=np.full(3,amt,dtype=np.float64) if axis is None else np.array([1.0,1.0,1.0]);
            if axis is not None: fac[axis]=amt
            ns["position"]=(pivot+pp*fac).tolist(); ns["scale"]=np.maximum(sc*fac,0.05).tolist(); ns["cell"]=list(instance_cell_from_state(ns)); changed[iid]=ns
    return changed


def _mw_transform_update(self,pos):
    t=self.transform_state
    if not t:return
    dx=pos.x()-t["start"].x(); dy=pos.y()-t["start"].y(); fine=bool(QApplication.keyboardModifiers()&Qt.ShiftModifier)
    cand=self._transform_preview(t["before"],t["mode"],t["axis"],dx,dy,fine)
    if self._validate_transform_states(cand):
        self._restore_instance_states(cand); t["last"]={k:dict(v) for k,v in cand.items()}; self.selected_instances=list(cand)
        self.modified=True; self.update_title(); self.update_status(); self.schedule_save()
    self.viewport.update()


def _mw_transform_finish(self,confirm=True):
    t=self.transform_state
    if not t:return
    self.transform_state=None
    before=t["before"]
    if not confirm:
        self._restore_instance_states(before)
    else:
        after=self._snapshot_instance_states(t["last"].keys())
        if before!=after:
            self.push_undo([("objtransform",before,after)])
            self.modified=True
    self.set_cursor_info(None); self.update_title(); self.update_status(); self.schedule_save(); self.viewport.update()


def _mw_project_world(self,p):
    P,V=self.viewport.matrices(); q=P@V@np.array([float(p[0]),float(p[1]),float(p[2]),1.0])
    if abs(q[3])<1e-9:return None
    return np.array([(q[0]/q[3]*0.5+0.5)*self.viewport.width(),(1.0-(q[1]/q[3]*0.5+0.5))*self.viewport.height()],dtype=np.float64)


def _mw_find_free_cell(self,asset_id,preferred=(0,0,0)):
    obj=self.scene.primitive_objects.get(asset_id)
    if obj is None:return None
    px,py,pz=[int(v) for v in preferred]
    for r in range(0,32):
        for x in range(px-r,px+r+1):
            for z in range(pz-r,pz+r+1):
                if max(abs(x-px),abs(z-pz))!=r:continue
                cell=(x,py,z); pos=instance_position_for_cell(obj,cell)
                st={"id":"probe","asset":asset_id,"cell":list(cell),"position":pos.tolist(),"rotation":[0,0,0],"scale":[1,1,1]}
                if self._validate_external_states({"probe":st}):return cell
    return None


def _mw_duplicate(self):
    if not self.selected_instances:return
    if self.transform_state is not None:self.finish_transform(True)
    selected=self._snapshot_instance_states(); directions=[(1,0,0),(0,0,1),(-1,0,0),(0,0,-1),(1,0,1),(-1,0,1),(1,0,-1),(-1,0,-1)]
    chosen=None
    for dx,dy,dz in directions:
        cand={}
        for st in selected.values():
            ns=dict(st); ns["id"]=uuid.uuid4().hex[:12]; ns["position"]=(np.asarray(st["position"])+np.array([dx,dy,dz],dtype=np.float64)).tolist(); ns["cell"]=list(instance_cell_from_state(ns)); cand[ns["id"]]=ns
        if self._validate_external_states(cand,ignore_ids=set(selected)):
            chosen=cand;break
    if chosen is None:
        QMessageBox.warning(self,APP_NAME,"Kopya için çakışmasız karo bulunamadı.");return
    self._restore_instance_states(chosen); self.selected_instances=list(chosen); self.push_undo([("objadd",dict(st)) for st in chosen.values()]); self.modified=True; self.update_title(); self.update_status(); self.schedule_save(); self.viewport.update(); self.start_transform("move")


def _mw_set_tool(self,t):
    self.tool=t
    for k,b in getattr(self,"tool_buttons",{}).items(): b.setStyleSheet(btn_style(k==t,14))
    if hasattr(self,"transform_buttons"):
        for k,b in self.transform_buttons.items(): b.setStyleSheet(btn_style(k==t,14))
    if hasattr(self,"paint_bar"): self.paint_bar.setVisible(t=="paint")
    self.viewport.update()


def _vp_mouse_press(self,e):
    self.setFocus(); b=e.button()
    if self.win.transform_state is not None:
        if b==Qt.LeftButton:
            self.win.finish_transform(True); e.accept(); return
        if b==Qt.RightButton:
            self.win.finish_transform(False); e.accept(); return
    if self.win.box_select_armed and b==Qt.LeftButton:
        self.win.box_select_start=e.pos(); self.win.box_select_current=e.pos(); self.win.box_select_armed=False; self.setCursor(Qt.CrossCursor); e.accept(); return
    if b==Qt.LeftButton:
        if self.win.tool=="select":
            hit=self.raycast_primitives(e.pos().x(),e.pos().y())
            if hit:self.win.select_instance(hit[1],bool(e.modifiers()&Qt.ControlModifier))
            elif not (e.modifiers()&Qt.ControlModifier):self.win.deselect_instances()
            e.accept();return
        mode="erase" if (e.modifiers()&Qt.ControlModifier) else self.win.tool
        self.begin_stroke(e.pos(),mode); self.win.on_world_changed(False); self.update(); return
    if b==Qt.MiddleButton:
        self.cam=True; self.cam_last=e.pos();return
    if b==Qt.RightButton:self.win.show_cube_menu(e.globalPos());return


def _vp_mouse_move(self,e):
    pos=e.pos()
    if self.win.box_select_start is not None:
        self.win.box_select_current=pos; self.update();return
    if self.win.transform_state is not None:
        self.win._update_transform_from_pos(pos);return
    if self.cam:
        dx,dy=pos.x()-self.cam_last.x(),pos.y()-self.cam_last.y();self.cam_last=pos
        if e.modifiers()&Qt.ShiftModifier:
            eye=self.eye(); f=self.target-eye; f/=max(1e-9,np.linalg.norm(f)); right=np.cross(f,np.array([0,1,0],dtype=np.float64)); right/=max(1e-9,np.linalg.norm(right)); up=np.cross(right,f); s=2*self.dist*math.tan(math.radians(self.fov)/2)/max(1,self.height());self.target+=(-right*dx+up*dy)*s
        else:self.yaw-=dx*0.009;self.pitch=max(-1.5,min(1.5,self.pitch+dy*0.009))
        self.update();return
    if self.stroke:
        try:self.stroke_to(pos)
        except Exception:traceback.print_exc();self.end_stroke()
        self.win.on_world_changed(False);self.update();return
    self.update_hover(pos,bool(e.modifiers()&Qt.ControlModifier))


def _vp_mouse_release(self,e):
    if e.button()==Qt.LeftButton and self.win.box_select_start is not None:
        a=self.win.box_select_start;b=self.win.box_select_current or e.pos();self.win.box_select_start=self.win.box_select_current=None
        x0,x1=sorted((a.x(),b.x()));y0,y1=sorted((a.y(),b.y()));add=False
        chosen=[]
        for iid,ins in self.win.scene.object_instances.items():
            if ins.get("hidden",False):continue
            bb=self.win._instance_bounds(ins)
            if not bb:continue
            pts=[self.win._project_world([x,y,z]) for x in (bb[0][0],bb[1][0]) for y in (bb[0][1],bb[1][1]) for z in (bb[0][2],bb[1][2])]
            pts=[p for p in pts if p is not None]
            if pts and min(p[0] for p in pts)>=x0 and max(p[0] for p in pts)<=x1 and min(p[1] for p in pts)>=y0 and max(p[1] for p in pts)<=y1:chosen.append(iid)
        self.win.selected_instances=chosen;self.win.update_status();self.update();return
    if e.button()==Qt.LeftButton and self.stroke:
        self.end_stroke();self.update_hover(e.pos(),bool(e.modifiers()&Qt.ControlModifier))
    elif e.button()==Qt.MiddleButton:self.cam=None


def _vp_key_press(self,e):
    if self.win.transform_state is not None:
        if e.key() in (Qt.Key_X,Qt.Key_Y,Qt.Key_Z):self.win.axis_key({Qt.Key_X:0,Qt.Key_Y:1,Qt.Key_Z:2}[e.key()]);return
        if e.key() in (Qt.Key_Return,Qt.Key_Enter):self.win.finish_transform(True);return
        if e.key()==Qt.Key_Escape:self.win.finish_transform(False);return
    if e.key()==Qt.Key_Home:self.reset_camera();return
    super(Viewport,self).keyPressEvent(e)


def _vp_double_click(self,e):
    hit=self.raycast_primitives(e.pos().x(),e.pos().y())
    if hit:
        self.win.select_instance(hit[1]); self.win.edit_primitive(hit[0])
    e.accept()


def _mw_install_features(self):
    if getattr(self,"_mkj_features_installed",False):return
    self._mkj_features_installed=True
    self.selected_instances=[];self.transform_state=None;self.box_select_armed=False;self.box_select_start=None;self.box_select_current=None
    # Add transform/select buttons to the existing top bar.
    try:
        lay=self.file_button.parentWidget().layout(); idx=lay.indexOf(self.strip_area)
        if idx < 0: idx=lay.count()
        self.extra_tool_buttons={}
        for key,label,tip in (("select","Seç [W]","Seçim aracı (W)"),("move","Taşı [G]","Taşı (G)"),("rotate","Döndür [R]","Döndür (R)"),("scale","Ölçek [S]","Ölçekle (S)")):
            b=QPushButton(label);b.setStyleSheet(btn_style(False,14));b.setFocusPolicy(Qt.NoFocus);b.setToolTip(tip)
            b.clicked.connect(lambda _=False,k=key:self.set_tool("select") if k=="select" else self.start_transform({"move":"move","rotate":"rotate","scale":"scale"}[k]))
            lay.insertWidget(idx,b);self.extra_tool_buttons[key]=b;idx+=1
        self.transform_buttons=self.extra_tool_buttons
        self.select_button=self.extra_tool_buttons["select"]
        self.tool_buttons.update({k:v for k,v in self.extra_tool_buttons.items() if k=="select"})
    except Exception:
        traceback.print_exc()
    # Application-level shortcuts, but WindowShortcut prevents modal/text widgets from eating letters.
    for seq,fn in (("W",lambda:self.set_tool("select")),("G",lambda:self.start_transform("move")),("R",lambda:self.start_transform("rotate")),("S",lambda:self.start_transform("scale")),("B",self.arm_box_select),("A",self.select_all_instances),("Alt+A",self.deselect_instances),("H",self.hide_selected),("Alt+H",self.unhide_all),("F",self.frame_selected),("Shift+D",self.duplicate_selected),("Delete",self.delete_selected),("X",lambda:self.axis_key(0)),("Y",lambda:self.axis_key(1)),("Z",lambda:self.axis_key(2))):
        sc=QShortcut(QKeySequence(seq),self);sc.setContext(Qt.WindowShortcut);sc.activated.connect(fn)
        setattr(self,"_mkj_sc_"+re.sub('[^A-Za-z0-9]','_',seq),sc)
    # Normalize library assets and ensure every asset has at least one real instance.
    for obj in self.scene.primitive_objects.values():
        obj.center_and_ground()
    for iid,ins in list(self.scene.object_instances.items()):
        obj=self.scene.primitive_objects.get(ins.get("asset"));
        if obj is not None:
            ins["position"]=instance_position_for_cell(obj,ins.get("cell",[0,0,0]),ins.get("rotation",[0,0,0]),ins.get("scale",[1,1,1])).tolist()
    for oid,obj in list(self.scene.primitive_objects.items()):
        if not any(ins.get("asset")==oid for ins in self.scene.object_instances.values()):
            cell=self._find_free_object_cell(oid,(0,0,0))
            if cell is not None:self.scene.add_object_instance(oid,cell)
    self.refresh_lists();self.update_status();self.viewport.update()


def _mw_status_with_selection(self):
    try:
        super_status = None
    except Exception:
        super_status = None
    # Call original status implementation saved under __orig_update_status__.
    if hasattr(self,"__orig_update_status__"):
        self.__orig_update_status__()
    n=len(getattr(self,"selected_instances",[]))
    if hasattr(self,"info_label"):
        txt=self.info_label.text()
        self.info_label.setText(txt+f"   | Seçili nesne: {n}")


def _scene_restore_object_instance(self, ins):
    iid = str(ins.get("id") or uuid.uuid4().hex[:12])
    old = self.object_instances.get(iid)
    if old is not None:
        self.object_instance_cells.pop((old.get("asset"), tuple(old.get("cell", [0,0,0]))), None)
    data = {
        "id": iid,
        "asset": str(ins.get("asset")),
        "cell": list(ins.get("cell", instance_cell_from_state(ins))),
        "position": [float(v) for v in ins.get("position", [0,0,0])],
        "rotation": [float(v) for v in ins.get("rotation", [0,0,0])],
        "scale": [max(0.05, float(v)) for v in ins.get("scale", [1,1,1])],
        "hidden": bool(ins.get("hidden", False)),
    }
    self.object_instances[iid] = data
    self.object_instance_cells[(data["asset"], tuple(data["cell"]))] = iid
    self.inst_rev += 1
    return iid


def _mw_axis_key(self, axis):
    if self.transform_state is None:
        return
    cur = self.transform_state.get("axis")
    self.transform_state["axis"] = None if cur == axis else axis
    self._update_transform_from_pos(self.viewport.mapFromGlobal(QCursor.pos()))


def _mw_arm_box_select(self):
    self.box_select_armed = True
    self.box_select_start = None
    self.box_select_current = None
    self.set_tool("select")
    self.viewport.setFocus()
    self.set_cursor_info("B: dikdörtgen seçim — sürükleyin")
    self.viewport.update()


# Preserve original methods while installing the feature layer.
Scene.restore_object_instance = _scene_restore_object_instance

Viewport._object_transform = _vp_object_transform
Viewport.raycast_primitives = _vp_raycast_primitives
Viewport._draw_primitives = _vp_draw_primitives
Viewport.mousePressEvent = _vp_mouse_press
Viewport.mouseMoveEvent = _vp_mouse_move
Viewport.mouseReleaseEvent = _vp_mouse_release
Viewport.keyPressEvent = _vp_key_press
Viewport.mouseDoubleClickEvent = _vp_double_click

MainWindow._snapshot_instance_states = _mw_snapshot
MainWindow._restore_instance_states = _mw_restore_states
MainWindow._validate_transform_states = _mw_validate_states
MainWindow._validate_external_states = _mw_validate_states
MainWindow.select_instance = _mw_select_instance
MainWindow.select_all_instances = _mw_select_all
MainWindow.deselect_instances = _mw_deselect_all
MainWindow.hide_selected = _mw_hide_selected
MainWindow.unhide_all = _mw_unhide_all
MainWindow.delete_selected = _mw_delete_selected
MainWindow._instance_bounds = _mw_instance_bounds
MainWindow._frame_selected = _mw_frame_selected
MainWindow._project_world = _mw_project_world
MainWindow._find_free_object_cell = _mw_find_free_cell
MainWindow.start_transform = _mw_transform_begin
MainWindow._transform_preview = _mw_preview
MainWindow._update_transform_from_pos = _mw_transform_update
MainWindow.finish_transform = _mw_transform_finish
MainWindow.duplicate_selected = _mw_duplicate
MainWindow.set_tool = _mw_set_tool
MainWindow.axis_key = _mw_axis_key
MainWindow.arm_box_select = _mw_arm_box_select
MainWindow.frame_selected = _mw_frame_selected

# Wrap MainWindow.__init__ so feature installation happens after the original UI/library setup.
_orig_mw_init = MainWindow.__init__
def _mw_init_features(self):
    _orig_mw_init(self)
    _mw_install_features(self)
MainWindow.__init__ = _mw_init_features

_orig_replay_action = MainWindow._replay_action_undo
def _replay_action_feature(self, action, undo=True):
    if action and action[0] == "objtransform":
        states = action[1] if undo else action[2]
        self._restore_instance_states(states)
        return
    _orig_replay_action(self, action, undo)
MainWindow._replay_action_undo = _replay_action_feature

# Avoid original status method fighting selection text: append a lightweight selection count.
_orig_update_status = MainWindow.update_status
MainWindow.__orig_update_status__ = _orig_update_status
def _update_status_feature(self):
    _orig_update_status(self)
    if hasattr(self,"info_label"):
        self.info_label.setText(self.info_label.text()+f"   | Seçili nesne: {len(getattr(self,'selected_instances',[]))}")
MainWindow.update_status = _update_status_feature


# ----------------------------------------------------------------------------
def apply_dark_palette(app):
    app.setStyle("Fusion")
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor("#2b2b2b"))
    pal.setColor(QPalette.WindowText, Qt.white)
    pal.setColor(QPalette.Base, QColor("#1e1e1e"))
    pal.setColor(QPalette.AlternateBase, QColor("#2b2b2b"))
    pal.setColor(QPalette.ToolTipBase, QColor("#333333"))
    pal.setColor(QPalette.ToolTipText, Qt.white)
    pal.setColor(QPalette.Text, Qt.white)
    pal.setColor(QPalette.Button, QColor("#333333"))
    pal.setColor(QPalette.ButtonText, Qt.white)
    pal.setColor(QPalette.BrightText, Qt.red)
    pal.setColor(QPalette.Highlight, QColor("#4a7bd0"))
    pal.setColor(QPalette.HighlightedText, Qt.white)
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor("#777777"))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#777777"))
    app.setPalette(pal)


def main():
    sys.excepthook = lambda t, v, tb: traceback.print_exception(t, v, tb)
    fmt = QSurfaceFormat()
    fmt.setVersion(2, 1)
    fmt.setDepthBufferSize(24)
    fmt.setSamples(4)
    QSurfaceFormat.setDefaultFormat(fmt)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    apply_dark_palette(app)
    win = MainWindow()
    win.show()
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        win.load_path(sys.argv[1])
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
