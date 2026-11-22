# Documentación Técnica y Auditoría del Sistema — Simulador Hidráulico Ciudad Bicentenario

Documento técnico generado mediante auditoría directa del código fuente (`main.py`, `src/`, `tests/`) y los conjuntos de datos (`data/csv/`, `data/DataSetBicentenario.xlsx`) del repositorio.

---

## 1. Arquitectura General del Sistema y Flujo de Datos

El proyecto implementa un **simulador hidráulico discreto de red de alcantarillado pluvial-sanitario** modelado como un **Grafo Acíclico Dirigido (DAG)** que drena hacia la **PTAR Punta Canoa (Nodo 31)**. Toda la lógica algorítmica fundamental (grafo, listas enlazadas, colas, pilas, tablas hash y colas de prioridad) está implementada con estructuras de datos propias en `src/data_structures/`.

### 1.1 Estructura de Carpetas y Módulos

| Directorio / Archivo | Responsabilidad Principal | Componentes Clave |
| :--- | :--- | :--- |
| [main.py](<main.py>) | Punto de entrada CLI y GUI | `main()`, `_build_parser()` |
| `src/data_structures/` | Estructuras de datos propias (sin `collections` ni `heapq`) | `HashTable`, `LinkedList`, `Queue`, `Stack`, `PriorityQueue`, `DirectedGraph` |
| `src/io/` | Ingesta, validación topológica/hidráulica y exportación | `load_dataset()`, `load_from_excel()`, `load_from_csv_dir()`, `export_to_csv_dir()` |
| `src/algorithms/` | Recorridos, consultas topológicas y análisis de criticidad | `bfs()`, `dfs()`, `topological_sort()`, `classify_utilization()`, `rank_critical_pipes()`, `compute_source_attribution()` |
| `src/simulation/` | Motor hidráulico discreto, comparación y generación de reportes | `SewerSimulationEngine`, `SimulationConfig`, `PipeIntervention`, `compare_all_scenarios()`, `generate_markdown_report()`, `generate_docx_report()` |
| `src/gui/` | Interfaz gráfica modular Tkinter + Matplotlib embebido | `BicentenarioSewerApp`, `ControlsPanelMixin`, `InspectorPanelMixin`, `ComparisonPanelMixin`, `GuidedTourMixin`, `NetworkCanvas`, `TemporalChartsPanel`, `ComparisonChartsPanel`, `widgets`, `theme`, `icons` |
| `data/` | Conjunto de datos oficial (Excel y CSV equivalentes) | `DataSetBicentenario.xlsx`, `data/csv/*.csv` |
| `tests/` | Suite de pruebas unitarias e integración GUI/DOCX | `test_data_structures.py`, `test_loader.py`, `test_algorithms.py`, `test_simulation.py`, `test_gui.py`, `test_docx_exporter.py` |

### 1.2 Estructuras de Datos Propias (`src/data_structures/`)

1. **`HashTable[K, V]` (`src/data_structures/hash_table.py`):**
   - Implementada mediante **encadenamiento separado** (`List[List[_Entry[K, V]]]`), con capacidad inicial `DEFAULT_CAPACITY = 16` (mínimo `4`) y factor de carga máximo `LOAD_FACTOR_THRESHOLD = 0.75`.
   - Función hash determinista en rango no negativo: `(hash(key) & 0x7FFFFFFF) % capacity`. Al superar el umbral de carga, ejecuta `_rehash()` duplicando la capacidad (`capacity * 2`).
   - Operaciones `put`, `get`, `remove`, `contains` en $O(1)$ amortizado. Se utiliza para indexar nodos, aristas, listas de adyacencia y conjuntos de visitados en recorridos.
2. **`LinkedList[T]` y `DoublyLinkedNode[T]` (`src/data_structures/linked_list.py`):**
   - Lista doblemente enlazada con punteros `_head`, `_tail` y contador `_size` (`DoublyLinkedNode` usa `__slots__ = ("data", "prev", "next")`).
   - Inserción y extracción en ambos extremos (`append`, `prepend`, `pop_front`, `pop_back`) en $O(1)$; acceso indexado `get_at` optimizado por mitad más cercana en $O(n)$; iteración bidireccional `iter_forward()` / `iter_backward()`.
   - Almacena listas de adyacencia en `DirectedGraph` y el historial completo de instantáneas `self.history` en `SewerSimulationEngine`.
3. **`Queue[T]` (`src/data_structures/queue.py`) y `Stack[T]` (`src/data_structures/stack.py`):**
   - `Queue` encapsula `LinkedList` con `enqueue` $\to$ `append` y `dequeue` $\to$ `pop_front` (FIFO en $O(1)$), empleada en `bfs()`, `topological_sort()` (Kahn) y `find_isolated_from_sinks()`.
   - `Stack` encapsula `LinkedList` con `push` $\to$ `append` y `pop` $\to$ `pop_back` (LIFO en $O(1)$), empleada en `dfs()` y `dfs_anim_frames()`.
4. **`PriorityQueue[T]` (`src/data_structures/priority_queue.py`):**
   - **Min-heap binario** respaldado por lista dinámica de tuplas `(priority, _seq, item)`, donde `_seq` garantiza estabilidad FIFO ante empates de prioridad. `push` y `pop` ejecutan en $O(\log n)$ mediante `_sift_up` y `_sift_down`.
   - Se utiliza en dos puntos críticos: (a) cola de eventos de tránsito hidráulico `_TransitEvent` ordenada por `arrival_time_s` en `SewerSimulationEngine.run`, y (b) ordenamiento de tuberías críticas en `rank_critical_pipes`.
5. **`DirectedGraph`, `ManholeNode` y `PipeEdge` (`src/data_structures/graph.py`):**
   - `ManholeNode`: `node_id`, `node_type` (`"manhole" | "source" | "sink"`), coordenadas normalizadas `(x, y)` y `label`.
   - `PipeEdge`: `pipe_id`, `from_node`, `to_node`, `diameter_in`, `diameter_m`, `manning_n`, `slope`, `q_max_m3s`, `length_m`, `note`. Propiedades calculadas:
     $$A_i = \frac{\pi D_i^2}{4}, \qquad V_i = \frac{Q_{\max,i}}{A_i}, \qquad t_i = \frac{L_i}{V_i}\;[\text{s}], \qquad t_{i,\min} = \frac{t_i}{60}$$
   - `DirectedGraph`: mantiene `_nodes`, `_pipes`, listas de adyacencia directa `_adj` e inversa `_radj` (ambas `HashTable[str, LinkedList[PipeEdge]]`), más tablas de fuentes `_sources`, sumideros `_sinks` y listas de orden de inserción `_node_order`, `_pipe_order`. Al agregar una tubería (`add_pipe`), crea automáticamente nodos faltantes como `"manhole"`.

### 1.3 Carga de Datos y Validación (`src/io/data_loader.py`)

`load_dataset(path)` detecta automáticamente si `path` es un directorio (invoca `load_from_csv_dir`) o un archivo `.xlsx` (invoca `load_from_excel` mediante `openpyxl` en modo `data_only=True`).

