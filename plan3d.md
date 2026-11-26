# Plan Técnico Definitivo: Módulo de Visualización Hidráulica 3D

**Proyecto:** Simulador Hidráulico · Ciudad Bicentenario (`ProyectoFinalJC`)  
**Motor seleccionado:** **Enfoque B — Motor 3D nativo sobre `QPainter` (`PySide6` puro)**  
**Estado:** Especificación definitiva validada contra `engine.py`, `models.py`, `center_panel.py`, `inspector_panel.py` y `data/csv/`  
**Dependencias nuevas:** **Ninguna** (`0` paquetes extra en `requirements.txt`)

---

## 1. Decisiones de Arquitectura y Encaje Exacto en la GUI Actual

### 1.1 Por qué `QPainter` 3D nativo (Enfoque B)
* **Cero dependencias nuevas:** [requirements.txt](requirements.txt) mantiene únicamente `PySide6>=6.7.0`, `matplotlib`, `openpyxl`, `python-docx`, `lxml` y `Pillow` (sin `pyqtgraph`, `PyOpenGL`, `pyvistaqt` ni `numpy`).
* **Cero riesgo en sustentación y tests:** Funciona de forma determinista en cualquier equipo Windows sin depender de drivers OpenGL dedicados y preserva la suite headless (`QT_QPA_PLATFORM=offscreen`) de `tests/test_gui.py` sin mocks gráficos.
* **Rendimiento y coherencia visual:** Con 46 nodos, 59 tuberías y una malla de referencia de $10 \times 10$ celdas (~250–300 primitivas), proyectar `(x, y, z)` con rotación orbital `(yaw, pitch)` y *Z-sorting* toma **< 1–2 ms por frame** (~60 FPS), reutilizando exactamente la paleta Vitela/Grafito, fuentes y escalas cromáticas de `src/gui/theme.py`.

### 1.2 Puntos de integración en la interfaz actual
1. **[CenterPanel](src/gui/panels/center_panel.py):**
   * Reemplazar el montaje directo de `self.network_canvas` dentro de `canvas_block` por un `QStackedWidget` (`self.canvas_stack`):
     * Índice `0`: `self.network_canvas` (Mapa 2D actual, sin cambios).
     * Índice `1`: `self.basin_3d` (`Basin3DWidget`).
   * Añadir a la derecha de `map_mode_bar` un `SegmentedControl` compacto **`2D` | `3D`** (`viewModeChanged = Signal(str)`).
   * **Ventaja:** La franja superior de KPIs (`kpi_header`) y el reproductor inferior (`player_frame` + `timeline_slider`) quedan **100 % compartidos** entre 2D y 3D.
   * **Compatibilidad con Tour Guiado y popups:** Si el usuario activa el `Tour Guiado` mientras está en `3D`, `app.py` conmuta automáticamente a `2D` para preservar el encuadre de `GuidedTourCard` y `animate_focus_region()`.

2. **[InspectorPanel](src/gui/panels/inspector_panel.py):**
   * Incrustar `self.pipe_inspector_3d` (`PipeInspector3DWidget`) dentro de una tarjeta colapsable compacta (**altura útil `128–132 px`** con botón `Visor 3D de tramo ▾ / ▸`) entre `pipe_intervention_card` y `source_attribution_card`, visible **únicamente** cuando hay una tubería seleccionada.
   * Esto permite ajustar obstrucción (`0%–100%`) o diámetro en la tarjeta de intervenciones y observar el efecto inmediato en el tubo 3D sin comprimir `txt_inspector` en pantallas de `768 px` de alto.

3. **[BicentenarioSewerApp](src/gui/app.py) y [AppState](src/gui/state.py):**
   * Añadir `view_mode: str = "2d"` en `AppState`.
   * **Lazy update en `_set_step(step_idx)`:**
     * `basin_3d.set_snapshot(...)` solo se invoca cuando `state.view_mode == "3d"`; en modo `2D` el costo es `0 ms`. Al cambiar `2D → 3D`, se sincroniza inmediatamente con el snapshot, el `map_mode` activo (`instant`, `peak`, `overload`), intervenciones y selección.
     * `pipe_inspector_3d.update_state(...)` solo se actualiza cuando `state.selected_pipe_id` no es `None` y el visor no está colapsado.
   * **Selección bidireccional:** Hacer clic en un nodo o tubería en `Basin3DWidget` emite `nodeSelected(str)` / `pipeSelected(str)` hacia `_on_node_selected` / `_on_pipe_selected`, sincronizando 2D, Inspector y tabla de Críticas.

