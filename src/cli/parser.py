"""ArgumentParser definition, subcommand tree, short aliases, and legacy argument translation."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any, Sequence

# Ensure src.cli has __path__ if it was stubbed as a flat ModuleType in test environments
_cli_mod = sys.modules.get("src.cli")
if _cli_mod is not None and not hasattr(_cli_mod, "__path__"):
    _cli_mod.__path__ = [str(Path(__file__).resolve().parent)]

from src.cli.handlers import (
    handle_auth,
    handle_backup,
    handle_clean,
    handle_daemon,
    handle_lanes,
    handle_loop,
    handle_migrate,
    handle_profile,
    handle_queue,
    handle_run,
    handle_service,
    handle_status,
    handle_test,
)
from src.config import BASE_DIR, DEFAULT_DB_PATH, RUNTIME_PROFILE

logger = logging.getLogger("cli")

CANONICAL_SUBCOMMANDS = {
    "run",
    "daemon",
    "status",
    "queue",
    "clean",
    "auth",
    "backup",
    "migrate",
    "service",
    "lanes",
    "loop",
    "profile",
    "benchmark",
    "test",
}



def build_parser() -> argparse.ArgumentParser:
    """Build the unified CLI ArgumentParser with 8 canonical subcommands and short aliases."""
    global_parent = argparse.ArgumentParser(add_help=False)
    global_parent.add_argument(
        "-p",
        "--profile",
        type=str,
        default=None,
        choices=["prod", "cli", "dev", "test"],
        help="Perfil de ejecución ('prod', 'cli', 'dev', 'test')",
    )
    global_parent.add_argument(
        "--db-path",
        type=str,
        default=DEFAULT_DB_PATH,
        help="Ruta de la base de datos SQLite",
    )
    global_parent.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        help="Confirmar operaciones sobre la base de producción desde otro perfil",
    )

    # Subparser dedicated global parent: default=argparse.SUPPRESS prevents subparser defaults
    # from overwriting root-level global flags passed before the subcommand.
    subparser_parent = argparse.ArgumentParser(add_help=False)
    subparser_parent.add_argument(
        "-p",
        "--profile",
        type=str,
        default=argparse.SUPPRESS,
        choices=["prod", "cli", "dev", "test"],
        help="Perfil de ejecución ('prod', 'cli', 'dev', 'test')",
    )
    subparser_parent.add_argument(
        "--db-path",
        type=str,
        default=argparse.SUPPRESS,
        help="Ruta de la base de datos SQLite",
    )
    subparser_parent.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Confirmar operaciones sobre la base de producción desde otro perfil",
    )

    parser = argparse.ArgumentParser(
        prog="main.py",
        description="YouTube Automation System CLI Runner",
        parents=[global_parent],
    )

    subparsers = parser.add_subparsers(
        dest="subcommand",
        metavar="<command>",
        help="Comando a ejecutar",
    )

    # 1. run
    run_parser = subparsers.add_parser(
        "run",
        parents=[subparser_parent],
        help="Ejecutar una iteración del pipeline, generación de historias o pruebas",
    )
    run_parser.add_argument(
        "-c",
        "--channel",
        type=str,
        default="all",
        help="Canal objetivo ('moku', 'aelithia', 'scifi', 'all')",
    )
    run_parser.add_argument(
        "-s",
        "--story-id",
        type=str,
        default=None,
        help="ID de historia específica en cola a procesar",
    )
    run_parser.add_argument(
        "-t",
        "--topic",
        type=str,
        default=None,
        help="Tema, premisa o texto para generar historia",
    )
    run_parser.add_argument(
        "--lane",
        type=str,
        default=None,
        help="Carril de producción (config/lanes.json) que gobierna el formato; "
        "por defecto el carril persistido de la historia o el del canal",
    )
    run_parser.add_argument(
        "--generate-only",
        action="store_true",
        help="Generar artefactos localmente sin subir a Drive, Telegram o YouTube",
    )
    run_parser.add_argument(
        "--dispatch-telegram",
        action="store_true",
        help="Enviar video generado a Telegram al finalizar",
    )
    run_parser.add_argument(
        "--test-telegram",
        action="store_true",
        help="Ejecutar prueba E2E de canal y entrega por Telegram",
    )
    run_parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Modo simulación sin efectos secundarios",
    )
    run_parser.add_argument(
        "--preflight",
        action="store_true",
        help="Validar configuración de producción sin llamadas externas",
    )

    # 2. daemon
    daemon_parser = subparsers.add_parser(
        "daemon",
        parents=[subparser_parent],
        help="Iniciar el programador continuo de producción multi-canal",
    )
    daemon_parser.add_argument(
        "-i",
        "--interval",
        type=int,
        default=60,
        help="Intervalo de sondeo del daemon en segundos (por defecto: 60); "
        "la cadencia real la marca cada carril en config/lanes.json",
    )
    daemon_parser.add_argument(
        "-c",
        "--channel",
        type=str,
        default="all",
        help="Canal objetivo ('moku', 'aelithia', 'scifi', 'all')",
    )
    daemon_parser.add_argument(
        "--lanes",
        type=str,
        default=None,
        help="Lista de carriles permitidos separados por coma (p.ej. moku-scp-shorts,moku-horror-long); "
        "por defecto todos los de config/lanes.json",
    )
    daemon_parser.add_argument(
        "--sequential",
        action="store_true",
        help="Procesar historias consecutivamente sin esperar intervalo",
    )
    daemon_parser.add_argument(
        "--mass-produce",
        action="store_true",
        help="Alias de compatibilidad con producción por lotes",
    )

    # 3. status
    status_parser = subparsers.add_parser(
        "status",
        parents=[subparser_parent],
        help="Consultar salud del sistema, estadísticas de cola y observabilidad",
    )
    status_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Salida en formato JSON estructurado",
    )
    status_parser.add_argument(
        "-c",
        "--channel",
        type=str,
        default="all",
        help="Canal para diagnóstico de APIs",
    )
    status_parser.add_argument(
        "--apis",
        action="store_true",
        help="Validar estado de YouTube OAuth, Google Drive y Cookies",
    )
    status_parser.add_argument(
        "--errors",
        action="store_true",
        help="Triaje de errores de observabilidad (eventos y ejecuciones fallidas)",
    )
    status_parser.add_argument(
        "--since",
        type=str,
        default="24h",
        help="Ventana temporal para --errors ('24h', '7d', '30m')",
    )
    status_parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=20,
        help="Límite de eventos a mostrar para --errors",
    )
    status_parser.add_argument(
        "--component",
        type=str,
        default=None,
        help="Filtrar --errors por componente (p.ej. llm, tts, resource_guard)",
    )
    status_parser.add_argument(
        "--level",
        type=str,
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Nivel de log mínimo para --errors",
    )
    status_parser.add_argument(
        "--agent-review",
        type=str,
        default=None,
        metavar="RUN_ID",
        help="QA visual extra: envía el video del run a un agente con visión",
    )
    status_parser.add_argument(
        "--check-pub",
        "--check-publication",
        dest="check_pub",
        action="store_true",
        help="Ejecutar verificación de publicación de 40 minutos y autorreparación",
    )

    # 4. queue
    queue_parser = subparsers.add_parser(
        "queue",
        parents=[subparser_parent],
        help="Inspección y gestión del ciclo de vida de la cola de historias",
    )
    queue_parser.add_argument(
        "action",
        nargs="?",
        default="list",
        choices=["list", "pause", "resume", "activate", "sweep"],
        help="Acción sobre la cola: list, pause, resume, activate, sweep",
    )
    queue_parser.add_argument(
        "target_channel",
        nargs="?",
        default=None,
        help="Canal objetivo para pause, resume o activate (posicional opcional)",
    )
    queue_parser.add_argument(
        "-c",
        "--channel",
        type=str,
        default=None,
        help="Canal objetivo (flag alternativa)",
    )
    queue_parser.add_argument(
        "-l",
        "--limit",
        type=int,
        default=50,
        help="Límite de historias a mostrar (por defecto: 50)",
    )
    queue_parser.add_argument(
        "--lane",
        type=str,
        default=None,
        help="Carril específico para pause o resume (ej. moku-horror-long)",
    )
    queue_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Salida en formato JSON",
    )

    # 5. clean
    clean_parser = subparsers.add_parser(
        "clean",
        parents=[subparser_parent],
        help="Limpieza de artefactos temporales y cachés expiradas",
    )
    clean_parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Simular limpieza sin borrar archivos o directorios",
    )
    clean_parser.add_argument(
        "--cache",
        action="store_true",
        help="Limpiar directorios de trabajo expirados y cachés temporales",
    )
    clean_parser.add_argument(
        "--sessions",
        action="store_true",
        help="Alias de compatibilidad para ciclo de vida de sesiones",
    )

    # 6. auth
    auth_parser = subparsers.add_parser(
        "auth",
        parents=[subparser_parent],
        help="Gestión de tokens OAuth para YouTube Data API v3",
    )
    auth_parser.add_argument(
        "action",
        nargs="?",
        default="url",
        choices=["url", "exchange", "login", "check", "standardize"],
        help="Acción OAuth: 'url', 'exchange', 'login' (servidor local interactivo), 'check' (validar estado), 'standardize' (normalizar formato)",
    )
    auth_parser.add_argument(
        "code",
        nargs="?",
        default=None,
        help="Código de autorización OAuth",
    )
    auth_parser.add_argument(
        "-c",
        "--channel",
        type=str,
        default="moku",
        help="Canal objetivo para el token ('moku', 'aelithia')",
    )
    auth_parser.add_argument(
        "--code",
        dest="code_flag",
        type=str,
        default=None,
        help="Código de autorización OAuth (flag opcional)",
    )
    auth_parser.add_argument(
        "--port",
        type=int,
        default=8585,
        help="Puerto local para flujo interactivo 'auth login' (predeterminado: 8585)",
    )

    # 7. backup
    backup_parser = subparsers.add_parser(
        "backup",
        parents=[subparser_parent],
        help="Respaldo verificado y vacuum-sealed de la base de datos SQLite",
    )
    backup_parser.add_argument(
        "-o",
        "--destination",
        "--dest",
        dest="destination",
        type=str,
        default=None,
        help="Ruta de destino para el archivo de respaldo",
    )
    backup_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Salida en formato JSON",
    )

    # 8. migrate
    migrate_parser = subparsers.add_parser(
        "migrate",
        parents=[subparser_parent],
        help="Aplicación de migraciones de esquema SQLite",
    )
    migrate_parser.add_argument(
        "-d",
        "--dry-run",
        action="store_true",
        help="Simular migraciones sin aplicar cambios",
    )
    migrate_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Salida en formato JSON",
    )

    # 9. service (manage.py compatibility)
    service_parser = subparsers.add_parser(
        "service",
        parents=[subparser_parent],
        help="Control de servicios Systemd y comandos de compilación",
    )
    service_parser.add_argument(
        "action",
        choices=["build", "start", "stop", "restart", "logs"],
        help="Acción de servicio ('build', 'start', 'stop', 'restart', 'logs')",
    )

    # 10. lanes
    lanes_parser = subparsers.add_parser(
        "lanes",
        parents=[subparser_parent],
        help="Listar todos los carriles de producción (config/lanes.json) y estado del planificador",
    )
    lanes_parser.add_argument(
        "-c",
        "--channel",
        type=str,
        default="all",
        help="Filtrar carriles por canal ('moku', 'aelithia', 'all')",
    )
    lanes_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Salida en formato JSON estructurado",
    )

    # 11. loop (Web-based procedural video loop engine & catalog)
    loop_parser = subparsers.add_parser(
        "loop",
        parents=[subparser_parent],
        help="Administrar y generar bucles de video procedurales por código web (Three.js/Canvas/WebGL)",
    )
    loop_parser.add_argument(
        "loop_action",
        nargs="?",
        default="list",
        choices=["list", "catalog", "generate", "preview", "audit", "daemon", "maintain"],
        help="Acción: 'list' (catálogo), 'generate' (crear), 'preview' (miniatura), 'audit' (integridad), 'daemon' (buffer activo)",
    )
    loop_parser.add_argument(
        "-c",
        "--category",
        type=str,
        default=None,
        help="Categoría temática ('cosmic_horror', 'monsters', 'dark_forest', 'space_abyss', 'scp', 'drama_aita')",
    )
    loop_parser.add_argument(
        "-o",
        "--orientation",
        type=str,
        default="vertical",
        choices=["vertical", "horizontal", "9:16", "16:9"],
        help="Orientación del bucle ('vertical' 1080x1920 o 'horizontal' 1920x1080)",
    )
    loop_parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help="Cantidad de bucles a sintetizar",
    )
    loop_parser.add_argument(
        "--duration",
        type=float,
        default=6.0,
        help="Duración del bucle en segundos (default: 6.0)",
    )
    loop_parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Cuadros por segundo (default: 30)",
    )
    loop_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Semilla generativa determinista",
    )
    loop_parser.add_argument(
        "--target",
        type=int,
        default=2,
        help="Objetivo mínimo de stock por categoría para daemon/maintain (default: 2)",
    )
    loop_parser.add_argument(
        "--cleanup",
        action="store_true",
        help="En audit, purgar automáticamente registros de archivos inexistentes",
    )
    loop_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ruta de archivo destino para preview",
    )
    loop_parser.add_argument(
        "-j",
        "--json",
        action="store_true",
        help="Salida en formato JSON estructurado",
    )

    # 12. profile / benchmark (Diagnostics, Profiling & Telemetry - R1)
    for p_name, p_help in [
        ("profile", "Diagnóstico, benchmarking y auditoría de rendimiento por fase (R1)"),
        ("benchmark", "Ejecutar ciclos de benchmarking y pruebas de carga por fase (R1)"),
    ]:
        profile_parser = subparsers.add_parser(
            p_name,
            parents=[subparser_parent],
            help=p_help,
        )
        profile_parser.add_argument(
            "-c",
            "--channel",
            type=str,
            default="moku",
            help="Canal objetivo ('moku', 'aelithia', 'scifi', 'all')",
        )
        profile_parser.add_argument(
            "-l",
            "--lane",
            type=str,
            default=None,
            help="Carril específico a perfilar",
        )
        profile_parser.add_argument(
            "-n",
            "--iterations",
            type=int,
            default=1,
            help="Número de ciclos de benchmarking a ejecutar (default: 1)",
        )
        profile_parser.add_argument(
            "--mock",
            action="store_true",
            default=True,
            help="Ejecutar benchmarking sobre arneses simulados sin costo de API/GPU",
        )
        profile_parser.add_argument(
            "--no-mock",
            dest="mock",
            action="store_false",
            help="Ejecutar profiling sobre el pipeline real",
        )
        profile_parser.add_argument(
            "--stages",
            nargs="+",
            default=None,
            help="Filtrar etapas específicas (ej. 5_tts_synthesis 9_video_rendering)",
        )
        profile_parser.add_argument(
            "--export-json",
            "-o",
            type=str,
            default=None,
            help="Ruta para exportar el reporte consolidado en JSON",
        )
        profile_parser.add_argument(
            "--history",
            action="store_true",
            default=False,
            help="Consultar métricas históricas de profiling desde SQLite",
        )
        profile_parser.add_argument(
            "--since",
            type=str,
            default="24h",
            help="Ventana de tiempo para histórico (ej. '1h', '24h', '7d')",
        )
        profile_parser.add_argument(
            "-j",
            "--json",
            action="store_true",
            default=False,
            help="Salida en formato JSON estructurado",
        )

    # 13. test (Unified Canonical Test & Integrity Runner)
    subparsers.add_parser(
        "test",
        parents=[subparser_parent],
        help="Ejecutar la suite integral de pruebas y auditoría de integridad (scripts/test.sh)",
    )

    return parser



def translate_legacy_args(argv: Sequence[str]) -> list[str]:
    """Translate legacy flat flags and historical commands into canonical subcommand invocations."""
    raw = list(argv)
    if raw and (raw[0].endswith("main.py") or raw[0].endswith("manage.py")):
        raw = raw[1:]

    if not raw:
        return ["status"]

    translated: list[str] = []
    i = 0
    subcmd: str | None = None
    subcmd_args: list[str] = []

    while i < len(raw):
        arg = raw[i]


        # Handle global flags
        if arg in ("-p", "--profile", "--db-path"):
            if i + 1 < len(raw):
                translated.extend([arg, raw[i + 1]])
                i += 2
            else:
                translated.append(arg)
                i += 1
            continue
        elif arg.startswith("--profile=") or arg.startswith("--db-path="):
            translated.append(arg)
            i += 1
            continue
        elif arg in ("-y", "--yes", "-h", "--help"):
            translated.append(arg)
            i += 1
            continue

        # Check if already a canonical subcommand
        if subcmd is None and arg in CANONICAL_SUBCOMMANDS:
            subcmd = arg
            i += 1
            while i < len(raw):
                subcmd_args.append(raw[i])
                i += 1
            break

        # Format flags were removed for run: the format now lives in config/lanes.json.
        # Fail loudly with the migration path instead of silently ignoring.
        if arg in ("-f", "--format", "--video-mode", "--short-test", "--duration"):
            raise SystemExit(
                f"Flag eliminado: {arg}. El formato ya no se elige por línea de comandos: "
                "cada carril en config/lanes.json define su formato. Usa 'main.py run --lane <id>' "
                "o 'main.py daemon' (la cadencia y el formato los gobierna cada carril)."
            )
        if arg.startswith("--video-mode=") or arg.startswith("--format="):

            raise SystemExit(
                f"Flag eliminado: {arg.split('=', 1)[0]}. El formato lo define cada carril "
                "en config/lanes.json; usa 'main.py run --lane <id>'."
            )


        # Check legacy positional commands
        if subcmd is None:
            if arg in ("status",):
                subcmd = "status"
            elif arg in ("run-once", "run_once"):
                subcmd = "run"
            elif arg in ("start-daemon", "start_daemon", "mass-produce", "mass_produce"):
                subcmd = "daemon"
                if "mass" in arg:
                    subcmd_args.append("--mass-produce")
            elif arg in ("list-queue", "list_queue"):
                subcmd = "queue"
                subcmd_args.append("list")
            elif arg in ("auth-url", "auth_url"):
                subcmd = "auth"
                subcmd_args.append("url")
            elif arg in ("auth-code", "auth_code"):
                subcmd = "auth"
                subcmd_args.append("exchange")
            elif arg in ("clean-cache", "clean_cache"):
                subcmd = "clean"
                subcmd_args.append("--cache")
            elif arg in ("clean-sessions", "clean_sessions", "inspect-sessions", "inspect_sessions"):
                subcmd = "clean"
                subcmd_args.append("--sessions")
            elif arg in ("check-apis", "check_apis"):
                subcmd = "status"
                subcmd_args.append("--apis")
            elif arg in ("check-approvals", "check_approvals"):
                subcmd = "queue"
                subcmd_args.append("sweep")
            elif arg in ("check-publication", "check_publication"):
                subcmd = "status"
                subcmd_args.append("--check-pub")
            elif arg in ("test-telegram", "test_telegram"):
                subcmd = "run"
                subcmd_args.append("--test-telegram")
            elif arg in ("preflight",):
                subcmd = "run"
                subcmd_args.append("--preflight")
            elif arg in ("errors",):
                subcmd = "status"
                subcmd_args.append("--errors")
            elif arg in ("pause", "resume"):
                subcmd = "queue"
                subcmd_args.append(arg)
            elif arg == "generate-only":
                subcmd = "run"
                subcmd_args.append("--generate-only")
            elif arg in ("build", "start", "stop", "restart", "logs"):
                subcmd = "service"
                subcmd_args.append(arg)
            elif arg in ("lanes", "list-lanes", "list_lanes"):
                subcmd = "lanes"

            if subcmd is not None:
                i += 1
                continue

        # Check legacy flags
        if arg == "--status":
            subcmd = "status"
        elif arg == "--run-once":
            subcmd = "run"
        elif arg in ("--daemon", "--start-daemon"):
            subcmd = "daemon"
        elif arg == "--mass-produce":
            subcmd = "daemon"
            subcmd_args.append("--mass-produce")
        elif arg == "--list-queue":
            subcmd = "queue"
            subcmd_args.append("list")
        elif arg == "--clean-cache":
            subcmd = "clean"
            subcmd_args.append("--cache")
        elif arg in ("--clean-sessions", "--inspect-sessions"):
            subcmd = "clean"
            subcmd_args.append("--sessions")
        elif arg == "--auth-url":
            subcmd = "auth"
            subcmd_args.append("url")
        elif arg == "--auth-code":
            subcmd = "auth"
            subcmd_args.append("exchange")
            if i + 1 < len(raw):
                subcmd_args.append(raw[i + 1])
                i += 1
        elif arg == "--check-apis":
            subcmd = "status"
            subcmd_args.append("--apis")
        elif arg == "--check-approvals":
            subcmd = "queue"
            subcmd_args.append("sweep")
        elif arg in ("--check-publication", "--check-pub"):
            subcmd = "status"
            subcmd_args.append("--check-pub")
        elif arg == "--test-telegram":
            subcmd = "run"
            subcmd_args.append("--test-telegram")
        elif arg == "--preflight":
            subcmd = "run"
            subcmd_args.append("--preflight")
        elif arg == "--errors":
            subcmd = "status"
            subcmd_args.append("--errors")
        elif arg == "--activate-channel":
            subcmd = "queue"
            subcmd_args.append("activate")
            if i + 1 < len(raw):
                subcmd_args.append(raw[i + 1])
                i += 1
        elif arg in ("--topic", "--story-id", "--generate-only", "--dispatch-telegram", "--lane"):
            if subcmd is None:
                subcmd = "run"
            subcmd_args.append(arg)
            if arg in ("--topic", "--story-id", "--lane") and i + 1 < len(raw):
                subcmd_args.append(raw[i + 1])
                i += 1
        elif arg in ("--agent-review",):
            if subcmd is None:
                subcmd = "status"
            subcmd_args.append(arg)
            if i + 1 < len(raw):
                subcmd_args.append(raw[i + 1])
                i += 1
        else:
            subcmd_args.append(arg)

        i += 1

    if subcmd is None:
        subcmd = "status"

    # Format flags were removed: the format lives in config/lanes.json now.
    # Fail loudly with the migration path instead of silently ignoring (except for 'loop' subcommand where --duration is valid).
    if subcmd != "loop":
        _REMOVED_FORMAT_FLAGS = {"-f", "--format", "--video-mode", "--short-test", "--duration"}
        offending = [
            token
            for token in [subcmd, *subcmd_args, *translated]
            if token in _REMOVED_FORMAT_FLAGS
            or token.startswith("--video-mode=")
            or token.startswith("--format=")
        ]
        if offending:
            raise SystemExit(
                f"Flag eliminado: {offending[0]}. El formato ya no se elige por línea de comandos: "
                "cada carril en config/lanes.json define su formato. Usa 'main.py run --lane <id>' "
                "o 'main.py daemon' (la cadencia y el formato los gobierna cada carril)."
            )

    return translated + [subcmd] + subcmd_args



def dispatch_cli(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Route parsed CLI Namespace to its corresponding handler with anti-contamination guard."""
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH) or DEFAULT_DB_PATH

    # Anti-contamination guard: never touch prod DB without confirmation if profile != prod
    if (
        RUNTIME_PROFILE != "prod"
        and Path(db_path).resolve() == (BASE_DIR / "data" / "shorts_queue.db").resolve()
        and not getattr(args, "yes", False)
    ):
        print(
            f"⛔ Perfil '{RUNTIME_PROFILE}': --db-path apunta a la base de producción. "
            "Repite con --profile prod o añade --yes para confirmar.",
            file=sys.stderr,
        )
        return 2

    # Map code_flag if present for auth handler
    if getattr(args, "code_flag", None) and not getattr(args, "code", None):
        setattr(args, "code", args.code_flag)

    subcommand = getattr(args, "subcommand", None)

    # If subcommand is explicit
    if subcommand == "run":
        return handle_run(args, parser)
    if subcommand == "daemon":
        return handle_daemon(args, parser)
    if subcommand == "status":
        return handle_status(args, parser)
    if subcommand == "queue":
        return handle_queue(args, parser)
    if subcommand == "clean":
        return handle_clean(args, parser)
    if subcommand == "auth":
        return handle_auth(args, parser)
    if subcommand == "backup":
        return handle_backup(args, parser)
    if subcommand == "migrate":
        return handle_migrate(args, parser)
    if subcommand == "service":
        return handle_service(args, parser)
    if subcommand == "lanes":
        return handle_lanes(args, parser)
    if subcommand == "loop":
        return handle_loop(args, parser)
    if subcommand in ("profile", "benchmark"):
        return handle_profile(args, parser)
    if subcommand == "test":
        return handle_test(args, parser)


    # Legacy mock / direct namespace fallback routing
    if (
        getattr(args, "run_once", False)
        or getattr(args, "test_telegram", False)
        or getattr(args, "topic", None) is not None
        or getattr(args, "story_id", None) is not None
        or getattr(args, "preflight", False)
        or getattr(args, "generate_only", False)
        or getattr(args, "dispatch_telegram", False)
    ):
        return handle_run(args, parser)

    if getattr(args, "daemon", False) or getattr(args, "mass_produce", False):
        return handle_daemon(args, parser)

    if (
        getattr(args, "check_apis", False)
        or getattr(args, "errors", False)
        or getattr(args, "agent_review", None) is not None
        or getattr(args, "check_publication", False)
        or getattr(args, "check_pub", False)
    ):
        return handle_status(args, parser)

    if getattr(args, "list_queue", False) or getattr(args, "activate_channel", None):
        return handle_queue(args, parser)

    if getattr(args, "clean_cache", False) or getattr(args, "clean_sessions", False) or getattr(args, "inspect_sessions", False):
        return handle_clean(args, parser)

    if getattr(args, "auth_url", False) or getattr(args, "auth_code", None) is not None:
        return handle_auth(args, parser)

    cmd = (getattr(args, "command", None) or "").lower()
    if cmd in ("run-once", "run_once", "run"):
        return handle_run(args, parser)
    if cmd in ("start-daemon", "start_daemon", "daemon", "mass-produce", "mass_produce"):
        return handle_daemon(args, parser)
    if cmd in ("list-queue", "list_queue", "queue"):
        return handle_queue(args, parser)
    if cmd in ("clean-cache", "clean_cache", "clean"):
        return handle_clean(args, parser)
    if cmd in ("auth-url", "auth_url", "auth-code", "auth_code", "auth"):
        return handle_auth(args, parser)
    if cmd in ("build", "start", "stop", "restart", "logs"):
        return handle_service(args, parser)
    if cmd in ("lanes", "list-lanes", "list_lanes"):
        return handle_lanes(args, parser)

    return handle_status(args, parser)
