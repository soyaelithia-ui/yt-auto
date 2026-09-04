// arctic_desolation.wgsl - Volumetric blizzard, tiered pine side framing, drifting aurora, soaring birds, and snowy terrain
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
    var shift: vec2<f32> = vec2<f32>(60.0, 60.0);
    var p_curr = p;
    for (var i: i32 = 0; i < 4; i = i + 1) {
        v = v + a * noise2d(p_curr);
        p_curr = p_curr * 2.0 + shift;
        a = a * 0.5;
    }
    return v;
}

// Distance to flying bird silhouette with flapping wings
fn bird_shape(p: vec2<f32>, flap_phase: f32) -> f32 {
    let px = abs(p.x);
    if (px > 0.028) { return 0.0; }
    let flap = sin(flap_phase);
    let wing_y = -px * (0.55 + 0.35 * flap) + (px * px * 12.0);
    let d_wing = abs(p.y - wing_y);
    let wing_thick = (0.028 - px) * 0.15;
    let is_wing = step(d_wing, wing_thick);
    let is_body = step(length(p * vec2<f32>(2.5, 5.0)), 0.006);
    return max(is_wing, is_body);
}

// Natural organic pine conifer tree silhouette
fn pine_tree_natural(p: vec2<f32>, trunk_x: f32, top_y: f32, height: f32, seed_val: f32) -> f32 {
    let dx = p.x - trunk_x;
    let y_rel = p.y - top_y;
    if (y_rel < 0.0 || y_rel > height) { return 0.0; }
    
    let t = y_rel / height;
    // Continuous conical base widening toward ground
    let cone = t * (0.045 + 0.075 * t);
    // Overlapping jagged pine branch clusters
    let boughs = (1.0 - fract(y_rel * 18.0)) * 0.016 * t;
    let needles = sin(y_rel * 150.0 + seed_val) * 0.003 + sin(dx * 180.0) * 0.002;
    let total_width = cone + boughs + needles;
    
    let is_canopy = step(abs(dx), total_width);
    let is_trunk = step(abs(dx), 0.006) * step(0.1, t);
    return max(is_canopy, is_trunk);
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let aspect = u.resolution.x / u.resolution.y;
    let p = (in.uv - 0.5) * vec2<f32>(aspect, 1.0);
    
    // --- TOP ZONE: Aurora Borealis & Cold Twilight Sky ---
    let sky_base = mix(vec3<f32>(0.07, 0.11, 0.18), vec3<f32>(0.14, 0.22, 0.32), clamp(p.y + 0.5, 0.0, 1.0));
    
    // Soft Aurora ribbon
    let aurora_x = p.x * 2.5 + sin(u.time * 0.15 + u.seed) * 0.25;
    let aurora_wave = sin(aurora_x * 4.0 + u.time * 0.4) * 0.05 + cos(aurora_x * 7.0) * 0.025;
    let aurora_d = abs(p.y - (-0.38 + aurora_wave));
    let aurora_glow = exp(-aurora_d * 20.0) * smoothstep(0.0, -0.45, p.y) * 0.45;
    let aurora_col = mix(vec3<f32>(0.25, 0.88, 0.62), u.accent_color, 0.35) * aurora_glow;
    
    let pale_sun_pos = vec2<f32>(-0.22 * aspect, -0.36);
    let d_sun = length(p - pale_sun_pos);
    let pale_glow = exp(-d_sun * 3.2) * 0.35;
    var sky = sky_base + aurora_col + vec3<f32>(0.65, 0.85, 0.98) * pale_glow;

    // --- TOP ZONE: Soaring Birds ---
    var birds_mask: f32 = 0.0;
    let flock_speed = u.time * (0.045 + 0.02 * u.speed);
    let flap_time = u.time * 12.0;
    for (var b: i32 = 0; b < 4; b = b + 1) {
        let bf = f32(b);
        let b_seed = u.seed * 4.1 + bf * 17.3;
        let bx = fract(flock_speed + bf * 0.1 + b_seed * 0.1) * (aspect + 0.3) - (aspect * 0.5 + 0.15);
        let by = -0.34 - bf * 0.028 + sin(bx * 2.8 + b_seed) * 0.015;
        let b_shape = bird_shape(p - vec2<f32>(bx, by), flap_time + bf * 1.6);
        birds_mask = max(birds_mask, b_shape);
    }
    let bird_col = vec3<f32>(0.04, 0.06, 0.09);

    // --- MIDGROUND: Distant Snowy Mountain Peaks (Layer 1) ---
    let ridge1 = -0.15 + 0.15 * sin(p.x * 2.2 + u.seed) + 0.06 * sin(p.x * 5.2) + 0.04 * fbm(vec2<f32>(p.x * 8.0, 0.0));
    let layer1_mask = smoothstep(ridge1 - 0.015, ridge1 + 0.015, p.y);
    let ridge1_snow = smoothstep(0.38, 0.78, fbm(vec2<f32>(p.x * 8.0, p.y * 12.0)));
    let layer1_col = mix(vec3<f32>(0.08, 0.12, 0.18), vec3<f32>(0.26, 0.36, 0.46), ridge1_snow * 0.7);

    // --- MIDGROUND: Rocky Hills (Layer 2) ---
    let ridge2 = 0.06 + 0.10 * sin(p.x * 2.8 + u.seed * 3.1) + 0.05 * sin(p.x * 6.0 + 1.2);
    let layer2_mask = smoothstep(ridge2 - 0.01, ridge2 + 0.01, p.y);
    let ridge2_snow = smoothstep(0.35, 0.75, fbm(vec2<f32>(p.x * 10.0, p.y * 15.0)));
    let layer2_col = mix(vec3<f32>(0.07, 0.10, 0.15), vec3<f32>(0.30, 0.40, 0.50), ridge2_snow * 0.75);

    // --- BOTTOM ZONE: Foreground Snow Plains & Drifts (Layer 3) ---
    let ground_y = 0.22 + 0.04 * sin(p.x * 3.5 + u.seed * 5.0);
    let layer3_mask = smoothstep(ground_y - 0.01, ground_y + 0.01, p.y);
    let ground_snow = fbm(vec2<f32>(p.x * 14.0, p.y * 22.0));
    let layer3_col = mix(vec3<f32>(0.06, 0.09, 0.13), vec3<f32>(0.34, 0.44, 0.54), ground_snow * 0.75);

    // Volumetric drifting snow mist / ground blizzard
    let wind_t = u.time * (0.35 + 0.15 * u.speed);
    let fog_uv = vec2<f32>(p.x * 1.8 - wind_t * 1.2, p.y * 3.0 + sin(p.x * 2.0 + wind_t) * 0.1);
    let fog_density = fbm(fog_uv * u.noise_scale + u.seed * 2.0) * smoothstep(-0.2, 0.45, p.y) * (0.5 + 0.25 * u.tension);
    let fog_col = mix(vec3<f32>(0.16, 0.25, 0.34), u.accent_color * 0.35, 0.25);

    // Composite Scenery Layers
    var col = sky;
    col = mix(col, bird_col, birds_mask);
    col = mix(col, layer1_col, layer1_mask);
    col = mix(col, layer2_col, layer2_mask);
    col = col + fog_col * fog_density;
    col = mix(col, layer3_col, layer3_mask);

    // --- LATERAL ZONES: Natural Pine Silhouettes on Left & Right Margins ---
    let wind_sway = sin(u.time * 1.2 + p.y * 1.5) * 0.003;
    
    // Left pines
    let tree_l1 = pine_tree_natural(p + vec2<f32>(wind_sway, 0.0), -0.44 * aspect, -0.15, 0.75, u.seed);
    let tree_l2 = pine_tree_natural(p + vec2<f32>(wind_sway * 0.8, 0.0), -0.38 * aspect, 0.0, 0.60, u.seed + 3.1);
    
    // Right pines
    let tree_r1 = pine_tree_natural(p - vec2<f32>(wind_sway, 0.0), 0.45 * aspect, -0.18, 0.78, u.seed + 7.7);
    let tree_r2 = pine_tree_natural(p - vec2<f32>(wind_sway * 0.7, 0.0), 0.39 * aspect, 0.02, 0.58, u.seed + 11.3);
    
    let fg_trees = clamp(tree_l1 + tree_l2 + tree_r1 + tree_r2, 0.0, 1.0);
    let tree_snow_rim = smoothstep(0.45, 0.85, fbm(vec2<f32>(p.x * 25.0, p.y * 30.0))) * 0.35;
    let tree_col = mix(vec3<f32>(0.04, 0.06, 0.08), vec3<f32>(0.24, 0.32, 0.40), tree_snow_rim);
    col = mix(col, tree_col, fg_trees);

    // Falling snow particles (2-layer parallax)
    var snow_glow: f32 = 0.0;
    let flake_wind = vec2<f32>(-0.45 * wind_t, wind_t * 0.6);
    
    // Layer A - fine background snow
    let grid_a = (p * 28.0 + flake_wind * 1.8);
    let cell_a = floor(grid_a);
    let local_a = fract(grid_a) - 0.5;
    let h_a = hash22(cell_a + u.seed * 7.7);
    let flake_pos_a = (h_a - 0.5) * 0.7;
    let dist_a = length(local_a - flake_pos_a);
    let flake_a = exp(-dist_a * 16.0) * step(0.65, h_a.x) * 0.45;
    snow_glow = snow_glow + flake_a;

    // Layer B - midground drifting snowflakes
    let grid_b = (p * 14.0 + flake_wind * 2.6);
    let cell_b = floor(grid_b);
    let local_b = fract(grid_b) - 0.5;
    let h_b = hash22(cell_b + u.seed * 11.3);
    let flake_pos_b = (h_b - 0.5) * 0.6;
    let dist_b = length(local_b - flake_pos_b);
    let flake_b = exp(-dist_b * 12.0) * step(0.82, h_b.x) * 0.65;
    snow_glow = snow_glow + flake_b;

    col = col + vec3<f32>(0.85, 0.92, 1.0) * snow_glow * (0.8 + 0.2 * u.glow_intensity);

    // Vignette
    let vig = 1.0 - length(in.uv - 0.5) * 0.45;
    col = col * clamp(vig, 0.0, 1.0);

    // Filmic tonemapping
    col = col / (vec3<f32>(1.0) + col * 0.45) * 0.95;

    return vec4<f32>(clamp(col, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}