---

## 2. Blindajes Técnicos Validados contra el Modelo Real (`engine.py` / `models.py`)

### 2.1 Cotas hidráulicas $z_i$ y unidades de `slope` (`elevation.py`)
En `data/csv/node_coords.csv` solo existen coordenadas esquemáticas normalizadas `(x, y) ∈ [0, 1]`; no hay elevación topográfica `z`. En `data/csv/pipes.csv`, `slope = 0.01` ($\text{m/m}$, $1\%$) y `length_m ∈ [51.63, 1149.04]\text{ m}$.

Reglas obligatorias en `compute_network_elevations(graph: DirectedGraph)`:
1. **Guardia de unidades de `slope`:**
   * Por defecto `slope` es fracción $\text{m/m}$ (`0.01`).
   * Si un dataset externo trae pendientes en porcentaje (heurística: mediana o valor $> 0.25$, más parámetro explícito opcional `slope_is_percent: Optional[bool] = None`), convertir como `slope / 100.0` antes de multiplicar por `length_m`.
2. **Múltiples sumideros y protección contra ciclos (Bellman-Ford inverso):**
   * Inicializar `z[sid] = 0.0` para **todos** los nodos en `graph.sink_ids()` y marcarlos en `resolved`.
   * Ejecutar a lo sumo $|V| - 1$ pasadas de relajación aguas arriba sobre todas las aristas $(u \to v)$:
     $$\text{si } v \in \text{resolved}: \quad z[u] = \max\big(z[u],\ z[v] + S_{\text{ef}}(u, v) \cdot L(u, v)\big)$$
   * Detener antes si una pasada no produce cambios. Garantiza terminación y monotonicidad en DAGs e inmunidad ante ciclos en redes externas.
3. **Nodos desconectados (IDW espacial):**
   * Para todo nodo $u \notin \text{resolved}$ (componentes aislados sin salida a sumideros), calcular $z[u]$ por **IDW** con los $k = 3$ vecinos más cercanos en $(x, y)$ dentro de `resolved`:
     $$z[u] = \frac{\sum_{j \in N_k(u)} w_j z[j]}{\sum_{j \in N_k(u)} w_j}, \qquad w_j = \frac{1}{\max(d_{uj}^2,\ 10^{-6})}$$
   * Si el grafo no tuviera ningún sumidero, usar `0.0` de respaldo.
4. **Cota de rasante de referencia ($z_{\text{suelo}, i}$):**
   * Sea $D_{\max, i}$ el diámetro máximo (en metros) entre las tuberías conectadas al nodo $i$ (`0.30 m` si está aislado):
     $$z_{\text{suelo}, i} = z_i + \max(1.5\text{ m},\ 1.5 \cdot D_{\max, i})$$
   * **Aclaración visual obligatoria:** Dado que `(x, y)` proviene de un plano esquemático y `z` se infiere de `slope × length_m`, el HUD del visor 3D etiquetará la superficie como **"Rasante hidráulica de referencia (planta esquemática)"** y no como levantamiento topográfico GIS real.

### 2.2 Subdivisión $10 \times 10$ de la malla de terreno para *Z-sorting*
* `QPainter` usa *painter's algorithm* (no tiene *Z-buffer* por píxel). Un plano único de terreno quedaría completamente delante o detrás de toda la red al orbitar.
* `elevation.py` construye una malla de **$10 \times 10$ celdas (100 quads)** sobre el bounding box ampliado de `(x, y)`, interpolando $z_{\text{suelo}}$ en cada vértice por IDW.
* En cada frame, cada celda, tramo de tubería, nodo, columna piezométrica y disco de rebose se ordena por su profundidad promedio en coordenadas de cámara, permitiendo que las columnas piezométricas atraviesen limpiamente la superficie desde cualquier ángulo.

### 2.3 Coherencia hidráulica en `PipeInspector3DWidget` (incluyendo obstrucción al 100 %)
En [engine.py](src/simulation/engine.py#L470-L489):
* Cuando `eff_q_max > 1e-12`: `flow_m3s` está acotado a `eff_q_max`, mientras `utilization_pct` refleja la demanda entrante acotada al tope físico (`120%`).
* **Caso borde crítico — Obstrucción al 100 % (`eff_q_max <= 1e-12`):** `engine.py` fija explícitamente `is_closed = True`, `flow_m3s = 0.0`, `utilization_pct = 0.0`, `demand_ratio_pct = 0.0`, pero conserva `demand_flow_m3s = q_demand` y `excess_flow_m3s = q_demand`, mientras el pozo aguas arriba (`from_node`) acumula `stored_volume_m3` y rebosa en `surface_flooding_m3` / `flooding_rate_m3s`.

Reglas exactas para `PipeInspector3DWidget` (sin división entre cero):
1. **Caso normal (`not ps.is_closed` y `eff_q_max > 1e-12`):**
   * Usar **`rho = min(1.0, max(0.0, ps.utilization_pct / 100.0))`** para la altura de la lámina de agua dentro del tubo (paridad 100 % con el mapa 2D y la ficha técnica).
   * Si existe obstrucción parcial (`0 < obstruction_pct < 100`), dibujar el depósito/reducción de sección en la solera proporcional a `obstruction_pct / 100.0`.
   * Color del fluido según `ps.utilization_pct`: azul hidráulico (`≤ 75%`), ámbar (`75%–100%`), rojo alerta (`> 100%`).
   * Mostrar el pozo aguas arriba (`from_node`) con nivel de agua proporcional a `stored_volume_m3 / max_manhole_storage_m3` y rebose activo si `ps.utilization_pct > 100%` o `upstream.surface_flooding_m3 > 0` o `upstream.flooding_rate_m3s > 0`.
2. **Caso borde — Obstrucción al 100 % (`ps.is_closed` o `eff_q_max <= 1e-12`):**
   * **Nunca dividir por `eff_q_max`.**
   * Dibujar un **tapón / compuerta de bloqueo físico** (bloque rayado rojo oscuro/grafito en la sección del tramo) con etiqueta visible **`BLOQUEADA 100%`**.
   * Evaluar si hay represamiento aguas arriba:
     ```python
     has_backwater = (
         ps.demand_flow_m3s > 1e-9
         or ps.excess_flow_m3s > 1e-9
         or upstream_stored_m3 > 1e-6
         or upstream_flooding_m3 > 1e-6
         or upstream_flooding_rate_m3s > 1e-9
     )
     ```
   * **Si `has_backwater` es verdadero:**
     * El segmento **aguas arriba del tapón** se dibuja **lleno / represado (`rho = 1.0`) en rojo alerta** (agua retenida contra el bloqueo).
     * El segmento **aguas abajo del tapón** se dibuja **vacío (`0.000 m³/s` conducido)** para reflejar fielmente que no pasa flujo.
     * El **pozo aguas arriba (`from_node`)** se dibuja **lleno / en rebose activo** (columna sobre rasante + alerta de represamiento).
   * **Si `has_backwater` es falso** (ej. Escenario 1 tiempo seco `0 mm/h` o `t = 0 min`):
     * Se muestra el tapón `BLOQUEADA 100% · SIN DEMANDA` con ambos lados secos, reflejando la intervención aplicada sin inventar inundación en tiempo seco.
3. **Tubería cerrada en `Basin3DWidget`:**
   * En la escena 3D de cuenca, cualquier tramo con `ps.is_closed == True` se renderiza con estilo **bloqueado** (color grafito/rojo oscuro con marca central de cierre), evitando que `utilization_pct == 0.0` lo pinte en verde "normal".

### 2.4 Rebose directo en rejillas de fuentes (`vol_inlet_spill`) y modos globales (`peak` / `overload`)
1. **Fuentes rebosando con pozo en `0 m³`:**
   * En [engine.py](src/simulation/engine.py#L367-L380), el exceso que supera la admisión de las 8 fuentes va directo a `surface_flooding_m3` aunque `stored_volume_m3 == 0`.
   * **Regla en `Basin3DWidget`:** Si `surface_flooding_m3 > 1e-6` o `flooding_rate_m3s > 1e-9`, la columna piezométrica del nodo **sube automáticamente por encima de $z_{\text{suelo}, i}$** (independientemente de `stored_volume_m3`) y activa el disco de charco superficial sobre $z_{\text{suelo}, i}$.
   * Si no rebosa: $h_i(t) = z_i + \text{clamp}(V_{\text{pozo}, i}(t) / V_{\max}, 0, 1) \cdot (z_{\text{suelo}, i} - z_i)$.
2. **Modos globales (`Pico Máximo` y `Minutos en Sobrecarga`):**
   * En `t = 90 min` (`snapshots[-1]`), los pozos ya drenaron. Por ello, cuando `map_mode in ("peak", "overload")`, `Basin3DWidget` lee directamente los agregados globales de `SimulationResult`:
     * Tuberías: `result.peak_pipe_utilization` (`peak`) o `result.pipe_overloaded_minutes` (`overload`).
     * Pozos y charcos: `result.max_manhole_storage_m3` y `result.max_node_flooding_m3`.
   * En modo `instant`, lee `snapshot.pipe_states` y `snapshot.node_states` del instante `t`.

---

## 3. Resumen de Mapeo Matemático: Simulación → Geometría 3D

| Elemento 3D | Entrada en el Modelo | Regla Geométrica y Visual |
| :--- | :--- | :--- |
| **Planta $(X, Y)$** | `node.x, node.y` (`node_coords.csv`) | Centrada en $[-1, 1]$ preservando relación de aspecto. |
| **Cota de nodo $z_i$** | `elevation.py` (`pipes.csv` + `sinks.csv`) | Normalizada al dominio $(X, Y)$ con factor `z_exag ∈ {1, 3, 5}`. |
| **Radio de tubería** | `resolve_pipe_hydraulics(edge, interv)` | Proporcional al diámetro efectivo `eff_diam_in` (`8"`..`20"` o intervenido). |
| **Color de tubería** | `utilization_pct` / `peak` / `overload` / `is_closed` | Paridad exacta con `theme.TIER_FILL_DARK`; estilo de bloqueo si `is_closed`. |
| **Columna piezométrica $h_i$** | `stored_volume_m3`, `surface_flooding_m3`, `flooding_rate_m3s` (o picos globales) | Entre $z_i$ y $z_{\text{suelo}, i}$ por llenado de pozo; sobrepasa $z_{\text{suelo}, i}$ si hay rebose (incluye rebose de rejilla en fuentes). |
| **Charco en superficie** | `surface_flooding_m3` (o `max_node_flooding_m3`) | Elipse horizontal sobre $z_{\text{suelo}, i}$ con $R_i = \min(R_{\max}, R_{\min} + k\sqrt{V_{\text{reb}, i}})$. |
| **Lámina en tubo (`Inspector`)** | `utilization_pct`, `is_closed`, `demand_flow_m3s`, `obstruction_pct`, `upstream NodeStepState` | $\rho = \min(1, U/100)$; si `is_closed`, tapón 100 % + represamiento aguas arriba y pozo en rebose si `has_backwater` (cero divisiones por `eff_q_max`). |

---

## 4. Estructura de Archivos

```text
src/
└── gui/
    ├── state.py                     # Añadir view_mode: str = "2d"
    ├── view3d/                      # Paquete autocontenido (PySide6 + QPainter puro)
    │   ├── __init__.py
    │   ├── elevation.py             # Cotas z_i (Bellman-Ford + IDW), guardia slope y malla 10x10
    │   ├── projection.py            # OrbitCamera (yaw, pitch, zoom, pan), proyección 3D→2D y Z-sort
    │   ├── pipe_inspector_3d.py     # PipeInspector3DWidget (lámina, obstrucción parcial/100%, pozo aguas arriba)
    │   └── basin_3d_widget.py       # Basin3DWidget (red enterrada, suelo 10x10, columnas, charcos, HUD, picking)
    └── panels/
        ├── center_panel.py          # QStackedWidget (2D/3D) + selector "2D | 3D" en map_mode_bar
        └── inspector_panel.py       # Tarjeta colapsable con PipeInspector3DWidget al seleccionar tubería
