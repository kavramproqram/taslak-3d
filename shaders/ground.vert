#version 330 core
layout(location=0) in vec2 aPos;
uniform mat4  uVP;
uniform vec2  uCenter;
uniform float uSize;
out vec2 vWorld;
void main() {
    vec2 p = aPos * uSize + uCenter;
    vWorld = p;
    gl_Position = uVP * vec4(p, 0.0, 1.0);
}
