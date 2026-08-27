"""Production script to generate 1 Short video and 2 Longform (10-min) videos and dispatch to Telegram."""
import os
import sys
import time
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv

# Ensure environment loaded from .env
env_path = BASE_DIR / ".env"
load_dotenv(env_path, override=True)
os.environ["TEST_MODE"] = "0"
os.environ["MOCK_DRIVE_UPLOAD"] = "1"
os.environ["TELEGRAM_LOCAL"] = "false"

from src.orchestrator.pipeline import PipelineOrchestrator
from src.telegram.notifier import TelegramNotifier
from src.log import get_logger

logger = get_logger("produce_real_videos")

def run():
    notifier = TelegramNotifier()
    orchestrator = PipelineOrchestrator()

    notifier.send_message("🚀 *YT_auto Pipeline*: Iniciando lote de producción real:\n1. 🎬 1 Short de Terror (Canal Moku)\n2. 📽️ 1 Video Largo de 10 min (Canal Moku - Terror/SCP)\n3. 📽️ 1 Video Largo de 10 min (Canal Aelithia - Drama/AITA)")

    jobs = [
        {
            "type": "SHORT",
            "channel": "moku",
            "format_mode": "short",
            "topic": "La criatura que acecha en el pozo abandonado",
            "duration": None,
        },
        {
            "type": "LONGFORM_1",
            "channel": "moku",
            "format_mode": "longform",
            "topic": "El Expediente Secreto del Faro de las Almas Perdidas",
            "duration": 10.2,
        },
        {
            "type": "LONGFORM_2",
            "channel": "aelithia",
            "format_mode": "longform",
            "topic": "Dilema de Herencia: Mi familia ocultó el testamento de mi abuelo",
            "duration": 10.2,
        },
    ]

    for idx, job in enumerate(jobs, 1):
        print(f"\n=======================================================")
        print(f"[{idx}/3] Produciendo {job['type']} para canal '{job['channel']}'...")
        print(f"Tema: {job['topic']}")
        print(f"=======================================================")
        
        notifier.send_message(f"⏳ *[{idx}/3] Procesando {job['type']}* ({job['channel']}):\n`{job['topic']}`")
        
        start_t = time.time()
        try:
            res = orchestrator.run_channel(
                channel=job["channel"],
                format_mode=job["format_mode"],
                topic=job["topic"],
                duration=job.get("duration"),
                dispatch_telegram=True,
            )
            elapsed = time.time() - start_t
            print(f"Resultado de {job['type']}: status={res.status}, error={res.error}, time={elapsed:.1f}s")
            
            if res.status in ("COMPLETED", "PUBLISHED", "READY", "PENDING_REVIEW") or (res.work_dir and os.path.exists(os.path.join(res.work_dir, "video.mp4"))):
                notifier.send_message(f"✅ *{job['type']} Finalizado y Entregado* ({elapsed:.1f}s):\nCanal: {job['channel']}\nEstado: {res.status}")
            else:
                notifier.send_message(f"⚠️ *{job['type']} Finalizado con advertencia*: status={res.status}, err={res.error}")
        except Exception as e:
            print(f"Error procesando {job['type']}: {e}")
            notifier.send_message(f"❌ *Error en {job['type']}*: {str(e)[:200]}")

    notifier.send_message("🎉 *Lote de producción completado*. Todos los videos fueron procesados y enviados para revisión.")
    print("\nLote completado con éxito.")

if __name__ == "__main__":
    run()
