"""Minimal dependency-free glTF 2.0 / GLB loader for Kavram3D.
Only triangle primitives with POSITION/NORMAL are consumed; textures remain external.
"""
from __future__ import annotations

import base64
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MeshData:
    vertices: list[float]
    half_extents: tuple[float, float, float]
    primitive_count: int = 0
    name: str = "Nesne"
    color: tuple[float, float, float, float] = (0.55, 0.58, 0.62, 1.0)
    group_name: str = "Imported"
    origin: tuple[float, float, float] = (0.0, 0.0, 0.0)


def _mat_mul(a: list[float], b: list[float]) -> list[float]:
    out = [0.0] * 16
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = (
                a[r] * b[c * 4] + a[4 + r] * b[c * 4 + 1] +
                a[8 + r] * b[c * 4 + 2] + a[12 + r] * b[c * 4 + 3]
            )
    return out


def _node_matrix(node: dict) -> list[float]:
    if "matrix" in node:
        return list(map(float, node["matrix"]))
    t = node.get("translation", [0.0, 0.0, 0.0])
    q = node.get("rotation", [0.0, 0.0, 0.0, 1.0])
    s = node.get("scale", [1.0, 1.0, 1.0])
    x, y, z, w = map(float, q)
    xx, yy, zz = x*x, y*y, z*z
    xy, xz, yz = x*y, x*z, y*z
    wx, wy, wz = w*x, w*y, w*z
    return [
        (1 - 2*(yy+zz))*s[0], (2*(xy+wz))*s[0], (2*(xz-wy))*s[0], 0,
        (2*(xy-wz))*s[1], (1 - 2*(xx+zz))*s[1], (2*(yz+wx))*s[1], 0,
        (2*(xz+wy))*s[2], (2*(yz-wx))*s[2], (1 - 2*(xx+yy))*s[2], 0,
        float(t[0]), float(t[1]), float(t[2]), 1,
    ]


def _transform_point(m: list[float], p: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        m[0]*p[0] + m[4]*p[1] + m[8]*p[2] + m[12],
        m[1]*p[0] + m[5]*p[1] + m[9]*p[2] + m[13],
        m[2]*p[0] + m[6]*p[1] + m[10]*p[2] + m[14],
    )


def _transform_normal(m: list[float], n: tuple[float, float, float]) -> tuple[float, float, float]:
    # For rotation/uniform scale this is sufficient and avoids a matrix inverse.
    x = m[0]*n[0] + m[4]*n[1] + m[8]*n[2]
    y = m[1]*n[0] + m[5]*n[1] + m[9]*n[2]
    z = m[2]*n[0] + m[6]*n[1] + m[10]*n[2]
    d = math.sqrt(x*x + y*y + z*z) or 1.0
    return x/d, y/d, z/d


def _load_container(path: Path) -> tuple[dict, bytes, Path | None]:
    raw = path.read_bytes()
    if path.suffix.lower() == ".glb":
        if len(raw) < 20 or raw[:4] != b"glTF":
            raise ValueError("Geçersiz GLB başlığı.")
        version, length = struct.unpack_from("<II", raw, 4)
        if version != 2 or length > len(raw):
            raise ValueError("Yalnızca glTF 2.0 GLB destekleniyor.")
        off = 12
        json_blob = None
        bin_blob = b""
        while off + 8 <= length:
            size, kind = struct.unpack_from("<II", raw, off)
            off += 8
            chunk = raw[off:off+size]
            off += size
            if kind == 0x4E4F534A:
                json_blob = chunk.rstrip(b" \t\r\n\x00")
            elif kind == 0x004E4942:
                bin_blob = chunk
        if json_blob is None:
            raise ValueError("GLB JSON bölümü bulunamadı.")
        return json.loads(json_blob.decode("utf-8")), bin_blob, None

    doc = json.loads(raw.decode("utf-8"))
    return doc, b"", path.parent


def _buffers(doc: dict, embedded: bytes, base_dir: Path | None) -> list[bytes]:
    out = []
    for i, b in enumerate(doc.get("buffers", [])):
        uri = b.get("uri")
        if not uri:
            out.append(embedded)
            continue
        if uri.startswith("data:"):
            _, encoded = uri.split(",", 1)
            out.append(base64.b64decode(encoded))
            continue
        if base_dir is None:
            raise ValueError("Harici glTF bufferı için klasör yok.")
        out.append((base_dir / uri).resolve().read_bytes())
    return out


def _component_format(component_type: int):
    return {
        5120: ("b", 1, False), 5121: ("B", 1, False),
        5122: ("h", 2, False), 5123: ("H", 2, False),
        5125: ("I", 4, False), 5126: ("f", 4, False),
    }.get(component_type)


def _type_width(type_name: str) -> int:
    return {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}.get(type_name, 1)


