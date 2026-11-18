# Simulador de Red de Alcantarillado — Ciudad Bicentenario (Cartagena)

Aplicación de escritorio en Python para la representación, simulación temporal y visualización por escala de colores del flujo en la red de alcantarillado del Macroproyecto Ciudad Bicentenario hasta el punto de descarga en la PTAR de Punta Canoa (Nodo `31`).

## Características Principales

- **Estructuras de datos implementadas desde cero** (`src/data_structures/`): `DirectedGraph`, `LinkedList` (listas de adyacencia e historial temporal), `Queue`, `PriorityQueue` (Min-Heap para eventos de tránsito y ranking), `Stack` y `HashTable`.
- **Algoritmos propios** (`src/algorithms/`): `BFS`, `DFS` iterativo con reconstrucción de caminos, ordenamiento topológico, búsqueda y trazado aguas arriba/abajo, y clasificación de criticidad según la escala de 5 colores de la guía (`0–25%`, `>25–50%`, `>50–75%`, `>75–100%`, `>100%`).
- **Carga dual validada** (`src/io/`): Lectura desde `data/DataSetBicentenario.xlsx` y desde archivos CSV normalizados en `data/csv/`.
- **Motor temporal conservativo de masa** (`src/simulation/`): Método racional ($Q = 0.00278 \cdot C \cdot I \cdot A$), velocidades de Manning, tiempos de tránsito $t_i = L_i / V_i$, distribución configurable en bifurcaciones y almacenamiento temporal en pozos ante sobrecarga.
- **Interfaz gráfica interactiva** (`src/gui/`): Lienzo con zoom/paneo y tooltips, reproductor temporal (iniciar, pausar, reanudar, paso a paso y barra de tiempo), tabla de tuberías críticas, gráficas Matplotlib y comparación entre los 5 escenarios.

## Requisitos

- Python 3.11+
- `openpyxl`, `matplotlib`, `python-docx`, `lxml`, `Pillow` (instalables con `pip install -r requirements.txt`)
- `tkinter` (incluido en Python estándar para Windows)

*(Nota: la exportación a Word `.docx` con ecuaciones OMML nativas funciona 100 % en Python puro sin requerir Pandoc instalado en el equipo de sustentación).*

## Ejecución

### Interfaz Gráfica (GUI)
```bash
python main.py
```

### Generación de Reportes y Documento Técnico (CLI)
```bash
python main.py --report-docx docs/REPORTE_ESCENARIOS.docx
python main.py --technical-docx docs/DOCUMENTO_TECNICO.docx
python main.py --report docs/REPORTE_ESCENARIOS.md
```

### Figuras Matplotlib a una columna (`3.5 × 2.8 in`)
```bash
python -m src.simulation.charts_export
```

### Pruebas Unitarias
```bash
python -m unittest discover -s tests -v
```

## Estructura del Proyecto

- `main.py`: Punto de entrada (GUI y modos CLI `--report`, `--report-docx`, `--technical-docx`).
- `requirements.txt`: Dependencias portables para ejecución en otro equipo.
- `data/`: Dataset oficial `DataSetBicentenario.xlsx` y su versión en `csv/`.
- `src/data_structures/`: Estructuras de datos obligatorias propias.
- `src/algorithms/`: BFS, DFS, consultas y análisis de criticidad.
- `src/io/`: Cargadores y validadores Excel/CSV.
- `src/simulation/`: Motor de simulación, comparación, figuras `3.5 × 2.8 in` y exportador Word `.docx` (OMML `8.5 pt`) sin Pandoc.
- `src/gui/`: Interfaz gráfica adaptable Tkinter + Matplotlib con sistema visual **Atlas Urbano de Infraestructura** (Obsidiana `#131820`, Papel técnico `#F7F8FA` y Cobalto `#0369A1`).
- `docs/`: Documento técnico en Word (`DOCUMENTO_TECNICO.docx`), Markdown y reportes de escenarios.
- `tests/`: Suite de pruebas unitarias.
