#version 330 core
in vec2 vWorld;
out vec4 FragColor;
void main() {
    vec2 g  = abs(fract(vWorld) - 0.5);
    float line = smoothstep(0.48, 0.5, max(g.x, g.y));
    vec3 base    = vec3(0.055, 0.060, 0.065);
    vec3 gridCol = vec3(0.185, 0.195, 0.210);
    vec3 col = mix(base, gridCol, line * 0.65);
    FragColor = vec4(col, 1.0);
}
