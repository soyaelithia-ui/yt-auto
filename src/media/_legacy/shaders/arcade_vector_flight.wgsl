// arcade_vector_flight.wgsl - Retro 80s Vector Arcade Space Shooter Background
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

fn dist_to_segment(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
    let pa = p - a;
    let ba = b - a;
    let h = clamp(dot(pa, ba) / max(0.0001, dot(ba, ba)), 0.0, 1.0);
    return length(pa - ba * h);
}

fn rot2d(p: vec2<f32>, a: f32) -> vec2<f32> {
    let s = sin(a);
    let c = cos(a);
    return vec2<f32>(c * p.x - s * p.y, s * p.x + c * p.y);
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let aspect = u.resolution.x / u.resolution.y;
    let p = (in.uv - 0.5) * vec2<f32>(aspect, 1.0);
    
    // Deep dark space void background
    var col = vec3<f32>(0.012, 0.016, 0.024);
    
    // 1. Perspective Arcade Grid at lower viewport
    let grid_y = in.uv.y;
    if (grid_y > 0.65) {
        let depth = 1.0 / max(0.01, grid_y - 0.60);
        let grid_x = p.x * depth;
        let grid_z = (u.time * 2.5 * u.speed) + depth;
        let line_x = abs(fract(grid_x * 0.8) - 0.5);
        let line_z = abs(fract(grid_z * 0.4) - 0.5);
        let grid_glow = smoothstep(0.08, 0.0, min(line_x, line_z)) * exp(-(grid_y - 0.65) * 4.0);
        col = col + vec3<f32>(0.02, 0.08, 0.16) * grid_glow * 0.45;
    }
    
    // 2. Distant Starfield & Vector Particles
    for (var i: i32 = 0; i < 16; i = i + 1) {
        let fi = f32(i);
        let s_seed = u.seed + fi * 31.41;
        let sx = (fract(sin(s_seed * 1.3) * 43758.5453) - 0.5) * aspect;
        let sy = fract(sin(s_seed * 2.7) * 23421.6312 + u.time * (0.15 + fi * 0.03) * u.speed) - 0.5;
        let d_star = length(p - vec2<f32>(sx, sy));
        let star_glow = (0.00015 * u.glow_intensity) / (d_star * d_star + 0.0008);
        col = col + vec3<f32>(0.2, 0.4, 0.6) * star_glow * 0.3;
    }
    
    // 3. Player Vector Spaceship (Delta Wing Triangle) at bottom
    let ship_sway = sin(u.time * 1.5 * u.speed) * 0.08 * aspect;
    let ship_pos = vec2<f32>(ship_sway, 0.36);
    let ship_p = p - ship_pos;
    
    // Ship Vertices (Nose, Left Wing, Right Wing, Center Notch)
    let s_nose = vec2<f32>(0.0, -0.045);
    let s_left = vec2<f32>(-0.035, 0.035);
    let s_right = vec2<f32>(0.035, 0.035);
    let s_notch = vec2<f32>(0.0, 0.02);
    
    let d_hull1 = dist_to_segment(ship_p, s_nose, s_left);
    let d_hull2 = dist_to_segment(ship_p, s_nose, s_right);
    let d_hull3 = dist_to_segment(ship_p, s_left, s_notch);
    let d_hull4 = dist_to_segment(ship_p, s_right, s_notch);
    let d_ship = min(min(d_hull1, d_hull2), min(d_hull3, d_hull4));
    
    let ship_line = smoothstep(0.004, 0.001, d_ship) * 0.9;
    let ship_halo = (0.00025 * u.glow_intensity) / (d_ship * d_ship + 0.0006);
    let ship_col = mix(u.accent_color, vec3<f32>(0.2, 0.8, 1.0), 0.5);
    col = col + ship_col * (ship_line + ship_halo * 0.4);
    
    // Thruster Particle Flame
    let flame_len = 0.025 + 0.015 * sin(u.time * 25.0);
    let d_flame = dist_to_segment(ship_p, s_notch, s_notch + vec2<f32>(0.0, flame_len));
    let flame_glow = (0.0003 * u.glow_intensity) / (d_flame * d_flame + 0.0004);
    col = col + vec3<f32>(1.0, 0.4, 0.1) * flame_glow * 0.4;
    
    // 4. Laser Beams Firing Upward
    for (var l: i32 = 0; l < 3; l = l + 1) {
        let fl = f32(l);
        let laser_t = fract(u.time * (2.2 + u.tension * 0.8) + fl * 0.33);
        let laser_y = mix(0.32, -0.48, laser_t);
        let laser_x = ship_sway + (fl - 1.0) * 0.018;
        let d_laser = dist_to_segment(p, vec2<f32>(laser_x, laser_y), vec2<f32>(laser_x, laser_y - 0.04));
        let laser_glow = (0.0004 * u.glow_intensity) / (d_laser * d_laser + 0.0005);
        col = col + mix(vec3<f32>(0.0, 1.0, 0.6), vec3<f32>(0.2, 0.8, 1.0), fl * 0.5) * laser_glow * 0.45;
    }
    
    // 5. Descending Polygonal Asteroids / Drone Targets
    for (var a: i32 = 0; a < 4; a = a + 1) {
        let fa = f32(a);
        let a_seed = u.seed + fa * 47.19;
        let a_t = fract(u.time * (0.35 + fa * 0.08) * u.speed + fa * 0.25);
        let ax = (sin(fa * 3.4 + a_seed) * 0.38) * aspect;
        let ay = mix(-0.48, 0.38, a_t);
        let a_rot = u.time * (1.2 + fa * 0.5) + a_seed;
        
        let local_p = rot2d(p - vec2<f32>(ax, ay), a_rot);
        let r_size = 0.035;
        
        // Hexagonal Asteroid wireframe
        let v0 = vec2<f32>(0.0, -r_size);
        let v1 = vec2<f32>(r_size * 0.866, -r_size * 0.5);
        let v2 = vec2<f32>(r_size * 0.866, r_size * 0.5);
        let v3 = vec2<f32>(0.0, r_size);
        let v4 = vec2<f32>(-r_size * 0.866, r_size * 0.5);
        let v5 = vec2<f32>(-r_size * 0.866, -r_size * 0.5);
        
        let d_e0 = dist_to_segment(local_p, v0, v1);
        let d_e1 = dist_to_segment(local_p, v1, v2);
        let d_e2 = dist_to_segment(local_p, v2, v3);
        let d_e3 = dist_to_segment(local_p, v3, v4);
        let d_e4 = dist_to_segment(local_p, v4, v5);
        let d_e5 = dist_to_segment(local_p, v5, v0);
        let d_ast = min(min(min(d_e0, d_e1), min(d_e2, d_e3)), min(d_e4, d_e5));
        
        let ast_line = smoothstep(0.0035, 0.001, d_ast) * 0.85;
        let ast_glow = (0.0002 * u.glow_intensity) / (d_ast * d_ast + 0.0008);
        let ast_col = mix(vec3<f32>(0.85, 0.25, 0.45), vec3<f32>(0.9, 0.6, 0.1), fa * 0.3);
        col = col + ast_col * (ast_line + ast_glow * 0.35);
    }
    
    // 6. Subtle CRT Scanline overlay
    let scanline = sin(in.uv.y * u.resolution.y * 1.5) * 0.04;
    col = col - vec3<f32>(scanline);
    
    // Edge Vignette
    let vig = 1.0 - length(in.uv - 0.5) * 0.65;
    col = col * clamp(vig, 0.0, 1.0);
    
    // Filmic Tonemapping
    col = col / (vec3<f32>(1.0) + col * 0.5) * 0.9;
    
    return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
