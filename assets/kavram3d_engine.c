#define _GNU_SOURCE
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <math.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

#define KV_INITIAL_OBJECT_CAPACITY 256
#define KV_MAX_MESH_BOUNDS 1024
#define KV_DEFAULT_HALF    0.5f

typedef struct {
    int   id;
    int   mesh_id;
    int   selected;
    char  name[128];
    float position[3];
    float rotation[3];
    float scale[3];
    float color[4];
    int   motion_enabled;
    float motion_speed;
    int   motion_mode;
    int   motion_axis;
    float motion_time;
    int   duplicate;
    int   group_id;
} KVObject;

typedef struct {
    float yaw, pitch, distance;
    float target[3];
    int   orthographic;
} KVCamera;

typedef struct {
    KVObject *objects;
    int      object_count;
    int      object_capacity;
    int      next_id;
    int      next_group_id;
    KVCamera camera;
    int      viewport_w, viewport_h;
    int      ground_visible;
    float    mesh_bounds[KV_MAX_MESH_BOUNDS][3];
    int      mesh_bounds_set[KV_MAX_MESH_BOUNDS];
} KVEngine;

typedef struct {
    int   id;
    int   mesh_id;
    int   selected;
    float model[16];
    float color[4];
} KVRenderItem;

static void mat4_identity(float m[16]) {
    memset(m, 0, 16 * sizeof(float));
    m[0] = m[5] = m[10] = m[15] = 1.0f;
}

static void mat4_mul(float out[16], const float a[16], const float b[16]) {
    float t[16];
    for (int c = 0; c < 4; ++c)
        for (int r = 0; r < 4; ++r)
            t[c*4+r] = a[r]*b[c*4+0] + a[4+r]*b[c*4+1] + a[8+r]*b[c*4+2] + a[12+r]*b[c*4+3];
    memcpy(out, t, sizeof(t));
}

static void mat4_translate(float m[16], float x, float y, float z) {
    mat4_identity(m); m[12]=x; m[13]=y; m[14]=z;
}
static void mat4_scale_m(float m[16], float x, float y, float z) {
    memset(m,0,16*sizeof(float)); m[0]=x; m[5]=y; m[10]=z; m[15]=1.0f;
}
static void mat4_rot_x(float m[16], float a){float c=cosf(a),s=sinf(a);mat4_identity(m);m[5]=c;m[6]=s;m[9]=-s;m[10]=c;}
static void mat4_rot_y(float m[16], float a){float c=cosf(a),s=sinf(a);mat4_identity(m);m[0]=c;m[2]=-s;m[8]=s;m[10]=c;}
static void mat4_rot_z(float m[16], float a){float c=cosf(a),s=sinf(a);mat4_identity(m);m[0]=c;m[1]=s;m[4]=-s;m[5]=c;}

static void mat4_look_at(float m[16], const float eye[3], const float tgt[3], const float up[3]) {
    float f[3] = { tgt[0]-eye[0], tgt[1]-eye[1], tgt[2]-eye[2] };
    float s[3], u[3];
    float flen = sqrtf(f[0]*f[0]+f[1]*f[1]+f[2]*f[2]);
    if (flen < 1e-8f) flen = 1.0f;
    f[0]/=flen; f[1]/=flen; f[2]/=flen;
    s[0]=f[1]*up[2]-f[2]*up[1]; s[1]=f[2]*up[0]-f[0]*up[2]; s[2]=f[0]*up[1]-f[1]*up[0];
    float slen=sqrtf(s[0]*s[0]+s[1]*s[1]+s[2]*s[2]);
    if (slen<1e-8f){s[0]=1;s[1]=0;s[2]=0;} else {s[0]/=slen;s[1]/=slen;s[2]/=slen;}
    u[0]=s[1]*f[2]-s[2]*f[1]; u[1]=s[2]*f[0]-s[0]*f[2]; u[2]=s[0]*f[1]-s[1]*f[0];
    m[0]=s[0];m[4]=s[1];m[8]=s[2];  m[12]=-(s[0]*eye[0]+s[1]*eye[1]+s[2]*eye[2]);
    m[1]=u[0];m[5]=u[1];m[9]=u[2];  m[13]=-(u[0]*eye[0]+u[1]*eye[1]+u[2]*eye[2]);
    m[2]=-f[0];m[6]=-f[1];m[10]=-f[2];m[14]=(f[0]*eye[0]+f[1]*eye[1]+f[2]*eye[2]);
    m[3]=0;m[7]=0;m[11]=0;m[15]=1;
}

static void mat4_perspective(float m[16], float fovy, float aspect, float near, float far) {
    float f = 1.0f / tanf(fovy * 0.5f);
    memset(m,0,16*sizeof(float));
    m[0]=f/aspect; m[5]=f;
    m[10]=(far+near)/(near-far); m[11]=-1.0f;
    m[14]=(2.0f*far*near)/(near-far);
}

static void mat4_ortho(float m[16], float l, float r, float b, float t, float n, float f) {
    memset(m,0,16*sizeof(float));
    m[0]=2.0f/(r-l); m[5]=2.0f/(t-b); m[10]=-2.0f/(f-n);
    m[12]=-(r+l)/(r-l); m[13]=-(t+b)/(t-b); m[14]=-(f+n)/(f-n); m[15]=1.0f;
}

static void mat4_xform_point(const float m[16], const float p[3], float out[3]) {
    out[0]=m[0]*p[0]+m[4]*p[1]+m[8]*p[2]+m[12];
    out[1]=m[1]*p[0]+m[5]*p[1]+m[9]*p[2]+m[13];
    out[2]=m[2]*p[0]+m[6]*p[1]+m[10]*p[2]+m[14];
}

