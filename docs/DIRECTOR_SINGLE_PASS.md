# Director: local asset sequence

The director lane is now an editorial selector, not a graphics renderer.

- Stage 4 selects local video resources from the catalog for each narrative act.
- Stages 8–9 build and compose the manifest through `LoopVideoEngine`.
- Matching local videos use stream-copy concat (`-c:v copy`); audio and soft subtitles are muxed separately.
- No Ken Burns/zoompan, runtime HUD, SVG, raster overlay, drawtext, drawbox, or generated video frame is allowed.
- `DIRECTOR_XFADE`, `MULTIACT_XFADE`, and `DIRECTOR_SINGLE_PASS` are retired and must not be used to alter production output.

Thumbnail generation is independent: `LocalAIThumbnailBank` resolves a locally generated image and `ThumbnailEngine` applies only bounded color grading. Text is never printed into the thumbnail.
