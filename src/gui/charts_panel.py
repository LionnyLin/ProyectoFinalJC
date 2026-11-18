"""Paneles de gráficas Matplotlib estilizados y adaptables a cualquier tamaño de panel."""

import tkinter as tk
from typing import List, Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D

from src.simulation.comparison import ScenarioSummary
from src.simulation.models import SimulationResult
from . import theme


def _apply_axis_style(ax) -> None:
    ax.set_facecolor(theme.PAPER_ALT_ROW)
    ax.tick_params(colors=theme.INK_PRIMARY, labelsize=7.5)
    for spine in ax.spines.values():
        spine.set_color(theme.INK_PRIMARY)
        spine.set_linewidth(0.85)
    ax.grid(True, linestyle="--", alpha=0.75, color=theme.PAPER_BORDER)


class TemporalChartsPanel(tk.Frame):
    """Gráfica temporal de hidrograma (entrada vs PTAR 31) y utilización por tubería."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=theme.PAPER_BG)
        self.figure = Figure(figsize=(3.4, 3.2), dpi=96, facecolor=theme.PAPER_BG)
        self.ax_flow = self.figure.add_subplot(211)
        self.ax_util = self.figure.add_subplot(212)
        self.figure.subplots_adjust(hspace=0.46, left=0.18, right=0.95, top=0.90, bottom=0.13)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().configure(width=280, height=220)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._cached_key: Optional[Tuple[int, Optional[str]]] = None
        self._cursor_flow: Optional[Line2D] = None
        self._cursor_util: Optional[Line2D] = None
        self._resize_after: Optional[str] = None

        _apply_axis_style(self.ax_flow)
        _apply_axis_style(self.ax_util)
        self.bind("<Configure>", self._on_resize)

    def _on_resize(self, event: tk.Event) -> None:
        if event.width < 140 or event.height < 140:
            return
        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(80, lambda: self._adjust_margins(event.width, event.height))

    def _adjust_margins(self, width: int, height: int) -> None:
        self._resize_after = None
        left = 0.19 if width < 380 else 0.14
        hspace = 0.74 if height < 420 else 0.64
        self.figure.subplots_adjust(hspace=hspace, left=left, right=0.96, top=0.86, bottom=0.12)
        self.canvas.draw_idle()

    def update_plots(
        self,
        result: Optional[SimulationResult],
        selected_pipe_id: Optional[str] = None,
        current_time_min: Optional[float] = None,
    ) -> None:
        cache_key = (id(result), selected_pipe_id) if result is not None else None
        if cache_key is not None and cache_key == self._cached_key:
            # Actualización rápida en reproducción: solo desplaza las líneas de tiempo
            if current_time_min is not None:
                if self._cursor_flow is not None:
                    self._cursor_flow.set_xdata([current_time_min, current_time_min])
                if self._cursor_util is not None:
                    self._cursor_util.set_xdata([current_time_min, current_time_min])
                self.canvas.draw_idle()
            return

        self._cached_key = cache_key
        self._cursor_flow = None
        self._cursor_util = None

        self.ax_flow.clear()
        self.ax_util.clear()
        _apply_axis_style(self.ax_flow)
        _apply_axis_style(self.ax_util)

        if result is None or not result.snapshots:
            self.ax_flow.set_title("Sin simulación ejecutada", color=theme.INK_PRIMARY, fontsize=9)
            self.canvas.draw_idle()
            return

        times = [s.time_min for s in result.snapshots]
        inflows = [s.total_source_inflow_m3s for s in result.snapshots]
        ptar_out = [s.total_sink_discharge_m3s for s in result.snapshots]

        self.ax_flow.plot(
            times, inflows, label="Entrada fuentes", color=theme.ACCENT_PRIMARY, linewidth=2.1
        )
        self.ax_flow.plot(
            times, ptar_out, label="Descarga PTAR (31)", color=theme.INK_PRIMARY, linewidth=2.1
        )
        t_cur = current_time_min if current_time_min is not None else times[0]
        self._cursor_flow = self.ax_flow.axvline(
            t_cur, color=theme.ACCENT_PRIMARY, linestyle=":", linewidth=1.4, alpha=0.9
        )
        self.ax_flow.set_title(
            "Balance de Caudales (m³/s)",
            color=theme.INK_PRIMARY,
            fontsize=9.5,
            fontweight="semibold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=22,
        )
        self.ax_flow.set_ylabel("m³/s", color=theme.INK_PRIMARY, fontsize=8)
        self.ax_flow.legend(
            loc="lower center",
            bbox_to_anchor=(0.5, 1.01),
            ncol=2,
            frameon=False,
            fontsize=7,
            labelcolor=theme.INK_PRIMARY,
        )

        target_pids: List[str] = []
        if selected_pipe_id and selected_pipe_id in result.peak_pipe_utilization:
            target_pids = [selected_pipe_id]
        else:
            sorted_p = sorted(
                result.peak_pipe_utilization.items(), key=lambda kv: kv[1], reverse=True
            )
            target_pids = [pid for pid, _ in sorted_p[:3]]

        palette = [theme.ACCENT_PRIMARY, "#f97316", theme.INK_PRIMARY]
        for idx, pid in enumerate(target_pids):
            utils = [
                s.pipe_states[pid].utilization_pct if pid in s.pipe_states else 0.0
                for s in result.snapshots
            ]
            self.ax_util.plot(
                times,
                utils,
                label=f"{pid} (máx. {result.peak_pipe_utilization.get(pid, 0.0):.1f}%)",
                color=palette[idx % len(palette)],
                linewidth=1.9,
            )

        self.ax_util.axhline(
            100.0, color="#dc2626", linestyle="--", linewidth=1.1, label="Capacidad 100%"
        )
        self._cursor_util = self.ax_util.axvline(
            t_cur, color=theme.ACCENT_PRIMARY, linestyle=":", linewidth=1.4, alpha=0.9
        )
        title_u = (
            f"Utilización Temporal — {selected_pipe_id}"
            if selected_pipe_id
            else "Utilización Temporal — Top 3 Críticas"
        )
        self.ax_util.set_title(
            title_u,
            color=theme.INK_PRIMARY,
            fontsize=9.5,
            fontweight="semibold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=22,
        )
        self.ax_util.set_xlabel("Tiempo (min)", color=theme.INK_SECONDARY, fontsize=8)
        self.ax_util.set_ylabel("% Cap.", color=theme.INK_SECONDARY, fontsize=8)
        self.ax_util.legend(
            loc="lower center",
            bbox_to_anchor=(0.5, 1.01),
            ncol=2,
            frameon=False,
            fontsize=7,
            labelcolor=theme.INK_PRIMARY,
        )

        self.canvas.draw_idle()


class ComparisonChartsPanel(tk.Frame):
    """Gráfica comparativa de los escenarios de precipitación con disposición adaptativa."""

    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master, bg=theme.PAPER_BG)
        self.figure = Figure(figsize=(3.4, 3.2), dpi=96, facecolor=theme.PAPER_BG)
        self._layout_mode: str = "stacked"  # 'stacked' (2x1) o 'side' (1x2)
        self._last_summaries: List[ScenarioSummary] = []
        self._resize_after: Optional[str] = None

        self.ax_bar = self.figure.add_subplot(211)
        self.ax_ptar = self.figure.add_subplot(212)
        self.figure.subplots_adjust(hspace=0.56, left=0.18, right=0.95, top=0.89, bottom=0.14)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().configure(width=280, height=220)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.bind("<Configure>", self._on_resize)
        self._draw_empty()

    def _on_resize(self, event: tk.Event) -> None:
        if event.width < 160 or event.height < 160:
            return
        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(90, lambda: self._reflow(event.width, event.height))

    def _reflow(self, width: int, height: int) -> None:
        self._resize_after = None
        new_mode = "side" if (width >= 560 and height < 480) else "stacked"
        if new_mode != self._layout_mode:
            self._layout_mode = new_mode
            self.update_comparison(self._last_summaries)
            return
        if self._layout_mode == "side":
            self.figure.subplots_adjust(wspace=0.32, left=0.11, right=0.97, top=0.86, bottom=0.22)
        else:
            left = 0.18 if width < 380 else 0.15
            hspace = 0.86 if height < 360 else 0.74
            self.figure.subplots_adjust(hspace=hspace, left=left, right=0.95, top=0.88, bottom=0.17)
        self.canvas.draw_idle()

    def _draw_empty(self) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.set_facecolor(theme.PAPER_ALT_ROW)
        ax.set_xticks([])
        ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_color(theme.PAPER_BORDER)
        ax.text(
            0.5,
            0.5,
            "Presione 'Comparar los 5 Escenarios'\npara generar la comparativa hidráulica.",
            ha="center",
            va="center",
            color=theme.INK_MUTED,
            fontsize=9,
            transform=ax.transAxes,
        )
        self.canvas.draw_idle()

    def update_comparison(self, summaries: List[ScenarioSummary]) -> None:
        self._last_summaries = list(summaries)
        if not summaries:
            self._draw_empty()
            return

        self.figure.clear()
        if self._layout_mode == "side":
            self.ax_bar = self.figure.add_subplot(121)
            self.ax_ptar = self.figure.add_subplot(122)
            self.figure.subplots_adjust(wspace=0.32, left=0.11, right=0.97, top=0.86, bottom=0.22)
        else:
            self.ax_bar = self.figure.add_subplot(211)
            self.ax_ptar = self.figure.add_subplot(212)
            self.figure.subplots_adjust(hspace=0.82, left=0.17, right=0.95, top=0.88, bottom=0.17)

        for ax in (self.ax_bar, self.ax_ptar):
            _apply_axis_style(ax)

        labels = [f"E{s.scenario_id}" for s in summaries]
        crit_counts = [s.num_critical_pipes for s in summaries]
        over_counts = [s.num_overloaded_pipes for s in summaries]
        x = list(range(len(labels)))
        width = 0.36
        max_c = max(crit_counts + over_counts + [4])

        self.ax_bar.bar(
            [i - width / 2 for i in x],
            crit_counts,
            width=width,
            label="Críticas (≥75%)",
            color="#ef4444",
        )
        self.ax_bar.bar(
            [i + width / 2 for i in x],
            over_counts,
            width=width,
            label="Sobrecarg. (>100%)",
            color="#991b1b",
        )
        self.ax_bar.set_ylim(0, max_c * 1.38)
        self.ax_bar.set_xticks(x)
        self.ax_bar.set_xticklabels(labels)
        self.ax_bar.set_ylabel("Tuberías", color=theme.INK_SECONDARY, fontsize=7.5)
        self.ax_bar.set_title(
            "Tuberías Críticas por Escenario",
            color=theme.INK_PRIMARY,
            fontsize=9,
            fontweight="semibold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
        )
        self.ax_bar.legend(
            loc="upper left",
            fontsize=6.5,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            labelcolor=theme.INK_PRIMARY,
        )

        colors = [theme.ACCENT_PRIMARY, theme.INK_PRIMARY, "#eab308", "#f97316", "#dc2626"]
        max_q = 0.01
        for idx, s in enumerate(summaries):
            ts = [snap.time_min for snap in s.result.snapshots]
            qs = [snap.total_sink_discharge_m3s for snap in s.result.snapshots]
            if qs:
                max_q = max(max_q, max(qs))
            cond_es = theme.translate_scenario_name(s.condition, compact=True)
            self.ax_ptar.plot(
                ts,
                qs,
                label=f"E{s.scenario_id} {cond_es}",
                color=colors[idx % len(colors)],
                linewidth=1.9,
            )
        self.ax_ptar.set_ylim(0, max_q * 1.42)
        self.ax_ptar.set_title(
            "Descarga PTAR 31 (m³/s)",
            color=theme.INK_PRIMARY,
            fontsize=9,
            fontweight="semibold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
        )
        self.ax_ptar.set_xlabel("Tiempo (min)", color=theme.INK_SECONDARY, fontsize=7.5)
        self.ax_ptar.set_ylabel("m³/s", color=theme.INK_SECONDARY, fontsize=7.5)
        self.ax_ptar.legend(
            loc="upper left",
            fontsize=6.5,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            labelcolor=theme.INK_PRIMARY,
            ncol=3 if self._layout_mode == "stacked" else 2,
        )

        self.canvas.draw_idle()