static void mat4_invert(const float m[16], float out[16]) {
    float inv[16];
    inv[0]=m[5]*m[10]*m[15]-m[5]*m[11]*m[14]-m[9]*m[6]*m[15]+m[9]*m[7]*m[14]+m[13]*m[6]*m[11]-m[13]*m[7]*m[10];
    inv[4]=-m[4]*m[10]*m[15]+m[4]*m[11]*m[14]+m[8]*m[6]*m[15]-m[8]*m[7]*m[14]-m[12]*m[6]*m[11]+m[12]*m[7]*m[10];
    inv[8]=m[4]*m[9]*m[15]-m[4]*m[11]*m[13]-m[8]*m[5]*m[15]+m[8]*m[7]*m[13]+m[12]*m[5]*m[11]-m[12]*m[7]*m[9];
    inv[12]=-m[4]*m[9]*m[14]+m[4]*m[10]*m[13]+m[8]*m[5]*m[14]-m[8]*m[6]*m[13]-m[12]*m[5]*m[10]+m[12]*m[6]*m[9];
    inv[1]=-m[1]*m[10]*m[15]+m[1]*m[11]*m[14]+m[9]*m[2]*m[15]-m[9]*m[3]*m[14]-m[13]*m[2]*m[11]+m[13]*m[3]*m[10];
    inv[5]=m[0]*m[10]*m[15]-m[0]*m[11]*m[14]-m[8]*m[2]*m[15]+m[8]*m[3]*m[14]+m[12]*m[2]*m[11]-m[12]*m[3]*m[10];
    inv[9]=-m[0]*m[9]*m[15]+m[0]*m[11]*m[13]+m[8]*m[1]*m[15]-m[8]*m[3]*m[13]-m[12]*m[1]*m[11]+m[12]*m[3]*m[9];
    inv[13]=m[0]*m[9]*m[14]-m[0]*m[10]*m[13]-m[8]*m[1]*m[14]+m[8]*m[2]*m[13]+m[12]*m[1]*m[10]-m[12]*m[2]*m[9];
    inv[2]=m[1]*m[6]*m[15]-m[1]*m[7]*m[14]-m[5]*m[2]*m[15]+m[5]*m[3]*m[14]+m[13]*m[2]*m[7]-m[13]*m[3]*m[6];
    inv[6]=-m[0]*m[6]*m[15]+m[0]*m[7]*m[14]+m[4]*m[2]*m[15]-m[4]*m[3]*m[14]-m[12]*m[2]*m[7]+m[12]*m[3]*m[6];
    inv[10]=m[0]*m[5]*m[15]-m[0]*m[7]*m[13]-m[4]*m[1]*m[15]+m[4]*m[3]*m[13]+m[12]*m[1]*m[7]-m[12]*m[3]*m[5];
    inv[14]=-m[0]*m[5]*m[14]+m[0]*m[6]*m[13]+m[4]*m[1]*m[14]-m[4]*m[2]*m[13]-m[12]*m[1]*m[6]+m[12]*m[2]*m[5];
    inv[3]=-m[1]*m[6]*m[11]+m[1]*m[7]*m[10]+m[5]*m[2]*m[11]-m[5]*m[3]*m[10]-m[9]*m[2]*m[7]+m[9]*m[3]*m[6];
    inv[7]=m[0]*m[6]*m[11]-m[0]*m[7]*m[10]-m[4]*m[2]*m[11]+m[4]*m[3]*m[10]+m[8]*m[2]*m[7]-m[8]*m[3]*m[6];
    inv[11]=-m[0]*m[5]*m[11]+m[0]*m[7]*m[9]+m[4]*m[1]*m[11]-m[4]*m[3]*m[9]-m[8]*m[1]*m[7]+m[8]*m[3]*m[5];
    inv[15]=m[0]*m[5]*m[10]-m[0]*m[6]*m[9]-m[4]*m[1]*m[10]+m[4]*m[2]*m[9]+m[8]*m[1]*m[6]-m[8]*m[2]*m[5];
    float det=m[0]*inv[0]+m[1]*inv[4]+m[2]*inv[8]+m[3]*inv[12];
    if (fabsf(det)<1e-12f){mat4_identity(out);return;}
    float id=1.0f/det;
    for (int i=0;i<16;++i) out[i]=inv[i]*id;
}

static int kv_ensure_capacity(KVEngine *e, int needed) {
    if (!e || needed < 0) return 0;
    if (needed <= e->object_capacity) return 1;
    int cap = e->object_capacity > 0 ? e->object_capacity : KV_INITIAL_OBJECT_CAPACITY;
    while (cap < needed) {
        if (cap > 1073741824) return 0;
        cap *= 2;
    }
    KVObject *next = (KVObject*)realloc(e->objects, (size_t)cap * sizeof(KVObject));
    if (!next) return 0;
    e->objects = next;
    e->object_capacity = cap;
    return 1;
}

static KVObject *kv_find(KVEngine *e, int id) {
    if (!e) return NULL;
    for (int i=0;i<e->object_count;++i) if (e->objects[i].id==id) return &e->objects[i];
    return NULL;
}
static int kv_index(KVEngine *e, int id) {
    if (!e) return -1;
    for (int i=0;i<e->object_count;++i) if (e->objects[i].id==id) return i;
    return -1;
}

static void kv_camera_position(const KVCamera *cam, float out[3]) {
    float cp=cosf(cam->pitch), sp=sinf(cam->pitch);
    float cy=cosf(cam->yaw),   sy=sinf(cam->yaw);
    out[0]=cam->target[0]+cam->distance*cp*cy;
    out[1]=cam->target[1]+cam->distance*cp*sy;
    out[2]=cam->target[2]+cam->distance*sp;
}

