# Enable cookie-first uploads and automatic marked-video purge

## Goal
Keep production stopped until rebuilt, then let the daemon delete only database records explicitly marked `MARKED_FOR_PURGE` when the YouTube control API becomes available again.

## Tasks
- [x] Enable cookie-first runtime configuration and uploader routing.
- [x] Verify focused uploader tests and configuration resolution.
- [x] Add bounded automatic purge of marked videos with ownership checks and quota stop behavior.
- [x] Wire the purge into maintenance sweeps and container configuration.
- [x] Verify, rebuild the image, and leave the container stopped.

## Evidence
- `purge_marked_videos` now verifies channel ownership before each delete and stops on quota/rate-limit failures.
- Maintenance sweeps process `MARKED_FOR_PURGE` in batches controlled by `AUTO_PURGE_MARKED_BATCH_SIZE` (default 50), retrying on the next sweep.
- Focused tests: 24 passed.
- Docker image rebuilt and `yt-automation` recreated with `--no-start`; status is `Created`, not running.

## Constraints
- Preserve existing staged graphics changes and current main commit.
- Never expose or modify cookie secret contents.
- Delete only rows already marked `MARKED_FOR_PURGE`.
- Stop the batch on quota/auth/rate-limit errors; retry on the next maintenance sweep.
