"""Generación de reportes RF12 en Markdown, CSV y Word (.docx) limpio de 1 columna."""

import csv
from datetime import datetime
import os
from typing import List, Optional

from src.algorithms.analysis import rank_critical_pipes
from src.io.data_loader import NetworkDataset
from .comparison import ScenarioSummary
from .models import SimulationResult

MODEL_ASSUMPTIONS_TEXT = (
    "Supuestos del Modelo Computacional (Sección 11):\n"
    "1. Escorrentía (Método Racional): Q = 0.00278 · C · I · A al 100 % durante la tormenta.\n"
    "2. Reparto en fuentes: ponderado por capacidad saliente de cada alcantarilla (o uniforme 1/N).\n"
    "3. Capacidad máxima: Qmax se toma directamente del dataset suministrado (Manning).\n"
    "4. Tiempo de tránsito: V_i = Qmax / (π·D²/4), t_i = L_i / V_i, gestionado con PriorityQueue.\n"
    "5. Bifurcaciones: reparto proporcional a Qmax saliente (o equitativo 1/k).\n"
    "6. Utilización y sobrecarga: O_i(t) = (Q_demanda / Qmax) × 100 sin tope artificial; "
    "el exceso se almacena temporalmente en el pozo y el excedente se registra como rebose "
    "superficial conservando la masa exacta."
)


def _split_rule_label(rule: str) -> str:
    return "Proporcional a Qmax" if rule == "proportional" else "Equitativa (1/k)"


def _source_dist_label(dist: str) -> str:
    return "Ponderada por capacidad" if dist == "capacity" else "Uniforme (1/N)"


