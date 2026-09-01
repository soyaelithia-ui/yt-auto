# Proposal: Project Operational, Editorial, and Architectural Policies (yt-auto v3.1)

## Problem Statement
While `yt-auto` has established modular code and pipeline stages, the project lacks a centralized, formal OpenSpec policy framework enforcing AI-first fail-closed governance, zero-quota direct session publishing, anti-filler pure procedural rendering standards, 2PC dual-database transactional integrity, and memory/RAM optimization constraints across all development and automated production workflows.

## Capabilities

### New Capabilities
- `editorial-and-content-policy`: Formal specification defining AI-First fail-closed narrative curation, 3-second hook retention rules, anti-filler procedural WebGL/Canvas rendering (zero static stock filler), and CC-BY-SA attribution compliance for lore ingestion.
- `operational-publishing-policy`: Formal specification governing zero-quota persistent session publishing via Playwright/InnerTube, automated cookie health monitoring (`SessionHealthValidator` <48h expiration threshold), and interactive Telegram human-in-the-loop review approvals.
- `concurrency-data-integrity-policy`: Formal specification enforcing two-phase commit (2PC) atomic reconciliation between `shorts_queue.db` and `review_state.db`, proactive dead-worker lease reaping via `os.kill(pid, 0)`, and SQLite WAL mode lock isolation.
- `media-processing-performance-policy`: Formal specification requiring RAM-based volatile audio temp allocation (`/dev/shm`), single-pass EBU R128 mastering (-14 LUFS / -1.5 dBTP), and dynamic Pillow font bounding box auto-wrapping with safe area margins.

### Modified Capabilities
- `service-health`: Integrated proactive session token lifecycle inspection with Telegram `/health` diagnostics.
- `youtube-publishing`: Refactored publishing hierarchy establishing direct session authentication as primary production path and Data API v3 as auxiliary metadata sync.

## Scope
- Establish comprehensive OpenSpec policy domain specifications in `openspec/specs/` and current change.
- Formalize editorial guidelines in `docs/` and agent system prompts.
- Enforce automated compliance checks for all four policy pillars across the testing harness.
- Provide clear operational runbooks for session rotation and incident remediation.

## Non-Scope
- Implementing manual interactive web forms for story curation (curation remains programmatic AI-driven).
- Supporting commercial third-party cloud render farms (pipeline remains deterministic on local/VPS compute).

## Rollback Plan
Policy specifications and enforcement wrappers can be updated or reverted via standard git version control without database schema migrations or destructive state modification.

## Performance Impact
RAM-based volatile I/O policies (`/dev/shm`) and single-pass FFmpeg mastering eliminate redundant SSD read/write cycles, cutting overall video composition latency by ~15-20%.
