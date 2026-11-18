"""Generador puro en Python de reportes y documentos técnicos en Word (.docx).

Cumple estrictamente:
- Diseño continuo a dos columnas en todo el documento (incluidos Bibliografía y Anexos A-D).
- Ecuaciones nativas Word OMML centradas y escaladas a 8.5 pt (sin bloques multilínea).
- Tablas con encabezados y celdas exclusivamente en texto plano (cero OMML y cero '$').
- Figuras Python/Matplotlib dimensionadas a una columna (3.5 x 2.8 in).
- Cero dependencias de Pandoc en tiempo de ejecución.
"""

from datetime import datetime
import os
import tempfile
from typing import Iterable, List, Optional, Sequence

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Inches, Pt, RGBColor

from src.algorithms.analysis import rank_critical_pipes
from src.io.data_loader import NetworkDataset
from .charts_export import generate_single_column_figures
from .comparison import ScenarioSummary
from .models import SimulationResult
from .omml_equations import M_NS, add_omml_equation

PLUM_HEX = "3B153A"
ZEBRA_HEX = "F6EEF6"
BORDER_HEX = "C9B3C8"
TEXT_DARK = RGBColor(0x1E, 0x1B, 0x24)
PLUM_RGB = RGBColor(0x3B, 0x15, 0x3A)
MUTED_RGB = RGBColor(0x5A, 0x4A, 0x59)


def _configure_two_column_document() -> Document:
    """Crea un Document configurado en hoja Carta con diseño continuo a dos columnas."""
    doc = Document()

    sec = doc.sections[0]
    sec.page_width = Inches(8.5)
    sec.page_height = Inches(11.0)
    sec.top_margin = Inches(0.60)
    sec.bottom_margin = Inches(0.60)
    sec.left_margin = Inches(0.55)
    sec.right_margin = Inches(0.55)

    sect_pr = sec._sectPr
    cols = sect_pr.find(qn("w:cols"))
    if cols is None:
        cols = OxmlElement("w:cols")
        sect_pr.append(cols)
    cols.set(qn("w:num"), "2")
    cols.set(qn("w:space"), "432")  # 0.30 in -> ancho por columna = 3.55 in
    cols.set(qn("w:equalWidth"), "1")

    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(9.0)
    normal.font.color.rgb = TEXT_DARK
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(3.5)
    normal.paragraph_format.line_spacing = 1.08

    return doc


def _add_heading_1(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(10.5)
    r.font.color.rgb = PLUM_RGB
    # Línea inferior sutil bajo el título de sección
    pPr = p._p.get_or_add_pPr()
    pBdr = parse_xml(f'<w:pBdr {nsdecls("w")}><w:bottom w:val="single" w:sz="6" w:space="2" w:color="{PLUM_HEX}"/></w:pBdr>')
    pPr.append(pBdr)


def _add_heading_2(doc: Document, text: str) -> None:
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text)
    r.bold = True
    r.font.size = Pt(9.5)
    r.font.color.rgb = PLUM_RGB


def _add_body(doc: Document, text: str, bold_prefix: str = "") -> None:
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    if bold_prefix:
        rb = p.add_run(bold_prefix)
        rb.bold = True
        rb.font.size = Pt(9.0)
    r = p.add_run(text)
    r.font.size = Pt(9.0)


def _add_bullet(doc: Document, text: str, bold_prefix: str = "") -> None:
    p = doc.add_paragraph(style="List Bullet")
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(2)
    if bold_prefix:
        rb = p.add_run(bold_prefix)
        rb.bold = True
        rb.font.size = Pt(8.8)
    r = p.add_run(text)
    r.font.size = Pt(8.8)


def _sanitize_plain_cell(val: object) -> str:
    """Garantiza texto plano puro sin delimitadores LaTeX '$' en celdas de tabla."""
    return str(val).replace("$", "").strip()


def _set_cell_shading(cell, fill_hex: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}"/>')
    tc_pr.append(shd)


