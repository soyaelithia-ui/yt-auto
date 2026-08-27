# Herramientas de Desarrollo y Diagnóstico — `dev/`

Este directorio centraliza los scripts de desarrollo, pruebas locales, diagnóstico de arneses y ejecución desatendida del sistema **yt-auto**. Todos los scripts cuentan con cabeceras de documentación técnica, soporte de argumentos estándar mediante `argparse`, logs estructurados con niveles de severidad y códigos de salida POSIX.

---

## 📋 Catálogo de Scripts

| Script | Propósito Principal | Ejemplo de Ejecución |
| :--- | :--- | :--- |
| **`generate_scp_short.py`** | Ejecuta el pipeline completo de 6 agentes para generar un YouTube Short vertical 1080x1920 (9:16). | `python3 dev/generate_scp_short.py --topic "SCP-2000"` |
| **`test_pipeline_harness.py`** | Diagnóstico integral Zero-Quota: verifica el binario `agy`, contratos JSON Schema, agentes y clasificadores. | `python3 dev/test_pipeline_harness.py` |
| **`produce_batch.py`** | Generación en lote de múltiples videos para los canales configurados (`moku`, `aelithia`). | `python3 dev/produce_batch.py --count 3 --channels moku` |
| **`run_telegram_bot.py`** | Inicia el servicio daemon del bot interactivo de Telegram con soporte para slash commands y callbacks. | `python3 dev/run_telegram_bot.py --autopilot` |
| **`audit_assets.py`** | Audita activos visuales candidatos aplicando la política estricta anti-filler. | `python3 dev/audit_assets.py --topic "SCP-2000"` |

---

## 🛠️ Guía de Uso Detallada

### 1. Generador de Shorts SCP (`dev/generate_scp_short.py`)
Ejecuta la cadena completa de agentes:
1. **Agent 1 (Curator)**: Hook de retención 0-3s y estructura en 4 actos.
2. **Agent 2 (Art Director)**: Paleta Rec.709 e iluminación volumétrica.
3. **Scenic Detector**: Identificación del bucle 3D (`scp_facility`).
4. **Agent 5 (Image Auditor)**: Veeduría de activos (descarta relleno/stock, aprueba insignias oficiales).
5. **Agent 6 (SEO Optimizer)**: Títulos A/B virales, tags y conceptos de miniatura.
6. **Agent 3 (Scene Planner)**: Manifiesto canónico `SceneManifestV2`.
7. **Agent 4 (QA Auditor)**: Inspección forense EBU R128 y luminancia.
8. **Telegram**: Envío opcional de vista previa y video final.

```bash
# Ejecución rápida en modo mock (render acelerado)
PYTHONPATH=. python3 dev/generate_scp_short.py --topic "SCP-2000: Deus Ex Machina"

# Ejecución con despacho a Telegram
PYTHONPATH=. python3 dev/generate_scp_short.py --topic "SCP-096: The Shy Guy" --dispatch-telegram

# Ejecución invocando el arnés Antigravity (IA Gemini 3.7 Flash)
PYTHONPATH=. python3 dev/generate_scp_short.py --topic "SCP-2000" --use-agent
```

### 2. Diagnóstico del Arnés (`dev/test_pipeline_harness.py`)
Valida la integridad del sistema en milisegundos sin consumir cuota de APIs ni generar archivos pesados:
```bash
PYTHONPATH=. python3 dev/test_pipeline_harness.py
```

### 3. Producción en Lote (`dev/produce_batch.py`)
Automatiza la preparación de series de videos para canales seleccionados:
```bash
# Producir un lote de prueba de 2 entregables
PYTHONPATH=. python3 dev/produce_batch.py --count 2 --channels moku aelithia --dry-run
```

### 4. Bot Interactivo de Telegram (`dev/run_telegram_bot.py`)
Lanza el proceso de escucha interactiva:
```bash
# Sondeo único de verificación
PYTHONPATH=. python3 dev/run_telegram_bot.py --once

# Iniciar bot con AutoPilot 24/7 activado (genera entregables cada 4 horas)
PYTHONPATH=. python3 dev/run_telegram_bot.py --autopilot --autopilot-interval 4.0
```

### 5. Auditoría de Activos Visuales (`dev/audit_assets.py`)
Evalúa cualquier conjunto de imágenes contra las reglas anti-filler:
```bash
PYTHONPATH=. python3 dev/audit_assets.py --topic "Inteligencia Artificial Cuántica"
```
