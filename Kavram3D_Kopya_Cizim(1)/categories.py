from __future__ import annotations
import json
from pathlib import Path

DEFAULT = {
    "Primitives": [
        {"name": "Cube", "mesh_id": 1, "builtin": True},
        {"name": "Sphere", "mesh_id": 2, "builtin": True},
        {"name": "Cylinder", "mesh_id": 3, "builtin": True},
        {"name": "Cone", "mesh_id": 4, "builtin": True},
        {"name": "Plane", "mesh_id": 5, "builtin": True},
    ],
    "Imported": [],
}


class CategoryStore:
    def __init__(self, path: Path):
        self.path = path
        self.data = {}
        self.load()

    def load(self):
        try:
            if self.path.exists():
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            self.data = {}
        if not isinstance(self.data, dict): self.data = {}
        changed = False
        for k, v in DEFAULT.items():
            if k not in self.data or not isinstance(self.data[k], list):
                self.data[k] = list(v); changed = True
        if changed: self.save()

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_category(self, name):
        name = (name or "").strip()
        if not name or name in self.data: return False
        self.data[name] = []
        self.save(); return True

    def add_asset(self, category, item):
        self.data.setdefault(category, []).append(item)
        self.save()

    def categories(self): return list(self.data.keys())
    def items(self, category): return list(self.data.get(category, []))
