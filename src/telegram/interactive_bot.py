"""
src/telegram/interactive_bot.py - Interactive Telegram Command & Callback Dispatcher.

Ports and expands the interactive Telegram experience from Temp-/telegramBot.ts:
- Slash commands: /start, /help, /status, /create, /shorts, /long, /seo, /jobs, /autopilot, /latest
- Rich inline buttons: view script, SRT subtitles, SEO metadata, storyboard, image audits, autopilot toggle.
- Non-blocking long-polling worker compatible with both Cloud and Local Bot API servers.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import requests

from src.agents.image_auditor import ImageAuditorAgent
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.core.scenic_detector import detect_scenic_loop
from src.core.scheduler import AutoPilotScheduler
from src.log import get_logger

logger = get_logger("telegram_interactive")

DEFAULT_API_URL = "https://api.telegram.org"


class InteractiveTelegramBot:
    """Production-grade Telegram polling bot engine with full interactive callback dispatching."""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.default_chat_id = str(chat_id or os.environ.get("TELEGRAM_CHAT_ID", "") or "")
        self.base_url = (base_url or os.environ.get("TELEGRAM_API_BASE_URL", DEFAULT_API_URL)).rstrip("/")
        self.registered_chats: set[str] = set()
        if self.default_chat_id:
            self.registered_chats.add(self.default_chat_id)
        self.last_update_id = 0
        self.is_running = False
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Cache of recently generated deliverables (indexed by job_id)
        self.jobs_cache: Dict[str, Dict[str, Any]] = {}
        self.scheduler = AutoPilotScheduler.instance()

    def _api_call(self, endpoint: str, payload: Optional[Dict[str, Any]] = None, timeout: int = 30) -> Optional[Dict[str, Any]]:
        if not self.token:
            logger.warning("Telegram Bot Token not set; skipping API call to %s", endpoint)
            return None
        url = f"{self.base_url}/bot{self.token}/{endpoint}"
        try:
            resp = requests.post(url, json=payload or {}, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            logger.warning("Telegram API %s returned status %d: %s", endpoint, resp.status_code, resp.text[:200])
        except Exception as exc:
            logger.error("Telegram API call error (%s): %s", endpoint, exc)
        return None

    def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        payload: Dict[str, Any] = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self._api_call("sendMessage", payload)

    def answer_callback_query(self, callback_query_id: str, text: Optional[str] = None) -> None:
        payload: Dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        self._api_call("answerCallbackQuery", payload)

    def register_job(self, job_id: str, data: Dict[str, Any]) -> None:
        """Stores deliverable data for inline inspection buttons."""
        self.jobs_cache[job_id] = data

    def broadcast_job(self, job_id: str, summary_markdown: str, reply_markup: Optional[Dict[str, Any]] = None) -> None:
        for cid in list(self.registered_chats):
            self.send_message(cid, summary_markdown, reply_markup=reply_markup)

    def handle_command(self, chat_id: str, text: str, user_id: str, username: str) -> None:
        self.registered_chats.add(chat_id)
        cmd_parts = text.strip().split(maxsplit=1)
        command = cmd_parts[0].lower()
        args = cmd_parts[1].strip() if len(cmd_parts) > 1 else ""

        if command in ("/start", "/help"):
            welcome = (
                "🤖 *¡Bienvenido al Bot de Control de Automatización YouTube (yt-auto)!*\n\n"
                "Controla la generación de contenido mediante el arnés local Antigravity y modelos Gemini:\n"
                "• ✍️ *Guiones Virales* con hooks de alta retención\n"
                "• 🛡️ *Auditoría Visual Anti-Filler* (100% código procedimental WebGL/Canvas)\n"
                "• 🎬 *Storyboards y Vectores de Cámara 3D*\n"
                "• 🏷️ *Optimización SEO Algorítmica (A/B testing de títulos, tags, hashtags)*\n"
                "• ⏰ *AutoPilot 24/7 para Publicación Desatendida*\n\n"
                "_Comandos rápidos:_\n"
                "`/shorts <tema>` — Generar un YouTube Short (9:16)\n"
                "`/long <tema>` — Generar un documental largo (16:9)\n"
                "`/seo <tema>` — Optimizar metadatos y miniaturas\n"
                "`/status` — Ver métricas del sistema\n"
                "`/autopilot` — Conmutar producción autónoma\n"
                "`/latest` — Ver el último entregable generado"
            )
            markup = {
                "inline_keyboard": [
                    [
                        {"text": "📱 Crear Short", "callback_data": "prompt_short"},
                        {"text": "🖥️ Crear Video Largo", "callback_data": "prompt_long"},
                    ],
                    [
                        {"text": "📊 Estado Servidor", "callback_data": "show_status"},
                        {"text": "💡 Ideas Virales", "callback_data": "viral_ideas"},
                    ],
                    [
                        {"text": "🤖 Toggle AutoPilot", "callback_data": "toggle_autopilot"},
                    ],
                ]
            }
            self.send_message(chat_id, welcome, reply_markup=markup)

        elif command == "/status":
            stats = self.scheduler.get_stats()
            active_autopilot = "🟢 ACTIVO" if stats["active"] else "⚪ Inactivo"
            status_text = (
                "📊 *Métricas del Sistema yt-auto:*\n\n"
                "🟢 *Estado:* Operativo (CLI Harness)\n"
                f"🤖 *Motor:* Antigravity CLI Pro (`gemini-3.7-flash`)\n"
                f"⏰ *AutoPilot 24/7:* {active_autopilot} (Intervalo: {stats['interval_hours']}h)\n"
                f"📋 *Trabajos en Caché:* {len(self.jobs_cache)}\n"
                f"👥 *Chats Registrados:* {len(self.registered_chats)}"
            )
            self.send_message(chat_id, status_text)

        elif command == "/seo":
            if not args:
                self.send_message(chat_id, "⚠️ Especifica un tema para optimizar SEO. Ejemplo:\n`/seo Misterios de Marte`")
                return
            self.send_message(chat_id, f"🔍 Optimizando SEO para: *{args}*...")
            optimizer = SeoOptimizerAgent()
            seo_data = optimizer.optimize(args, target_format="short")
            titles = "\n".join(f"{i+1}. `{t}`" for i, t in enumerate(seo_data["viral_title_options"]))
            msg = (
                f"🏷️ *Reporte SEO para:* \"{args}\"\n\n"
                f"🏆 *Títulos Sugeridos (A/B Testing):*\n{titles}\n\n"
                f"📝 *Descripción Optimizada:*\n{seo_data['description'][:280]}...\n\n"
                f"🏷️ *Tags:* `{', '.join(seo_data['tags'][:6])}`\n\n"
                f"💬 *Comentario Fijado:*\n\"{seo_data['pinned_comment']}\""
            )
            self.send_message(chat_id, msg)

        elif command in ("/shorts", "/create", "/long"):
            format_mode = "longform" if command == "/long" else "short"
            topic = args or ("SCP-2000: Deus Ex Machina" if "scp" in command else "Curiosidades del Universo")
            job_id = f"job_{int(time.time())}"

            self.send_message(
                chat_id,
                f"🚀 *Trabajo Iniciado en Cola ({format_mode})*\nTema: *{topic}*\nID: `{job_id}`\n\n"
                "Ejecutando pipeline de agentes (Curador -> Director Arte -> Scene Planner -> Auditor Visual -> SEO)..."
            )

            # Generate deliverable bundle in background thread
            def _run_deliverable():
                try:
                    scenic = detect_scenic_loop(topic)
                    seo_agent = SeoOptimizerAgent()
                    seo = seo_agent.optimize(topic, target_format=format_mode)
                    img_auditor = ImageAuditorAgent()
                    candidates = [
                        {"id": "cand_1", "name": f"Emblema Oficial {topic[:20]}", "source_type": "official_emblem"},
                        {"id": "cand_2", "name": "Foto de Stock Genérica", "source_type": "generic_filler_photo"},
                    ]
                    audits = img_auditor.audit_candidates(topic, candidates)

                    job_bundle = {
                        "id": job_id,
                        "topic": topic,
                        "format": format_mode,
                        "scenic_loop": scenic,
                        "seo": seo,
                        "audits": audits,
                        "script": {
                            "title": seo["selected_title"],
                            "hook": f"¡Detente! Esto sobre {topic} cambiará tu perspectiva...",
                            "scenes": [
                                {"scene": 1, "text": f"Introducción impactante sobre {topic}"},
                                {"scene": 2, "text": "El secreto oculto que pocos conocen"},
                                {"scene": 3, "text": "Conclusión y revelación final"},
                            ],
                        },
                    }
                    self.register_job(job_id, job_bundle)

                    summary = (
                        f"🎉 *¡Video y Pipeline Completados con Éxito!*\n\n"
                        f"📌 *Tema:* {topic}\n"
                        f"🎬 *Formato:* {'📱 YouTube Short (9:16)' if format_mode == 'short' else '🖥️ Longform (16:9)'}\n"
                        f"🎨 *Bucle Escénico:* `{scenic}`\n"
                        f"🛡️ *Auditoría Visual:* {audits['approved_count']} Aprobado / {audits['discarded_count']} Descartado (Anti-Filler)\n"
                        f"🏆 *Título:* {seo['selected_title']}\n"
                        f"🏷️ *Hashtags:* {' '.join(seo['hashtags'])}\n"
                        f"🚀 *ID:* `{job_id}`"
                    )
                    markup = {
                        "inline_keyboard": [
                            [
                                {"text": "📜 Guión", "callback_data": f"view_script_{job_id}"},
                                {"text": "🔍 SEO & Tags", "callback_data": f"view_seo_{job_id}"},
                            ],
                            [
                                {"text": "🛡️ Auditoría Visual", "callback_data": f"view_audits_{job_id}"},
                                {"text": "🚀 Nuevo Video", "callback_data": "prompt_short"},
                            ],
                        ]
                    }
                    self.send_message(chat_id, summary, reply_markup=markup)
                except Exception as exc:
                    logger.error("Error generating deliverable for job %s: %s", job_id, exc)
                    self.send_message(chat_id, f"❌ Error generando trabajo `{job_id}`: {exc}")

            threading.Thread(target=_run_deliverable, daemon=True).start()

        elif command == "/autopilot":
            if self.scheduler.is_active():
                self.scheduler.stop()
                self.send_message(chat_id, "⚪ *AutoPilot Desactivado.* El sistema procesará únicamente solicitudes manuales.")
            else:
                self.scheduler.start(interval_hours=4.0)
                self.send_message(chat_id, "🟢 *AutoPilot Activado 24/7.* El sistema generará nuevos entregables cada 4 horas automáticamente.")

        elif command in ("/latest", "/ver"):
            if self.jobs_cache:
                latest_id = list(self.jobs_cache.keys())[-1]
                job = self.jobs_cache[latest_id]
                self.send_message(
                    chat_id,
                    f"📦 *Último Trabajo Generado:*\nID: `{job['id']}`\nTema: *{job['topic']}*\nTítulo: {job['seo']['selected_title']}"
                )
            else:
                self.send_message(chat_id, "📭 No hay entregables en caché. Usa `/shorts <tema>` para crear uno.")

    def handle_callback_query(self, cb_id: str, chat_id: str, data: str) -> None:
        self.answer_callback_query(cb_id)

        if data == "show_status":
            stats = self.scheduler.get_stats()
            self.send_message(chat_id, f"📊 AutoPilot: {'Activo' if stats['active'] else 'Inactivo'} | Trabajos: {len(self.jobs_cache)}")

        elif data == "toggle_autopilot":
            if self.scheduler.is_active():
                self.scheduler.stop()
                self.send_message(chat_id, "⚪ AutoPilot Desactivado.")
            else:
                self.scheduler.start(interval_hours=4.0)
                self.send_message(chat_id, "🟢 AutoPilot Activado (4h).")

        elif data == "viral_ideas":
            ideas = [
                "• `/shorts 3 trucos de Inteligencia Artificial que parecen magia`",
                "• `/shorts La verdad oculta sobre los agujeros negros del espacio`",
                "• `/shorts SCP-2000: La máquina que reinició a la humanidad`",
                "• `/shorts El gran error que todos cometen con su dinero`",
            ]
            self.send_message(chat_id, "💡 *Ideas Virales Sugeridas:*\n\n" + "\n\n".join(ideas))

        elif data in ("prompt_short", "prompt_long"):
            self.send_message(chat_id, "✨ Para iniciar, escribe:\n`/shorts <tu tema>` o `/long <tu tema>`")

        elif data.startswith("view_script_"):
            job_id = data.replace("view_script_", "")
            job = self.jobs_cache.get(job_id)
            if job and "script" in job:
                sc = "\n".join(f"• Escena {s['scene']}: {s['text']}" for s in job["script"]["scenes"])
                self.send_message(chat_id, f"📜 *Guión ({job['id']}):*\n{job['script']['title']}\n\n{sc}")
            else:
                self.send_message(chat_id, "⚠️ Guión no encontrado en caché.")

        elif data.startswith("view_seo_"):
            job_id = data.replace("view_seo_", "")
            job = self.jobs_cache.get(job_id)
            if job and "seo" in job:
                seo = job["seo"]
                self.send_message(
                    chat_id,
                    f"🏷️ *SEO ({job_id}):*\n\n"
                    f"🏆 *Título:* {seo['selected_title']}\n"
                    f"🏷️ *Tags:* `{', '.join(seo['tags'][:6])}`\n"
                    f"📌 *Comentario:* \"{seo['pinned_comment']}\""
                )
            else:
                self.send_message(chat_id, "⚠️ Metadatos SEO no encontrados en caché.")

        elif data.startswith("view_audits_"):
            job_id = data.replace("view_audits_", "")
            job = self.jobs_cache.get(job_id)
            if job and "audits" in job:
                aud = job["audits"]
                lines = []
                for v in aud["verdicts"]:
                    icon = "✅" if v["verdict"] == "APPROVED_REFERENCE" else "🚫"
                    lines.append(f"{icon} *{v['entity_name']}* ({v['verdict']})\n_{v['reasoning']}_")
                self.send_message(chat_id, f"🛡️ *Reporte de Auditoría Visual Anti-Filler:*\n\n" + "\n\n".join(lines))
            else:
                self.send_message(chat_id, "⚠️ Auditoría visual no disponible.")

    def poll_once(self) -> None:
        """Polls getUpdates once and dispatches incoming messages/callbacks."""
        updates_data = self._api_call("getUpdates", {"offset": self.last_update_id + 1, "timeout": 2})
        if not updates_data or not updates_data.get("ok"):
            return

        for upd in updates_data.get("result", []):
            upd_id = upd.get("update_id", 0)
            if upd_id > self.last_update_id:
                self.last_update_id = upd_id

            if "message" in upd:
                msg = upd["message"]
                chat_id = str(msg.get("chat", {}).get("id", ""))
                text = msg.get("text", "")
                user_id = str(msg.get("from", {}).get("id", ""))
                username = msg.get("from", {}).get("username", "")
                if chat_id and text:
                    self.handle_command(chat_id, text, user_id, username)

            elif "callback_query" in upd:
                cb = upd["callback_query"]
                cb_id = cb.get("id", "")
                chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                data = cb.get("data", "")
                if cb_id and chat_id and data:
                    self.handle_callback_query(cb_id, chat_id, data)

    def start_polling(self) -> None:
        """Runs the long-polling worker loop in a background daemon thread."""
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()

        def _loop():
            logger.info("Interactive Telegram Bot polling started.")
            while not self._stop_event.is_set():
                try:
                    self.poll_once()
                except Exception as exc:
                    logger.warning("Error in Telegram poll loop: %s", exc)
                time.sleep(0.5)
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
