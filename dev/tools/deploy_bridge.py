#!/usr/bin/env python3
"""
dev/tools/deploy_bridge.py - Bridge & Monitoring Controller between Dev and Deploy.

Allows monitoring, inspecting logs, syncing code fixes, and controlling services
in /home/moku/Deploy/YouTubeChannels directly from the development repository,
ensuring zero collision of resources, databases, or processes.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
DEPLOY_ROOT = Path("/home/moku/Deploy/YouTubeChannels")


def _run(cmd: list[str], cwd: Optional[Path] = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd or DEPLOY_ROOT),
        capture_output=True,
        text=True,
        check=check,
    )


def cmd_status(args: argparse.Namespace) -> int:
    print("=" * 70)
    print("🛰️  [DEPLOY BRIDGE] Estado del Entorno de Despliegue")
    print("=" * 70)
    print(f"📁 Directorio de Despliegue : {DEPLOY_ROOT}")
    print(f"📁 Directorio de Desarrollo : {REPO_ROOT}")

    if not DEPLOY_ROOT.is_dir():
        print("❌ ERROR: El directorio de despliegue no existe.")
        return 1

    # 1. Git Status & Commit Parity
    try:
        deploy_rev = _run(["git", "rev-parse", "--short", "HEAD"]).stdout.strip()
        dev_rev = _run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_ROOT).stdout.strip()
        print(f"🌿 Commit Despliegue       : {deploy_rev}")
        print(f"🌿 Commit Desarrollo       : {dev_rev}")
        if deploy_rev == dev_rev:
            print("  ✅ Paridad de versiones: Despliegue sincronizado con desarrollo.")
        else:
            print(f"  ⚠️  Divergencia de versiones: despliegue={deploy_rev}, dev={dev_rev}")
    except Exception as e:
        print(f"  ❌ Error consultando git: {e}")

    # 2. Production Healthcheck
    health_script = DEPLOY_ROOT / "healthcheck.py"
    py_bin = DEPLOY_ROOT / ".venv" / "bin" / "python"
    if health_script.is_file() and py_bin.is_file():
        print("\n🩺 Diagnóstico de Salud (healthcheck.py):")
        res = subprocess.run([str(py_bin), str(health_script)], cwd=str(DEPLOY_ROOT), capture_output=True, text=True)
        for line in res.stdout.splitlines():
            print(f"   {line}")
        if res.returncode == 0:
            print("  ✅ Todos los sistemas de producción operativos.")
        else:
            print(f"  ⚠️  Healthcheck reportó estado no óptimo (código {res.returncode})")

    # 3. Tmux Services Status
    ctl_script = DEPLOY_ROOT / "deploy" / "ctl.sh"
    if ctl_script.is_file():
        print("\n🎛️  Servicios Tmux (deploy/ctl.sh status):")
        res = subprocess.run([str(ctl_script), "status"], cwd=str(DEPLOY_ROOT), capture_output=True, text=True)
        for line in res.stdout.splitlines():
            print(f"   {line}")

    # 4. User Systemd Status
    print("\n⚙️  Units de Systemd de Usuario:")
    for unit in ("ytauto-lanes-daemon.service", "ytauto-review-bot.service"):
        res = subprocess.run(["systemctl", "--user", "is-active", unit], capture_output=True, text=True)
        state = res.stdout.strip() or "inactive"
        icon = "🟢" if state == "active" else "⚪"
        print(f"   {icon} {unit:<30}: {state}")

    print("=" * 70)
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    logs_dir = DEPLOY_ROOT / "logs"
    if not logs_dir.is_dir():
        print("❌ El directorio logs/ no existe en el despliegue.")
        return 1

    services = ["sched", "bot"] if args.service == "all" else [args.service]
    for svc in services:
        log_file = logs_dir / f"{svc}.out"
        print(f"\n📋 --- Logs de '{svc}' ({log_file}) [Últimas {args.lines} líneas] ---")
        if log_file.is_file():
            res = subprocess.run(["tail", "-n", str(args.lines), str(log_file)], capture_output=True, text=True)
            print(res.stdout or "(archivo vacío)")
        else:
            print("(no hay archivo de registro todavía)")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    print("🔄 [DEPLOY BRIDGE] Sincronizando código productivo hacia /home/moku/Deploy/YouTubeChannels...")
    if not DEPLOY_ROOT.is_dir():
        print("❌ Error: Directorio de despliegue no encontrado.")
        return 1

    try:
        # Fetch from local repo and fast-forward
        print("  1. Obteniendo últimos commits de desarrollo...")
        _run(["git", "fetch", str(REPO_ROOT), "main"])
        _run(["git", "merge", "--ff-only", "FETCH_HEAD"])

        # Re-apply sparse checkout to ensure all required components exist
        print("  2. Verificando sparse-checkout...")
        _run([
            "git", "sparse-checkout", "set",
            "src", "config", "schemas", "deploy", "lib", "review",
            "assets", "main.py", "manage.py", "healthcheck.py",
            "requirements.txt", "constraints.txt", ".env.example",
        ])

        # Apply database migrations if any
        py_bin = DEPLOY_ROOT / ".venv" / "bin" / "python"
        if py_bin.is_file():
            print("  3. Ejecutando migraciones de esquema SQLite...")
            res = subprocess.run([str(py_bin), "main.py", "migrate"], cwd=str(DEPLOY_ROOT), capture_output=True, text=True)
            print(f"     {res.stdout.strip()}")

        print("🎉 [Sincronización completada con éxito].")
        return 0
    except subprocess.CalledProcessError as e:
        print(f"❌ Error durante la sincronización: {e.stderr or e.stdout}")
        return 1


def cmd_ctl(args: argparse.Namespace) -> int:
    ctl_script = DEPLOY_ROOT / "deploy" / "ctl.sh"
    if not ctl_script.is_file():
        print("❌ Error: deploy/ctl.sh no encontrado en despliegue.")
        return 1

    cmd = [str(ctl_script), args.action, args.target]
    print(f"🚀 Ejecutando en despliegue: {' '.join(cmd)}")
    res = subprocess.run(cmd, cwd=str(DEPLOY_ROOT))
    return res.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Deploy Bridge & Monitoring Controller for yt-auto",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Status
    p_status = subparsers.add_parser("status", help="Consultar estado de salud y paridad del despliegue")
    p_status.set_defaults(func=cmd_status)

    # Logs
    p_logs = subparsers.add_parser("logs", help="Ver logs en vivo de los servicios de despliegue")
    p_logs.add_argument("-s", "--service", choices=["sched", "bot", "all"], default="all", help="Servicio a consultar")
    p_logs.add_argument("-n", "--lines", type=int, default=30, help="Número de líneas a mostrar")
    p_logs.set_defaults(func=cmd_logs)

    # Sync
    p_sync = subparsers.add_parser("sync", help="Sincronizar cambios de código hacia despliegue")
    p_sync.set_defaults(func=cmd_sync)

    # Ctl
    p_ctl = subparsers.add_parser("ctl", help="Controlar servicios tmux en despliegue (start/stop/restart/status)")
    p_ctl.add_argument("action", choices=["start", "stop", "restart", "status"], help="Acción a realizar")
    p_ctl.add_argument("target", choices=["sched", "bot", "all"], default="all", nargs="?", help="Servicio objetivo")
    p_ctl.set_defaults(func=cmd_ctl)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
