from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (
    QColorDialog, QComboBox, QDoubleSpinBox, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout,
    QWidget, QGroupBox, QFormLayout
)


class ObjectsPanel(QWidget):
    def __init__(self, controller, parent=None):
        super().__init__(parent)
        self.controller = controller
        self.categories = controller.categories
        self.selected_color = QColor(133, 138, 148)
        self._syncing = False

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(7)

        # Cisim türleri
        root.addWidget(QLabel("Cisim türleri"))
        self.category = QComboBox()
        self.category.currentTextChanged.connect(self._load_types)
        root.addWidget(self.category)
        self.types = QListWidget()
        self.types.setMaximumHeight(110)
        self.types.itemClicked.connect(self._type_clicked)
        root.addWidget(self.types)
        row = QHBoxLayout()
        self.btn_cat = QPushButton("+ Kategori")
        self.btn_add = QPushButton("+ Nesne")
        row.addWidget(self.btn_cat)
        row.addWidget(self.btn_add)
        root.addLayout(row)
        self.btn_cat.clicked.connect(self._add_category)
        self.btn_add.clicked.connect(self._add_object)

        # Sahnedeki nesneler
        root.addWidget(QLabel("Sahnedeki nesneler"))
        self.objects = QListWidget()
        self.objects.setSelectionMode(QListWidget.ExtendedSelection)
        self.objects.itemSelectionChanged.connect(self._selection_changed)
        root.addWidget(self.objects, 1)

        # Önizleme + info
        info_row = QHBoxLayout()
        self.preview_label = QLabel("Önizleme")
        self.preview_label.setFixedSize(200, 140)
        self.preview_label.setStyleSheet(
            "border:1px solid #444; background:#0a0a0a; border-radius:4px;"
        )
        self.preview_label.setAlignment(Qt.AlignCenter)
        info_row.addWidget(self.preview_label)
        self.info = QLabel("Seçim yok")
        self.info.setWordWrap(True)
        info_row.addWidget(self.info, 1)
        root.addLayout(info_row)

        # Renk
        color_box = QGroupBox("Renk")
        color_form = QFormLayout(color_box)
        self.color_btn = QPushButton("Renk seç")
        self.color_btn.clicked.connect(self._choose_color)
        color_form.addRow(self.color_btn)
        self.btn_apply_color = QPushButton("Rengi uygula")
        self.btn_apply_color.clicked.connect(self._apply_color)
        color_form.addRow(self.btn_apply_color)
        root.addWidget(color_box)

        # Dönüşüm
        tr_box = QGroupBox("Dönüşüm")
        tr_row = QHBoxLayout(tr_box)
        for label, mode in (("Taşı", "G"), ("Döndür", "R"), ("Ölçek", "S")):
            b = QPushButton(label)
            b.clicked.connect(lambda _, m=mode: controller.set_transform(m))
            tr_row.addWidget(b)
        root.addWidget(tr_box)

        # Hareket
        mot_box = QGroupBox("Hareket")
        mot_form = QFormLayout(mot_box)
        self.motion_mode = QComboBox()
        self.motion_mode.addItem("Hareketsiz", 0)
        self.motion_mode.addItem("Döndür", 1)
        self.motion_mode.addItem("Yukarı-aşağı", 2)
        self.motion_mode.addItem("Nefes", 3)
        mot_form.addRow("Mod:", self.motion_mode)
        self.motion_axis = QComboBox()
        self.motion_axis.addItem("X", 0)
        self.motion_axis.addItem("Y", 1)
        self.motion_axis.addItem("Z", 2)
        mot_form.addRow("Eksen:", self.motion_axis)
        self.speed = QDoubleSpinBox()
        self.speed.setRange(-20.0, 20.0)
        self.speed.setSingleStep(0.1)
        self.speed.setValue(1.0)
        self.speed.setDecimals(2)
        mot_form.addRow("Hız:", self.speed)
        self.btn_motion = QPushButton("Başlat")
        self.btn_motion.clicked.connect(self._toggle_motion)
        mot_form.addRow(self.btn_motion)
        root.addWidget(mot_box)

        self.btn_delete = QPushButton("Seçiliyi sil")
        self.btn_delete.clicked.connect(self._delete_selected)
        root.addWidget(self.btn_delete)
        self.btn_subdivide = QPushButton("8 parçaya böl")
        self.btn_subdivide.clicked.connect(controller.subdivide)
        root.addWidget(self.btn_subdivide)

        self.preview_timer = QTimer(self)
        self.preview_timer.timeout.connect(self._update_preview)
        self.preview_timer.start(600)

        self.refresh_categories()
        self.refresh_objects()

    def _update_preview(self):
        if self.controller.view and hasattr(self.controller.view, "grabFramebuffer"):
            try:
                pix = self.controller.view.grabFramebuffer()
                if not pix.isNull():
                    self.preview_label.setPixmap(
                        pix.scaled(self.preview_label.size(),
                                   Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception:
                pass

    def refresh_categories(self):
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItems(self.categories.categories())
        self.category.blockSignals(False)
        self._load_types(self.category.currentText())

    def refresh_objects(self):
        if self._syncing:
            return
        self._syncing = True
        selected = set(self.controller.engine.selected_ids())
        self.objects.clear()
        for oid in self.controller.engine.object_ids():
            info = self.controller.engine.info(oid)
            item = QListWidgetItem(f"{info['name']}  [#{oid}]")
            item.setData(Qt.UserRole, oid)
            item.setSelected(oid in selected)
            self.objects.addItem(item)
        self._syncing = False
        self._refresh_info()

    def _load_types(self, category):
        self.types.clear()
        for item in self.categories.items(category):
            li = QListWidgetItem(str(item.get("name", "Nesne")))
            li.setData(Qt.UserRole, item)
            self.types.addItem(li)
        if self.types.count():
            self.types.setCurrentRow(0)
        self._type_clicked(self.types.currentItem())

    def _type_clicked(self, item):
        if not item:
            return
        data = item.data(Qt.UserRole) or {}
        self.controller.set_draw_tool(int(data.get("mesh_id", 1)), str(data.get("name", "Nesne")))

    def _add_category(self):
        from PyQt5.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "Yeni kategori", "Kategori adı:")
        if ok and self.categories.add_category(name):
            self.refresh_categories()
            self.category.setCurrentText(name)

    def _add_object(self):
        if self.types.currentItem():
            self._type_clicked(self.types.currentItem())
        self.controller.add_current_center()

    def _selection_changed(self):
        if self._syncing:
            return
        ids = [int(x.data(Qt.UserRole)) for x in self.objects.selectedItems()]
        if not ids:
            self.controller.engine.lib.kavram3d_select(self.controller.engine.h, 0)
        elif len(ids) == 1:
            self.controller.engine.lib.kavram3d_select(self.controller.engine.h, ids[0])
        else:
            self.controller.engine.lib.kavram3d_select(self.controller.engine.h, ids[0])
            for oid in ids[1:]:
                self.controller.engine.lib.kavram3d_toggle_select(self.controller.engine.h, oid)
        self._refresh_info()
        if self.controller.view:
            self.controller.view.update()

    def _refresh_info(self):
        ids = self.controller.engine.selected_ids()
        if not ids:
            self.info.setText("Seçim yok")
            self.btn_motion.setText("Başlat")
            return
        info = self.controller.engine.info(ids[0])
        self.info.setText(f"{info['name']}\nMesh: {info['mesh_id']}\nSeçili: {len(ids)}")
        self.motion_mode.setCurrentIndex(self.motion_mode.findData(info["motion_mode"]))
        self.motion_axis.setCurrentIndex(self.motion_axis.findData(info["motion_axis"]))
        self.speed.setValue(info["motion_speed"])
        self.btn_motion.setText("Durdur" if info["motion_enabled"] else "Başlat")
        c = info["color"]
        self.selected_color = QColor.fromRgbF(*c)
        self._set_color_button()

    def _set_color_button(self):
        self.color_btn.setStyleSheet(
            f"background:{self.selected_color.name()}; color:#000; font-weight:700;")

    def _choose_color(self):
        c = QColorDialog.getColor(self.selected_color, self, "Cisim rengi")
        if c.isValid():
            self.selected_color = c
            self._set_color_button()
            self._apply_color()

    def _apply_color(self):
        rgb = (self.selected_color.redF(),
               self.selected_color.greenF(),
               self.selected_color.blueF())
        # Önce motor-seviyesindeki seçimi uygula
        for oid in self.controller.engine.selected_ids():
            self.controller.set_color(int(oid), rgb)
        # Sonra listedeki seçililere de uygula (kullanıcı listeden seçmiş olabilir)
        for item in self.objects.selectedItems():
            oid = int(item.data(Qt.UserRole))
            self.controller.set_color(oid, rgb)
        self.refresh_objects()

    def _toggle_motion(self):
        ids = self.controller.engine.selected_ids()
        if not ids:
            return
        enabled = not self.controller.engine.info(ids[0])["motion_enabled"]
        self.controller.set_motion(
            enabled, self.speed.value(),
            self.motion_mode.currentData(),
            self.motion_axis.currentData())
        self.refresh_objects()

    def _delete_selected(self):
        for oid in list(self.controller.engine.selected_ids()):
            self.controller.engine.lib.kavram3d_delete_object(
                self.controller.engine.h, oid)
        self.controller.scene_changed()