- **Archivos CSV requeridos en `data/csv/`:**
  - `sources.csv`: 8 nodos fuente (`1, 6, 9, 17, 18, 19, 20, 27`).
  - `sinks.csv`: 1 nodo sumidero (`31`).
  - `pipes.csv`: 59 tuberías (`P1` a `P59`), con longitud total de red de `19,163.57 m`, pendiente uniforme $S = 0.01\;\text{m/m}$ y rugosidad $n = 0.015$. Diámetros comerciales presentes: `8"` ($0.2032\;\text{m}$, $Q_{\max}=0.02965436\;\text{m}^3/\text{s}$), `10"` ($0.254\;\text{m}$, $0.05376693$), `12"` ($0.3048\;\text{m}$, $0.08743095$), `14"` ($0.3556\;\text{m}$, $0.13188335$), `16"` ($0.4064\;\text{m}$, $0.18829343$) y `20"` ($0.508\;\text{m}$, $0.34139870$). Algunas aristas incluyen anotaciones (`**` o `***`, por ejemplo `P1, P3, P5, P13, P21, P28, P29, P30, P38, P57, P58`).
  - `drainage_basin.csv`: `runoff_coefficient_c = 0.75`, `area_ha = 388.0`.
  - `precipitation_scenarios.csv`: 5 escenarios (`1: Dry weather 0.0 mm/h`, `2: Light rain 10.0 mm/h`, `3: Moderate rain 30.0 mm/h`, `4: Heavy rain 60.0 mm/h`, `5: Extreme rain 100.0 mm/h`).
  - `node_coords.csv` (opcional): coordenadas normalizadas $(x, y) \in [0, 1]^2$ y etiquetas para los 46 nodos. Si falta, `_assign_missing_coordinates` (`data_loader.py:147-187`) ubica los nodos automáticamente por capas topológicas mediante algoritmo de Kahn.
- **Carga desde Excel (`DataSetBicentenario.xlsx`):** lee las hojas `Source(s)`, `Sink(s)`, `Pipe(s)`, `Drainage Basin`, `Precipitation Scenarios` (y opcionalmente `Node Coords`). Si `Qmax` falta o es $\le 0$, aplica la fórmula de Manning de respaldo (`data_loader.py:328`):
  $$Q_{\max} = \frac{1}{n} \cdot A \cdot \left(\frac{D}{4}\right)^{2/3} \cdot S^{1/2}$$
- **Reglas de validación (`_validate_dataset`, `data_loader.py:190-220`):** exige al menos 1 tubería, $\ge 1$ fuente, $\ge 1$ sumidero, intersección vacía entre fuentes y sumideros, $0 < C \le 1$, $A > 0$, parámetros geométricos/hidráulicos $> 0$, al menos 1 escenario, y verifica mediante `topological_sort(graph)` que la red sea un **DAG libre de ciclos** (lanza `DataLoadError` si detecta ciclos).

### 1.4 Flujo de Datos Entre Componentes

```text
data/DataSetBicentenario.xlsx  o  data/csv/*.csv
        │
        ▼  src/io/data_loader.py :: load_dataset()
NetworkDataset (DirectedGraph[46 nodos, 59 aristas] + DrainageBasin + 5 PrecipitationScenario)
        │
        ├──► src/algorithms/traversals.py & queries.py
        │       ├── topological_sort()   ──► Orden de propagación en el motor
        │       ├── bfs / dfs / anim     ──► Recorridos y tira visual Queue/Stack en GUI
        │       └── trace_up/downstream  ──► Aislamiento de cuenca & find_isolated_from_sinks()
        │
        ├──► src/simulation/engine.py :: SewerSimulationEngine.run(SimulationConfig)
        │       ├── Usa PriorityQueue (_TransitEvent) para retardo cinemático L/V
        │       ├── Almacena LinkedList de TimeStepSnapshot en engine.history
        │       └── Produce SimulationResult (snapshots[0..N], picos, minutos >100%, error de masa)
        │               │
        │               ├──► src/simulation/comparison.py :: compare_all_scenarios() (5 escenarios)
        │               ├──► src/simulation/reporter.py / docx_exporter.py (.md + _tuberias.csv / .docx + OMML)
        │               └──► src/gui/app.py :: BicentenarioSewerApp
        │                       ├── NetworkCanvas (mapa interactivo + pulsos Manning + anillos rebose)
        │                       ├── TemporalChartsPanel (hidrogramas + % utilización + perfil longitudinal)
        │                       ├── ComparisonChartsPanel (barras >=75% / >100% + curvas PTAR 31)
        │                       └── Inspector / Tabla de Críticas (rank_critical_pipes) / Trazabilidad fuentes
```

---

## 2. Análisis Exhaustivo de la Interfaz Gráfica (UI/UX)

La interfaz está construida sobre Tkinter/ttk (`src/gui/app.py`, 2,069 líneas, junto a los paneles desacoplados `controls_panel.py`, `inspector_panel.py`, `comparison_panel.py` y `guided_tour.py`) con gráficos Matplotlib embebidos (`src/gui/charts_panel.py`), un lienzo cartográfico propio (`src/gui/network_canvas.py`), sistema de tokens cromáticos/tipográficos (`src/gui/theme.py`), controles reutilizables (`src/gui/widgets.py`) e iconos vectoriales rasterizados con Pillow (`src/gui/icons.py`).

> **Catálogo visual unificado:** Las 24 capturas de pantalla viñeta por viñeta están en `docs/screenshots/` (regenerables con `python scripts/capture_doc_screenshots.py`) e incrustadas en el entregable maestro a dos columnas [`docs/DOCUMENTO_TECNICO.docx`](docs/DOCUMENTO_TECNICO.docx).

### 2.1 Sistema Visual, Tipografía, DPI e Iconografía (`theme.py`, `icons.py`)

- **Paleta cromática fija (`src/gui/theme.py:24-75`):**
  - `SHELL_BG = "#4A4A4A"` (Grafito): barra superior, barra de estado, encabezados de láminas y tabla.
  - `DOCK_BG = "#CBCBCB"` (Plata Mineral): muelle de los paneles laterales izquierdo y derecho, barra de modo cartográfico.
  - `CANVAS_BG = "#FFFFE3"` / `PAPER_BG = "#FFFFE3"` (Vitela / Marfil): fondo del lienzo del grafo, tarjetas e inspector.
  - `ACCENT_PRIMARY = "#6D8196"` (Azul Pizarra): filetes, botones primarios, selección y focos activos.
- **Tipografía adaptativa (`theme.py:130-169`):** resuelve por disponibilidad del sistema `Inter` (o `Segoe UI Variable Text`, `Segoe UI`, `DejaVu Sans`) para UI, `Inter`/`Segoe UI Semibold` para títulos, y `Consolas` (o `Cascadia Mono`, `JetBrains Mono`, `DejaVu Sans Mono`) para telemetría numérica.
- **Manejo de DPI (`theme.py:78-127`, `app.py:71-75`):** `enable_dpi_awareness()` activa `SetProcessDpiAwareness(1)` en Windows; `resolve_dpi_scale()` calcula `winfo_fpixels("1i") / 96.0` acotado en `[1.0, 2.0]`. Los lienzos Matplotlib fijan un DPI embebido acotado `_mpl_dpi = min(116, max(96, round(96 * min(1.20, dpi_scale))))` para evitar recortes en pantallas HiDPI.
- **Iconos (`src/gui/icons.py`):** `build_icon_set()` dibuja primitivas Pillow (`ImageDraw`) con supermuestreo `SUPERSAMPLE = 3` (42×42 px reducidos con `Resampling.LANCZOS` a 14×14 px escalados por DPI) para `brand_network`, `play`, `pause`, `step_back`, `step_fwd`, `reset`, `search`, `sliders`, `chart`, `crosshair` y `chevron`.

### 2.2 Disposición General y Adaptabilidad Responsiva (`src/gui/app.py`)