static void kv_view_projection(KVEngine *e, float vp[16]) {
    float eye[3], up[3]={0,0,1};
    kv_camera_position(&e->camera, eye);
    float dir[3]={e->camera.target[0]-eye[0],e->camera.target[1]-eye[1],e->camera.target[2]-eye[2]};
    float dl=sqrtf(dir[0]*dir[0]+dir[1]*dir[1]+dir[2]*dir[2]);
    if (dl>1e-6f){dir[0]/=dl;dir[1]/=dl;dir[2]/=dl;}
    if (fabsf(dir[2])>0.99f){up[0]=1;up[1]=0;up[2]=0;}
    float view[16], proj[16];
    mat4_look_at(view, eye, e->camera.target, up);
    float aspect=(e->viewport_h>0)?(float)e->viewport_w/(float)e->viewport_h:1.0f;
    if (aspect<=0.0f) aspect=1.0f;
    if (e->camera.orthographic) {
        float hh=e->camera.distance*0.5f, hw=hh*aspect;
        mat4_ortho(proj,-hw,hw,-hh,hh,0.01f,e->camera.distance*20.0f+1000.0f);
    } else {
        mat4_perspective(proj,45.0f*(float)M_PI/180.0f,aspect,0.05f,10000.0f);
    }
    mat4_mul(vp, proj, view);
}

static void kv_object_model(const KVObject *o, float out[16]) {
    float t[16],rx[16],ry[16],rz[16],sc[16],tmp[16];
    mat4_translate(t,o->position[0],o->position[1],o->position[2]);
    mat4_rot_z(rz,o->rotation[2]);
    mat4_rot_y(ry,o->rotation[1]);
    mat4_rot_x(rx,o->rotation[0]);
    mat4_scale_m(sc,o->scale[0],o->scale[1],o->scale[2]);
    mat4_mul(tmp,rz,ry); mat4_mul(tmp,tmp,rx); mat4_mul(tmp,tmp,sc);
    mat4_mul(out,t,tmp);
}

static void kv_object_model_animated(const KVObject *o, float motion_time, float out[16]) {
    KVObject tmp=*o;
    if (o->motion_enabled && o->motion_mode!=0) {
        float t=motion_time*o->motion_speed;
        int ax=o->motion_axis; if (ax<0||ax>2) ax=2;
        if (o->motion_mode==1) tmp.rotation[ax]+=t;
        else if (o->motion_mode==2) tmp.position[ax]+=sinf(t)*0.75f;
        else if (o->motion_mode==3) {
            float p=1.0f+0.15f*sinf(t);
            tmp.scale[0]*=p; tmp.scale[1]*=p; tmp.scale[2]*=p;
        }
    }
    kv_object_model(&tmp,out);
}

static void kv_mesh_half(KVEngine *e, int mesh_id, float out[3]) {
    if (mesh_id>=0 && mesh_id<KV_MAX_MESH_BOUNDS && e->mesh_bounds_set[mesh_id]) {
        out[0]=e->mesh_bounds[mesh_id][0];
        out[1]=e->mesh_bounds[mesh_id][1];
        out[2]=e->mesh_bounds[mesh_id][2];
    } else { out[0]=out[1]=out[2]=KV_DEFAULT_HALF; }
}

static float kv_obj_radius(KVEngine *e, const KVObject *o) {
    float h[3]; kv_mesh_half(e,o->mesh_id,h);
    float r=sqrtf(h[0]*h[0]+h[1]*h[1]+h[2]*h[2]);
    float sm=fabsf(o->scale[0]);
    if (fabsf(o->scale[1])>sm) sm=fabsf(o->scale[1]);
    if (fabsf(o->scale[2])>sm) sm=fabsf(o->scale[2]);
    if (sm<1e-6f) sm=1.0f;
    return r*sm;
}

static float kv_ray_sphere(const float ro[3],const float rd[3],const float c[3],float r) {
    float oc[3]={ro[0]-c[0],ro[1]-c[1],ro[2]-c[2]};
    float b=oc[0]*rd[0]+oc[1]*rd[1]+oc[2]*rd[2];
    float cc=oc[0]*oc[0]+oc[1]*oc[1]+oc[2]*oc[2]-r*r;
    float disc=b*b-cc;
    if (disc<0.0f) return -1.0f;
    float sq=sqrtf(disc);
    float t0=-b-sq, t1=-b+sq;
    if (t0>0.0f) return t0;
    if (t1>0.0f) return t1;
    return -1.0f;
}

static void kv_pick_ray(KVEngine *e, float sx, float sy, float ro[3], float rd[3]) {
    float vp[16],inv[16];
    kv_view_projection(e,vp);
    mat4_invert(vp,inv);
    float w=(float)e->viewport_w, h=(float)e->viewport_h;
    if (w<=0.0f) w=1.0f; if (h<=0.0f) h=1.0f;
    float ndc_x=(2.0f*sx/w)-1.0f, ndc_y=1.0f-(2.0f*sy/h);
    float pn[3]={ndc_x,ndc_y,-1.0f}, pf[3]={ndc_x,ndc_y,1.0f};
    float wn[3],wf[3];
    mat4_xform_point(inv,pn,wn);
    mat4_xform_point(inv,pf,wf);
    ro[0]=wn[0]; ro[1]=wn[1]; ro[2]=wn[2];
    rd[0]=wf[0]-wn[0]; rd[1]=wf[1]-wn[1]; rd[2]=wf[2]-wn[2];
    float l=sqrtf(rd[0]*rd[0]+rd[1]*rd[1]+rd[2]*rd[2]);
    if (l<1e-8f) l=1.0f;
    rd[0]/=l; rd[1]/=l; rd[2]/=l;
}


