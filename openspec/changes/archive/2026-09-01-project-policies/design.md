# Design: Unified Architecture & Policy Framework (yt-auto v3.1)

## Architecture Overview

```mermaid
flowchart TD
    subgraph P1_Editorial["1. Editorial & Content Policy"]
        E1[Curator Agent - Gemini 3.7 Flash] --> E2[Sanitizer & 3-Sec Hook Guard]
        E2 --> E3[Anti-Filler Pure Procedural WebGL/Three.js]
        E3 --> E4[CC BY-SA 3.0 Attribution Injector]
    end

    subgraph P2_Audio_DSP["2. Audio DSP & Performance Policy"]
        E4 --> A1[TTSRouter Multi-Tier Fallback]
        A1 --> A2[Volatile /dev/shm Temp Allocation]
        A2 --> A3[Single-Pass EBU R128 Mastering -14 LUFS]
        A3 --> A4[Pillow Font Geometry Auto-Wrapping 260px Safe Area]
    end

    subgraph P3_Persistence_Reaper["3. Concurrency & Data Integrity Policy"]
        A4 --> D1[LoopVideoEngine Canonical Master 1080x1920]
        D1 --> D2[SQLite WAL Mode busy_timeout=30000]
        D3[LeaseReaper Active PID Daemon os.kill] -.-> D2
    end

    subgraph P4_Publishing_Review["4. Operational & Publishing Policy"]
        D2 --> R1[Telegram Review Bot 2x2 Inline Keyboards]
        R1 -->|Approved| R2[DBReconciler 2PC Atomic Coordinator]
        R2 --> R3[SessionHealthValidator <48h Expiration Check]
        R3 --> R4[SessionUploader Zero-Quota Direct Publish]
    end
```

## Architectural Decisions & Tradeoffs

### Decision 1: Direct Session Publication over YouTube Data API v3
- **Rationale**: YouTube Data API v3 enforces a strict daily quota of 10,000 units (~6 video uploads max). Massive production multi-lane automation requires unconstrained publishing capabilities. Authenticated session cookies (Playwright / InnerTube) eliminate this bottleneck.
- **Tradeoff**: Session cookies require monitoring for expiration (`LOGIN_INFO`, `SAPISID`). Handled via proactive `SessionHealthValidator` warning when $<48\text{h}$ remaining.

### Decision 2: 2PC Dual-Database Reconciliation Adapter
- **Rationale**: `shorts_queue.db` (worker production) and `review_state.db` (human editorial) operate as separate SQLite WAL databases. Independent non-transactional writes risk duplicate YouTube uploads or orphan approval states on transient network failure.
- **Tradeoff**: Minimal coordination overhead during the approval phase; resolved through synchronous `BEGIN IMMEDIATE` locks and verified `run_id` idempotency.

### Decision 3: Active PID Lease Reaper over Passive TTL Timeout
- **Rationale**: Workers that crash unexpectedly (OOM, SIGKILL) leave lane leases locked until the 900-second TTL expires, stalling pipeline lanes for 15 minutes.
- **Tradeoff**: Background daemon executes `os.kill(pid, 0)` every 30 seconds, immediately detecting dead worker PIDs and releasing leases in $<35$ seconds with zero CPU churn.
