"""ArgumentParser definition, subcommand tree, short aliases, and legacy argument translation."""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

# Ensure src.cli has __path__ if it was stubbed as a flat ModuleType in test environments
_cli_mod = sys.modules.get("src.cli")
if _cli_mod is not None and not hasattr(_cli_mod, "__path__"):
    _cli_mod.__path__ = [str(Path(__file__).resolve().parent)]

from src.cli.handlers import (
    handle_auth,
    handle_backup,
    handle_clean,
    handle_daemon,
    handle_inventory,
    handle_lanes,
    handle_loop,
    handle_mcp,
    handle_migrate,
    handle_profile,
    handle_prune_underperforming,
    handle_queue,
    handle_run,
    handle_service,
    handle_status,
    handle_sweep_24h,
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
    "inventory",
    "migrate",
    "service",
    "lanes",
    "loop",
    "profile",
    "benchmark",
    "test",
    "mcp",
    "sweep-24h",
    "prune-underperforming",
}



def build_parser() -> argparse.ArgumentParser:
    """Build the unified CLI ArgumentParser with canonical subcommands and short aliases."""
    from src.cli.subparsers import build_parent_parsers, register_all_subcommands

    global_parent, subparser_parent = build_parent_parsers()
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
    register_all_subcommands(subparsers, subparser_parent)
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
    if subcommand == "inventory":
        return handle_inventory(args, parser)
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
    if subcommand == "mcp":
        return handle_mcp(args, parser)
    if subcommand == "sweep-24h":
        return handle_sweep_24h(args, parser)
    if subcommand == "prune-underperforming":
        return handle_prune_underperforming(args, parser)


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