La ventana principal (`BicentenarioSewerApp`, tamaño mínimo `780×540`) se organiza en tres franjas verticales globales (`app.py:434-667`):
1. **Barra superior (`topbar`):** fondo `#4A4A4A`, filete inferior `#6D8196` de 3 px. Contiene insignia, título, subtítulo, botones toggle `Controles` y `Análisis`, y `actions_bar` a la derecha.
2. **Área principal (`main_pane`, `tk.PanedWindow` horizontal):** divide `left_panel` (muelle controles), `center_panel` (telemetría + grafo + reproductor) y `right_panel` (notebook analítico).
3. **Barra de estado inferior (`statusbar`):** muestra `status_var` a la izquierda y `lbl_shortcuts_hint` (`Espacio: Reproducir/Pausar · ←/→: Paso · Ctrl+F: Buscar · Esc: Limpiar`) a la derecha (oculto cuando `width < 980`).

**Reglas responsivas (`_apply_responsive_layout`, `app.py:836-948`):**
- `wide` ($\ge 1180$ px, `theme.BREAKPOINT_MEDIUM`): los 3 paneles pueden estar visibles simultáneamente. En `topbar`, si `width >= 1660` muestra botones individuales (`Cargar Excel`, `Cargar CSV`, `Exportar CSV`, `Supuestos`); si `1220 <= width < 1660` los agrupa en `Menubutton("Archivo y Modelo")`.
- `medium` ($920 \le \text{width} < 1180$ px): oculta el subtítulo, acorta el título a `"Ciudad Bicentenario"` y ajusta `minsize`/`sash_place`.
- `compact` ($< 920$ px, `theme.BREAKPOINT_COMPACT`): impone **exclusividad entre `left_panel` y `right_panel`** (abrir uno cierra automáticamente el otro, ver `toggle_left_panel` / `toggle_right_panel` en `app.py:963-977`), acorta los textos de botones (`Reporte`, `Archivo`, `Guía Esc. N`) y compacta los encabezados de tablas y pestañas.

### 2.3 Desglose de Paneles y Controles Interactivos

#### A. Panel Izquierdo (`left_panel`, scroll vertical con rueda del ratón)
Posee dos pestañas superiores (`Simulación` y `Recorridos`, `_switch_rail_tab`):
- **Pestaña `Simulación` (`app.py:1036-1232`):**
  1. **Lámina *Escenario y parámetros*:**
     - `combo_scenario` (`_ScenarioMenuButton` sobre `tk.Menubutton` + `tk.Menu`): lista los escenarios formateados en español (`theme.format_scenario_display`), pausa la reproducción si está activa antes de abrir y dispara re-simulación inmediata al seleccionar.
     - 5 campos `tk.Spinbox` con re-ejecución debounced a `140 ms` (`_schedule_param_rerun`):
       - `Duración simulación (min)`: rango `10–360`, inc `10`, default `90.0`.
       - `Duración lluvia (min)`: rango `0–360`, inc `5`, default `60.0`.
       - `Paso temporal Δt (min)`: rango `0.5–10.0`, inc `0.5`, default `1.0`.
       - `Ingreso pluvial (%)`: rango `0.5–100.0`, inc `0.5`, default `100.0`.
       - `Caudal sanitario (m³/s)`: rango `0.0–0.05`, inc `0.001`, default `0.000`.
     - Botones preset rápidos: `Oficial Guía (100%)` ($\to 100.0\%,\; Q_{\text{san}}=0.0$) y `Calibrado (2.5% + Q_san)` ($\to 2.5\%,\; Q_{\text{san}}=0.003$).
     - 2 selectores `_ScenarioMenuButton` (`tk.Menubutton` + `tk.Menu` estilizado, inmunes al bug de popdown en blanco bajo Windows `clam` + HiDPI al hacer doble clic sin elegir opción, mapeados ES $\leftrightarrow$ clave interna vía `theme.py`):
       - `Bifurcación`: `"Proporcional"` (`proportional`) | `"Equitativa"` (`equal`).
       - `Reparto fuentes`: `"Por capacidad"` (`capacity`) | `"Uniforme (1/8)"` (`equal`).
     - Botón primario `Ejecutar simulación`: ejecuta `run_simulation(..., auto_play=True)` y arranca la reproducción desde `t = 0`.
  2. **Lámina dinámica de Leyenda (`sec_leg`):** muestra los 5 rangos cromáticos y un contador de tuberías por banda. En `instant` muestra `Escala oficial · t = X min` (`theme.COLOR_SCALE_LEGEND`); en las vistas congeladas globales muestra `Pico máximo · 0–X min` (`theme.COLOR_SCALE_LEGEND`) y `Sobrecarga acumulada · 0–X min` (`OVERLOAD_PERSISTENCE_LEVELS`).

- **Pestaña `Recorridos` (`app.py:1234-1443`):**
  1. **Lámina *Búsqueda y recorridos*:** entrada `entry_search` (`Ctrl+F`, busca por ID/etiqueta/nota con `search_entities` y centra/selecciona el resultado), `combo_bfs_start` (default `"6"`), `combo_bfs_target` (default `"31"`), botones `BFS`, `DFS`, `Limpiar`, `Animar recorrido` (animación paso a paso: `560 ms` BFS, `340 ms` DFS), `Aguas abajo` (`trace_downstream`) y `Aguas arriba` (`trace_upstream`).
  2. **Lámina *Bitácora de recorrido*:** tira visual `_struct_strip_box` que renderiza en tiempo real los primeros 6 elementos de la estructura activa (`Cola (Queue) · FRENTE → FINAL` en BFS o `Pila (Stack) · TOPE ↑` en DFS, resaltando la cabeza en `#6D8196`) y caja de texto oscura `txt_traversal` (`#4A4A4A`).

#### B. Panel Central (`center_panel`, `app.py:1444-1795`)
1. **Franja de telemetría (`kpi_header`):**
   - Fila superior: píldora oscura de contexto (`t = X.X / 90 min · Escenario` en `Instantáneo O(t)`, o `Pico máximo · 0–90 min` / `Sobrecarga acumulada · 0–90 min` en vistas globales) y checkboxes `% Util.` e `IDs` (controlan `show_util_labels` y `show_pipe_labels` en `NetworkCanvas`).
   - Fila de 4 tarjetas KPI sincronizadas con el modo activo: en `Instantáneo O(t)` muestran `UTILIZACIÓN MÁX.`, `CRÍTICAS (>75–100%)`, `SOBRECARGA (>100%)` y `DESCARGA PTAR 31` ($	ext{m}^3/	ext{s}$); en `Pico Máximo` muestran los picos globales `0–duración total` (`PICO MÁX. UTIL.`, `CRÍTICAS PICO`, `SOBRECARGA PICO`, `PICO DESCARGA PTAR 31`); y en `Minutos en Sobrecarga` muestran `MÁX. SOBREC. ACUM.`, `TUBERÍAS >0 min >100%`, `COLAPSO CRÓNICO (>75%)` y `VOLUMEN PTAR 31` ($	ext{m}^3$).
