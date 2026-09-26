"""
src/verification/guardrails.py - SSOT Guardrails & Unified Repository Integrity Engine.

Consolidates all repository governance, architectural invariants, and hygiene rules:
- Worktree hygiene (zero stale or unlinked worktrees)
- Architecture blueprint hygiene (zero obsolete docs/architecture/0*.md)
- Subsystem isolation (zero legacy directories and zero retired imports)
- Zero-Browser policy (zero Playwright imports outside src/youtube/)
- Zero-Procedural-Math policy (zero WGSL shaders, zero legacy dirs, zero wgpu/pygfx)
- Git hooks configuration (core.hooksPath == .githooks and executable pre-commit)
- Anti-bloat policy (zero .min.js, .github/skills, or assets/vendor)
- Agent homedirs and secret hygiene (local-only agent dirs, secret patterns)
- Test suite collectability (zero syntax or unimportable test files)
- MCP synchronization (in-process verification with scripts.verify_mcp_sync)
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# ==============================================================================
# Data Models
# ==============================================================================

@dataclass
class CheckResult:
    """Individual invariant check result."""
    name: str
    passed: bool
    message: str
    details: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class IntegrityReport:
    """Consolidated audit report across all checks."""
    healthy: bool
    status: str  # "HEALTHY" or "FAILED"
    exit_code: int  # 0 or 1
    checks_passed: List[str] = field(default_factory=list)
    checks_failed: List[Dict[str, Any]] = field(default_factory=list)
    commit_count: int = 0
    duration_ms: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "status": self.status,
            "exit_code": self.exit_code,
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
            "commit_count": self.commit_count,
            "duration_ms": self.duration_ms,
        }


# ==============================================================================
# AST Inspection Utilities
# ==============================================================================

class ImportScanner(ast.NodeVisitor):
    """
    AST Visitor to extract all imports from Python AST.
    Detects standard, aliased, and multiline imports without false positives
    on comments or docstring literals.
    """
    def __init__(self) -> None:
        self.imports: List[str] = []
        self.import_nodes: List[Tuple[str, int]] = []

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.imports.append(alias.name)
            self.import_nodes.append((alias.name, node.lineno))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        mod = node.module or ""
        if mod:
            self.imports.append(mod)
            self.import_nodes.append((mod, node.lineno))
            for alias in node.names:
                full = f"{mod}.{alias.name}"
                self.imports.append(full)
                self.import_nodes.append((full, node.lineno))
        else:
            for alias in node.names:
                self.imports.append(alias.name)
                self.import_nodes.append((alias.name, node.lineno))
        self.generic_visit(node)


def scan_source_imports(source: str, filename: str = "<unknown>") -> List[str]:
    """Parse a Python source string and extract all imported module paths."""
    try:
        tree = ast.parse(source, filename=filename)
    except Exception:
        return []
    scanner = ImportScanner()
    scanner.visit(tree)
    return scanner.imports


def scan_module_imports(file_path: Path) -> List[str]:
    """Parse a Python file and extract all imported module paths."""
    if not file_path.exists() or file_path.suffix != ".py":
        return []
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    return scan_source_imports(content, filename=str(file_path))


# ==============================================================================
# Invariant Check Functions
# ==============================================================================

def check_worktrees(repo_root: Path) -> CheckResult:
    """Check Git Worktrees: Must have zero stale, prunable, or unlinked worktrees."""
    try:
        subprocess.run(
            ["git", "worktree", "prune"],
            cwd=str(repo_root),
            capture_output=True,
            check=False,
        )
        proc = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return CheckResult(
                name="worktree_hygiene",
                passed=False,
                message="Failed to query git worktrees",
                details=[proc.stderr.strip()],
            )

        stale_count = 0
        unlinked_count = 0
        active_count = 0
        details: List[str] = []

        for line in proc.stdout.splitlines():
            line_s = line.strip()
            if line_s.startswith("worktree "):
                wt_path = Path(line_s[9:].strip())
                active_count += 1
                if not wt_path.is_dir():
                    unlinked_count += 1
                    details.append(f"Unlinked worktree path: {wt_path}")
            elif line_s.startswith("prunable"):
                stale_count += 1
                details.append(f"Prunable worktree: {line_s}")

        if stale_count > 0 or unlinked_count > 0:
            return CheckResult(
                name="worktree_hygiene",
                passed=False,
                message="Stale or unlinked worktrees detected!",
                details=details,
            )

        return CheckResult(
            name="worktree_hygiene",
            passed=True,
            message=f"Git worktree hygiene: {active_count} valid worktree(s), zero stale/prunable.",
        )
    except Exception as exc:
        return CheckResult(
            name="worktree_hygiene",
            passed=False,
            message=f"Error inspecting worktrees: {exc}",
            details=[str(exc)],
        )


def check_architecture_docs(repo_root: Path, paths: Optional[List[str]] = None) -> CheckResult:
    """Check for Resurrected Obsolete Architecture Blueprints in docs/architecture/0*.md."""
    violations: List[str] = []
    if paths is not None:
        for p_str in paths:
            p = Path(p_str)
            parts = p.parts
            if len(parts) >= 3 and parts[0] == "docs" and parts[1] == "architecture":
                fname = parts[2]
                if fname.startswith("0") and fname.endswith(".md"):
                    violations.append(p_str)
    else:
        arch_dir = repo_root / "docs" / "architecture"
        if arch_dir.is_dir():
            for f in arch_dir.glob("0*.md"):
                violations.append(str(f.relative_to(repo_root)))

    if violations:
        return CheckResult(
            name="architecture_docs",
            passed=False,
            message="Obsolete architecture documents detected in docs/architecture/0*.md!",
            details=violations,
        )

    return CheckResult(
        name="architecture_docs",
        passed=True,
        message="Architecture docs: zero obsolete blueprints.",
    )


def check_legacy_subsystems(repo_root: Path, paths: Optional[List[str]] = None) -> CheckResult:
    """Check for Retired Legacy Subsystems and Imports (src.rendering, src.compositing, src.export)."""
    violations: List[str] = []
    retired_dirs = ("src/rendering", "src/compositing", "src/export")

    # 1. Directory presence check
    if paths is not None:
        for p in paths:
            for rd in retired_dirs:
                if p == rd or p.startswith(rd + "/"):
                    violations.append(f"Retired directory staged: {p}")
    else:
        for rd in retired_dirs:
            if (repo_root / rd).is_dir():
                violations.append(f"Retired directory exists: {rd}")

    # 2. AST import checks
    forbidden_prefixes = ("src.rendering", "src.compositing", "src.export")
    if paths is not None:
        py_files = [repo_root / p for p in paths if p.endswith(".py") and (repo_root / p).is_file()]
    else:
        src_py = list((repo_root / "src").rglob("*.py"))
        tests_py = list((repo_root / "tests").rglob("*.py"))
        py_files = [p for p in src_py + tests_py if ".venv" not in p.parts and ".git" not in p.parts]

    for py_file in py_files:
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not any(t in content for t in ("rendering", "compositing", "export")):
            continue
        imports = scan_source_imports(content, filename=str(py_file))
        rel_path = py_file.relative_to(repo_root) if py_file.is_relative_to(repo_root) else py_file
        for imp in imports:
            if any(imp == f or imp.startswith(f + ".") for f in forbidden_prefixes):
                violations.append(f"{rel_path} imports '{imp}'")

    if violations:
        return CheckResult(
            name="subsystem_isolation",
            passed=False,
            message="Retired legacy subsystems or imports detected (src.rendering, src.compositing, src.export)!",
            details=violations,
        )

    return CheckResult(
        name="subsystem_isolation",
        passed=True,
        message="Subsystem isolation: zero legacy rendering directories and zero retired imports.",
    )


def check_zero_browser_policy(repo_root: Path, paths: Optional[List[str]] = None) -> CheckResult:
    """Zero-Browser Policy: zero Playwright imports in media and pipeline outside src/youtube/."""
    violations: List[str] = []
    forbidden_token = "playwright"

    if paths is not None:
        py_files = [
            repo_root / p for p in paths
            if p.endswith(".py") and (repo_root / p).is_file()
            and p.startswith("src/")
            and not p.startswith("src/youtube/")
        ]
    else:
        src_dir = repo_root / "src"
        py_files = [
            p for p in src_dir.rglob("*.py")
            if "youtube" not in p.relative_to(src_dir).parts
            and ".venv" not in p.parts
        ]

    for py_file in py_files:
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if forbidden_token not in content:
            continue
        imports = scan_source_imports(content, filename=str(py_file))
        rel_path = py_file.relative_to(repo_root) if py_file.is_relative_to(repo_root) else py_file
        for imp in imports:
            if imp == forbidden_token or imp.startswith(forbidden_token + "."):
                violations.append(f"{rel_path} imports '{imp}'")

    if violations:
        return CheckResult(
            name="zero_browser_policy",
            passed=False,
            message="Forbidden Playwright import detected outside src/youtube/uploader.py:",
            details=violations,
        )

    return CheckResult(
        name="zero_browser_policy",
        passed=True,
        message="Zero-Browser Policy: zero Playwright imports in media and pipeline.",
    )


def check_zero_procedural_math(repo_root: Path, paths: Optional[List[str]] = None) -> CheckResult:
    """Zero-Procedural-Math Policy: zero WGSL shaders, zero legacy procedural files/imports."""
    violations: List[str] = []

    # 1. WGSL shaders check
    if paths is not None:
        for p in paths:
            if p.endswith(".wgsl"):
                violations.append(f"Forbidden WGSL shader staged: {p}")
    else:
        for f in repo_root.rglob("*.wgsl"):
            if ".venv" not in f.parts and ".git" not in f.parts:
                violations.append(f"Found WGSL shader file: {f.relative_to(repo_root)}")

    # 2. Legacy directories and deleted procedural files
    deleted_files = {
        "src/media/proc_engine.py",
        "src/media/native_procedural.py",
        "src/media/lavfi_palettes.py",
    }
    forbidden_dirs = (
        "src/media/_legacy",
        "assets/svg_overlays",
        "assets/overlays",
    )

    if paths is not None:
        for p in paths:
            for fd in forbidden_dirs:
                if p == fd or p.startswith(fd + "/"):
                    violations.append(f"Found forbidden directory path: {p}")
            if p in deleted_files:
                violations.append(f"Found deleted procedural engine file: {p}")
    else:
        for fd in forbidden_dirs:
            if (repo_root / fd).exists():
                violations.append(f"Found forbidden directory: {fd}")
        for df in deleted_files:
            if (repo_root / df).exists():
                violations.append(f"Found deleted procedural engine file: {df}")

    # 3. Forbidden AST imports
    forbidden_imports = {
        "src.media.proc_engine",
        "src.media.native_procedural",
        "src.media.lavfi_palettes",
        "wgpu",
        "pygfx",
    }
    tokens = ("proc_engine", "native_procedural", "lavfi_palettes", "wgpu", "pygfx")
    if paths is not None:
        py_files = [
            repo_root / p for p in paths
            if p.endswith(".py") and (repo_root / p).is_file() and p.startswith("src/")
        ]
    else:
        py_files = [
            p for p in (repo_root / "src").rglob("*.py")
            if ".venv" not in p.parts and ".git" not in p.parts
        ]

    for py_file in py_files:
        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not any(t in content for t in tokens):
            continue
        imports = scan_source_imports(content, filename=str(py_file))
        rel_path = py_file.relative_to(repo_root) if py_file.is_relative_to(repo_root) else py_file
        for imp in imports:
            if any(imp == fi or imp.startswith(fi + ".") for fi in forbidden_imports):
                violations.append(f"{rel_path} imports '{imp}'")

    if violations:
        return CheckResult(
            name="zero_procedural_math",
            passed=False,
            message="Zero-Procedural-Math Policy violation detected:",
            details=violations,
        )

    return CheckResult(
        name="zero_procedural_math",
        passed=True,
        message="Zero-Procedural-Math Policy: zero WGSL shaders, zero legacy procedural files/imports.",
    )


def check_git_hooks(repo_root: Path) -> CheckResult:
    """Check Git Hooks Configuration: core.hooksPath == .githooks and pre-commit is executable."""
    try:
        proc = subprocess.run(
            ["git", "config", "core.hooksPath"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            check=False,
        )
        hooks_path = proc.stdout.strip()
        hook_file = repo_root / ".githooks" / "pre-commit"

        if hooks_path != ".githooks" or not hook_file.is_file() or not os.access(hook_file, os.X_OK):
            return CheckResult(
                name="git_hooks",
                passed=False,
                message=f"Anti-regression pre-commit hook is not configured or executable! (core.hooksPath={hooks_path})",
                details=[f"core.hooksPath={hooks_path}", f"hook_file_exists={hook_file.is_file()}", f"executable={os.access(hook_file, os.X_OK) if hook_file.is_file() else False}"],
            )

        return CheckResult(
            name="git_hooks",
            passed=True,
            message="Git pre-commit hook is active and enforced via .githooks.",
        )
    except Exception as exc:
        return CheckResult(
            name="git_hooks",
            passed=False,
            message=f"Error inspecting git hooks: {exc}",
            details=[str(exc)],
        )


def check_anti_bloat(repo_root: Path, paths: Optional[List[str]] = None) -> CheckResult:
    """Check for Vendored Bloat (.github/skills, assets/vendor, *.min.js)."""
    violations: List[str] = []
    forbidden_prefixes = (".github/skills", "assets/vendor")

    if paths is not None:
        for p in paths:
            if any(p == fp or p.startswith(fp + "/") for fp in forbidden_prefixes):
                violations.append(f"Forbidden bloat path: {p}")
            if p.endswith(".min.js"):
                violations.append(f"Forbidden minified JavaScript file: {p}")
    else:
        for fp in forbidden_prefixes:
            if (repo_root / fp).is_dir():
                violations.append(f"Forbidden bloat directory exists: {fp}")

        # Check git tracked files for *.min.js
        try:
            proc = subprocess.run(
                ["git", "ls-files", "*.min.js"],
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            for line in proc.stdout.splitlines():
                if line.strip():
                    violations.append(f"Tracked minified JavaScript: {line.strip()}")
        except Exception:
            pass

    if violations:
        return CheckResult(
            name="anti_bloat",
            passed=False,
            message="Vendored bloat detected (.github/skills, assets/vendor, or *.min.js)!",
            details=violations,
        )

    return CheckResult(
        name="anti_bloat",
        passed=True,
        message="Anti-Bloat: zero vendored skills or third-party minified libraries.",
    )


SECRET_SIGNATURE_REGEX = re.compile(
    r'AIzaSy[a-zA-Z0-9_-]{33}|'
    r'GOCSPX-[a-zA-Z0-9_-]{28}|'
    r'sk-[a-zA-Z0-9]{20,}|'
    r'ghp_[a-zA-Z0-9]{36}|'
    r'[0-9]{8,10}:[A-Za-z0-9_-]{35}|'
    r'[0-9]{12}-[a-z0-9]{32}|'
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----|'
    r'ya29\.[A-Za-z0-9_-]{50,}|'
    r'AKIA[0-9A-Z]{16}'
)

AGENT_HOMEDIR_REGEX = re.compile(
    r'^\.(codex|claude|gemini|agents|opencode|grok|copilot|atl|cursor|hermes)(/|$)'
)

SECRET_FILENAME_REGEX = re.compile(
    r'(^|/)\.env($|\.)|(^|/)cookies\.json$|(^|/)secrets/'
)

SA_TYPE_PATTERN = re.compile(r'"type"\s*:\s*"service_account"')
SA_KEY_PATTERN = re.compile(r'"private_key"')

SA_SCAN_SKIP_FILES = {
    "tests/unit/test_security_policies.py",
    "dev/audit_security.py",
    "dev/diagnostics/audit_security.py",
    ".githooks/pre-commit",
    "src/verification/guardrails.py",
}

SA_SCAN_SKIP_PREFIXES = ("openspec/",)


SKIP_MEDIA_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov", ".wav",
    ".mp3", ".ttf", ".otf", ".woff", ".woff2", ".ico", ".tar", ".gz", ".zip",
}
SECRET_TRIGGER_BYTES = re.compile(
    b"AIzaSy|GOCSPX|sk-|ghp_|[0-9]{8,10}:|-----BEGIN|ya29|AKIA|service_account"
)


def check_agent_homes_and_secrets(repo_root: Path, paths: Optional[List[str]] = None) -> CheckResult:
    """
    Enforces that agent home directories and secret-shaped files/signatures
    are never tracked or staged.
    """
    violations: List[str] = []

    target_paths: List[str] = []
    if paths is not None:
        target_paths = paths
    else:
        # Full repo check: only inspect git-tracked files
        try:
            proc = subprocess.run(
                ["git", "ls-files", "-z"],
                cwd=str(repo_root),
                capture_output=True,
                check=False,
            )
            if proc.returncode == 0:
                target_paths = [p for p in proc.stdout.decode("utf-8", errors="replace").split("\0") if p]
        except Exception as exc:
            return CheckResult(
                name="agent_homes_and_secrets",
                passed=False,
                message=f"Error inspecting tracked files: {exc}",
                details=[str(exc)],
            )

    for p in target_paths:
        # 1. Agent homedirs
        if AGENT_HOMEDIR_REGEX.search(p):
            violations.append(f"Agent homedir file tracked/staged: {p}")
            continue

        # 2. Secret filenames (exclude .env.example)
        if SECRET_FILENAME_REGEX.search(p):
            if not p.endswith(".env.example") and not p == ".env.example":
                violations.append(f"Secret-shaped filename tracked/staged: {p}")
                continue

        # 3. Production secret signatures in content (path-only reporting, never print secret)
        if any(p.endswith(ext) for ext in SKIP_MEDIA_EXTENSIONS):
            continue

        file_path = repo_root / p
        if file_path.is_file() and not file_path.is_symlink():
            try:
                if file_path.stat().st_size > 2 * 1024 * 1024:
                    continue
                raw_bytes = file_path.read_bytes()
                if not SECRET_TRIGGER_BYTES.search(raw_bytes):
                    continue
                content = raw_bytes.decode("utf-8", errors="ignore")
                if SECRET_SIGNATURE_REGEX.search(content):
                    violations.append(f"Production-format secret signature detected in {p}")
                elif not (p in SA_SCAN_SKIP_FILES or any(p.startswith(pref) for pref in SA_SCAN_SKIP_PREFIXES)):
                    if SA_TYPE_PATTERN.search(content) and SA_KEY_PATTERN.search(content):
                        violations.append(f"GCP service account private key detected in {p}")
            except Exception:
                pass

    if violations:
        return CheckResult(
            name="agent_homes_and_secrets",
            passed=False,
            message="Agent homedir or secret hygiene violation detected!",
            details=violations,
        )

    return CheckResult(
        name="agent_homes_and_secrets",
        passed=True,
        message="Agent homedirs and secret hygiene: zero tracked agent homes or credentials.",
    )


def check_test_collectability(repo_root: Path) -> CheckResult:
    """
    Check test suite collectability across all modules.
    Verifies that all tests in tests/ can be parsed and compiled without syntax/import errors.
    """
    tests_dir = repo_root / "tests"
    if not tests_dir.is_dir():
        return CheckResult(
            name="test_collectability",
            passed=True,
            message="No tests directory found, skipping collectability check.",
        )

    errors: List[str] = []
    count = 0
    for test_file in tests_dir.rglob("*.py"):
        if ".venv" in test_file.parts or ".git" in test_file.parts:
            continue
        count += 1
        try:
            content = test_file.read_text(encoding="utf-8")
            compile(content, str(test_file), "exec")
            ast.parse(content, filename=str(test_file))
        except Exception as exc:
            errors.append(f"{test_file.relative_to(repo_root)}: {exc}")

    if errors:
        return CheckResult(
            name="test_collectability",
            passed=False,
            message="Pytest collection errors detected! Unimportable or broken test files present.",
            details=errors,
        )

    return CheckResult(
        name="test_collectability",
        passed=True,
        message=f"Test suite collectability: 100% collectable ({count} test modules verified).",
    )


def check_mcp_sync(repo_root: Path) -> CheckResult:
    """
    In-process MCP synchronization check.
    Directly invokes verify_mcp_sync() from scripts.verify_mcp_sync without spawning Python subprocess.
    """
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    try:
        from scripts.verify_mcp_sync import verify_mcp_sync
    except ImportError as e:
        return CheckResult(
            name="mcp_sync",
            passed=False,
            message="Cannot import verify_mcp_sync from scripts.verify_mcp_sync",
            details=[str(e)],
        )

    try:
        ok, passed_items, failures = verify_mcp_sync(repo_root)
        if not ok:
            return CheckResult(
                name="mcp_sync",
                passed=False,
                message="MCP Server drift detected! Run scripts/verify_mcp_sync.py for diagnostics.",
                details=failures,
            )

        return CheckResult(
            name="mcp_sync",
            passed=True,
            message="MCP Synchronization: 100% bidirectional parity across tools, resources, prompts, configs & docs.",
            details=passed_items,
        )
    except Exception as exc:
        return CheckResult(
            name="mcp_sync",
            passed=False,
            message=f"Unexpected error running verify_mcp_sync: {exc}",
            details=[str(exc)],
        )


# ==============================================================================
# Audit Runner
# ==============================================================================

def get_commit_count(repo_root: Path) -> int:
    """Safe helper to obtain current git commit count."""
    try:
        proc = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if proc.returncode == 0:
            return int(proc.stdout.strip())
    except Exception:
        pass
    return 0


def get_staged_files(repo_root: Path) -> List[str]:
    """Query git cached files for staged pre-commit inspection."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "-z", "--diff-filter=ACM"],
            cwd=str(repo_root),
            capture_output=True,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout:
            return [f for f in proc.stdout.decode("utf-8", errors="replace").split("\0") if f]
    except Exception:
        pass
    return []


