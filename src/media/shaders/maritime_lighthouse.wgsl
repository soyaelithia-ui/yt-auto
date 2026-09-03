// maritime_lighthouse.wgsl - Procedural Maritime Lighthouse, Nocturnal Moon, Ocean Waves & Volumetric Beacon
// High-craft procedural atmospheric shader for nautical, coastal, and lighthouse mystery narratives.

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
    var p3 = fract(vec3<f32>(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

fn noise2d(p: vec2<f32>) -> f32 {
    let i = floor(p);
    let f = fract(p);
    let u_smooth = f * f * (3.0 - 2.0 * f);
    return mix(
        mix(hash21(i + vec2<f32>(0.0, 0.0)), hash21(i + vec2<f32>(1.0, 0.0)), u_smooth.x),
        mix(hash21(i + vec2<f32>(0.0, 1.0)), hash21(i + vec2<f32>(1.0, 1.0)), u_smooth.x),
        u_smooth.y
    );
}

fn fbm2d(p: vec2<f32>) -> f32 {
    var v = 0.0;
    var a = 0.5;
    var shift = vec2<f32>(100.0, 100.0);
    var pos = p;
    for (var i = 0; i < 4; i = i + 1) {
        v += a * noise2d(pos);
        pos = pos * 2.0 + shift;
        a *= 0.5;
    }
    return v;
}

@fragment
fn fs_main(in: VertexOutput) -> @location(0) vec4<f32> {
    let uv = in.uv;
    let aspect = u.resolution.x / u.resolution.y;
    // Map uv to centered coordinates where (+Y is up, -Y is down)
    let p = vec2<f32>((uv.x - 0.5) * aspect, 0.5 - uv.y);

    let t = u.time * 0.45 + u.seed * 0.19;

    // --- 1. Nocturnal Sky Gradient ---
    let sky_top = vec3<f32>(0.010, 0.022, 0.048);
    let sky_horizon = vec3<f32>(0.035, 0.065, 0.110);
    var color = mix(sky_horizon, sky_top, clamp(p.y * 1.6 + 0.3, 0.0, 1.0));

    // --- 2. Nocturnal Moon & Soft Radial Glow (Top Right) ---
    let moon_pos = vec2<f32>(0.25 * aspect, 0.32);
    let moon_dist = length(p - moon_pos);
    let moon_r = 0.068;
    
    // Moon Atmospheric Radial Glow
    let moon_halo = exp(-moon_dist * 13.0) * 0.32;
    color += vec3<f32>(0.75, 0.88, 0.98) * moon_halo;

    // Moon Disc & Crater Textures
    if (moon_dist < moon_r) {
        let moon_uv = (p - moon_pos) / moon_r;
        let crater_n = fbm2d(moon_uv * 4.2 + 15.7);
        let moon_surf = mix(0.72, 0.96, crater_n);
        let edge_aa = smoothstep(moon_r, moon_r - 0.0035, moon_dist);
        let moon_col = vec3<f32>(0.88, 0.94, 1.0) * moon_surf;
        color = mix(color, moon_col, edge_aa * 0.94);
    }

    // --- 3. Horizontal Cloud Strata & Nocturnal Wisps ---
    let cloud_y1 = sin(p.y * 25.0 + fbm2d(vec2<f32>(p.x * 3.0 + t * 0.04, p.y * 8.0)) * 2.0) * 0.5 + 0.5;
    let cloud_mask1 = smoothstep(0.55, 0.85, cloud_y1) * smoothstep(0.1, 0.45, p.y);
    color += vec3<f32>(0.06, 0.09, 0.15) * cloud_mask1 * 0.40;

    let cloud_y2 = fbm2d(vec2<f32>(p.x * 2.5 + t * 0.06, p.y * 5.0 + 8.2));
    let cloud_mask2 = smoothstep(0.42, 0.70, cloud_y2) * smoothstep(-0.05, 0.35, p.y);
    color += vec3<f32>(0.04, 0.07, 0.12) * cloud_mask2 * 0.35;

    // --- 4. Ocean Horizon & Rolling Waves (p.y < -0.10) ---
    let horizon_y = -0.10;
    if (p.y < horizon_y) {
        let sea_depth = clamp((horizon_y - p.y) * 2.6, 0.0, 1.0);
        
        let wave_x = p.x * 16.0 + t * 1.6;
        let wave_y = (horizon_y - p.y) * 60.0;
        let wave_1 = sin(wave_x + sin(wave_y * 0.4 + t * 1.1)) * 0.5 + 0.5;
        let wave_2 = cos(p.x * 32.0 - t * 2.2 + wave_y * 0.8) * 0.5 + 0.5;
        let wave_foam = pow(wave_1 * wave_2, 3.2) * (0.14 + 0.32 * sea_depth);

        let deep_sea = vec3<f32>(0.006, 0.016, 0.038);
        let surface_sea = vec3<f32>(0.020, 0.048, 0.088);
        var sea_col = mix(surface_sea, deep_sea, sea_depth);

        // Specular Moon Glint on Wave Surface
        let moon_refl_x = abs(p.x - moon_pos.x);
        let moon_glint = exp(-moon_refl_x * 8.0) * wave_1 * (1.0 - sea_depth * 0.45) * 0.35;
        sea_col += vec3<f32>(0.72, 0.88, 1.0) * moon_glint;

        // Foam highlights with cyan accent
        sea_col += u.accent_color * wave_foam * 0.35;
        color = sea_col;
    }

    // --- 5. Rocky Headland Cliff Silhouette (Bottom Left) ---
    // Smooth cliff curve from p.x in [-0.55*aspect, -0.05*aspect]
    let cliff_curve = -0.10 + smoothstep(0.0, -0.40 * aspect, p.x) * 0.32 + fbm2d(vec2<f32>(p.x * 8.0, 5.1)) * 0.035;
    let is_cliff = p.y < cliff_curve && p.x < -0.02 * aspect;
    if (is_cliff) {
        color = vec3<f32>(0.006, 0.009, 0.014);
    }

    // --- 6. Lighthouse Tower Body on Cliff ---
    let lh_x = -0.22 * aspect;
    let lh_base_y = 0.12; // Base of tower on cliff ledge
    let lh_top_y = 0.42;  // Height of tower

    if (p.y >= lh_base_y && p.y <= lh_top_y) {
        let prog = (p.y - lh_base_y) / (lh_top_y - lh_base_y);
        let half_w = mix(0.040, 0.024, prog);
        let dx = abs(p.x - lh_x);
        if (dx < half_w) {
            let band = step(0.5, fract(prog * 5.0));
            let tower_col = mix(vec3<f32>(0.009, 0.013, 0.020), vec3<f32>(0.018, 0.025, 0.038), band);
            color = tower_col;
        }
    }

    // Lantern Room & Gallery Railing
    let lantern_y = lh_top_y + 0.035;
    let lantern_r = 0.026;
    let gallery_w = 0.036;
    // Gallery Balcony Platform
    if (abs(p.y - lh_top_y) < 0.006 && abs(p.x - lh_x) < gallery_w) {
        color = vec3<f32>(0.008, 0.012, 0.018);
    }
    // Lantern Room Dome
    if (length(p - vec2<f32>(lh_x, lantern_y)) < lantern_r) {
        color = vec3<f32>(0.010, 0.016, 0.025);
    }

    // --- 7. Volumetric Rotating Beacon Beam ---
    let lamp_origin = vec2<f32>(lh_x, lantern_y);
    let beam_angle = t * 1.6;
    let beam_dir = vec2<f32>(cos(beam_angle), sin(beam_angle) * 0.22 - 0.04);
    
    let to_pixel = p - lamp_origin;
    let dist_to_lamp = length(to_pixel);
    let norm_to_pixel = normalize(to_pixel);
    
    let beam_alignment = dot(norm_to_pixel, beam_dir);
    if (beam_alignment > 0.70 && dist_to_lamp > 0.015 && dist_to_lamp < 1.7) {
        let cone_intensity = pow(smoothstep(0.70, 0.995, beam_alignment), 2.4);
        let dist_falloff = exp(-dist_to_lamp * 1.7);
        let beam_dust = fbm2d(p * 9.0 + vec2<f32>(t * 0.25, 0.0)) * 0.3 + 0.7;
        
        let beam_glow = cone_intensity * dist_falloff * beam_dust * 0.52;
        let beam_col = mix(u.accent_color, vec3<f32>(1.0, 0.96, 0.82), 0.65);
        color += beam_col * beam_glow;
    }

    // Lamp Core Flare & Glint
    let flare_facing = pow(max(0.0, sin(beam_angle)), 4.0);
    let flare_dist = length(p - lamp_origin);
    let flare = exp(-flare_dist * 45.0) * (0.35 + 0.65 * flare_facing);
    color += vec3<f32>(1.0, 0.96, 0.82) * flare * 0.65;

    // --- 8. Film Grain & Vignette ---
    let grain = (hash21(in.position.xy + vec2<f32>(t * 80.0, 0.0)) - 0.5) * 0.022;
    color += vec3<f32>(grain);

    let d_center = length(uv - vec2<f32>(0.5, 0.5));
    let vignette = 1.0 - smoothstep(0.38, 0.88, d_center) * 0.40;
    color *= vignette;

    color = clamp(color, vec3<f32>(0.0), vec3<f32>(0.85));

    return vec4<f32>(color, 1.0);
}
