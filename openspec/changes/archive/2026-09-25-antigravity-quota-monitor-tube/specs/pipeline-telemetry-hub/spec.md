# Specification: Pipeline Telemetry Hub

## Capability Overview
The `pipeline-telemetry-hub` capability establishes a unified operational observability collector ("El Tubo") for `yt-auto`. It gathers real-time host resource metrics (CPU, RAM, filesystem storage), daemon heartbeat liveness, channel execution controls, active concurrency worker locks, and external API circuit breaker states into a consolidated, zero-overhead telemetry snapshot (`TubeSnapshot`).

## Requirements

### Requirement 1: Host Resource Observability and Headroom Budget Enforcement
The system SHALL sample host CPU utilization, process Resident Set Size (RSS) memory, and volume disk free headroom without spawning external processes or daemon containers, strictly verifying compliance with resource policy constraints ($\le 2.0$ CPU cores and $\le 2.0$ GiB RAM budget per REG-14, and $\ge 2.0$ GiB free storage).

1. The sampling routine SHALL measure CPU utilization percentage and current process RSS memory in MiB and GiB in $< 2\text{ ms}$ wall-clock time using `/proc` filesystem telemetry or `psutil`.
2. The sampling routine SHALL measure available storage space on the active workspace / output disk partition and assert that free space remains $\ge 2.0\text{ GiB}$.
3. When RSS memory exceeds $2.0\text{ GiB}$ ($2048\text{ MiB}$) or free disk drops below $2.0\text{ GiB}$, the telemetry collector SHALL mark resource status as `DEGRADED` or `CRITICAL`.

#### Scenario: Real-time sampling of healthy host resources within budget
- **Given** a host environment where the current process RSS is $450\text{ MiB}$ and available disk space is $15.5\text{ GiB}$
- **When** the telemetry collector samples host resources
- **Then** the collector MUST report status `OK`
- **And** `ram_rss_mib` MUST be recorded accurately
- **And** sampling latency MUST NOT exceed $5\text{ ms}$.

#### Scenario: Detecting RAM budget overrun or storage headroom starvation
- **Given** a host environment where process RSS reaches $2.1\text{ GiB}$ or free disk space drops to $1.2\text{ GiB}$
- **When** the telemetry collector samples host resources
- **Then** the resource status MUST be reported as `CRITICAL` or `DEGRADED`
- **And** the telemetry snapshot MUST include clear diagnostic headroom warnings.

---

### Requirement 2: Daemon Liveness and Heartbeat Stoppage Detection
The telemetry hub SHALL monitor daemon heartbeat timestamps recorded in `daemon_liveness` via `read_daemon_heartbeat()` to determine autonomous scheduler liveness.

1. If the elapsed duration since the last recorded heartbeat is $\le 60\text{ seconds}$, the daemon liveness state SHALL be reported as `HEALTHY`.
2. If the elapsed duration since the last recorded heartbeat is $> 60\text{ seconds}$ and $\le 120\text{ seconds}$, the daemon liveness state SHALL be reported as `DEGRADED`.
3. If the elapsed duration since the last recorded heartbeat is $> 120\text{ seconds}$, the daemon liveness state SHALL be reported as `STALE` (or `HALTED`).
4. If no heartbeat record exists (`heartbeat_at = 0`), the daemon liveness state SHALL be reported as `STOPPED`.

#### Scenario: Daemon heartbeat within normal execution cycle (Happy Path)
- **Given** a daemon process actively updating `daemon_liveness` where `heartbeat_at` was written $15\text{ seconds}$ ago
- **When** daemon liveness is evaluated by the telemetry collector
- **Then** liveness status MUST be `HEALTHY`
- **And** `heartbeat_age_seconds` MUST evaluate to approximately $15$.