2. **Selector de modo cartográfico (`map_mode_bar`):** selector segmentado de 3 botones (`Instantáneo O(t)`, `Pico Máximo`, `Minutos en Sobrecarga`) con adaptación de texto en 3 anchos (`>=660`, `>=480`, `<480`). `Pico Máximo` y `Minutos en Sobrecarga` operan como **vistas diagnósticas congeladas globales (`0–duración total`)**: al seleccionarlos pausan automáticamente la reproducción, muestran de inmediato los resultados completos calculados por el motor (`peak_pipe_utilization`, `pipe_overloaded_minutes`, `snapshots[-1]`) sin depender del minuto actual del slider ni perder datos al volver a `t = 0`, y conservan `current_step` para restaurarlo al regresar a `Instantáneo O(t)` (o automáticamente al usar `Inicio`, `-1`, `+1`, `Reproducir` o el slider).
3. **Lienzo `NetworkCanvas` + Ficha flotante `_tour_card`:** esta última implementa el **Recorrido Guiado (4 Hallazgos)** (`_build_tour_stops`, `app.py:4145-4649`): define 4 paradas temporales adaptadas a cada escenario (`t = 5, 25, 40/50, 65 min`), resalta el subgrafo relevante, atenúa el resto, enfoca la cámara evitando la ficha (`left_reserve_px`) y muestra métricas clave con botones `Anterior`, `Siguiente hallazgo` y `Cerrar`.
4. **Reproductor temporal (`player_frame`):** botones `Inicio` (`Home`), `-1` (`←`), `Reproducir/Pausar` (`Espacio`), `+1` (`→`), selector `Velocidad` (`1x: 420 ms`, `2x: 210 ms`, `5x: 85 ms`, `10x: 40 ms`), indicador `Balance masa OK · Err X.XXe-XX m³`, y `timeline_slider` horizontal (`0` a `n_snaps - 1`).

#### C. Panel Derecho (`right_panel`, `ttk.Notebook` con 4 pestañas, `app.py:1796-2369`)
1. **Pestaña `Inspector`:**
   - Barra contextual `inspector_actions` (visible al seleccionar nodo o tubería): `Centrar`, `Aislar cuenca` (resalta solo `trace_upstream ∪ trace_downstream` de la entidad seleccionada), y para nodos botones *toggle* `Aguas arriba` / `Aguas abajo` (el segundo clic restaura la vista normal; los botones del panel izquierdo `Recorridos` mantienen limpieza explícita con `Limpiar`).
   - Tarjeta `Intervención en vivo` (visible al seleccionar una tubería): slider `Obstrucción (%)` (`0–100%`, paso `5%`), combobox `Diámetro` (`Original` + `6", 8", 10", 12", 14", 16", 18", 20", 24", 30", 36", 42", 48"`), botones `Aplicar y re-simular`, `Restaurar tramo` y `Restaurar red`. Guarda el estado previo en `_previous_result` para comparar el hidrograma `Antes` vs `Después`.
   - Tarjeta `Composición por Fuente Aportante`: barra apilada monocromática (`canvas_source_bar`, 8 tonos de grafito/pizarra/plata) + texto porcentual generado por `compute_source_attribution()`.
   - Área `txt_inspector`: ficha técnica del nodo o tubería seleccionado + bloque `RESUMEN DEL ESCENARIO`.
2. **Pestaña `Tuberías Críticas`:** 4 radiobuttons mutuamente excluyentes `Todas`, `Resto (≤75%)`, `Críticas (>75–100%)` y `Sobrec. (>100%)`; `ttk.Treeview` (`tree_critical`) alimentada por `rank_critical_pipes()`. Soporta selección bidireccional con el grafo y doble clic para centrar cámara.
3. **Pestaña `Evolución`:** aloja `TemporalChartsPanel`.
4. **Pestaña `Comparación`:** botón con estado de sincronización `Recalcular 5 Escenarios` (se resalta cuando cambian parámetros, conserva timestamp y duración en `lbl_comp_hint` sin sobrescribirse al redimensionar, y también se ejecuta automáticamente al entrar a la pestaña si `_comparisons_dirty`), tabla `tree_comp` envuelta en `comp_table_wrap` con scrollbars horizontal (`Light.Horizontal.TScrollbar`) y vertical (`Light.Vertical.TScrollbar`), soporte `<Shift-MouseWheel>` y columnas `stretch=False` medidas con `tkfont.Font.measure` para mostrar las 8 columnas (incluyendo `Rebose (m³)`) y nombres completos de escenario sin recortes (doble clic activa el escenario en la simulación principal), más el panel `ComparisonChartsPanel`.

### 2.4 Renderizado del Grafo (`src/gui/network_canvas.py`)

`NetworkCanvas` (1,947 líneas) hereda de `tk.Canvas` sobre fondo `#FFFFE3`.

- **Proyección de coordenadas (`_world_to_screen`, `network_canvas.py:928-937`):**
  Con ancho `w`, alto `h`, márgenes adaptativos `pad_x = max(28, min(68, 0.08 * w))` y `pad_y = max(32, min(64, 0.11 * h))`, factor `scale = min(w - 2*pad_x, h - 2*pad_y)` y offsets centrados `off_x`, `off_y`, cada coordenada normalizada $(x, y) \in [0, 1]^2$ se transforma mediante:
  $$x_s = \left(\text{off}_x + x \cdot \text{scale} - \frac{w}{2}\right) \cdot \text{zoom} + \frac{w}{2} + \text{pan}_x$$
  $$y_s = \left(\text{off}_y + y \cdot \text{scale} - \frac{h}{2}\right) \cdot \text{zoom} + \frac{h}{2} + \text{pan}_y$$
  con `zoom` acotado en `[0.55, 4.5]`.
- **Dibujo de nodos y rebose/almacenamiento (`network_canvas.py:1594-1781`):**
  - Radio dinámico proporcional sin piso rígido: calcula `min_node_dist` ($d_{\min}$) entre todo par de nodos y fija $r_{\text{node}} = \max\bigl(2.8, \min(16.5,\; 10.4 \cdot s \cdot \sqrt{\text{zoom}} \cdot \text{dpi\_boost},\; 0.30 \cdot d_{\min})\bigr)$ (incrementado proporcionalmente en el sumidero `node_type == "sink"`), escalando también grosores, anillos, separación de extremos y `arrowshape`. Los textos internos de nodos, tuberías y placas usan tamaños en **píxeles exactos** (negativos en Tkinter) inmunes al escalado DPI de Windows, ocultando el ID interno cuando $r_{\text{node}} < 5.6\;\text{px}$ (salvo sumidero o nodo seleccionado) manteniendo siempre el tooltip.
  - Colores base y placas sin colisión: **Fuente** (`#6D8196`, borde `#3E4F60`, texto `#FFFFE3`, insignia `"Fuente"`), **Pozo** (`#FFFFE3`, borde `#4A4A4A`, texto `#4A4A4A`), **Sumidero PTAR** (`#4A4A4A`, borde `#6D8196`, texto `#FFFFE3`, insignia `"PTAR Punta Canoa · 31"` con respaldo compacto `"PTAR · 31"`). Las placas se ubican mediante detección de colisiones (`_overlay_boxes`, `_boxes_overlap`, `_box_hits_segment`) evitando nodos vecinos, tuberías y barras flotantes antes de colocar etiquetas de tuberías.
  - **Saturación / rebose nodal (`_draw_flood_rings`, `network_canvas.py:854-888`):** cuando `surcharge_vol = stored_volume_m3 + surface_flooding_m3 > 1e-3`, dibuja **1 o 2 anillos concéntricos** (`flood_ring`) alrededor del pozo con radio creciente logarítmicamente `extra = min(14.0, (4.5 + 3.6 * log10(1.0 + surcharge_vol)) * scale * sqrt(zoom))`: tono naranja `#f97316` si el volumen es moderado ($\le 0.5\;\text{m}^3$ sin rebose superficial), o rojo `#ef4444` / doble anillo `#dc2626` + `#FCA5A5` cuando hay rebose superficial o sobrecarga severa.
