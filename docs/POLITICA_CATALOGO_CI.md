# Política de Catálogo: CI (seed de test) vs Producción

> **Estado:** OFICIAL / REPOSITORIO  
> **Alcance:** `assets/loops/`, catálogo SQLite (`src/core/catalog.py`), `visual_bank` / scenery  
> **Última actualización:** 2026-09  

Norma para agentes y humanos: qué está permitido en CI frente a producción.

## 1. CI / tests

Si `assets/loops/` está vacío (solo `.gitkeep`), fixtures / `isolated_catalog` pueden seedear **placeholders sintéticos** (≥50). Precedente [#71](https://github.com/Ade-ia2005/yt-auto/pull/71). **No** commitear MP4 sintéticos a `main`.

## 2. Producción / `DEFAULT_DB`

No inventar media. Sin archivo real → skip / no publicar basura. Media real = LFS o artefacto, no blobs inventados en el árbol.

## 3. `visual_bank` / scenery

Índice cruzado con disco (precedente [#72](https://github.com/Ade-ia2005/yt-auto/pull/72) / [#74](https://github.com/Ade-ia2005/yt-auto/pull/74)): sin entradas fantasma ni media sintética en scenery.

Clasificación scenery vs title cards / quarantine: [visual-assets-policy.md](visual-assets-policy.md) (no duplicar reglas aquí).

## 4. Qué no hacer

No rellenar `assets/loops/` con basura para “poner CI verde”. No subir placeholders al árbol versionado. No tratar el seed de test como política de prod.

## 5. Persistencia de Métricas de Calidad en Manifiesto (`bank_manifest.json`)

Para evitar decodificación redundante y saturación de CPU en la puerta de control de calidad (`10_qa_gating`), cada activo maestro registrado en `assets/loops/bank_manifest.json` debe persistir obligatoriamente sus métricas visuales certificadas:
- `longest_black_seconds`: duración máxima de cuadros negros (float, típicamente `0.0`).
- `perceptual_luminance`: resumen estructurado de luminancia perceptual conteniendo `avg_luminance`, `dark_ratio`, `passed`, y `luminance_params`.

El motor `LoopVideoEngine.get_loop_quality_metrics` consume este manifiesto; cuando los valores están presentes, `validate_prepublication` sella `black_source = "precomputed_visual"` y `luminance_source = "precomputed_visual"`, omitiendo la ejecución en vivo de FFmpeg.

## 6. Aprovisionamiento de Assets en Worktrees Concurrentes

En entornos multi-agente concurrentes, los repositorios derivados no deben duplicar gigabytes de videos MP4 ni inventar archivos ficticios. El script `scripts/setup_worktree_env.sh`:
- Enlaza simbióticamente `data/loop_catalog.db` desde el repositorio principal (`$PRIMARY_ROOT`).
- Crea enlaces simbólicos individuales para cada video `.mp4` en `assets/loops/` hacia su contraparte física en `$PRIMARY_ROOT`.
- Mantiene los archivos versionados (`bank_manifest.json` y `.gitkeep`) bajo control de Git sin colisiones de estado ni rastreo indebido de binarios.

## 7. Catálogo Permanente de Marca, Ventana de Revisión y Borrado Post-Publicación

A partir de la reestructuración v3.2:
- **Base de Recursos Permanente (6 Bucles Maestros):** El catálogo oficial de producción consta estrictamente de 6 bucles maestros certificados con identidad de marca (3 Horror/Terror, 3 Drama). Todos los clips atómicos no marcados y activos de canales deshabilitados (Sci-Fi) han sido purgados físicamente y del catálogo SQLite (`data/loop_catalog.db`).
- **Canales y Cadencias Oficiales:**
  - 8 Shorts / hora: 4 Horror SCP (`cadence.min_gap_seconds: 900`) + 4 Drama (`cadence.min_gap_seconds: 900`).
  - 3 Videos Largos / hora: 2 Drama AITA (`cadence.min_gap_seconds: 1800`, uno cada 30 min) + 1 Horror (`cadence.min_gap_seconds: 3600`, uno cada 60 min).
  - Canal Sci-Fi inhabilitado (`enabled: false`).
- **Ventana de Revisión para Rechazo (Telegram 2 Horas):** Todo video generado se envía obligatoriamente a Telegram en estado `PENDING_REVIEW` con los metadatos de veredicto técnico adjuntos. El operador humano dispone de una ventana de 2 horas (7200s) para veto/rechazo o aprobación inmediata. Si transcurren las 2 horas sin intervención humana, el barrido automático (`_run_auto_publish_sweep`) lo publica en YouTube (*fail-open programado*).
- **Eliminación Física Local Post-Publicación:** Confirmada la subida pública a YouTube y el respaldo verificado en Google Drive, la rutina `delete_local_post_publication` elimina de `work/<run_id>/` el archivo `.mp4` y los audios TTS (`.mp3`, `.wav`), manteniendo únicamente metadatos ligeros. La permanencia a largo plazo reside 100% en Google Drive.

## Referencias

`src/core/catalog.py` · [OPERACION.md](OPERACION.md) · [MULTICHANNEL_PIPELINE.md](MULTICHANNEL_PIPELINE.md) · [visual-assets-policy.md](visual-assets-policy.md)
