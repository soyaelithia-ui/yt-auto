// cozy_hearth.wgsl - Atmospheric Rainy Cabin Interior with Warm Fireplace Glow
struct Uniforms {
    resolution: vec2<f32>,
    time: f32,
    duration: f32,
    seed: f32,
    tension: f32,
    noise_scale: f32,
    speed: f32,
    accent_color: vec3<f32>,
    distortion: f32,
    glow_intensity: f32,
    custom_1: f32,
    custom_2: f32,
    custom_3: f32,
};
@group(0) @binding(0) var<uniform> u: Uniforms;

struct VertexOutput {
    @builtin(position) position: vec4<f32>,
    @location(0) uv: vec2<f32>,
};

@vertex
fn vs_main(@builtin(vertex_index) vertex_index: u32) -> VertexOutput {
    var out: VertexOutput;
    let x = f32(i32(vertex_index & 1u) * 4 - 1);
    let y = f32(i32(vertex_index >> 1u) * 4 - 1);
    out.position = vec4<f32>(x, y, 0.0, 1.0);
    out.uv = vec2<f32>((x + 1.0) * 0.5, (1.0 - y) * 0.5);
    return out;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let aspect = u.resolution.x / u.resolution.y;
    let p = (in.uv - 0.5) * vec2<f32>(aspect, 1.0);
    
    // Deep dark moody cabin room base (Rec.709 low luminance)
    var col = vec3<f32>(0.015, 0.012, 0.010);
    
    // 1. Rainy Window Pane on Left Side
    let win_x = (in.uv.x - 0.20) * aspect;
    if (in.uv.x < 0.38) {
        // Window frame edge
        let frame_edge = smoothstep(0.005, 0.0, abs(in.uv.x - 0.36));
        col = col + vec3<f32>(0.02, 0.03, 0.05) * frame_edge;
        
        // Cold outside rainy ambience
        let rain_sky = mix(vec3<f32>(0.01, 0.02, 0.04), vec3<f32>(0.02, 0.04, 0.07), in.uv.y);
        col = mix(col, rain_sky, 0.6);
        
        // Rain droplets trickling down glass
        for (var r: i32 = 0; r < 8; r = r + 1) {
            let fr = f32(r);
            let r_seed = u.seed + fr * 23.17;
            let rx = 0.04 + (fr * 0.04);
            let ry = fract(in.uv.y * 3.0 + u.time * (0.4 + fr * 0.1) * u.speed + r_seed);
            let d_drop = length(vec2<f32>(in.uv.x - rx, in.uv.y - ry));
            let drop_glow = smoothstep(0.006, 0.001, d_drop);
            col = col + vec3<f32>(0.04, 0.08, 0.12) * drop_glow;
        }
    }
    
    // 2. Warm Hearth / Fireplace Glow on Lower Right
    let hearth_pos = vec2<f32>(0.35 * aspect, 0.38);
    let d_hearth = length(p - hearth_pos);
    let fire_flicker = sin(u.time * 6.0) * 0.05 + sin(u.time * 14.0) * 0.03 + 0.92;
    let hearth_glow = (0.003 * u.glow_intensity * fire_flicker) / (d_hearth * d_hearth + 0.04);
    let hearth_col = vec3<f32>(0.85, 0.38, 0.12);
    col = col + hearth_col * hearth_glow * 0.45;
    
    // 3. Floating Amber Hearth Embers
    for (var e: i32 = 0; e < 12; e = e + 1) {
        let fe = f32(e);
        let e_seed = u.seed + fe * 19.81;
        let ex = hearth_pos.x + (sin(u.time * 1.2 + e_seed) * 0.06 - 0.04 * fe * 0.1);
        let ey = hearth_pos.y - fract(u.time * (0.2 + fe * 0.04) * u.speed + e_seed) * 0.45;
        let d_ember = length(p - vec2<f32>(ex, ey));
        let ember_glow = (0.00015 * u.glow_intensity) / (d_ember * d_ember + 0.0003);
        col = col + vec3<f32>(1.0, 0.55, 0.15) * ember_glow * 0.35;
    }
    
    // 4. Subtle wood grain horizontal lines on right wall
    if (in.uv.x > 0.42) {
        let plank_y = fract(in.uv.y * 12.0);
        let plank_seam = smoothstep(0.04, 0.0, plank_y);
        col = col - vec3<f32>(0.008) * plank_seam;
    }
    
    // Heavy edge vignette for center narrative focus
    let vig = 1.0 - length(in.uv - 0.5) * 0.65;
    col = col * clamp(vig, 0.0, 1.0);
    
    // Filmic tonemapping
    col = col / (vec3<f32>(1.0) + col * 0.5) * 0.88;
    
    return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
