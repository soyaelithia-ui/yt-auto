// cosmic_singularity.wgsl - Accretion disk raymarching, gravitational lensing, Doppler beaming, shooting star trails, and cosmic dust pillars
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

fn hash21(p: vec2<f32>) -> f32 {
    let q = fract(sin(vec2<f32>(dot(p, vec2<f32>(127.1, 311.7)), dot(p, vec2<f32>(269.5, 183.3)))) * 43758.5453);
    return q.x;
}

fn hash22(p: vec2<f32>) -> vec2<f32> {
    let n = sin(vec2<f32>(dot(p, vec2<f32>(127.1, 311.7)), dot(p, vec2<f32>(269.5, 183.3)))) * 43758.5453;
    return fract(n);
}

fn noise2d(p: vec2<f32>) -> f32 {
    let i = floor(p);
    let f = fract(p);
    let u_smooth = f * f * (3.0 - 2.0 * f);
    let a = hash21(i + vec2<f32>(0.0, 0.0));
    let b = hash21(i + vec2<f32>(1.0, 0.0));
    let c = hash21(i + vec2<f32>(0.0, 1.0));
    let d = hash21(i + vec2<f32>(1.0, 1.0));
    return mix(mix(a, b, u_smooth.x), mix(c, d, u_smooth.x), u_smooth.y);
}

fn fbm(p: vec2<f32>) -> f32 {
    var v: f32 = 0.0;
    var a: f32 = 0.5;
    var shift: vec2<f32> = vec2<f32>(100.0, 100.0);
    var p_curr = p;
    for (var i: i32 = 0; i < 4; i = i + 1) {
        v = v + a * noise2d(p_curr);
        p_curr = p_curr * 2.0 + shift;
        a = a * 0.5;
    }
    return v;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let aspect = u.resolution.x / u.resolution.y;
    var p = (in.uv - 0.5) * vec2<f32>(aspect, 1.0);
    
    let rs: f32 = 0.22;
    let r = length(p);
    
    // Gravitational light deflection
    let deflection = (rs * rs * 0.6) / (r * r + 0.008);
    let p_lensed = p * (1.0 - deflection * u.distortion);
    
    // Accretion disk coordinate warp
    let disk_tilt = 0.35;
    let disk_y = p.y / disk_tilt;
    let r_disk = length(vec2<f32>(p.x, disk_y));
    let phi_disk = atan2(disk_y, p.x);
    
    // Keplerian angular velocity
    let omega = (1.8 + u.tension * 0.6) / (sqrt(r_disk * r_disk * r_disk) + 0.15);
    let time_swirl = u.time * u.speed * omega * 0.2 + u.seed * 0.5;
    
    let disk_uv = vec2<f32>(r_disk * 3.5 - time_swirl, phi_disk * 1.5 + r_disk * 2.5);
    let plasma = fbm(disk_uv * u.noise_scale);
    
    // Relativistic Doppler beaming
    let v_los = -sin(phi_disk) * 0.65;
    let doppler = pow(max(0.1, 1.0 + v_los), 2.2);
    
    // Disk radial mask
    let disk_mask = smoothstep(rs * 1.08, rs * 1.35, r_disk) * (1.0 - smoothstep(rs * 2.0, rs * 4.0, r_disk));
    let disk_intensity = disk_mask * plasma * doppler * 2.0;
    
    // Photon ring spike
    let photon_ring = exp(-pow(abs(r - rs * 1.15) * 75.0, 1.8)) * (1.2 + 0.4 * sin(u.time * (3.0 + u.tension)));
    
    // Event horizon shadow
    let shadow = smoothstep(rs * 0.95, rs * 1.04, r);
    
    // --- TOP ZONE: Relativistic Jets & Shooting Star Trails ---
    let jet_x = abs(p.x) / (abs(p.y) + 0.08);
    let jet = exp(-jet_x * 18.0) * smoothstep(rs * 0.8, rs * 2.2, abs(p.y)) * (0.25 + 0.25 * sin(u.time * (4.0 + u.tension)));
    
    // Shooting star meteor streak
    let meteor_t = fract(u.time * 0.4 + u.seed * 3.1);
    let meteor_start = vec2<f32>(-0.4 * aspect, -0.45);
    let meteor_dir = vec2<f32>(0.6, 0.35);
    let meteor_pos = meteor_start + meteor_dir * (meteor_t * 1.8);
    let d_meteor = length(p - meteor_pos);
    let meteor_trail = exp(-d_meteor * 45.0) * smoothstep(0.0, 0.5, meteor_t) * (1.0 - smoothstep(0.5, 1.0, meteor_t)) * 0.7;

    // --- LATERAL ZONES: Cosmic Dust Pillars (Left & Right) ---
    let pillar_l = fbm(vec2<f32>((p.x + 0.42 * aspect) * 4.0, p.y * 3.0)) * smoothstep(0.0, -0.35 * aspect, p.x);
    let pillar_r = fbm(vec2<f32>((p.x - 0.42 * aspect) * 4.0, p.y * 3.0)) * smoothstep(0.0, 0.35 * aspect, p.x);
    let pillars = (pillar_l + pillar_r) * 0.35;

    // Background nebula
    let bg_nebula = fbm(p * 2.5 + u.seed * 4.0) * 0.15;
    let bg_color = mix(vec3<f32>(0.04, 0.05, 0.09), vec3<f32>(0.08, 0.12, 0.18), clamp(p.y + 0.5, 0.0, 1.0)) 
                 + (bg_nebula + pillars) * u.accent_color * 0.45
                 + vec3<f32>(0.8, 0.9, 1.0) * meteor_trail;
    
    // Smooth anti-aliased point starfield
    let star_uv = p_lensed * 28.0;
    let star_cell = floor(star_uv);
    let star_local = fract(star_uv) - 0.5;
    let star_h = hash22(star_cell + u.seed * 13.7);
    let star_pos = (star_h - 0.5) * 0.7;
    let d_star = length(star_local - star_pos);
    let stars = exp(-d_star * 14.0) * step(0.68, star_h.x) * 0.55;
    
    // Palette calculation
    let base_color = u.accent_color;
    let hot_color = vec3<f32>(0.95, 0.80, 0.60);
    let disk_color = mix(base_color * 0.8, hot_color, pow(plasma, 1.6));
    let ring_color = vec3<f32>(0.7, 0.85, 1.0) * photon_ring;
    let jet_color = vec3<f32>(0.3, 0.55, 0.8) * jet;
    
    var col = bg_color + (disk_color * disk_intensity + ring_color * (0.8 + 0.4 * u.glow_intensity) + jet_color) * shadow;
    col = col + vec3<f32>(stars) * (1.0 - disk_mask * 0.8) * shadow;
    
    // Vignette
    let vig = 1.0 - length(in.uv - 0.5) * 0.55;
    col = col * clamp(vig, 0.0, 1.0);

    // Filmic tonemapping
    col = col / (vec3<f32>(1.0) + col * 0.5) * 0.9;
    
    return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
