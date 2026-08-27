#!/usr/bin/env python3
"""
dev/run_telegram_bot.py - Daemon Runner for the Interactive Telegram Bot.

Runs the long-polling Telegram bot with interactive command handling:
/start, /help, /status, /create, /shorts, /long, /seo, /jobs, /autopilot, /latest
and inline keyboards for script inspection, SRT subtitles, SEO tags, and visual audits.
"""
from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from dotenv import load_dotenv
load_dotenv(ROOT_DIR / ".env")

from src.telegram.interactive_bot import InteractiveTelegramBot
from src.log import get_logger

logger = get_logger("dev_run_telegram_bot")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Interactive Telegram Bot Service Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--token", type=str, default=None, help="Telegram Bot Token (default: env TELEGRAM_BOT_TOKEN)")
    parser.add_argument("--chat-id", type=str, default=None, help="Authorized Chat ID (default: env TELEGRAM_CHAT_ID)")
    parser.add_argument("--once", action="store_true", default=False, help="Poll updates once and exit (for testing/diagnostics)")
    parser.add_argument("--autopilot", action="store_true", default=False, help="Start with AutoPilot 24/7 enabled")
    parser.add_argument("--autopilot-interval", type=float, default=4.0, help="AutoPilot interval in hours")
    args = parser.parse_args()

    token = args.token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = args.chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN no configurado en entorno ni en argumentos CLI.")
        if not args.once:
            logger.info("Modo de espera: Puedes configurar TELEGRAM_BOT_TOKEN en .env")

    bot = InteractiveTelegramBot(token=token, chat_id=chat_id)

    if args.autopilot:
        logger.info("Iniciando AutoPilot 24/7 (intervalo: %.1f horas)...", args.autopilot_interval)
        bot.scheduler.start(interval_hours=args.autopilot_interval)

    if args.once:
        logger.info("Ejecutando sondeo único (getUpdates single poll)...")
        bot.poll_once()
        logger.info("Sondeo único completado.")
        return 0

    logger.info("=======================================================")
    logger.info("🤖 Interactive Telegram Bot Activo (Polling)")
    logger.info("Presiona Ctrl+C para detener el servicio.")
    logger.info("=======================================================")

    bot.start_polling()

    def _signal_handler(sig, frame):
        logger.info("\nSeñal recibida (%s). Deteniendo bot...", sig)
        bot.stop_polling()
        bot.scheduler.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    try:
        while bot.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        _signal_handler("SIGINT", None)

    return 0


if __name__ == "__main__":
    sys.exit(main())
