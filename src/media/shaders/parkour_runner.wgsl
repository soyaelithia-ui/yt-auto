// parkour_runner.wgsl - Stylized Isometric / 3D Blocky Platformer Parkour Course
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

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let aspect = u.resolution.x / u.resolution.y;
    let p = (in.uv - 0.5) * vec2<f32>(aspect, 1.0);
    
    // Deep dark twilight / cyber synth background gradient
    var col = mix(vec3<f32>(0.015, 0.018, 0.03), vec3<f32>(0.03, 0.02, 0.05), in.uv.y);
    
    // 1. Perspective Grid Track Lines
    let scroll_z = u.time * 2.0 * u.speed;
    for (var i: i32 = -3; i <= 3; i = i + 1) {
        let fi = f32(i);
        let track_x = fi * 0.12 * aspect;
        let d_track = dist_to_segment(p, vec2<f32>(track_x * 0.2, -0.5), vec2<f32>(track_x * 1.6, 0.5));
        let track_glow = smoothstep(0.004, 0.001, d_track);
        col = col + vec3<f32>(0.06, 0.12, 0.24) * track_glow * 0.3;
    }
    
    // 2. Scrolling Blocky Voxel Platforms (Parkour Steps)
    for (var k: i32 = 0; k < 6; k = k + 1) {
        let fk = f32(k);
        let step_seed = u.seed + fk * 13.37;
        let step_t = fract(u.time * (0.35 + fk * 0.02) * u.speed + fk * 0.18);
        let step_y = mix(-0.45, 0.45, step_t);
        let step_x = (sin(fk * 2.5 + step_seed) * 0.22) * aspect;
        
        let pw = 0.07 * (1.0 + step_t * 0.8); // Perspective scaling
        let ph = 0.025 * (1.0 + step_t * 0.8);
        
        let p_top_l = vec2<f32>(step_x - pw, step_y);
        let p_top_r = vec2<f32>(step_x + pw, step_y);
        let p_bot_r = vec2<f32>(step_x + pw, step_y + ph);
        let p_bot_l = vec2<f32>(step_x - pw, step_y + ph);
        
        let d1 = dist_to_segment(p, p_top_l, p_top_r);
        let d2 = dist_to_segment(p, p_top_r, p_bot_r);
        let d3 = dist_to_segment(p, p_bot_r, p_bot_l);
        let d4 = dist_to_segment(p, p_bot_l, p_top_l);
        let d_block = min(min(d1, d2), min(d3, d4));
        
        let block_line = smoothstep(0.0035, 0.001, d_block) * 0.85;
        let block_glow = (0.00025 * u.glow_intensity) / (d_block * d_block + 0.0006);
        let step_col = mix(u.accent_color, vec3<f32>(0.9, 0.2, 0.6), fk * 0.25);
        col = col + step_col * (block_line + block_glow * 0.35);
    }
    
    // 3. Blocky Runner Character silhouette jumping on current step
    let jump_cycle = fract(u.time * 1.8 * u.speed);
    let jump_h = sin(jump_cycle * 3.14159) * 0.06;
    let runner_x = sin(u.time * 0.9 * u.speed) * 0.15 * aspect;
    let runner_y = 0.18 - jump_h;
    let char_p = p - vec2<f32>(runner_x, runner_y);
    
    // Head cube
    let d_head = max(abs(char_p.x) - 0.014, abs(char_p.y + 0.028) - 0.014);
    let head_line = smoothstep(0.003, 0.001, d_head);
    // Torso cube
    let d_torso = max(abs(char_p.x) - 0.018, abs(char_p.y + 0.005) - 0.016);
    let torso_line = smoothstep(0.003, 0.001, d_torso);
    // Legs
    let leg_l = dist_to_segment(char_p, vec2<f32>(-0.01, 0.021), vec2<f32>(-0.012, 0.042));
    let leg_r = dist_to_segment(char_p, vec2<f32>(0.01, 0.021), vec2<f32>(0.012, 0.042));
    let legs_line = smoothstep(0.003, 0.001, min(leg_l, leg_r));
    
    let char_outline = max(max(head_line, torso_line), legs_line);
    let char_glow = (0.0002 * u.glow_intensity) / (length(char_p) * length(char_p) + 0.0008);
    col = col + vec3<f32>(0.0, 1.0, 0.7) * (char_outline * 0.9 + char_glow * 0.3);
    
    // 4. Floating Diamond Collectibles
    for (var c: i32 = 0; c < 3; c = c + 1) {
        let fc = f32(c);
        let gem_t = fract(u.time * 0.4 * u.speed + fc * 0.33);
        let gem_x = (sin(fc * 4.1 + u.seed) * 0.28) * aspect;
        let gem_y = mix(-0.4, 0.3, gem_t);
        let d_gem = abs(p.x - gem_x) + abs(p.y - gem_y) - 0.018;
        let gem_line = smoothstep(0.003, 0.001, abs(d_gem));
        let gem_glow = (0.00015 * u.glow_intensity) / (d_gem * d_gem + 0.0005);
        col = col + vec3<f32>(1.0, 0.85, 0.2) * (gem_line + gem_glow * 0.3);
    }
    
    // Vignette
    let vig = 1.0 - length(in.uv - 0.5) * 0.7;
    col = col * clamp(vig, 0.0, 1.0);
    
    // Filmic tonemapping
    col = col / (vec3<f32>(1.0) + col * 0.5) * 0.88;
    
    return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
