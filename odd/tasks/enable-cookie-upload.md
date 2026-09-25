# Enable cookie-first YouTube uploads

## Goal
Route production YouTube uploads through authenticated session cookies before any Data API attempt, while preserving explicit API-only behavior.

## Tasks
- [x] Add cookie-first runtime configuration and uploader routing.
- [x] Run focused uploader regression coverage and verify configuration resolution.

## Evidence
- `docker-compose.yml` sets `PREFER_SESSION_UPLOAD` to `1` by default; API remains fallback.
- `src/youtube/uploader/__init__.py` tries the existing InnerTube/Playwright cookie flow before API for normal uploads.
- `.venv/bin/python -m pytest -q tests/unit/test_youtube_uploader.py` — 36 passed.
- `git diff --check` — passed.

## Constraints
- Preserve existing staged graphics changes.
- Do not expose or modify cookie secret contents.
- Keep `api_only=True` as an explicit Data API escape hatch.
