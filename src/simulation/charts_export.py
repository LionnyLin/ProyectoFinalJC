"""Script de generación de figuras Matplotlib dimensionadas a una columna (3.5 × 2.8 in)."""

import os
from typing import List
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from src.io.data_loader import load_dataset
from src.simulation.comparison import ScenarioSummary, compare_all_scenarios
from src.simulation.models import SimulationConfig, SimulationResult, compute_symlog_ticks

SINGLE_COL_FIGSIZE = (3.5, 2.8)
DPI = 300


def _apply_publication_rc() -> None:
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 7.0,
        "axes.titlesize": 7.8,
        "axes.titleweight": "bold",
        "axes.labelsize": 7.0,
        "xtick.labelsize": 6.6,
        "ytick.labelsize": 6.6,
        "legend.fontsize": 6.0,
        "axes.edgecolor": "#475569",
        "axes.linewidth": 0.7,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
    })


def generate_single_column_figures(
    result: SimulationResult,
    comparisons: List[ScenarioSummary],
    out_dir: str,
) -> List[str]:
    """Genera 3 figuras PNG en español a 3.5 × 2.8 in (300 DPI) para columnas Word."""
    _apply_publication_rc()
    os.makedirs(out_dir, exist_ok=True)
    paths: List[str] = []

    ts = [s.time_min for s in result.snapshots]
    q_in = [s.total_source_inflow_m3s for s in result.snapshots]
    q_ptar = [s.total_sink_discharge_m3s for s in result.snapshots]
    q_flood = [0.0]
    for idx in range(1, len(result.snapshots)):
        dt_s = max((ts[idx] - ts[idx - 1]) * 60.0, 1e-6)
        dv = max(
            0.0,
            result.snapshots[idx].total_surface_flooding_m3
            - result.snapshots[idx - 1].total_surface_flooding_m3,
        )
        q_flood.append(dv / dt_s)

    # Figura 1: Dos subpaneles apilados (Entrada/Rebose arriba; PTAR 31 abajo con su escala)
    fig1, (ax1_top, ax1_bot) = plt.subplots(
        2,
        1,
        figsize=SINGLE_COL_FIGSIZE,
        dpi=DPI,
        sharex=True,
        gridspec_kw={"height_ratios": [1.0, 0.95]},
        constrained_layout=True,
    )
    ax1_top.plot(ts, q_in, label="Entrada (fuentes)", color="#3B153A", linewidth=1.6)
    if any(v > 1e-6 for v in q_flood):
        ax1_top.plot(
            ts, q_flood, label="Rebose superf.", color="#dc2626", linestyle="--", linewidth=1.35
        )
    max_top = max(q_in + q_flood, default=1.0)
    ax1_top.set_ylim(0.0, max(0.05, max_top * 1.32))
    ax1_top.set_ylabel("Entrada (m³/s)")
    ax1_top.set_title(
        f"Hidrograma Escenario {result.config.scenario_id} ({result.config.intensity_mm_h:.0f} mm/h)"
    )
    ax1_top.grid(True)
    ax1_top.legend(loc="upper right", frameon=True)

    ax1_bot.plot(ts, q_ptar, label="Descarga PTAR (nodo 31)", color="#0F766E", linewidth=1.7)
    ax1_bot.fill_between(ts, q_ptar, color="#0F766E", alpha=0.14)
    pk_ptar = max(q_ptar, default=0.0)
    if pk_ptar > 1e-6:
        idx_pk = q_ptar.index(pk_ptar)
        ax1_bot.annotate(
            f"Pico: {pk_ptar:.2f} m³/s",
            xy=(ts[idx_pk], pk_ptar),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=6.0,
            fontweight="bold",
            color="#0F766E",
        )
    ax1_bot.set_ylim(0.0, max(0.05, pk_ptar * 1.36))
    ax1_bot.set_xlabel("Tiempo (min)")
    ax1_bot.set_ylabel("PTAR 31 (m³/s)")
    ax1_bot.grid(True)
    ax1_bot.legend(loc="upper left", frameon=True)

    p1 = os.path.join(out_dir, "fig1_hidrograma_ptar.png")
    fig1.savefig(p1, dpi=DPI)
    plt.close(fig1)
    paths.append(p1)

    # Figura 2: Top 5 tuberías con escala symlog legible y trazos diferenciados
    fig2, ax2 = plt.subplots(figsize=SINGLE_COL_FIGSIZE, dpi=DPI, constrained_layout=True)
    top5 = sorted(
        result.peak_pipe_utilization.items(),
        key=lambda kv: (kv[1], result.peak_pipe_demand_ratio.get(kv[0], 0.0)),
        reverse=True,
    )[:5]
    palette = ["#991b1b", "#dc2626", "#ea580c", "#ca8a04", "#0284c7"]
    styles = ["-", "--", "-.", ":", "-"]
    widths = [1.8, 1.5, 1.35, 1.35, 1.25]
    for idx, (pid, pk) in enumerate(top5):
        utils = [s.pipe_states[pid].utilization_pct for s in result.snapshots]
        lbl = f"{pid} ({pk:,.0f}%)"
        ax2.plot(
            ts,
            utils,
            label=lbl,
            color=palette[idx % len(palette)],
            linestyle=styles[idx % len(styles)],
            linewidth=widths[idx % len(widths)],
        )
    max_u = max((pk for _, pk in top5), default=100.0)
    ax2.axhspan(0.0, 75.0, color="#22c55e", alpha=0.06, zorder=0)
    ax2.axhspan(75.0, 100.0, color="#f97316", alpha=0.09, zorder=0)
    ax2.axhline(100.0, color="#991b1b", linestyle="--", linewidth=1.2, label="Cap. 100%")
    if max_u > 250.0:
        ax2.set_yscale("symlog", linthresh=100.0, linscale=0.85)
        ax2.set_ylim(0.0, max_u * 3.0)
        ax2.set_yticks(compute_symlog_ticks(max_u * 1.4))
        ax2.minorticks_off()
    else:
        ax2.set_ylim(0.0, max(135.0, max_u * 1.38))
    ax2.yaxis.set_major_formatter(
        FuncFormatter(lambda v, _: f"{int(round(v)):,}%" if v >= 1 else "0%")
    )
    ax2.set_title("Utilización — Top 5 Tuberías Críticas")
    ax2.set_xlabel("Tiempo (min)")
    ax2.set_ylabel("Utilización (% Cap.)")
    ax2.grid(True)
    ax2.legend(loc="upper right", ncol=2, frameon=True, columnspacing=0.6)
    p2 = os.path.join(out_dir, "fig2_top5_utilizacion.png")
    fig2.savefig(p2, dpi=DPI)
    plt.close(fig2)
    paths.append(p2)

    # Figura 3: Comparación multiescenario (Conteo tuberías arriba + Rebose m³ abajo)
    fig3, (ax3_top, ax3_bot) = plt.subplots(
        2,
        1,
        figsize=SINGLE_COL_FIGSIZE,
        dpi=DPI,
        sharex=True,
        gridspec_kw={"height_ratios": [1.05, 0.95]},
        constrained_layout=True,
    )
    labels = [f"E{s.scenario_id}\n{s.intensity_mm_h:.0f}mm" for s in comparisons]
    crit = [s.num_near_capacity_pipes for s in comparisons]
    over = [s.num_overloaded_pipes for s in comparisons]
    floods_k = [s.total_surface_flooding_m3 / 1000.0 for s in comparisons]
    x = list(range(len(labels)))
    w = 0.36
    b1 = ax3_top.bar([i - w / 2 for i in x], crit, width=w, label="Críticas (>75–100%)", color="#ef4444")
    b2 = ax3_top.bar([i + w / 2 for i in x], over, width=w, label="Sobrec. (>100%)", color="#991b1b")
    max_b = max(crit + over, default=10)
    for rect in list(b1) + list(b2):
        val = int(round(rect.get_height()))
        ax3_top.text(
            rect.get_x() + rect.get_width() / 2.0,
            rect.get_height() + max_b * 0.03,
            f"{val}",
            ha="center",
            va="bottom",
            fontsize=5.8,
            fontweight="bold" if val > 0 else "normal",
        )
    ax3_top.set_ylim(0.0, max(5.0, max_b * 1.48))
    ax3_top.set_title("Comparación de Escenarios de Precipitación")
    ax3_top.set_ylabel("Tuberías")
    ax3_top.grid(True, axis="y")
    ax3_top.legend(loc="upper left", ncol=2, frameon=True)

    b3 = ax3_bot.bar(x, floods_k, width=0.52, color=["#94A3B8", "#38BDF8", "#FACC15", "#FB923C", "#DC2626"][: len(x)])
    max_fk = max(floods_k, default=10.0)
    for rect, fk in zip(b3, floods_k):
        lbl_f = f"{fk:.1f}k" if fk >= 1.0 else f"{fk * 1000.0:.0f}"
        ax3_bot.text(
            rect.get_x() + rect.get_width() / 2.0,
            rect.get_height() + max(0.5, max_fk * 0.03),
            lbl_f,
            ha="center",
            va="bottom",
            fontsize=5.8,
            fontweight="bold",
        )
    ax3_bot.set_ylim(0.0, max(10.0, max_fk * 1.30))
    ax3_bot.set_xticks(x)
    ax3_bot.set_xticklabels(labels)
    ax3_bot.set_ylabel("Rebose (×10³ m³)")
    ax3_bot.grid(True, axis="y")

    p3 = os.path.join(out_dir, "fig3_comparacion_escenarios.png")
    fig3.savefig(p3, dpi=DPI)
    plt.close(fig3)
    paths.append(p3)

    return paths


if __name__ == "__main__":
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    ds = load_dataset(os.path.join(base_dir, "data", "DataSetBicentenario.xlsx"))
    base_cfg = SimulationConfig(scenario_id=3, scenario_name="Moderate rain", intensity_mm_h=30.0)
    comps = compare_all_scenarios(ds, base_cfg)
    out = os.path.join(base_dir, "docs", "figuras")
    primary = comps[2] if len(comps) > 2 else comps[0]
    generated = generate_single_column_figures(primary.result, comps, out)
    for g in generated:
        print("Figura 3.5x2.8 in generada:", g)
