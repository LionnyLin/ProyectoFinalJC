# Plan Detallado: Documento Técnico Definitivo Único en Word (`.docx`) a Dos Columnas con Capturas Viñeta por Viñeta

## 1. Objetivo

Consolidar **toda la documentación técnica del proyecto** —tanto los requisitos base de `GuiaDocente.md` como todas las **funcionalidades extras (Nivel Avanzado 5.0)**— en un **único documento técnico definitivo en Word (`docs/DOCUMENTO_TECNICO.docx`)**, generado 100 % en Python puro mediante `src/simulation/docx_exporter.py` (sin Pandoc), manteniendo estrictamente la **maquetación continua a dos columnas** y adjuntando **screenshots reales y legibles viñeta por viñeta**.

---

## 2. Diagnóstico de Brechas Actuales en el Repositorio

Al auditar el estado actual en `main` (`1f79997`), se identificaron las siguientes inconsistencias que este plan resuelve:

1. **Desfase entre código y documentación existente:**
   - `src/simulation/docx_exporter.py` (líneas 582–588) no documenta de forma explícita las funcionalidades extras ni incluye capturas de la GUI; además `docs/DOCUMENTO_TECNICO.md` aún menciona *"35 pruebas unitarias"* (actualmente son **41**), *"factor de ingreso calibrado por defecto 2.5%"* (hoy el predeterminado es **100 % Oficial Guía** con `Q_san = 0.0 m³/s`) y *"utilización acotada ∈ [0, 115 %]"* (hoy se reporta **sin techo artificial**).
   - `DOCUMENTACION.md` cita líneas antiguas de `src/gui/app.py` (`4,964 líneas`) previas a la modularización de `src/gui/` (`controls_panel.py`, `inspector_panel.py`, `comparison_panel.py`, `guided_tour.py`, `widgets.py`; hoy `app.py` tiene `2,069` líneas).
   - `docs/Funcionalidades_Extras_Proyecto.docx` existe como archivo aislado de 1 columna en lugar de estar integrado en el entregable único `docs/DOCUMENTO_TECNICO.docx`.
2. **Problemas de legibilidad y estado temporal detectados en capturas previas:**
   - Capturar únicamente la ventana completa (`1440×860`) y reducirla a `3.45 in` (ancho de una columna en Word) vuelve muy pequeño el texto de paneles internos.
   - Al aplicar intervenciones (`_action_apply_intervention`) o cambiar parámetros en la GUI, la simulación reinicia la reproducción en `t = 0.0 min`; algunas capturas previas quedaron en `t = 0.0 min` en lugar de pausarse en minutos con tormenta activa (`t = 35–45 min`).

---

## 3. Reglas de Maquetación a Dos Columnas (Restricciones Duras)

El documento único debe cumplir todas las validaciones de `_validate_docx_compliance()` en `src/simulation/docx_exporter.py` y `tests/test_docx_exporter.py`:

- **Geometría de página:** Carta (`8.5 × 11.0 in`), márgenes `0.60 in` (sup/inf) y `0.55 in` (izq/der), `w:cols w:num="2"` continuo en todas las secciones, espaciado entre columnas `w:space="432"` (`0.30 in`) $\implies$ **ancho útil por columna = `3.55 in`**.
- **Figuras y screenshots:** ancho fijo **`3.45 in`** (`_add_single_column_figure`) para que ningún screenshot invada el margen central ni rompa la columna.
- **Ecuaciones:** exclusivamente **OMML nativo centrado a `8.5 pt`** (`w:sz = 17` vía `src/simulation/omml_equations.py`), nunca dentro de tablas.
- **Tablas:** texto plano puro (sin `$` ni OMML), ancho total de columnas $\le 3.45\;\text{in}$, encabezado repetible (`w:tblHeader`) y cebra `#F6EEF6` / `#3B153A`.
- **Figuras Matplotlib exportadas:** `3.5 × 2.8 in` @ `300 DPI` (`1050 × 840 px`) generadas por `src/simulation/charts_export.py`.

### Estrategia de Captura para Máxima Legibilidad en `3.45 in`

