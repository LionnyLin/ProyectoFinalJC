# Plan 2 — Refactorización Selectiva sobre `main` (`1f94137`)

Plan sintetizado de modificaciones reales a ejecutar sobre la rama `main`, conservando todas las funcionalidades hidráulicas, entregables y pruebas existentes, y aplicando únicamente mejoras con valor técnico y alineación a `GuiaDocente.md`.

---

## 1. Resumen Ejecutivo: Qué se modifica y qué NO

### Lo que SÍ se va a modificar
1. **Eliminar el hietograma triangular** (motor, modelos, reportes, GUI, pruebas y docs), dejando únicamente lluvia **uniforme** constante (fiel a `DataSetBicentenario.xlsx` y `GuiaDocente.md` §4.1.5).
2. **Eliminar duplicación interna** en `data_loader.py` (Excel vs. CSV) y en `traversals.py` (`bfs`/`dfs` normal vs. animado), manteniendo exactamente las mismas APIs públicas y validaciones.
3. **Mejorar legibilidad y fluidez de gráficas** en `charts_panel.py`: doble eje Y en el hidrograma (`Entrada/Rebose` izq. + `PTAR 31` der.), escala `symlog` adaptativa en utilización y blitting para el cursor temporal.
4. **Modularizar `src/gui/app.py`** (4,964 líneas) extrayendo sus paneles y el recorrido guiado a módulos propios dentro de `src/gui/`, dejando `app.py` como coordinador ligero.
5. **Actualizar pruebas y documentación** afectadas por el retiro de `triangular` y la nueva estructura modular.

### Lo que NO se toca (se conserva íntegro)
- **Estructuras de datos propias** (`src/data_structures/`): `LinkedList`, `Queue`, `Stack`, `HashTable`, `PriorityQueue`, `DirectedGraph`.
- **Capacidades hidráulicas y análisis avanzado**: `PipeIntervention` (obstrucción y cambio de diámetro), `dry_weather_flow_per_source_m3s` opcional (default `0.0`), `split_rule` y `source_distribution`, almacenamiento en pozos + rebose superficial, `compute_source_attribution()`, `classify_overload_persistence()`, `find_isolated_from_sinks()` y `build_route_to_sink()` (perfil longitudinal).
- **Modos cartográficos y UX**: `Instantáneo O(t)`, `Pico Máximo`, `Minutos en Sobrecarga`, recorrido guiado de 4 hallazgos, `src/gui/icons.py` (`Pillow`) y `src/gui/theme.py` (paleta `#4A4A4A`, `#CBCBCB`, `#FFFFE3`, `#6D8196`).
- **Exportación y entregables**: `docx_exporter.py`, `omml_equations.py`, `charts_export.py`, `main.py` (`--report`, `--report-docx`, `--technical-docx`), `data/` y `GuiaDocente.md`.

---

## 2. Mapa Exacto de Archivos a Modificar / Crear

### A. Archivos modificados

| Archivo | Cambio concreto |
| :--- | :--- |
| `src/simulation/models.py` | Retirar el campo `hyetograph` de `SimulationConfig` (lluvia siempre uniforme). |
| `src/simulation/engine.py` | Eliminar `_effective_intensity()` y la rama `"triangular"` de `_interval_mean_intensity()`. |
| `src/simulation/comparison.py` | Quitar el paso de `hyetograph` al construir `SimulationConfig` por escenario. |
| `src/simulation/reporter.py` | Actualizar la línea de perfil temporal a uniforme constante en `storm_duration_min`. |
| `src/io/data_loader.py` | Extraer helpers compartidos `_add_validated_pipe()` y `_finalize_dataset()` para unificar `load_from_excel()` y `load_from_csv_dir()`. |
| `src/algorithms/traversals.py` | Unificar `bfs`/`bfs_anim_frames` y `dfs`/`dfs_anim_frames` con parámetro interno `record_frames=False`, conservando las 4 funciones públicas. |
| `src/gui/theme.py` | Eliminar `HYETOGRAPH_TO_ES` y `ES_TO_HYETOGRAPH`. |
| `src/gui/charts_panel.py` | Añadir `twinx()` en `ax_flow` para `PTAR 31`, `symlog` (`linthresh=100.0`) en `ax_util` cuando pico > `250 %`, y blitting para las líneas cursoras. |
| `src/gui/app.py` | Quitar `var_hyetograph`/`combo_hyetograph` y reducir de ~4,964 L a ~600–800 L delegando la construcción de paneles y tour a los nuevos módulos de `src/gui/`. |
| `tests/test_simulation.py` | Ajustar `test_m1_m2_m3_m8_regressions` para probar integración uniforme con duraciones impares (`storm=1, dt=3, duration=10`). |
| `tests/test_gui.py` | Quitar aserciones de `var_hyetograph_es` / `combo_hyetograph` y mantener cobertura completa de los paneles modularizados. |
| `DOCUMENTACION.md` | Retirar referencias a `Triangular` y actualizar la tabla de módulos de `src/gui/`. |

### B. Archivos nuevos (extracción modular desde `src/gui/app.py`)

| Nuevo archivo | Responsabilidad extraída |
| :--- | :--- |
| `src/gui/widgets.py` | `_ScenarioMenuButton` y helpers reutilizables de botones/tarjetas estilizadas. |
| `src/gui/controls_panel.py` | Panel izquierdo scrollable (`Simulación`, `Recorridos`, tira en vivo `Queue`/`Stack`, bitácora y leyenda). |
| `src/gui/inspector_panel.py` | Pestañas *Inspector* (acciones contextuales, `PipeIntervention`, barra de atribución de fuentes, ficha) y *Tuberías Críticas*. |
| `src/gui/comparison_panel.py` | Pestaña *Comparación* (botón de estado, tabla `tree_comp` con scroll H/V y `ComparisonChartsPanel`). |
| `src/gui/guided_tour.py` | Tarjeta flotante y lógica de paradas del *Recorrido Guiado (4 Hallazgos)*. |

---

## 3. Orden de Ejecución y Criterio de Verificación

1. **Paso 1 — Retiro de `Hietograma` (`triangular`):** `models.py`, `engine.py`, `comparison.py`, `reporter.py`, `theme.py`, retiro del control en `app.py`, ajuste de `tests/` y `DOCUMENTACION.md`.
2. **Paso 2 — Limpieza de duplicación backend:** `data_loader.py` y `traversals.py`.
3. **Paso 3 — Gráficas mejoradas:** `charts_panel.py` (`twinx()`, `symlog`, blitting).
4. **Paso 4 — Modularización GUI:** extracción progresiva de `widgets.py` → `guided_tour.py` → `comparison_panel.py` → `inspector_panel.py` → `controls_panel.py`, manteniendo `app.py` como orquestador.
5. **Paso 5 — Verificación obligatoria tras los cambios:**
   - `python -m unittest discover -s tests -v` (100 % verde sin perder cobertura).
   - `python main.py --report docs/REPORTE_ESCENARIOS.md --report-docx docs/REPORTE_ESCENARIOS.docx --technical-docx docs/DOCUMENTO_TECNICO.docx` y `python -m src.simulation.charts_export`.
   - Exclusión de archivos internos (`AUDITORIA_ERRORES.md`, `PLAN_CORRECCIONES.md`, `PRODUCT.md`, `plan2.md`, `.dsh/`, `.impeccable/`, `.git/`) únicamente al generar el `.zip` de entrega final.