- **Dibujo de aristas dirigidas e intervenciones (`network_canvas.py:1244-1592`):**
  - Se dibujan como líneas con flecha terminal (`arrow=tk.LAST`) recortadas en ambos extremos por `node_radius + 1.5` y `node_radius + 3.0`.
  - Grosor proporcional al diámetro efectivo: $\text{base\_width} = 2.0 + (D_{\text{ef},\text{in}} - 8.0) \times 0.24$, escalado por `sqrt(zoom) * scale_factor` y sumando `+1.5 px` cuando está sobrecargada.
  - **Estados visuales especiales:** halo rojo suave (`#FECACA`) bajo tramos sobrecargados; doble línea paralela en `#6D8196` cuando $D_{\text{ef}} > D_{\text{orig}}$ (marca `[ØXX"]`); barras perpendiculares naranja/rojo o `×` de cierre al 100% con guionado `(3, 3)` (`_draw_obstruction_bars`, marca `[OBST XX%]`); línea discontinua atenuada para nodos/tuberías aislados de la PTAR (`[AISLADO DE 31]`).
  - **Pulsos animados de flujo (`_tick_pulses`, `network_canvas.py:725-800`):** cuando `_is_playing == True` y `anim is None`, un timer cada `_PULSE_TICK_MS = 55 ms` avanza hasta 3 marcadores `▸` por tubería usando la velocidad efectiva de Manning (`_BASE_PX_PER_MPS = 28.0 px/s` por m/s), mostrando visualmente el sentido del flujo y su rapidez relativa.
  - **Optimización de reproducción (`_fast_update_snapshot`, `network_canvas.py:300-408`):** durante la reproducción temporal, actualiza colores, grosores, halos, anillos de rebose y textos de etiquetas *in-place* mediante `itemconfigure` sobre las referencias cacheadas (`_pipe_draw_refs`, `_pipe_label_refs`), evitando reconstruir los objetos del canvas en cada paso.
  - **Etiquetas sin solapamiento:** ordena la cola `label_queue` por prioridad (marcas técnicas, badges `>100%`, selección, foco, sobrecarga, criticidad) y utiliza `placed_boxes` con desplazamiento perpendicular (`nudge` `3.5 / 6.0 px`) descartando las que colisionen.
- **Eventos de interacción (`network_canvas.py:939-1180`):**
  - `<ButtonPress-1>` / `<B1-Motion>` / `<ButtonRelease-1>`: clic selecciona nodo o tubería (con tolerancia de `9 px` a segmentos); arrastre $>4\;\text{px}$ ejecuta pan del lienzo.
  - `<MouseWheel>` / `<Button-4>` / `<Button-5>`: zoom centrado en el cursor (`×1.12` / `÷1.12`).
  - `<Double-Button-1>`: restablece vista (`reset_view()`).
  - `<Motion>`: tooltip flotante contextual tras `220 ms` de reposo sobre una entidad (muestra diámetro, $Q$, $Q_{\max}$, % utilización física, demanda $\times Q_{\max}$, tránsito, o entradas/salidas/pozo/rebose del nodo) + barra superior izquierda `_stamp_lbl` (título de mapa), controles de zoom `+` / `−` / `⟲` (`_zoom_bar`) y leyenda de interacción inferior derecha (`_hint_bar`).

### 2.5 Panel de Gráficos y Telemetría (`src/gui/charts_panel.py`)

1. **`TemporalChartsPanel` (`charts_panel.py:13-336`):**
   - **Sub-pestaña 1 — `Hidrograma y %`:** figura Matplotlib 2×1 (`ax_flow` arriba, `ax_util` abajo) con eje X compartido `Tiempo (min)`:
     - `ax_flow`: curva `Entrada total` (`#4A4A4A`), curva + relleno `PTAR 31` (`#6D8196`), línea discontinua `Antes (PTAR)` si existe `_previous_result` tras una intervención, y **cursor vertical rojo (`#ef4444`)** en `t = current_time_min` que se actualiza sin redibujar toda la figura durante la reproducción (`_move_time_cursor`).
     - `ax_util`: si hay tubería seleccionada muestra su utilización física (`%`) y una curva punteada de demanda (`×Qmax`) si supera `100.5%` (más curva `Antes` si hubo intervención); si no hay selección grafica las **Top 3 tuberías críticas** por pico histórico. Incluye línea horizontal `100%`.
   - **Sub-pestaña 2 — `Perfil longitudinal (Q vs Qmax)`:** obtiene la ruta dirigida hacia `31` mediante `build_route_to_sink()` (del elemento seleccionado, o `P31` por defecto) y dibuja barras horizontales/verticales agrupadas de `Capacidad Qmax` (`#B3B8BE`) vs `Caudal físico Q(t)` en el paso `current_step_index` coloreado según `classify_utilization()`, anotando `% utilización` o `Dem. X.X×` sobre cada barra.
   - **Sincronización con $t$ y rendimiento:** `update_plots()` aplica throttling a `85 ms` cuando `throttle_draw=True` (durante reproducción activa) y fuerza redraw exacto al pausar o cambiar de pestaña; `_sync_figure_size` iguala el `figsize` en pulgadas al tamaño real del widget dividido por el DPI fijo para evitar saltos de escala.
2. **`ComparisonChartsPanel` (`charts_panel.py:339-473`):**
   - Grafica las métricas globales de los 5 escenarios: `ax_bar` (barras agrupadas excluyentes `Críticas (>75–100%)` en `#ef4444` vs `Sobrec. (>100%)` en `#991b1b`) y `ax_ptar` (los 5 hidrogramas de descarga en `PTAR 31`).
   - Reorganiza automáticamente entre diseño vertical (`2×1`) cuando `h >= w * 0.86` y horizontal (`1×2`) cuando el panel es ancho.

---

## 3. Modos de Operación, Escenarios y Consideraciones del Modelo

### 3.1 Modos de Simulación y Operación Existentes en el Código

1. **Escenarios de precipitación (`data/csv/precipitation_scenarios.csv`):**

| ID | Condición (Dataset) | Nombre UI (ES) | Intensidad $I$ (mm/h) | Comportamiento Típico (Config. por Defecto) |
| :---: | :--- | :--- | :---: | :--- |
| 1 | `Dry weather` | Tiempo seco | `0.0` | Sin lluvia ni $Q_{\text{san}}$ por defecto ($0.000\;\text{m}^3/\text{s}$); toda la red en `0.0 %`. |
| 2 | `Light rain` | Lluvia ligera | `10.0` | Primeros tramos críticos; cuello local en `P25`. |
| 3 | `Moderate rain` | Lluvia moderada | `30.0` | Escenario base CLI/GUI; saturación de cabeceras de 8" y colector `P25`. |
| 4 | `Heavy rain` | Lluvia fuerte | `60.0` | Presurización extendida y rebose superficial relevante. |
| 5 | `Extreme rain` | Lluvia extrema | `100.0` | Demanda $>4\times Q_{\max}$ en cabeceras; alto rebose en vía. |

2. **Modos de distribución entre nodos fuente (`SimulationConfig.source_distribution`, `engine.py:60-92`):**
   - **`"capacity"` (*Por capacidad*, valor por defecto):** reparte el caudal pluvial efectivo de la cuenca proporcionalmente a la capacidad instalada de salida de cada nodo fuente:
     $$w_s = \frac{\sum_{e \in \text{out}(s)} Q_{\max,e}}{\sum_{s' \in S} \sum_{e \in \text{out}(s')} Q_{\max,e}}$$
   - **`"equal"` (*Uniforme (1/8)*):** reparte el caudal pluvial en partes iguales entre todas las fuentes activas ($w_s = 1 / |S|$, con $|S| = 8 \implies 12.5\%$ cada una).
3. **Reglas de reparto en nodos de bifurcación (`SimulationConfig.split_rule`, `engine.py:242-255`):**
   - **`"proportional"` (*Proporcional a capacidad*, valor por defecto):** si un nodo tiene $k > 1$ tuberías salientes, el volumen disponible se divide en proporción a la capacidad efectiva $Q_{\max,\text{ef},e}$ de cada salida (si todas tienen capacidad nula, usa $1/k$).
   - **`"equal"` (*Equitativa*):** divide el flujo disponible por igual entre todas las tuberías salientes ($w_e = 1/k$).