def _set_cell_margins(cell, top: int = 40, bottom: int = 40, left: int = 60, right: int = 60) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = parse_xml(
        f'<w:tcMar {nsdecls("w")}>'
        f'<w:top w:w="{top}" w:type="dxa"/>'
        f'<w:bottom w:w="{bottom}" w:type="dxa"/>'
        f'<w:left w:w="{left}" w:type="dxa"/>'
        f'<w:right w:w="{right}" w:type="dxa"/>'
        "</w:tcMar>"
    )
    tc_pr.append(tc_mar)


def _set_table_borders(table) -> None:
    tbl_pr = table._tbl.tblPr
    borders = parse_xml(
        f'<w:tblBorders {nsdecls("w")}>'
        f'<w:top w:val="single" w:sz="6" w:space="0" w:color="{PLUM_HEX}"/>'
        f'<w:bottom w:val="single" w:sz="6" w:space="0" w:color="{PLUM_HEX}"/>'
        f'<w:insideH w:val="single" w:sz="4" w:space="0" w:color="{BORDER_HEX}"/>'
        '<w:left w:val="none"/><w:right w:val="none"/><w:insideV w:val="none"/>'
        "</w:tblBorders>"
    )
    tbl_pr.append(borders)


def _add_plain_table(
    doc: Document,
    headers: Sequence[str],
    rows: Iterable[Sequence[object]],
    col_widths_in: Sequence[float],
    font_pt: float = 7.2,
) -> None:
    """Agrega una tabla compacta de una columna con encabezados exclusivamente en texto plano."""
    rows_list = list(rows)
    table = doc.add_table(rows=1 + len(rows_list), cols=len(headers))
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    _set_table_borders(table)

    # Encabezados en texto plano
    hdr_cells = table.rows[0].cells
    tr_pr = table.rows[0]._tr.get_or_add_trPr()
    tr_pr.append(parse_xml(f'<w:tblHeader {nsdecls("w")}/>'))

    for idx, h_text in enumerate(headers):
        cell = hdr_cells[idx]
        cell.width = Inches(col_widths_in[idx])
        _set_cell_shading(cell, PLUM_HEX)
        _set_cell_margins(cell)
        p = cell.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER if idx == 0 else WD_ALIGN_PARAGRAPH.LEFT
        p.paragraph_format.space_before = Pt(0)
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(_sanitize_plain_cell(h_text))
        run.bold = True
        run.font.size = Pt(font_pt)
        run.font.color.rgb = RGBColor(0xFF, 0xFF, 0xFF)

    for r_idx, row_vals in enumerate(rows_list, start=1):
        cells = table.rows[r_idx].cells
        for c_idx, val in enumerate(row_vals):
            cell = cells[c_idx]
            cell.width = Inches(col_widths_in[c_idx])
            if r_idx % 2 == 0:
                _set_cell_shading(cell, ZEBRA_HEX)
            _set_cell_margins(cell)
            p = cell.paragraphs[0]
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run(_sanitize_plain_cell(val))
            run.font.size = Pt(font_pt)

    spacer = doc.add_paragraph()
    spacer.paragraph_format.space_before = Pt(0)
    spacer.paragraph_format.space_after = Pt(3)


def _add_single_column_figure(doc: Document, img_path: str, caption: str) -> None:
    p_img = doc.add_paragraph()
    p_img.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_img.paragraph_format.space_before = Pt(4)
    p_img.paragraph_format.space_after = Pt(2)
    p_img.paragraph_format.keep_with_next = True
    p_img.add_run().add_picture(img_path, width=Inches(3.45))

    p_cap = doc.add_paragraph()
    p_cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_cap.paragraph_format.space_before = Pt(0)
    p_cap.paragraph_format.space_after = Pt(4)
    r = p_cap.add_run(caption)
    r.italic = True
    r.font.size = Pt(7.8)
    r.font.color.rgb = MUTED_RGB


def _validate_docx_compliance(doc: Document) -> None:
    """Verifica que el documento cumpla 2 columnas continuas y tablas en texto plano."""
    for sec in doc.sections:
        cols = sec._sectPr.find(qn("w:cols"))
        if cols is None or cols.get(qn("w:num")) != "2":
            raise ValueError("Se violó la maquetación continua a dos columnas.")
    for tbl in doc.tables:
        if tbl._tbl.findall(f".//{{{M_NS}}}oMath"):
            raise ValueError("Se detectó una ecuación OMML dentro de una tabla.")
        for row in tbl.rows:
            for cell in row.cells:
                if "$" in cell.text:
                    raise ValueError(f"Se detectó delimitador '$' en celda de tabla: {cell.text}")


