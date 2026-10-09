#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
MKJ Pencere Sistemi — Blender tarzı alan (area) yöneticisi
==========================================================

Bu dosya yalnızca PENCERE SİSTEMİDİR; hiçbir editör içermez.
Editörler mkj_editorler.py içinde toplanır ve buraya kayıt edilir.

Blender'dan alınan mantık
  * Ekran, kenarları paylaşan dikdörtgen ALANLARA bölünür (varsayılan: 4 alan).
  * Her alanın başlığında, sol kenarda editör simgesi vardır; tıklayınca
    diğer editörlerin listesi açılır.
  * İki alanın arasındaki KENARDAN tutup sürükleyince komşu alanlar yeniden boyutlanır
    (aynı hat üzerindeki bağlı kenarlar birlikte hareket eder).
  * Alanın KÖŞESİNDEN tutup:
        - alanın içine doğru sürüklersen  -> alan BÖLÜNÜR (önizleme çizgisi görünür)
        - komşu alanın üzerine doğru sürüklersen -> alanlar BİRLEŞİR
          (üzerine sürüklediğin alan kararır ve kapanır, sen genişlersin)
  * Ctrl+Space: imlecin altındaki alanı büyüt / eski haline döndür.

Basit kısayol havuzu (Blender'dan bilerek sade)
  Ctrl+Space ........ alanı büyüt / küçült
  Shift+F1..F8 ...... imlecin altındaki alanın editörünü değiştir
  Başlıkta sağ tık / ⋮ ... böl, kapat, büyüt, düzeni sıfırla
  Başlığa çift tık .. büyüt / küçült

Bağlantı şekli
  mkj_editorler.py şunu yapar:
      reg = EditorRegistry(fallback="ozellikler")
      reg.register(EditorType("id", "Ad", QIcon, fabrika, unique=False))
      yonetici = AreaManager(reg, baglam)
      yonetici.build_default([...4 editör kimliği...])
  Fabrika fonksiyonu  fabrika(baglam) -> QWidget  döndürür.
  unique=True olan editör (ör. 3B görünüm) aynı anda tek alanda bulunabilir;
  başka alandan seçilirse iki alan editör değiştirir (swap).
"""
import math

from PyQt5.QtWidgets import (
    QWidget, QFrame, QVBoxLayout, QHBoxLayout, QToolButton, QLabel, QMenu,
    QShortcut, QSizePolicy
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QBrush, QKeySequence, QCursor, QPolygonF
)
from PyQt5.QtCore import Qt, QRect, QPoint, QPointF, QSize, pyqtSignal

EPS = 1e-4          # normalize koordinat eşitlik toleransı
GAP = 6             # alanlar arası boşluk (px) — kenar tutma bölgesi burasıdır
MIN_W = 90          # alan en az genişlik (px)
MIN_H = 70          # alan en az yükseklik (px)
HEADER_H = 26
CORNER = 14         # köşe eylem bölgesi boyutu (px)
JOIN_ABSORBS_TARGET = True   # True: sürüklediğin alan, üzerine geldiği alanı yutar

MENU_CSS = (
    "QMenu{background:#2b2b2b;color:#ddd;border:1px solid #111;padding:3px;}"
    "QMenu::item{padding:5px 22px 5px 10px;border-radius:3px;}"
    "QMenu::item:selected{background:#4a7bd0;}"
    "QMenu::item:disabled{color:#777;}"
    "QMenu::separator{height:1px;background:#444;margin:4px 6px;}"
)


# ----------------------------------------------------------------------------
# Editör kaydı
# ----------------------------------------------------------------------------
class EditorType:
    def __init__(self, tid, name, icon, factory, unique=False):
        self.id = tid
        self.name = name
        self.icon = icon
        self.factory = factory
        self.unique = unique
        self.instance = None    # unique editörlerde kalıcı widget
        self.owner = None       # unique editörü şu an tutan alan

    def widget(self, ctx):
        if self.unique:
            if self.instance is None:
                self.instance = self.factory(ctx)
            return self.instance
        return self.factory(ctx)


class EditorRegistry:
    def __init__(self, fallback=None):
        self._types = {}
        self._order = []
        self.fallback = fallback    # bölünen/boşta kalan alan için unique OLMAYAN editör

    def register(self, et):
        if et.id not in self._types:
            self._order.append(et.id)
        self._types[et.id] = et

    def get(self, tid):
        return self._types.get(tid)

    def ordered(self):
        return [self._types[i] for i in self._order]

    def index(self, tid):
        return self._order.index(tid) if tid in self._order else -1


# ----------------------------------------------------------------------------
# Köşe eylem bölgesi
# ----------------------------------------------------------------------------
class CornerZone(QWidget):
    """Alanın 4 köşesindeki küçük şeffaf bölge: sürükle -> böl / birleştir."""

    def __init__(self, area, corner):
        super().__init__(area)
        self.area = area
        self.corner = corner      # 0 sol-üst, 1 sağ-üst, 2 sağ-alt, 3 sol-alt
        self.hover = False
        self.setFixedSize(CORNER, CORNER)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.setToolTip("Sürükle: içeri = böl · komşu alana = birleştir")

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def paintEvent(self, e):
        if not self.hover:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 150), 1.2))
        s = CORNER - 2
        sx = -1 if self.corner in (0, 3) else 1
        sy = -1 if self.corner in (0, 1) else 1
        ox = 1 if sx < 0 else s
        oy = 1 if sy < 0 else s
        for k in (4, 8, 12):
            # köşeye paralel eğik çizgiler (Blender'daki tutamaç gibi)
            p.drawLine(int(ox - sx * 0), int(oy - sy * k + sy * 0),
                       int(ox - sx * k), int(oy - sy * 0))

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.area.manager.corner_begin(self.area, self.corner, e.globalPos())
            e.accept()
        else:
            e.ignore()

    def mouseMoveEvent(self, e):
        if e.buttons() & Qt.LeftButton:
            self.area.manager.corner_move(e.globalPos())
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.area.manager.corner_end()
            e.accept()


class _Header(QFrame):
    doubleClicked = pyqtSignal()

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit()
        e.accept()


# ----------------------------------------------------------------------------
# Alan
# ----------------------------------------------------------------------------
class Area(QFrame):
    def __init__(self, manager, rect):
        super().__init__(manager)
        self.manager = manager
        self.rect = [float(v) for v in rect]     # normalize x0, y0, x1, y1
        self.editor_id = None
        self.widget = None
        self.setObjectName("mkjArea")
        self.setStyleSheet("#mkjArea{background:#262626;border:1px solid #101010;border-radius:5px;}")

        v = QVBoxLayout(self)
        v.setContentsMargins(1, 1, 1, 1)
        v.setSpacing(0)

        self.header = _Header(self)
        self.header.setObjectName("mkjHeader")
        self.header.setFixedHeight(HEADER_H)
        self.header.setStyleSheet(
            "#mkjHeader{background:#333;border-top-left-radius:4px;border-top-right-radius:4px;}")
        self.header.setContextMenuPolicy(Qt.CustomContextMenu)
        self.header.customContextMenuRequested.connect(
            lambda pos: self.show_area_menu(self.header.mapToGlobal(pos)))
        self.header.doubleClicked.connect(lambda: self.manager.toggle_maximize(self))
        hl = QHBoxLayout(self.header)
        hl.setContentsMargins(CORNER + 2, 0, 4, 0)
        hl.setSpacing(4)

        btn_css = ("QToolButton{background:#3d3d3d;border:1px solid #1a1a1a;border-radius:4px;"
                   "color:#ddd;padding:1px 5px;}QToolButton:hover{background:#505050;}")
        self.type_btn = QToolButton(self.header)
        self.type_btn.setStyleSheet(btn_css)
        self.type_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.type_btn.setIconSize(QSize(18, 18))
        self.type_btn.setText("▾")
        self.type_btn.setCursor(Qt.PointingHandCursor)
        self.type_btn.setToolTip("Editör türünü değiştir")
        self.type_btn.clicked.connect(self.show_type_menu)
        hl.addWidget(self.type_btn)

        self.title = QLabel("", self.header)
        self.title.setStyleSheet("color:#bbb;font-size:12px;")
        hl.addWidget(self.title, 1)

        self.menu_btn = QToolButton(self.header)
        self.menu_btn.setStyleSheet(btn_css)
        self.menu_btn.setText("⋮")
        self.menu_btn.setCursor(Qt.PointingHandCursor)
        self.menu_btn.setToolTip("Alan seçenekleri (böl, kapat, büyüt)")
        self.menu_btn.clicked.connect(
            lambda: self.show_area_menu(self.menu_btn.mapToGlobal(QPoint(0, self.menu_btn.height()))))
        hl.addWidget(self.menu_btn)
        v.addWidget(self.header)

        self.body = QWidget(self)
        self.body.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        self.body.setMinimumSize(0, 0)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        v.addWidget(self.body, 1)

        self.corners = [CornerZone(self, i) for i in range(4)]

    # -- yerleşim
    def resizeEvent(self, e):
        super().resizeEvent(e)
        w, h = self.width(), self.height()
        c = CORNER
        pos = [(1, 1), (w - c - 1, 1), (w - c - 1, h - c - 1), (1, h - c - 1)]
        for z, (x, y) in zip(self.corners, pos):
            z.move(x, y)
        self.raise_corners()

    def raise_corners(self):
        for z in self.corners:
            z.raise_()

    # -- editör yaşam döngüsü
    def _detach(self):
        tid, w = self.editor_id, self.widget
        et = self.manager.registry.get(tid) if tid else None
        if w is not None:
            self.body_layout.removeWidget(w)
            w.hide()
            w.setParent(self.manager)      # unique editör burada "park" edilir
            w.hide()
        if et is not None and et.unique and et.owner is self:
            et.owner = None
        self.widget = None
        self.editor_id = None
        return tid, w

    def _dispose(self, tid, w):
        if w is None:
            return
        et = self.manager.registry.get(tid)
        if et is None or not et.unique:
            w.deleteLater()

    def _attach(self, tid, w=None):
        reg = self.manager.registry
        et = reg.get(tid)
        if et is None:
            tid = reg.fallback
            et = reg.get(tid)
        if w is None:
            w = et.widget(self.manager.context)
        if et.unique:
            et.owner = self
        self.editor_id = tid
        self.widget = w
        self.body_layout.addWidget(w)
        w.show()
        self.refresh_header()
        self.raise_corners()

    def set_editor(self, tid):
        reg = self.manager.registry
        et = reg.get(tid)
        if et is None or tid == self.editor_id:
            return
        if et.unique and et.owner is not None and et.owner is not self:
            # tek örnek başka alanda: iki alan editör değiştirir
            other = et.owner
            my_tid, my_w = self._detach()
            _, o_w = other._detach()
            self._attach(tid, o_w)
            if my_tid:
                other._attach(my_tid, my_w)
            else:
                other._attach(reg.fallback)
            self.manager.layoutChanged.emit()
            return
        old_tid, old_w = self._detach()
        self._dispose(old_tid, old_w)
        self._attach(tid)
        self.manager.layoutChanged.emit()

    def refresh_header(self):
        et = self.manager.registry.get(self.editor_id)
        if et is None:
            return
        self.type_btn.setIcon(et.icon)
        t = et.name
        if self.manager.maximized is self:
            t += "   — büyütülmüş (Ctrl+Space ile geri al)"
        self.title.setText(t)

    # -- menüler
    def show_type_menu(self):
        reg = self.manager.registry
        m = QMenu(self)
        m.setStyleSheet(MENU_CSS)
        hdr = m.addAction("Editör Türü")
        hdr.setEnabled(False)
        for et in reg.ordered():
            label = et.name
            if et.unique and et.owner not in (None, self):
                label += "  (buraya taşı)"
            k = reg.index(et.id)
            if 0 <= k < 8:
                label += "\tShift+F%d" % (k + 1)
            act = m.addAction(et.icon, label)
            act.setCheckable(True)
            act.setChecked(et.id == self.editor_id)
            act.triggered.connect(lambda _c=False, i=et.id: self.set_editor(i))
        m.exec_(self.type_btn.mapToGlobal(QPoint(0, self.type_btn.height())))

    def show_area_menu(self, gpos):
        mg = self.manager
        m = QMenu(self)
        m.setStyleSheet(MENU_CSS)
        a_v = m.addAction("Dikey Böl")
        a_h = m.addAction("Yatay Böl")
        m.addSeparator()
        a_max = m.addAction("Küçült (geri al)" if mg.maximized is self else "Büyüt\tCtrl+Space")
        a_close = m.addAction("Alanı Kapat")
        a_close.setEnabled(mg.maximized is None and len(mg.areas) > 1)
        a_v.setEnabled(mg.maximized is None)
        a_h.setEnabled(mg.maximized is None)
        m.addSeparator()
        a_reset = m.addAction("Düzeni Sıfırla (4 bölüm)")
        act = m.exec_(gpos)
        r = self.rect
        if act == a_v:
            mg.split(self, "v", (r[0] + r[2]) * 0.5)
        elif act == a_h:
            mg.split(self, "h", (r[1] + r[3]) * 0.5)
        elif act == a_max:
            mg.toggle_maximize(self)
        elif act == a_close:
            mg.close_area(self)
        elif act == a_reset:
            mg.reset_layout()


# ----------------------------------------------------------------------------
# Köşe sürükleme önizleme katmanı
# ----------------------------------------------------------------------------
class _Overlay(QWidget):
    def __init__(self, mgr):
        super().__init__(mgr)
        self.mgr = mgr
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, e):
        m = self.mgr
        st = m.corner_drag
        if not st or not st.get("mode"):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        g = GAP // 2
        a = st["area"]
        R = m.px_rect(a).adjusted(g, g, -g, -g)
        if st["mode"] == "split" and st.get("valid"):
            p.setPen(QPen(QColor(255, 255, 255, 230), 2))
            if st["orient"] == "v":
                x = int(round(st["pos"] * m.width()))
                p.fillRect(QRect(x, R.top(), R.right() - x, R.height()), QColor(255, 255, 255, 30))
                p.drawLine(x, R.top(), x, R.bottom())
            else:
                y = int(round(st["pos"] * m.height()))
                p.fillRect(QRect(R.left(), y, R.width(), R.bottom() - y), QColor(255, 255, 255, 30))
                p.drawLine(R.left(), y, R.right(), y)
        elif st["mode"] == "join" and st.get("target") is not None:
            t = st["target"]
            keep, gone = (a, t) if JOIN_ABSORBS_TARGET else (t, a)
            RG = m.px_rect(gone).adjusted(g, g, -g, -g)
            RK = m.px_rect(keep).adjusted(g, g, -g, -g)
            p.fillRect(RG, QColor(0, 0, 0, 150))
            p.setPen(QPen(QColor(255, 170, 40, 230), 2))
            p.setBrush(Qt.NoBrush)
            p.drawRect(RK.adjusted(1, 1, -1, -1))
            # genişleme oku
            c1 = QPointF(RK.center())
            c2 = QPointF(RG.center())
            d = c2 - c1
            ln = math.hypot(d.x(), d.y())
            if ln > 1:
                u = QPointF(d.x() / ln, d.y() / ln)
                nrm = QPointF(-u.y(), u.x())
                tip = c2
                base = QPointF(tip.x() - u.x() * 26, tip.y() - u.y() * 26)
                p.setPen(QPen(QColor(255, 255, 255, 220), 3))
                p.drawLine(QPointF(c1.x(), c1.y()), base)
                poly = QPolygonF([tip,
                                  QPointF(base.x() + nrm.x() * 12, base.y() + nrm.y() * 12),
                                  QPointF(base.x() - nrm.x() * 12, base.y() - nrm.y() * 12)])
                p.setBrush(QColor(255, 255, 255, 220))
                p.setPen(Qt.NoPen)
                p.drawPolygon(poly)


# ----------------------------------------------------------------------------
# Yönetici
# ----------------------------------------------------------------------------
class AreaManager(QWidget):
    layoutChanged = pyqtSignal()

    def __init__(self, registry, context=None, parent=None):
        super().__init__(parent)
        self.registry = registry
        self.context = context
        self.areas = []
        self.maximized = None
        self.edge_drag = None
        self.corner_drag = None
        self.setMouseTracking(True)
        self.setMinimumSize(200, 150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.overlay = _Overlay(self)

        QShortcut(QKeySequence("Ctrl+Space"), self, activated=self._shortcut_maximize)
        for i in range(8):
            QShortcut(QKeySequence("Shift+F%d" % (i + 1)), self,
                      activated=lambda k=i: self._shortcut_editor(k))

    # -- yardımcılar
    def paintEvent(self, e):
        QPainter(self).fillRect(self.rect(), QColor("#151515"))

    def px_rect(self, a):
        W, H = max(1, self.width()), max(1, self.height())
        r = a.rect
        x0, x1 = int(round(r[0] * W)), int(round(r[2] * W))
        y0, y1 = int(round(r[1] * H)), int(round(r[3] * H))
        return QRect(x0, y0, x1 - x0, y1 - y0)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.relayout()

    def relayout(self):
        g = GAP // 2
        for a in self.areas:
            if self.maximized is not None and a is not self.maximized:
                a.hide()
                continue
            r = self.rect() if self.maximized is not None else self.px_rect(a)
            a.setGeometry(r.adjusted(g, g, -g, -g))
            a.show()
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()
        self.overlay.update()

    def area_under_cursor(self):
        p = self.mapFromGlobal(QCursor.pos())
        for a in self.areas:
            if a.isVisible() and a.geometry().contains(p):
                return a
        return None

    # -- oluştur / yok et
    def new_area(self, rect, tid):
        a = Area(self, rect)
        self.areas.append(a)
        a.set_editor(tid)
        a.show()
        return a

    def _destroy_area(self, a):
        tid, w = a._detach()
        a._dispose(tid, w)
        if a in self.areas:
            self.areas.remove(a)
        if self.maximized is a:
            self.maximized = None
        a.hide()
        a.deleteLater()

    def clear(self):
        self.maximized = None
        for a in list(self.areas):
            self._destroy_area(a)

    def build_default(self, ids):
        """Ekranı 4 alana böler (2x2)."""
        self.clear()
        xs, ys = 0.6, 0.62
        rects = [[0, 0, xs, ys], [xs, 0, 1, ys], [0, ys, xs, 1], [xs, ys, 1, 1]]
        used = set()
        for r, tid in zip(rects, ids):
            et = self.registry.get(tid)
            if et is None or (et.unique and tid in used):
                tid = self.registry.fallback
            used.add(tid)
            self.new_area(r, tid)
        self.relayout()
        self.layoutChanged.emit()

    def reset_layout(self):
        ids = getattr(self, "default_ids", None) or [t.id for t in self.registry.ordered()[:4]]
        self.build_default(ids)

    # -- komşuluk
    def neighbor(self, a, direction):
        """a ile tam kenar paylaşan komşu (köşe-sürükleme birleştirmesi için)."""
        r = a.rect
        for b in self.areas:
            if b is a:
                continue
            s = b.rect
            same_y = abs(s[1] - r[1]) < EPS and abs(s[3] - r[3]) < EPS
            same_x = abs(s[0] - r[0]) < EPS and abs(s[2] - r[2]) < EPS
            if direction == "right" and abs(s[0] - r[2]) < EPS and same_y:
                return b
            if direction == "left" and abs(s[2] - r[0]) < EPS and same_y:
                return b
            if direction == "down" and abs(s[1] - r[3]) < EPS and same_x:
                return b
            if direction == "up" and abs(s[3] - r[1]) < EPS and same_x:
                return b
        return None

    def join(self, keep, gone):
        if keep is gone or keep not in self.areas or gone not in self.areas:
            return False
        keep.rect = [min(keep.rect[0], gone.rect[0]), min(keep.rect[1], gone.rect[1]),
                     max(keep.rect[2], gone.rect[2]), max(keep.rect[3], gone.rect[3])]
        self._destroy_area(gone)
        self.relayout()
        self.layoutChanged.emit()
        return True

    def close_area(self, a):
        if len(self.areas) < 2 or self.maximized is not None:
            return False
        for d in ("left", "right", "up", "down"):
            n = self.neighbor(a, d)
            if n is not None:
                return self.join(n, a)
        return False

    def split(self, a, orient, pos):
        """orient 'v': dikey çizgi (yan yana), 'h': yatay çizgi (alt alta). pos normalize."""
        W, H = max(1, self.width()), max(1, self.height())
        r = a.rect
        if orient == "v":
            lo, hi = r[0] + MIN_W / W, r[2] - MIN_W / W
        else:
            lo, hi = r[1] + MIN_H / H, r[3] - MIN_H / H
        if lo > hi:
            return None
        pos = max(lo, min(hi, pos))
        et = self.registry.get(a.editor_id)
        tid = a.editor_id
        if et is None or et.unique:
            tid = self.registry.fallback
        if orient == "v":
            new_rect = [pos, r[1], r[2], r[3]]
            a.rect[2] = pos
        else:
            new_rect = [r[0], pos, r[2], r[3]]
            a.rect[3] = pos
        n = self.new_area(new_rect, tid)
        self.relayout()
        self.layoutChanged.emit()
        return n

    # -- büyüt / küçült
    def toggle_maximize(self, a=None):
        if self.maximized is not None:
            self.maximized = None
        else:
            a = a or self.area_under_cursor()
            if a is None or len(self.areas) < 2:
                return
            self.maximized = a
        self.corner_drag = None
        self.edge_drag = None
        self.relayout()
        for x in self.areas:
            x.refresh_header()
        self.layoutChanged.emit()

    def _shortcut_maximize(self):
        self.toggle_maximize(self.area_under_cursor())

    def _shortcut_editor(self, k):
        a = self.area_under_cursor()
        ets = self.registry.ordered()
        if a is not None and 0 <= k < len(ets):
            a.set_editor(ets[k].id)

    # -- kenar sürükleme -------------------------------------------------
    def edge_at(self, p):
        W, H = max(1, self.width()), max(1, self.height())
        tol = GAP // 2 + 1
        best = None
        for a in self.areas:
            r = a.rect
            x0, x1, y0, y1 = r[0] * W, r[2] * W, r[1] * H, r[3] * H
            if r[2] < 1 - EPS and abs(p.x() - x1) <= tol and y0 - tol <= p.y() <= y1 + tol:
                d = abs(p.x() - x1)
                if best is None or d < best[0]:
                    best = (d, "v", r[2], a)
            if r[3] < 1 - EPS and abs(p.y() - y1) <= tol and x0 - tol <= p.x() <= x1 + tol:
                d = abs(p.y() - y1)
                if best is None or d < best[0]:
                    best = (d, "h", r[3], a)
        if best is None:
            return None
        return best[1], best[2], best[3]

    def _edge_chain(self, orient, c, seed):
        if orient == "v":
            hi_i, lo_i, iv = 2, 0, (1, 3)
        else:
            hi_i, lo_i, iv = 3, 1, (0, 2)
        cands = []
        for a in self.areas:
            if abs(a.rect[hi_i] - c) < EPS:
                cands.append((a, "hi"))
            if abs(a.rect[lo_i] - c) < EPS:
                cands.append((a, "lo"))
        cur = [seed.rect[iv[0]], seed.rect[iv[1]]]
        chosen = {id(seed)}
        changed = True
        while changed:
            changed = False
            for a, side in cands:
                if (id(a), side) in chosen or id(a) in chosen and a is seed:
                    pass
                key = (id(a), side)
                if key in chosen:
                    continue
                a0, a1 = a.rect[iv[0]], a.rect[iv[1]]
                if a0 <= cur[1] + EPS and a1 >= cur[0] - EPS:
                    chosen.add(key)
                    cur[0] = min(cur[0], a0)
                    cur[1] = max(cur[1], a1)
                    changed = True
        hi = [a for a, s in cands if s == "hi" and (id(a), s) in chosen]
        lo = [a for a, s in cands if s == "lo" and (id(a), s) in chosen]
        if seed not in hi:
            hi.append(seed)
        return hi, lo, hi_i, lo_i

    def _edge_begin(self, orient, c, seed):
        hi, lo, hi_i, lo_i = self._edge_chain(orient, c, seed)
        self.edge_drag = {"orient": orient, "hi": hi, "lo": lo, "hi_i": hi_i, "lo_i": lo_i}

    def _edge_move(self, p):
        st = self.edge_drag
        W, H = max(1, self.width()), max(1, self.height())
        if st["orient"] == "v":
            v, minn = p.x() / W, MIN_W / W
        else:
            v, minn = p.y() / H, MIN_H / H
        lower = max([a.rect[st["lo_i"]] + minn for a in st["hi"]] or [0.0])
        upper = min([b.rect[st["hi_i"]] - minn for b in st["lo"]] or [1.0])
        if lower > upper:
            return
        v = max(lower, min(upper, v))
        for a in st["hi"]:
            a.rect[st["hi_i"]] = v
        for b in st["lo"]:
            b.rect[st["lo_i"]] = v
        self.relayout()

    def mouseMoveEvent(self, e):
        if self.maximized is not None:
            self.unsetCursor()
            return
        if self.edge_drag:
            self._edge_move(e.pos())
            return
        hit = self.edge_at(e.pos())
        if hit:
            self.setCursor(Qt.SplitHCursor if hit[0] == "v" else Qt.SplitVCursor)
        else:
            self.unsetCursor()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.maximized is None:
            hit = self.edge_at(e.pos())
            if hit:
                self._edge_begin(*hit)
                e.accept()
                return
        e.ignore()

    def mouseReleaseEvent(self, e):
        if self.edge_drag:
            self.edge_drag = None
            self.layoutChanged.emit()
            e.accept()

    # -- köşe sürükleme --------------------------------------------------
    def corner_begin(self, area, corner, gpos):
        if self.maximized is not None:
            return
        self.corner_drag = {
            "area": area, "corner": corner, "start": self.mapFromGlobal(gpos),
            "mode": None, "orient": None, "pos": 0.0, "valid": False,
            "target": None, "dir": None,
        }

    def corner_move(self, gpos):
        st = self.corner_drag
        if not st:
            return
        p = self.mapFromGlobal(gpos)
        a = st["area"]
        d = p - st["start"]
        if st["mode"] is None and abs(d.x()) + abs(d.y()) < 6:
            return
        W, H = max(1, self.width()), max(1, self.height())
        R = self.px_rect(a)
        if R.contains(p):
            if st["mode"] != "split" or st["orient"] is None:
                st["orient"] = "v" if abs(d.x()) >= abs(d.y()) else "h"
            st["mode"] = "split"
            st["target"] = None
            r = a.rect
            if st["orient"] == "v":
                lo, hi = r[0] + MIN_W / W, r[2] - MIN_W / W
                val = p.x() / W
            else:
                lo, hi = r[1] + MIN_H / H, r[3] - MIN_H / H
                val = p.y() / H
            st["valid"] = lo <= hi
            st["pos"] = max(lo, min(hi, val)) if st["valid"] else val
        else:
            st["mode"] = "join"
            st["orient"] = None
            st["valid"] = False
            over = {
                "left": R.left() - p.x(), "right": p.x() - R.right(),
                "up": R.top() - p.y(), "down": p.y() - R.bottom(),
            }
            direction = max(over, key=over.get)
            st["dir"] = direction
            st["target"] = self.neighbor(a, direction)
        self.overlay.update()

    def corner_end(self):
        st = self.corner_drag
        self.corner_drag = None
        self.overlay.update()
        if not st:
            return
        a = st["area"]
        if st["mode"] == "split" and st.get("valid"):
            self.split(a, st["orient"], st["pos"])
        elif st["mode"] == "join" and st.get("target") is not None:
            t = st["target"]
            if JOIN_ABSORBS_TARGET:
                self.join(a, t)
            else:
                self.join(t, a)

    # -- kaydet / yükle --------------------------------------------------
    def to_dict(self):
        return {"areas": [{"rect": [round(v, 5) for v in a.rect], "editor": a.editor_id}
                          for a in self.areas]}

    def load_dict(self, d):
        items = d.get("areas", [])
        if not items:
            raise ValueError("boş düzen")
        total = 0.0
        rects = []
        for it in items:
            r = [float(v) for v in it["rect"]]
            if not (0 - EPS <= r[0] < r[2] <= 1 + EPS and 0 - EPS <= r[1] < r[3] <= 1 + EPS):
                raise ValueError("bozuk dikdörtgen")
            total += (r[2] - r[0]) * (r[3] - r[1])
            rects.append((r, str(it.get("editor"))))
        if abs(total - 1.0) > 1e-2:
            raise ValueError("alanlar ekranı kaplamıyor")
        self.clear()
        used = set()
        for r, tid in rects:
            et = self.registry.get(tid)
            if et is None or (et.unique and tid in used):
                tid = self.registry.fallback
            used.add(tid)
            self.new_area(r, tid)
        self.relayout()
        self.layoutChanged.emit()
