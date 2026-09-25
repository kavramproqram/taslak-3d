from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QHBoxLayout, QPushButton, QStackedWidget, QVBoxLayout, QWidget
)

from file_manager import FileManager


class _EmbeddedFileManager(FileManager):
    """FileManager'ı gömülü panel içinde kullanmak için close'u yutar."""

    def closeEvent(self, event):
        event.ignore()

    def hideEvent(self, event):
        # Gömülü widget gizlenmesin
        event.ignore()


class FilePanel(QWidget):
    """Dosya Yöneticisi paneli — ayrı pencere açmaz, gömülüdür."""

    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Mod değiştirme çubuğu
        bar = QHBoxLayout()
        self.btn_mode_open = QPushButton("İçe Aktarma Modu")
        self.btn_mode_export = QPushButton("Dışa Aktarma Modu")
        self.btn_mode_open.clicked.connect(lambda: self._set_mode("open"))
        self.btn_mode_export.clicked.connect(lambda: self._set_mode("export"))
        bar.addWidget(self.btn_mode_open)
        bar.addWidget(self.btn_mode_export)
        bar.addStretch(1)
        root.addLayout(bar)

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)

        # Import modunda gömülü FileManager
        self.fm_open = _EmbeddedFileManager(
            self, target_editor="Sphere", mode="open")
        self.fm_open.filesSelected.connect(self._import_paths)
        self.stack.addWidget(self.fm_open)

        # Export modunda gömülü FileManager
        self.fm_export = _EmbeddedFileManager(
            self,
            mode="export",
            export_callback=self._export_callback,
            filter_extensions={".k3d", ".glb", ".gltf"},
            default_export_name="scene",
            export_compression="xz")
        self.fm_export.exportCompleted.connect(self._export_done)
        self.stack.addWidget(self.fm_export)

        self.stack.setCurrentIndex(0)
        self._mode = "open"

    def _set_mode(self, mode):
        self._mode = mode
        self.stack.setCurrentIndex(0 if mode == "open" else 1)
        if mode == "export":
            self.fm_export.refresh_size if hasattr(self.fm_export, "refresh_size") else None
        # Widget görünür kalsın
        cur = self.stack.currentWidget()
        if cur:
            cur.show()

    def _import_paths(self, paths):
        for path in paths:
            try:
                self.controller.import_path(path)
            except Exception as exc:
                self.controller.toast(f"İçe aktarma hatası: {exc}")

    def _export_callback(self, path, compression):
        try:
            self.controller.export_scene(path)
            return True
        except Exception as exc:
            self.controller.toast(f"Dışa aktarma hatası: {exc}")
            return False

    def _export_done(self, path):
        self.controller.toast(f"Dışa aktarıldı: {path}")
