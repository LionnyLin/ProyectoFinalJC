"""Generador de reportes técnicos (Markdown y CSV) para escenarios y tuberías críticas."""

import csv
from datetime import datetime
import os
from typing import List, Optional

from src.algorithms.analysis import classify_utilization, rank_critical_pipes
from src.io.data_loader import NetworkDataset
from .comparison import ScenarioSummary
from .models import SimulationResult


def generate_markdown_report(
    dataset: NetworkDataset,
    current_result: SimulationResult,
    comparisons: Optional[List[ScenarioSummary]] = None,
    out_path: str = "reporte_simulacion.md",
) -> str:
    """Genera un reporte detallado en Markdown y retorna la ruta escrita."""
    cfg = current_result.config
    n_nodes, n_pipes, n_src, n_snk, total_len = dataset.graph.summary()
    last_snap = current_result.snapshots[-1]
    ranked = rank_critical_pipes(
        dataset.graph,
        current_result.peak_pipe_flow,
        current_result.peak_pipe_utilization,
        pipe_demand_ratios_pct=current_result.peak_pipe_demand_ratio,
        pipe_excess_flows_m3s={
            pid: max(0.0, current_result.peak_pipe_demand_flow.get(pid, 0.0) - p.q_max_m3s)
            for p in dataset.graph.pipes()
            for pid in [p.pipe_id]
        },
    )

    lines: List[str] = [
        "# Reporte de Simulación — Red de Alcantarillado Ciudad Bicentenario",
        "",
        f"**Fecha de generación:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ",
        f"**Fuente de datos:** `{dataset.source_path}`  ",
        f"**Descarga final (Sumidero):** {', '.join(dataset.graph.sink_ids())} (PTAR Punta Canoa)  ",
        "",
        "## 1. Resumen de la Red",
        f"- **Vértices (Alcantarillas / Pozos):** {n_nodes} ({n_src} fuentes, {n_snk} sumidero)",
        f"- **Aristas dirigidas (Tuberías):** {n_pipes}",
        f"- **Longitud total de la red:** {total_len:,.2f} m ({total_len / 1000.0:.2f} km)",
        f"- **Cuenca de drenaje:** C = {dataset.basin.runoff_coefficient_c}, A = {dataset.basin.area_ha} ha",
        "",
        "## 2. Supuestos y Parámetros del Escenario Evaluado",
        f"- **Escenario:** {cfg.scenario_id} — {cfg.scenario_name} ({cfg.intensity_mm_h:.1f} mm/h)",
        f"- **Método Racional:** $Q = 0.00278 \\cdot C \\cdot I \\cdot A$ con factor de ingreso pluvial = {cfg.ingress_factor * 100:.1f}%",
        f"- **Caudal sanitario base (tiempo seco):** {cfg.dry_weather_flow_per_source_m3s:.4f} m³/s por fuente",
        f"- **Duración de simulación / lluvia:** {cfg.duration_min:.1f} min / {cfg.storm_duration_min:.1f} min ($\\Delta t$ = {cfg.dt_min:.2f} min)",
        f"- **Perfil temporal (hietograma):** {cfg.hyetograph}",
        f"- **Reparto entre fuentes:** {cfg.source_distribution} (por capacidad instalada o uniforme 1/8)",
        f"- **Regla de distribución en bifurcaciones:** {cfg.split_rule}",
        "- **Tiempo de tránsito:** $t_i = L_i / V_i$, con $V_i = Q_{max,i} / A_i$ (velocidad a tubo lleno de Manning)",
        f"- **Utilización física vs. demanda:** Conducción física acotada a $\\le {cfg.max_physical_utilization_pct:.0f}\\%$ bajo sobrepresión; el exceso de demanda se reporta por separado como índice ($\\times Q_{{max}}$) y déficit.",
        f"- **Pozos finitos y rebose:** Capacidad máxima de pozo = {cfg.max_manhole_storage_m3:.1f} m³ antes de derivar excedente a rebose superficial en vía con conservación exacta de masa.",
        "",
        "## 3. Resultados Globales y Conservación de Masa",
        f"- **Volumen total inyectado:** {current_result.total_inflow_m3:,.3f} m³",
        f"- **Volumen descargado en PTAR Punta Canoa (Nodo 31):** {current_result.total_sink_discharge_m3:,.3f} m³",
        f"- **Caudal pico en PTAR Punta Canoa:** {current_result.peak_sink_discharge_m3s:.4f} m³/s",
        f"- **Volumen remanente (en pozos + tránsito al cierre):** {current_result.final_residual_m3:,.3f} m³",
        f"- **Rebose superficial acumulado en vía:** {current_result.total_surface_flooding_m3:,.3f} m³",
        f"- **Error máximo de balance de masa:** {current_result.max_mass_balance_error_m3:.3e} m³",
        f"- **Tuberías críticas (>= 75 %):** {len(current_result.ever_critical_pipes)} ({', '.join(current_result.ever_critical_pipes) or 'Ninguna'})",
        f"- **Tuberías sobrecargadas (> 100 %):** {len(current_result.ever_overloaded_pipes)} ({', '.join(current_result.ever_overloaded_pipes) or 'Ninguna'})",
        f"- **Tiempo de cómputo:** {current_result.execution_time_ms:.2f} ms",
        "",
        "## 4. Ranking de Tuberías por Utilización Física Pico",
        "| # | Tubería | Tramo | Q_físico (m³/s) | Q_max (m³/s) | Util. Fís (%) | Demanda | Estado | Déficit (m³/s) |",
        "|---:|:---:|:---:|---:|---:|---:|---:|:---|---:|",
    ]

    for rec in ranked[:25]:
        lines.append(
            f"| {rec.rank} | {rec.pipe_id} | {rec.from_node} -> {rec.to_node} | "
            f"{rec.flow_m3s:.5f} | {rec.q_max_m3s:.5f} | {rec.utilization_pct:.2f}% | "
            f"{rec.demand_ratio_pct / 100.0:.2f}x | {rec.category.label} | {rec.excess_flow_m3s:.5f} |"
        )

    if comparisons:
        lines.extend([
            "",
            "## 5. Comparación entre Escenarios de Precipitación",
            "| Escenario | Condición | Intensidad (mm/h) | Util. Fís. Máx (%) | Demanda Máx | Tubería Crítica | Críticas (>=75%) | Sobrecargadas (>100%) | Pico PTAR (m³/s) | Rebose (m³) | Error Masa (m³) |",
            "|:---:|:---|---:|---:|---:|:---:|---:|---:|---:|---:|---:|",
        ])
        for sc in comparisons:
            lines.append(
                f"| {sc.scenario_id} | {sc.condition} | {sc.intensity_mm_h:.1f} | "
                f"{sc.max_utilization_pct:.2f}% | {sc.max_demand_ratio_pct / 100.0:.2f}x | {sc.most_critical_pipe} | "
                f"{sc.num_critical_pipes} | {sc.num_overloaded_pipes} | "
                f"{sc.peak_sink_discharge_m3s:.4f} | {sc.total_surface_flooding_m3:,.2f} | {sc.mass_balance_error_m3:.2e} |"
            )

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # También exportar CSV de detalle por tubería junto al reporte
    csv_path = os.path.splitext(out_path)[0] + "_tuberias.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "rank", "pipe_id", "from_node", "to_node",
            "peak_flow_m3s", "q_max_m3s", "peak_utilization_pct",
            "peak_demand_factor", "state", "excess_flow_m3s", "final_utilization_pct",
        ])
        for rec in ranked:
            final_u = last_snap.pipe_states[rec.pipe_id].utilization_pct
            w.writerow([
                rec.rank,
                rec.pipe_id,
                rec.from_node,
                rec.to_node,
                round(rec.flow_m3s, 6),
                round(rec.q_max_m3s, 6),
                round(rec.utilization_pct, 2),
                round(rec.demand_ratio_pct / 100.0, 3),
                classify_utilization(rec.utilization_pct).label,
                round(rec.excess_flow_m3s, 6),
                round(final_u, 2),
            ])

    return os.path.abspath(out_path)
