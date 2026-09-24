# FFmpeg low-CPU defaults

Goal: near-zero resource on the default hot path (beats already stream-copy).

## Knobs (SSOT)

| Env | Default (compose) | Role |
|-----|-------------------|------|
| `RENDER_PRESET` | `veryfast` | x264 preset when a re-encode is unavoidable |
| `RENDER_CRF` | `21` | Quality target (≤22 with veryfast is YT-safe) |
| `FFMPEG_THREADS` | `4` | Cap encoder threads inside the cgroup |

Helpers: `src/media/encode_defaults.py` (`default_render_preset`, `default_render_crf`, `default_ffmpeg_threads`, `loop_matches_target_geometry`).

## Rules

1. **Stream-Copy en loops (`LoopVideoEngine`)**: Prioriza `-c:v copy` cuando los subtítulos no se incrustan en el video. Tanto `lib/video.py` como `LoopVideoEngine.ensure_h264_main_profile` admiten perfiles H.264 `Main` y `High` de forma nativa sin forzar re-codificación con `libx264`, permitiendo completar la composición en $\le 3$ segundos con uso mínimo de CPU.
2. **Re-encode paths** (vertical + libass, hybrid zoompan, multi-scene master): use `veryfast` + CRF 21 — **not** `slow` (CPU disaster) and **not** blind `ultrafast` on final delivers.
3. **Pillow / rawvideo frame loops**: Permanently purged from the video pipeline. Composition relies exclusively on pre-rendered assets and FFmpeg native filters (`zoompan` for Ken Burns).
4. **Catalog loop segments** (`LoopVideoEngine`): stream-copy trim (`-c:v copy`) via concat demuxer when `loop_matches_target_geometry` matches target resolution and no subtitles are burned.
5. **QA gating live fallbacks thread limiting contract (`-threads 2`)**: When analyzing uncertified media lacking precomputed manifest metrics, live FFmpeg fallback subprocesses (`detect_long_black_frames` and `analyze_perceptual_luminance` in `src/core/quality.py`) strictly enforce `-threads 2` immediately preceding `-i`. This caps CPU thread utilization and prevents 100% core spikes or host exhaustion on multi-core VPS environments.
6. **Certified catalog assets stream-copy & QA bypass guarantee**: Master video assets indexed in `assets/loops/bank_manifest.json` contain certified empirical visual metrics (`longest_black_seconds: 0.0` and `perceptual_luminance`). Prepublication validation (`validate_prepublication` in `src/core/quality.py`) detects `report.facts["black_source"] == "precomputed_visual"` and `report.facts["luminance_source"] == "precomputed_visual"`, bypassing CPU-heavy live frame decoding entirely (0 frames decoded). Coupled with `-c:v copy` muxing in `LoopVideoEngine` and `MultiSceneCompositor`, video delivery achieves near-zero CPU overhead.
7. **Post-publish disk reclamation**: Inmediatamente tras la confirmación de subida a YouTube (`PUBLISHED`) y respaldo en Drive, `delete_local_post_publication` elimina el archivo de video final `.mp4` y audios TTS (`.wav`/`.mp3`), asegurando que el host mantenga espacio libre y cero fugas de almacenamiento sin alterar los metadatos ligeros de auditoría.
8. **Target Resource Envelope (≤ 2 Cores CPU, ≤ 2.0 GiB RAM)**: El hot path de producción está dimensionado para operar bajo un techo objetivo de **≤ 2 CPU Cores** (≤ 200% de CPU agregada) y **≤ 2.0 GiB RAM** (2,048 MiB de memoria residente pico). Cualquier desarrollo o refactorización que aumente el consumo sostenido de recursos por encima de este umbral debe ser rechazado. Docker compose mantiene cgroups de seguridad más amplios (`cpus: 4.0`, `mem_limit: 6g`) solo para evitar terminaciones abruptas OOM en picos esporádicos, pero el software debe ceñirse al presupuesto de 2 Cores / 2 GB RAM.
9. **Multi-act stream-copy turnaround ceiling (≤ 45s)**: Longform horizontal video rendering with multiple thematic narrative acts must execute exclusively via stream-copy (`-c:v copy`), completing within a turnaround ceiling of ≤ 45s under the ≤ 2 CPU Cores and ≤ 2.0 GiB RAM budget.

## Guardrails

See `tests/unit/test_ffmpeg_low_cpu_defaults.py` and `tests/unit/test_anti_regression_guardrails.py`.

## Coordination with director single-pass (PR #11)

Catalog loop stream-copy / geometry logic in `LoopVideoEngine.render_scene_segment` is intentionally aligned with
`MultiSceneCompositor` single-pass assembly on `perf/director-single-pass-ffmpeg`, calling
`loop_matches_target_geometry` to guarantee zero-copy rendering without re-encoding overhead.
