precision highp float;

uniform vec2 uResolution;
uniform float uTime;
uniform float uGlitchIntensity;
uniform float uTension;
uniform vec3 uCameraPos;
uniform vec3 uColorTint;
varying vec2 vUv;

#define MAX_STEPS 80
#define SURF_DIST 0.002
#define MAX_DIST 40.0
#define PI 3.14159265359

// Smooth minimum for organic geometric blending
float smin(float a, float b, float k) {
    float h = clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0);
    return mix(b, a, h) - k * h * (1.0 - h);
}

// Signed distance to a box
float sdBox(vec3 p, vec3 b) {
    vec3 q = abs(p) - b;
    return length(max(q, 0.0)) + min(max(q.x, max(q.y, q.z)), 0.0);
}

// Distance estimator with infinite spatial domain repetition
float map(vec3 p) {
    // Floor plane with abyssal depth
    float dFloor = p.y + 2.5;

    // Domain repetition: c = period spacing
    vec3 c = vec3(6.0, 0.0, 6.0);
    vec3 q = vec3(mod(p.x + 0.5 * c.x, c.x) - 0.5 * c.x, p.y, mod(p.z + 0.5 * c.z, c.z) - 0.5 * c.z);

    // Monolith geometry: tall non-Euclidean slabs with strange bevels
    float h = 6.0 + sin(floor(p.x / c.x) * 3.1 + floor(p.z / c.z) * 1.7) * 2.0;
    float dMonolith = sdBox(q - vec3(0.0, h * 0.5 - 2.5, 0.0), vec3(0.65, h * 0.5, 0.65)) - 0.08;

    // Glowing fissures inside monoliths
    float fissures = length(max(abs(q.xz) - vec2(0.68), 0.0));

    return min(dFloor, dMonolith);
}

// Normal estimation
vec3 calcNormal(vec3 p) {
    float d = map(p);
    vec2 e = vec2(0.001, 0.0);
    vec3 n = d - vec3(
        map(p - e.xyy),
        map(p - e.yxy),
        map(p - e.yyx)
    );
    return normalize(n);
}

void main() {
    vec2 uv = (gl_FragCoord.xy * 2.0 - uResolution.xy) / min(uResolution.x, uResolution.y);

    // Camera origin with slow ominous drift
    vec3 ro = uCameraPos;
    if (length(ro) < 0.01) {
        ro = vec3(sin(uTime * 0.12) * 1.5, 1.2 + sin(uTime * 0.08) * 0.3, -uTime * 0.85);
    }
    vec3 target = ro + vec3(sin(uTime * 0.09) * 0.4, -0.1, -1.0);

    // Camera ray matrix
    vec3 fwd = normalize(target - ro);
    vec3 right = normalize(cross(fwd, vec3(0.0, 1.0, 0.0)));
    vec3 up = cross(right, fwd);
    vec3 rd = normalize(uv.x * right + uv.y * up + 1.4 * fwd);

    // Raymarching loop
    float dO = 0.0;
    float minDistance = 1000.0;
    int hitStep = 0;

    for (int i = 0; i < MAX_STEPS; i++) {
        vec3 p = ro + rd * dO;
        float dS = map(p);
        dO += dS * 0.85; // slight under-stepping for safety
        minDistance = min(minDistance, dS);
        hitStep = i;
        if (dS < SURF_DIST || dO > MAX_DIST) break;
    }

    vec3 col = vec3(0.004, 0.015, 0.01);

    // Volumetric fog calculation via Beer-Lambert absorption law: T(d) = exp(-sigma * d)
    float fogSigma = 0.09 + uTension * 0.05;
    float transmittance = exp(-fogSigma * min(dO, MAX_DIST));
    vec3 fogColor = vec3(0.01, 0.06, 0.04);

    if (dO < MAX_DIST) {
        vec3 p = ro + rd * dO;
        vec3 n = calcNormal(p);

        // Directional cold light
        vec3 lightDir = normalize(vec3(0.4, 0.8, -0.5));
        float diff = max(dot(n, lightDir), 0.0);
        float amb = 0.15;

        // Base surface color: brutalist slate
        vec3 surfaceColor = vec3(0.08, 0.12, 0.10);

        // Ominous bio-luminescent veins on monolith edges
        float edgeGlow = smoothstep(0.4, 0.0, minDistance) * uTension;
        vec3 glowColor = vec3(0.0, 1.0, 0.5) * edgeGlow * 1.5;

        vec3 lit = surfaceColor * (diff + amb) + glowColor;

        // Apply Beer-Lambert fog blending
        col = mix(fogColor, lit, transmittance);
    } else {
        col = fogColor;
    }

    // Sky / Void ambient gradient
    col += vec3(0.0, 0.02, 0.015) * (1.0 - uv.y);

    gl_FragColor = vec4(col, 1.0);
}
