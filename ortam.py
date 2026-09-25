from __future__ import annotations

import json
from pathlib import Path

DEFAULT_LAYOUT={"left_top":1,"left_bottom":2,"right_top":3,"right_bottom":4}


class EnvironmentStore:
    def __init__(self, base_dir):
        self.path=Path(base_dir)/"environments.json"; self.current="Ana Sphere"; self.environments={}; self.load()

    def load(self):
        try: self.environments=json.loads(self.path.read_text(encoding="utf-8")).get("environments",{})
        except Exception: self.environments={}
        if "Ana Sphere" not in self.environments:
            self.environments["Ana Sphere"]={"layout":dict(DEFAULT_LAYOUT)}
            self.save()
        return self.get_layout()

    def save(self, state=None):
        if state is not None:
            self.environments.setdefault(self.current, {})["layout"] = dict(state)
        self.path.write_text(json.dumps({"current":self.current,"environments":self.environments},ensure_ascii=False,indent=2),encoding="utf-8")

    def get_layout(self): return dict(self.environments.get(self.current,{}).get("layout",DEFAULT_LAYOUT))
    def set_layout(self,layout): self.environments.setdefault(self.current,{})["layout"]=dict(layout); self.save()