static int kv_project_point(KVEngine *e, const float p[3], float *sx, float *sy) {
    if (!e || !p || !sx || !sy) return 0;
    float vp[16]; kv_view_projection(e, vp);
    float clip[4];
    clip[0] = vp[0]*p[0] + vp[4]*p[1] + vp[8]*p[2]  + vp[12];
    clip[1] = vp[1]*p[0] + vp[5]*p[1] + vp[9]*p[2]  + vp[13];
    clip[2] = vp[2]*p[0] + vp[6]*p[1] + vp[10]*p[2] + vp[14];
    clip[3] = vp[3]*p[0] + vp[7]*p[1] + vp[11]*p[2] + vp[15];
    if (fabsf(clip[3]) < 1e-8f) return 0;
    float nx = clip[0] / clip[3];
    float ny = clip[1] / clip[3];
    *sx = (nx + 1.0f) * 0.5f * (float)e->viewport_w;
    *sy = (1.0f - ny) * 0.5f * (float)e->viewport_h;
    return 1;
}

static int kv_id_in_list(const int *ids, int count, int id) {
    if (!ids || count <= 0) return 0;
    for (int i=0; i<count; ++i) if (ids[i] == id) return 1;
    return 0;
}

static float kv_object_bottom(KVEngine *e, const KVObject *o) {
    return o->position[2] - kv_obj_radius(e, o);
}

static int kv_candidate_collides(KVEngine *e,
                                 const int *source_ids, int source_count,
                                 int mesh_id, const float pos[3],
                                 const float rot[3], const float scale[3],
                                 float extra_gap) {
    (void)rot;
    KVObject tmp;
    memset(&tmp, 0, sizeof(tmp));
    tmp.mesh_id = mesh_id;
    tmp.position[0] = pos[0]; tmp.position[1] = pos[1]; tmp.position[2] = pos[2];
    tmp.scale[0] = scale[0]; tmp.scale[1] = scale[1]; tmp.scale[2] = scale[2];
    float r = kv_obj_radius(e, &tmp);
    float rr;
    for (int i=0; i<e->object_count; ++i) {
        KVObject *o=&e->objects[i];
        if (kv_id_in_list(source_ids, source_count, o->id)) continue;
        rr = r + kv_obj_radius(e, o) + extra_gap;
        float dx=pos[0]-o->position[0], dy=pos[1]-o->position[1], dz=pos[2]-o->position[2];
        if (dx*dx + dy*dy + dz*dz < rr*rr) return 1;
    }
    return 0;
}

static int kv_seed_default_cube(KVEngine *e) {
    if (!kv_ensure_capacity(e, 1)) return 0;
    KVObject *o=&e->objects[0];
    memset(o,0,sizeof(*o));
    o->id=e->next_id++;
    o->mesh_id=1;
    strcpy(o->name,"Cube");
    o->position[2]=0.5f;
    o->scale[0]=o->scale[1]=o->scale[2]=1.0f;
    o->color[0]=0.55f;o->color[1]=0.58f;o->color[2]=0.62f;o->color[3]=1.0f;
    o->selected=1;
    e->object_count=1;
    return 1;
}

void *kavram3d_create(void) {
    KVEngine *e=(KVEngine*)calloc(1,sizeof(KVEngine));
    if (!e) return NULL;
    e->object_capacity = 0;
    e->objects = NULL;
    e->next_id=1;
    e->next_group_id=1;
    e->camera.yaw=-60.0f*(float)M_PI/180.0f;
    e->camera.pitch=25.0f*(float)M_PI/180.0f;
    e->camera.distance=12.0f;
    e->viewport_w=1; e->viewport_h=1;
    e->ground_visible=1;
    kv_seed_default_cube(e);
    return e;
}
void kavram3d_destroy(void *h){
    KVEngine*e=(KVEngine*)h;
    if(!e)return;
    free(e->objects);
    free(e);
}
void kavram3d_reset(void *h){
    KVEngine*e=(KVEngine*)h;
    if(!e)return;
    e->object_count=0;
    e->next_id=1;
    e->next_group_id=1;
    kv_seed_default_cube(e);
}
void kavram3d_set_viewport(void *h,int w,int hh){KVEngine*e=(KVEngine*)h;if(!e)return;e->viewport_w=w>0?w:1;e->viewport_h=hh>0?hh:1;}
void kavram3d_get_view_projection(void *h,float *out){KVEngine*e=(KVEngine*)h;if(!e||!out)return;float vp[16];kv_view_projection(e,vp);memcpy(out,vp,sizeof(vp));}
void kavram3d_get_camera_position(void *h,float *out){KVEngine*e=(KVEngine*)h;if(!e||!out)return;float p[3];kv_camera_position(&e->camera,p);out[0]=p[0];out[1]=p[1];out[2]=p[2];}
int kavram3d_object_count(void *h){KVEngine*e=(KVEngine*)h;return e?e->object_count:0;}
int kavram3d_object_id_at(void *h,int i){KVEngine*e=(KVEngine*)h;if(!e||i<0||i>=e->object_count)return 0;return e->objects[i].id;}
int kavram3d_selected_id(void *h){KVEngine*e=(KVEngine*)h;if(!e)return 0;for(int i=0;i<e->object_count;++i)if(e->objects[i].selected)return e->objects[i].id;return 0;}
int kavram3d_selected_count(void *h){KVEngine*e=(KVEngine*)h;if(!e)return 0;int c=0;for(int i=0;i<e->object_count;++i)if(e->objects[i].selected)++c;return c;}
int kavram3d_selected_id_at(void *h,int index){KVEngine*e=(KVEngine*)h;if(!e||index<0)return 0;int c=0;for(int i=0;i<e->object_count;++i)if(e->objects[i].selected){if(c==index)return e->objects[i].id;++c;}return 0;}
void kavram3d_select(void *h,int id){KVEngine*e=(KVEngine*)h;if(!e)return;for(int i=0;i<e->object_count;++i)e->objects[i].selected=(e->objects[i].id==id)?1:0;}
void kavram3d_toggle_select(void *h,int id){KVEngine*e=(KVEngine*)h;if(!e)return;KVObject*o=kv_find(e,id);if(o)o->selected=!o->selected;}