def _read_accessor(doc: dict, buffers: list[bytes], accessor_index: int) -> list[tuple[float, ...]]:
    acc = doc["accessors"][accessor_index]
    if acc.get("sparse"):
        raise ValueError("Sparse accessor henüz desteklenmiyor.")
    fmt_info = _component_format(acc["componentType"])
    if not fmt_info:
        raise ValueError(f"Desteklenmeyen componentType: {acc['componentType']}")
    fmt, component_size, _ = fmt_info
    width = _type_width(acc["type"])
    view = doc["bufferViews"][acc["bufferView"]]
    buf = buffers[view["buffer"]]
    offset = int(view.get("byteOffset", 0)) + int(acc.get("byteOffset", 0))
    stride = int(view.get("byteStride", component_size * width))
    normalized = bool(acc.get("normalized", False))

    def decode(value):
        if not normalized:
            return float(value)
        if acc["componentType"] == 5120:
            return max(-1.0, float(value) / 127.0)
        if acc["componentType"] == 5121:
            return float(value) / 255.0
        if acc["componentType"] == 5122:
            return max(-1.0, float(value) / 32767.0)
        if acc["componentType"] == 5123:
            return float(value) / 65535.0
        return float(value)

    result = []
    unpack_fmt = "<" + fmt * width
    for i in range(int(acc["count"])):
        start = offset + i * stride
        end = start + component_size * width
        values = struct.unpack(unpack_fmt, buf[start:end])
        result.append(tuple(decode(v) for v in values))
    return result



def _material_color(doc: dict, material_index: int | None):
    try:
        if material_index is None:
            return (0.55, 0.58, 0.62, 1.0)
        mat = doc.get("materials", [])[int(material_index)]
        pbr = mat.get("pbrMetallicRoughness", {})
        c = pbr.get("baseColorFactor", [0.55, 0.58, 0.62, 1.0])
        if len(c) == 4:
            return tuple(float(max(0.0, min(1.0, x))) for x in c)
    except Exception:
        pass
    return (0.55, 0.58, 0.62, 1.0)


def load_gltf_scene(path: str | Path) -> list[MeshData]:
    """Load each renderable glTF node as a separate Kavram object.

    This intentionally does not merge nodes into one mesh, so an imported
    atom/assembly remains a collection of independent objects that can be
    multi-selected and duplicated as a group.
    """
    path = Path(path).resolve()
    doc, embedded, base_dir = _load_container(path)
    buffers = _buffers(doc, embedded, base_dir)
    nodes = doc.get("nodes", [])
    meshes = doc.get("meshes", [])
    scenes = doc.get("scenes", [])
    scene_idx = int(doc.get("scene", 0)) if scenes else -1
    roots = scenes[scene_idx].get("nodes", []) if scene_idx >= 0 else list(range(len(nodes)))
    result: list[MeshData] = []

    def visit(node_index: int, parent: list[float], group_name: str):
        node = nodes[node_index]
        world = _mat_mul(parent, _node_matrix(node))
        mesh_index = node.get("mesh")
        node_vertices: list[float] = []
        all_min = [float("inf")] * 3
        all_max = [float("-inf")] * 3
        primitive_count = 0
        colors=[]
        if mesh_index is not None:
            mesh = meshes[int(mesh_index)]
            for primitive in mesh.get("primitives", []):
                if int(primitive.get("mode", 4)) != 4:
                    continue
                attrs = primitive.get("attributes", {})
                if "POSITION" not in attrs:
                    continue
                pos = _read_accessor(doc, buffers, int(attrs["POSITION"]))
                nor = _read_accessor(doc, buffers, int(attrs["NORMAL"])) if "NORMAL" in attrs else None
                indices = _read_accessor(doc, buffers, int(primitive["indices"])) if "indices" in primitive else [(float(i),) for i in range(len(pos))]
                idx = [int(v[0]) for v in indices]
                if len(idx) % 3:
                    idx = idx[:len(idx) - len(idx) % 3]
                if nor is None:
                    accum = [[0.0, 0.0, 0.0] for _ in pos]
                    for t in range(0, len(idx), 3):
                        a,b,c=pos[idx[t]],pos[idx[t+1]],pos[idx[t+2]]
                        ab=(b[0]-a[0],b[1]-a[1],b[2]-a[2]); ac=(c[0]-a[0],c[1]-a[1],c[2]-a[2])
                        fn=(ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0])
                        for vi in (idx[t],idx[t+1],idx[t+2]):
                            accum[vi][0]+=fn[0];accum[vi][1]+=fn[1];accum[vi][2]+=fn[2]
                    nor=[]
                    for n in accum:
                        ln=math.sqrt(n[0]*n[0]+n[1]*n[1]+n[2]*n[2]) or 1.0
                        nor.append((n[0]/ln,n[1]/ln,n[2]/ln))
                for vi in idx:
                    p3=_transform_point(world, tuple(map(float,pos[vi][:3])))
                    n3=_transform_normal(world, tuple(map(float,nor[vi][:3])))
                    node_vertices.extend((p3[0],p3[1],p3[2],n3[0],n3[1],n3[2]))
                    for j in range(3):
                        all_min[j]=min(all_min[j],p3[j]); all_max[j]=max(all_max[j],p3[j])
                colors.append(_material_color(doc, primitive.get("material")))
                primitive_count += 1
        if node_vertices:
            center=((all_min[0]+all_max[0])*0.5,
                    (all_min[1]+all_max[1])*0.5,
                    (all_min[2]+all_max[2])*0.5)
            centered=[]
            for i in range(0,len(node_vertices),6):
                centered.extend((node_vertices[i]-center[0],node_vertices[i+1]-center[1],node_vertices[i+2]-center[2],
                                 node_vertices[i+3],node_vertices[i+4],node_vertices[i+5]))
            half=tuple(max(0.001,(all_max[i]-all_min[i])*0.5) for i in range(3))
            if colors:
                color=tuple(sum(c[k] for c in colors)/len(colors) for k in range(4))
            else:
                color=(0.55,0.58,0.62,1.0)
            node_name=str(node.get("name") or f"{group_name}_{node_index}")
            result.append(MeshData(centered, half, primitive_count, node_name, color, group_name, center))
        for child in node.get("children", []):
            visit(int(child), world, group_name)

    ident=[1.0,0,0,0, 0,1.0,0,0, 0,0,1.0,0, 0,0,0,1.0]
    group_name=path.stem
    for root in roots:
        visit(int(root),ident,group_name)
    if not result:
        raise ValueError("GLB/glTF içinde çizilebilir nesne bulunamadı.")
    return result

