# FFmpeg low-CPU defaults

The production hot path uses local videos and stream-copy composition.

## Rules

1. `LoopVideoEngine` prioritizes concat-demuxer `-c:v copy` for local assets with matching geometry.
2. Audio and optional soft subtitles are muxed without regenerating video frames.
3. Runtime graphics, zoompan, HUD/SVG/raster overlays, procedural shaders, Pillow frame loops, and browser rendering are retired.
4. `RENDER_PRESET`, `RENDER_CRF`, and `FFMPEG_THREADS` remain available for the rare local compatibility re-encode or QA fallback.
5. Catalog integrity and visual QA remain fail-closed; missing or uncertified local assets do not trigger remote downloads or generated video frames.

Helpers: `src/media/encode_defaults.py` and `src/media/loop_engine.py`.
See `docs/visual-assets-policy.md` for the asset boundary.
