from __future__ import annotations

import json
import shutil
import hashlib
import ctypes
from pathlib import Path


class SceneIO:
    def __init__(self, controller):
        self.controller = controller
        self.root = controller.root
        self.assets_dir = self.root / "assets"
        self.assets_dir.mkdir(parents=True, exist_ok=True)

    def _rel(self, path: Path) -> str:
        try:
            return str(path.resolve().relative_to(self.root.resolve()))
        except Exception:
            return str(path)

    def _stage_asset(self, src: Path) -> Path:
        digest = hashlib.sha1(str(src).encode("utf-8")).hexdigest()[:10]
        if src.suffix.lower() == ".glb":
            target = self.assets_dir / f"{src.stem}-{digest}.glb"
            if src != target:
                shutil.copy2(src, target)
            return target
        package = self.assets_dir / f"{src.stem}-{digest}"
        package.mkdir(parents=True, exist_ok=True)
        target = package / src.name
        shutil.copy2(src, target)
        try:
            data = json.loads(src.read_text(encoding="utf-8"))
        except Exception:
            return target
        for buf in data.get("buffers", []):
            uri = buf.get("uri")
            if not uri or uri.startswith("data:"):
                continue
            import urllib.parse
            rel = Path(urllib.parse.unquote(uri))
            if rel.is_absolute():
                continue
            source_buf = (src.parent / rel).resolve()
            if not source_buf.exists() or not source_buf.is_file():
                continue
            dest_buf = (package / rel).resolve()
            dest_buf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_buf, dest_buf)
        return target

    def import_asset(self, source: str):
        src = Path(source).resolve()
        ext = src.suffix.lower()
        if ext not in (".glb", ".gltf", ".blend", ".fbx", ".obj",
                       ".stl", ".ply", ".dae", ".3ds"):
            raise ValueError("Desteklenen 3D formatı: glb, gltf, blend, fbx, obj, stl, ply, dae, 3ds.")
        target = self._stage_asset(src)
        mesh_id, half = self.controller.view.register_imported_mesh(str(target))
        item = {"name": src.stem, "mesh_id": mesh_id, "builtin": False, "asset": self._rel(target)}
        self.controller.categories.add_asset("Imported", item)
        self.controller.object_panel.refresh_categories()
        self.controller.set_draw_tool(mesh_id, src.stem)
        self.controller.toast(f"Model eklendi: {src.name}")
        return mesh_id, item

    def export_scene(self, save_path: str, compression: str = "xz"):
        path = Path(save_path)
        if path.suffix.lower() not in (".k3d", ".kavram3d"):
            path = path.with_suffix(".k3d")
        path.parent.mkdir(parents=True, exist_ok=True)
        objects=[]; assets=[]
        for oid in self.controller.engine.object_ids():
            info=self.controller.engine.info(oid); pos,rot,scale=self.controller.engine.state(oid)
            asset=None
            for category in self.controller.categories.categories():
                for item in self.controller.categories.items(category):
                    if int(item.get("mesh_id",-1))==info["mesh_id"] and not item.get("builtin"):
                        asset=item.get("asset"); break
                if asset: break
            objects.append({"id":oid,"name":info["name"],"mesh_id":info["mesh_id"],"position":pos,"rotation":rot,"scale":scale,"color":info["color"],"duplicate":info["duplicate"],"motion":{"enabled":info["motion_enabled"],"speed":info["motion_speed"],"mode":info["motion_mode"],"axis":info["motion_axis"]},"asset":asset})
        seen=set()
        for category in self.controller.categories.categories():
            for item in self.controller.categories.items(category):
                if item.get("asset") and item["asset"] not in seen:
                    assets.append(dict(item)); seen.add(item["asset"])
        data={"format":"Kavram3D","version":2,"assets":assets,"objects":objects}
        text=json.dumps(data,ensure_ascii=False,indent=2)
        if compression == "xz":
            import lzma; path.write_bytes(lzma.compress(text.encode("utf-8"), preset=6))
        elif compression == "gz":
            import gzip; path.write_bytes(gzip.compress(text.encode("utf-8"), compresslevel=6))
        else:
            path.write_text(text,encoding="utf-8")
        self.controller.toast(f"Sahne dışa aktarıldı: {path.name}")
        return True

    def import_scene(self, source: str):
        path=Path(source).resolve()
        raw=path.read_bytes()
        if raw[:6] == b"\xfd7zXZ\x00":
            import lzma; data=json.loads(lzma.decompress(raw).decode("utf-8"))
        elif raw[:2] == b"\x1f\x8b":
            import gzip; data=json.loads(gzip.decompress(raw).decode("utf-8"))
        else:
            data=json.loads(raw.decode("utf-8"))

        engine=self.controller.engine
        engine.lib.kavram3d_reset(engine.h)
        for asset in data.get("assets", []):
            rel=asset.get("asset")
            if not rel:
                continue
            asset_path=(self.root/rel).resolve()
            if not asset_path.exists():
                continue
            mesh_id=int(asset.get("mesh_id", 0))
            try:
                if mesh_id not in self.controller.view.meshes:
                    self.controller.view.register_imported_mesh(str(asset_path), preferred_id=mesh_id)
            except Exception:
                continue
            self.controller.categories.add_asset("Imported", asset)

        # Varsayılan küpü, sahne dosyası en az bir nesne içeriyorsa silmek için
        # önce yeni nesneleri oluşturuyoruz; motor son tek nesneyi silmez.
        default_id=engine.object_ids()[0] if engine.object_ids() else 0
        first_created=0
        for obj in data.get("objects", []):
            p=obj.get("position", [0,0,.5])
            rid=engine.lib.kavram3d_create_object(
                engine.h, int(obj.get("mesh_id",1)),
                str(obj.get("name","Nesne")).encode("utf-8"),
                float(p[0]), float(p[1]), float(p[2])
            )
            if not first_created:
                first_created=rid
            engine.set_state(rid,(obj.get("position",p),obj.get("rotation",[0,0,0]),obj.get("scale",[1,1,1])))
            c=obj.get("color")
            if c:
                engine.lib.kavram3d_set_object_color(engine.h,rid,(ctypes.c_float*4)(float(c[0]),float(c[1]),float(c[2]),1.0))
            m=obj.get("motion",{})
            engine.lib.kavram3d_set_object_motion(engine.h,rid,1 if m.get("enabled") else 0,float(m.get("speed",1)),int(m.get("mode",0)),int(m.get("axis",2)))
        if first_created and default_id and default_id != first_created:
            engine.lib.kavram3d_delete_object(engine.h,default_id)
        engine.lib.kavram3d_select(engine.h, first_created or (engine.object_ids()[0] if engine.object_ids() else 0))
        self.controller.object_panel.refresh_categories()
        self.controller.object_panel.refresh_objects()
        self.controller.view.update()
        self.controller.toast(f"Sahne içe aktarıldı: {path.name}")
        return True
