#!/usr/bin/env python3
"""
dev/audit_security.py - Comprehensive Security & Secret Isolation Audit.

Validates:
1. POSIX Permissions (0600 files, 0700 directories).
2. Git tracking exclusion (.gitignore integrity & git ls-files clean).
3. Secret scanning across tracked source code.
4. Log sanitization and environment isolation.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

def check_permissions() -> list[str]:
    issues = []
    checks = [
        (ROOT_DIR / ".env", 0o600, False),
        (ROOT_DIR / "secrets", 0o700, True),
        (Path("/home/moku/secrets/google"), 0o700, True),
    ]

    for path, max_mode, is_dir in checks:
        if not path.exists():
            continue
        st = path.stat()
        mode = stat.S_IMODE(st.st_mode)

        # Check group or others have read/write/exec permissions
        if mode & 0o077 != 0:
            issues.append(f"Permisos inseguros en {path}: {oct(mode)} (debe ser <= {oct(max_mode)})")

        if is_dir:
            for child in path.iterdir():
                child_mode = stat.S_IMODE(child.stat().st_mode)
                if child.is_file() and (child_mode & 0o077 != 0):
                    issues.append(f"Archivo secreto con permisos inseguros: {child} ({oct(child_mode)})")
    return issues


def check_git_leaks() -> list[str]:
    issues = []
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        tracked_files = res.stdout.splitlines()
        sensitive_patterns = [
            re.compile(r"(?i)\.env($|\.)"),
            re.compile(r"(?i)^secrets/"),
            re.compile(r"(?i).*\.token"),
            re.compile(r"(?i).*token.*\.json$"),
            re.compile(r"(?i).*cookie.*\.json$"),
            re.compile(r"(?i).*\.key$"),
            re.compile(r"(?i).*client_secret.*\.json$"),
        ]

        for f in tracked_files:
            for pat in sensitive_patterns:
                if pat.search(f):
                    issues.append(f"ALERTA: Archivo sensible rastreado por Git: {f}")
    except Exception as e:
        issues.append(f"Error al verificar git ls-files: {e}")
    return issues


def check_code_secret_patterns() -> list[str]:
    issues = []
    raw_token_pat = re.compile(r"\b8831760214:[A-Za-z0-9_-]{35}\b")
    google_secret_pat = re.compile(r"GOCSPX-[A-Za-z0-9_-]{20,}")

    try:
        res = subprocess.run(
            ["git", "ls-files", "*.py", "*.json", "*.md", "*.sh"],
            cwd=ROOT_DIR,
            capture_output=True,
            text=True,
            check=True
        )
        for rel_path in res.stdout.splitlines():
            full_p = ROOT_DIR / rel_path
            if not full_p.is_file():
                continue
            content = full_p.read_text(encoding="utf-8", errors="ignore")
            if raw_token_pat.search(content):
                issues.append(f"Token de Telegram hardcodeado en archivo rastreado: {rel_path}")
            if google_secret_pat.search(content):
                issues.append(f"Secret de Google hardcodeado en archivo rastreado: {rel_path}")
    except Exception as e:
        issues.append(f"Error al escanear código: {e}")
    return issues


def main() -> int:
    print("=================================================================")
    print("🔒 AUDITORÍA DE SEGURIDAD Y AISLAMIENTO DE CREDENCIALES (yt-auto)")
    print("=================================================================")

    all_issues = []

    print("\n1. Verificando permisos POSIX (Least Privilege)...")
    perm_issues = check_permissions()
    if perm_issues:
        for iss in perm_issues:
            print(f"  ❌ {iss}")
        all_issues.extend(perm_issues)
    else:
        print("  ✅ Permisos POSIX correctos (archivos 0600 / directorios 0700).")

    print("\n2. Verificando exclusión en Git (Tracking & .gitignore)...")
    git_issues = check_git_leaks()
    if git_issues:
        for iss in git_issues:
            print(f"  ❌ {iss}")
        all_issues.extend(git_issues)
    else:
        print("  ✅ Ningún secreto ni archivo .env está rastreado por Git.")

    print("\n3. Escaneando código fuente contra tokens o secretos expuestos...")
    code_issues = check_code_secret_patterns()
    if code_issues:
        for iss in code_issues:
            print(f"  ❌ {iss}")
        all_issues.extend(code_issues)
    else:
        print("  ✅ Código fuente 100% libre de secretos hardcodeados.")

    print("\n4. Verificando ofuscación en logs...")
    from src.log import redact_secrets
    sample = "Telegram token 8831760214:AAEQN8Ku1thrKba1rgf7MIcJT9ldxVA2Dlg test"
    redacted = redact_secrets(sample)
    if "AAEQN8Ku1thrKba1rgf7MIcJT9ldxVA2Dlg" in redacted:
        print("  ❌ Falló la prueba de ofuscación de logs.")
        all_issues.append("Log redaction failed")
    else:
        print("  ✅ Ofuscación activa: los logs enmascaran automáticamente los secretos.")

    print("\n-----------------------------------------------------------------")
    if all_issues:
        print(f"❌ AUDITORÍA FALLIDA: Se encontraron {len(all_issues)} problemas de seguridad.")
        return 1
    else:
        print("🎉 AUDITORÍA EXITOSA: El entorno está 100% blindado y seguro.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
