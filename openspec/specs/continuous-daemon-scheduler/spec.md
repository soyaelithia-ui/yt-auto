# Specification: Continuous Daemon Scheduler

## Capability Overview
The `continuous-daemon-scheduler` capability manages the 24/7 autonomous continuous execution lifecycle for video generation pipelines. It enforces 64-bit SimHash narrative deduplication, bounded concurrency semaphores to prevent GPU/RAM exhaustion, automatic post-render scratch cleanup with disk watermark guards, and resilient liveness monitoring with exponential backoff.

## Requirements

### Requirement 1: 64-Bit SimHash Narrative Deduplication
The scheduler MUST compute a 64-bit SimHash fingerprint over generated script text and narrative concepts before initiating rendering. The scheduler MUST reject any candidate script whose 64-bit Hamming distance to any previously generated script within a rolling history window ($\ge 100$ items) is strictly less than 4 bits ($Hamming < 4$), triggering automated narrative regeneration.

#### Scenario: Unique script passes 64-bit SimHash deduplication check (Happy Path)
- **Given** a newly synthesized script with narrative content distinct from existing database records
- **When** the scheduler evaluates the 64-bit SimHash against the database history
- **Then** the calculated minimum Hamming distance MUST be $\ge 4$ bits
- **And** the scheduler MUST accept the script for rendering and record its SimHash in the repository.

#### Scenario: Duplicate or near-identical script rejected by SimHash guard (Edge Case)
- **Given** a newly generated script that shares 95% semantic token overlap with a script generated 2 hours prior
- **When** SimHash deduplication executes and yields a Hamming distance of 2 bits ($< 4$)
- **Then** the scheduler MUST reject the duplicate script
- **And** the scheduler MUST log a duplicate rejection event and request a fresh narrative generation.

### Requirement 2: Bounded Concurrency Semaphore and Workload Throttling
The scheduler MUST limit concurrent video rendering and GPU/FFmpeg tasks through a bounded concurrency semaphore (default limit $N = 1$ for heavy rendering, $N \le 2$ for light synthesis). The scheduler MUST NOT launch unbounded concurrent subprocesses that exceed system RAM or GPU VRAM limits.

#### Scenario: Bounded execution of queued render jobs (Happy Path)
- **Given** 4 video generation jobs waiting in the processing queue and a semaphore limit of 1
- **When** the scheduler processes the queue
- **Then** exactly 1 render job MUST execute actively at any given time
- **And** subsequent jobs MUST wait until the active task releases the semaphore upon completion.

#### Scenario: High concurrency job arrival during peak GPU utilization (Edge Case)
- **Given** an active rendering job occupying the execution semaphore
- **When** an urgent or scheduled trigger arrives
- **Then** the scheduler MUST enqueue the request without spawning parallel FFmpeg encoders
- **And** system memory and VRAM utilization MUST remain within safe operational bounds.

### Requirement 3: Post-Render Temporary Artifact Sweeper and Disk Guard
The scheduler and cleanup subsystem MUST sweep all intermediate scratch assets (uncompressed raw frames, intermediate WAV files, temporary subtitle files) immediately upon successful render completion or run failure. Additionally, the scheduler MUST enforce a minimum free disk space watermark ($5.0\text{ GB}$). If free disk capacity drops below the floor, the daemon MUST pause processing and emit operational alerts.

#### Scenario: Automatic post-render scratch cleanup (Happy Path)
- **Given** a completed video render that generated 3.2 GB of temporary frame buffers and audio stems in `work/`
- **When** post-render execution finishes
- **Then** the cleaner MUST remove all temporary intermediate files tagged with the `run_id`
- **And** the final master MP4 in the artifact repository MUST remain intact.

#### Scenario: Pipeline crash or unexpected exception during multi-act rendering (Edge Case)
- **Given** a rendering job that raises an unhandled exception or terminates prematurely
- **When** the scheduler handles the error
- **Then** the cleanup routine MUST execute in a `finally` block to sweep partial scratch files
- **And** the disk space MUST NOT accumulate orphaned rawvideo buffers.

### Requirement 4: Uninterrupted 24/7 Autonomous Daemon Lifecycle and Liveness Watchdog
The continuous daemon MUST run in an autonomous loop with non-blocking heartbeat updates, graceful shutdown handling on `SIGINT`/`SIGTERM`, and automatic recovery from transient exceptions via exponential backoff with jitter. The daemon MUST alert operators if heartbeat latency exceeds stale thresholds ($> 600\text{s}$).

#### Scenario: Continuous autonomous loop with periodic heartbeat (Happy Path)
- **Given** the daemon running in continuous mode with a 60-second polling interval
- **When** each iteration completes
- **Then** the daemon MUST touch the liveness heartbeat in the database
- **And** the loop MUST proceed to the next iteration without manual operator intervention.

#### Scenario: Consecutive transient network or API failures (Edge Case)
- **Given** 3 consecutive network failures or rate-limit errors during pipeline execution
- **When** the error breaker evaluates the consecutive failure counter
- **Then** the daemon MUST enter exponential backoff with randomized jitter
- **And** the daemon process MUST remain alive and resume processing once connectivity is restored.