Para que cada screenshot se lea nítidamente dentro de una columna de `3.45 in` (~`8.76 cm`):
1. **Capturas de Ventana Completa (`1280×740`):** usadas solo cuando importa la vista panorámica del sistema completo (modos cartográficos globales, aislamiento de cuenca, recorrido guiado, UI responsiva).
2. **Recortes Enfocados de Widget/Panel (`520–860 px` de ancho):** usadas para detalles densos (panel izquierdo de controles, visor `Queue`/`Stack` en `Recorridos`, barra apilada `Composición por Fuente Aportante` + ficha del `Inspector`, zoom de `NetworkCanvas` sobre pozos con `_draw_flood_rings` y marcas de intervención, sub-pestañas de `TemporalChartsPanel` y tabla `Tuberías Críticas`).
3. **Tarjetas Terminales Compactas (`860 px` de ancho, fuente `16 pt`):** usadas para evidencias CLI (`--report`, `--report-docx`, `--technical-docx`), `export_to_csv_dir` y salida de las `41` pruebas unitarias.
4. **Control estricto del reloj de reproducción:** después de cada cambio de escenario o intervención, cancelar cualquier `after()` de autoplay (`is_playing = False`) y fijar el instante objetivo (`t = 35–45 min`) antes de capturar.

---

## 4. Estructura Propuesta del Documento Único (`docs/DOCUMENTO_TECNICO.docx`)

El documento se reorganiza en un **único entregable maestro** a dos columnas con numeración continua de secciones, ecuaciones y figuras:

1. **Encabezado y Resumen Ejecutivo**
   - Alcance académico (`GuiaDocente.md`), resumen de la red (`46` vértices, `59` tuberías, `19,163.57 m`, PTAR `31`) y síntesis de las mejoras de Nivel Avanzado 5.0.
2. **1. Introducción, Caso de Estudio y Matriz de Requisitos (`RF01–RF12`)**
   - Tabla compacta de cobertura de requisitos base + capacidades extras.
   - **Screenshot:** vista general de la aplicación en operación activa (`Esc. 3`, `t = 35 min`).
3. **2. Arquitectura Modular y Estructuras de Datos Propias (`src/data_structures/`)**
   - Tabla de módulos reales del repositorio (`data_structures`, `io`, `algorithms`, `simulation`, `gui`, `tests`).
   - Explicación técnica de `HashTable`, `LinkedList` doble, `Queue`, `Stack`, `PriorityQueue` (Min-Heap con desempate FIFO) y `DirectedGraph`.
4. **3. Algoritmos, Recorridos y Análisis de Red (`src/algorithms/`) — *con screenshots viñeta por viñeta***
   - **3.1 Animación paso a paso BFS y DFS con visor en vivo de `Queue` / `Stack`:** explicación + *Screenshots (recorte panel `Recorridos` + mapa)* mostrando BFS (Cola) y DFS (Pila + *backtracking*).
   - **3.2 Ordenamiento topológico (Kahn) y verificación DAG:** `46/46` nodos sin ciclos.
   - **3.3 Trazado `Aguas arriba` / `Aguas abajo` + `Aislar cuenca`:** explicación de `trace_upstream` / `trace_downstream` + *Screenshot* aislando subcuenca tributaria.
   - **3.4 Detección de nodos desconectados (`find_isolated_from_sinks`):** explicación de BFS inverso + *Screenshot* cerrando `P29` al `100 %` en `t = 40 min` con nodos/tramos `[AISLADO DE 31]`.
   - **3.5 Composición por fuente aportante (`compute_source_attribution`):** formulación de trazabilidad desde `F1..F27` + *Screenshot (recorte Inspector)* con barra apilada en nodo confluente `30`.
   - **3.6 Persistencia de sobrecarga y ranking (`classify_overload_persistence`, `rank_critical_pipes`):** explicación + *Screenshot* de la pestaña `Tuberías Críticas`.
