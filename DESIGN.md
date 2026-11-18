---
name: Ciudad Bicentenario — Lámina Cartográfica de Archivo Hidráulico
description: Sistema visual en español para la simulación hidráulica y análisis de grafos de la red de alcantarillado de Ciudad Bicentenario.
colors:
  graphite-shell: "#4a4a4a"
  graphite-surface: "#3d3d3d"
  graphite-elevated: "#595959"
  mineral-silver: "#cbcbcb"
  silver-hover: "#bcbcbc"
  ivory-vellum: "#ffffe3"
  ivory-subtle: "#f2f2d5"
  ivory-alt-row: "#f7f7da"
  slate-steel: "#6d8196"
  slate-steel-hover: "#5a6c80"
  slate-steel-text: "#495b6e"
  slate-soft: "#e4e8df"
  ink-primary: "#4a4a4a"
  ink-muted: "#5a6570"
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
    fontFamily: "Segoe UI, Arial, sans-serif"
    fontSize: "8.5pt"
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: "Segoe UI, Arial, sans-serif"
    fontSize: "8pt"
    fontWeight: 700
    lineHeight: 1.2
  mono:
    fontFamily: "Cascadia Mono, Consolas, monospace"
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
  button-primary:
    backgroundColor: "{colors.slate-steel}"
    textColor: "{colors.ivory-vellum}"
    rounded: "{rounded.none}"
    padding: "4px 10px"
  button-secondary-dark:
    backgroundColor: "{colors.graphite-elevated}"
    textColor: "{colors.ivory-vellum}"
    rounded: "{rounded.none}"
    padding: "4px 9px"
  button-secondary-dock:
    backgroundColor: "{colors.mineral-silver}"
    textColor: "{colors.graphite-shell}"
    rounded: "{rounded.none}"
    padding: "4px 8px"
  sheet-card:
    backgroundColor: "{colors.ivory-vellum}"
    borderColor: "{colors.graphite-shell}"
    rounded: "{rounded.none}"
---

# Design System: Ciudad Bicentenario — Lámina Cartográfica de Archivo Hidráulico

## Overview

**Creative North Star: "Lámina Cartográfica de Archivo Hidráulico"**

La interfaz organiza el simulador como una mesa cartográfica de ingeniería civil sobre papel vitela cálido (`#FFFFE3`), enmarcada por muelles estructurales en plata mineral (`#CBCBCB`), anclada arriba y abajo por una envolvente de comando en grafito (`#4A4A4A`) y articulada interactivamente en azul pizarra (`#6D8196`).

Toda la presentación visible está redactada íntegramente en español —incluyendo escenarios (`Tiempo seco`, `Lluvia ligera`, `Lluvia moderada`, `Lluvia fuerte`, `Lluvia extrema`), reglas de bifurcación (`Proporcional`, `Equitativa`) e hietograma (`Uniforme`, `Triangular`)— sin alterar los identificadores internos del motor de simulación ni la escala oficial de 5 colores de la Sección 7.

**Key Characteristics:**
- Cuatro anclas cromáticas estrictas (`#4A4A4A`, `#CBCBCB`, `#FFFFE3`, `#6D8196`) con separación arquitectónica por filetes de `1px` y reglas de acento de `2px–3px`.
- Cuarentena cromática estricta: los colores de semáforo permanecen reservados exclusivamente para la escala oficial de 5 niveles de la Sección 7 y las alertas de balance/sobrecarga.
- Láminas estructuradas (`#FFFFE3`) con encabezados sólidos (`#4A4A4A` / `#6D8196`) dentro de muelles `#CBCBCB`, y bitácora de recorridos en consola oscura `#4A4A4A`.
- Iconografía vectorial rasterizada con supermuestreo `3x` en `src/gui/icons.py` (`Pillow`), incluyendo el emblema de red en cabecera.

## Colors

### Primary
- **Slate Steel** (`#6D8196`): Acciones primarias (`Ejecutar simulación`, `Reproducir`, `Generar Reporte`, `Buscar`, `Comparar 5 Escenarios`), pestañas activas, regla divisoria de cabecera, nodo sumidero PTAR `31`, barras superiores de KPIs y curvas principales en Matplotlib.
- **Slate Steel Hover** (`#5A6C80`): Estado hover sobre botones primarios con contraste ≥ 4.9:1 frente a `#FFFFE3`.
- **Slate Text on Light** (`#495B6E`): Títulos de sección en el inspector y lectura destacada de la PTAR `31` sobre `#FFFFE3` (contraste ≥ 6.2:1).

### Secondary
- **Official Utilization Scale** (`#22c55e`, `#eab308`, `#f97316`, `#ef4444`, `#991b1b`): Escala normativa de 5 niveles (`0–25 %`, `>25–50 %`, `>50–75 %`, `>75–100 %`, `>100 %`), acompañada sobre `#FFFFE3` por tonos de texto accesibles (`#15803d`, `#854d0e`, `#c2410c`, `#dc2626`, `#991b1b`).

