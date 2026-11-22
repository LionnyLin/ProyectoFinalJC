# Simulador de Red de Alcantarillado — Ciudad Bicentenario (Cartagena)

Aplicación de escritorio en Python para modelar, simular en el tiempo y visualizar el comportamiento hidráulico de la red de alcantarillado del **Macroproyecto Ciudad Bicentenario** (**46 nodos**, **59 tuberías**, **19 163.57 m** totales) desde sus **8 alcantarillas fuente** (`1, 6, 9, 17, 18, 19, 20, 27`) hasta la descarga final en la **PTAR Punta Canoa (Nodo `31`)**.

![Vista general del simulador](docs/screenshots/00_vista_general.png)

Todo el núcleo algorítmico (grafo dirigido, listas doblemente enlazadas, cola, pila, tabla hash y cola de prioridad Min-Heap) está implementado **desde cero** en Python puro, cumpliendo íntegramente los requisitos funcionales **RF01–RF12** y el **Nivel Avanzado (5.0)** de la guía del proyecto.

## Requisitos e Instalación

- **Python:** `>= 3.11`
- **Dependencias directas (`requirements.txt`):** **5** paquetes externos:
  - `openpyxl>=3.1.2` — lectura del dataset oficial en Excel (`.xlsx`)
  - `matplotlib>=3.8.0` — hidrogramas, perfil longitudinal, comparación y figuras del documento técnico
  - `python-docx>=1.1.0` — exportación de reportes y documento técnico en Word (`.docx`)
  - `lxml>=5.0.0` — ecuaciones OMML nativas dentro del `.docx`
  - `Pillow>=10.0.0` — iconos de la interfaz (supermuestreo) y tarjetas de las capturas
- **Tkinter:** incluido por defecto en Python para Windows y macOS; en Linux (Debian/Ubuntu) instalar con `sudo apt install python3-tk`.
- La exportación a Word con ecuaciones OMML funciona en Python puro, **sin Pandoc**.

### Windows (instalación y ejecución automatizada)

```bat
setup.bat          :: Crea .venv, instala requirements.txt y verifica dependencias
setup.bat --run    :: Prepara el ambiente e inicia la interfaz gráfica
setup.bat --test   :: Prepara el ambiente y ejecuta la suite de pruebas
```

Una vez preparado el entorno virtual, también puedes iniciar directamente con `.venv\Scripts\python.exe main.py`.

### Linux / macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Uso

### 1. Interfaz Gráfica (GUI)

```bash
python main.py                   # Carga data/DataSetBicentenario.xlsx por defecto
python main.py --data data/csv   # Carga equivalente desde la carpeta CSV normalizada
```

### 2. Reportes y Documento Técnico por CLI (sin abrir ventana)

Ejecuta la comparativa completa de los 5 escenarios bajo parámetros equivalentes y exporta el reporte Markdown (con su archivo hermano `*_tuberias.csv`), el reporte Word a dos columnas con ecuaciones OMML y/o el Documento Técnico completo con Anexos A–D:

```bash
python main.py --report docs/REPORTE_ESCENARIOS.md --report-docx docs/REPORTE_ESCENARIOS.docx
python main.py --technical-docx docs/DOCUMENTO_TECNICO.docx
```

### 3. Figuras y Capturas de Documentación

```bash
python -m src.simulation.charts_export        # fig1–fig3 a una columna (3.5 × 2.8 in) en docs/figuras/
python scripts/capture_doc_screenshots.py     # 24 capturas en docs/screenshots/ (Windows: PrintWindow; Linux/X11: ImageMagick)
```

El script de capturas abre la aplicación real, reproduce cada escenario de la documentación y compone además tres tarjetas de terminal con la ejecución real de la exportación CSV, el CLI y la suite de pruebas. Debe ejecutarse **antes** de `--technical-docx` para que el documento incruste las capturas.

### 4. Pruebas Automatizadas (127 pruebas en 11 archivos)

```bash
python -m pytest -q
# o con unittest:
python -m unittest discover -s tests -v
```

Las pruebas de GUI abren ventanas Tk reales; en un entorno sin pantalla se omiten automáticamente.

## Interfaz y Atajos

- **Topbar:** toggles `Controles` / `Análisis`, menú `Archivo y Modelo` (cargar Excel/CSV, exportar CSV, supuestos), exportación `MD/CSV` y `Word`, y botón `Recorrido guiado`.
- **Panel izquierdo** con pestañas `Simulación` (escenario, 5 parámetros, presets, bifurcación y reparto) y `Recorridos` (búsqueda, BFS/DFS/aguas arriba/abajo y bitácora con la cola/pila en vivo).
- **Centro:** cabecera con 4 tarjetas KPI que cambian con el modo de mapa, selector `Instantáneo O(t)` / `Pico Máximo` / `Minutos en Sobrecarga`, lienzo del grafo y reproductor (`Inicio`, `-1`, `Reproducir`, `+1`, velocidades `0.5x`–`10x`, slider e indicador de balance de masa).
- **Panel derecho:** pestañas `Inspector`, `Tuberías Críticas`, `Evolución` (hidrograma y perfil longitudinal) y `Comparación`.
- **Atajos:** `Espacio` reproducir/pausar · `←`/`→` paso atrás/adelante · `Inicio` volver a `t = 0` · `Ctrl+F` buscar · `Esc` limpiar (se ignoran mientras se escribe en un campo).
- **Layout responsivo:** tres niveles (`compact` < 940 px, `medium` < 1220 px y `wide`); en modo compacto los paneles lateral izquierdo y derecho son excluyentes, los textos se acortan y la barra de atajos se oculta bajo 980 px.

