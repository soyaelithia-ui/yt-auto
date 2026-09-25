# Política de Gobernanza, Cadencia de Verificación y Cláusula de Negativa (Kill Switch)

> **Estado:** NORMA OFICIAL INNEGOCIABLE | **Ámbito:** Agentes IA, Devs y Pipelines | **Script:** `scripts/verify_integrity.sh`

## 1. Cláusula de Negativa Obligatoria (Work Refusal / Kill Switch)

Si en cualquier momento se detecta una violación a los 6 invariantes del sistema, cualquier agente de IA o desarrollador **TIENE LA OBLIGACIÓN FORMAL DE NEGARSE A CONTINUAR TRABAJANDO**, abortar el lanzamiento de pipelines y emitir una alerta crítica inmediata al operador. Bajo ninguna circunstancia se permite continuar sobre un árbol comprometido.

## 2. Los 6 Invariantes Innegociables de Calidad

1. **Aislamiento Absoluto de Medios (Zero-Browser Policy)**: Cero imports de `playwright` o `chromium` en `src/media/`, `src/cli/`, `src/narrative/` o `src/core/`. Restringido solo a `src/youtube/` para respaldo Studio.
2. **Higiene de Árbol Git (Single SSOT)**: Cero worktrees huérfanos o prunable. La rama `main` debe ser la única activa y sincronizada con `origin/main`.
3. **Candado Pre-Commit Activo**: `.githooks/pre-commit` instalado, ejecutable y configurado (`git config core.hooksPath == .githooks`).
4. **Cero Documentos Resucitados**: Cero planos en `docs/architecture/0*.md` y cero directorios jubilados (`src/rendering/`, `src/compositing/`, `src/export/`).
5. **Certificación de Suite de Anti-Regresión**: La suite de guardrails (`tests/unit/test_anti_regression_guardrails.py`, REG-01 a REG-14) debe aprobar al 100%.
6. **Cero Vías Procedurales o Matemáticas de Video (100% Asset-Based Pipeline)**: Cero `wgpu`, shaders WGSL, Pillow frame loops o filtros procedurales FFmpeg. Composición exclusiva con assets reales (`LoopVideoEngine` stream-copy `-c:v copy`, Ken Burns en fotos reales y overlays). Fail-closed con `CatalogAssetNotFoundError`.

## 3. Cadencia de Verificación Obligatoria

| Disparador | Acción Obligatoria | Comportamiento si Falla |
|---|---|---|
| **Cada 25 Commits** | Auditoría con `./scripts/verify_integrity.sh`. | **Bloqueo**: Refusal activo. No se admite commit 26 hasta subsanar. |
| **Inicio de Sesión de Agente** | Verificación de liveness y worktrees huérfanos. | **Alerta al Usuario**: El agente notifica anomalía y ejecuta saneamiento. |
| **Antes de Lanzar Pipeline** | Auditoría previa al renderizado de video real. | **Abort**: El pipeline se niega a arrancar para proteger recursos. |

## 4. Procedimiento Estándar de Auditoría

```bash
./scripts/verify_integrity.sh
```

- **Salida `0`**: Sistema saludable. Autorizado para proceder.
- **Salida `1`**: Violación de gobernanza. Se activa el rechazo de trabajo.

## 5. Prioridad de Valor de Producto y Política Anti-Bloat

- **Prohibición de Refactorización Prematura**: Prohibido reescribir módulos en `src/` solo para reducir líneas si cumplen pruebas y presupuestos de rendimiento.
- **Política Anti-Bloat (Cero Grasa Externa)**: Prohibido comitear bundles minificados (`*.min.js`) o librerías de terceros dentro del repositorio. Candado pre-commit aborta automáticamente bundles externos.
