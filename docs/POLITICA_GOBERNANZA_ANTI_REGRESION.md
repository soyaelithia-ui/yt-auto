# Política de Gobernanza, Cadencia de Verificación y Cláusula de Negativa (Kill Switch)

> **Estado:** NORMA OFICIAL INNEGOCIABLE  
> **Ámbito:** Todos los Agentes de IA, Desarrolladores y Pipelines de Producción  
> **Script de Ejecución:** `scripts/verify_integrity.sh`

---

## 1. Cláusula de Negativa Obligatoria (Work Refusal / Kill Switch)

> [!CAUTION]
> **MANDATO DE DETENCIÓN INMEDIATA**:
> Si en cualquier momento se detecta una violación a los 5 invariantes del sistema, cualquier agente de IA o desarrollador **TIENE LA OBLIGACIÓN FORMAL DE NEGARSE A CONTINUAR TRABAJANDO**, abortar el lanzamiento de pipelines y emitir una alerta crítica inmediata al operador.
>
> **Bajo ninguna circunstancia se permite continuar implementando funcionalidades o generando videos sobre un árbol de trabajo comprometido.**

---

## 2. Los 5 Invariantes Innegociables de Calidad

1. **Aislamiento Absoluto de Medios (Zero-Browser Policy)**:
   - Cero imports de `playwright`, `puppeteer` o invocaciones de `chromium` en `src/media/`, `src/cli/`, `src/narrative/` o `src/core/`.
   - Playwright queda estrictamente restringido a `src/youtube/` para subidas de respaldo a YouTube Studio.
2. **Higiene de Árbol Git (Single SSOT)**:
   - Todo worktree activo debe corresponder a un árbol válido y sincronizado con HEAD. Cero worktrees huérfanos o en estado 'prunable'.
   - La rama `main` debe ser la única rama activa de producción y estar perfectamente sincronizada con `origin/main` en GitHub. Cero ramas muertas o divergentes.
3. **Candado Pre-Commit Activo**:
   - `.githooks/pre-commit` debe estar instalado, tener permisos `+x` y estar configurado en Git (`git config core.hooksPath == .githooks`).
4. **Cero Documentos Resucitados**:
   - Prohibida la existencia de planos antiguos en `docs/architecture/0*.md`.
   - Prohibida la existencia de directorios jubilados (`src/rendering/`, `src/compositing/`, `src/export/`).
5. **Certificación de Suite de Anti-Regresión**:
   - La suite de pruebas de guardrails (`tests/unit/test_anti_regression_guardrails.py`, REG-01 a REG-30) debe aprobar al 100% en tiempo de ejecución.
6. **Cero Vías Procedurales o Matemáticas de Video (100% Asset-Based Pipeline)**:
   - Prohibición permanente de motores procedurales/matemáticos (`wgpu`, shaders WGSL, `src/media/_legacy/`, `proc_engine.py`, `NativeProceduralEngine`, WebGL o canvas2d).
   - Prohibición de bucles de rasterizado frame a frame por software vía Pillow (`_render_scene_pillow_rawvideo`, `force_pillow_rawvideo`).
   - Prohibición de filtros generativos matemáticos de FFmpeg (`gradients=`, `mandelbrot`, `cellauto`).
   - Toda composición se realiza exclusivamente mediante assets reales del catálogo (`LoopVideoEngine` con stream-copy `-c:v copy`, Ken Burns nativo en imágenes fijas, y overlays PNG pre-renderizados en `assets/overlays/`). Fail-closed mediante `CatalogAssetNotFoundError` si falta cualquier asset.

---

## 3. Cadencia de Verificación Obligatoria

La verificación de integridad mediante `./scripts/verify_integrity.sh` es obligatoria bajo las siguientes condiciones de cadencia:

| Disparador | Acción Obligatoria | Comportamiento si Falla |
|---|---|---|
| **Cada 25 Commits** | Auditoría completa automatizada con `./scripts/verify_integrity.sh`. | **Bloqueo**: Refusal activo. No se admite el commit 26 hasta subsanar. |
| **Inicio de Sesión de Agente** | Verificación de liveness y worktrees huérfanos antes de proponer cambios. | **Alerta al Usuario**: El agente notifica la anomalía y ejecuta saneamiento. |
| **Antes de Lanzar Pipeline de Producción** | Auditoría previa al renderizado de video real (carriles largos o Shorts). | **Abort**: El pipeline se niega a arrancar para no saturar CPU/RAM con navegadores. |

---

## 4. Procedimiento Estándar de Auditoría

Para verificar el cumplimiento en cualquier momento:

```bash
./scripts/verify_integrity.sh
```

- **Código de salida `0`**: Sistema saludable. Autorizado para proceder con desarrollo o generación.
- **Código de salida `1`**: Violación de gobernanza. El script detalla los puntos fallidos y activa el rechazo de trabajo.

---

## 5. Prioridad de Valor de Producto y Política Anti-Bloat

> [!IMPORTANT]
> **Mandato de Enfoque**: Los agentes de IA y desarrolladores deben priorizar la entrega de **valor real de producto** (videos publicados y funcionando) sobre la estética o reducción cosmética del código.

### Directivas Clave:
1. **Prohibición de Refactorización Prematura**:
   - Queda terminantemente prohibido emprender reescrituras masivas o fusiones de módulos en `src/` con el único fin de 'reducir líneas de código' si el código actual ya cumple con sus pruebas y contratos de rendimiento.
   - Cualquier refactorización estructural debe estar justificada por un cuello de botella real en producción y aprobada explícitamente por el usuario.
2. **Política Anti-Bloat (Cero Grasa de Terceros)**:
   - Queda terminantemente prohibido hacer commit de librerías minificadas (`*.min.js`), bundles compilados externos o conjuntos de herramientas de terceros (skills ajenos con cientos de archivos `.mjs` o `.js`) dentro del repositorio.
   - Todo módulo auxiliar debe mantenerse como dependencia declarada en `requirements.txt` o ejecutarse fuera del árbol de Git.
   - El candado pre-commit (`.githooks/pre-commit`) abortará automáticamente cualquier commit que contenga archivos minificados o bundles en `.github/skills/` o `assets/vendor/`.
