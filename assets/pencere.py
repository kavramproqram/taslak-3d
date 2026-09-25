from __future__ import annotations

import json
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QListWidget, QListWidgetItem, QStackedWidget, QPushButton,
    QLabel, QMenu, QInputDialog
)

from viewport import GLView
from nomper import ShortcutsPanel
from object_panel import ObjectsPanel
from file_panel import FilePanel


class SideMenu(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setFixedWidth(190)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header = QHBoxLayout()
        title = QLabel("Alanlar")
        title.setStyleSheet("font-weight:700;")
        header.addWidget(title, 1)
        self.btn_flip = QPushButton("↔")
        self.btn_flip.setFixedSize(28, 24)
        self.btn_flip.setToolTip("Yan menüyü sağa/sola taşı (Y)")
        self.btn_flip.clicked.connect(self.main_window.flip_side_menu)
        header.addWidget(self.btn_flip)
        layout.addLayout(header)

        self.list = QListWidget()
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._context_menu)
        self.list.itemClicked.connect(self._clicked)
        layout.addWidget(self.list, 1)

        self.btn_add = QPushButton("+")
        self.btn_add.setFixedHeight(32)
        self.btn_add.clicked.connect(self._add_workspace)
        layout.addWidget(self.btn_add)

        self._populate()

    def _populate(self):
        self.list.clear()
        for name in self.main_window.CORE_PANELS:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, name)
            self.list.addItem(item)

    def _clicked(self, item):
        self.main_window.show_panel(item.data(Qt.UserRole))

    def _context_menu(self, pos):
        item = self.list.itemAt(pos)
        if not item:
            return
        name = item.data(Qt.UserRole)
        if name in self.main_window.CORE_PANELS:
            return
        menu = QMenu(self)
        act = menu.addAction("Sil")
        if menu.exec_(self.list.mapToGlobal(pos)) == act:
            self.main_window.remove_workspace(name)

    def _add_workspace(self):
        name, ok = QInputDialog.getText(self, "Yeni Çalışma Alanı", "Ad:")
        if ok and name.strip():
            self.main_window.add_workspace(name.strip())


