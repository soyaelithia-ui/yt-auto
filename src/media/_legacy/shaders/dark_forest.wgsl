// dark_forest.wgsl - Volumetric fog, ancient tree silhouettes, hanging canopy, soaring bats, and moonlight god-rays
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
    var shift: vec2<f32> = vec2<f32>(50.0, 50.0);
    var p_curr = p;
    for (var i: i32 = 0; i < 4; i = i + 1) {
        v = v + a * noise2d(p_curr);
        p_curr = p_curr * 2.0 + shift;
        a = a * 0.5;
    }
    return v;
}

// Bat/Bird flight silhouette
fn bat_shape(p: vec2<f32>, flap_phase: f32) -> f32 {
    let px = abs(p.x);
    if (px > 0.035) { return 0.0; }
    let flap = sin(flap_phase);
    let wing_y = -px * (0.4 + 0.2 * flap) + sin(px * 50.0) * 0.004;
    let d_wing = abs(p.y - wing_y);
    let wing_thick = (0.035 - px) * 0.12;
    let is_wing = step(d_wing, wing_thick);
    let is_body = step(length(p * vec2<f32>(2.0, 4.0)), 0.007);
    return max(is_wing, is_body);
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let aspect = u.resolution.x / u.resolution.y;
    let p = (in.uv - 0.5) * vec2<f32>(aspect, 1.0);
    
    // --- TOP ZONE: Moon & Celestial Light & Canopy ---
    let moon_pos = vec2<f32>(0.22 * aspect, 0.35);
    let d_moon = length(p - moon_pos);
    let moon_halo = exp(-d_moon * 4.0) * 0.55;
    let moon_disk = smoothstep(0.065, 0.055, d_moon) * 0.8;
    
    // Moonlight god-rays
    let ray_dir = normalize(p - moon_pos);
    let ray_angle = atan2(ray_dir.y, ray_dir.x);
    let ray_noise = fbm(vec2<f32>(ray_angle * 4.0, u.time * 0.04 * u.speed));
    let god_rays = pow(ray_noise, 2.2) * exp(-d_moon * 2.0) * (0.8 + 0.2 * sin(u.time * 1.5));
    
    var sky = mix(vec3<f32>(0.05, 0.09, 0.15), vec3<f32>(0.12, 0.20, 0.28), clamp(p.y + 0.5, 0.0, 1.0));
    sky = sky + vec3<f32>(0.75, 0.88, 0.98) * (moon_disk + moon_halo * 0.5) + vec3<f32>(0.35, 0.55, 0.75) * god_rays * 0.5;

    // Distant nocturnal creatures in top sky
    var bat_mask: f32 = 0.0;
    let flock_t = u.time * (0.05 + 0.03 * u.speed);
    for (var k: i32 = 0; k < 4; k = k + 1) {
        let kf = f32(k);
        let k_seed = u.seed * 3.1 + kf * 13.7;
        let bx = fract(flock_t + kf * 0.12 + k_seed * 0.1) * (aspect + 0.3) - (aspect * 0.5 + 0.15);
        let by = 0.28 + kf * 0.03 + sin(bx * 3.0 + k_seed) * 0.02;
        let b = bat_shape(p - vec2<f32>(bx, by), u.time * 14.0 + kf * 1.8);
        bat_mask = max(bat_mask, b);
    }
    let bat_col = vec3<f32>(0.02, 0.03, 0.05);

    // --- MIDGROUND: Distant Mountain Silhouette (Layer 1) ---
    let dist_ridge = -0.05 + 0.12 * sin(p.x * 2.0 + u.seed) + 0.06 * sin(p.x * 5.5);
    let layer1_mask = smoothstep(dist_ridge + 0.01, dist_ridge - 0.01, p.y);
    let layer1_col = vec3<f32>(0.06, 0.10, 0.14);
    
    // --- MIDGROUND: Pine Canopy (Layer 2) ---
    let wind = sin(u.time * (1.2 + u.tension * 0.4) + p.y * 3.0) * 0.015 * (p.y + 0.5);
    let px_tree = (p.x + wind) * 6.5;
    let tree_id = floor(px_tree);
    let tree_local_x = fract(px_tree) - 0.5;
    let tree_h = 0.25 + 0.22 * hash21(vec2<f32>(tree_id, u.seed * 7.1));
    let pine_profile = max(0.0, 1.0 - abs(tree_local_x) * 4.5 - (p.y + 0.3) / tree_h);
    let layer2_mask = step(0.01, pine_profile) * step(p.y, tree_h - 0.3);
    let layer2_col = vec3<f32>(0.04, 0.08, 0.10);
    
    // --- LATERAL ZONES: Foreground Ancient Tree Trunks & Overhanging Branch Canopy ---
    let fg_sway = sin(u.time * (1.5 + u.tension * 0.5)) * 0.004;
    let trunk_l = smoothstep(0.06, 0.03, abs(p.x + 0.46 * aspect + fg_sway + sin(p.y * 4.0) * 0.01));
    let trunk_r = smoothstep(0.05, 0.025, abs(p.x - 0.47 * aspect - fg_sway * 0.8 - cos(p.y * 3.5) * 0.01));
    let canopy_top = step(0.68, fbm(vec2<f32>(p.x * 10.0, (p.y + 0.4) * 8.0))) * step(-0.5, p.y) * step(p.y, -0.28);
    let layer3_mask = clamp(trunk_l + trunk_r + canopy_top, 0.0, 1.0);
    let layer3_col = vec3<f32>(0.02, 0.04, 0.06);
    
    // --- BOTTOM ZONE: Volumetric Ground Fog & Spores ---
    let fog_coord = vec2<f32>(p.x * 2.2 + u.time * 0.08 * u.speed, p.y * 3.5 + sin(p.x * 2.5 + u.time * 0.15) * 0.15);
    let fog_fbm = fbm(fog_coord * u.noise_scale + u.seed * 3.0);
    let fog_height_falloff = smoothstep(0.2, -0.5, p.y);
    let fog_density = fog_fbm * fog_height_falloff * (0.6 + 0.2 * u.tension);
    let fog_color = mix(vec3<f32>(0.12, 0.20, 0.24), u.accent_color * 0.35, 0.3);
    
    // Delicate floating ambient spores / embers
    var spore_glow: f32 = 0.0;
    for (var k: i32 = 0; k < 12; k = k + 1) {
        let kf = f32(k);
        let spore_seed = u.seed + kf * 17.3;
        let sx = (sin(u.time * 0.25 + kf * 2.1 + spore_seed) * 0.45) * aspect;
        let sy = -0.45 + 0.4 * sin(u.time * 0.35 + kf * 3.7 + spore_seed) + 0.03 * kf;
        let d_sp = length(p - vec2<f32>(sx, sy));
        let pulse = 0.4 + 0.4 * sin(u.time * 3.0 + kf * 1.7);
        let spore = exp(-d_sp * 30.0) * pulse * 0.45;
        spore_glow = spore_glow + spore;
    }
    let spore_color = u.accent_color * spore_glow * (0.8 + 0.3 * u.glow_intensity);
    
    // Composite scenery layers
    var col = sky;
    col = mix(col, bat_col, bat_mask);
    col = mix(col, layer1_col, layer1_mask);
    col = mix(col, layer2_col, layer2_mask);
    col = col + fog_color * fog_density;
    col = mix(col, layer3_col, layer3_mask);
    col = col + spore_color;
    
    // Vignette
    let vig = 1.0 - length(in.uv - 0.5) * 0.5;
    col = col * clamp(vig, 0.0, 1.0);

    // Filmic tonemapping
    col = col / (vec3<f32>(1.0) + col * 0.45) * 0.95;
    
    return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
