#!/usr/bin/env python3
"""Resident Telegram review bot for tmux (no cron/systemd on this host).

Routes both review callbacks (approve/reject/redo/info) and admin control
commands/buttons (/menu, /stats, /priv, /pub, /unlist, /del, /delsi) through
src.telegram.callbacks.poll_callbacks, which is poison-proof and backs off
on network failures. Credentials come from the project .env via src.config.
"""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

_SHUTDOWN = False


def _on_signal(_signum, _frame):
    global _SHUTDOWN
    _SHUTDOWN = True


def main() -> int:
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)
    os.environ.setdefault("YT_PROFILE", "prod")
    os.environ.setdefault("ENABLE_TELEGRAM_CALLBACK_POLLING", "1")

    import src.config  # noqa: F401  (loads .env, resolves profile roots)
    from src.log import setup_logging
    from src.telegram.callbacks import poll_callbacks
    from review.telegram_bot import TelegramReviewBot

    setup_logging()
    bot = TelegramReviewBot()
    if not bot.token or not bot.chat_id:
        print("[review-bot] missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID; aborting", flush=True)
        return 1
    print(f"[review-bot] started pid={os.getpid()} chat={bot.chat_id}", flush=True)
    heartbeat = poll_callbacks(bot, lambda: _SHUTDOWN)
    print(
        f"[review-bot] shutdown; seconds since last successful poll: "
        f"{heartbeat.seconds_since_success():.1f}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