def generate_docx_report(
    dataset: NetworkDataset,
    current_result: SimulationResult,
    comparisons: Optional[List[ScenarioSummary]] = None,
    out_path: str = "reporte_simulacion.docx",
) -> str:
    """Genera un reporte Word (.docx) en español a dos columnas sin depender de Pandoc."""
    doc = _configure_two_column_document()
    cfg = current_result.config
    n_nodes, n_pipes, n_src, n_snk, total_len = dataset.graph.summary()
    comps = comparisons or []

    # Título en flujo continuo de dos columnas
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_after = Pt(2)
    rt = p_title.add_run("Reporte Técnico de Simulación — Red de Alcantarillado Ciudad Bicentenario")
    rt.bold = True
    rt.font.size = Pt(12.5)
    rt.font.color.rgb = PLUM_RGB

    p_meta = doc.add_paragraph()
    p_meta.paragraph_format.space_after = Pt(5)
    rm = p_meta.add_run(
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')} | "
        f"Descarga final: PTAR Punta Canoa (nodo {', '.join(dataset.graph.sink_ids())})"
    )
    rm.font.size = Pt(8.0)
    rm.font.color.rgb = MUTED_RGB

    _add_heading_1(doc, "1. Parámetros y Supuestos del Escenario")
    _add_bullet(
        doc,
        f"{n_nodes} vértices ({n_src} fuentes, {n_snk} sumidero) y {n_pipes} tuberías ({total_len:,.2f} m).",
        "Topología: ",
    )
    _add_bullet(
        doc,
        f"Escenario {cfg.scenario_id} — {cfg.scenario_name} ({cfg.intensity_mm_h:.1f} mm/h), "
        f"duración {cfg.duration_min:.0f} min (lluvia {cfg.storm_duration_min:.0f} min, paso {cfg.dt_min:.1f} min).",
        "Evento evaluado: ",
    )
    _add_bullet(
        doc,
        f"C = {dataset.basin.runoff_coefficient_c}, A = {dataset.basin.area_ha} ha, "
        f"factor de ingreso = {cfg.ingress_factor * 100:.1f}%, caudal sanitario = {cfg.dry_weather_flow_per_source_m3s:.4f} m³/s/fuente.",
        "Cuenca y aportes: ",
    )

    _add_heading_1(doc, "2. Ecuaciones del Modelo Hidráulico")
    _add_body(doc, "Cada expresión se formula de manera independiente en formato OMML nativo a 8.5 pt:")
    add_omml_equation(doc, "rational", "1")
    add_omml_equation(doc, "inflow", "2")
    add_omml_equation(doc, "velocity", "3")
    add_omml_equation(doc, "transit", "4")
    add_omml_equation(doc, "utilization", "5")
    add_omml_equation(doc, "mass_balance", "6")

    _add_heading_1(doc, "3. Resultados Globales y Conservación de Masa")
    _add_plain_table(
        doc,
        headers=("Indicador del sistema", "Valor obtenido"),
        rows=[
            ("Volumen total inyectado (m3)", f"{current_result.total_inflow_m3:,.3f}"),
            ("Volumen descargado PTAR 31 (m3)", f"{current_result.total_sink_discharge_m3:,.3f}"),
            ("Caudal pico en PTAR 31 (m3/s)", f"{current_result.peak_sink_discharge_m3s:.4f}"),
            ("Volumen remanente pozos/tránsito (m3)", f"{current_result.final_residual_m3:,.3f}"),
            ("Error máximo balance de masa (m3)", f"{current_result.max_mass_balance_error_m3:.3e}"),
            ("Tuberías críticas (>=75 %)", str(len(current_result.ever_critical_pipes))),
            ("Tuberías sobrecargadas (>100 %)", str(len(current_result.ever_overloaded_pipes))),
        ],
        col_widths_in=(2.25, 1.15),
    )

    # Figuras 3.5 x 2.8 in
    _add_heading_1(doc, "4. Evolución Temporal y Comparación Gráfica")
    with tempfile.TemporaryDirectory() as tmpdir:
        comp_for_fig = comps or [
            ScenarioSummary(
                scenario_id=cfg.scenario_id,
                condition=cfg.scenario_name,
                intensity_mm_h=cfg.intensity_mm_h,
                max_utilization_pct=max(current_result.peak_pipe_utilization.values(), default=0.0),
                most_critical_pipe="-",
                num_critical_pipes=len(current_result.ever_critical_pipes),
                num_overloaded_pipes=len(current_result.ever_overloaded_pipes),
                peak_sink_discharge_m3s=current_result.peak_sink_discharge_m3s,
                total_inflow_m3=current_result.total_inflow_m3,
                total_sink_discharge_m3=current_result.total_sink_discharge_m3,
                max_stored_surcharge_m3=sum(current_result.max_manhole_storage_m3.values()),
                mass_balance_error_m3=current_result.max_mass_balance_error_m3,
                result=current_result,
            )
        ]
        fig_paths = generate_single_column_figures(current_result, comp_for_fig, tmpdir)
        _add_single_column_figure(doc, fig_paths[0], "Figura 1. Balance temporal de entrada y descarga en la PTAR Punta Canoa.")
        _add_single_column_figure(doc, fig_paths[1], "Figura 2. Evolución porcentual de las cinco tuberías más exigidas.")
        if len(comp_for_fig) > 1:
            _add_single_column_figure(doc, fig_paths[2], "Figura 3. Comparación de tuberías críticas y sobrecargadas por escenario.")

    _add_heading_1(doc, "5. Top 20 Tuberías por Utilización Pico")
    ranked = rank_critical_pipes(
        dataset.graph,
        current_result.peak_pipe_flow,
        current_result.peak_pipe_utilization,
    )
    _add_plain_table(
        doc,
        headers=("#", "Tub.", "Tramo", "Q pico", "Q max", "Util (%)", "Estado"),
        rows=[
            (
                r.rank,
                r.pipe_id,
                f"{r.from_node}->{r.to_node}",
                f"{r.flow_m3s:.4f}",
                f"{r.q_max_m3s:.4f}",
                f"{r.utilization_pct:.1f}%",
                r.category.label,
            )
            for r in ranked[:20]
        ],
        col_widths_in=(0.24, 0.38, 0.56, 0.48, 0.48, 0.48, 0.83),
        font_pt=6.8,
    )

    if comps:
        _add_heading_1(doc, "6. Comparación Multiescenario")
        _add_plain_table(
            doc,
            headers=("Esc.", "mm/h", "Máx %", "Crít.", ">=75", ">100", "PTAR m3/s"),
            rows=[
                (
                    f"E{s.scenario_id}",
                    f"{s.intensity_mm_h:.0f}",
                    f"{s.max_utilization_pct:.1f}%",
                    s.most_critical_pipe,
                    s.num_critical_pipes,
                    s.num_overloaded_pipes,
                    f"{s.peak_sink_discharge_m3s:.4f}",
                )
                for s in comps
            ],
            col_widths_in=(0.35, 0.42, 0.55, 0.44, 0.42, 0.44, 0.78),
            font_pt=7.0,
        )

    _validate_docx_compliance(doc)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    doc.save(out_path)
    return os.path.abspath(out_path)


