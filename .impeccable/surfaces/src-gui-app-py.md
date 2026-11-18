---
version: 2
slug: "src-gui-app-py"
primary_target: "src/gui/app.py"
related_targets: ["src/gui/network_canvas.py","src/gui/charts_panel.py","src/gui/theme.py","src/gui/icons.py"]
---

# Surface Brief — Simulador Hidráulico Ciudad Bicentenario

## Scope and Visitor Mode

- **Surface:** Aplicación de escritorio Python/Tkinter (`src/gui/app.py`, `network_canvas.py`, `charts_panel.py`, `theme.py`, `icons.py`)
- **Mode:** `operate`

## Audience, Job, Action & Constraints

- **Audiencia:** Estudiantes/evaluadores de Estructuras de Datos y analistas hidráulicos en portátiles, proyectores o monitores amplios.
- **Idioma:** 100 % en español en toda la presentación gráfica (títulos, escenarios, parámetros, reglas de bifurcación/hietograma, tablas, gráficas, tooltips, inspector y barra de estado).
- **Paleta fijada por el usuario:** `#4A4A4A` (Grafito), `#CBCBCB` (Plata mineral), `#FFFFE3` (Vitela / Marfil cálido) y `#6D8196` (Azul pizarra), manteniendo intacta y en cuarentena la escala oficial de 5 colores de la Sección 7 (`#22c55e`, `#eab308`, `#f97316`, `#ef4444`, `#991b1b` / `#7f1d1d`).
- **Restricciones:** Preservar 100 % de los requisitos funcionales, pruebas unitarias (`tests/test_gui.py` y demás), Python 3.11 + Tkinter + Matplotlib, y adaptabilidad total a distintos tamaños de ventana (`compact < 940px`, `medium 940–1219px`, `wide >= 1220px`).

## Direction contract

- **THESIS:** Abandona el riel lateral oscuro obsidiana y los paneles blancos genéricos para articular una mesa cartográfica de archivo en **Vitela (`#FFFFE3`), Plata Mineral (`#CBCBCB`), Grafito (`#4A4A4A`) y Azul Pizarra (`#6D8196`)**, donde los datos hidráulicos viven sobre láminas claras de alto contraste ancladas por una cabecera y consola de bitácora en grafito sólido.
- **OWN-WORLD:** Cabecera de comando y barra de cierre en `#4A4A4A` con regla estructural `#6D8196` (2px) y tipografía `#FFFFE3`; muelles laterales en `#CBCBCB` que enmarcan tarjetas planas `#FFFFE3` con filetes `1px` `#4A4A4A`; lienzo central sobre papel vitela `#FFFFE3` con retícula ortogonal sutil y cápsula flotante `#4A4A4A`; toda interacción primaria y foco de selección resueltos en `#6D8196` con tinta `#FFFFE3`.
- **STORY:** Al abrir o redimensionar la ventana, el operador lee de inmediato el reloj de simulación sobre placa `#4A4A4A` junto a los 4 indicadores KPI en `#FFFFE3`, identifica tuberías críticas sobre la lámina marfil sin deslumbramiento, ejecuta recorridos `BFS`/`DFS` con lectura en bitácora oscura y alterna entre los 5 escenarios en español fluido.
- **FIRST VIEWPORT:** Cabecera superior en `#4A4A4A` (emblema vectorial de red, título, insignia de dataset/escenario, conmutadores `Controles`/`Análisis` y acciones de archivo/reporte), seguida de franja de telemetría (reloj `#4A4A4A` + 4 KPIs `#FFFFE3` con acento superior `#6D8196`), muelle izquierdo `#CBCBCB` con tarjetas `#FFFFE3` (`Simulación` / `Recorridos`), lienzo central `#FFFFE3` con controles flotantes `#4A4A4A` y reproductor inferior `#CBCBCB`/`#FFFFE3`, y muelle derecho analítico (`Inspector`, `Tuberías Críticas`, `Evolución`, `Comparación`) cerrado por barra de estado `#4A4A4A`.
- **FORM:** Candidato 5 (*Lámina Cartográfica de Archivo Hidráulico*), elevado por la disciplina de jerarquía por cambio de fila en tiempo real (del tablero de salidas) y la legibilidad de diagrama de tránsito en codos e intersecciones (`PTAR 31` y rutas `BFS`/`DFS` con lectura directa). `seed:7bc550bcc657cb12`.
- **FINISH:** Verificado en captura real sobre `wide (1440×880)`, `medium (1080×680)` y `compact (840×580)` + suite completa (`23` pruebas unitarias en verde). Veredicto: `ship`. Documentado en `DESIGN.md` y `.impeccable/design.json`.