def load_gltf(path: str | Path) -> MeshData:
    path = Path(path).resolve()
    doc, embedded, base_dir = _load_container(path)
    buffers = _buffers(doc, embedded, base_dir)
    nodes = doc.get("nodes", [])
    meshes = doc.get("meshes", [])
    scenes = doc.get("scenes", [])
    scene_idx = int(doc.get("scene", 0)) if scenes else -1
    roots = scenes[scene_idx].get("nodes", []) if scene_idx >= 0 else list(range(len(nodes)))

    output: list[float] = []
    all_min = [float("inf")] * 3
    all_max = [float("-inf")] * 3
    prim_count = 0

    def visit(node_index: int, parent: list[float]):
        nonlocal prim_count
        node = nodes[node_index]
        world = _mat_mul(parent, _node_matrix(node))
        mesh_index = node.get("mesh")
        if mesh_index is not None:
            mesh = meshes[int(mesh_index)]
            for primitive in mesh.get("primitives", []):
                if int(primitive.get("mode", 4)) != 4:
                    continue
                attrs = primitive.get("attributes", {})
                if "POSITION" not in attrs:
                    continue
                pos = _read_accessor(doc, buffers, int(attrs["POSITION"]))
                nor = _read_accessor(doc, buffers, int(attrs["NORMAL"])) if "NORMAL" in attrs else None
                indices = _read_accessor(doc, buffers, int(primitive["indices"])) if "indices" in primitive else [(float(i),) for i in range(len(pos))]
                idx = [int(v[0]) for v in indices]
                if len(idx) % 3:
                    idx = idx[:len(idx) - len(idx) % 3]
                if nor is None:
                    nor = [(0.0, 0.0, 0.0)] * len(pos)
                    accum = [[0.0, 0.0, 0.0] for _ in pos]
                    for t in range(0, len(idx), 3):
                        a, b, c = pos[idx[t]], pos[idx[t+1]], pos[idx[t+2]]
                        ab = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
                        ac = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
                        fn = (ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0])
                        for vi in (idx[t], idx[t+1], idx[t+2]):
                            accum[vi][0] += fn[0]; accum[vi][1] += fn[1]; accum[vi][2] += fn[2]
                    nor = []
                    for n in accum:
                        ln = math.sqrt(n[0]*n[0] + n[1]*n[1] + n[2]*n[2]) or 1.0
                        nor.append((n[0]/ln, n[1]/ln, n[2]/ln))
                for vi in idx:
                    p = _transform_point(world, tuple(map(float, pos[vi][:3])))
                    n = _transform_normal(world, tuple(map(float, nor[vi][:3])))
                    output.extend((p[0], p[1], p[2], n[0], n[1], n[2]))
                    for j in range(3):
                        all_min[j] = min(all_min[j], p[j])
                        all_max[j] = max(all_max[j], p[j])
                prim_count += 1
        for child in node.get("children", []):
            visit(int(child), world)

    ident = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]
    for root in roots:
        visit(int(root), ident)

    if not output:
        raise ValueError("GLB/glTF içinde çizilebilir üçgen bulunamadı.")
    half = tuple(max(0.001, (all_max[i] - all_min[i]) * 0.5) for i in range(3))
    return MeshData(output, half, prim_count)
