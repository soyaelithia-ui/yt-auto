# Media Processing and Performance Policy Specification (Delta)

## Purpose
Codifies operational resource governance and concurrency semaphores during multi-lane daemon execution. Updates `Hard Target Resource Ceiling Governance (2 Cores CPU, 2.0 GiB RAM)` to mandate strict global rendering semaphores (`_SHORT_RENDER_SEMAPHORE = 2`, `_LONG_RENDER_SEMAPHORE = 1`), bounding total multi-lane daemon execution strictly within $\le 2$ CPU Cores ($\le 200\%$) and $\le 2.0\text{ GiB RAM}$ ($2,048\text{ MiB}$ peak RSS).

## MODIFIED Requirements

### Requirement: Hard Target Resource Ceiling Governance (2 Cores CPU, 2.0 GiB RAM)
(Previously: Enforced the hard target operational ceiling of $\le 2.0$ CPU Cores and $\le 2.0\text{ GiB}$ RAM across individual renders and probe tasks, but did not mandate explicit global concurrency semaphores to partition parallel Short and Longform renders during continuous multi-lane daemon execution)

In strict accordance with Section 5 of `AGENTS.md` and anti-regression invariant `REG-14`, all media processing workflows, pipeline stages, and multi-lane autonomous daemon engines MUST operate within an inviolable hard target operational ceiling of:
- **CPU Aggregate Target**: $\le 2.0$ CPU Cores ($\le 200\%$ aggregate CPU utilization across all active threads and subprocesses).
- **RAM Resident Target**: $\le 2.0$ GiB RAM ($2,048\text{ MiB}$ peak resident memory RSS).

To prevent concurrent media rendering operations from exceeding the resource envelope during multi-lane daemon execution, rendering tasks MUST be strictly partitioned by global thread semaphores:
1. **Short Renders Semaphore**: `_SHORT_RENDER_SEMAPHORE = threading.Semaphore(2)`. At most two concurrent vertical Short renders (`image_animation` or vertical re-encode) MAY execute simultaneously.
2. **Longform Renders Semaphore**: `_LONG_RENDER_SEMAPHORE = threading.Semaphore(1)`. At most one horizontal longform render (`horror-horror-long`, `drama-aita-long`, `scifi-singularity-long`) MAY execute concurrently. Concurrent or parallel longform renders are STRICTLY PROHIBITED.

The multi-lane daemon worker thread pool capacity MUST NOT exceed 3 concurrent workers (`YT_MAX_PARALLEL_LANES=3`). Total aggregate CPU utilization across all concurrent lanes and subprocesses MUST NOT exceed $200\%$ (2 Cores), and peak aggregate resident memory MUST NOT exceed $2,048\text{ MiB}$ (2.0 GiB RAM).

All FFmpeg subprocess invocations MUST bound thread execution with `-threads 2` for audio mastering, loudness probes, and QA checks, and at most `-threads 4` during video encoding passes. Probes MUST specify `-vn` to skip decoding video frame data into memory.

Resource consumption MUST follow the monotonic optimization directive: usage MUST only decrease or remain stable, never climbing across commits. If any multi-lane execution or architectural feature breaches the 2 Cores / 2.0 GiB RAM ceiling, the system MUST trigger the Resource Work Refusal policy to halt and optimize the implementation before deployment.

#### Scenario: Multi-lane concurrent render execution bounded by semaphores (Happy Path)
- **Given** a multi-lane daemon running with up to 3 concurrent worker threads across shorts and longform lanes
- **When** video composition stages are reached across multiple lanes simultaneously
- **Then** Short renders MUST acquire a token from `_SHORT_RENDER_SEMAPHORE` (capacity 2)
- **And** Longform renders MUST acquire a token from `_LONG_RENDER_SEMAPHORE` (capacity 1)
- **And** aggregate CPU utilization across all concurrent lanes MUST NOT exceed 2.0 Cores (200%)
- **And** peak aggregate resident memory (RSS) MUST NOT exceed 2,048 MiB.

#### Scenario: Longform render serialization via single-token semaphore (Happy Path)
- **Given** an active horizontal longform render executing `horror-horror-long` holding `_LONG_RENDER_SEMAPHORE`
- **When** a second horizontal longform render (`drama-aita-long`) initiates composition
- **Then** the second longform render MUST block waiting for the semaphore token
- **And** zero concurrent horizontal longform renders MUST execute in parallel.

#### Scenario: Short render concurrency capped at two tokens (Happy Path)
- **Given** two vertical Short renders actively executing and occupying both tokens of `_SHORT_RENDER_SEMAPHORE`
- **When** a third vertical Short render attempts to start video composition
- **Then** the third Short render MUST block until one of the active renders releases its semaphore token
- **And** at most 2 Short renders MUST execute concurrently.

#### Scenario: Probe operations enforce low-CPU thread bounding (Happy Path)
- **Given** an invocation of `ffprobe` or audio loudness analysis on media assets
- **When** the probe command is constructed
- **Then** it MUST specify `-threads 2`
- **And** it MUST specify `-vn` to skip decoding video frame data into memory.

#### Scenario: Resource work refusal on budget breach (Edge Case)
- **Given** a prospective media composition pipeline or multi-lane configuration that consumes $> 2.0$ Cores or $> 2.0$ GiB RAM
- **When** anti-regression guardrail or performance benchmarks run
- **Then** the test suite MUST fail with a resource target violation
- **And** automated agents MUST refuse to merge the change until optimized.
