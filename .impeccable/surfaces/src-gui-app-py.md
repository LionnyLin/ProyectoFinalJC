---
version: 1
slug: "src-gui-app-py"
primary_target: "src/gui/app.py"
related_targets: ["src/gui/network_canvas.py","src/gui/charts_panel.py","src/gui/theme.py"]
---

# Surface Brief — Simulador Hidráulico Ciudad Bicentenario

## Scope and Visitor Mode

- **Surface:** Aplicación de escritorio Python/Tkinter (`src/gui/app.py`, `network_canvas.py`, `charts_panel.py`, `theme.py`)
- **Mode:** `operate`

## Audience, Job, Action & Constraints

- **Audiencia:** Estudiantes/evaluadores de Estructuras de Datos y analistas hidráulicos en portátiles, proyectores o monitores amplios.
- **Tarea:** Cargar la red, ajustar escenario/parámetros hidráulicos, simular y reproducir el tránsito temporal hacia la PTAR (`31`), consultar recorridos (`BFS`, `DFS`, aguas arriba/abajo), inspeccionar tuberías críticas, graficar evolución/comparación de 5 escenarios y exportar CSV/DOCX/MD.
- **Restricciones:** Preservar 100% de requisitos funcionales, escala de 5 colores de la Sección 7 (`#22c55e`, `#eab308`, `#f97316`, `#ef4444`, `#991b1b`), Python 3.11 + Tkinter + Matplotlib, y adaptabilidad total a distintos tamaños de ventana (desde ~`900×620` hasta `1920×1080+`).

## Direction contract

- **THESIS:** Reemplaza el tablero oscuro rígido de tres columnas fijas por una mesa de trabajo diurna estilo **Atlas Urbano de Infraestructura** (`#F7F8FA` papel técnico de dibujo, `#131820` barra superior y riel de comandos obsidiana, `#0284C7` cobalto hidráulico para trazados activos) que mantiene legible el grafo dirigido (`46` nodos, `59` tuberías) y todos los controles esenciales en cualquier tamaño de ventana sin recortes ni colisiones.
- **OWN-WORLD:** Riel izquierdo y barra superior en obsidiana mate (`#131820` / `#1B222D` / borde `#2A3444`) frente a un lienzo cartográfico claro (`#F7F8FA` / retícula `#E6EAF0`) y panel analítico blanco (`#FFFFFF` / divisores 1px `#D8DFE8`). Cero tarjetas anidadas ni ornamentos decorativos; cuarentena estricta de color para que solo las 5 categorías de utilización, el sumidero PTAR (`#0D9488`) y la ruta seleccionada (`#0284C7`) destaquen con máxima claridad.
- **STORY:** Al abrir o redimensionar la app, el usuario identifica de inmediato el estado crítico de la red, reproduce o recorre el tiempo sin parpadeos en las gráficas, traza rutas `BFS`/`DFS`/aguas arriba/aguas abajo con lectura tramo a tramo y consulta/compara los 5 escenarios o exporta reportes desde cualquier resolución.
- **FIRST VIEWPORT:** Barra superior adaptativa (título del proyecto + acciones de archivo/reporte que colapsan a menú compacto en ventanas estrechas), banda KPI/estado adaptable, riel izquierdo colapsable con scroll por rueda del ratón (`Escenario y Parámetros`, `Escala de Utilización`, `Consultas y Recorridos`), lienzo central `NetworkCanvas` con barra flotante de zoom/ajuste y reproductor temporal (`Inicio`, `-1`, `Play/Pausa` unificado, `+1`, `Velocidad`, `Balance de masa`), y panel derecho colapsable (`Inspector`, `Críticas`, `Evolución`, `Comparación`) que en pantallas estrechas funciona como cajón/pestaña conmutable sin aplastar el grafo.
- **FORM:** Candidato 4 (*Atlas Urbano de Infraestructura*), elevado con disciplina tabular de tablero de salidas (columnas numéricas alineadas en KPIs y tablas), cuarentena cromática de léxico técnico (jerarquía tipográfica sin ruido) y seguimiento tramo-a-tramo en rutas `BFS`/`DFS` (`Fuente → Tramos → PTAR 31`). `seed:87601e9bf2c85850`.
- **FINISH:** unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
