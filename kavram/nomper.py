from __future__ import annotations

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QGridLayout, QHBoxLayout, QInputDialog, QLabel, QListWidget,
    QListWidgetItem, QMenu, QPushButton, QTabWidget, QVBoxLayout, QWidget
)

from kyol import dispatch_action, ALIASES


NUMPAD_KEYS = [
    ("Num Lock", "NumLock", 0, 0), ("/", "Num/", 0, 1), ("*", "Num*", 0, 2), ("-", "Num-", 0, 3),
    ("7", "Num7", 1, 0), ("8", "Num8", 1, 1), ("9", "Num9", 1, 2), ("+", "Num+", 1, 3),
    ("4", "Num4", 2, 0), ("5", "Num5", 2, 1), ("6", "Num6", 2, 2), ("Enter", "NumEnter", 2, 3),
    ("1", "Num1", 3, 0), ("2", "Num2", 3, 1), ("3", "Num3", 3, 2), ("0", "Num0", 3, 3),
    (".", "Num.", 4, 0),
]

ACTION_ROWS = [
    ("Nesne ekle (+)", "add"),
    ("Seçiliyi sil (-)", "delete"),
    ("Seçili grubu kopyala", "duplicate"),
    ("Taşı (G)", "G"),
    ("Döndür (R)", "R"),
    ("Ölçek (S)", "S"),
    ("8 parçaya böl (/)", "subdivide"),
    ("Hareket başlat/durdur (*)", "motion"),
    ("Tam ekran (.)", "toggle_maximize"),
]


class ShortcutsPanel(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.numlock = True

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_numpad_tab(), "Numpad")
        self.tabs.addTab(self._build_shortcuts_tab(), "Kısayollar")
        root.addWidget(self.tabs)

    # ---------------- Numpad sekmesi ----------------
    def _build_numpad_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        title = QLabel("Kısayol / Numper")
        title.setStyleSheet("font-weight:700;")
        layout.addWidget(title)

        self.state = QLabel("Numper açık")
        layout.addWidget(self.state)

        grid = QGridLayout()
        grid.setSpacing(4)
        for label, key, r, c in NUMPAD_KEYS:
            b = QPushButton("÷" if key == "Num/" else label)
            b.setMinimumSize(QSize(48, 38))
            f = QFont("DejaVu Sans Mono", 10)
            f.setBold(True)
            b.setFont(f)
            b.clicked.connect(lambda _, k=key: self._numpad_click(k))
            grid.addWidget(b, r, c)
        layout.addLayout(grid)

        layout.addWidget(QLabel("Eylemler"))
        for label, key in ACTION_ROWS:
            b = QPushButton(label)
            b.clicked.connect(lambda _, k=key: self._action_click(k))
            layout.addWidget(b)

        layout.addStretch(1)
        return w

    def _numpad_click(self, key):
        if key == "NumLock":
            self.numlock = not self.numlock
            self.state.setText("Numper açık" if self.numlock else "Numper kilitli")
            return
        if not self.numlock:
            return
        self.controller.handle_numpad(key)

    def _action_click(self, key):
        target = ALIASES.get(key, key)
        dispatch_action(self.controller, target)

    def flash(self, key):
        self.state.setText(f"Son: {key}")

    # ---------------- Kısayol sekmesi ----------------
    def _build_shortcuts_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        info = QLabel("Sağ tık → Düzenle  (kısayolların hepsi buradan değişir)")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.shortcut_list = QListWidget()
        self.shortcut_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.shortcut_list.customContextMenuRequested.connect(self._context_menu)
        layout.addWidget(self.shortcut_list)

        self.refresh_shortcuts()
        return w

    def refresh_shortcuts(self):
        if not hasattr(self, "shortcut_list"):
            return
        self.shortcut_list.clear()
        for action, key in sorted(self.controller.shortcuts.items()):
            item = QListWidgetItem(f"{action:26s}  →  {key}")
            item.setData(Qt.UserRole, action)
            self.shortcut_list.addItem(item)

    # Controller tarafından çağrılır
    def refresh(self):
        self.refresh_shortcuts()

    def _context_menu(self, pos):
        item = self.shortcut_list.itemAt(pos)
        if not item:
            return
        action = item.data(Qt.UserRole)
        menu = QMenu(self)
        act = menu.addAction("Düzenle")
        if menu.exec_(self.shortcut_list.mapToGlobal(pos)) == act:
            self._edit(action)

    def _edit(self, action):
        current = self.controller.shortcuts.get(action, "")
        key, ok = QInputDialog.getText(
            self, "Kısayol Düzenle",
            f"{action} için yeni kısayol:",
            text=current)
        if ok and key.strip():
            self.controller.set_shortcut(action, key.strip())
            self.refresh_shortcuts()