4. **Perfil temporal de lluvia (`engine.py`):** bloque **uniforme** constante, $I_{\text{ef}}(t) = I_{\text{media}}$ para $0 < t \le t_{\text{lluvia}}$ y $0$ para $t > t_{\text{lluvia}}$.
5. **Presets de ingreso y calibración en GUI:**
   - `Oficial Guía (100%)` *(predeterminado)*: `ingress_factor = 1.0`, `dry_weather_flow_per_source_m3s = 0.0`.
   - `Calibrado (2.5% + Q_san)` *(análisis de sensibilidad)*: `ingress_factor = 0.025`, `dry_weather_flow_per_source_m3s = 0.003`.
6. **Modos de lectura cartográfica (`network_canvas.py`):** `"instant"` (utilización instantánea en $t$), `"peak"` (vista congelada global del pico máximo en $0\text{–}t_{\text{total}}$) y `"overload_minutes"` (vista congelada global de minutos acumulados con utilización $> 100\%$ en $0\text{–}t_{\text{total}}$).
7. **Intervenciones en vivo (`PipeIntervention`):** obstrucción parcial/total ($0\%–100\%$) y cambio de diámetro comercial por tubería sin mutar el `DirectedGraph` base.
8. **Modos de ejecución:** aplicación interactiva GUI (por defecto en `main.py`) o generación batch por CLI (`--report`, `--report-docx`, `--technical-docx`).

### 3.2 Supuestos y Consideraciones Hidráulicas del Motor

Implementados en `src/simulation/models.py` y `src/simulation/engine.py`:
1. **Hidrología por Método Racional agregado:** convierte lluvia sobre la cuenca ($C=0.75$, $A=388.0\;\text{ha}$) mediante el factor SI $0.00278\;(\text{m}^3/\text{s})/(\text{mm/h}\cdot\text{ha})$ integrado analíticamente sobre cada sub-intervalo $[t_a, t_b]$ (`_interval_mean_intensity`) con `ingress_factor = 1.0` (100 % por defecto).
2. **Caudal sanitario base ($Q_{\text{san}}$):** `dry_weather_flow_per_source_m3s = 0.0 m³/s` por defecto (configurable opcionalmente desde la GUI o `SimulationConfig` para análisis de sensibilidad).
3. **Flujo uniforme / permanente por paso de tiempo:** la capacidad y velocidad de referencia en cada tramo provienen de la ecuación de Manning a tubo lleno ($S=0.01$, $n=0.015$). No se resuelven las ecuaciones completas de Saint-Venant (inercia, gradiente de presión ni remanso aguas arriba).
4. **Tránsito cinemático continuo mediante sub-pasos internos:** internamente el motor integra con sub-pasos $\Delta t_{\text{sim}} \le \min(\Delta t_{\text{usuario}},\; 10\;\text{s},\; 0.25 \cdot t_{\min,\text{red}})$ para garantizar que ninguna tubería se cruce instantáneamente dentro de un mismo intervalo. Cada paquete enviado al final del sub-paso $t_{\text{sub}}$ se encola en la `PriorityQueue` con llegada $t_{\text{llegada}} = t_{\text{sub}} + t_{\text{trans},i}$, manteniendo la descarga invariante frente a $\Delta t_{\text{usuario}}$.
5. **Orden topológico y acoplamiento nodal:** el barrido nodal en cada sub-paso sigue `topological_sort(graph)`.
6. **Capacidad finita de almacenamiento en pozos y rebose en vía:** cada pozo no sumidero tiene capacidad máxima `max_manhole_storage_m3 = 4.0 m³`. Cuando la salida está restringida por $Q_{\max,\text{ef}}$, el excedente se almacena en el pozo hasta $4.0\;\text{m}^3$; todo volumen adicional por encima de $4.0\;\text{m}^3$ pasa a **rebose superficial acumulado** (`node_flooded[u]`) y **no reingresa a la red** en pasos posteriores, quedando auditado en la conservación global de masa.
7. **Condiciones de frontera:**
   - **Fuentes (`source`):** reciben inyección externa en cada sub-paso más cualquier eventual llegada interna; sus pozos siguen las mismas reglas de salida, almacenamiento y rebose.
   - **Sumidero / PTAR (`sink`):** descarga libre sin restricción de capacidad (`cum_sink_m3 += avail_vol`). La carga de red rechaza nodos intermedios sin salida y fuentes aisladas de sumideros (`_validate_graph_and_data`).
8. **Paso de integración temporal y horizonte:** $\Delta t = 1.0\;\text{min}$ ($60\;\text{s}$) por defecto sobre `duration_min = 90.0 min` (emitiendo `91` instantáneas en $t = 0, 1, \dots, 90\;\text{min}$, recortando exactamente el último paso si `duration_min` no es múltiplo de $\Delta t$), con lluvia activa hasta `storm_duration_min = 60.0 min`.

---

## 4. Lógica Matemática del Manejo de Porcentajes de Uso y Clasificación

### 4.1 Capacidad Hidráulica Máxima ($Q_{\max}$) e Intervenciones

Para cada tubería $i$ en condiciones base, el dataset provee $D_i$ (en pulgadas y metros), $n_i$, $S_i$, $L_i$ y $Q_{\max,i}$. Cuando $Q_{\max}$ se calcula desde cero en `src/io/data_loader.py:328`, se usa Manning a sección circular llena ($R_h = D_i / 4$, $A_i = \pi D_i^2 / 4$):
$$Q_{\max,i} = \frac{1}{n_i}\,A_i\,\left(\frac{D_i}{4}\right)^{2/3}\,S_i^{1/2}$$

Cuando existe una `PipeIntervention(pipe_id, obstruction_pct, diameter_in_override)`, la función `resolve_pipe_hydraulics()` (`src/simulation/models.py:38-61`) recalcula los parámetros efectivos usando las leyes de escala de Manning ($Q \propto D^{8/3}$ y $V \propto D^{2/3}$):
$$\text{scale}_D = \frac{D_{\text{ef},i}}{D_{i}}, \qquad Q_{\text{diam},i} = Q_{\max,i} \cdot \text{scale}_D^{8/3}, \qquad V_{\text{ef},i} = V_i \cdot \text{scale}_D^{2/3}$$
$$f_{\text{apertura},i} = \max\!\left(0.0,\; 1.0 - \frac{p_{\text{obst},i}}{100}\right), \qquad Q_{\max,\text{ef},i} = Q_{\text{diam},i} \cdot f_{\text{apertura},i}, \qquad t_{\text{trans},\text{ef},i} = \frac{L_i}{V_{\text{ef},i}}$$

### 4.2 Porcentaje de Utilización Oficial, Caudal Conducido y Pico Histórico

En cada intervalo del motor (`SewerSimulationEngine.run()`, `src/simulation/engine.py`):
1. **Volúmenes y caudales en el tramo $i = (u \to v)$:**
   - Volumen demandado desde el nodo $u$: $V_{\text{dem},i} = V_{\text{disp},u} \cdot w_i$ (incluye llegadas nuevas del intervalo y descarga del almacenamiento acumulado en el pozo).
   - Capacidad del paso: $V_{\text{cap},i} = Q_{\max,\text{ef},i} \cdot \Delta t_{\text{sim}}$.
   - Volumen efectivamente conducido: $V_{\text{env},i} = \min(V_{\text{dem},i}, V_{\text{cap},i})$, y exceso retenido aguas arriba: $V_{\text{exc},i} = \max(0,\; V_{\text{dem},i} - V_{\text{cap},i})$.
   - Caudal conducido real (coherente al 100 % con `node.outflow_m3s`):
     $$Q_{\text{cond},i}(t) = \frac{V_{\text{env},i}}{\Delta t_{\text{sim}}} \le Q_{\max,\text{ef},i}$$
   - Caudal de demanda total sobre el tramo (considerando el aporte solicitado desde el nodo más el caudal en tránsito):
     $$Q_{\text{dem},i}(t) = \max\!\left(\frac{V_{\text{dem},i}}{\Delta t_{\text{sim}}},\; Q_{\text{cond},i}(t),\; \frac{V_{\text{tránsito},i}}{t_{\text{trans},\text{ef},i}}\right)$$

