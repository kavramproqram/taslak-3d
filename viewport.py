from __future__ import annotations

import array
import ctypes
import math
from dataclasses import dataclass
from pathlib import Path

from PyQt5.QtCore import QPoint, Qt, pyqtSignal
from PyQt5.QtGui import QFont, QSurfaceFormat
from PyQt5.QtWidgets import QOpenGLWidget, QVBoxLayout, QLabel, QWidget
from OpenGL.GL import *
from OpenGL.raw.GL.VERSION.GL_2_0 import glVertexAttribPointer as raw_glVertexAttribPointer

from native_engine import NativeEngine
from scene_import import MeshData, load_gltf

ROOT = Path(__file__).resolve().parent
SHADERS = ROOT / "shaders"


@dataclass
class GPUMesh:
    vao: int
    vbo: int
    count: int


class GLView(QOpenGLWidget):
    object_selected = pyqtSignal()
    scene_changed = pyqtSignal()
    status = pyqtSignal(str)

    def __init__(self, engine: NativeEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(0, 0)
        self.last = QPoint()
        self.drag_mode = None
        self.transform_mode = None
        self.draw_mesh_id = 1
        self.draw_name = "Cube"
        self.draw_target = 0
        self.draw_last = None
        self.drag_started = False
        self.initialized = False
        self.meshes: dict[int, GPUMesh] = {}
        self.mesh_bounds: dict[int, tuple[float, float, float]] = {}
        self.next_imported_mesh_id = 1000
        self.cube_program = 0
        self.ground_program = 0
        self.ground_vao = 0
        self.ground_vbo = 0
        self._u = {}

    def read_shader(self, name):
        path = SHADERS / name
        return path.read_text(encoding="utf-8")

    def compile_shader(self, source, shader_type):
        sid = glCreateShader(shader_type)
        glShaderSource(sid, source)
        glCompileShader(sid)
        if glGetShaderiv(sid, GL_COMPILE_STATUS) != GL_TRUE:
            log = glGetShaderInfoLog(sid)
            if isinstance(log, bytes): log = log.decode("utf-8", "replace")
            glDeleteShader(sid)
            raise RuntimeError(log)
        return sid

    def create_program(self, vs_name, fs_name):
        p = glCreateProgram()
        vs = self.compile_shader(self.read_shader(vs_name), GL_VERTEX_SHADER)
        fs = self.compile_shader(self.read_shader(fs_name), GL_FRAGMENT_SHADER)
        glAttachShader(p, vs); glAttachShader(p, fs); glLinkProgram(p)
        glDeleteShader(vs); glDeleteShader(fs)
        if glGetProgramiv(p, GL_LINK_STATUS) != GL_TRUE:
            log = glGetProgramInfoLog(p)
            if isinstance(log, bytes): log = log.decode("utf-8", "replace")
            glDeleteProgram(p)
            raise RuntimeError(log)
        return p

    @staticmethod
    def _cube_data():
        cube = [
            (-.5,-.5,.5,0,0,1),(.5,-.5,.5,0,0,1),(.5,.5,.5,0,0,1),(-.5,-.5,.5,0,0,1),(.5,.5,.5,0,0,1),(-.5,.5,.5,0,0,1),
            (.5,-.5,-.5,0,0,-1),(-.5,-.5,-.5,0,0,-1),(-.5,.5,-.5,0,0,-1),(.5,-.5,-.5,0,0,-1),(-.5,.5,-.5,0,0,-1),(.5,.5,-.5,0,0,-1),
            (-.5,.5,.5,0,1,0),(.5,.5,.5,0,1,0),(.5,.5,-.5,0,1,0),(-.5,.5,.5,0,1,0),(.5,.5,-.5,0,1,0),(-.5,.5,-.5,0,1,0),
            (-.5,-.5,-.5,0,-1,0),(.5,-.5,-.5,0,-1,0),(.5,-.5,.5,0,-1,0),(-.5,-.5,-.5,0,-1,0),(.5,-.5,.5,0,-1,0),(-.5,-.5,.5,0,-1,0),
            (.5,-.5,.5,1,0,0),(.5,-.5,-.5,1,0,0),(.5,.5,-.5,1,0,0),(.5,-.5,.5,1,0,0),(.5,.5,-.5,1,0,0),(.5,.5,.5,1,0,0),
            (-.5,-.5,-.5,-1,0,0),(-.5,-.5,.5,-1,0,0),(-.5,.5,.5,-1,0,0),(-.5,-.5,-.5,-1,0,0),(-.5,.5,.5,-1,0,0),(-.5,.5,-.5,-1,0,0),
        ]
        return array.array("f", [v for item in cube for v in item])

    @staticmethod
    def _sphere_data(segments=24, rings=12):
        data = []
        for r in range(rings):
            phi0 = math.pi * r / rings
            phi1 = math.pi * (r + 1) / rings
            for s in range(segments):
                t0 = 2 * math.pi * s / segments
                t1 = 2 * math.pi * (s + 1) / segments
                pts = []
                for phi, th in ((phi0,t0),(phi0,t1),(phi1,t1),(phi1,t0)):
                    x = math.sin(phi)*math.cos(th); y = math.sin(phi)*math.sin(th); z = math.cos(phi)
                    pts.append((x*.5,y*.5,z*.5,x,y,z))
                data.extend((pts[0],pts[1],pts[2],pts[0],pts[2],pts[3]))
        return array.array("f", [v for tri in data for v in tri])

    @staticmethod
    def _cylinder_data(segments=24, cone=False):
        data=[]
        for s in range(segments):
            a0=2*math.pi*s/segments; a1=2*math.pi*(s+1)/segments
            r0=.5; r1=.0 if cone else .5
            p0=(r0*math.cos(a0),r0*math.sin(a0),-.5); p1=(r0*math.cos(a1),r0*math.sin(a1),-.5)
            q0=(r1*math.cos(a0),r1*math.sin(a0),.5); q1=(r1*math.cos(a1),r1*math.sin(a1),.5)
            if cone:
                n0=(math.cos(a0),math.sin(a0),0.65); n1=(math.cos(a1),math.sin(a1),0.65)
            else:
                n0=(math.cos(a0),math.sin(a0),0); n1=(math.cos(a1),math.sin(a1),0)
            data += [(p0[0],p0[1],p0[2],*n0),(p1[0],p1[1],p1[2],*n1),(q1[0],q1[1],q1[2],*n1),
                     (p0[0],p0[1],p0[2],*n0),(q1[0],q1[1],q1[2],*n1),(q0[0],q0[1],q0[2],*n0)]
            if not cone:
                data += [(.0,.0,-.5,0,0,-1),(p1[0],p1[1],-.5,0,0,-1),(p0[0],p0[1],-.5,0,0,-1),
                         (.0,.0,.5,0,0,1),(q0[0],q0[1],.5,0,0,1),(q1[0],q1[1],.5,0,0,1)]
        return array.array("f", [v for item in data for v in item])

    @staticmethod
    def _plane_data():
        return array.array("f", [-.5,-.5,0,0,0,1,.5,-.5,0,0,0,1,.5,.5,0,0,0,1,-.5,-.5,0,0,0,1,.5,.5,0,0,0,1,-.5,.5,0,0,0,1])

    def _upload_mesh(self, mesh_id, data):
        vao = glGenVertexArrays(1); vbo = glGenBuffers(1)
        glBindVertexArray(vao); glBindBuffer(GL_ARRAY_BUFFER, vbo)
        glBufferData(GL_ARRAY_BUFFER, data.tobytes(), GL_STATIC_DRAW)
        glEnableVertexAttribArray(0); raw_glVertexAttribPointer(0,3,GL_FLOAT,GL_FALSE,24,ctypes.c_void_p(0))
        glEnableVertexAttribArray(1); raw_glVertexAttribPointer(1,3,GL_FLOAT,GL_FALSE,24,ctypes.c_void_p(12))
        glBindVertexArray(0)
        self.meshes[mesh_id] = GPUMesh(vao, vbo, len(data)//6)

    def initializeGL(self):
        if self.context() is None or not self.context().isValid(): raise RuntimeError("OpenGL context geçersiz.")
        self.makeCurrent()
        try:
            glEnable(GL_DEPTH_TEST); glEnable(GL_CULL_FACE); glCullFace(GL_BACK)
            glClearColor(.012,.012,.014,1)
            self.cube_program = self.create_program("cube.vert","cube.frag")
            self.ground_program = self.create_program("ground.vert","ground.frag")
            self._upload_mesh(1, self._cube_data()); self._upload_mesh(2, self._sphere_data());
            self._upload_mesh(3, self._cylinder_data()); self._upload_mesh(4, self._cylinder_data(cone=True)); self._upload_mesh(5, self._plane_data())
            self.mesh_bounds.update({1:(.5,.5,.5),2:(.5,.5,.5),3:(.5,.5,.5),4:(.5,.5,.5),5:(.5,.5,.02)})
            gdata = array.array("f",[-1,-1,1,-1,1,1,-1,-1,1,1,-1,1])
            self.ground_vao=glGenVertexArrays(1); self.ground_vbo=glGenBuffers(1)
            glBindVertexArray(self.ground_vao); glBindBuffer(GL_ARRAY_BUFFER,self.ground_vbo); glBufferData(GL_ARRAY_BUFFER,gdata.tobytes(),GL_STATIC_DRAW)
            glEnableVertexAttribArray(0); raw_glVertexAttribPointer(0,2,GL_FLOAT,GL_FALSE,8,ctypes.c_void_p(0)); glBindVertexArray(0)
            self._u = {name: glGetUniformLocation(self.cube_program,name) for name in ("uVP","uModel","uCameraPos","uColor","uSelected")}
            self._gu = {name: glGetUniformLocation(self.ground_program,name) for name in ("uVP","uCenter","uSize")}
            self.initialized=True
        finally:
            self.doneCurrent()

    def resizeGL(self,w,h):
        if not self.initialized: return
        self.engine.lib.kavram3d_set_viewport(self.engine.h,max(1,w),max(1,h))
        glViewport(0,0,max(1,w),max(1,h))

    def paintGL(self):
        if not self.initialized: return
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        vp=self.engine.lib.kavram3d_get_view_projection
        vp_data=(ctypes.c_float*16)(); self.engine.lib.kavram3d_get_view_projection(self.engine.h,vp_data)
        cam=(ctypes.c_float*3)(); self.engine.lib.kavram3d_get_camera_position(self.engine.h,cam)
        if self.engine.lib.kavram3d_ground_visible(self.engine.h):
            glUseProgram(self.ground_program); glUniformMatrix4fv(self._gu["uVP"],1,GL_FALSE,vp_data); glUniform2f(self._gu["uCenter"],cam[0],cam[1]); glUniform1f(self._gu["uSize"],10000.0)
            glBindVertexArray(self.ground_vao); glDisable(GL_CULL_FACE); glDrawArrays(GL_TRIANGLES,0,6); glEnable(GL_CULL_FACE)
        items=self.engine.render_items(); items.sort(key=lambda x:x.mesh_id)
        glUseProgram(self.cube_program); glUniformMatrix4fv(self._u["uVP"],1,GL_FALSE,vp_data); glUniform3f(self._u["uCameraPos"],cam[0],cam[1],cam[2])
        bound_mesh=None; has_selected=False
        for item in items:
            mesh=self.meshes.get(item.mesh_id)
            if mesh is None: continue
            if bound_mesh != item.mesh_id:
                glBindVertexArray(mesh.vao); bound_mesh=item.mesh_id
            glUniformMatrix4fv(self._u["uModel"],1,GL_FALSE,item.model)
            color=tuple(item.color[:3])
            glUniform3f(self._u["uColor"],*color); glUniform1i(self._u["uSelected"],1 if item.selected else 0)
            glDrawArrays(GL_TRIANGLES,0,mesh.count)
            if item.selected:
                has_selected=True
                glPolygonMode(GL_FRONT_AND_BACK,GL_LINE)
                hi=(min(1.0,color[0]+.22),min(1.0,color[1]+.18),min(1.0,color[2]+.05))
                glUniform3f(self._u["uColor"],*hi); glUniform1i(self._u["uSelected"],1); glDrawArrays(GL_TRIANGLES,0,mesh.count)
                glPolygonMode(GL_FRONT_AND_BACK,GL_FILL)
        glBindVertexArray(0)

    def register_imported_mesh(self, path: str, preferred_id: int | None = None):
        data: MeshData = load_gltf(path)
        mesh_id = preferred_id if preferred_id is not None else self.next_imported_mesh_id
        while mesh_id in self.meshes: mesh_id += 1
        self.next_imported_mesh_id = max(self.next_imported_mesh_id, mesh_id + 1)
        if not self.initialized:
            raise RuntimeError("GL context hazır değil; mesh daha sonra yüklenebilir.")
        self.makeCurrent()
        try:
            self._upload_mesh(mesh_id, array.array("f", data.vertices))
            self.mesh_bounds[mesh_id] = data.half_extents
            hb=(ctypes.c_float*3)(*data.half_extents); self.engine.lib.kavram3d_set_mesh_bounds(self.engine.h,mesh_id,hb)
        finally:
            self.doneCurrent()
        return mesh_id, data.half_extents

    def set_draw_tool(self, mesh_id, name):
        self.draw_mesh_id = int(mesh_id); self.draw_name = str(name)
        self.status.emit(f"Çizim türü: {self.draw_name}")

    def _ground_point(self, p):
        out=(ctypes.c_float*3)()
        ok=self.engine.lib.kavram3d_screen_to_ground(self.engine.h,float(p.x()),float(p.y()),out)
        return (float(out[0]),float(out[1]),float(out[2])) if ok else None

    def mousePressEvent(self, event):
        self.setFocus(Qt.MouseFocusReason)
        self.last = event.pos()
        self.drag_started = False
        mods = event.modifiers()

        if event.button() == Qt.MiddleButton:
            if mods & Qt.ControlModifier:
                self.drag_mode = "zoom"
            elif mods & Qt.ShiftModifier:
                self.drag_mode = "pan"
            else:
                self.drag_mode = "rotate"
            return

        if event.button() != Qt.LeftButton:
            return

        hit = self.engine.lib.kavram3d_pick(
            self.engine.h, float(event.x()), float(event.y()))

        if mods & Qt.ControlModifier:
            # Ctrl + Sol tık = sil
            if hit:
                self.engine.lib.kavram3d_delete_object(self.engine.h, hit)
                self.object_selected.emit()
                self.scene_changed.emit()
                self.update()
            return

        # Düz sol tık = kopya üret
        if hit:
            selected = self.engine.selected_ids()
            if selected:
                src_info = self.engine.info(selected[0])
                src_state = self.engine.state(selected[0])
                nid = self.engine.lib.kavram3d_add_object_at_surface(
                    self.engine.h, src_info["mesh_id"],
                    float(event.x()), float(event.y()),
                    src_info["name"].encode(), hit)
                if nid:
                    self.engine.set_state(nid, src_state)
                    rgba = (ctypes.c_float * 4)(
                        src_info["color"][0], src_info["color"][1],
                        src_info["color"][2], 1.0)
                    self.engine.lib.kavram3d_set_object_color(self.engine.h, nid, rgba)
                    self.engine.lib.kavram3d_set_object_motion(
                        self.engine.h, nid,
                        1 if src_info["motion_enabled"] else 0,
                        src_info["motion_speed"],
                        src_info["motion_mode"],
                        src_info["motion_axis"])
                    self.engine.lib.kavram3d_select(self.engine.h, nid)
            else:
                self.engine.lib.kavram3d_add_object_at_surface(
                    self.engine.h, self.draw_mesh_id,
                    float(event.x()), float(event.y()),
                    self.draw_name.encode(), hit)
            self.object_selected.emit()
            self.scene_changed.emit()
            self.update()
        else:
            if not (mods & Qt.ShiftModifier):
                self.engine.lib.kavram3d_select(self.engine.h, 0)
            self.object_selected.emit()
            self.scene_changed.emit()
            self.update()

    def mouseMoveEvent(self,event):
        d=event.pos()-self.last; self.last=event.pos(); dx=float(d.x()); dy=float(d.y())
        if self.drag_mode=="rotate": self.engine.lib.kavram3d_rotate_view(self.engine.h,dx,dy); self.update(); return
        if self.drag_mode=="pan": self.engine.lib.kavram3d_pan_view(self.engine.h,dx,dy); self.update(); return
        if self.drag_mode=="zoom": self.engine.lib.kavram3d_zoom_view(self.engine.h,-dy*.08); self.update(); return
        if self.drag_mode=="transform" and self.transform_mode:
            fn={"G":"kavram3d_move_selected_drag","R":"kavram3d_rotate_selected_drag","S":"kavram3d_scale_selected_drag"}[self.transform_mode]
            getattr(self.engine.lib,fn)(self.engine.h,dx,dy); self.scene_changed.emit(); self.update(); return
        if self.drag_mode in ("add-stamp","duplicate-stamp"):
            if self.draw_last is None or (event.pos()-self.draw_last).manhattanLength()>=28:
                if self.drag_mode=="add-stamp":
                    oid=self.engine.lib.kavram3d_add_object_at_surface(self.engine.h,self.draw_mesh_id,float(event.x()),float(event.y()),self.draw_name.encode(),self.draw_target)
                else:
                    oid=self.engine.lib.kavram3d_duplicate_selected_at_surface(self.engine.h,float(event.x()),float(event.y()),self.draw_target)
                if oid: self.draw_last=event.pos(); self.scene_changed.emit()
            self.update(); return
        if self.drag_mode=="delete-stamp":
            hit=self.engine.lib.kavram3d_pick(self.engine.h,float(event.x()),float(event.y()))
            if hit: self.engine.lib.kavram3d_delete_object(self.engine.h,hit); self.scene_changed.emit()
            self.update()

    def mouseReleaseEvent(self,event):
        if event.button() in (Qt.LeftButton,Qt.MiddleButton):
            if self.drag_mode=="transform": self.transform_mode=None
            self.drag_mode=None; self.draw_last=None; self.draw_target=0

    def wheelEvent(self,event):
        self.engine.lib.kavram3d_zoom_view(self.engine.h,float(event.angleDelta().y())/120.0); self.update()

    def set_transform_mode(self, mode):
        if mode not in ("G","R","S") or self.engine.lib.kavram3d_selected_count(self.engine.h)<=0:
            self.transform_mode=None; self.drag_mode=None
            return
        self.transform_mode=mode; self.drag_mode="transform"
        self.status.emit({"G":"Taşıma","R":"Döndürme","S":"Ölçek"}[mode])

    def cancel_transform(self): self.transform_mode=None; self.drag_mode=None


def configure_opengl():
    fmt=QSurfaceFormat(); fmt.setRenderableType(QSurfaceFormat.OpenGL); fmt.setProfile(QSurfaceFormat.CoreProfile); fmt.setVersion(3,3); fmt.setDepthBufferSize(24); fmt.setStencilBufferSize(8); fmt.setSwapInterval(1); QSurfaceFormat.setDefaultFormat(fmt)