def generate_markdown_report(
    dataset: NetworkDataset,
    result: SimulationResult,
    comparisons: Optional[List[ScenarioSummary]],
    out_path: str,
) -> str:
    """Genera un reporte completo en Markdown y exporta el detalle tabular en CSV."""
    n_nodes, n_pipes, n_src, n_sink, total_len = dataset.graph.summary()
    cfg = result.config
    ranked = rank_critical_pipes(
        dataset.graph, result.peak_pipe_flow, result.peak_pipe_utilization, min_utilization_pct=0.0
    )
    last_snap = result.snapshots[-1] if result.snapshots else None

    lines = [
        "# Reporte de Simulación — Alcantarillado Ciudad Bicentenario",
        "",
        f"- **Fecha de generación:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- **Fuente de datos:** `{os.path.basename(dataset.source_path)}`",
        f"- **Red:** {n_nodes} nodos ({n_src} fuentes, {n_sink} sumidero PTAR Punta Canoa 31), "
        f"{n_pipes} tuberías, longitud total {total_len:,.2f} m.",
        f"- **Cuenca de drenaje:** C = {dataset.basin.runoff_coefficient_c:.2f}, A = {dataset.basin.area_ha:.1f} ha.",
        "",
        "## 1. Escenario y Parámetros de Simulación",
        f"- **Escenario:** {cfg.scenario_id} — {cfg.scenario_name} ({cfg.intensity_mm_h:.1f} mm/h)",
        f"- **Duración total:** {cfg.duration_min:.1f} min | **Lluvia:** {cfg.storm_duration_min:.1f} min | "
        f"**Δt:** {cfg.dt_min:.2f} min",
        f"- **Distribución en bifurcaciones:** {_split_rule_label(cfg.split_rule)}",
        f"- **Distribución entre fuentes:** {_source_dist_label(cfg.source_distribution)}",
        f"- **Almacenamiento amortiguador por pozo:** {cfg.max_manhole_storage_m3:.2f} m³",
        "",
        "## 2. Supuestos del Modelo",
        "- **Método Racional:** Q = 0.00278 · C · I · A (100 %, sin caudal sanitario artificial).",
        "- **Capacidad máxima (Manning):** Qmax leída directamente del archivo docente.",
        "- **Tránsito con retardo:** V = Qmax / A, t_i = L_i / V_i gestionado con PriorityQueue propia.",
        "- **Utilización:** O_i(t) = (Q_demanda / Qmax) × 100 sin tope artificial.",
        "- **Sobrecarga conservativa:** el caudal conducido se limita a Qmax y el exceso se "
        "acumula en el pozo y rebose superficial sin pérdida de masa.",
        "",
        "## 3. Resultados Globales hasta PTAR Punta Canoa (Nodo 31)",
        f"- **Volumen total inyectado:** {result.total_inflow_m3:,.3f} m³",
        f"- **Volumen descargado en PTAR 31:** {result.total_sink_discharge_m3:,.3f} m³",
        f"- **Caudal pico en PTAR 31:** {result.peak_sink_discharge_m3s:.4f} m³/s",
        f"- **Volumen remanente (pozos + tránsito):** {result.final_residual_m3:,.3f} m³",
        f"- **Rebose superficial acumulado:** {result.total_surface_flooding_m3:,.3f} m³",
        f"- **Error máximo de conservación de masa:** {result.max_mass_balance_error_m3:.3e} m³",
        f"- **Tuberías cercanas a capacidad (>75–100 %):** {len(result.ever_near_capacity_pipes)} "
        f"({', '.join(result.ever_near_capacity_pipes) or 'Ninguna'})",
        f"- **Tuberías sobrecargadas (>100 %):** {len(result.ever_overloaded_pipes)} "
        f"({', '.join(result.ever_overloaded_pipes) or 'Ninguna'})",
        f"- **Tiempo de cómputo:** {result.execution_time_ms:.2f} ms",
        "",
        "## 4. Ranking de Tuberías Críticas (Top 25)",
        "| # | Tubería | Tramo | Q_cond (m³/s) | Q_max (m³/s) | Util. Pico (%) | Estado | Exceso (m³/s) |",
        "|---:|:---:|:---:|---:|---:|---:|:---|---:|",
    ]
    for rec in ranked[:25]:
        lines.append(
            f"| {rec.rank} | {rec.pipe_id} | {rec.from_node} -> {rec.to_node} | "
            f"{rec.flow_m3s:.5f} | {rec.q_max_m3s:.5f} | {rec.utilization_pct:.2f}% | "
            f"{rec.category.label} | {rec.excess_flow_m3s:.5f} |"
        )

    if comparisons:
        lines.extend([
            "",
            "## 5. Comparación entre Escenarios de Precipitación",
            "| Esc. | Condición | I (mm/h) | Util. Máx (%) | Tubería Crítica | >75–100% | >100% | Pico PTAR (m³/s) | Rebose (m³) | Error Masa (m³) |",
            "|:---:|:---|---:|---:|:---:|---:|---:|---:|---:|---:|",
        ])
        for sc in comparisons:
            lines.append(
                f"| {sc.scenario_id} | {sc.condition} | {sc.intensity_mm_h:.1f} | "
                f"{sc.max_utilization_pct:.2f}% | {sc.most_critical_pipe} | "
                f"{sc.num_near_capacity_pipes} | {sc.num_overloaded_pipes} | "
                f"{sc.peak_sink_discharge_m3s:.4f} | {sc.total_surface_flooding_m3:,.2f} | "
                f"{sc.mass_balance_error_m3:.2e} |"
            )

    abs_out = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(abs_out), exist_ok=True)
    with open(abs_out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    csv_path = os.path.splitext(abs_out)[0] + "_tuberias.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "rank", "pipe_id", "from_node", "to_node", "peak_flow_m3s", "q_max_m3s",
            "peak_utilization_pct", "state", "excess_flow_m3s", "final_utilization_pct",
        ])
        for rec in ranked:
            final_u = (
                last_snap.pipe_states[rec.pipe_id].utilization_pct
                if (last_snap is not None and rec.pipe_id in last_snap.pipe_states)
                else 0.0
            )
            w.writerow([
                rec.rank, rec.pipe_id, rec.from_node, rec.to_node,
                round(rec.flow_m3s, 6), round(rec.q_max_m3s, 6),
                round(rec.utilization_pct, 2), rec.category.label,
                round(rec.excess_flow_m3s, 6), round(final_u, 2),
            ])
    return abs_out


def _add_docx_table(doc, headers: List[str], rows: List[List[str]]) -> None:
    table = doc.add_table(rows=1 + len(rows), cols=len(headers))
    table.style = "Table Grid"
    for c_idx, title in enumerate(headers):
        cell = table.rows[0].cells[c_idx]
        cell.text = title
        for p in cell.paragraphs:
            for r in p.runs:
                r.bold = True
    for r_idx, row in enumerate(rows, start=1):
        for c_idx, val in enumerate(row):
            table.rows[r_idx].cells[c_idx].text = str(val)


