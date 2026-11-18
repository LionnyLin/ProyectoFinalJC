"""Paneles de gráficas Matplotlib embebidos en Tkinter."""

import tkinter as tk
from typing import List, Optional

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from src.simulation.comparison import ScenarioSummary
from src.simulation.models import SimulationResult
from . import theme


class TemporalChartsPanel(tk.Frame):
    """Gráfica temporal de hidrograma (entrada vs PTAR 31) y utilización por tubería."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=theme.BG_PANEL)
        self.figure = Figure(figsize=(5.5, 4.4), dpi=96, facecolor=theme.BG_PANEL)
        self.ax_flow = self.figure.add_subplot(211)
        self.ax_util = self.figure.add_subplot(212)
        self.figure.subplots_adjust(hspace=0.45, left=0.14, right=0.96, top=0.92, bottom=0.12)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._style_axes()

    def _style_axes(self) -> None:
        for ax in (self.ax_flow, self.ax_util):
            ax.set_facecolor(theme.BG_CANVAS)
            ax.tick_params(colors=theme.TEXT_SECONDARY, labelsize=8)
            for spine in ax.spines.values():
                spine.set_color(theme.BORDER_COLOR)
            ax.grid(True, linestyle="--", alpha=0.25, color="#64748b")

    def update_plots(
        self,
        result: Optional[SimulationResult],
        selected_pipe_id: Optional[str] = None,
        current_time_min: Optional[float] = None,
    ) -> None:
        self.ax_flow.clear()
        self.ax_util.clear()
        self._style_axes()

        if result is None or not result.snapshots:
            self.ax_flow.set_title("Sin simulación ejecutada", color=theme.TEXT_PRIMARY, fontsize=9)
            self.canvas.draw_idle()
            return

        times = [s.time_min for s in result.snapshots]
        inflows = [s.total_source_inflow_m3s for s in result.snapshots]
        ptar_out = [s.total_sink_discharge_m3s for s in result.snapshots]

        self.ax_flow.plot(times, inflows, label="Entrada Fuentes", color="#38bdf8", linewidth=1.8)
        self.ax_flow.plot(times, ptar_out, label="Descarga PTAR (31)", color="#10b981", linewidth=2.0)
        if current_time_min is not None:
            self.ax_flow.axvline(current_time_min, color="#fbbf24", linestyle=":", linewidth=1.4)
        self.ax_flow.set_title("Balance de Caudales (m³/s)", color=theme.TEXT_PRIMARY, fontsize=9)
        self.ax_flow.set_ylabel("m³/s", color=theme.TEXT_SECONDARY, fontsize=8)
        self.ax_flow.legend(loc="upper right", fontsize=7, facecolor=theme.BG_PANEL, labelcolor=theme.TEXT_PRIMARY)

        # Curva de utilización de tubería seleccionada o top 3 críticas
        target_pids: List[str] = []
        if selected_pipe_id and selected_pipe_id in result.peak_pipe_utilization:
            target_pids = [selected_pipe_id]
        else:
            sorted_p = sorted(
                result.peak_pipe_utilization.items(), key=lambda kv: kv[1], reverse=True
            )
            target_pids = [pid for pid, _ in sorted_p[:3]]

        palette = ["#f97316", "#ef4444", "#eab308"]
        for idx, pid in enumerate(target_pids):
            utils = [
                s.pipe_states[pid].utilization_pct if pid in s.pipe_states else 0.0
                for s in result.snapshots
            ]
            self.ax_util.plot(
                times,
                utils,
                label=f"{pid} (máx {result.peak_pipe_utilization.get(pid, 0.0):.1f}%)",
                color=palette[idx % len(palette)],
                linewidth=1.8,
            )

        self.ax_util.axhline(100.0, color="#ef4444", linestyle="--", linewidth=1.2, label="Capacidad 100%")
        if current_time_min is not None:
            self.ax_util.axvline(current_time_min, color="#fbbf24", linestyle=":", linewidth=1.4)
        title_u = (
            f"Utilización Temporal — {selected_pipe_id}"
            if selected_pipe_id
            else "Utilización Temporal — Top 3 Críticas"
        )
        self.ax_util.set_title(title_u, color=theme.TEXT_PRIMARY, fontsize=9)
        self.ax_util.set_xlabel("Tiempo (min)", color=theme.TEXT_SECONDARY, fontsize=8)
        self.ax_util.set_ylabel("% Cap.", color=theme.TEXT_SECONDARY, fontsize=8)
        self.ax_util.legend(loc="upper right", fontsize=7, facecolor=theme.BG_PANEL, labelcolor=theme.TEXT_PRIMARY)

        self.canvas.draw_idle()


class ComparisonChartsPanel(tk.Frame):
    """Gráfica comparativa de los escenarios de precipitación."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=theme.BG_PANEL)
        self.figure = Figure(figsize=(5.5, 3.6), dpi=96, facecolor=theme.BG_PANEL)
        self.ax_bar = self.figure.add_subplot(121)
        self.ax_ptar = self.figure.add_subplot(122)
        self.figure.subplots_adjust(wspace=0.35, left=0.11, right=0.97, top=0.86, bottom=0.22)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def update_comparison(self, summaries: List[ScenarioSummary]) -> None:
        for ax in (self.ax_bar, self.ax_ptar):
            ax.clear()
            ax.set_facecolor(theme.BG_CANVAS)
            ax.tick_params(colors=theme.TEXT_SECONDARY, labelsize=7.5)
            for spine in ax.spines.values():
                spine.set_color(theme.BORDER_COLOR)
            ax.grid(True, linestyle="--", alpha=0.25, color="#64748b")

        if not summaries:
            self.canvas.draw_idle()
            return

        labels = [f"E{s.scenario_id}\n{s.intensity_mm_h:.0f}mm" for s in summaries]
        crit_counts = [s.num_critical_pipes for s in summaries]
        over_counts = [s.num_overloaded_pipes for s in summaries]
        x = list(range(len(labels)))
        width = 0.36

        self.ax_bar.bar([i - width / 2 for i in x], crit_counts, width=width, label="Críticas (>=75%)", color="#ef4444")
        self.ax_bar.bar([i + width / 2 for i in x], over_counts, width=width, label="Sobrecarg. (>100%)", color="#7f1d1d")
        self.ax_bar.set_xticks(x)
        self.ax_bar.set_xticklabels(labels)
        self.ax_bar.set_title("Tuberías Críticas", color=theme.TEXT_PRIMARY, fontsize=8.5)
        self.ax_bar.legend(fontsize=6.5, facecolor=theme.BG_PANEL, labelcolor=theme.TEXT_PRIMARY)

        # Curvas temporales hacia PTAR Punta Canoa
        colors = ["#22c55e", "#38bdf8", "#eab308", "#f97316", "#ef4444"]
        for idx, s in enumerate(summaries):
            ts = [snap.time_min for snap in s.result.snapshots]
            qs = [snap.total_sink_discharge_m3s for snap in s.result.snapshots]
            self.ax_ptar.plot(
                ts, qs, label=f"E{s.scenario_id} ({s.intensity_mm_h:.0f})",
                color=colors[idx % len(colors)], linewidth=1.6,
            )
        self.ax_ptar.set_title("Descarga PTAR 31 (m³/s)", color=theme.TEXT_PRIMARY, fontsize=8.5)
        self.ax_ptar.set_xlabel("Tiempo (min)", color=theme.TEXT_SECONDARY, fontsize=7.5)
        self.ax_ptar.legend(fontsize=6.5, facecolor=theme.BG_PANEL, labelcolor=theme.TEXT_PRIMARY)

        self.canvas.draw_idle()
