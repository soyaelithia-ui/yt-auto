# Delta Specification: Media Pipeline Hardening

## Capability Overview
The `media-pipeline-hardening` capability governs the lifecycle, execution safety, and streaming architecture of FFmpeg/FFprobe operations across all audio synthesis, DSP mixing, and multi-act visual compositing engines.

## Added Requirements

### Requirement 5: Exception Guards for Direct Popen Chains
All media render modules (including `proc_engine.py`, `subtitles.py`, `stream_renderer.py`, and `web_renderer.py`) MUST wrap dual `subprocess.Popen` pipe chains and browser sessions in robust `try/finally` blocks to ensure cleanup on exceptions.

#### Scenario: Clean execution of dual Popen chain (Happy Path)
- **Given** a successful rendering operation involving two piped `Popen` subprocesses
- **When** the rendering completes without exceptions
- **Then** the `finally` block MUST safely invoke `wait()` on the processes
- **And** the processes MUST terminate cleanly without leaking resources.

#### Scenario: Exception during browser and FFmpeg processing (Edge Case)
- **Given** an active rendering session involving an FFmpeg `Popen` process and an open browser
- **When** an unexpected exception occurs during the render loop
- **Then** the `finally` block MUST execute
- **And** it MUST explicitly invoke `kill()` and `wait()` on the FFmpeg subprocess
- **And** it MUST invoke `close()` on the browser instance before propagating the exception.

#### Scenario: Cleanup failure during exception handling (Error State)
- **Given** an exception occurred in the render loop triggering the `finally` cleanup block
- **When** the `kill()` or `close()` operations themselves raise an exception (e.g., process already dead)
- **Then** the cleanup block MUST suppress these secondary cleanup exceptions
- **And** the original render loop exception MUST be correctly re-raised to the caller.
