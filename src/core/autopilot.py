"""
src/core/autopilot.py - Autonomous 24/7 Production AutoPilot Scheduler.

Ports and enriches the cron scheduling service from Temp-/scheduler.ts into a robust,
thread-safe background scheduler for unattended video production batches.
"""
from __future__ import annotations

import random
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from src.log import get_logger

logger = get_logger("autopilot_scheduler")

AUTO_TOPICS: List[str] = [
    "5 Secretos de Inteligencia Artificial que Transformarán 2026",
    "Misterios del Océano Profundo que la Ciencia Apenas Logra Explicar",
    "Cómo los Algoritmos de YouTube Deciden qué Video Hacer Viral",
    "La Historia no Contada detrás de las Mayores Fortunas del Mundo",
    "Avances Cuánticos que Harán Obsoletos los Teléfonos Actuales",
    "Curiosidades del Espacio Exterior que Parecen de Ciencia Ficción",
    "SCP-2000: El Reinicio Oculto de la Humanidad tras el Fin del Mundo",
    "Los 3 Animales Más Letales y Silenciosos del Planeta",
]


class AutoPilotScheduler:
    """Thread-safe 24/7 AutoPilot scheduler for unattended production runs."""

    _instance: Optional["AutoPilotScheduler"] = None
    _lock = threading.Lock()

    def __init__(self, interval_seconds: float = 14400.0) -> None:  # Default: 4 hours (14400s)
        self.interval_seconds = interval_seconds
        self._is_active = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._trigger_callback: Optional[Callable[[str, str], Any]] = None
        self._run_count = 0
        self._last_run_at: Optional[str] = None
        self._last_topic: Optional[str] = None

    @classmethod
    def instance(cls) -> "AutoPilotScheduler":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def set_trigger_callback(self, callback: Callable[[str, str], Any]) -> None:
        """Sets the callback invoked on each scheduled tick: callback(topic, format_mode)."""
        self._trigger_callback = callback

    def is_active(self) -> bool:
        return self._is_active

    def get_stats(self) -> Dict[str, Any]:
        return {
            "active": self._is_active,
            "interval_seconds": self.interval_seconds,
            "interval_hours": round(self.interval_seconds / 3600.0, 2),
            "run_count": self._run_count,
            "last_run_at": self._last_run_at,
            "last_topic": self._last_topic,
        }

    def start(self, interval_hours: Optional[float] = None) -> bool:
        """Starts the AutoPilot scheduler background worker thread."""
        with self._lock:
            if self._is_active:
                logger.info("AutoPilot scheduler is already active.")
                return True

            if interval_hours and interval_hours > 0:
                self.interval_seconds = interval_hours * 3600.0

            self._stop_event.clear()
            self._is_active = True
            self._thread = threading.Thread(target=self._worker_loop, daemon=True, name="AutoPilotWorker")
            self._thread.start()
            logger.info("AutoPilot scheduler STARTED (interval=%.1f hours).", self.interval_seconds / 3600.0)
            return True

    def stop(self) -> bool:
        """Stops the AutoPilot scheduler."""
        with self._lock:
            if not self._is_active:
                return False
            self._stop_event.set()
            self._is_active = False
            logger.info("AutoPilot scheduler STOPPED.")
            return True

    def trigger_now(self, topic: Optional[str] = None) -> Optional[str]:
        """Manually triggers an immediate AutoPilot production tick."""
        chosen_topic = topic or random.choice(AUTO_TOPICS)
        self._run_count += 1
        self._last_run_at = datetime.now(timezone.utc).isoformat()
        self._last_topic = chosen_topic
        logger.info("AutoPilot triggered tick #%d for topic: '%s'", self._run_count, chosen_topic)

        if self._trigger_callback:
            try:
                self._trigger_callback(chosen_topic, "short")
            except Exception as exc:
                logger.error("AutoPilot callback exception: %s", exc)
        return chosen_topic

    def _worker_loop(self) -> None:
        """Internal daemon loop sleeping for interval_seconds between ticks."""
        while not self._stop_event.is_set():
            if self._stop_event.wait(timeout=self.interval_seconds):
                break
            if self._is_active:
                self.trigger_now()
