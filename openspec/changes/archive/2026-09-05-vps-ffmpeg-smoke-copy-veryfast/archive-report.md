# Archive Report: vps-ffmpeg-smoke-copy-veryfast

**Change Name**: `vps-ffmpeg-smoke-copy-veryfast`
**Archived To**: `openspec/changes/archive/2026-09-05-vps-ffmpeg-smoke-copy-veryfast/`
**Archive Date**: `2026-09-05`
**Status**: Closed & Shipped (intentional-with-warnings: live VPS argv capture remains an operator step)

---

## 1. Executive Summary

Shipped a fail-closed FFmpeg hot-path smoke parser (`src/media/ffmpeg_hot_path_smoke.py`) and CLI (`scripts/smoke_ffmpeg_hot_path.sh`) that require live argv evidence of stream-copy on the cheap path and `veryfast` + CRF 21 on unavoidable re-encodes. The change MUST NOT modify compositor, proc_engine, or pipeline.

---

## 2. Specs Synced to Source of Truth

| Domain | Action | Details |
|--------|--------|---------|
| `ffmpeg-hot-path-smoke` | Created | Mechanical copy of full spec to `openspec/specs/ffmpeg-hot-path-smoke/spec.md` (4 requirements, 9 scenarios). Source vs temp copy `diff -r` empty. |

Change-folder mechanical `diff -r` vs archive destination: empty (byte-identical).

---

## 3. Tasks Reconciliation

- **Total Implementation Tasks**: 9
- **Completed Tasks**: 9 (100%)
- **Pending / Unchecked Tasks**: 0
- **Task Completion Gate**: Passed.
- **state.yaml**: created at archive time with `status: completed`, `current_phase: archive` (the active folder had no `state.yaml`).

---

## 4. Verification Proof

- **verify-report**: verdict `pass_with_warnings`; 0 CRITICAL; 4/4 requirements; 9/9 scenarios; 8/8 unit tests at verification time.
- **Warnings (final state)**: fail-closed look-PR block is process (CLI exit 1), not an automated SDD latch; live VPS argv capture remains an operator step. These are non-critical and do not block archive.

---

## 5. Archived Artifacts Manifest

- `proposal.md`
- `design.md`
- `tasks.md`
- `verify-report.md`
- `state.yaml`
- `specs/ffmpeg-hot-path-smoke/spec.md`

---

## 6. SDD Cycle Complete

The change has been planned, implemented, verified, and archived. Ready for the next change.
