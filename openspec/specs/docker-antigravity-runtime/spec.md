# Docker Antigravity Runtime Specification

## Purpose

The `docker-antigravity-runtime` capability defines container runtime specifications for executing Google Antigravity agents in Docker using the official CLI installer (`curl -fsSL https://antigravity.google/cli/install.sh`) and Python SDK with non-root security boundaries (`USER 10001:10001`), read-only root filesystems, volume isolation, and clean session persistence for Antigravity Pro quota consumption. This specification eliminates all host binary staging scripts (`scripts/stage_agy.sh`) and host OAuth token scraping dependencies, ensuring fully hermetic, self-contained container deployments across CI/CD and production environments.

## Requirements

### Requirement: Self-Contained Container Image Build With Official Installer
The container image MUST install the Antigravity CLI directly during build via the official installation script (`curl -fsSL https://antigravity.google/cli/install.sh | bash -s -- --dir /usr/local/bin`) and declared Python dependencies (`requirements.txt`) without relying on host staging scripts (`scripts/stage_agy.sh`) or staged ELF binaries (`build/agy`). The container image MUST NOT require a host copy step (`COPY build/agy`).

#### Scenario: Clean Docker Image Build With Official Installer (Happy Path)
- **Given** a clean workspace checkout where `build/agy` does not exist and `scripts/stage_agy.sh` has not been executed
- **When** `docker compose build` or `docker build` is executed against the Dockerfile
- **Then** the build MUST succeed and install `agy` directly to `/usr/local/bin/agy` from the official installer endpoint
- **And** the build MUST install Python dependencies from `requirements.txt`.

#### Scenario: Staging Script Absence Does Not Invalidate Build (Edge Case)
- **Given** a build environment where `scripts/stage_agy.sh` has been removed
- **When** automated build or linting checks evaluate container build prerequisites
- **Then** the build verification MUST complete without errors indicating missing staging scripts or missing ELF binaries.

#### Scenario: Ephemeral CI/CD Environment Construction (Edge Case)
- **Given** a headless CI/CD runner lacking local host binaries at `/home/moku/.local/bin/agy`
- **When** the container image is built from source
- **Then** the image build MUST complete cleanly with exit code 0
- **And** the binary `/usr/local/bin/agy` MUST be executable and report its version.

---

### Requirement: Non-Root Execution and Volume Isolation
The containerized application MUST execute under an unprivileged non-root user and group (`USER 10001:10001`, named `appuser`). The container root filesystem SHOULD be mounted read-only during production operation, and filesystem write operations MUST be confined to designated writable paths and mounted named volumes (`/tmp`, `/app/data`, `/app/output`, and `/home/appuser/.gemini`). The container environment MUST NOT require write access to system binary directories (`/usr/local/bin`, `/bin`, `/usr/bin`).

#### Scenario: Daemon Executes and Writes to Designated Named Volumes (Happy Path)
- **Given** a container instance initialized from `docker-compose.yml`
- **When** the application daemon executes scheduled video generation workflows
- **Then** the runtime process UID and GID MUST both evaluate to `10001`
- **And** database writes to `/app/data` and video rendering writes to `/app/output` MUST succeed.

#### Scenario: Unauthorized Write to Root or Binary Paths Denied (Edge Case)
- **Given** a container running under UID `10001`
- **When** a process attempts to create, modify, or delete files in `/usr/local/bin` or the container root `/`
- **Then** the filesystem operation MUST be denied with an access or read-only filesystem error
- **And** container isolation boundaries MUST remain unbreached.

#### Scenario: Service Identity in Compose Configuration (Happy Path)
- **Given** service definitions in `docker-compose.yml`
- **When** container user directives are inspected
- **Then** all worker and channel services MUST execute under unprivileged non-root identity.

---

### Requirement: Antigravity Pro Quota Harness Execution and Clean Session Governance
Agent interactions MUST primarily execute through the Antigravity CLI harness (`agy`) to consume the user's Antigravity Pro subscription quota (`gemini-3.8-flash-high`) without raw API billing. The container MUST persist the user's legitimate CLI session via the dedicated volume mount (`yt_agy_home:/home/appuser/.gemini`). The system MUST NOT attempt to scrape, reverse-engineer, or read client credentials from compiled binaries, and MUST NOT use `docker cp` injection scripts (`scripts/lib/antigravity_auth.py`).

#### Scenario: Pro Quota Harness Invocation via CLI (Happy Path)
- **Given** an authenticated Antigravity Pro session mounted in `/home/appuser/.gemini`
- **When** `ProgrammaticAgent` executes a prompt (for story curation or SEO optimization)
- **Then** the agent MUST invoke `/usr/local/bin/agy` using the persistent session
- **And** consume Pro subscription quota without incurring API key billing
- **And** return structured responses adhering strictly to the caller's target schema.

#### Scenario: Container Execution With Volume Mounted Session (Happy Path)
- **Given** a deployment environment where `yt_agy_home` contains valid session credentials
- **When** the container daemon starts
- **Then** `agy` CLI commands MUST authenticate seamlessly using the mounted session
- **And** no binary scraping or manual token manipulation scripts MUST be executed.

#### Scenario: Graceful Handling of Unauthenticated State (Edge Case)
- **Given** an unauthenticated container session where Pro credentials are not yet initialized
- **When** `ProgrammaticAgent` runs a task
- **Then** the agent MUST log an actionable diagnostic error indicating re-login instructions
- **And** gracefully trigger procedural narrative fallback without halting the daemon.

---

### Requirement: Entrypoint Permissions and Health Validation
The container entrypoint script (`scripts/docker_entrypoint.sh`) MUST validate that `/usr/local/bin/agy` is installed and executable, ensure essential application paths (`/app/data`, `/app/output`, `/home/appuser/.gemini`, `/tmp`) exist and are writable by UID `10001`, and ensure non-root execution.

#### Scenario: Entrypoint Successfully Launches Daemon on Valid Permissions (Happy Path)
- **Given** a container starting up with writable volume mounts and `/usr/local/bin/agy` present
- **When** `scripts/docker_entrypoint.sh` executes
- **Then** directory write permissions MUST be successfully validated
- **And** the application daemon process MUST be started under UID `10001`.

#### Scenario: Entrypoint Terminates on Missing Binary (Edge Case)
- **Given** a corrupted image where `/usr/local/bin/agy` is missing or not executable
- **When** `scripts/docker_entrypoint.sh` executes
- **Then** the entrypoint MUST print an explicit error to stderr and exit with code 1.

#### Scenario: Entrypoint Terminates on Unwritable Required Volume (Edge Case)
- **Given** a container configuration where `/app/data` is mounted read-only or owned by an incompatible UID
- **When** `scripts/docker_entrypoint.sh` executes pre-flight checks
- **Then** the script MUST detect the unwritable path
- **And** print an explicit diagnostic error message to stderr
- **And** exit with a non-zero exit code before launching the daemon.