void kavram3d_select_box(void *h, float x0, float y0, float x1, float y1, int additive) {
    KVEngine*e=(KVEngine*)h; if(!e) return;
    if (!additive) for (int i=0;i<e->object_count;++i) e->objects[i].selected=0;
    float l=fminf(x0,x1), r=fmaxf(x0,x1), t=fminf(y0,y1), b=fmaxf(y0,y1);
    for (int i=0;i<e->object_count;++i) {
        KVObject *o=&e->objects[i];
        float sx,sy;
        if (!kv_project_point(e,o->position,&sx,&sy)) continue;
        if (sx>=l && sx<=r && sy>=t && sy<=b) o->selected=1;
    }
}

int kavram3d_pick(void *h,float sx,float sy){
    KVEngine*e=(KVEngine*)h;if(!e)return 0;
    float ro[3],rd[3];kv_pick_ray(e,sx,sy,ro,rd);
    int best=0;float bt=1e30f;
    for(int i=0;i<e->object_count;++i){
        KVObject*o=&e->objects[i];
        float r=kv_obj_radius(e,o);
        float c[3]={o->position[0],o->position[1],o->position[2]};
        float t=kv_ray_sphere(ro,rd,c,r);
        if(t>0.0f&&t<bt){bt=t;best=o->id;}
    }
    return best;
}

int kavram3d_screen_to_ground(void *h,float sx,float sy,float *out){
    KVEngine*e=(KVEngine*)h;if(!e||!out)return 0;
    float ro[3],rd[3];kv_pick_ray(e,sx,sy,ro,rd);
    if(fabsf(rd[2])<1e-8f){out[0]=out[1]=out[2]=0;return 0;}
    float t=-ro[2]/rd[2];
    if(t<0){out[0]=out[1]=out[2]=0;return 0;}
    out[0]=ro[0]+rd[0]*t;out[1]=ro[1]+rd[1]*t;out[2]=0;
    return 1;
}

void kavram3d_rotate_view(void *h,float dx,float dy){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    e->camera.yaw-=dx*0.01f;e->camera.pitch+=dy*0.01f;
    float lim=(float)M_PI/2.0f-0.01f;
    if(e->camera.pitch>lim)e->camera.pitch=lim;
    if(e->camera.pitch<-lim)e->camera.pitch=-lim;
}
void kavram3d_pan_view(void *h,float dx,float dy){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    float cp=cosf(e->camera.pitch),sp=sinf(e->camera.pitch);
    float cy=cosf(e->camera.yaw),sy=sinf(e->camera.yaw);
    float right[3]={-sy,cy,0},up[3]={-sp*cy,-sp*sy,cp};
    float s=e->camera.distance*0.002f;
    e->camera.target[0]+=(-dx*right[0]+dy*up[0])*s;
    e->camera.target[1]+=(-dx*right[1]+dy*up[1])*s;
    e->camera.target[2]+=(-dx*right[2]+dy*up[2])*s;
}
void kavram3d_zoom_view(void *h,float delta){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    float f=1.0f-delta*0.1f;
    if(f<0.1f)f=0.1f;if(f>10.0f)f=10.0f;
    e->camera.distance*=f;
    if(e->camera.distance<0.1f)e->camera.distance=0.1f;
    if(e->camera.distance>5000.0f)e->camera.distance=5000.0f;
}
void kavram3d_focus_selected(void *h){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    int id=kavram3d_selected_id(h);if(!id)return;
    KVObject*o=kv_find(e,id);if(!o)return;
    e->camera.target[0]=o->position[0];
    e->camera.target[1]=o->position[1];
    e->camera.target[2]=o->position[2];
    float r=kv_obj_radius(e,o);
    e->camera.distance=r*6.0f;
    if(e->camera.distance<1.0f)e->camera.distance=1.0f;
}
void kavram3d_set_preset(void *h,int preset){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    switch(preset){
        case 1: e->camera.yaw=-90.0f*(float)M_PI/180.0f; e->camera.pitch=89.0f*(float)M_PI/180.0f; break;
        case 3: e->camera.yaw=-90.0f*(float)M_PI/180.0f; e->camera.pitch=0.0f; break;
        case 7: e->camera.yaw=0.0f; e->camera.pitch=0.0f; break;
        default:e->camera.yaw=-60.0f*(float)M_PI/180.0f; e->camera.pitch=25.0f*(float)M_PI/180.0f; break;
    }
    if(e->camera.distance<1.0f)e->camera.distance=12.0f;
}
void kavram3d_toggle_projection(void *h){KVEngine*e=(KVEngine*)h;if(!e)return;e->camera.orthographic=!e->camera.orthographic;}
int kavram3d_is_orthographic(void *h){KVEngine*e=(KVEngine*)h;return e?e->camera.orthographic:0;}
int kavram3d_ground_visible(void *h){KVEngine*e=(KVEngine*)h;return e?e->ground_visible:0;}

