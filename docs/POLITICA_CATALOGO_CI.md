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

## Referencias

`src/core/catalog.py` · [OPERACION.md](OPERACION.md) · [MULTICHANNEL_PIPELINE.md](MULTICHANNEL_PIPELINE.md) · [visual-assets-policy.md](visual-assets-policy.md)