5. **4. Modelo Matemático y Motor Hidráulico Avanzado (`src/simulation/`) — *con screenshots viñeta por viñeta***
   - Ecuaciones OMML `8.5 pt` (`1` a `7`: Racional, Entrada efectiva, Manning, Velocidad, Tránsito, Utilización oficial sin techo, Balance de masa).
   - **4.1 Sub-pasos continuos con `PriorityQueue` (`_TransitEvent`):** invariancia `0.0000 %` frente a $\Delta t$ + *Screenshot* de simulación activa en `t = 35 min` con error de balance `~10⁻⁹ m³` + tabla de verificación $\Delta t \in \{0.5, 1.0, 2.0, 5.0\}\;\text{min}$.
   - **4.2 Almacenamiento finito en pozos (`4.0 m³`) + rebose superficial (`surface_flooding_m3`):** conservación exacta de masa + *Screenshot* en `Esc. 5` (`t = 45 min`) mostrando pozo saturado en el Inspector y anillos concéntricos de rebose.
   - **4.3 Intervenciones en vivo (`PipeIntervention`):** leyes de escala Manning ($Q \propto D^{8/3}$, $V \propto D^{2/3}$) + *2 Screenshots*: (a) tubería `P29` obstruida `80 %` en `t = 40 min` con marcador `[OBST 80%]`, (b) hidrograma comparativo *Antes vs. Después*.
   - **4.4 Reglas configurables desde la GUI:** bifurcación (`Proporcional` / `Equitativa`), reparto entre fuentes (`Por capacidad` / `Uniforme 1/8`), presets (`Oficial Guía 100%` vs `Calibrado 2.5% + Q_san`) + *Screenshot (recorte panel Controles)*.
6. **5. Interfaz Gráfica y Visualización Cartográfica (`src/gui/`) — *con screenshots viñeta por viñeta***
   - Paleta **Lámina Cartográfica** (`#4A4A4A`, `#CBCBCB`, `#FFFFE3`, `#6D8196`), manejo HiDPI e iconos rasterizados.
   - **5.1 Tres Modos Cartográficos (`Instantáneo O(t)`, `Pico Máximo`, `Minutos en Sobrecarga`):** *3 Screenshots* comparativos en `Esc. 5` (`t = 45 min` vs envolvente global `0–90 min`).
   - **5.2 Lienzo `NetworkCanvas` avanzado:** pulsos de Manning, `_draw_flood_rings`, marcas de obstrucción/ampliación, zoom en cursor, paneo, tooltips, placas sin colisión y layout topológico automático + *Screenshot con zoom* sobre zona de confluencia `30–D–G–31` en `t = 45 min`.
   - **5.3 Gráficas Avanzadas (`charts_panel.py`):** hidrograma con doble eje Y (`twinx()`), escala `symlog`, blitting en cursores y perfil longitudinal `Q vs Qmax` hasta PTAR `31` + *2 Screenshots (recortes subtab `hydro` y subtab `profile`)*.
   - **5.4 Recorrido Guiado (`Guía Esc. N · 4 Hallazgos`, `guided_tour.py`):** 4 paradas por escenario con cámara automática y datos de snapshots + *Screenshot* de tarjeta flotante activa.
   - **5.5 UI Responsiva, Comparación Multiescenario, Atajos y Diálogo de Supuestos:** 3 breakpoints (`wide`/`medium`/`compact`), atajos (`Espacio`, `←/→`, `Home`, `Ctrl+F`, `Esc`) + *2 Screenshots* (pestaña `Comparación` y ventana en modo `compact`).
7. **6. Resultados Globales, Comparación de Escenarios y Figuras Matplotlib (`3.5 × 2.8 in`)**
   - Tabla comparativa de los 5 escenarios (`Dry weather` a `Extreme rain`) y las 3 figuras de `charts_export.py`.
8. **7. Datos, Reportes Automáticos por CLI y Validación (`src/io/`, `main.py`, `tests/`) — *con screenshots viñeta por viñeta***
   - **7.1 Carga dual `.xlsx` + `.csv` y exportación (`export_to_csv_dir`):** validación topológica DAG y layout automático sin coordenadas + *Screenshot tarjeta terminal* de exportación CSV.
   - **7.2 Generación automática por CLI (`main.py`):** `--report`, `--report-docx` y `--technical-docx` sin Pandoc + *Screenshot tarjeta terminal*.
   - **7.3 Suite de 41 pruebas unitarias automatizadas (`tests/`):** cobertura de los 6 archivos de prueba + *Screenshot tarjeta terminal* de `python -m unittest discover -s tests -v`.
9. **8. Conclusiones, Limitaciones y Bibliografía**
10. **Anexos A–D**
    - **Anexo A:** Complejidad asintótica de estructuras propias.
    - **Anexo B:** Inventario completo de tuberías (`P1`–`P59`).
    - **Anexo C:** Resultados detallados por escenario (masa inyectada, PTAR, rebose, error).
    - **Anexo D:** Comandos reproducibles de ejecución, generación documental y pruebas.