class MainWindow(QMainWindow):
    CORE_PANELS = ["3D Alan", "Kısayollar", "Dosya Yöneticisi", "Nesne / Hareket"]

    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        controller.window = self
        self.setWindowTitle("Kavram")
        self.resize(1400, 850)
        self.setMinimumSize(900, 600)

        self._side_on_right = False
        self._fullscreen_panel = None

        self._build()
        self._wire()
        self._apply_styles()
        self._restore_layout()
        QApplication.instance().installEventFilter(self)
        self.show_panel("3D Alan")

    def _build(self):
        self.central = QWidget()
        self.setCentralWidget(self.central)
        self.layout = QHBoxLayout(self.central)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.side_menu = SideMenu(self)
        self.workspace = QStackedWidget()

        self.layout.addWidget(self.side_menu)
        self.layout.addWidget(self.workspace, 1)

        self.panels = {}
        self.panels["3D Alan"] = GLView(self.controller.engine)
        self.panels["Kısayollar"] = ShortcutsPanel(self.controller)
        self.panels["Dosya Yöneticisi"] = FilePanel(self.controller)
        self.panels["Nesne / Hareket"] = ObjectsPanel(self.controller)

        for w in self.panels.values():
            self.workspace.addWidget(w)

        self.panels["3D Alan"].controller = self.controller
        self.controller.view = self.panels["3D Alan"]
        self.controller.shortcuts_panel = self.panels["Kısayollar"]
        self.controller.file_panel = self.panels["Dosya Yöneticisi"]
        self.controller.object_panel = self.panels["Nesne / Hareket"]

    def _wire(self):
        self.controller.view.object_selected.connect(self._sync)
        self.controller.view.scene_changed.connect(self._sync)
        self.controller.view.status.connect(self.statusBar().showMessage)
        self.statusBar().showMessage("Hazır — T: menü, 1-4: alanlar, Sol tık: kopya, Ctrl+Sol tık: sil")

    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background:#202020; color:#ededed; }
            QListWidget { background:#181818; border:1px solid #3a3a3a; border-radius:4px; }
            QListWidget::item { padding:8px; }
            QListWidget::item:selected { background:#2a4a6a; }
            QPushButton { background:#292929; color:#f0f0f0; border:1px solid #555;
                          border-radius:4px; padding:6px; }
            QPushButton:hover { background:#3a3a3a; }
            QGroupBox { border:1px solid #3a3a3a; border-radius:4px; margin-top:8px; padding-top:8px; }
            QGroupBox::title { subcontrol-origin: margin; left:8px; padding:0 4px; }
            QTabWidget::pane { border:1px solid #3a3a3a; }
            QTabBar::tab { background:#252525; padding:6px 12px; }
            QTabBar::tab:selected { background:#2a4a6a; }
        """)

    def _sync(self):
        if self.controller.object_panel:
            self.controller.object_panel.refresh_objects()
        if self.controller.view:
            self.controller.view.update()

    def show_panel(self, name):
        if name not in self.panels:
            return
        self.workspace.setCurrentWidget(self.panels[name])
        for i in range(self.side_menu.list.count()):
            it = self.side_menu.list.item(i)
            if it.data(Qt.UserRole) == name:
                self.side_menu.list.setCurrentRow(i)
                break

    def add_workspace(self, name):
        if name in self.panels:
            return
        label = QLabel(f"Çalışma Alanı: {name}")
        label.setAlignment(Qt.AlignCenter)
        self.workspace.addWidget(label)
        self.panels[name] = label
        item = QListWidgetItem(name)
        item.setData(Qt.UserRole, name)
        self.side_menu.list.addItem(item)
        self._save_layout()

    def remove_workspace(self, name):
        if name in self.CORE_PANELS:
            return
        w = self.panels.pop(name, None)
        if w:
            self.workspace.removeWidget(w)
            w.deleteLater()
        for i in range(self.side_menu.list.count()):
            if self.side_menu.list.item(i).data(Qt.UserRole) == name:
                self.side_menu.list.takeItem(i)
                break
        self._save_layout()

    def toggle_side_menu(self):
        self.side_menu.setVisible(not self.side_menu.isVisible())

    def flip_side_menu(self):
        self.layout.removeWidget(self.side_menu)
        self.layout.removeWidget(self.workspace)
        if self._side_on_right:
            self.layout.addWidget(self.side_menu)
            self.layout.addWidget(self.workspace, 1)
            self._side_on_right = False
        else:
            self.layout.addWidget(self.workspace, 1)
            self.layout.addWidget(self.side_menu)
            self._side_on_right = True
        self._save_layout()

    def _save_layout(self):
        try:
            path = self.controller.root / "layout.json"
            data = {
                "side_on_right": self._side_on_right,
                "side_visible": self.side_menu.isVisible(),
                "current": self.workspace.currentIndex(),
                "workspaces": list(self.panels.keys()),
            }
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                            encoding="utf-8")
        except Exception:
            pass

    def _restore_layout(self):
        try:
            path = self.controller.root / "layout.json"
            if not path.exists():
                return
            data = json.loads(path.read_text(encoding="utf-8"))
            # Ek çalışma alanlarını geri yükle
            for name in data.get("workspaces", []):
                if name not in self.panels:
                    self.add_workspace(name)
            if data.get("side_on_right") and not self._side_on_right:
                self.flip_side_menu()
            if not data.get("side_visible", True):
                self.side_menu.setVisible(False)
        except Exception:
            pass

    def eventFilter(self, watched, event):
        if event.type() == event.KeyPress:
            self.controller.handle_key_event(event)
            if event.isAccepted():
                return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event):
        self._save_layout()
        self.controller.shutdown()
        event.accept()