## Arquitectura Modular del Repositorio

El código ejecutable suma **9 777 líneas** (`main.py` + `src/`), **2 767 líneas** de pruebas (`tests/`) y **465 líneas** del script de capturas, para **13 009 líneas** Python (conteo `wc -l`):

```text
ProyectoFinalJC/
├── main.py                      # (78 L)    Entrada GUI y CLI (--data, --report, --report-docx, --technical-docx)
├── setup.bat                    # Script de preparación, ejecución y pruebas en Windows
├── requirements.txt             # 5 dependencias: openpyxl, matplotlib, python-docx, lxml, Pillow
├── DOCUMENTACION.md             # Referencia técnica y guía de estudio para sustentación
├── GuiaDocente.md               # Guía para el docente
├── assets/fonts/                # Tipografía local Inter (Regular, Medium, SemiBold, Bold)
├── data/
│   ├── DataSetBicentenario.xlsx # Dataset oficial de la red, cuenca y 5 escenarios
│   └── csv/                     # Espejo CSV normalizado (pipes, sources, sinks, basin, coords)
├── docs/                        # DOCUMENTO_TECNICO (.md/.docx), REPORTE_ESCENARIOS (.md/.docx/.csv),
│   ├── figuras/                 #   figuras fig1–fig3 a una columna
│   └── screenshots/             #   24 capturas de la aplicación y de la terminal
├── scripts/
│   └── capture_doc_screenshots.py  # (465 L) Generador reproducible de las 24 capturas
├── src/                         # (9 699 L) Código fuente modular (sin contar main.py)
│   ├── data_structures/         # (576 L)   LinkedList, Queue, Stack, HashTable, PriorityQueue, DirectedGraph
│   ├── io/                      # (336 L)   data_loader.py (carga/validación Excel y CSV + exportación CSV)
│   ├── algorithms/              # (931 L)   traversals.py (BFS/DFS/Kahn + fotogramas), queries.py, analysis.py
│   ├── simulation/              # (2 095 L) models, engine, comparison, reporter (MD/CSV), docx_exporter,
│   │                            #           omml_equations, charts_export
│   └── gui/                     # (5 760 L) Interfaz Tkinter + Matplotlib en paneles independientes:
│       ├── app.py               # (1 253 L) Orquestador y dueño único del estado UI
│       ├── network_canvas.py    # (1 255 L) Lienzo en 2 fases, modos de mapa, pulsos, intervenciones, cámara
│       ├── charts_panel.py      # (1 033 L) Hidrograma, perfil longitudinal y gráficas de comparación
│       ├── inspector_panel.py   # (640 L)   Inspector (intervenciones, composición por fuente) y tuberías críticas
│       ├── controls_panel.py    # (540 L)   Escenarios, parámetros, presets, BFS/DFS y bitácora Queue/Stack
│       ├── guided_tour.py       # (318 L)   Recorrido guiado de 4 hallazgos por escenario
│       ├── comparison_panel.py  # (235 L)   Tabla de 8 columnas y recálculo bajo demanda
│       ├── theme.py             # (225 L)   Paleta cartográfica, fuentes, DPI y breakpoints
│       ├── icons.py             # (147 L)   Iconos Pillow con supermuestreo
│       └── widgets.py           # (109 L)   Menubutton de selección y diámetros comerciales
└── tests/                       # (2 767 L) 127 pruebas en 11 archivos (estructuras, cargador, algoritmos,
                                 #           motor, DOCX, lienzo y GUI)
```

## Características Principales (RF01–RF12 + Nivel Avanzado 5.0)