---

## 5. Matriz Completa de Screenshots (Viñeta por Viñeta)

Todos los archivos se guardarán en `docs/screenshots/` con nombres estables y reproducibles:

| ID | Viñeta / Funcionalidad | Archivo en `docs/screenshots/` | Tipo de Captura | Estado Exacto de Simulación |
| :--- | :--- | :--- | :--- | :--- |
| S00 | Vista general sistema | `00_vista_general.png` | Ventana `1280×740` | Esc. 3, `t = 35 min`, modo `Instantáneo` |
| S01 | Sub-pasos `PriorityQueue` | `01_1_subpasos_transit.png` | Ventana + zoom reloj/balance | Esc. 3, `t = 35 min`, balance `~10⁻⁹ m³` |
| S02 | Almacenamiento `4.0 m³` + rebose | `01_2_almacenamiento_rebose.png` | Recorte Inspector + Canvas Esc. 5 | Esc. 5, `t = 45 min`, nodo con rebose seleccionado |
| S03a | Intervención `PipeIntervention` (mapa) | `01_3a_intervencion_mapa.png` | Recorte Canvas + Inspector | Esc. 3, **`t = 40 min`**, `P29` obst. `80 %` |
| S03b | Comparativa *Antes vs. Después* | `01_3b_antes_despues.png` | Recorte `TemporalChartsPanel` | Esc. 3, `t = 40 min`, curva punteada `Antes` |
| S04 | Reglas configurables GUI | `01_4_reglas_gui.png` | Recorte panel `Controles` | `Equitativa`, `Uniforme`, `Calibrado 2.5% + Q_san` |
| S05a | Animación BFS + visor `Queue` | `02_1a_bfs_queue.png` | Ventana `1280×740` (`trav`) | BFS desde `9` a `31`, paso 8, `Cola` visible |
| S05b | Animación DFS + visor `Stack` | `02_1b_dfs_stack.png` | Ventana `1280×740` (`trav`) | DFS desde `9` a `31`, paso 10, `Pila` visible |
| S06 | `Aguas arriba` + `Aislar cuenca` | `02_2_aguas_arriba_aislar.png` | Ventana `1280×740` | Nodo `K` con traza aguas arriba y cuenca aislada |
| S07 | Nodos desconectados (`find_isolated_from_sinks`) | `02_3_nodos_desconectados.png` | Ventana `1280×740` | Esc. 3, **`t = 40 min`**, `P29` al `100 %` |
| S08 | Composición por fuente (`F1..F27`) | `02_4_composicion_fuentes.png` | Recorte `Inspector` | Esc. 3, `t = 40 min`, nodo `30` (barra apilada) |
| S09 | Persistencia sobrecarga (`>100 %`) | `02_5_persistencia_sobrecarga.png` | Recorte `Tuberías Críticas` | Esc. 5, tabla ordenada + modo `Sobrecarga` |
| S10a | Modo `Instantáneo O(t)` | `03_1a_modo_instantaneo.png` | Ventana `1280×740` | Esc. 5, `t = 45 min` |
| S10b | Modo `Pico Máximo` | `03_1b_modo_pico.png` | Ventana `1280×740` | Esc. 5, vista global `0–90 min` |
| S10c | Modo `Minutos en Sobrecarga` | `03_1c_modo_sobrecarga.png` | Ventana `1280×740` | Esc. 5, vista global `0–90 min` |
| S11 | `NetworkCanvas` zoom + `_draw_flood_rings` | `03_2_canvas_zoom_rebose.png` | Recorte `NetworkCanvas` | Esc. 5, **`t = 45 min`**, zoom `1.85×` en `30-D-G-31` |
| S12a | Hidrograma `twinx()` + `symlog` | `03_3a_hidrograma_twinx.png` | Recorte `TemporalChartsPanel` | Esc. 3, `t = 40 min`, subtab `hydro` |
| S12b | Perfil longitudinal `Q vs Qmax` | `03_3b_perfil_longitudinal.png` | Recorte `TemporalChartsPanel` | Esc. 3, `t = 40 min`, subtab `profile` |
| S13 | Recorrido Guiado (`4 Hallazgos`) | `03_4_recorrido_guiado.png` | Ventana `1280×740` | Esc. 5, parada 2 con cámara enfocada |
| S14a | Pestaña `Comparación` 5 escenarios | `03_5a_comparacion_escenarios.png` | Ventana `1280×740` | 5 escenarios calculados + tabla/gráficas |
| S14b | UI responsiva modo `compact` | `03_5b_ui_compacta.png` | Ventana `900×700` | Breakpoint `< 920 px` + exclusividad paneles |
| S15 | Carga dual + `export_to_csv_dir` | `04_1_carga_export_csv.png` | Tarjeta terminal (`860 px`) | Ejecución real exportando a CSV |
| S16 | Generación CLI (`main.py`) | `04_2_cli_reportes.png` | Tarjeta terminal (`860 px`) | Salida real de `--report`, `--report-docx`, `--technical-docx` |
| S17 | Suite de 41 pruebas (`unittest`) | `04_3_tests_41.png` | Tarjeta terminal (`860 px`) | Salida real `Ran 41 tests ... OK` |

