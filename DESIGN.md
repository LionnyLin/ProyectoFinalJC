---
name: Ciudad Bicentenario — Simulador Hidráulico
description: Atlas Urbano de Infraestructura para simulación temporal y análisis de grafos en la red de alcantarillado de Ciudad Bicentenario.
colors:
  hydraulic-cobalt: "#0369a1"
  hydraulic-cobalt-hover: "#075985"
  hydraulic-sky-on-dark: "#38bdf8"
  hydraulic-sky-soft: "#e0f2fe"
  ptar-emerald: "#0f766e"
  obsidian-shell: "#131820"
  obsidian-surface: "#1b222d"
  obsidian-elevated: "#242d3b"
  obsidian-border: "#2f3b4e"
  porcelain-drafting: "#f7f8fa"
  paper-white: "#ffffff"
  paper-subtle: "#f2f4f7"
  paper-border: "#d6dee8"
  ink-primary: "#111827"
  ink-secondary: "#334155"
  ink-muted: "#64748b"
  tier-low: "#22c55e"
  tier-moderate: "#eab308"
  tier-high: "#f97316"
  tier-critical: "#ef4444"
  tier-overloaded: "#991b1b"
typography:
  headline:
    fontFamily: "Inter, Segoe UI, Arial, sans-serif"
    fontSize: "11pt"
    fontWeight: 700
    lineHeight: 1.25
  title:
    fontFamily: "Inter, Segoe UI, Arial, sans-serif"
    fontSize: "9pt"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "Inter, Segoe UI, Arial, sans-serif"
    fontSize: "8.5pt"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Inter, Segoe UI, Arial, sans-serif"
    fontSize: "8pt"
    fontWeight: 700
    lineHeight: 1.2
  mono:
    fontFamily: "JetBrains Mono, Cascadia Mono, Consolas, monospace"
    fontSize: "9pt"
    fontWeight: 400
    lineHeight: 1.35
rounded:
  none: "0px"
  sharp: "1px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
components:
  button-primary-light:
    backgroundColor: "{colors.hydraulic-cobalt}"
    textColor: "{colors.paper-white}"
    rounded: "{rounded.none}"
    padding: "4px 10px"
  button-primary-dark:
    backgroundColor: "{colors.hydraulic-sky-on-dark}"
    textColor: "{colors.obsidian-shell}"
    rounded: "{rounded.none}"
    padding: "4px 10px"
  button-secondary-light:
    backgroundColor: "{colors.paper-subtle}"
    textColor: "{colors.ink-primary}"
    rounded: "{rounded.none}"
    padding: "4px 8px"
  button-secondary-dark:
    backgroundColor: "{colors.obsidian-elevated}"
    textColor: "{colors.paper-white}"
    rounded: "{rounded.none}"
    padding: "4px 9px"
---

# Design System: Ciudad Bicentenario — Simulador Hidráulico

## Overview

**Creative North Star: "Atlas Urbano de Infraestructura"**

El sistema visual organiza la mesa de trabajo hidráulica como un plano técnico de ingeniería civil de alta legibilidad diurna: una envolvente de comando en obsidiana mate (`#131820`) sostiene los parámetros y herramientas de recorrido de grafos, mientras el lienzo central de porcelana reticulada (`#F7F8FA`) y los paneles editoriales blancos (`#FFFFFF`) garantizan contraste nítido en portátiles y proyectores de aula.

La densidad y la jerarquía responden al modo operativo de ingeniería: divisores rectos de `1px`, ausencia total de tarjetas decorativas anidadas y una cuarentena cromática estricta para que las cinco categorías de utilización hidráulica, el sumidero de la PTAR Punta Canoa y las rutas `BFS`/`DFS` activas destaquen de inmediato sin ruido visual.

**Key Characteristics:**
- Contraste diurno de plano cartográfico (`#F7F8FA` / `#FFFFFF`) anclado por una barra y riel de control en obsidiana (`#131820`).
- Cuarentena cromática estricta: los tonos semánticos pertenecen exclusivamente a la escala oficial de 5 niveles de la Sección 7, a la PTAR (`#0F766E`) y al foco cobalto (`#0369A1` / `#38BDF8`).
- Numerales tabulares monoespaciados alineados en banda KPI, tablas de criticidad, inspector y comparativa de escenarios.
- Iconografía vectorial uniforme generada con `Pillow` mediante supermuestreo `3x` (`src/gui/icons.py`), sin glifos Unicode informales.

## Colors

La paleta separa la zona de mando oscura del plano analítico claro y reserva el color saturado únicamente para el foco interactivo y los estados hidráulicos reales.