#### Scenario: Daemon heartbeat exceeding 60-second threshold (Degraded State)
- **Given** a daemon process whose last heartbeat update was recorded $75\text{ seconds}$ ago
- **When** daemon liveness is evaluated by the telemetry collector
- **Then** liveness status MUST be `DEGRADED`
- **And** the collector MUST flag the scheduler cycle as delayed.

#### Scenario: Daemon heartbeat exceeding 120-second threshold (Stale/Halted State)
- **Given** a daemon process that terminated abruptly with the last heartbeat recorded $180\text{ seconds}$ ago
- **When** daemon liveness is evaluated by the telemetry collector
- **Then** liveness status MUST be `STALE`
- **And** the snapshot MUST report the scheduler as stopped or unresponsive.

---

### Requirement 3: Channel Controls and Worker Concurrency Lock Monitoring
The telemetry hub SHALL inspect channel operational flags in `channel_controls` and active worker concurrency leases in `leases` and `lane_leases`.

1. The collector SHALL query `channel_controls` to detect any channel where `paused = 1`, extracting the associated `reason` and `updated_at` timestamp.
2. The collector SHALL query active worker locks from `leases` and `lane_leases`, extracting active `owner`, `run_id`, `lane_id` or `channel`, `acquired_at`, and `expires_at`.
3. The collector SHALL identify expired or orphaned worker locks where `expires_at < current_epoch_seconds` that have not yet been reclaimed.
4. Channel stoppages and active leases SHALL be consolidated into a structured summary for operational presentation.

#### Scenario: Querying paused channel controls and active lane leases
- **Given** channel `drama` is paused in `channel_controls` with reason `"Maintenance window"`
- **And** lane `horror-scp-shorts` is actively leased by worker `worker-pod-1` with run ID `run-987`
- **When** channel stoppages and active leases are collected
- **Then** `paused_channels` MUST contain `{"channel": "drama", "reason": "Maintenance window", "paused": True}`
- **And** `active_locks` MUST list `horror-scp-shorts` assigned to `worker-pod-1` with run ID `run-987`
- **And** expired locks MUST be zero if lease expiration is in the future.

#### Scenario: Identifying orphaned or expired worker locks
- **Given** a lane lease in `lane_leases` with `expires_at` in the past ($t - 45\text{s}$)
- **When** the lock state is analyzed by the collector
- **Then** the lock MUST be categorized as `ORPHANED` or `EXPIRED`
- **And** the snapshot MUST flag the lease as pending recovery.

---

### Requirement 4: External API Circuit Breaker State Aggregation
The telemetry hub SHALL inspect the real-time circuit breaker status across all integrated external AI and platform APIs (Antigravity Pro, Gemini REST, Grok, TTS routers, and YouTube uploaders).

1. The collector SHALL query circuit breaker states (`CLOSED`, `OPEN`, `HALF_OPEN`) from registered `CircuitBreaker` instances.
2. For circuit breakers in the `OPEN` state, the collector SHALL calculate the remaining cooldown duration (`retry_after()` in seconds) and failure count.
3. The snapshot SHALL aggregate all tripped circuit breakers, marking the overall system integration health as `DEGRADED` whenever any breaker is in the `OPEN` state.

#### Scenario: All provider circuit breakers in closed healthy state (Happy Path)
- **Given** all provider circuit breakers (`antigravity`, `gemini`, `grok`, `tts`, `youtube`) are in state `CLOSED`
- **When** circuit breaker telemetry is gathered
- **Then** `circuit_breakers` MUST list all providers with state `CLOSED`
- **And** `tripped_count` MUST equal 0.

#### Scenario: Provider circuit breaker tripped open due to consecutive failures
- **Given** the Gemini REST circuit breaker has tripped to `OPEN` following 5 consecutive 5xx errors with cooldown remaining of 42 seconds
- **When** circuit breaker telemetry is gathered
- **Then** the Gemini circuit breaker MUST report state `OPEN`
- **And** `retry_after_seconds` MUST report 42
- **And** the aggregate integration health status MUST be reported as `DEGRADED`.
