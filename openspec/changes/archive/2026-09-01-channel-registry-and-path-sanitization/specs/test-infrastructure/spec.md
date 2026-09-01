# Specification: Test Infrastructure Path Sanitization

## Capability Overview
The `test-infrastructure` capability guarantees test hermeticity, isolation, and portability by eliminating foreign hardcoded filesystem paths from test suites and deployment manifests.

## Requirements

### Requirement 1: Dynamic Fixture Paths in Unit Tests
Unit tests testing media integrity and audio quality MUST use temporary mock directories (`tmp_path`) or repository-anchored paths rather than hardcoded foreign paths (such as `/home/Moku/...`).

#### Scenario: Running media integrity tests in isolated workspace (Happy Path)
- **Given** a test runner running in any execution environment
- **When** `pytest tests/unit/test_audio_quality.py` or `pytest tests/unit/test_media_integrity.py` executes
- **Then** the tests MUST locate or generate test fixtures dynamically
- **And** MUST NOT fail due to missing external developer directories.

### Requirement 2: Docker Compose Binary Path Fallbacks
The Docker Compose orchestration manifest MUST use container-safe default paths for binaries and secrets without embedding foreign usernames.

#### Scenario: Inspecting docker-compose.yml configuration (Happy Path)
- **Given** `docker-compose.yml`
- **When** the file is parsed by Docker Compose
- **Then** all volume mounts MUST reference environment variables with generic fallbacks (e.g. `${AGY_BINARY_PATH:-/usr/local/bin/agy}`).
