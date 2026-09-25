from __future__ import annotations

from PyQt5.QtCore import Qt

NUMPAD_SET = {
    Qt.Key_0, Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4,
    Qt.Key_5, Qt.Key_6, Qt.Key_7, Qt.Key_8, Qt.Key_9,
    Qt.Key_Plus, Qt.Key_Minus, Qt.Key_Asterisk, Qt.Key_Slash,
    Qt.Key_Period, Qt.Key_Return, Qt.Key_Enter,
}


def event_to_key(event):
    mods = []
    if event.modifiers() & Qt.ControlModifier:
        mods.append("Ctrl")
    if event.modifiers() & Qt.ShiftModifier:
        mods.append("Shift")
    if event.modifiers() & Qt.AltModifier:
        mods.append("Alt")

    key_map = {
        Qt.Key_T: "T", Qt.Key_C: "C", Qt.Key_Y: "Y", Qt.Key_Space: "Space",
        Qt.Key_1: "1", Qt.Key_2: "2", Qt.Key_3: "3", Qt.Key_4: "4",
        Qt.Key_5: "5", Qt.Key_6: "6", Qt.Key_7: "7", Qt.Key_8: "8",
        Qt.Key_9: "9", Qt.Key_0: "0",
        Qt.Key_Plus: "Num+", Qt.Key_Minus: "Num-",
        Qt.Key_Asterisk: "Num*", Qt.Key_Slash: "Num/",
        Qt.Key_Period: "Num.", Qt.Key_Return: "NumEnter",
        Qt.Key_Enter: "NumEnter",
    }
    base = key_map.get(event.key(), "")
    if not base:
        text = event.text().strip()
        if text:
            base = text.upper()
    if not base:
        return ""

    # Numpad ayrımı
    if event.modifiers() & Qt.KeypadModifier and base in "0123456789":
        base = "Num" + base

    return "+".join(mods + [base])


def dispatch_action(controller, action, event=None):
    win = controller.window

    if action == "toggle_side_menu":
        if win: win.toggle_side_menu(); return True
    if action == "flip_side_menu":
        if win: win.flip_side_menu(); return True
    if action == "show_panel_1":
        if win: win.show_panel(win.CORE_PANELS[0]); return True
    if action == "show_panel_2":
        if win: win.show_panel(win.CORE_PANELS[1]); return True
    if action == "show_panel_3":
        if win: win.show_panel(win.CORE_PANELS[2]); return True
    if action == "show_panel_4":
        if win: win.show_panel(win.CORE_PANELS[3]); return True

    if action == "delete_selected":
        controller.delete_selected(); return True
    if action == "duplicate_selected":
        controller.duplicate_selected(); return True
    if action == "add_object":
        controller.add_current(); return True
    if action == "subdivide":
        controller.subdivide(); return True
    if action == "toggle_motion":
        if controller.object_panel:
            controller.object_panel._toggle_motion()
        return True
    if action in ("transform_move", "G"):
        controller.set_transform("G"); return True
    if action in ("transform_rotate", "R"):
        controller.set_transform("R"); return True
    if action in ("transform_scale", "S"):
        controller.set_transform("S"); return True

    if action == "focus_selected":
        if controller.view:
            controller.view.engine.lib.kavram3d_focus_selected(controller.view.engine.h)
            controller.view.update()
        return True
    if action == "toggle_projection":
        if controller.view:
            controller.view.engine.lib.kavram3d_toggle_projection(controller.view.engine.h)
            controller.view.update()
        return True
    if action == "preset_top":
        controller.view.engine.lib.kavram3d_set_preset(controller.view.engine.h, 1)
        controller.view.update(); return True
    if action == "preset_front":
        controller.view.engine.lib.kavram3d_set_preset(controller.view.engine.h, 3)
        controller.view.update(); return True
    if action == "preset_right":
        controller.view.engine.lib.kavram3d_set_preset(controller.view.engine.h, 7)
        controller.view.update(); return True
    if action == "preset_home":
        controller.view.engine.lib.kavram3d_set_preset(controller.view.engine.h, 0)
        controller.view.update(); return True
    if action == "toggle_maximize":
        if win:
            if win.isMaximized(): win.showNormal()
            else: win.showMaximized()
        return True
    if action == "export":
        if controller.file_panel:
            controller.file_panel._set_mode("export")
        return True
    return False


# Alias: eski numpad eylem butonları için
ALIASES = {
    "add": "add_object",
    "delete": "delete_selected",
    "duplicate": "duplicate_selected",
    "motion": "toggle_motion",
    "G": "transform_move",
    "R": "transform_rotate",
    "S": "transform_scale",
}
