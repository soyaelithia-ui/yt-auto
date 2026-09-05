# Thumbnail quality samples (analog horror bar)

Branch: `feat/thumbs-analog-horror-quality` (worktree `nova-thumbs`).

Changes:
- New `src/media/thumbnails/analog_horror.py` (grain, CA, scanlines, cyan cast, crushed blacks, pixel OSD)
- Wired into `ChiaroscuroColorGrader.process_analog_horror`, `ThumbnailEngine` (moku/horror/scp), and design_* scripts

Samples for Yon → Aelithia (not production publish):
- `sample_scp_analog.jpg` — vertical SCP
- `sample_horror_analog.jpg` — horizontal creepypasta
- `sample_aita.jpg` — AITA unchanged path (control)

Ref bar: `/workspace/refs/aelithia_quality_ref.mp4`
