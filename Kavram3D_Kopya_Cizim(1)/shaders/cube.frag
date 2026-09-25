#version 330 core
in vec3 vNormal;
in vec3 vWorldPos;
uniform vec3 uCameraPos;
uniform vec3 uColor;
uniform int  uSelected;
out vec4 FragColor;
void main() {
    vec3 N = normalize(vNormal);
    vec3 L = normalize(vec3(0.45, -0.65, 0.90));
    vec3 V = normalize(uCameraPos - vWorldPos);
    vec3 H = normalize(L + V);
    float diff = max(dot(N, L), 0.0);
    float spec = pow(max(dot(N, H), 0.0), 32.0);
    vec3 col = uColor * (0.35 + 0.65 * diff) + vec3(1.0) * spec * 0.25;
    if (uSelected == 1) col = mix(col, vec3(1.0, 0.55, 0.05), 0.35);
    FragColor = vec4(col, 1.0);
}
