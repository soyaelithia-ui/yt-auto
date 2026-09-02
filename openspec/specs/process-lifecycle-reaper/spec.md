# Specification: Process Lifecycle Reaper

## Capability Overview
The `process-lifecycle-reaper` capability provides a safety net against orphaned child processes (such as FFmpeg or worker subprocesses) during fatal interpreter crashes or `SIGKILL` events. It is a lightweight, `atexit`-registered module that tracks active child PIDs and forces termination at shutdown if they remain running.

## Requirements

### Requirement 1: PID Registration and Tracking
The reaper MUST provide thread-safe mechanisms to register and unregister spawned child process PIDs.

#### Scenario: Registering a new child process (Happy Path)
- **Given** an initialized reaper module
- **When** a media render module spawns a new FFmpeg or worker process
- **Then** the module MUST register the process PID with the reaper
- **And** the PID MUST be stored in the reaper's active tracking set.

#### Scenario: Deregistering a cleanly exited process (Happy Path)
- **Given** a child process PID currently tracked by the reaper
- **When** the child process completes normally and its `wait()` returns
- **Then** the caller MUST unregister the PID
- **And** the reaper MUST remove the PID from its active tracking set.

### Requirement 2: Orphan Sweeping on Interpreter Exit
The reaper MUST automatically activate during Python interpreter shutdown and sweep all remaining registered PIDs.

#### Scenario: Sweeping orphaned processes at exit (Edge Case)
- **Given** an interpreter shutdown event triggered by a fatal error
- **When** the `atexit` callback executes
- **Then** the reaper MUST iterate through all currently registered PIDs
- **And** the reaper MUST send a `SIGTERM` followed by a `SIGKILL` to each PID to ensure termination.

#### Scenario: Sweeping a PID that has already terminated (Edge Case)
- **Given** a registered PID that has terminated externally without being unregistered
- **When** the reaper attempts to kill the process during shutdown
- **Then** the OS-level `OSError` or `ProcessLookupError` MUST be caught and suppressed
- **And** the reaper MUST proceed to the next PID without interrupting the shutdown sequence.

### Requirement 3: Scoped PID Ownership Verification
The reaper SHOULD ensure it only attempts to terminate processes that belong to the current application session, minimizing risks of killing unrelated system processes.

#### Scenario: Attempting to kill PID with mismatched ownership (Error State)
- **Given** a registered PID that was recycled by the OS for a different application
- **When** the reaper attempts to terminate the PID at shutdown
- **Then** the reaper SHOULD perform a sanity check (e.g., process group or command name) before sending signals
- **And** the reaper MUST NOT terminate the unrelated process if the check fails.