### Primary
- **Hydraulic Cobalt** (`#0369a1`): Acciones primarias sobre superficies claras (`Reproducir`, `Comparar 5 Escenarios`), selección de tuberías/nodos en lienzo y texto de encabezados activos.
- **Hydraulic Cobalt Hover** (`#075985`): Estado hover y activo sobre botones primarios claros.
- **Hydraulic Sky on Dark** (`#38bdf8`): Acento de foco y CTA principal sobre la barra superior y el riel obsidiana (`Ejecutar simulación`, `Buscar`, botones de panel activo).
- **Hydraulic Sky Soft** (`#e0f2fe`): Resaltado de filas seleccionadas en tablas y etiquetas de rutas `BFS`/`DFS` en el grafo.

### Secondary
- **PTAR Emerald** (`#0f766e`): Reservado exclusivamente para el nodo sumidero terminal (`31`, PTAR Punta Canoa), su etiqueta y la lectura de descarga acumulada.
- **Official Utilization Scale** (`#22c55e`, `#eab308`, `#f97316`, `#ef4444`, `#991b1b`): Escala normativa de 5 niveles (`0–25 %`, `>25–50 %`, `>50–75 %`, `>75–100 %`, `>100 %`), acompañada sobre blanco por tonos de texto accesibles (`#15803d`, `#a16207`, `#c2410c`, `#dc2626`, `#991b1b`).

### Neutral
- **Obsidian Shell** (`#131820`): Fondo base de la barra superior y del riel lateral izquierdo.
- **Obsidian Surface & Elevated** (`#1b222d`, `#242d3b`): Campos de entrada oscuros y botones secundarios del shell, separados por bordes `1px` (`#2f3b4e`).
- **Porcelain Drafting Ground** (`#f7f8fa`): Papel técnico del `NetworkCanvas`, con retícula menor (`#ebeef3`) y mayor (`#dce2ec`).
- **Paper White & Subtle** (`#ffffff`, `#f2f4f7`): Superficies del panel derecho de análisis, banda KPI, reproductor temporal y gráficas Matplotlib, con divisores `1px` (`#d6dee8`).
- **Ink Ramp** (`#111827`, `#334155`, `#64748b`): Jerarquía de texto principal, secundario y metadatos sobre fondo claro.

### Named Rules
**The Color Quarantine Rule.** Ningún elemento decorativo utiliza colores saturados; los tonos verdes, ámbar, naranja y rojo quedan restringidos estrictamente a los 5 tramos de utilización hidráulica, la PTAR Punta Canoa y los indicadores de conservación de masa.

## Typography

**Display / Titles Font:** `Inter Medium` (500, desde `assets/fonts/`, respaldo `Segoe UI`)
**Body / UI Controls Font:** `Segoe UI` (`Arial` como respaldo en sistema)
**Label/Mono Font:** `Cascadia Mono` (`Consolas` como respaldo en sistema)

**Character:** Tipografía utilitaria de precisión cartográfica que separa con claridad los títulos de panel en sans-serif de los caudales, porcentajes y longitudes tabulares en fuente monoespaciada.

### Hierarchy
- **Headline** (Bold, `11pt`, line-height `1.25`): Título principal de la barra superior (`Red de Alcantarillado · Ciudad Bicentenario`).
- **Title** (Bold, `9pt`, line-height `1.3`): Encabezados de sección en riel (`Escenario y parámetros`, `Escala de utilización`, `Consultas y recorridos`) y títulos de subgráficas.
- **Body** (Regular, `8.5pt–9pt`, line-height `1.4`): Etiquetas de controles, filas descriptivas del inspector y estado del sistema.
- **Label** (Bold, `7pt–8pt`): Captions de tarjetas KPI (`UTIL. MÁX.`, `CRÍTICAS ≥75%`, `SOBREC. >100%`, `PTAR 31`), pestañas y botones compactos.
- **Mono** (Regular/Bold, `7pt–10pt`): Lecturas numéricas tabulares (`0.3054 m³/s`, `265.9%`, `t = 60.0 / 90 min`), tablas `Treeview` y etiquetas de tuberías sobre el lienzo.

### Named Rules
**The Tabular Numerals Rule.** Todo caudal, porcentaje de utilización, tiempo de simulación y error de balance de masa se renderiza en la fuente monoespaciada (`self.mono_font`) para mantener columnas estables durante la reproducción cuadro a cuadro.

## Layout

La aplicación adopta una estructura de tres regiones dentro de un `PanedWindow` horizontal con ventana mínima `780×540` y tres umbrales adaptativos:
- **Wide (`>= 1220px`):** Barra superior expandida con 5 botones de acción directa, riel izquierdo obsidiana (`272–292px`), lienzo central con banda KPI de 2 filas y panel derecho blanco (`332–392px`) abiertos simultáneamente.
- **Medium (`940–1219px`):** Acciones secundarias de archivo agrupadas en menú desplegable `Archivo y Modelo`, rieles ajustados (`264–272px` / `292–334px`), reproductor temporal compacto con botones icónicos y pestañas analíticas adaptadas.
- **Compact (`< 940px`):** Barra superior condensada (`Archivo` + `Reporte`), cajones laterales mutuamente excluyentes (`Parámetros` o `Análisis` alternando sin aplastar el lienzo central) y conmutador interno `Simulación | Recorridos` en el riel izquierdo para evitar desplazamientos ciegos.