- **Estructuras de datos desde cero (RF01–RF02):** `DirectedGraph` con listas de adyacencia (`LinkedList`) e indexación `O(1)` (`HashTable` potencia de 2 con método `add()`), `Queue` FIFO, `Stack` LIFO y `PriorityQueue` Min-Heap binario determinista. Una prueba AST garantiza que `src/data_structures` no importa `collections` ni `heapq`.
- **Carga dual validada (RF01):** lectura desde `DataSetBicentenario.xlsx` o carpeta `data/csv/`, validación topológica de grafo acíclico dirigido (DAG) mediante Kahn y exportación a CSV normalizado.
- **Recorridos BFS y DFS con bitácora en vivo (RF03–RF04):** búsqueda en anchura (`Queue`) y profundidad iterativa (`Stack`) con reconstrucción de ruta, animación paso a paso (`560 ms` BFS / `340 ms` DFS), frente activo y backtracking del DFS, y tira de la estructura activa (`Cola (Queue) · FRENTE → FINAL` / `Pila (Stack) · TOPE ↑`).
- **Búsqueda y trazado (RF05):** búsqueda exacta `O(1)` por ID con respaldo por subcadena (`search_entities`), ficha técnica, trazado aguas abajo (hacia PTAR `31`) o aguas arriba (subcuenca aportante), `Aislar cuenca` y detección de nodos incomunicados de la PTAR.
- **Simulación física conservativa con retardo de tránsito (RF06–RF08):**
  - Escorrentía por Método Racional ($Q = 0.00278 \cdot C \cdot I \cdot A$, con $C = 0.75$ y $A = 388\text{ ha}$) multiplicada por un **factor de ingreso pluvial** (`100 %` oficial; preset `Calibrado` `2.5 %`) más un **caudal sanitario** $Q_{\text{san}}$ por fuente.
  - Capacidad $Q_{\max}$ tomada del dataset, velocidad $V_i = Q_{\max}/(\pi D^2/4)$ y tiempo de viaje $t_i = L_i/V_i$ programado con `PriorityQueue` (sin teletransporte; llegada mínima a PTAR `31` en 8.75 min, primer caudal visible en `t = 10 min`).
  - Conducción limitada a $\min(Q_{\text{demanda}}, Q_{\max})$, almacenamiento temporal en pozos (`4.0 m³` por defecto) y rebose superficial con balance de masa exacto (error $< 10^{-8}\text{ m}^3$) e invarianza ante $\Delta t$.
  - **Intervenciones en vivo:** obstrucción `0–100 %` y cambio de diámetro comercial por tubería sin mutar el grafo base, con comparación `Antes / Después` y `Restaurar tramo / Restaurar red`.
- **Escala oficial de 5 colores y ranking crítico (RF09–RF10):** clasificación visual y ordenamiento descendente con `PriorityQueue` según la Sección 7 del PDF (desempate por razón de demanda $\times Q_{\max}$):

| Rango de Utilización $O_i(t)$ | Color Oficial | Estado Hidráulico |
|:---:|:---:|:---|
| `0–25 %` | `#22c55e` (Verde) | Baja utilización |
| `>25–50 %` | `#eab308` (Amarillo) | Utilización moderada |
| `>50–75 %` | `#f97316` (Naranja) | Utilización alta |
| `>75–100 %` | `#ef4444` (Rojo) | Cercana a capacidad máxima |
| `>100 %` | `#991b1b` (Rojo oscuro) | Capacidad excedida (sobrecarga) |

- **Modos de lectura del mapa:** `Instantáneo O(t)`, `Pico Máximo` y `Minutos en Sobrecarga` (vistas globales congeladas que pausan la reproducción y restauran el paso al volver), con leyenda y tarjetas KPI que se adaptan al modo.
- **Inspector y análisis:** barra de acciones (`Centrar`, `Aislar cuenca`, `Aguas arriba/abajo`), tarjeta `Intervención en vivo`, **composición por fuente aportante** (barra apilada + porcentajes) y bloque `RESUMEN DEL ESCENARIO`; tuberías críticas con filtros `Todas` / `Resto (≤75%)` / `Críticas (>75–100%)` / `Sobrec. (>100%)`.
- **Gráficas de evolución:** hidrograma con doble eje (entrada, PTAR `31`, curva `Antes`, cursor de tiempo y utilización de la tubería seleccionada o top 3) y **perfil longitudinal** de la ruta hacia la PTAR (`% uso vs. Cap.` o `Q (m³/s)`) con nota de cuello de botella.
- **Lienzo animado:** pulsos de flujo durante la reproducción, anillos de rebose, doble línea al ampliar diámetro, barras de obstrucción, tramos aislados punteados, halo de sobrecarga, tooltips con demanda $\times Q_{\max}$, zoom animado y foco de cuenca/recorrido.
- **Recorrido guiado:** 4 hallazgos por escenario con ficha flotante, atenuación del resto del grafo y cámara animada.
- **Comparación de 5 escenarios y reportes (RF11–RF12):** evaluación de los 5 escenarios de lluvia (`0, 10, 30, 60, 100 mm/h`) con tabla de 9 columnas, recálculo bajo demanda, gráficas con selector de métrica, y exportación a **Markdown, CSV, Word (`.docx`) a dos columnas con ecuaciones OMML** y **Documento Técnico** (Anexos A–D con figuras y capturas) desde GUI o CLI.

## Rendimiento Verificado

- Motor: ≈ 36 ms por escenario de 90 min (91 instantáneas; ≈ 8 ms el tiempo seco) y ≈ 156 ms los 5 escenarios.
- Lienzo en dos fases (`rebuild_geometry` solo al cargar/zoom/paneo/redimensionar; `update_visuals` con `itemconfigure` sin borrar ítems), pestañas ocultas sin redibujar y cursor temporal rápido en las gráficas.

Para consultar complejidades Big-O, ecuaciones del modelo, desglose de módulos, matriz de cumplimiento del PDF y preguntas frecuentes de sustentación, consulta [DOCUMENTACION.md](DOCUMENTACION.md); el entregable a dos columnas está en [docs/DOCUMENTO_TECNICO.docx](docs/DOCUMENTO_TECNICO.docx).
