// tactical_chamber.wgsl - Brutalist containment architecture, lateral support arches, industrial catwalk, warning strobe pulses
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

fn sd_box(p: vec3<f32>, b: vec3<f32>) -> f32 {
    let q = abs(p) - b;
    return length(max(q, vec3<f32>(0.0))) + min(max(q.x, max(q.y, q.z)), 0.0);
}

fn sd_cylinder(p: vec3<f32>, r: f32, h: f32) -> f32 {
    let d = vec2<f32>(length(p.xz) - r, abs(p.y) - h);
    return min(max(d.x, d.y), 0.0) + length(max(d, vec2<f32>(0.0)));
}

fn map_scene(pos: vec3<f32>) -> vec2<f32> {
    let rep_z = 2.2;
    let seed_entropy = fract(sin(u.seed * 12.9898 + 78.233) * 43758.5453);
    let p_mod = vec3<f32>(pos.x, pos.y, (fract((pos.z + rep_z * 0.5) / rep_z) - 0.5) * rep_z);
    
    let floor_d = pos.y - (-1.2);
    let ceil_d = 1.6 - pos.y;
    let wall_left = pos.x - (-1.9);
    let wall_right = 1.9 - pos.x;
    var d_tunnel = min(min(floor_d, ceil_d), min(wall_left, wall_right));
    
    // Lateral structural columns / reinforced containment ribs
    let rib_thick = 0.22 + 0.04 * sin(seed_entropy * 6.28318);
    let rib_l = sd_box(p_mod - vec3<f32>(-1.75, 0.0, 0.0), vec3<f32>(rib_thick, 1.5, 0.28));
    let rib_r = sd_box(p_mod - vec3<f32>(1.75, 0.0, 0.0), vec3<f32>(rib_thick, 1.5, 0.28));
    let ribs = min(rib_l, rib_r);
    
    // Central containment cell vessel
    let vessel_r = 0.52 + 0.08 * (seed_entropy - 0.5);
    let vessel = sd_cylinder(p_mod - vec3<f32>(0.0, -0.3, 0.0), vessel_r, 0.95);
    
    var mat_id: f32 = 1.0;
    var d_min = d_tunnel;
    
    if (ribs < d_min) {
        d_min = ribs;
        mat_id = 2.0;
    }
    if (vessel < d_min) {
        d_min = vessel;
        mat_id = 3.0;
    }
    
    return vec2<f32>(d_min, mat_id);
}

fn calc_normal(p: vec3<f32>) -> vec3<f32> {
    let e = 0.002;
    let d = map_scene(p).x;
    let n = vec3<f32>(
        map_scene(p + vec3<f32>(e, 0.0, 0.0)).x - d,
        map_scene(p + vec3<f32>(0.0, e, 0.0)).x - d,
        map_scene(p + vec3<f32>(0.0, 0.0, e)).x - d
    );
    return normalize(n);
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let aspect = u.resolution.x / u.resolution.y;
    let p = (in.uv - 0.5) * vec2<f32>(aspect, 1.0);
    
    let seed_entropy = fract(sin(u.seed * 12.9898 + 78.233) * 43758.5453);
    let seed_entropy2 = fract(sin(u.seed * 93.9898 + 33.719) * 23758.5453);
    let seed_rot = seed_entropy2 * 6.2831853;
    
    let cam_speed = 0.35 * u.speed;
    let cam_offset_x = (seed_entropy - 0.5) * 0.3;
    let cam_offset_y = (seed_entropy2 - 0.5) * 0.2;
    let cam_z = u.time * cam_speed + seed_entropy * 17.3891;
    let ro = vec3<f32>(cam_offset_x, cam_offset_y, cam_z);
    let rd = normalize(vec3<f32>(p.x, p.y, 1.15));
    
    var t: f32 = 0.1;
    var mat_id: f32 = 0.0;
    var hit = false;
    for (var i: i32 = 0; i < 48; i = i + 1) {
        let pos = ro + rd * t;
        let res = map_scene(pos);
        if (res.x < 0.003) {
            mat_id = res.y;
            hit = true;
            break;
        }
        if (t > 18.0) {
            break;
        }
        t = t + res.x * 0.85;
    }
    
    var col = vec3<f32>(0.12, 0.16, 0.22);
    
    let strobe_freq = 3.5 + u.tension * 2.5;
    let strobe_pulse = pow(max(0.0, sin(u.time * strobe_freq + seed_rot)), 6.0);
    let alarm_color = mix(vec3<f32>(0.9, 0.55, 0.2), u.accent_color, 0.5);
    let ambient_light = vec3<f32>(0.16, 0.20, 0.26);
    
    if (hit) {
        let pos = ro + rd * t;
        let nor = calc_normal(pos);
        
        let light_pos = vec3<f32>(0.0, 1.3, floor((pos.z + 1.1) / 2.2) * 2.2);
        let light_dir = normalize(light_pos - pos);
        let dist_light = length(light_pos - pos);
        let atten = 1.0 / (1.0 + dist_light * dist_light * 0.25);
        
        let diff = max(0.0, dot(nor, light_dir));
        let half_vec = normalize(light_dir - rd);
        let spec = pow(max(0.0, dot(nor, half_vec)), 16.0);
        
        var albedo = vec3<f32>(0.32, 0.36, 0.40);
        
        // --- BOTTOM ZONE: Floor Grate with Hazard Markings ---
        if (pos.y < -1.15) {
            let grid_offset = seed_entropy * 0.5;
            let grid_x = smoothstep(0.04, 0.06, abs(fract(pos.x * 2.0 + grid_offset) - 0.5));
            let grid_z = smoothstep(0.04, 0.06, abs(fract(pos.z * 2.0 + grid_offset) - 0.5));
            let grid = grid_x * grid_z;
            
            // Yellow caution stripes along boundary
            let stripe_x = abs(pos.x) - 1.2;
            let stripe = step(0.0, stripe_x) * step(stripe_x, 0.4) * step(0.5, fract((pos.x + pos.z) * 2.0));
            albedo = mix(mix(vec3<f32>(0.18, 0.20, 0.24), vec3<f32>(0.42, 0.46, 0.50), grid), vec3<f32>(0.75, 0.65, 0.15), stripe * 0.6);
        }
        
        if (mat_id == 3.0) {
            let band = smoothstep(0.06, 0.0, abs(pos.y - (-0.3)));
            albedo = albedo + u.accent_color * band * (0.6 + strobe_pulse * 0.6);
        }
        
        let light_contrib = (diff + spec * 0.5) * atten * (0.3 + 0.7 * strobe_pulse * u.glow_intensity);
        col = albedo * (ambient_light + light_contrib * alarm_color) + ambient_light * 0.4;
        
        let fog_factor = 1.0 - exp(-t * 0.08);
        col = mix(col, vec3<f32>(0.12, 0.16, 0.22), fog_factor);
    }
    
    // --- TOP ZONE: Ceiling Beacon Sweep ---
    let beacon_angle = u.time * (1.5 + 0.5 * u.speed) + seed_rot;
    let beacon_sweep = max(0.0, dot(normalize(p + vec2<f32>(0.0, 0.2)), vec2<f32>(cos(beacon_angle), sin(beacon_angle))));
    let beacon_glow = pow(beacon_sweep, 3.0) * 0.15;
    col = col + alarm_color * beacon_glow;
    
    let scanline = 0.96 + 0.04 * sin(in.uv.y * u.resolution.y * 1.5 + u.time * 6.0);
    let vig = 1.0 - length(in.uv - 0.5) * 0.5;
    
    col = col * scanline * clamp(vig, 0.0, 1.0);
    
    return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
