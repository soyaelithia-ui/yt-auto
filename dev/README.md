# Herramientas de Desarrollo y Diagnóstico — `dev/`

Este directorio centraliza las herramientas de desarrollo, diagnóstico, experimentación y gestión operativa del sistema **yt-auto**.

La estructura está organizada de forma funcional en subdirectorios temáticos para mantener el repositorio limpio y desacoplado del entorno de despliegue en producción (`/home/moku/Deploy/YouTubeChannels`).

---

## 📁 Estructura del Directorio

```
dev/
├── diagnostics/              # Auditorías de seguridad, arnés y calidad
│   ├── audit_assets.py       # Auditoría de activos visuales (política anti-filler)
│   ├── audit_security.py     # Auditoría de permisos POSIX y fuga de secretos
│   └── test_pipeline_harness.py # Diagnóstico integral Zero-Quota
│
├── experiments/              # Scripts monográficos y experimentos de video
│   ├── generate_two_videos.py
│   ├── produce_and_upload_upgraded_showcase.py
│   ├── produce_scp5000_10min_and_short.py
│   ├── produce_scp5000_long_and_short.py
│   ├── produce_scp5000_multi_act_cinematic.py
│   ├── publish_new_cosmic_short.py
│   ├── upload_scp5000_cinematic.py
│   ├── upload_scp5000_to_youtube.py
│   └── upload_showcase_to_youtube.py
│
├── tools/                    # Utilidades operativas y herramientas batch
│   ├── deploy_bridge.py      # Puente de monitoreo y sincronización con /home/moku/Deploy
│   ├── produce_batch.py      # Generador de lotes para canales
│   ├── run_telegram_bot.py   # Servicio del bot de Telegram en desarrollo
│   ├── setup_drive_folders.py# Configuración de carpetas en Google Drive
│   └── switch_env.sh         # Conmutador de perfiles (prod / test / dev)
│
└── audit_security.py -> diagnostics/audit_security.py  # Enlace de retrocompatibilidad
```

---

## 📋 Catálogo de Herramientas Principales

| Categoría | Script | Propósito | Ejemplo de Ejecución |
| :--- | :--- | :--- | :--- |
| **Diagnóstico** | `diagnostics/audit_security.py` | Audita que no existan credenciales expuestas ni permisos inseguros. | `python3 dev/diagnostics/audit_security.py` |
| **Diagnóstico** | `diagnostics/audit_assets.py` | Audita candidatos visuales con política estricta anti-filler. | `python3 dev/diagnostics/audit_assets.py --topic "SCP-2000"` |
| **Diagnóstico** | `diagnostics/test_pipeline_harness.py` | Verifica schemas Draft-07, agentes y clasificadores de entorno. | `python3 dev/diagnostics/test_pipeline_harness.py` |
| **Operación** | `tools/deploy_bridge.py` | Supervisa y diagnostica el estado del despliegue en producción. | `python3 dev/tools/deploy_bridge.py status` |
| **Operación** | `tools/produce_batch.py` | Producción en lote para canales (`horror`, `drama`). | `python3 dev/tools/produce_batch.py --count 2` |
| **Operación** | `tools/run_telegram_bot.py` | Ejecuta el bot de Telegram en modo interactivo o de sondeo. | `python3 dev/tools/run_telegram_bot.py --once` |
| **Operación** | `tools/switch_env.sh` | Configura variables de entorno para `prod`, `test` o `cli`. | `source dev/tools/switch_env.sh cli` |

---

## 🔒 Invariantes y Reglas de Integridad
- No modificar el enlace retrocompatible `dev/audit_security.py` requerido por las políticas de pre-commit.
- Todo script dentro de `dev/` debe resolver la raíz del repositorio mediante `Path(__file__).resolve().parents[2]` para asegurar portabilidad en ejecuciones directas.
- Para verificar la integridad completa del repositorio, ejecutar siempre `./scripts/verify_integrity.sh`.