def generate_docx_report(
    dataset: NetworkDataset,
    result: SimulationResult,
    comparisons: Optional[List[ScenarioSummary]],
    out_path: str,
) -> str:
    """Genera un reporte Word (.docx) limpio de una columna con resultados y escenarios."""
    from docx import Document

    doc = Document()
    n_nodes, n_pipes, n_src, n_sink, total_len = dataset.graph.summary()
    cfg = result.config
    ranked = rank_critical_pipes(
        dataset.graph, result.peak_pipe_flow, result.peak_pipe_utilization, min_utilization_pct=0.0
    )

    doc.add_heading("Reporte de Simulación — Red de Alcantarillado Ciudad Bicentenario", level=0)
    doc.add_paragraph(
        f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | "
        f"Dataset: {os.path.basename(dataset.source_path)} | "
        f"Red: {n_nodes} nodos ({n_src} fuentes, {n_sink} sumidero PTAR 31), "
        f"{n_pipes} tuberías ({total_len:,.2f} m)."
    )

    doc.add_heading("1. Escenario y Parámetros", level=1)
    _add_docx_table(doc, ["Parámetro", "Valor"], [
        ["Escenario", f"{cfg.scenario_id} — {cfg.scenario_name} ({cfg.intensity_mm_h:.1f} mm/h)"],
        ["Cuenca de drenaje", f"C = {dataset.basin.runoff_coefficient_c:.2f}, A = {dataset.basin.area_ha:.1f} ha"],
        ["Configuración temporal", f"Duración {cfg.duration_min:.0f} min, Lluvia {cfg.storm_duration_min:.0f} min, Δt = {cfg.dt_min:.2f} min"],
        ["Regla de bifurcación", _split_rule_label(cfg.split_rule)],
        ["Distribución de fuentes", _source_dist_label(cfg.source_distribution)],
        ["Almacenamiento por pozo", f"{cfg.max_manhole_storage_m3:.2f} m³"],
    ])

    doc.add_heading("2. Resultados Globales hasta PTAR Punta Canoa (Nodo 31)", level=1)
    _add_docx_table(doc, ["Indicador", "Resultado"], [
        ["Volumen total inyectado", f"{result.total_inflow_m3:,.2f} m³"],
        ["Volumen descargado en PTAR 31", f"{result.total_sink_discharge_m3:,.2f} m³"],
        ["Caudal pico en PTAR 31", f"{result.peak_sink_discharge_m3s:.4f} m³/s"],
        ["Volumen remanente (pozos + tránsito)", f"{result.final_residual_m3:,.2f} m³"],
        ["Rebose superficial acumulado", f"{result.total_surface_flooding_m3:,.2f} m³"],
        ["Error máximo de conservación de masa", f"{result.max_mass_balance_error_m3:.3e} m³"],
        ["Tuberías cercanas a capacidad (>75–100 %)", str(len(result.ever_near_capacity_pipes))],
        ["Tuberías sobrecargadas (>100 %)", str(len(result.ever_overloaded_pipes))],
    ])

    doc.add_heading("3. Top 20 Tuberías Críticas", level=1)
    _add_docx_table(
        doc,
        ["#", "Tubería", "Tramo", "Q_cond (m³/s)", "Q_max (m³/s)", "Util. Pico", "Estado"],
        [
            [
                str(r.rank), r.pipe_id, f"{r.from_node} -> {r.to_node}",
                f"{r.flow_m3s:.4f}", f"{r.q_max_m3s:.4f}", f"{r.utilization_pct:.1f}%", r.category.label,
            ]
            for r in ranked[:20]
        ],
    )

    if comparisons:
        doc.add_heading("4. Comparación de Escenarios de Precipitación", level=1)
        _add_docx_table(
            doc,
            ["Esc.", "Condición", "I (mm/h)", "Util. Máx", "Crítica", ">75–100%", ">100%", "Pico PTAR", "Rebose (m³)"],
            [
                [
                    str(sc.scenario_id), sc.condition, f"{sc.intensity_mm_h:.0f}",
                    f"{sc.max_utilization_pct:.1f}%", sc.most_critical_pipe,
                    str(sc.num_near_capacity_pipes), str(sc.num_overloaded_pipes),
                    f"{sc.peak_sink_discharge_m3s:.4f}", f"{sc.total_surface_flooding_m3:,.1f}",
                ]
                for sc in comparisons
            ],
        )

    doc.add_heading("5. Supuestos del Modelo Computacional", level=1)
    for line in MODEL_ASSUMPTIONS_TEXT.splitlines()[1:]:
        doc.add_paragraph(line)

    abs_out = os.path.abspath(out_path)
    os.makedirs(os.path.dirname(abs_out), exist_ok=True)
    doc.save(abs_out)
    return abs_out