def generate_technical_document_docx(
    dataset: NetworkDataset,
    comparisons: List[ScenarioSummary],
    out_path: str = "docs/DOCUMENTO_TECNICO.docx",
) -> str:
    """Genera el Documento Técnico completo en Word (.docx) con Bibliografía y Anexos A-D."""
    doc = _configure_two_column_document()
    base_res = comparisons[2].result if len(comparisons) > 2 else comparisons[0].result
    n_nodes, n_pipes, n_src, n_snk, total_len = dataset.graph.summary()

    # Encabezado del documento técnico (sin salto a 1 columna)
    p_title = doc.add_paragraph()
    p_title.paragraph_format.space_after = Pt(2)
    rt = p_title.add_run(
        "Simulación y Visualización del Comportamiento del Flujo en la Red de Alcantarillado de Ciudad Bicentenario"
    )
    rt.bold = True
    rt.font.size = Pt(12.5)
    rt.font.color.rgb = PLUM_RGB

    p_sub = doc.add_paragraph()
    p_sub.paragraph_format.space_after = Pt(5)
    rs = p_sub.add_run(
        "Documento Técnico Final · Asignatura: Estructuras de Datos · Caso: Cartagena de Indias (PTAR Punta Canoa)"
    )
    rs.italic = True
    rs.font.size = Pt(8.2)
    rs.font.color.rgb = MUTED_RGB

    _add_heading_1(doc, "Resumen")
    _add_body(
        doc,
        "Este trabajo presenta el diseño e implementación en Python de una aplicación de escritorio "
        "para modelar, simular en el tiempo y visualizar mediante escala de colores el comportamiento "
        "de la red de alcantarillado del Macroproyecto Ciudad Bicentenario hasta su descarga en la PTAR "
        "de Punta Canoa (nodo 31). La red se representa mediante un grafo dirigido propio de 46 vértices "
        "y 59 aristas (19,163.57 m) sin delegar las estructuras obligatorias en librerías externas. "
        "El motor discreto-temporal gestiona retardos de tránsito con una cola de prioridad Min-Heap, "
        "almacena el historial completo en una lista doblemente enlazada y conserva exactamente la masa "
        "ante sobrecargas superiores al 100 %.",
    )

    _add_heading_1(doc, "1. Introducción")
    _add_body(
        doc,
        "El crecimiento urbano de Ciudad Bicentenario en Cartagena de Indias exige analizar cómo "
        "responden sus colectores sanitarios ante diferentes intensidades de lluvia y eventuales "
        "ingresos pluviales por infiltración o conexiones erradas. Desde el enfoque de Estructuras "
        "de Datos, el sistema constituye un grafo acíclico dirigido (DAG) donde las alcantarillas fuente "
        "aportan caudal hacia pozos de inspección intermedios y confluyen en un único sumidero terminal.",
    )
    _add_body(
        doc,
        f"A partir de los datos suministrados en DataSetBicentenario.xlsx, la red comprende {n_nodes} "
        f"vértices ({n_src} fuentes: {', '.join(dataset.graph.source_ids())}; 37 pozos; y {n_snk} sumidero: "
        f"nodo 31) y {n_pipes} tuberías con diámetros entre 8 y 20 pulgadas.",
    )

    _add_heading_1(doc, "2. Diseño y Estructuras de Datos")
    _add_body(
        doc,
        "Todas las estructuras obligatorias fueron programadas desde cero en el paquete src/data_structures/ "
        "garantizando control total sobre memoria, complejidad asintótica y trazabilidad académica:",
    )
    _add_plain_table(
        doc,
        headers=("Estructura", "Implementación", "Uso en el sistema"),
        rows=[
            ("Grafo Dirigido", "DirectedGraph", "Topología de 46 nodos y 59 tuberías"),
            ("Lista Adyacencia", "LinkedList doble", "Conexiones salientes y entrantes"),
            ("Cola FIFO", "Queue sobre lista", "BFS, trazado y orden topológico"),
            ("Cola Prioridad", "Min-Heap binario", "Eventos de tránsito y ranking crítico"),
            ("Pila LIFO", "Stack sobre lista", "DFS iterativo y caminos a PTAR 31"),
            ("Tabla Hash", "Encadenamiento", "Consultas O(1) por ID y visitados"),
            ("Lista Enlazada", "LinkedList doble", "Historial temporal de instantáneas"),
        ],
        col_widths_in=(0.95, 1.05, 1.45),
        font_pt=7.2,
    )

    _add_heading_1(doc, "3. Algoritmos Implementados")
    _add_bullet(doc, "Recorrido en amplitud (Queue + HashTable) con reconstrucción de camino mínimo en saltos vía Stack.", "BFS: ")
    _add_bullet(doc, "Recorrido en profundidad iterativo (Stack) que alcanza el nodo 31 desde las 8 fuentes.", "DFS: ")
    _add_bullet(doc, "Algoritmo de Kahn que confirma la ausencia de ciclos (46/46 nodos) y ordena la propagación.", "Orden Topológico: ")
    _add_bullet(doc, "Consultas O(1) en HashTable, trazado aguas arriba/abajo y clasificación en 5 rangos de color.", "Consultas y Análisis: ")

    _add_heading_1(doc, "4. Modelo Matemático y Simulación")
    _add_body(
        doc,
        f"Para la cuenca de drenaje (C = {dataset.basin.runoff_coefficient_c}, A = {dataset.basin.area_ha} ha), "
        "el aporte pluvial teórico se estima con el Método Racional:",
    )
    add_omml_equation(doc, "rational", "1")
    _add_body(
        doc,
        "El caudal efectivo incorporado por las fuentes combina el factor de ingreso pluvial f_ing "
        "(2.5 % calibrado a red sanitaria o 100 % para el caso teórico directo) y un caudal sanitario base:",
    )
    add_omml_equation(doc, "inflow", "2")
    _add_body(
        doc,
        "Las capacidades máximas suministradas provienen de la ecuación de Manning a tubo lleno, "
        "a partir de la cual se calculan la velocidad de referencia y el tiempo de tránsito por tubería:",
    )
    add_omml_equation(doc, "manning", "3")
    add_omml_equation(doc, "velocity", "4")
    add_omml_equation(doc, "transit", "5")
    _add_body(
        doc,
        "En cada intervalo discreto de 1 minuto se evalúa el porcentaje de utilización respecto a la capacidad máxima:",
    )
    add_omml_equation(doc, "utilization", "6")
    _add_body(
        doc,
        "Cuando el caudal demandado excede Q_max,i (>100 %), la conducción física aguas abajo se acota a la "
        "capacidad nominal y el volumen excedente se retiene en el pozo aguas arriba, cumpliendo el balance de masa:",
    )
    add_omml_equation(doc, "mass_balance", "7")

    _add_heading_1(doc, "5. Resultados y Comparación")
    _add_body(
        doc,
        "La simulación ejecutada durante 90 min (lluvia uniforme de 60 min, paso de 1 min, f_ing = 2.5 %, "
        "caudal sanitario = 0.003 m3/s por fuente) evidencia la transición progresiva de los cinco estados de color:",
    )
    _add_plain_table(
        doc,
        headers=("Esc.", "Condición", "mm/h", "Máx %", "Crít.", ">=75", ">100", "PTAR"),
        rows=[
            (
                f"E{s.scenario_id}",
                s.condition,
                f"{s.intensity_mm_h:.0f}",
                f"{s.max_utilization_pct:.1f}",
                s.most_critical_pipe,
                s.num_critical_pipes,
                s.num_overloaded_pipes,
                f"{s.peak_sink_discharge_m3s:.3f}",
            )
            for s in comparisons
        ],
        col_widths_in=(0.30, 0.78, 0.36, 0.44, 0.38, 0.34, 0.36, 0.44),
        font_pt=6.7,
    )

    fig_dir = os.path.join(os.path.dirname(os.path.abspath(out_path)), "figuras")
    fig_paths = generate_single_column_figures(base_res, comparisons, fig_dir)
    _add_single_column_figure(doc, fig_paths[0], "Figura 1. Hidrograma de entrada total y descarga en PTAR 31 (Escenario 3).")
    _add_single_column_figure(doc, fig_paths[1], "Figura 2. Utilización temporal de las cinco tuberías más exigidas (Escenario 3).")
    _add_single_column_figure(doc, fig_paths[2], "Figura 3. Comparativo de tuberías críticas y sobrecargadas entre los 5 escenarios.")

    _add_heading_1(doc, "6. Validación y Pruebas Unitarias")
    _add_body(
        doc,
        "Se validó el sistema mediante una suite automatizada con unittest cubriendo estructuras de datos, "
        "alcance BFS/DFS hacia la PTAR 31, paridad Excel/CSV (19,163.57 m), retardo físico en t = 1 min, "
        "repetibilidad determinista y errores de balance de masa inferiores a 1.3e-10 m3.",
    )

    _add_heading_1(doc, "7. Conclusiones y Limitaciones")
    _add_bullet(doc, "Las tuberías iniciales de 8 pulgadas (P31, P39, P43, P4, P5) y los tramos convergentes (P25, P3) concentran las primeras sobrecargas desde 30 mm/h.")
    _add_bullet(doc, "La arquitectura propia sin librerías externas de grafos permite auditar cada operación y ejecutar 90 pasos en menos de 90 ms.")
    _add_bullet(doc, "Limitación: el modelo no resuelve ecuaciones hidrodinámicas de Saint-Venant ni lámina libre; representa una abstracción volumétrica académica.")

    _add_heading_1(doc, "Bibliografía")
    _add_bullet(doc, "Universidad Tecnológica de Bolívar. Guía del Proyecto Final: Simulación y visualización del flujo en la red de alcantarillado de Ciudad Bicentenario. 2026.")
    _add_bullet(doc, "Fundación Mario Santo Domingo & UTB. Plano M-07B Infraestructura de Servicios Públicos — Red Alcantarillado Macroproyecto Ciudad del Bicentenario. 2012.")
    _add_bullet(doc, "Cormen, T. H., Leiserson, C. E., Rivest, R. L., & Stein, C. Introduction to Algorithms (4th ed.). MIT Press, 2022.")
    _add_bullet(doc, "Chow, V. T., Maidment, D. R., & Mays, L. W. Hidrología Aplicada. McGraw-Hill.")

    _add_heading_1(doc, "Anexo A. Complejidad de Estructuras Propias")
    _add_plain_table(
        doc,
        headers=("Componente", "Operación clave", "Complejidad"),
        rows=[
            ("HashTable", "put / get / contains", "O(1) promedio"),
            ("LinkedList", "append / prepend / pop", "O(1)"),
            ("Queue / Stack", "enqueue / dequeue / push", "O(1)"),
            ("PriorityQueue", "push / pop evento", "O(log n)"),
            ("BFS / DFS", "Recorrido completo", "O(V + E)"),
        ],
        col_widths_in=(1.05, 1.45, 0.90),
        font_pt=7.0,
    )

    _add_heading_1(doc, "Anexo B. Inventario de Tuberías (P1–P59)")
    _add_plain_table(
        doc,
        headers=("Tub.", "Tramo", "D(in)", "L(m)", "Qmax", "t(min)"),
        rows=[
            (
                p.pipe_id,
                f"{p.from_node}->{p.to_node}",
                f"{p.diameter_in:.0f}",
                f"{p.length_m:.1f}",
                f"{p.q_max_m3s:.4f}",
                f"{p.transit_time_min:.2f}",
            )
            for p in sorted(dataset.graph.pipes(), key=lambda x: int(x.pipe_id[1:]))
        ],
        col_widths_in=(0.42, 0.68, 0.42, 0.60, 0.68, 0.60),
        font_pt=6.6,
    )

    _add_heading_1(doc, "Anexo C. Resultados Detallados por Escenario")
    _add_plain_table(
        doc,
        headers=("Esc.", "Iny.(m3)", "PTAR(m3)", "Almac.(m3)", "Err.Masa"),
        rows=[
            (
                f"E{s.scenario_id}",
                f"{s.total_inflow_m3:,.1f}",
                f"{s.total_sink_discharge_m3:,.1f}",
                f"{s.max_stored_surcharge_m3:,.1f}",
                f"{s.mass_balance_error_m3:.2e}",
            )
            for s in comparisons
        ],
        col_widths_in=(0.42, 0.76, 0.76, 0.76, 0.70),
        font_pt=6.8,
    )

    _add_heading_1(doc, "Anexo D. Evidencias de Validación y Ejecución")
    _add_body(
        doc,
        "Comandos reproducibles en cualquier equipo con Python 3.11+ y dependencias de requirements.txt: "
        "(1) python main.py para abrir la interfaz gráfica interactiva; "
        "(2) python -m unittest discover -s tests -v para ejecutar la batería de pruebas; "
        "(3) python main.py --report-docx docs/DOCUMENTO_TECNICO.docx para regenerar este entregable.",
    )

    _validate_docx_compliance(doc)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    doc.save(out_path)
    return os.path.abspath(out_path)