static void kv_drag_selected(KVEngine *e,float dx,float dy,int mode){
    if(!e)return;
    for(int i=0;i<e->object_count;++i){
        KVObject*o=&e->objects[i];
        if(!o->selected)continue;
        if(mode==0){
            float cp=cosf(e->camera.pitch),sp=sinf(e->camera.pitch);
            float cy=cosf(e->camera.yaw),sy=sinf(e->camera.yaw);
            float right[3]={-sy,cy,0},up[3]={-sp*cy,-sp*sy,cp};
            float s=e->camera.distance*0.002f;
            o->position[0]+=( dx*right[0]+(-dy)*up[0])*s;
            o->position[1]+=( dx*right[1]+(-dy)*up[1])*s;
            o->position[2]+=( dx*right[2]+(-dy)*up[2])*s;
        } else if(mode==1){
            o->rotation[2]+=dx*0.01f;
            o->rotation[0]+=dy*0.01f;
        } else if(mode==2){
            float f=1.0f+(dx+dy)*0.005f;
            if(f<0.01f)f=0.01f;
            o->scale[0]*=f;o->scale[1]*=f;o->scale[2]*=f;
        }
    }
}
void kavram3d_move_selected_drag(void*h,float dx,float dy){kv_drag_selected((KVEngine*)h,dx,dy,0);}
void kavram3d_rotate_selected_drag(void*h,float dx,float dy){kv_drag_selected((KVEngine*)h,dx,dy,1);}
void kavram3d_scale_selected_drag(void*h,float dx,float dy){kv_drag_selected((KVEngine*)h,dx,dy,2);}

void kavram3d_get_object_state(void *h,int id,float*p,float*r,float*s){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    KVObject*o=kv_find(e,id);if(!o)return;
    if(p){p[0]=o->position[0];p[1]=o->position[1];p[2]=o->position[2];}
    if(r){r[0]=o->rotation[0];r[1]=o->rotation[1];r[2]=o->rotation[2];}
    if(s){s[0]=o->scale[0];s[1]=o->scale[1];s[2]=o->scale[2];}
}
void kavram3d_set_object_state(void *h,int id,const float*p,const float*r,const float*s){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    KVObject*o=kv_find(e,id);if(!o)return;
    if(p){o->position[0]=p[0];o->position[1]=p[1];o->position[2]=p[2];}
    if(r){o->rotation[0]=r[0];o->rotation[1]=r[1];o->rotation[2]=r[2];}
    if(s){o->scale[0]=s[0];o->scale[1]=s[1];o->scale[2]=s[2];}
}

int kavram3d_create_object(void *h,int mesh_id,const char *name,float x,float y,float z){
    KVEngine*e=(KVEngine*)h;if(!e)return 0;
    if(!kv_ensure_capacity(e, e->object_count + 1)) return 0;
    KVObject*o=&e->objects[e->object_count++];
    memset(o,0,sizeof(*o));
    o->id=e->next_id++;
    o->mesh_id=mesh_id;
    if(name)strncpy(o->name,name,sizeof(o->name)-1);
    else strcpy(o->name,"Nesne");
    o->position[0]=x;o->position[1]=y;o->position[2]=z;
    o->scale[0]=o->scale[1]=o->scale[2]=1.0f;
    o->color[0]=0.55f;o->color[1]=0.58f;o->color[2]=0.62f;o->color[3]=1.0f;
    o->selected=1;
    o->group_id=0;
    return o->id;
}

static int kv_add_object_at_ground(void*h,int mesh_id,float gx,float gy,const char*name,int target){
    KVEngine*e=(KVEngine*)h;if(!e)return 0;
    float p[3]={gx,gy,0};
    float sc[3]={1,1,1}, rt[3]={0,0,0};
    KVObject probe; memset(&probe,0,sizeof(probe)); probe.mesh_id=mesh_id;
    probe.scale[0]=probe.scale[1]=probe.scale[2]=1.0f;
    float new_r=kv_obj_radius(e,&probe);
    if(target){
        KVObject*t=kv_find(e,target);
        if(t){
            float r=kv_obj_radius(e,t);
            p[0]=t->position[0]; p[1]=t->position[1]; p[2]=t->position[2]+r+new_r;
        } else {
            p[2]=new_r;
        }
    } else {
        p[2]=new_r;
    }
    if(kv_candidate_collides(e,NULL,0,mesh_id,p,rt,sc,0.01f)) return 0;
    return kavram3d_create_object(h,mesh_id,name,p[0],p[1],p[2]);
}

int kavram3d_add_object_at_surface(void*h,int mesh_id,float sx,float sy,const char*name,int target){
    float p[3]={0,0,0};
    if(!kavram3d_screen_to_ground(h,sx,sy,p)) return 0;
    return kv_add_object_at_ground(h,mesh_id,p[0],p[1],name,target);
}

float kavram3d_selected_brush_spacing(void *h) {
    KVEngine *e=(KVEngine*)h;
    if(!e) return 0.0f;
    int first_id=0, n=0;
    for(int i=0;i<e->object_count;++i){
        KVObject *o=&e->objects[i];
        if(!o->selected) continue;
        if(!first_id) first_id=o->id;
        ++n;
    }
    if(!n) return 0.0f;
    KVObject *anchor=kv_find(e,first_id);
    if(!anchor) return 0.0f;
    float max_extent=0.0f;
    for(int i=0;i<e->object_count;++i){
        KVObject *o=&e->objects[i];
        if(!o->selected) continue;
        float r=kv_obj_radius(e,o);
        float dx=o->position[0]-anchor->position[0];
        float dy=o->position[1]-anchor->position[1];
        float dz=o->position[2]-anchor->position[2];
        float extent=sqrtf(dx*dx+dy*dy+dz*dz)+r;
        if(extent>max_extent) max_extent=extent;
    }
    return fmaxf(max_extent*2.0f+0.02f,0.05f);
}

