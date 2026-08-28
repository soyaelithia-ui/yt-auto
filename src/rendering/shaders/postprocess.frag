precision highp float;

uniform sampler2D tDiffuse;
uniform vec2 uResolution;
uniform float uTime;
uniform float uGlitchIntensity;
uniform float uTension;
varying vec2 vUv;

// Pseudo-random hash
float hash(vec2 p) {
    vec3 p3  = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

// 2D Noise
float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
}

// Barrel distortion (CRT curve)
vec2 crtDistortion(vec2 uv, float k) {
    vec2 centered = uv - 0.5;
    float r2 = dot(centered, centered);
    return 0.5 + centered * (1.0 + k * r2);
}

void main() {
    // 1. Block Glitch / Horizontal Row Displacement
    vec2 uv = vUv;
    if (uGlitchIntensity > 0.001) {
        float slice = floor(uv.y * 35.0);
        float sliceNoise = hash(vec2(slice, floor(uTime * 15.0)));
        if (sliceNoise < uGlitchIntensity * 0.45) {
            float shift = (hash(vec2(slice, uTime)) - 0.5) * uGlitchIntensity * 0.08;
            uv.x += shift;
        }
    }

    // 2. CRT Barrel Lens Curvature
    float barrelK = 0.06 + uTension * 0.04;
    vec2 crtUv = crtDistortion(uv, barrelK);

    // Dark border outside CRT curve
    if (crtUv.x < 0.0 || crtUv.x > 1.0 || crtUv.y < 0.0 || crtUv.y > 1.0) {
        gl_FragColor = vec4(0.01, 0.02, 0.015, 1.0);
        return;
    }

    // 3. Dynamic Chromatic Aberration
    vec2 toCenter = crtUv - 0.5;
    float dist = dot(toCenter, toCenter);
    float caOffset = dist * 0.018 + (uGlitchIntensity * 0.025);

    vec2 uvR = crtUv + toCenter * caOffset;
    vec2 uvG = crtUv;
    vec2 uvB = crtUv - toCenter * caOffset;

    float colR = texture2D(tDiffuse, uvR).r;
    float colG = texture2D(tDiffuse, uvG).g;
    float colB = texture2D(tDiffuse, uvB).b;
    vec3 col = vec3(colR, colG, colB);

    // 4. Scanlines with Micro-Flicker
    float scanlineCount = uResolution.y * 0.5;
    float scanline = sin(crtUv.y * scanlineCount * 3.14159265);
    float flicker = 0.96 + 0.04 * sin(uTime * 45.0 + hash(vec2(uTime, 0.0)));
    col *= (0.85 + 0.15 * scanline) * flicker;

    // 5. Analog Film Grain (Pseudo-random per frame/pixel)
    float grain = (hash(crtUv * uResolution + fract(uTime * 43.123)) - 0.5) * 0.14;
    col += vec3(grain);

    // 6. Split Toning / Cosmic Color Grading
    // Shadows: Abyssal green (#03140d -> 0.012, 0.078, 0.051)
    // Highlights: Cool cyan-grey (#b4d4dc -> 0.706, 0.831, 0.863)
    float lum = dot(col, vec3(0.299, 0.587, 0.114));
    
    // Desaturate to 65% (keep 35% color, 65% monochrome base)
    vec3 desat = mix(col, vec3(lum), 0.35);

    vec3 shadowTint = vec3(0.012, 0.078, 0.051);
    vec3 highlightTint = vec3(0.706, 0.831, 0.863);

    vec3 graded = mix(shadowTint * (lum * 2.0), highlightTint, smoothstep(0.15, 0.95, lum));
    col = mix(desat, graded, 0.45);

    // Crushed blacks & high contrast analog curve
    col = smoothstep(0.04, 0.98, col);

    // Vignette
    float vig = 1.0 - smoothstep(0.3, 0.75, length(toCenter));
    col *= vig;

    gl_FragColor = vec4(col, 1.0);
}
