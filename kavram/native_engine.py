from __future__ import annotations

import ctypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB_PATH = ROOT / "build" / "libkavram3d.so"


class RenderItem(ctypes.Structure):
    _fields_ = [
        ("id", ctypes.c_int),
        ("mesh_id", ctypes.c_int),
        ("selected", ctypes.c_int),
        ("model", ctypes.c_float * 16),
        ("color", ctypes.c_float * 4),
    ]


class NativeEngine:
    def __init__(self, path: Path = LIB_PATH):
        if not path.exists():
            raise RuntimeError(f"Native motor bulunamadı: {path}\nÖnce ./build.sh çalıştırın.")
        self.lib = ctypes.CDLL(str(path))
        P = ctypes.POINTER(ctypes.c_float)
        I = ctypes.c_int
        V = ctypes.c_void_p

        self.lib.kavram3d_create.restype = V
        self.lib.kavram3d_destroy.argtypes = [V]
        self.lib.kavram3d_reset.argtypes = [V]
        self.lib.kavram3d_set_viewport.argtypes = [V, I, I]
        self.lib.kavram3d_get_view_projection.argtypes = [V, P]
        self.lib.kavram3d_get_camera_position.argtypes = [V, P]
        self.lib.kavram3d_object_count.argtypes = [V]
        self.lib.kavram3d_object_id_at.argtypes = [V, I]
        self.lib.kavram3d_selected_id.argtypes = [V]
        self.lib.kavram3d_selected_count.argtypes = [V]
        self.lib.kavram3d_selected_id_at.argtypes = [V, I]
        self.lib.kavram3d_select.argtypes = [V, I]
        self.lib.kavram3d_toggle_select.argtypes = [V, I]
        self.lib.kavram3d_pick.argtypes = [V, ctypes.c_float, ctypes.c_float]
        self.lib.kavram3d_screen_to_ground.argtypes = [V, ctypes.c_float, ctypes.c_float, P]
        for name in ("kavram3d_rotate_view", "kavram3d_pan_view"):
            getattr(self.lib, name).argtypes = [V, ctypes.c_float, ctypes.c_float]
        self.lib.kavram3d_zoom_view.argtypes = [V, ctypes.c_float]
        self.lib.kavram3d_focus_selected.argtypes = [V]
        self.lib.kavram3d_set_preset.argtypes = [V, I]
        self.lib.kavram3d_toggle_projection.argtypes = [V]
        self.lib.kavram3d_is_orthographic.argtypes = [V]
        self.lib.kavram3d_ground_visible.argtypes = [V]
        for name in ("kavram3d_move_selected_drag", "kavram3d_rotate_selected_drag", "kavram3d_scale_selected_drag"):
            getattr(self.lib, name).argtypes = [V, ctypes.c_float, ctypes.c_float]
        self.lib.kavram3d_get_object_state.argtypes = [V, I, P, P, P]
        self.lib.kavram3d_set_object_state.argtypes = [V, I, P, P, P]
        self.lib.kavram3d_create_object.argtypes = [V, I, ctypes.c_char_p, ctypes.c_float, ctypes.c_float, ctypes.c_float]
        self.lib.kavram3d_add_object_at_surface.argtypes = [V, I, ctypes.c_float, ctypes.c_float, ctypes.c_char_p, I]
        self.lib.kavram3d_duplicate_selected_at_surface.argtypes = [V, ctypes.c_float, ctypes.c_float, I]
        self.lib.kavram3d_delete_object.argtypes = [V, I]
        self.lib.kavram3d_subdivide_selected.argtypes = [V]
        self.lib.kavram3d_set_mesh_bounds.argtypes = [V, I, P]
        self.lib.kavram3d_get_object_info.argtypes = [V, I, ctypes.POINTER(I), P, ctypes.POINTER(I), ctypes.POINTER(I), ctypes.POINTER(ctypes.c_float), ctypes.POINTER(I), ctypes.POINTER(I), ctypes.c_char_p, ctypes.c_size_t]
        self.lib.kavram3d_set_object_color.argtypes = [V, I, P]
        self.lib.kavram3d_set_object_motion.argtypes = [V, I, I, ctypes.c_float, I, I]
        self.lib.kavram3d_set_selected_motion.argtypes = [V, I, ctypes.c_float, I, I]
        self.lib.kavram3d_active_animation_count.argtypes = [V]
        self.lib.kavram3d_tick.argtypes = [V, ctypes.c_float]
        self.lib.kavram3d_render_item_count.argtypes = [V]
        self.lib.kavram3d_get_render_items.argtypes = [V, ctypes.POINTER(RenderItem), I]
        self.h = self.lib.kavram3d_create()
        if not self.h:
            raise RuntimeError("Native motor oluşturulamadı.")

    def close(self):
        if getattr(self, "h", None):
            self.lib.kavram3d_destroy(self.h)
            self.h = None

    def object_ids(self):
        n = self.lib.kavram3d_object_count(self.h)
        return [self.lib.kavram3d_object_id_at(self.h, i) for i in range(n)]

    def selected_ids(self):
        n = self.lib.kavram3d_selected_count(self.h)
        return [self.lib.kavram3d_selected_id_at(self.h, i) for i in range(n)]

    def state(self, oid: int):
        p = (ctypes.c_float * 3)(); r = (ctypes.c_float * 3)(); s = (ctypes.c_float * 3)()
        self.lib.kavram3d_get_object_state(self.h, oid, p, r, s)
        return tuple(p), tuple(r), tuple(s)

    def set_state(self, oid: int, state):
        p, r, s = state
        self.lib.kavram3d_set_object_state(self.h, oid, (ctypes.c_float * 3)(*p), (ctypes.c_float * 3)(*r), (ctypes.c_float * 3)(*s))

    def info(self, oid: int):
        mesh = ctypes.c_int(); color = (ctypes.c_float * 4)(); dup = ctypes.c_int(); enabled = ctypes.c_int()
        speed = ctypes.c_float(); mode = ctypes.c_int(); axis = ctypes.c_int(); name = ctypes.create_string_buffer(128)
        self.lib.kavram3d_get_object_info(self.h, oid, ctypes.byref(mesh), color, ctypes.byref(dup), ctypes.byref(enabled), ctypes.byref(speed), ctypes.byref(mode), ctypes.byref(axis), name, len(name))
        return {
            "mesh_id": mesh.value, "color": tuple(color[:3]), "duplicate": bool(dup.value),
            "motion_enabled": bool(enabled.value), "motion_speed": float(speed.value),
            "motion_mode": int(mode.value), "motion_axis": int(axis.value),
            "name": name.value.decode("utf-8", "replace"),
        }

    def render_items(self):
        n = self.lib.kavram3d_render_item_count(self.h)
        if n <= 0:
            return []
        arr = (RenderItem * n)()
        count = self.lib.kavram3d_get_render_items(self.h, arr, n)
        return [arr[i] for i in range(count)]

    def active_animation_count(self):
        return int(self.lib.kavram3d_active_animation_count(self.h))
