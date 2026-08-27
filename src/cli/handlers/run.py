"""Handler for 'run' subcommand and single pipeline execution."""
from __future__ import annotations

import argparse
import logging
import sys
from typing import Any

logger = logging.getLogger("main")


def _resolve_channel_key(channel: str | None) -> str:
    if "src.branding" in sys.modules:
        br = sys.modules["src.branding"]
    else:
        import src.branding as br

    return br.resolve_channel_key(channel)


def _get_active_channels(db_path: str | None = None) -> list[str]:
    if "src.channel_manager" in sys.modules:
        cm = sys.modules["src.channel_manager"]
    else:
        import src.channel_manager as cm

    func = getattr(cm, "get_active_channels", None)
    if func is None:
        return ["moku", "aelithia"]
    try:
        return list(func(db_path))
    except TypeError:
        return list(func())


def _get_locks():
    main_mod = sys.modules.get("main")
    if main_mod is not None:
        acq = getattr(main_mod, "acquire_lock", None)
        rel = getattr(main_mod, "release_lock", None)
        if acq is not None and rel is not None:
            return acq, rel

    if "src.core.lock" in sys.modules:
        lock_mod = sys.modules["src.core.lock"]
        return lock_mod.acquire_lock, lock_mod.release_lock
    from src.core.lock import acquire_lock, release_lock

    return acquire_lock, release_lock


def _get_channel_lock_cls():
    if "src.core.lock" in sys.modules:
        lock_mod = sys.modules["src.core.lock"]
    else:
        import src.core.lock as lock_mod

    return lock_mod.ChannelLock, lock_mod.ChannelLockError


def _get_orchestrator_cls():
    if "src.orchestrator" in sys.modules:
        orch_mod = sys.modules["src.orchestrator"]
    else:
        import src.orchestrator as orch_mod

    return getattr(orch_mod, "PipelineOrchestrator", None)


def _require_production_preflight() -> None:
    import src.config as cfg

    try:
        cfg.validate_runtime_config(
            require_drive=True,
            require_publish=True,
            require_review=True,
        )
    except RuntimeError as exc:
        print(f"Production preflight: FAIL: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def handle_run(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Execute single pipeline iteration, topic generation, or telegram canary test."""
    import src.config as cfg

    db_path = getattr(args, "db_path", cfg.DEFAULT_DB_PATH)
    PipelineOrchestrator = _get_orchestrator_cls()
    ChannelLock, ChannelLockError = _get_channel_lock_cls()
    acquire_lock, release_lock = _get_locks()

    orchestrator = PipelineOrchestrator(db_path=db_path)

    if getattr(args, "preflight", False):
        _require_production_preflight()
        print("Production preflight: PASS")
        return 0

    if getattr(args, "test_telegram", False):
        raw_ch = getattr(args, "channel", "all") or "all"
        if raw_ch in ("all", None):
            ch = "moku"
        else:
            try:
                ch = _resolve_channel_key(raw_ch)
            except (ValueError, KeyError):
                msg = f"Canal desconocido o inválido: {raw_ch!r}. Canales válidos: 'moku', 'aelithia'"
                if parser is not None:
                    parser.error(msg)
                else:
                    print(f"Error: {msg}", file=sys.stderr)
                    return 2
        acquire_lock(ch)
        try:
            print(f"=== Running E2E Test Pipeline & Telegram Delivery for channel [{ch}] ===")
            canary = orchestrator.run_telegram_canary(
                channel=ch,
                story_id=getattr(args, "story_id", None),
            )
            print(f"[{ch}] E2E Pipeline Test Result: {canary.status}")
            if canary.video_file and canary.telegram_ok:
                print(
                    "Telegram Delivery Result: "
                    f"ok={canary.telegram_ok}, "
                    "message_id=None, "
                    f"detail={canary.telegram_detail}, "
                    f"error={canary.error}"
                )
            elif not canary.video_file:
                print(f"Rendered video file not found at: {canary.video_file or ''}")
            if canary.status == "FAILED" and not canary.video_file:
                sys.exit(1)
            return 0
        finally:
            release_lock(ch)

    target_story = getattr(args, "topic", None) or getattr(args, "story_id", None)
    channel = getattr(args, "channel", "all") or "all"
    if target_story and channel == "all":
        if parser is not None:
            parser.error("--topic o --story-id requiere --channel moku o --channel aelithia")
        else:
            print("Error: --topic o --story-id requiere --channel moku o --channel aelithia", file=sys.stderr)
            return 2

    if channel != "all":
        try:
            ch = _resolve_channel_key(channel)
        except (ValueError, KeyError):
            msg = f"Canal desconocido o inválido: {channel!r}. Canales válidos: 'moku', 'aelithia', 'all'"
            if parser is not None:
                parser.error(msg)
            else:
                print(f"Error: {msg}", file=sys.stderr)
                return 2

    lane_id = getattr(args, "lane", None)

    if channel == "all":
        active = _get_active_channels(db_path)
        skipped_channels: list[str] = []
        ran_channels: list[str] = []
        for ch in active:
            holder = ChannelLock(ch)
            try:
                holder.acquire()
            except ChannelLockError:
                logger.warning(
                    "Canal [%s] bloqueado por otro proceso; omitido en este turno",
                    ch,
                )
                skipped_channels.append(ch)
                continue
            try:
                res = orchestrator.run_channel(
                    channel=ch,
                    generate_only=getattr(args, "generate_only", False),
                    dispatch_telegram=getattr(args, "dispatch_telegram", False),
                    skip_lock=True,
                )
                print(f"[{ch}] Result: {res.status}")
                ran_channels.append(ch)
            finally:
                holder.release()
        if skipped_channels:
            print(f"[all] Canales omitidos (lock ajeno): {', '.join(skipped_channels)}")
        if not ran_channels:
            print("[all] Ningún canal disponible (todos bloqueados)")
            raise SystemExit(1)
        return 0
    else:
        acquire_lock(ch)
        try:
            print(f"=== Running pipeline iteration for channel: [{ch}] (lane={lane_id}, topic={target_story}) ===")
            res = orchestrator.run_channel(
                channel=ch,
                topic=getattr(args, "topic", None),
                story_id=getattr(args, "story_id", None),
                lane_id=lane_id,
                generate_only=getattr(args, "generate_only", False),
                dispatch_telegram=getattr(args, "dispatch_telegram", False),
            )
            print(f"[{ch}] Result: {res.status}")
            if res.telegram_delivery:
                print(f"[{ch}] Telegram Dispatch: ok={res.telegram_delivery['ok']}, message_id={res.telegram_delivery.get('message_id')}, detail={res.telegram_delivery.get('detail')}")
            print("\nOverall Execution Summary:", {ch: res.raw_result})
            return 0
        finally:
            release_lock(ch)