tests/
└── test_view3d.py                   # Pruebas unitarias de elevation, projection, caso borde 100% y widgets offscreen
```

---

## 5. Plan de Implementación por Fases

### Fase 1 — Cimiento Matemático y Visor 3D de Tubería (`elevation.py`, `projection.py`, `pipe_inspector_3d.py`)
1. **`src/gui/view3d/elevation.py`:**
   * Dataclass `ElevationProfile` (`node_z`, `ground_z`, `grid_cells`, `min_z`, `max_z`, `slope_unit_normalized`).
   * `compute_network_elevations(graph, grid_n=10, slope_is_percent=None)` con guardia de `slope`, Bellman-Ford inverso multi-sumidero, IDW para desconectados y malla $10 \times 10$.
2. **`src/gui/view3d/projection.py`:**
   * `OrbitCamera` (`yaw`, `pitch`, `zoom`, `pan_x`, `pan_y`, `project_point`, `screen_scale`, `reset`).
   * Primitivas auxiliares de dibujo 3D para `QPainter` (cápsulas/cilindros con sombreado lateral, polígonos de malla, elipses proyectadas en plano horizontal y utilidades de *Z-sorting*).
3. **`src/gui/view3d/pipe_inspector_3d.py`:**
   * Widget `PipeInspector3DWidget` (`128–132 px` de alto) con vista isométrica de corte longitudinal inclinado según la pendiente real.
   * Implementación completa de:
     * Estado normal y parcial (`rho = min(1, utilization_pct / 100)` + depósito de obstrucción parcial).
     * **Caso borde `is_closed` / `eff_q_max <= 1e-12` (100 % obstruido):** tapón físico + represamiento rojo aguas arriba + pozo aguas arriba en rebose cuando `has_backwater`, y tramo seco aguas abajo (sin división entre cero).
     * Rotación suave al arrastrar + doble clic para resetear ángulo.
4. **Integración en `InspectorPanel` y `app.py`:**
   * Insertar tarjeta colapsable `Visor 3D de tramo` y conectarla a `_refresh_inspector()` y `_set_step()`.
5. **Pruebas Fase 1 (`tests/test_view3d.py`):**
   * Cotas monotónicas aguas arriba, múltiples sumideros, protección ante ciclos, nodos desconectados por IDW, detección de `slope` en `%` vs `m/m`.
   * Render offscreen de `PipeInspector3DWidget` en 4 estados: seco (`0%`), normal (`60%`), sobrecargado (`120%`) y **obstruido al 100 % (`eff_q_max == 0`) con y sin represamiento**.

### Fase 2 — Escena 3D de Cuenca y Toggle `2D | 3D` (`basin_3d_widget.py`, `center_panel.py`)
1. **`src/gui/view3d/basin_3d_widget.py`:**
   * Precalcula `ElevationProfile` una única vez al cargar el grafo (`set_graph`).
   * Dibuja red enterrada (tubos escalados por diámetro efectivo, estilo especial para `is_closed`), nodos y malla $10 \times 10$ semitransparente con *Z-sorting*.
   * HUD flotante minimalista: *Resetear cámara*, *Suelo: `0%` / `45%` / `100%`*, *Escala Z: `1x` / `3x` / `5x`* y nota discreta de *"Rasante hidráulica de referencia (planta esquemática)"*.
   * Controles de ratón: arrastrar = orbitar, `Shift+arrastrar` / clic derecho = pan, rueda = zoom, clic izquierdo = picking de nodo/tubería.
2. **`src/gui/panels/center_panel.py`, `state.py` y `app.py`:**
   * Montar `QStackedWidget` (`2D | 3D`) en `CenterPanel` y cablear *lazy update* en `_set_step()` + conmutación automática a `2D` al iniciar `Tour Guiado`.

### Fase 3 — Dinámica Piezométrica, Charcos de Rebose y Verificación Integral
1. **Columnas piezométricas y charcos en `Basin3DWidget`:**
   * Soporte completo para `instant` (snapshot `t`), `peak` (`max_manhole_storage_m3`, `max_node_flooding_m3`, `peak_pipe_utilization`) y `overload` (`pipe_overloaded_minutes` + máximos de rebose).
   * Regla explícita de rebose de rejilla en fuentes (`surface_flooding_m3 > 0` eleva la columna sobre la rasante aunque `stored_volume_m3 == 0`).
   * Tooltip flotante en 3D y leyenda compacta de capas.
2. **Pruebas y documentación:**
   * Ampliar `tests/test_view3d.py` y `tests/test_gui.py` (toggle `2D ↔ 3D`, lazy update, picking 3D, modos `instant/peak/overload`, obstrucción 100 % en vivo y benchmark de frame `< 5 ms`).
   * Actualizar `DOCUMENTACION.md`.

---

## 6. Criterios de Aceptación
1. **Fidelidad hidráulica y cero errores numéricos:** Cotas monotónicas aguas arriba desde todos los sumideros, paridad cromática exacta con 2D y manejo limpio de `eff_q_max == 0` (obstrucción 100 %) sin `ZeroDivisionError` ni falsos tubos vacíos.
2. **Rendimiento:** Reproducción fluida en Escenario 5 (`10x`) tanto en `2D` (cero impacto por *lazy update*) como en `3D` (`< 5 ms/frame`).
3. **Portabilidad total:** `python -m unittest discover -s tests` pasa completo en modo `QT_QPA_PLATFORM=offscreen` sin instalar paquetes externos adicionales.
