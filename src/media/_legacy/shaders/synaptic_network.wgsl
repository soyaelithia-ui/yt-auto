// synaptic_network.wgsl - Dark moody neural graph nodes, subtle synaptic filaments (Rec.709 low luminance)
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

fn proj_on_segment(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
    let pa = p - a;
    let ba = b - a;
    return clamp(dot(pa, ba) / max(0.0001, dot(ba, ba)), 0.0, 1.0);
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let aspect = u.resolution.x / u.resolution.y;
    let p = (in.uv - 0.5) * vec2<f32>(aspect, 1.0);
    
    // Deep dark biological background gradient (luminance 15-25)
    let bg_distort = sin(p.x * 2.5 + u.time * 0.2) * cos(p.y * 2.5 + u.time * 0.15) * 0.02;
    let bg_r = length(p + vec2<f32>(bg_distort, bg_distort));
    var col = mix(vec3<f32>(0.015, 0.025, 0.04), vec3<f32>(0.03, 0.05, 0.08), clamp(bg_r * 1.4, 0.0, 1.0));
    
    // 10 Distributed Neuronal Somas across canvas
    var nodes: array<vec2<f32>, 10>;
    for (var i: i32 = 0; i < 10; i = i + 1) {
        let fi = f32(i);
        let n_seed = u.seed + fi * 17.37;
        let base_x = (sin(fi * 2.1 + n_seed) * 0.42) * aspect;
        let base_y = cos(fi * 2.8 + n_seed) * 0.44;
        let drift = vec2<f32>(
            sin(u.time * 0.25 * u.speed + fi * 3.1) * 0.015,
            cos(u.time * 0.3 * u.speed + fi * 2.7) * 0.015
        );
        nodes[i] = vec2<f32>(base_x, base_y) + drift;
    }
    
    var node_glow: f32 = 0.0;
    var axon_glow: f32 = 0.0;
    var pulse_glow: f32 = 0.0;
    
    // Render Node Bodies & Halos
    for (var i: i32 = 0; i < 10; i = i + 1) {
        let fi = f32(i);
        let d_node = length(p - nodes[i]);
        let fire_phase = sin(u.time * (1.5 + u.tension * 0.8) + fi * 2.3);
        let activity = 0.4 + 0.4 * fire_phase;
        
        let core = smoothstep(0.012, 0.003, d_node) * 0.4;
        let halo = (0.0003 * u.glow_intensity * activity) / (d_node * d_node + 0.0025);
        node_glow = node_glow + core + halo;
    }
    
    // Render Axons & Filaments
    let connections = array<vec2<i32>, 14>(
        vec2<i32>(0, 1), vec2<i32>(1, 2), vec2<i32>(2, 3), vec2<i32>(3, 4),
        vec2<i32>(4, 5), vec2<i32>(5, 6), vec2<i32>(6, 7), vec2<i32>(7, 8),
        vec2<i32>(8, 9), vec2<i32>(0, 3), vec2<i32>(2, 5), vec2<i32>(4, 7),
        vec2<i32>(1, 8), vec2<i32>(3, 9)
    );
    
    for (var k: i32 = 0; k < 14; k = k + 1) {
        let idx_a = connections[k].x;
        let idx_b = connections[k].y;
        let pos_a = nodes[idx_a];
        let pos_b = nodes[idx_b];
        
        let wave_offset = sin(dot(p, vec2<f32>(6.0, 5.0)) + u.time * 0.4) * 0.003;
        let p_wavy = p + vec2<f32>(wave_offset, wave_offset);
        
        let d_axon = dist_to_segment(p_wavy, pos_a, pos_b);
        let axon_core = (0.00025 * u.noise_scale) / (d_axon * d_axon + 0.0012);
        axon_glow = axon_glow + axon_core;
        
        let h = proj_on_segment(p, pos_a, pos_b);
        let pulse_speed = (0.5 + u.tension * 0.3) * u.speed;
        let pulse_t = fract(u.time * pulse_speed + f32(k) * 0.23);
        let pulse_dist = abs(h - pulse_t);
        let pulse_shape = exp(-pulse_dist * pulse_dist * 60.0);
        let pulse_intensity = (pulse_shape * 0.0006 * u.glow_intensity) / (d_axon * d_axon + 0.0010);
        pulse_glow = pulse_glow + pulse_intensity;
    }
    
    // --- LATERAL ZONES: Dendritic Tree Trunks Framing Borders ---
    let dendrite_l = exp(-abs(p.x + 0.46 * aspect) * 20.0) * (0.5 + 0.3 * sin(p.y * 6.0 + u.time * 0.4));
    let dendrite_r = exp(-abs(p.x - 0.46 * aspect) * 20.0) * (0.5 + 0.3 * cos(p.y * 6.0 + u.time * 0.4));
    let dendrites = (dendrite_l + dendrite_r) * 0.15;

    // Subtle Moody Colors
    let axon_col = mix(vec3<f32>(0.08, 0.18, 0.32), u.accent_color * 0.4, 0.4) * (axon_glow + dendrites) * 0.35;
    let node_col = mix(u.accent_color * 0.4, vec3<f32>(0.35, 0.55, 0.75), 0.3) * node_glow * 0.35;
    let pulse_col = vec3<f32>(0.35, 0.60, 0.85) * pulse_glow * 0.4;
    
    col = col + axon_col + node_col + pulse_col;
    
    // Heavy edge vignette for center readability
    let vig = 1.0 - length(in.uv - 0.5) * 0.75;
    col = col * clamp(vig, 0.0, 1.0);

    // Filmic tonemapping
    col = col / (vec3<f32>(1.0) + col * 0.6) * 0.85;
    
    return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