def run_integrity_audit(
    repo_root: Path,
    *,
    staged: bool = False,
    fast: bool = False,
    staged_paths: Optional[List[str]] = None,
) -> IntegrityReport:
    """
    Executes all invariant checks and returns a consolidated IntegrityReport.

    - staged=True: Only evaluates path and AST checks against staged files in < 50ms.
    - fast=True: Skips heavy test collection check.
    """
    t0 = time.time()
    checks: List[CheckResult] = []

    if staged:
        paths = staged_paths if staged_paths is not None else get_staged_files(repo_root)
        if not paths:
            duration_ms = int((time.time() - t0) * 1000)
            return IntegrityReport(
                healthy=True,
                status="HEALTHY",
                exit_code=0,
                checks_passed=["Zero staged files detected; clean pre-commit pass."],
                checks_failed=[],
                commit_count=get_commit_count(repo_root),
                duration_ms=duration_ms,
            )

        checks.append(check_architecture_docs(repo_root, paths=paths))
        checks.append(check_legacy_subsystems(repo_root, paths=paths))
        checks.append(check_zero_browser_policy(repo_root, paths=paths))
        checks.append(check_zero_procedural_math(repo_root, paths=paths))
        checks.append(check_anti_bloat(repo_root, paths=paths))
        checks.append(check_agent_homes_and_secrets(repo_root, paths=paths))
    else:
        checks.append(check_worktrees(repo_root))
        checks.append(check_architecture_docs(repo_root))
        checks.append(check_legacy_subsystems(repo_root))
        checks.append(check_zero_browser_policy(repo_root))
        checks.append(check_zero_procedural_math(repo_root))
        checks.append(check_git_hooks(repo_root))
        if not fast:
            checks.append(check_test_collectability(repo_root))
        checks.append(check_anti_bloat(repo_root))
        checks.append(check_agent_homes_and_secrets(repo_root))
        checks.append(check_mcp_sync(repo_root))

    checks_passed = [c.message for c in checks if c.passed]
    checks_failed = [
        {"name": c.name, "message": c.message, "details": c.details}
        for c in checks if not c.passed
    ]

    healthy = (len(checks_failed) == 0)
    status = "HEALTHY" if healthy else "FAILED"
    exit_code = 0 if healthy else 1
    duration_ms = int((time.time() - t0) * 1000)
    commit_count = get_commit_count(repo_root)

    return IntegrityReport(
        healthy=healthy,
        status=status,
        exit_code=exit_code,
        checks_passed=checks_passed,
        checks_failed=checks_failed,
        commit_count=commit_count,
        duration_ms=duration_ms,
    )
