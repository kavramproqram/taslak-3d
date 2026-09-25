from __future__ import annotations

from PyQt5.QtCore import QMimeData, QPoint, QTimer, Qt, pyqtSignal
from PyQt5.QtGui import QDrag
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

PANEL_MIME = "application/x-kavram3d-panel"


class SignalHub(QWidget):
    toast = pyqtSignal(str)
    scene_changed = pyqtSignal()
    animation_changed = pyqtSignal()


class PanelHeader(QWidget):
    swap_requested = pyqtSignal(int, int)
    focus_requested = pyqtSignal(int)

    def __init__(self, title, pid_ref, parent=None):
        super().__init__(parent)
        self.pid_ref = pid_ref
        self.press = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 3, 4, 3)
        lay.setSpacing(4)
        grip = QLabel("⋮⋮")
        grip.setFixedWidth(18)
        grip.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(grip)
        title_label = QLabel(title)
        title_label.setProperty("panelTitle", True)
        title_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        lay.addWidget(title_label, 1)
        self.close_button = QPushButton("×")
        self.close_button.setObjectName("panelCloseBtn")
        self.close_button.setFixedSize(24, 24)
        self.close_button.clicked.connect(self._close)
        lay.addWidget(self.close_button)
        self.setAcceptDrops(True)

    def _close(self):
        p = self.parent()
        if p is not None and hasattr(p, "request_close"):
            p.request_close()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.press = e.pos()
            pid = self.pid_ref()
            if pid is not None:
                self.focus_requested.emit(pid)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self.press is None or not (e.buttons() & Qt.LeftButton):
            return super().mouseMoveEvent(e)
        if (e.pos() - self.press).manhattanLength() < 12:
            return
        src = self.pid_ref()
        if src is None:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(PANEL_MIME, str(src).encode())
        drag.setMimeData(mime)
        parent = self.parent()
        if parent is not None:
            pix = parent.grab()
            if pix.width() > 420:
                pix = pix.scaledToWidth(420, Qt.SmoothTransformation)
            drag.setPixmap(pix)
            drag.setHotSpot(self.press)
        self.press = None
        drag.exec_(Qt.MoveAction)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(PANEL_MIME):
            e.acceptProposedAction()

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(PANEL_MIME):
            e.ignore(); return
        try:
            src = int(bytes(e.mimeData().data(PANEL_MIME)).decode())
        except Exception:
            e.ignore(); return
        dst = self.pid_ref()
        if src != dst and dst is not None:
            self.swap_requested.emit(src, dst)
        e.acceptProposedAction()


class Panel(QFrame):
    close_requested = pyqtSignal(int)
    swap_requested = pyqtSignal(int, int)
    focus_requested = pyqtSignal(int)

    def __init__(self, pid, title, parent=None):
        super().__init__(parent)
        self.setMinimumSize(0, 0)
        self.panel_id = pid
        self.setProperty("panel", True)
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(0)
        self.header = PanelHeader(title, lambda: self.panel_id, self)
        self.header.focus_requested.connect(self.focus_requested)
        self.header.swap_requested.connect(self.swap_requested)
        self.body.addWidget(self.header)

    def request_close(self):
        self.close_requested.emit(self.panel_id)

    def set_focused(self, focused):
        self.setProperty("focused", bool(focused))
        self.style().unpolish(self); self.style().polish(self)


class PanelPlaceholder(QWidget):
    restore_clicked = pyqtSignal()
    def __init__(self, title, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self); lay.setContentsMargins(16, 16, 16, 16)
        lay.addStretch(1)
        info = QLabel(f"{title}\nkapalı")
        info.setAlignment(Qt.AlignCenter)
        info.setStyleSheet("color:#707070; font-weight:600;")
        lay.addWidget(info)
        self.button = QPushButton("+")
        self.button.setObjectName("restorePanelBtn")
        self.button.setFixedSize(72, 72)
        self.button.clicked.connect(self.restore_clicked)
        lay.addWidget(self.button, 0, Qt.AlignCenter)
        lay.addStretch(1)


class PanelSlot(QWidget):
    def __init__(self, position, title, parent=None):
        super().__init__(parent)
        self.position = position
        self.closed_pid = 0
        self.setMinimumSize(0, 0)
        self.stack = QStackedWidget(self)
        self.stack.setMinimumSize(0, 0)
        self.placeholder = PanelPlaceholder(title)
        self.stack.addWidget(self.placeholder)
        lay = QVBoxLayout(self); lay.setContentsMargins(0, 0, 0, 0); lay.setSpacing(0); lay.addWidget(self.stack)
        self.current_panel = None

    def set_panel(self, panel):
        if self.current_panel is panel and panel is not None:
            self.stack.setCurrentWidget(panel); return
        if self.current_panel is not None:
            old = self.current_panel
            self.stack.removeWidget(old)
            old.setParent(None)
        self.current_panel = panel
        if panel is None:
            self.stack.setCurrentWidget(self.placeholder)
            return
        self.stack.addWidget(panel)
        self.stack.setCurrentWidget(panel)

    def clear_panel(self): self.set_panel(None)
    def has_panel(self): return self.current_panel is not None


class Toast(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent); self.setObjectName("toast"); self.setAlignment(Qt.AlignCenter); self.hide()
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.hide)
    def show_message(self, text, msec=1200):
        self.setText(text); self.adjustSize()
        p = self.parent(); self.move(max(0, (p.width()-self.width())//2), max(0, p.height()-self.height()-48))
        self.show(); self.raise_(); self.timer.start(msec)