### Neutral
- **Graphite Shell** (`#4A4A4A`): Barra superior, barra de estado inferior, encabezados de tablas `Treeview`, placa del reloj en vivo, cápsula flotante de zoom, consola de bitácora, nodos fuente y bordes estructurales de `1px`.
- **Mineral Silver** (`#CBCBCB`): Fondo base de los muelles laterales (`left_panel`, `right_panel`), marco central, botones secundarios de muelle y riel de barra temporal.
- **Ivory Vellum** (`#FFFFE3`): Papel de dibujo técnico de `NetworkCanvas`, fondo de tarjetas de parámetros, inspector, tablas, reproductor y gráficas Matplotlib (`#F7F7DA` en filas alternas y fondo de ejes).

### Named Rules
**The Color Quarantine Rule.** Ningún elemento decorativo introduce colores ajenos a `#4A4A4A`, `#CBCBCB`, `#FFFFE3` y `#6D8196`; los tonos verde, ámbar, naranja y rojo quedan restringidos a los 5 tramos de utilización hidráulica, el anillo de sobrecarga en pozos y los indicadores reales de criticidad/balance.

## Typography

**Display / Titles Font:** `Inter Medium` (500, desde `assets/fonts/`, respaldo `Segoe UI`)
**Body / UI Controls Font:** `Segoe UI` (`Arial` como respaldo en sistema)
**Label/Mono Font:** `Cascadia Mono` (`Consolas` como respaldo en sistema)

### Hierarchy
- **Headline** (Bold, `11pt`): Título principal de la barra superior (`Simulador Hidráulico · Ciudad Bicentenario`).
- **Title** (Bold, `9pt`): Encabezados de lámina (`Escenario y parámetros`, `Escala oficial de utilización`, `Búsqueda y recorridos`, `Bitácora de recorrido`) y títulos de subgráficas.
- **Body** (Regular, `8.5pt–9pt`): Etiquetas de controles, filas del inspector y barra de estado.
- **Label** (Bold, `7pt–8pt`): Captions de KPIs (`UTILIZACIÓN MÁX.`, `CRÍTICAS (≥75%)`, `SOBRECARGA (>100%)`, `DESCARGA PTAR 31`), pestañas y botones.
- **Mono** (Regular/Bold, `7pt–10pt`): Reloj de simulación, cifras tabulares, tablas `Treeview`, bitácora y etiquetas de tuberías.

### Named Rules
**The Tabular Numerals Rule.** Todo caudal, porcentaje de utilización, tiempo de simulación y error de balance de masa se renderiza en fuente monoespaciada (`self.mono_font`).

## Layout

Ventana mínima `780×540` con `PanedWindow` horizontal y tres umbrales adaptativos:
- **Wide (`>= 1220px`):** Barra superior expandida con emblema, 5 botones de acción directa, muelle izquierdo (`288px`), franja de telemetría + lienzo central + reproductor y muelle derecho (`382px`) abiertos simultáneamente.
- **Medium (`940–1219px`):** Menú agrupado `Archivo y Modelo`, reproductor compacto icónico, reloj condensado y pestañas ajustadas sin ocultar las opciones `IDs` / `% Util.`.
- **Compact (`< 940px`):** Barra superior condensada (`Archivo` + `Reporte`), cajones laterales mutuamente excluyentes (`Controles` o `Análisis`), columnas compactas tanto en `Comparación` (6 columnas) como en `Tuberías Críticas` (encabezados y estados abreviados sin recorte).

## Elevation & Depth

Superficie **plana arquitectónica sin sombras**: la jerarquía se construye por planos tonales (`#CBCBCB` → `#FFFFE3` → `#4A4A4A` / `#6D8196`) delimitados por líneas rectas de `1px` (`#4A4A4A`) y reglas de acento de `2px–3px` (`#6D8196`).

## Shapes

Contenedores, láminas, botones, pestañas, campos de entrada y placas del grafo emplean esquinas rectas (`0px`–`1px`). En `NetworkCanvas`, las fuentes usan círculo `#4A4A4A` con borde `#6D8196` e insignia `Fuente` en `#CBCBCB`, los pozos usan `#FFFFE3` con trazo `#4A4A4A`, y la PTAR `31` usa `#6D8196` con borde `#4A4A4A` y placa oscura `PTAR Punta Canoa · 31`.

## Do's and Don'ts

### Do:
- **Do** mantener toda la presentación visible en español y la escala oficial de 5 colores de la Sección 7 intacta.
- **Do** adaptar columnas y encabezados de `tree_critical` y `tree_comp` al ancho real del panel derecho para evitar recortes en ventanas compactas.
- **Do** actualizar únicamente las líneas cursoras de `TemporalChartsPanel` durante la reproducción temporal.
- **Do** usar iconos vectoriales rasterizados desde `src/gui/icons.py`.

### Don't:
- **Don't** introducir colores saturados fuera de la paleta `#4A4A4A`, `#CBCBCB`, `#FFFFE3`, `#6D8196` y la escala de la Sección 7.
- **Don't** usar glifos Unicode informales como sistema de iconos ni sombras paralelas.
- **Don't** acoplar los textos traducidos al español de la GUI con los valores internos en inglés exigidos por `SimulationConfig` (`proportional`/`equal`, `uniform`/`triangular`).