## Elevation & Depth

Superficie **plana y arquitectónica sin sombras paralelas**: la profundidad se comunica únicamente mediante contraste de valor entre el shell obsidiana (`#131820`), el papel de dibujo (`#f7f8fa`) y los paneles blancos (`#ffffff`), delimitados por líneas finas de `1px` (`#2f3b4e` en oscuro, `#d6dee8` en claro). Los controles flotantes sobre el lienzo (barra de zoom y etiquetas de tuberías) emplean fondo blanco sólido con borde `1px` (`#cbd5e1` / `#e2e8f0`).

### Named Rules
**The Flat-By-Hairline Rule.** Las regiones no apilan tarjetas ni sombras; cada separación estructural usa una línea recta de `1px` o un cambio limpio de plano tonal.

## Shapes

Geometría **rectilínea y de precisión técnica**: contenedores, botones, pestañas, campos de entrada y etiquetas de tuberías usan esquinas vivas (`0px`–`1px` de borde sólido) coherentes con un plano de ingeniería. En el grafo, todos los vértices son círculos escalados dinámicamente según la distancia mínima entre nodos conectados (`node_radius <= min_edge_dist * 0.27`), con anillos concéntricos discontinuos (`#d97706`) para pozos con volumen almacenado por sobrecarga.

## Components

### Buttons
- **Shape:** Rectángulo plano sin relieve (`relief="flat"`, borde `1px`).
- **Primary (Light / Dark):** `#0369a1` con texto blanco `#ffffff` en áreas claras (`Reproducir`, `Comparar 5 Escenarios`); `#38bdf8` con tinta oscura `#0b1220` sobre obsidiana (`Ejecutar simulación`, `Buscar`, `Generar Reporte`).
- **Secondary:** `#f2f4f7` con borde `#d6dee8` sobre claro; `#242d3b` con borde `#2f3b4e` sobre oscuro. Estados hover consistentes (`#e6ecf4` / `#2d3849`).
- **Fixed Transport Width:** `btn_play_pause` fija su ancho en píxeles (`102px` completo / `32px` compacto) para que alternar `Reproducir` y `Pausar` no desplace los controles vecinos.

### Cards / Containers
- **Corner Style:** Esquinas rectas (`0px`), sin tarjetas anidadas.
- **Background:** Banda KPI en `#f8fafc` con rejilla uniforme de 4 columnas; secciones del riel en `#131820` separadas por reglas `1px` `#2f3b4e`.

### Inputs / Fields
- **Style:** `Spinbox`, `Entry` y `TCombobox` sobre `#1b222d` con borde `1px` `#2f3b4e` y texto `#f4f6f9` en el riel oscuro; `highlightcolor` en `#38bdf8` al enfocar.

### Navigation
- **Topbar + Segmented Rail Switcher:** Botones de alternancia de panel (`Parámetros`, `Análisis`) en barra superior, conmutador `Simulación | Recorridos` en el riel izquierdo y `ttk.Notebook` de 4 pestañas (`Inspector`, `Tuberías Críticas`/`Críticas`, `Evolución`, `Comparación`/`Comparar`) en el panel derecho.

### Network Drafting Canvas
- Retícula ortogonal doble (`36px` menor `#ebeef3`, `144px` mayor `#dce2ec`) sobre `#f7f8fa`, con controles flotantes de zoom (`−`, `100%`, `+`, `Ajustar`), detección de colisiones entre etiquetas de tuberías por prioridad (seleccionada > resaltada > sobrecargada > crítica) y desplazamiento lateral automático en tramos verticales para evitar cubrir las flechas de flujo.

## Do's and Don'ts

### Do:
- **Do** mantener los 5 colores oficiales de utilización de la Sección 7 intactos sobre el lienzo y las leyendas.
- **Do** adaptar columnas (`displaycolumns`), textos de pestañas y visibilidad de barras auxiliares según el ancho real del contenedor, sin recortar cifras ni encabezados.
- **Do** actualizar únicamente las líneas cursoras de `TemporalChartsPanel` durante la reproducción temporal para evitar parpadeos de Matplotlib.
- **Do** usar iconos vectoriales rasterizados desde `src/gui/icons.py` (`Pillow`) en todos los controles de acción y transporte.

### Don't:
- **Don't** introducir tarjetas con bordes redondeados pesados, gradientes decorativos ni colores ajenos fuera de la paleta definida.
- **Don't** colocar etiquetas de sección numeradas (`01 / 02`), kickers decorativos ni metadatos del tema en la barra de estado.
- **Don't** permitir que las etiquetas del grafo se superpongan sobre nodos vecinos o crucen el eje de tuberías verticales.
- **Don't** usar glifos Unicode o emojis como sistema de iconos en botones o menús.