float kavram3d_mesh_brush_spacing(void *h,int mesh_id) {
    KVEngine *e=(KVEngine*)h;
    if(!e) return 0.05f;
    KVObject tmp; memset(&tmp,0,sizeof(tmp));
    tmp.mesh_id=mesh_id;
    tmp.scale[0]=tmp.scale[1]=tmp.scale[2]=1.0f;
    return fmaxf(kv_obj_radius(e,&tmp)*2.0f+0.02f,0.05f);
}

float kavram3d_draw_spacing_for_selection_or_mesh(void *h, int mesh_id) {
    KVEngine *e=(KVEngine*)h;
    if(!e) return 0.05f;
    float selected=kavram3d_selected_brush_spacing(h);
    if(selected>0.0f) return selected;
    return kavram3d_mesh_brush_spacing(h,mesh_id);
}

static int kv_duplicate_selection_at_ground(void *h, float gx, float gy){
    KVEngine*e=(KVEngine*)h;if(!e)return 0;
    int n=0;
    for(int i=0;i<e->object_count;++i) if(e->objects[i].selected) ++n;
    if(!n)return 0;
    int *ids=(int*)malloc((size_t)n*sizeof(int));
    float *pos=(float*)malloc((size_t)n*3*sizeof(float));
    if(!ids||!pos){free(ids);free(pos);return 0;}
    int k=0;
    for(int i=0;i<e->object_count;++i) if(e->objects[i].selected) ids[k++]=e->objects[i].id;

    KVObject *anchor=kv_find(e,ids[0]);
    if(!anchor){free(ids);free(pos);return 0;}
    float target[3]={gx,gy,0.0f};

    float min_bottom=1e30f;
    for(int i=0;i<n;++i){
        KVObject*o=kv_find(e,ids[i]); if(!o) continue;
        float bottom=kv_object_bottom(e,o);
        if(bottom<min_bottom)min_bottom=bottom;
    }
    if(min_bottom>1e20f)min_bottom=0.0f;
    float delta[3]={target[0]-anchor->position[0],target[1]-anchor->position[1],-min_bottom};

    for(int i=0;i<n;++i){
        KVObject*o=kv_find(e,ids[i]); if(!o){free(ids);free(pos);return 0;}
        pos[i*3+0]=o->position[0]+delta[0];
        pos[i*3+1]=o->position[1]+delta[1];
        pos[i*3+2]=o->position[2]+delta[2];
    }

    /* Aynı fırça izi içinde grup parçaları birbirine göre nasıl duruyorsa o şekilde kalır.
       Mevcut sahnedeki başka nesnelerle çakışan bir damga üretilmez. */
    for(int i=0;i<n;++i){
        KVObject*o=kv_find(e,ids[i]);
        if(kv_candidate_collides(e,ids,n,o->mesh_id,&pos[i*3],o->rotation,o->scale,0.01f)){
            free(ids);free(pos);return 0;
        }
    }

    if(!kv_ensure_capacity(e, e->object_count + n)){
        free(ids);free(pos);return 0;
    }
    int new_group=e->next_group_id++;
    int created=0;
    for(int i=0;i<n;++i){
        KVObject*src=kv_find(e,ids[i]); if(!src) continue;
        KVObject*no=&e->objects[e->object_count++];
        *no=*src;
        no->id=e->next_id++;
        no->position[0]=pos[i*3+0];
        no->position[1]=pos[i*3+1];
        no->position[2]=pos[i*3+2];
        no->motion_time=0.0f;
        no->selected=0;
        no->duplicate=1;
        no->group_id=new_group;
        if(!created)created=no->id;
    }
    free(ids);free(pos);
    return created;
}

int kavram3d_duplicate_selection_at_surface(void*h,float sx,float sy){
    KVEngine*e=(KVEngine*)h;if(!e)return 0;
    float target[3];
    if(!kavram3d_screen_to_ground(h,sx,sy,target))return 0;
    return kv_duplicate_selection_at_ground(h,target[0],target[1]);
}

int kavram3d_duplicate_selected_at_surface(void*h,float sx,float sy,int target){
    (void)target;
    return kavram3d_duplicate_selection_at_surface(h,sx,sy);
}

int kavram3d_duplicate_selection_at_ground(void*h,float gx,float gy){
    return kv_duplicate_selection_at_ground(h,gx,gy);
}

void kavram3d_delete_selected(void*h){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    int write=0;
    for(int read=0;read<e->object_count;++read){
        if(e->objects[read].selected) continue;
        if(write!=read) e->objects[write]=e->objects[read];
        ++write;
    }
    e->object_count=write;
}

void kavram3d_delete_object(void*h,int id){
    KVEngine*e=(KVEngine*)h;if(!e||!id)return;
    int idx=kv_index(e,id);if(idx<0)return;
    for(int i=idx;i<e->object_count-1;++i)e->objects[i]=e->objects[i+1];
    e->object_count--;
}

void kavram3d_set_object_group(void*h,int id,int group_id){
    KVEngine*e=(KVEngine*)h;if(!e)return; KVObject*o=kv_find(e,id); if(o)o->group_id=group_id;
}
int kavram3d_get_object_group(void*h,int id){
    KVEngine*e=(KVEngine*)h;if(!e)return 0; KVObject*o=kv_find(e,id); return o?o->group_id:0;
}

