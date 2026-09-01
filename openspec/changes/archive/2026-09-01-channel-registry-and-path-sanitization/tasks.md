# Tasks: Dynamic Channel Registry & Path Sanitization

## Review Workload Forecast
Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: stacked-to-main
400-line budget risk: Low

## Phase 1: Dynamic Channel Domain Resolution (TDD RED -> GREEN)
- [x] 1.1 [TDD-RED] Add unit tests in `tests/unit/test_channel_domain_dynamic.py`:
  - Test `canonical_channel("scifi")` succeeds and returns `"scifi"`.
  - Test `canonical_channel()` with custom channel in `config/channels/`.
  - Test `canonical_channel("invalid_ch_xyz")` raises `ValueError`.
  - Test legacy aliases (`terror`, `aita`, `scp`) resolve properly.
- [x] 1.2 [TDD-GREEN] Refactor `src/core/domain.py` `canonical_channel()`:
  - Dynamically query `ChannelProfileRegistry.list_active_channel_ids()` when an input is not in the static alias map.
  - Avoid circular imports via lazy resolution.
- [x] 1.3 [TDD-GREEN] Refactor `src/config.py` `RuntimeSettings.channel()`:
  - Dynamically load `ChannelProfile` from `ChannelProfileRegistry` when a channel key is not in `self.channels`.
  - Convert `ChannelProfile` into compatible `ChannelSettings` on the fly.
- [x] 1.4 Verify `pytest tests/unit/test_channel_domain_dynamic.py tests/unit/test_branding.py` passes.

## Phase 2: Path Sanitization in Tests & Docker (TDD RED -> GREEN)
- [x] 2.1 [TDD-GREEN] Sanitize `tests/unit/test_audio_quality.py`:
  - Replace `/home/Moku/projects/YTShort/work/scp_SCP-087/scp-087_final.mp4` with a dynamic synthetic audio/video path using `tmp_path`.
- [x] 2.2 [TDD-GREEN] Sanitize `tests/unit/test_media_integrity.py`:
  - Replace `/home/Moku/projects/YTShort/...` references with `tmp_path` fixtures.
- [x] 2.3 [TDD-GREEN] Sanitize `docker-compose.yml`:
  - Replace `/home/mvfhymyhqw/.local/bin/agy` with `/usr/local/bin/agy`.
- [x] 2.4 Verify `pytest tests/unit/test_audio_quality.py tests/unit/test_media_integrity.py` passes.

## Phase 3: Full Regression Verification
- [x] 3.1 Run complete unit test suite (`pytest tests/unit`) to confirm 100% pass rate.
- [x] 3.2 Verify no foreign hardcoded paths remain.