2. **Cálculo del porcentaje de utilización oficial $O_i(t)$ sin techo artificial:**
   - **Caso tubo cerrado ($Q_{\max,\text{ef},i} \le 10^{-12}$):** `is_closed = True`, $Q_{\text{cond},i} = 0$, $O_i(t) = 0.0\%$ y `is_overloaded = False`.
   - **Caso tubo abierto ($Q_{\max,\text{ef},i} > 10^{-12}$):** aplicando directamente la fórmula de la guía (§5.5) sobre la demanda real del tramo, sin techo artificial de `115 %`:
     $$O_i(t) = \frac{Q_{\text{dem},i}(t)}{Q_{\max,\text{ef},i}} \times 100, \qquad D_i(t) = O_i(t), \qquad \text{PipeStepState.flow\_m3s} = Q_{\text{cond},i}(t)$$

3. **Máximos en todo el horizonte y tiempo en sobrecarga (`engine.py:397-412`):**
   - `peak_pipe_utilization[pid]` $= \max_{t} U_i(t)$ y `peak_pipe_demand_ratio[pid]` $= \max_{t} D_i(t)$.
   - `pipe_overloaded_minutes[pid]`: acumula $+\Delta t_{\min}$ por cada paso $k \ge 1$ en que $U_i(t_k) > 100.0\%$ (es decir, cuando `pid` pertenece a `snap.overloaded_pipe_ids`).

### 4.3 Umbrales Exactos de Clasificación Visual y Estadística

Definidos en `src/algorithms/analysis.py:9-40` (`classify_utilization`) y `src/gui/theme.py:66-72` (`COLOR_SCALE_LEGEND`):

| Banda | Rango de $U_i(t)$ (%) | Etiqueta Oficial | Color (`analysis.py`) | Color en Canvas / Leyenda GUI | Flags booleanos |
| :---: | :--- | :--- | :---: | :---: | :--- |
| 0 | $0\% \le U \le 25\%$ | Baja utilización | `#22c55e` | `#22c55e` | `is_critical=False`, `is_overloaded=False` |
| 1 | $25\% < U \le 50\%$ | Utilización moderada | `#eab308` | `#eab308` | `is_critical=False`, `is_overloaded=False` |
| 2 | $50\% < U \le 75\%$ | Utilización alta | `#f97316` | `#f97316` | `is_critical=False`, `is_overloaded=False` |
| 3 | $75\% < U \le 100\%$ | Cercana a la capacidad máxima | `#ef4444` | `#ef4444` | **`is_critical=True`**, `is_overloaded=False` |
| 4 | $U > 100\%$ | Capacidad excedida | `#991b1b` | `#991b1b` | **`is_critical=True`**, **`is_overloaded=True`** |

**Reglas exactas de conteo y ranking:**
- **Frontera exacta `> 75.0 %`:** tanto `classify_utilization()` como `engine.py` y `rank_critical_pipes()` usan estrictamente `U > 75.0` para la banda 3 (`Cercana a la capacidad máxima`) y `U > 100.0` para la banda 4 (`Capacidad excedida`).
- **Conjuntos separados y unión crítica:**
  - `near_capacity_pipe_ids` / `ever_near_capacity_pipes`: tramos exclusivamente en **$75\% < U \le 100\%$** (`Críticas (>75–100%)`).
  - `overloaded_pipe_ids` / `ever_overloaded_pipes`: tramos exclusivamente en **$U > 100\%$** (`Sobrec. (>100%)`).
  - `critical_pipe_ids` / `ever_critical_pipes`: unión acumulada de cualquier tramo con $U > 75.0\%$ (en un horizonte completo una misma tubería puede visitar ambos rangos en distintos instantes).
- **Ordenamiento en `rank_critical_pipes()` (`analysis.py:59-115`):** utiliza `PriorityQueue` con clave de prioridad `(-utilization_pct, -demand_ratio_pct)`, posicionando primero los tramos con mayor utilización física y desempatando por mayor razón de demanda.
- **Clasificación de persistencia de sobrecarga (`classify_overload_persistence`, `analysis.py:127-141`):** sobre `pct_dur = (overloaded_min / total_duration_min) * 100`: `0 min` (`#22c55e`), $\le 25\%$ (`#eab308`), $\le 50\%$ (`#f97316`), $\le 75\%$ (`#ef4444`) y $> 75\%$ (`#991b1b`).

---

## 5. Procedimiento Matemático Paso a Paso de las Salidas del Inspector y Resumen

A continuación se desglosa exactamente el algoritmo y las ecuaciones de `src/simulation/engine.py` y `src/gui/app.py` tomando como referencia numérica exacta el **Escenario 3 — Lluvia moderada ($I = 30\;\text{mm/h}$)** en el instante **$t = 30.0\;\text{min}$** bajo la configuración oficial por defecto (`duration_min=90.0`, `storm_duration_min=60.0`, `dt_min=1.0`, `ingress_factor=1.0`, `Q_san=0.0 m³/s`, `source_distribution="capacity"`, `split_rule="proportional"`, `V_max=4.0 m³`).

### 5.1 Cálculo en Nodos (Referencia: `NODO 20 (FUENTE)` en $t = 30.0\;\text{min}$)

