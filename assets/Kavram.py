from __future__ import annotations

import sys
import json
import ctypes
from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QSurfaceFormat
from PyQt5.QtWidgets import QApplication

from native_engine import NativeEngine
from categories import CategoryStore
from ortam import EnvironmentStore
from scene_io import SceneIO
from pencere import MainWindow
from kyol import event_to_key, dispatch_action, ALIASES


class AppController:
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parent)
        self.engine = NativeEngine()
        self.categories = CategoryStore(self.root / "categories.json")
        self.environment = EnvironmentStore(self.root)
        self.scene_io = SceneIO(self)
        self.window = None
        self.view = None
        self.object_panel = None
        self.file_panel = None
        self.shortcuts_panel = None
        self.current_mesh_id = 1
        self.current_name = "Cube"
        self.shortcuts = self._load_shortcuts()

    def _shortcuts_path(self):
        return self.root / "shortcuts.json"

    def _default_shortcuts(self):
        return {
            "toggle_side_menu": "T",
            "flip_side_menu": "Y",
            "show_panel_1": "1",
            "show_panel_2": "2",
            "show_panel_3": "3",
            "show_panel_4": "4",
            "delete_selected": "Ctrl+Sol Tık + Sürükle",
            "duplicate_selected": "Sol Tık + Sürükle",
            "add_object": "Num+",
            "subdivide": "Num/",
            "toggle_motion": "Num*",
            "focus_selected": "Num6",
            "toggle_projection": "Num5",
            "preset_top": "Num7",
            "preset_front": "Num8",
            "preset_right": "Num9",
            "preset_home": "Num0",
            "toggle_maximize": "Num.",
            "export": "NumEnter",
            "transform_move": "G",
            "transform_rotate": "R",
            "transform_scale": "S",
        }

    def _load_shortcuts(self):
        path = self._shortcuts_path()
        defaults = self._default_shortcuts()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                for k, v in defaults.items():
                    data.setdefault(k, v)
                return data
            except Exception:
                pass
        return defaults

    def set_shortcut(self, action, key):
        self.shortcuts[action] = key
        self._shortcuts_path().write_text(
            json.dumps(self.shortcuts, ensure_ascii=False, indent=2),
            encoding="utf-8")
        if self.shortcuts_panel:
            self.shortcuts_panel.refresh()

    # ---------- işlemler ----------
    def toast(self, message):
        if self.window:
            self.window.statusBar().showMessage(message, 2500)

    def set_draw_tool(self, mesh_id, name):
        self.current_mesh_id = int(mesh_id)
        self.current_name = str(name)
        if self.view:
            self.view.set_draw_tool(mesh_id, name)
        self.toast(f"Çizim türü: {name}")

    def add_current_center(self):
        self.add_current()

    def delete_object(self, oid):
        self.engine.lib.kavram3d_delete_object(self.engine.h, int(oid))
        self.scene_changed()

    def set_color(self, oid, rgb):
        rgba = (ctypes.c_float * 4)(float(rgb[0]), float(rgb[1]), float(rgb[2]), 1.0)
        self.engine.lib.kavram3d_set_object_color(self.engine.h, int(oid), rgba)
        self.scene_changed()

    def add_current(self):
        if not self.view:
            return
        self.view.engine.lib.kavram3d_add_object_at_surface(
            self.view.engine.h, self.current_mesh_id,
            float(self.view.width()) * 0.5, float(self.view.height()) * 0.5,
            self.current_name.encode("utf-8"), 0)
        self.scene_changed()

    def duplicate_selected(self):
        if self.view:
            self.view.engine.lib.kavram3d_duplicate_selected_at_surface(
                self.view.engine.h,
                float(self.view.width()) * 0.5,
                float(self.view.height()) * 0.5, 0)
            self.scene_changed()

    def delete_selected(self):
        if not self.view:
            return
        self.engine.lib.kavram3d_delete_selected(self.engine.h)
        self.scene_changed()

    def subdivide(self):
        self.engine.lib.kavram3d_subdivide_selected(self.engine.h)
        self.scene_changed()
        self.toast("Seçili küp 8 parçaya bölündü")

    def set_transform(self, mode):
        if self.view:
            self.view.set_transform_mode(mode)

    def choose_draw_type(self, mesh_id, name):
        self.set_draw_tool(mesh_id, name)

    def apply_color(self, color):
        rgba = (ctypes.c_float * 4)(color.redF(), color.greenF(),
                                     color.blueF(), color.alphaF())
        for oid in self.engine.selected_ids():
            self.engine.lib.kavram3d_set_object_color(self.engine.h, oid, rgba)
        self.scene_changed()

    def set_motion(self, mode, speed, axis, enabled=True):
        self.engine.lib.kavram3d_set_selected_motion(
            self.engine.h, 1 if enabled else 0,
            float(speed), int(mode), int(axis))
        self.scene_changed()

    def scene_changed(self):
        if self.view:
            self.view.update()
        if self.object_panel:
            self.object_panel.refresh_objects()

    def import_path(self, path):
        try:
            ext = Path(path).suffix.lower()
            if ext in (".glb", ".gltf", ".blend", ".fbx", ".obj",
                       ".stl", ".ply", ".dae", ".3ds"):
                self.scene_io.import_asset(path)
            elif ext in (".k3d", ".kavram3d"):
                self.scene_io.import_scene(path)
            else:
                raise ValueError("Desteklenen giriş: glb, gltf, k3d, blend, fbx, obj, stl")
        except Exception as exc:
            self.toast(f"İçe aktarma hatası: {exc}")

    def export_scene(self, path):
        try:
            self.scene_io.export_scene(path)
        except Exception as exc:
            self.toast(f"Dışa aktarma hatası: {exc}")

    # ---------- klavye ----------
    def handle_key_event(self, event):
        if event.type() != event.KeyPress:
            event.ignore()
            return
        key = event_to_key(event)
        if not key:
            event.ignore()
            return

        for action, shortcut in self.shortcuts.items():
            if shortcut == key:
                target = ALIASES.get(action, action)
                if dispatch_action(self, target, event):
                    event.accept()
                    return

        if key == "Escape":
            if self.view:
                self.view.cancel_transform()
            event.accept()
            return
        event.ignore()

    def handle_numpad(self, key):
        # Numpad → eylem eşlemesi
        mapping = {
            "Num1": "show_panel_1", "Num2": "show_panel_2",
            "Num3": "show_panel_3", "Num4": "show_panel_4",
            "Num5": "toggle_projection",
            "Num6": "focus_selected",
            "Num7": "preset_top",
            "Num8": "preset_front",
            "Num9": "preset_right",
            "Num0": "preset_home",
            "Num+": "add_object",
            "Num-": "delete_selected",
            "Num*": "toggle_motion",
            "Num/": "subdivide",
            "Num.": "toggle_maximize",
            "NumEnter": "export",
        }
        action = mapping.get(key)
        if action:
            return dispatch_action(self, action)
        return False

    def tick(self):
        if not self.view:
            return
        active = self.engine.active_animation_count()
        if active:
            self.engine.lib.kavram3d_tick(self.engine.h, 1.0 / 60.0)
            self.view.update()

    def shutdown(self):
        self.engine.close()


def configure():
    fmt = QSurfaceFormat()
    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    fmt.setProfile(QSurfaceFormat.CoreProfile)
    fmt.setVersion(3, 3)
    fmt.setDepthBufferSize(24)
    fmt.setStencilBufferSize(8)
    fmt.setSwapInterval(1)
    QSurfaceFormat.setDefaultFormat(fmt)


def main():
    configure()
    app = QApplication(sys.argv)
    app.setApplicationName("Kavram")
    app.setOrganizationName("Kavram")
    controller = AppController()
    window = MainWindow(controller)

    timer = QTimer(window)
    timer.setInterval(16)
    timer.timeout.connect(controller.tick)
    timer.start()

    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