---

## 6. Archivos a Crear o Modificar

1. **Crear `scripts/capture_doc_screenshots.py`:**
   - Script limpio, determinista y reutilizable para generar todas las imágenes en `docs/screenshots/` mediante `PrintWindow` (sin depender de que el escritorio esté desbloqueado) + recortes exactos de widgets por coordenadas cliente.
   - Asegura `is_playing = False` y cancelación de `_play_after_id` tras cada simulación/intervención para congelar exactamente el minuto `t = 35–45 min`.
2. **Actualizar `src/simulation/docx_exporter.py`:**
   - En `generate_technical_document_docx()`:
     - Incorporar las secciones completas de arquitectura modular, algoritmos avanzados, motor hidráulico, GUI, CLI y pruebas (`41` pruebas unitarias).
     - Resolver la ruta de `docs/screenshots/` relativa al proyecto e incrustar cada captura con `_add_single_column_figure(doc, path, caption)` (`3.45 in`) dentro del flujo a **2 columnas** en su viñeta correspondiente.
     - Si alguna captura no existiera en un entorno temporal aislado, omitirla o generar un fallback limpio sin romper `test_docx_exporter.py`.
3. **Actualizar `docs/DOCUMENTO_TECNICO.md`, `DOCUMENTACION.md` y `README.md`:**
   - Alinear cifras (`41` pruebas, `100%` Oficial Guía por defecto, `Q_san = 0.0`, utilización sin techo, arquitectura real de `src/gui/`).
   - Enlazar las capturas de `docs/screenshots/` en la documentación Markdown y dejar `docs/DOCUMENTO_TECNICO.docx` como documento Word maestro único (eliminando o archivando `docs/Funcionalidades_Extras_Proyecto.docx` para evitar duplicidad).
4. **Actualizar/Verificar `tests/test_docx_exporter.py`:**
   - Confirmar que `generate_technical_document_docx()` pasa `_assert_docx_rules(out2, expected_min_omml=7)` (2 columnas continuas en todas las secciones, OMML `8.5 pt` centrado, tablas en texto plano sin `$`, y todas las figuras/capturas embebidas en `word/media/`).

---

## 7. Secuencia de Ejecución y Verificación

1. **Paso 1:** Crear `scripts/capture_doc_screenshots.py` y ejecutarlo para poblar `docs/screenshots/` (24 imágenes).
2. **Paso 2:** Inspeccionar visualmente una muestra representativa de las capturas nuevas (verificando que `t = 35–45 min` esté activo y que los recortes de panel sean nítidos).
3. **Paso 3:** Actualizar `src/simulation/docx_exporter.py` para construir el `docs/DOCUMENTO_TECNICO.docx` definitivo a 2 columnas con toda la documentación + todas las capturas viñeta por viñeta.
4. **Paso 4:** Sincronizar `docs/DOCUMENTO_TECNICO.md`, `DOCUMENTACION.md` y `README.md`, y retirar `docs/Funcionalidades_Extras_Proyecto.docx` si ya queda unificado.
5. **Paso 5:** Regenerar los entregables oficiales (`python main.py --technical-docx docs/DOCUMENTO_TECNICO.docx` y `--report-docx docs/REPORTE_ESCENARIOS.docx`).
6. **Paso 6:** Ejecutar `python -m unittest discover -s tests -v` y validar que las `41` pruebas pasan sin errores, además de inspeccionar la estructura XML y páginas del `.docx` final.
