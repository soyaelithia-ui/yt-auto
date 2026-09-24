"""Modular subcommand registration for the CLI ArgumentParser."""
from __future__ import annotations

import argparse
from typing import Tuple

from src.config import DEFAULT_DB_PATH


def build_parent_parsers() -> Tuple[argparse.ArgumentParser, argparse.ArgumentParser]:
    """Build shared parent parsers for global flags and subparser inheritance."""
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
    return global_parent, subparser_parent


def register_run_subcommand(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'run' subcommand."""
    p = subparsers.add_parser(
        "run",
        parents=[parent],
        help="Ejecutar una iteración del pipeline, generación de historias o pruebas",
    )
    p.add_argument("-c", "--channel", type=str, default="all", help="Canal objetivo ('horror' / canal 1, 'drama' / canal 2, 'scifi', 'all')")
    p.add_argument("-s", "--story-id", type=str, default=None, help="ID de historia específica en cola a procesar")
    p.add_argument("-t", "--topic", type=str, default=None, help="Tema, premisa o texto para generar historia")
    p.add_argument(
        "--lane",
        type=str,
        default=None,
        help="Carril de producción (config/lanes.json) que gobierna el formato; "
        "por defecto el carril persistido de la historia o el del canal",
    )
    p.add_argument("--generate-only", action="store_true", help="Generar artefactos localmente sin subir a Drive, Telegram o YouTube")
    p.add_argument("--dispatch-telegram", action="store_true", help="Enviar video generado a Telegram al finalizar")
    p.add_argument("--test-telegram", action="store_true", help="Ejecutar prueba E2E de canal y entrega por Telegram")
    p.add_argument("-d", "--dry-run", action="store_true", help="Modo simulación sin efectos secundarios")
    p.add_argument("--preflight", action="store_true", help="Validar configuración de producción sin llamadas externas")


def register_daemon_subcommand(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'daemon' subcommand."""
    p = subparsers.add_parser(
        "daemon",
        parents=[parent],
        help="Iniciar el programador continuo de producción multi-canal",
    )
    p.add_argument(
        "-i",
        "--interval",
        type=int,
        default=60,
        help="Intervalo de sondeo del daemon en segundos (por defecto: 60); la cadencia real la marca cada carril",
    )
    p.add_argument("-c", "--channel", type=str, default="all", help="Canal objetivo ('horror' / canal 1, 'drama' / canal 2, 'scifi', 'all')")
    p.add_argument(
        "--lanes",
        type=str,
        default=None,
        help="Lista de carriles permitidos separados por coma (p.ej. horror-scp-shorts,horror-long)",
    )
    p.add_argument("--sequential", action="store_true", help="Procesar historias consecutivamente sin esperar intervalo")
    p.add_argument("--mass-produce", action="store_true", help="Alias de compatibilidad con producción por lotes")


def register_status_subcommand(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'status' subcommand."""
    p = subparsers.add_parser(
        "status",
        parents=[parent],
        help="Consultar salud del sistema, estadísticas de cola y observabilidad",
    )
    p.add_argument("-j", "--json", action="store_true", help="Salida en formato JSON estructurado")
    p.add_argument("-c", "--channel", type=str, default="all", help="Canal para diagnóstico de APIs")
    p.add_argument("--apis", action="store_true", help="Validar estado de YouTube OAuth, Google Drive y Cookies")
    p.add_argument("--errors", action="store_true", help="Triaje de errores de observabilidad (eventos y ejecuciones fallidas)")
    p.add_argument("--since", type=str, default="24h", help="Ventana temporal para --errors ('24h', '7d', '30m')")
    p.add_argument("-l", "--limit", type=int, default=20, help="Límite de eventos a mostrar para --errors")
    p.add_argument("--component", type=str, default=None, help="Filtrar --errors por componente")
    p.add_argument("--level", type=str, default=None, choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], help="Nivel de log mínimo")
    p.add_argument("--agent-review", type=str, default=None, metavar="RUN_ID", help="QA visual extra: envía el video del run a un agente con visión")
    p.add_argument("--check-pub", "--check-publication", dest="check_pub", action="store_true", help="Ejecutar verificación de publicación de 40 minutos")


def register_queue_subcommand(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'queue' subcommand."""
    p = subparsers.add_parser(
        "queue",
        parents=[parent],
        help="Inspección y gestión del ciclo de vida de la cola de historias",
    )
    p.add_argument("action", nargs="?", default="list", choices=["list", "pause", "resume", "activate", "sweep"], help="Acción sobre la cola")
    p.add_argument("target_channel", nargs="?", default=None, help="Canal objetivo para pause, resume o activate")
    p.add_argument("-c", "--channel", type=str, default=None, help="Canal objetivo (flag alternativa)")
    p.add_argument("-l", "--limit", type=int, default=50, help="Límite de historias a mostrar (por defecto: 50)")
    p.add_argument("--lane", type=str, default=None, help="Carril específico para pause o resume")
    p.add_argument("-j", "--json", action="store_true", help="Salida en formato JSON")


def register_clean_subcommand(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'clean' subcommand."""
    p = subparsers.add_parser(
        "clean",
        parents=[parent],
        help="Limpieza de artefactos temporales y cachés expiradas",
    )
    p.add_argument("-d", "--dry-run", action="store_true", help="Simular limpieza sin borrar archivos o directorios")
    p.add_argument("--cache", action="store_true", help="Limpiar directorios de trabajo expirados y cachés temporales")
    p.add_argument("--sessions", action="store_true", help="Alias de compatibilidad para ciclo de vida de sesiones")


def register_auth_subcommand(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'auth' subcommand."""
    p = subparsers.add_parser(
        "auth",
        parents=[parent],
        help="Gestión de tokens OAuth para YouTube Data API v3",
    )
    p.add_argument(
        "action",
        nargs="?",
        default="url",
        choices=["url", "exchange", "login", "check", "standardize"],
        help="Acción OAuth: 'url', 'exchange', 'login', 'check', 'standardize'",
    )
    p.add_argument("code", nargs="?", default=None, help="Código de autorización OAuth")
    p.add_argument("-c", "--channel", type=str, default="horror", help="Canal objetivo para el token ('horror' / canal 1, 'drama' / canal 2)")
    p.add_argument("--code", dest="code_flag", type=str, default=None, help="Código de autorización OAuth (flag opcional)")
    p.add_argument("--port", type=int, default=8585, help="Puerto local para flujo interactivo 'auth login'")


def register_backup_and_migrate_subcommands(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'backup' and 'migrate' subcommands."""
    bp = subparsers.add_parser(
        "backup",
        parents=[parent],
        help="Respaldo verificado y vacuum-sealed de la base de datos SQLite",
    )
    bp.add_argument("-o", "--destination", "--dest", dest="destination", type=str, default=None, help="Ruta de destino")
    bp.add_argument("-j", "--json", action="store_true", help="Salida en formato JSON")

    mp = subparsers.add_parser(
        "migrate",
        parents=[parent],
        help="Aplicación de migraciones de esquema SQLite",
    )
    mp.add_argument("-d", "--dry-run", action="store_true", help="Simular migraciones sin aplicar cambios")
    mp.add_argument("-j", "--json", action="store_true", help="Salida en formato JSON")


def register_inventory_subcommand(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'inventory' subcommand."""
    ip = subparsers.add_parser(
        "inventory",
        parents=[parent],
        help="Gestión e inspección del inventario 100%% de videos e historias publicadas para agentes IA",
    )
    ip.add_argument("inventory_action", nargs="?", choices=["list", "sync", "backup", "digest"], default="list", help="Acción de inventario")
    ip.add_argument("-c", "--channel", type=str, default="all", help="Canal ('horror', 'drama', o 'all')")
    ip.add_argument("-l", "--limit", type=int, default=50, help="Límite de elementos a procesar o mostrar")
    ip.add_argument("--folder-id", type=str, default=None, help="ID de carpeta de Google Drive para respaldo")
    ip.add_argument("-j", "--json", action="store_true", help="Salida en formato JSON")


def register_service_and_lanes_subcommands(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'service' and 'lanes' subcommands."""
    sp = subparsers.add_parser(
        "service",
        parents=[parent],
        help="Control de servicios Systemd y comandos de compilación",
    )
    sp.add_argument("action", choices=["build", "start", "stop", "restart", "logs"], help="Acción de servicio")

    lp = subparsers.add_parser(
        "lanes",
        parents=[parent],
        help="Listar todos los carriles de producción (config/lanes.json) y estado del planificador",
    )
    lp.add_argument("-c", "--channel", type=str, default="all", help="Filtrar carriles por canal ('horror' / canal 1, 'drama' / canal 2, 'all')")
    lp.add_argument("-j", "--json", action="store_true", help="Salida en formato JSON estructurado")


def register_loop_subcommand(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'loop' subcommand."""
    p = subparsers.add_parser(
        "loop",
        parents=[parent],
        help="Administrar catálogo de bucles de video pre-renderizados y verificar inventario de activos",
    )
    p.add_argument(
        "loop_action",
        nargs="?",
        default="list",
        choices=["list", "catalog", "generate", "preview", "audit", "daemon", "maintain"],
        help="Acción: 'list', 'catalog', 'generate', 'preview', 'audit', 'daemon', 'maintain'",
    )
    p.add_argument("-c", "--category", type=str, default=None, help="Categoría temática")
    p.add_argument("-o", "--orientation", type=str, default="vertical", choices=["vertical", "horizontal", "9:16", "16:9"], help="Orientación del bucle")
    p.add_argument("-n", "--count", type=int, default=1, help="Cantidad de bucles a sintetizar")
    p.add_argument("--duration", type=float, default=6.0, help="Duración del bucle en segundos")
    p.add_argument("--fps", type=int, default=30, help="Cuadros por segundo")
    p.add_argument("--seed", type=int, default=None, help="Semilla generativa determinista")
    p.add_argument("--target", type=int, default=2, help="Objetivo mínimo de stock por categoría")
    p.add_argument("--cleanup", action="store_true", help="En audit, purgar automáticamente registros inexistentes")
    p.add_argument("--output", type=str, default=None, help="Ruta de archivo destino para preview")
    p.add_argument("-j", "--json", action="store_true", help="Salida en formato JSON estructurado")


def register_profile_and_benchmark_subcommands(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'profile' and 'benchmark' subcommands."""
    for p_name, p_help in [
        ("profile", "Diagnóstico, benchmarking y auditoría de rendimiento por fase (R1)"),
        ("benchmark", "Ejecutar ciclos de benchmarking y pruebas de carga por fase (R1)"),
    ]:
        p = subparsers.add_parser(p_name, parents=[parent], help=p_help)
        p.add_argument("-c", "--channel", type=str, default="horror", help="Canal objetivo ('horror' / canal 1, 'drama' / canal 2, 'scifi', 'all')")
        p.add_argument("-l", "--lane", type=str, default=None, help="Carril específico a perfilar")
        p.add_argument("-n", "--iterations", type=int, default=1, help="Número de ciclos de benchmarking a ejecutar")
        p.add_argument("--mock", action="store_true", default=True, help="Ejecutar sobre arneses simulados sin costo de API/GPU")
        p.add_argument("--no-mock", dest="mock", action="store_false", help="Ejecutar profiling sobre el pipeline real")
        p.add_argument("--stages", nargs="+", default=None, help="Filtrar etapas específicas")
        p.add_argument("--export-json", "-o", type=str, default=None, help="Ruta para exportar el reporte consolidado en JSON")
        p.add_argument("--history", action="store_true", default=False, help="Consultar métricas históricas de profiling")
        p.add_argument("--since", type=str, default="24h", help="Ventana de tiempo para histórico")
        p.add_argument("-j", "--json", action="store_true", default=False, help="Salida en formato JSON estructurado")


def register_test_and_mcp_subcommands(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'test' and 'mcp' subcommands."""
    subparsers.add_parser(
        "test",
        parents=[parent],
        help="Ejecutar la suite integral de pruebas y auditoría de integridad (scripts/test.sh)",
    )

    mp = subparsers.add_parser(
        "mcp",
        parents=[parent],
        help="Iniciar el servidor Model Context Protocol (MCP)",
    )
    mp.add_argument("--transport", choices=["stdio", "sse"], default="stdio", help="Transporte de comunicación ('stdio' o 'sse')")
    mp.add_argument("--host", type=str, default="127.0.0.1", help="Dirección de escucha para transporte SSE")
    mp.add_argument("--port", type=int, default=8000, help="Puerto de escucha para transporte SSE")


def register_analytics_subcommands(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register 'sweep-24h' and 'prune-underperforming' subcommands."""
    sp = subparsers.add_parser(
        "sweep-24h",
        parents=[parent],
        help="Ejecutar barrido de 24 horas de métricas de YouTube y purga autónoma",
    )
    sp.add_argument("--channel", type=str, default="all", help="Canal objetivo ('moku', 'aelithia', o 'all')")
    sp.add_argument("--live", action="store_true", help="Ejecutar mutaciones en vivo (por defecto: dry-run)")
    sp.add_argument("--force", action="store_true", help="Forzar ejecución ignorando el intervalo de 24h")

    pp = subparsers.add_parser(
        "prune-underperforming",
        parents=[parent],
        help="Evaluar y purgar videos con bajo rendimiento tras periodo de gracia",
    )
    pp.add_argument("--channel", type=str, default="moku", help="Canal objetivo ('moku' o 'aelithia')")
    pp.add_argument("--live", action="store_true", help="Ejecutar eliminación real en YouTube (por defecto: dry-run)")
    pp.add_argument("--min-score", type=float, default=25.0, help="Umbral mínimo de puntuación de éxito (por defecto: 25.0)")
    pp.add_argument("--grace-hours", type=float, default=24.0, help="Horas mínimas de antigüedad requeridas (por defecto: 24.0)")
    pp.add_argument("--max-delete", type=int, default=2, help="Límite máximo de videos a eliminar por canal (por defecto: 2)")
    pp.add_argument("--force", action="store_true", help="Ignorar interruptor AUTO_PRUNE_ENABLED")

    cl = subparsers.add_parser(
        "collect-links",
        parents=[parent],
        help="Recolección automática nativa de enlaces y métricas de videos en YouTube",
    )
    cl.add_argument("-c", "--channel", type=str, default="all", help="Canal objetivo ('horror', 'drama', 'all')")
    cl.add_argument("-l", "--limit", type=int, default=0, help="Límite de videos a recolectar (0 = 100%% de la cuenta)")
    cl.add_argument("--live", action="store_true", help="Consultar directamente a YouTube API (por defecto: dry-run)")


def register_all_subcommands(subparsers: argparse._SubParsersAction, parent: argparse.ArgumentParser) -> None:
    """Register all canonical subcommands on the main argument parser."""
    register_run_subcommand(subparsers, parent)
    register_daemon_subcommand(subparsers, parent)
    register_status_subcommand(subparsers, parent)
    register_queue_subcommand(subparsers, parent)
    register_clean_subcommand(subparsers, parent)
    register_auth_subcommand(subparsers, parent)
    register_backup_and_migrate_subcommands(subparsers, parent)
    register_inventory_subcommand(subparsers, parent)
    register_service_and_lanes_subcommands(subparsers, parent)
    register_loop_subcommand(subparsers, parent)
    register_profile_and_benchmark_subcommands(subparsers, parent)
    register_test_and_mcp_subcommands(subparsers, parent)
    register_analytics_subcommands(subparsers, parent)