void kavram3d_subdivide_selected(void*h){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    int n=0;
    for(int i=0;i<e->object_count;++i) if(e->objects[i].selected) ++n;
    if(!n) return;
    int *ids=(int*)malloc((size_t)n*sizeof(int));
    if(!ids) return;
    int ik=0;
    for(int i=0;i<e->object_count;++i) if(e->objects[i].selected) ids[ik++]=e->objects[i].id;
    for(int i=0;i<e->object_count;++i)e->objects[i].selected=0;
    for(int k=0;k<n;++k){
        KVObject*src=kv_find(e,ids[k]);if(!src)continue;
        if(!kv_ensure_capacity(e, e->object_count+8)) break;
        float half[3];kv_mesh_half(e,src->mesh_id,half);
        for(int dx=-1;dx<=1;dx+=2)for(int dy=-1;dy<=1;dy+=2)for(int dz=-1;dz<=1;dz+=2){
            if(!kv_ensure_capacity(e, e->object_count+1)) break;
            KVObject*o=&e->objects[e->object_count++];
            *o=*src;
            o->id=e->next_id++;
            o->scale[0]=src->scale[0]*0.5f;
            o->scale[1]=src->scale[1]*0.5f;
            o->scale[2]=src->scale[2]*0.5f;
            o->position[0]=src->position[0]+(float)dx*half[0]*src->scale[0]*0.5f;
            o->position[1]=src->position[1]+(float)dy*half[1]*src->scale[1]*0.5f;
            o->position[2]=src->position[2]+(float)dz*half[2]*src->scale[2]*0.5f;
            o->motion_time=0.0f;o->selected=1;
        }
        int idx=kv_index(e,src->id);
        if(idx>=0){for(int i=idx;i<e->object_count-1;++i)e->objects[i]=e->objects[i+1];e->object_count--;}
    }
    free(ids);
}

void kavram3d_set_mesh_bounds(void*h,int mesh_id,const float*half){
    KVEngine*e=(KVEngine*)h;if(!e||!half)return;
    if(mesh_id<0||mesh_id>=KV_MAX_MESH_BOUNDS)return;
    e->mesh_bounds[mesh_id][0]=half[0];
    e->mesh_bounds[mesh_id][1]=half[1];
    e->mesh_bounds[mesh_id][2]=half[2];
    e->mesh_bounds_set[mesh_id]=1;
}

void kavram3d_get_object_info(void*h,int id,int*mesh_id,float*color,int*duplicate,int*enabled,float*speed,int*mode,int*axis,char*name,size_t cap){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    KVObject*o=kv_find(e,id);if(!o)return;
    if(mesh_id)*mesh_id=o->mesh_id;
    if(color){color[0]=o->color[0];color[1]=o->color[1];color[2]=o->color[2];color[3]=o->color[3];}
    if(duplicate)*duplicate=o->duplicate;
    if(enabled)*enabled=o->motion_enabled;
    if(speed)*speed=o->motion_speed;
    if(mode)*mode=o->motion_mode;
    if(axis)*axis=o->motion_axis;
    if(name&&cap){strncpy(name,o->name,cap-1);name[cap-1]='\0';}
}

void kavram3d_set_object_color(void*h,int id,const float*rgba){
    KVEngine*e=(KVEngine*)h;if(!e||!rgba)return;
    KVObject*o=kv_find(e,id);if(!o)return;
    o->color[0]=rgba[0];o->color[1]=rgba[1];o->color[2]=rgba[2];o->color[3]=rgba[3];
}

void kavram3d_set_object_motion(void*h,int id,int enabled,float speed,int mode,int axis){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    KVObject*o=kv_find(e,id);if(!o)return;
    o->motion_enabled=enabled?1:0;
    o->motion_speed=speed;o->motion_mode=mode;o->motion_axis=axis;o->motion_time=0;
}

void kavram3d_set_selected_motion(void*h,int enabled,float speed,int mode,int axis){
    KVEngine*e=(KVEngine*)h;if(!e)return;
    for(int i=0;i<e->object_count;++i)
        if(e->objects[i].selected){
            e->objects[i].motion_enabled=enabled?1:0;
            e->objects[i].motion_speed=speed;
            e->objects[i].motion_mode=mode;
            e->objects[i].motion_axis=axis;
        }
}

int kavram3d_active_animation_count(void*h){
    KVEngine*e=(KVEngine*)h;if(!e)return 0;
    int c=0;
    for(int i=0;i<e->object_count;++i)
        if(e->objects[i].motion_enabled&&e->objects[i].motion_mode!=0)++c;
    return c;
}

void kavram3d_tick(void*h,float dt){
    KVEngine*e=(KVEngine*)h;if(!e||dt<=0)return;
    for(int i=0;i<e->object_count;++i){
        KVObject*o=&e->objects[i];
        if(o->motion_enabled&&o->motion_mode!=0)o->motion_time+=dt;
    }
}

int kavram3d_render_item_count(void*h){KVEngine*e=(KVEngine*)h;return e?e->object_count:0;}

int kavram3d_get_render_items(void*h,KVRenderItem*out,int cap){
    KVEngine*e=(KVEngine*)h;if(!e||!out||cap<=0)return 0;
    int n=e->object_count;if(n>cap)n=cap;
    for(int i=0;i<n;++i){
        KVObject*o=&e->objects[i];
        out[i].id=o->id;
        out[i].mesh_id=o->mesh_id;
        out[i].selected=o->selected;
        kv_object_model_animated(o,o->motion_time,out[i].model);
        memcpy(out[i].color,o->color,sizeof(out[i].color));
    }
    return n;
}

#ifdef __cplusplus
}
#endif
