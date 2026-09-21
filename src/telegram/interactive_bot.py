"""
src/telegram/interactive_bot.py - Interactive Telegram Command & Callback Dispatcher.

Integrates seamlessly with TelegramReviewBot, supporting:
- Slash commands: /start, /help, /menu, /status, /health, /create, /shorts, /long, /seo, /autopilot, /latest, /stats, /priv, /pub, /unlist, /del, /delsi
- Rich inline buttons: view script, SEO metadata, image audits, autopilot toggle, YouTube control menu, and review HITL (approve/reject/redo/info).
- Elevated 2000 MB (2 GB) upload limits via Local Bot API Server, with automatic 50 MB cloud fallback and lightweight review proxy.
- Long-polling worker with exponential backoff and poisoned update containment.
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from typing import Any, Dict, Optional

from review import DeliveryResult, TelegramReviewBot
from review.telegram_bot import send_telegram_message, is_local_bot_api
from src.core.scheduler import AutoPilotScheduler
from src.log import get_logger
from src.telegram.callbacks import _route_update, poll_callbacks

logger = get_logger("telegram_interactive")


class InteractiveTelegramBot:
    """Production-grade Telegram interactive engine backed by TelegramReviewBot."""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        base_url: Optional[str] = None,
        bot: Optional[TelegramReviewBot] = None,
    ) -> None:
        self.bot = bot or TelegramReviewBot(
            token=token,
            chat_id=chat_id,
            base_url=base_url,
        )
        self.token = self.bot.token
        self.default_chat_id = str(self.bot.chat_id)
        self.base_url = self.bot.base_url
        self.registered_chats: set[str] = set()
        if self.default_chat_id:
            self.registered_chats.add(self.default_chat_id)
        self.last_update_id = 0
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.scheduler = AutoPilotScheduler.instance()

    @property
    def jobs_cache(self) -> Dict[str, Dict[str, Any]]:
        return self.bot.jobs_cache

    @jobs_cache.setter
    def jobs_cache(self, value: Dict[str, Dict[str, Any]]) -> None:
        self.bot.jobs_cache = value

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> DeliveryResult:
        """Send formatted text message."""
        return send_telegram_message(
            message=text,
            chat_id=str(chat_id),
            token=self.token,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            bot=self.bot,
        )

    def send_video(
        self,
        video_path: str,
        caption: Optional[str] = None,
        chat_id: Optional[str] = None,
        duration: Optional[float] = None,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> DeliveryResult:
        """Send video file up to 2 GB via local server or streaming multipart."""
        return self.bot.send_video(
            video_path=video_path,
            caption=caption,
            chat_id=str(chat_id or self.default_chat_id),
            duration=duration,
            parse_mode=parse_mode,
            reply_markup=reply_markup,
            **kwargs,
        )

    def send_document(
        self,
        document_path: str,
        caption: Optional[str] = None,
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
    ) -> DeliveryResult:
        return self.bot.send_document(
            document_path=document_path,
            caption=caption,
            chat_id=str(chat_id or self.default_chat_id),
            parse_mode=parse_mode,
        )

    def send_photo(
        self,
        photo_path: str,
        caption: Optional[str] = None,
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
    ) -> DeliveryResult:
        return self.bot.send_photo(
            photo_path=photo_path,
            caption=caption,
            chat_id=str(chat_id or self.default_chat_id),
            parse_mode=parse_mode,
        )

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        return self.bot.answer_callback_query(
            callback_query_id=callback_query_id,
            text=text,
            show_alert=show_alert,
        )

    def register_job(self, job_id: str, data: Dict[str, Any]) -> None:
        """Stores deliverable data for inline inspection buttons."""
        self.bot.register_job(job_id, data)

    def broadcast_job(self, job_id: str, summary_markdown: str, reply_markup: Optional[Dict[str, Any]] = None) -> None:
        for cid in list(self.registered_chats):
            self.send_message(cid, summary_markdown, reply_markup=reply_markup)

    def handle_command(self, chat_id: str, text: str, user_id: str = "", username: str = "") -> DeliveryResult:
        update = {
            "message": {
                "chat": {"id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id},
                "from": {"id": int(user_id) if str(user_id).isdigit() else user_id, "username": username},
                "text": text,
            }
        }
        return self.bot.handle_text_command(update)

    def handle_callback_query(self, callback_query_id: str, chat_id: str, data: str) -> DeliveryResult:
        update = {
            "callback_query": {
                "id": callback_query_id,
                "chat_instance": "1",
                "message": {
                    "chat": {"id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id},
                    "message_id": 1,
                },
                "from": {"id": int(chat_id) if str(chat_id).lstrip("-").isdigit() else chat_id},
                "data": data,
            }
        }
        if data.startswith("ctl:"):
            return self.bot.handle_control_callback(update)
        return self.bot.handle_callback_query(update)

    def poll_once(self) -> None:
        """Polls getUpdates once and dispatches incoming messages/callbacks."""
        try:
            updates = self.bot.get_updates(offset=self.last_update_id + 1, timeout=2)
            for upd in updates:
                upd_id = upd.get("update_id", 0)
                if isinstance(upd_id, int) and upd_id > self.last_update_id:
                    self.last_update_id = upd_id
                _route_update(self.bot, upd)
        except Exception as exc:
            logger.warning("Error in poll_once: %s", exc)

    def start_polling(self) -> None:
        """Runs the long-polling worker loop in a background daemon thread."""
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()

        def _loop():
            logger.info("Interactive Telegram Bot polling started.")
            poll_callbacks(self.bot, should_stop=lambda: self._stop_event.is_set(), poll_timeout=20)
            logger.info("Interactive Telegram Bot polling stopped.")

        self._thread = threading.Thread(target=_loop, daemon=True, name="TelegramPollWorker")
        self._thread.start()

    def stop_polling(self) -> None:
        self.is_running = False
        self._stop_event.set()


def main() -> int:
    parser = argparse.ArgumentParser(description="Interactive Telegram Bot Service")
    parser.add_argument("--token", type=str, default=None, help="Telegram Bot Token")
    parser.add_argument("--chat-id", type=str, default=None, help="Authorized Chat ID")
    parser.add_argument("--once", action="store_true", default=False, help="Poll once and exit")
    args = parser.parse_args()

    bot = InteractiveTelegramBot(token=args.token, chat_id=args.chat_id)
    if args.once:
        bot.poll_once()
        print("Polled once cleanly.")
        return 0

    print("🚀 Iniciando Interactive Telegram Bot (Presiona Ctrl+C para detener)...")
    server_type = "Servidor Local 2000 MB (2 GB)" if is_local_bot_api(bot.base_url) else "Cloud Bot API 50 MB"
    print(f"📡 Modo Telegram: {server_type} ({bot.base_url})")
    bot.start_polling()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo bot...")
        bot.stop_polling()
    return 0


if __name__ == "__main__":
    sys.exit(main())
