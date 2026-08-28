precision highp float;

uniform vec2 uResolution;
uniform float uTime;
uniform float uGlitchIntensity;
uniform float uTension;
uniform vec3 uColorTint;
varying vec2 vUv;

#define PI 3.14159265359

float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

// Background cosmic starfield
vec3 starfield(vec2 uv) {
    float n = hash(floor(uv * 120.0));
    float star = smoothstep(0.985, 1.0, n) * hash(uv * 33.0);
    return vec3(star * 0.7, star * 0.85, star * 1.0);
}

void main() {
    vec2 st = (gl_FragCoord.xy * 2.0 - uResolution.xy) / min(uResolution.x, uResolution.y);

    float r = length(st);
    float theta = atan(st.y, st.x);

    // Event Horizon radius (Schwarzschild radius simulation)
    float rs = 0.28;

    // Gravitational Light Bending / Deflection: alpha ~ 1 / r^2
    vec2 deflectedUV = st;
    if (r > rs * 0.95) {
        float deflection = (rs * rs) / (r * r + 0.001);
        deflectedUV = st * (1.0 - deflection * 0.45);
    }

    vec3 col = vec3(0.002, 0.005, 0.008);

    // 1. Lensed Starfield
    col += starfield(deflectedUV);

    // 2. Accretion Disk Simulation (flattened tilted ring in polar coordinates)
    // Stretch Y coordinate to tilt the disk
    vec2 diskUV = vec2(st.x, st.y * 2.8 + sin(st.x * 2.0) * 0.15);
    float rDisk = length(diskUV);
    float thetaDisk = atan(diskUV.y, diskUV.x);

    float diskInner = rs * 1.15;
    float diskOuter = rs * 3.4;

    if (rDisk > diskInner && rDisk < diskOuter) {
        // Disk rotational velocity
        float rotSpeed = 3.2 / sqrt(rDisk + 0.01);
        float diskAngle = thetaDisk - uTime * rotSpeed;

        // Swirling plasma filaments
        float filaments = sin(diskAngle * 6.0 + rDisk * 25.0) * 0.5 + 0.5;
        float density = smoothstep(diskInner, diskInner + 0.15, rDisk) * smoothstep(diskOuter, diskOuter - 0.6, rDisk);

        // Relativistic Doppler Beaming Asymmetry:
        // Material rotating toward observer (st.x < 0) is blue-shifted and substantially brighter.
        // Material rotating away (st.x > 0) is red-shifted and dimmer.
        float dopplerFactor = 1.0 - 0.75 * (st.x / (r + 0.001));

        vec3 blueBeam = vec3(0.3, 0.7, 1.2) * (dopplerFactor * dopplerFactor);
        vec3 redBeam = vec3(1.1, 0.35, 0.1) * (1.0 / (dopplerFactor + 0.1));
        vec3 diskColor = mix(redBeam, blueBeam, smoothstep(0.4, 1.6, dopplerFactor));

        float diskBrightness = density * (0.8 + 0.4 * filaments) * dopplerFactor * 1.8;
        col += diskColor * diskBrightness;
    }

    // 3. Photon Sphere Ring (Sharp gravitational focal ring)
    float photonSphere = smoothstep(0.015, 0.0, abs(r - rs * 1.08));
    col += vec3(0.7, 0.9, 1.4) * photonSphere * 2.5;

    // 4. Pure Black Event Horizon (Light Cannot Escape)
    if (r < rs) {
        // Absolute void of the black hole center
        col = vec3(0.0);
    } else {
        // Inner shadow falloff
        float shadow = smoothstep(rs, rs + 0.06, r);
        col *= shadow;
    }

    // Dynamic gravitational tension pulsing
    col *= (1.0 + uTension * 0.3 * sin(uTime * 4.0));

    gl_FragColor = vec4(col, 1.0);
}
