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

void main() {
    vec2 st = (gl_FragCoord.xy * 2.0 - uResolution.xy) / min(uResolution.x, uResolution.y);
    float r = length(st);
    float theta = atan(st.y, st.x); // [-PI, PI]

    // Sonar sweep rotation speed
    float sweepAngle = mod(uTime * 1.8, 2.0 * PI) - PI;
    float angleDiff = mod(theta - sweepAngle + 2.0 * PI, 2.0 * PI);

    // Phosphor decay trail
    float trail = exp(-angleDiff * 1.8);
    if (r > 0.92) trail = 0.0;

    // Green phosphor base color
    vec3 phosphorColor = vec3(0.0, 1.0, 0.42);
    if (length(uColorTint) > 0.01) {
        phosphorColor = normalize(uColorTint + vec3(0.0, 0.4, 0.1));
    }

    vec3 col = vec3(0.005, 0.02, 0.01);

    // Sonar range rings
    float rings = abs(sin(r * 22.0));
    rings = smoothstep(0.92, 0.98, rings) * 0.18;
    if (r < 0.90) {
        col += phosphorColor * rings;
    }

    // Concentric outer bezel & grid lines
    float bezel = smoothstep(0.91, 0.92, r) - smoothstep(0.93, 0.94, r);
    col += phosphorColor * bezel * 0.8;

    // Axis crosshairs
    float axes = (smoothstep(0.004, 0.0, abs(st.x)) + smoothstep(0.004, 0.0, abs(st.y))) * 0.12;
    if (r < 0.90) col += phosphorColor * axes;

    // Sweep line beam
    float sweepBeam = smoothstep(0.03, 0.0, angleDiff) * smoothstep(0.91, 0.85, r);
    col += vec3(0.6, 1.0, 0.8) * sweepBeam * 1.5;

    // Background phosphor glow from trail
    col += phosphorColor * trail * 0.45 * smoothstep(0.91, 0.85, r);

    // 3 Dynamic Anomalous Target Blips (Hydroacoustic contacts)
    vec2 targets[3];
    targets[0] = vec2(0.35 * cos(uTime * 0.15 + 1.0), 0.35 * sin(uTime * 0.15 + 1.0));
    targets[1] = vec2(0.62 * cos(-uTime * 0.08 + 3.2), 0.62 * sin(-uTime * 0.08 + 3.2));
    targets[2] = vec2(0.78 * cos(uTime * 0.22 + 4.5), 0.78 * sin(uTime * 0.22 + 4.5));

    for (int i = 0; i < 3; i++) {
        float dTarget = length(st - targets[i]);
        float targetAngle = atan(targets[i].y, targets[i].x);
        float blipDiff = mod(targetAngle - sweepAngle + 2.0 * PI, 2.0 * PI);
        float blipFade = exp(-blipDiff * 3.5);

        // Blip pulse
        float blip = smoothstep(0.035, 0.005, dTarget) * blipFade;
        // Red anomalous signature increases with tension
        vec3 blipColor = mix(vec3(0.2, 1.0, 0.5), vec3(1.0, 0.15, 0.05), clamp(uTension * 1.2, 0.0, 1.0));
        col += blipColor * blip * 2.2;
    }

    // Subtle background hydrophone acoustic noise
    float seaNoise = hash(st + fract(uTime * 0.01)) * 0.04;
    col += phosphorColor * seaNoise;

    gl_FragColor = vec4(col, 1.0);
}
