# `_legacy` quarantine (native_procedural / wgpu)

**Status:** quarantined. Not production.

- SSOT: FFmpeg (beats stream-copy / director zoompan) + Pillow thumbnails.
- `native_procedural.py` + `shaders/` remain for historical / opt-in experiments only.
- Production modules (`pipeline`, `compositor`, `loop_worker`, `hybrid_engine`, `proc_engine`)
  must not import this package unless `ENABLE_NATIVE_PROCEDURAL=1`.
- Default: `ENABLE_NATIVE_PROCEDURAL=0`.

The public shim `src/media/native_procedural.py` re-exports with a DEPRECATED
guard so accidental hot-path imports fail closed without the opt-in flag.
