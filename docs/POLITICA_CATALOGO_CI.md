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

## Referencias

`src/core/catalog.py` · [OPERACION.md](OPERACION.md) · [MULTICHANNEL_PIPELINE.md](MULTICHANNEL_PIPELINE.md) · [visual-assets-policy.md](visual-assets-policy.md)