El inspector muestra para `NODO 20 (FUENTE)`:
- `Tuberías entrantes : Ninguna (Fuente)`
- `Tuberías salientes : P39` ($20 \to B$, $D=8" = 0.2032\;\text{m}$, $L=222.21\;\text{m}$, $Q_{\max}=0.02965436\;\text{m}^3/\text{s}$, $V=0.91443\;\text{m/s}$, $t_{\text{trans}}=243.00\;\text{s} \approx 4.05\;\text{min}$)
- `Caudal entrada : 1.45327 m³/s`
- `Caudal salida  : 0.02965 m³/s` *(idéntico a `P39.flow_m3s`)*
- `Vol. en pozo   : 4.000 m³ (máx 4.0 m³)`
- `Rebose en vía  : 2,558.51 m³`

#### Paso 1: Caudal de Entrada ($Q_{\text{in}}$)
1. **Caudal pluvial bruto por el Método Racional (`engine.py:86`):** con $C = 0.75$, $I(30.0) = 30.0\;\text{mm/h}$ (hietograma uniforme con $30.0 \le 60.0\;\text{min}$) y $A = 388.0\;\text{ha}$:
   $$Q_{\text{racional}} = 0.00278 \cdot C \cdot I(t) \cdot A = 0.00278 \cdot 0.75 \cdot 30.0 \cdot 388.0 = 24.2694\;\text{m}^3/\text{s}$$
2. **Aporte pluvial efectivo ingresado a la red:** con el parámetro oficial por defecto `ingress_factor = 1.0` ($100\%$):
   $$Q_{\text{lluvia, ef}} = 1.0 \cdot 24.2694 = 24.2694\;\text{m}^3/\text{s}$$
3. **Ponderación hacia el Nodo 20 bajo `source_distribution = "capacity"`:** se suma la capacidad efectiva de las tuberías salientes de las 8 fuentes (`1, 6, 9, 17, 18, 19, 20, 27`):
   $$C_{\text{total, fuentes}} = \sum_{s \in S} \sum_{e \in \text{out}(s)} Q_{\max,\text{ef},e} = 0.49522283\;\text{m}^3/\text{s}$$
   Como el Nodo 20 solo tiene la salida `P39` ($C_{20} = 0.02965436\;\text{m}^3/\text{s}$):
   $$w_{20} = \frac{0.02965436}{0.49522283} = 0.0598808344\;(5.9881\%)$$
4. **Suma del caudal sanitario base ($Q_{\text{san}} = 0.0$ por defecto):**
   $$Q_{\text{in},20} = Q_{\text{lluvia, ef}} \cdot w_{20} + Q_{\text{san}} = 24.2694 \cdot 0.0598808344 + 0.0 = \mathbf{1.45327192\;\text{m}^3/\text{s}}$$
   *(En un **nodo interno / pozo de inspección**, no hay inyección pluvial directa ni $Q_{\text{san}}$; su `inflow_m3s` corresponde únicamente al caudal que llega desde sus tuberías entrantes en ese paso).*

#### Paso 2: Caudal de Salida ($Q_{\text{out}}$) y Utilización Real
En el intervalo del minuto $30$ ($[29, 30]\;\text{min}$, integrado con sub-pasos $\Delta t_{\text{sim}} = 10\;\text{s}$):
- La capacidad por minuto de `P39` es $V_{\text{cap},P39} = 0.02965436 \cdot 60 = 1.779261\;\text{m}^3/\text{min}$.
- Como el caudal entrante ($1.453272\;\text{m}^3/\text{s}$) excede con creces a $Q_{\max,P39}$, la tubería evacua exactamente su capacidad máxima:
  $$Q_{\text{out},20} = Q_{\text{cond},P39} = \mathbf{0.02965436\;\text{m}^3/\text{s}}$$
- Al considerar además los $4.000\;\text{m}^3$ almacenados en el pozo disponibles en el minuto ($4.000 / 60 = 0.066667\;\text{m}^3/\text{s}$), la demanda total sobre `P39` es $1.453272 + 0.066667 = \mathbf{1.519939\;\text{m}^3/\text{s}}$, lo que produce una utilización oficial sin recorte de:
  $$O_{P39}(30) = \frac{1.519939}{0.02965436} \times 100 = \mathbf{5,125.52\%}$$
  con $7.4136\;\text{m}^3$ en tránsito sobre `P39`.

#### Paso 3: Balance de Volumen en Pozo (`Vol. en pozo`) y Rebose en Vía (`Rebose en vía`)
Tras despachar $V_{\text{saliente}} = 1.779261\;\text{m}^3/\text{min}$, el remanente llena primero el pozo hasta $V_{\max} = 4.0\;\text{m}^3$ (saturándose en los primeros segundos de lluvia) y el resto pasa a `node_flooded_m3[20]`. Hasta $t = 30.0\;\text{min}$, el Nodo 20 ha recibido $1.45327192 \times 1800 = 2,615.8895\;\text{m}^3$, ha enviado hacia `P39` $0.02965436 \times 1800 = 53.3778\;\text{m}^3$ y retiene $4.0000\;\text{m}^3$ en el pozo:
$$V_{\text{rebose},20}(30.0) = 2,615.8895 - 53.3778 - 4.0000 = \mathbf{2,558.5116\;\text{m}^3} \xrightarrow{\text{UI}} \mathbf{2,558.51\;\text{m}^3}$$

---

### 5.2 Cálculo del Resumen del Escenario (Referencia: `Escenario 3` en $t = 30.0\;\text{min}$)

El bloque `RESUMEN DEL ESCENARIO` combina variables instantáneas/acumuladas del snapshot `snap` actual ($t = 30.0\;\text{min}$) con métricas globales de `self.result` sobre todo el horizonte $[0, 90]\;\text{min}$:

| Línea del Resumen UI | Valor exacto (Esc. 3, $t=30$) | Origen en código | Fórmula / Definición Matemática |
| :--- | :--- | :--- | :--- |
| `Escenario` | `3 — Lluvia moderada (30 mm/h)` | `result.config` | ID, nombre traducido e intensidad $I = 30\;\text{mm/h}$. |
| `Cuenca` | `C=0.75, A=388.0 ha` | `dataset.basin` | Coeficiente de escorrentía $C$ y área tributaria $A$. |
| `Ingreso / Fuent.` | `100% · Por capacidad \| Q_san=0.0000` | `result.config` | $f_{\text{ing}} = 1.0$, reparto por capacidad efectiva y $Q_{\text{san}} = 0.0\;\text{m}^3/\text{s}$/fuente. |
| `Entrada acum.` | `43,684.92 m³` | `snap.cumulative_inflow_m3` ($t=30$) | $24.2694\;\text{m}^3/\text{s} \times 1800\;\text{s} = 43,684.9200\;\text{m}^3$. |
| `Descarga PTAR 31` | `87.94 m³ (pico 0.3078 m³/s)` | `snap.cumulative_sink_discharge_m3` ($t=30$) y `result.peak_sink_discharge_m3s` (global) | Volumen acumulado evacuado en el Nodo 31 hasta $t=30$ ($87.9447\;\text{m}^3$), junto al máximo instantáneo de $\dot{V}_{\text{PTAR}}(t)$ en todo el horizonte ($0.307773\;\text{m}^3/\text{s}$). |
| `Pozos / Tránsito` | `44.79 / 704.36 m³` | `snap.total_manhole_storage_m3` / `snap.total_pipe_transit_m3` ($t=30$) | Suma del volumen retenido en los 46 pozos ($44.7855\;\text{m}^3$) vs. suma del volumen de agua que viaja dentro de las 59 tuberías esperando su llegada ($704.3642\;\text{m}^3$). |
| `Rebose superf.` | `42,847.83 m³` | `snap.total_surface_flooding_m3` ($t=30$) | Integral acumulada del exceso desbordado en todos los nodos de la red: $42,847.8256\;\text{m}^3$. |
| `Error balance` | `1.710e-09 m³` | `result.max_mass_balance_error_m3` (global) | Máximo error absoluto de conservación de masa en $[0, 90]\;\text{min}$; en $t=30$ el error instantáneo es $6.185 \times 10^{-10}\;\text{m}^3$. |
| `Críticas (>75–100%)` | `20 tuberías` | `len(result.ever_near_capacity_pipes)` | Tramos que estuvieron en $75\% < O_i(t) \le 100\%$ en al menos un paso. |
| `Sobrec. (>100%)` | `18 tuberías` | `len(result.ever_overloaded_pipes)` | Tramos que superaron $O_i(t) > 100\%$ en al menos un paso (la unión total $>75\%$ suma `21` tuberías). |

#### Verificación Exacta de Conservación de Masa Global
En cada paso, el motor audita:
$$\text{Error}(t_k) = \left|\; V_{\text{entrada}}(t_k) - \Bigl(V_{\text{PTAR}}(t_k) + V_{\text{pozos}}(t_k) + V_{\text{tránsito}}(t_k) + V_{\text{rebose}}(t_k)\Bigr) \;\right|$$
Sustituyendo los valores en $t = 30.0\;\text{min}$:
$$87.944750 + 44.785469 + 704.364210 + 42,847.825571 = 43,684.920000\;\text{m}^3$$
$$\text{Error}(30.0) = 6.185 \times 10^{-10}\;\text{m}^3 \le \text{máx}_{k \in [0,90]} = 1.710 \times 10^{-9}\;\text{m}^3$$
