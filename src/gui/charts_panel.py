"""Panel de gráficas temporales (hidrograma doble eje y utilización % con escala adaptativa)."""

import time
import tkinter as tk
from typing import Dict, List, Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.ticker import FuncFormatter

from src.simulation.models import SimulationResult
from . import theme

_CURSOR_THROTTLE_S = 0.08
_TOP3_STYLES: Tuple[Tuple[str, str], ...] = (
    (theme.PALETTE_GRAPHITE, "-"),
    (theme.ACCENT_PRIMARY, "--"),
    ("#d97706", "-."),
)
_LEGEND_KW = dict(
    frameon=True, facecolor=theme.PAPER_BG, edgecolor=theme.PAPER_BORDER, framealpha=0.94,
)


def _style_axis(ax, title: str, ylabel: str) -> None:
    """Aplica la estética editorial vitela/grafito a un eje Matplotlib."""
    ax.set_facecolor(theme.PAPER_BG)
    ax.set_title(title, fontsize=8.5, fontweight="bold", color=theme.INK_PRIMARY, loc="left", pad=4)
    ax.set_ylabel(ylabel, fontsize=7.5, color=theme.INK_PRIMARY)
    ax.tick_params(colors=theme.INK_PRIMARY, labelsize=7.2)
    for name, spine in ax.spines.items():
        spine.set_color(theme.INK_PRIMARY)
        spine.set_linewidth(0.8 if name in ("left", "bottom") else 0.45)
    ax.grid(True, linestyle="--", linewidth=0.6, color=theme.CANVAS_GRID_MAJOR, alpha=0.85)
    ax.set_axisbelow(True)


def _fmt_pct_tick(val: float, _pos: int) -> str:
    if val >= 1000.0:
        return f"{val / 1000.0:g}k"
    return f"{val:g}"


class ChartsPanel(tk.Frame):
    """Gráficas sincronizadas de hidrograma de red y utilización hidráulica por tubería."""

    def __init__(self, parent: tk.Misc, fonts: Optional[Dict[str, Tuple[str, int, str]]] = None) -> None:
        super().__init__(parent, bg=theme.PAPER_BG)
        self._fonts = fonts or {}
        self._result: Optional[SimulationResult] = None
        self._selected_pipe_id: Optional[str] = None
        self._dirty = False
        self._cursor_dirty = False
        self._is_visible = True
        self._pending_time = 0.0
        self._last_cursor_draw = 0.0
        self._cursor_after_id: Optional[str] = None
        self._cursor_hydro = None
        self._cursor_util = None
        self._bg = None

        self.fig = Figure(figsize=(4.4, 5.4), dpi=96, facecolor=theme.PAPER_BG, constrained_layout=True)
        self.ax_hydro, self.ax_util = self.fig.subplots(2, 1)
        self.ax_hydro_ptar = self.ax_hydro.twinx()
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.mpl_connect("draw_event", self._on_mpl_draw)
        tk_widget = self.canvas.get_tk_widget()
        tk_widget.configure(bg=theme.PAPER_BG, highlightthickness=0, bd=0)
        tk_widget.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self._draw_empty()

    def set_result(
        self,
        result: Optional[SimulationResult],
        selected_pipe_id: Optional[str] = None,
        is_visible: bool = True,
    ) -> None:
        """Actualiza resultados de simulación; difiere el redibujo si el panel está oculto."""
        self._result = result
        self._selected_pipe_id = selected_pipe_id
        self._is_visible = bool(is_visible)
        if result is not None and result.snapshots:
            t0, t1 = result.snapshots[0].time_min, result.snapshots[-1].time_min
            self._pending_time = min(max(self._pending_time, t0), t1)
        else:
            self._pending_time = 0.0
        if not self._is_visible:
            self._dirty = True
            return
        self._redraw()

    def update_cursor(self, time_min: float, is_visible: bool = True) -> None:
        """Mueve los cursores verticales con blitting rápido y throttle mínimo."""
        self._pending_time = float(time_min)
        self._is_visible = bool(is_visible)
        if not self._is_visible:
            self._cursor_dirty = True
            return
        if self._dirty:
            self._redraw()
            return
        if self._cursor_hydro is None or self._cursor_util is None:
            return
        now = time.monotonic()
        elapsed = now - self._last_cursor_draw
        if elapsed < _CURSOR_THROTTLE_S:
            self._cursor_dirty = True
            if self._cursor_after_id is None:
                delay_ms = max(20, int((_CURSOR_THROTTLE_S - elapsed) * 1000) + 5)
                self._cursor_after_id = self.after(delay_ms, self._flush_cursor)
            return
        self._apply_cursor(now)

    def mark_visible(self) -> None:
        """Ejecuta redibujo completo o actualización de cursor pendiente al hacerse visible."""
        self._is_visible = True
        if self._dirty:
            self._redraw()
        elif self._cursor_dirty:
            self._apply_cursor(time.monotonic())

    def _cancel_cursor_timer(self) -> None:
        if self._cursor_after_id is not None:
            try:
                self.after_cancel(self._cursor_after_id)
            except tk.TclError:
                pass
            self._cursor_after_id = None

    def _flush_cursor(self) -> None:
        self._cursor_after_id = None
        if self._is_visible and not self._dirty and self._cursor_dirty:
            self._apply_cursor(time.monotonic())

    def _on_mpl_draw(self, _event) -> None:
        if self._cursor_hydro is None or self._cursor_util is None:
            self._bg = None
            return
        self._bg = self.canvas.copy_from_bbox(self.fig.bbox)
        self.ax_hydro.draw_artist(self._cursor_hydro)
        self.ax_util.draw_artist(self._cursor_util)

    def _apply_cursor(self, now: float) -> None:
        self._cancel_cursor_timer()
        if self._cursor_hydro is not None:
            self._cursor_hydro.set_xdata([self._pending_time, self._pending_time])
        if self._cursor_util is not None:
            self._cursor_util.set_xdata([self._pending_time, self._pending_time])
        self._last_cursor_draw = now
        self._cursor_dirty = False
        if self._bg is not None and self._cursor_hydro is not None and self._cursor_util is not None:
            self.canvas.restore_region(self._bg)
            self.ax_hydro.draw_artist(self._cursor_hydro)
            self.ax_util.draw_artist(self._cursor_util)
            self.canvas.blit(self.fig.bbox)
        else:
            self.canvas.draw_idle()

    def _draw_empty(self) -> None:
        self._cursor_hydro = self._cursor_util = self._bg = None
        self.ax_hydro_ptar.clear()
        self.ax_hydro_ptar.set_visible(False)
        for ax, title, ylabel in (
            (self.ax_hydro, "Hidrograma de red", "Caudal (m³/s)"),
            (self.ax_util, "Utilización hidráulica", "Utilización (%)"),
        ):
            ax.clear()
            _style_axis(ax, title, ylabel)
            ax.text(0.5, 0.5, "Sin datos de simulación", transform=ax.transAxes,
                    ha="center", va="center", fontsize=8.5, color=theme.INK_MUTED)
            ax.set_xticks([])
            ax.set_yticks([])
        self.ax_util.set_xlabel("Tiempo (min)", fontsize=7.5, color=theme.INK_PRIMARY)
        self.canvas.draw_idle()

    def _redraw(self) -> None:
        self._cancel_cursor_timer()
        self._dirty = self._cursor_dirty = False
        if self._result is None or not self._result.snapshots:
            self._draw_empty()
            return

        snaps = self._result.snapshots
        times: List[float] = [s.time_min for s in snaps]
        inflows = [s.total_source_inflow_m3s for s in snaps]
        outflows = [s.total_sink_discharge_m3s for s in snaps]
        floods = [sum(ns.flooding_rate_m3s for ns in s.node_states.values()) for s in snaps]
        x_end = times[-1] if times[-1] > times[0] else times[0] + 1.0

        # Subgráfica 1: Hidrograma (doble eje cuando entrada >> descarga PTAR 31)
        ax1, ax1r = self.ax_hydro, self.ax_hydro_ptar
        ax1.clear()
        ax1r.clear()
        _style_axis(ax1, "Hidrograma de red", "Entrada / Rebose (m³/s)")
        ax1.plot(times, inflows, color=theme.ACCENT_PRIMARY, lw=1.7, label="Entrada fuentes")
        if any(r > 1e-9 for r in floods):
            ax1.plot(times, floods, color="#ef4444", ls="--", lw=1.35, label="Rebose superf.")

        max_in, max_out = max(inflows, default=0.0), max(outflows, default=0.0)
        use_dual = max_in > 0.0 and max_out > 0.0 and max_in > 5.0 * max_out
        if use_dual:
            ax1r.set_visible(True)
            ax1r.plot(times, outflows, color=theme.PALETTE_GRAPHITE, lw=2.0, label="PTAR 31 (eje der.)")
            ax1r.yaxis.tick_right()
            ax1r.yaxis.set_label_position("right")
            ax1r.set_ylabel("PTAR 31 (m³/s)", fontsize=7.4, color=theme.PALETTE_GRAPHITE)
            ax1r.tick_params(axis="y", colors=theme.PALETTE_GRAPHITE, labelsize=7.1)
            ax1r.set_ylim(0.0, max_out * 1.42)
            ax1r.spines["right"].set_color(theme.PALETTE_GRAPHITE)
            ax1r.spines["right"].set_linewidth(0.85)
            for side in ("left", "top", "bottom"):
                ax1r.spines[side].set_visible(False)
            ax1.set_ylim(0.0, max_in * 1.32)
            h1, l1 = ax1.get_legend_handles_labels()
            h2, l2 = ax1r.get_legend_handles_labels()
            ax1.legend(h1 + h2, l1 + l2, loc="upper right", fontsize=6.4, **_LEGEND_KW)
        else:
            ax1r.set_visible(False)
            ax1.set_ylabel("Caudal (m³/s)", fontsize=7.5, color=theme.INK_PRIMARY)
            ax1.plot(times, outflows, color=theme.PALETTE_GRAPHITE, lw=1.8, label="Descarga PTAR 31")
            ax1.set_ylim(0.0, max(0.05, max(max_in, max_out) * 1.32))
            ax1.legend(loc="upper right", fontsize=6.5, **_LEGEND_KW)
        ax1.set_xlim(times[0], x_end)
        self._cursor_hydro = ax1.axvline(self._pending_time, color="#991b1b", ls="--", lw=1.15, alpha=0.85, animated=True)

        # Subgráfica 2: Utilización % (escala lineal 0-100% + logarítmica >100% si hay sobrecarga alta)
        ax2 = self.ax_util
        ax2.clear()
        peaks = self._result.peak_pipe_utilization
        sel = self._selected_pipe_id
        if sel and sel in snaps[0].pipe_states:
            series = [s.pipe_states[sel].utilization_pct for s in snaps]
            peak_val = peaks.get(sel, max(series, default=0.0))
            max_u = max(series, default=0.0)
            _style_axis(ax2, f"Utilización — {sel}", "Utilización (%)")
            ax2.plot(times, series, color=theme.ACCENT_PRIMARY, lw=1.9, label=f"{sel} ({peak_val:.1f}%)")
            ax2.fill_between(times, series, 0.0, color=theme.ACCENT_PRIMARY, alpha=0.12)
        else:
            top3 = sorted(peaks.items(), key=lambda kv: kv[1], reverse=True)[:3]
            max_u = max((v for _, v in top3), default=0.0)
            _style_axis(ax2, "Utilización — Top 3 críticas", "Utilización (%)")
            for idx, (pid, peak_val) in enumerate(top3):
                series = [s.pipe_states[pid].utilization_pct if pid in s.pipe_states else 0.0 for s in snaps]
                col, ls = _TOP3_STYLES[idx % len(_TOP3_STYLES)]
                ax2.plot(times, series, color=col, ls=ls, lw=1.8 - idx * 0.2, label=f"{pid} ({peak_val:.0f}%)")

        ax2.axhline(75.0, color="#ef4444", ls="--", lw=1.0, label="75% crítica")
        ax2.axhline(100.0, color="#991b1b", ls="-", lw=1.1, label="100% sobrecarga")
        ax2.set_xlabel("Tiempo (min)", fontsize=7.5, color=theme.INK_PRIMARY)
        ax2.set_xlim(times[0], x_end)
        if max_u > 300.0:
            ax2.set_yscale("symlog", linthresh=100.0, linscale=1.35)
            top_lim = max_u * 12.0
            ax2.set_ylim(0.0, top_lim)
            ticks = [t for t in (0, 50, 100, 500, 2000, 10000, 50000, 200000) if t <= top_lim]
            ax2.set_yticks(ticks)
            ax2.yaxis.set_major_formatter(FuncFormatter(_fmt_pct_tick))
            ax2.set_ylabel("Utilización % (symlog >100%)", fontsize=7.1, color=theme.INK_PRIMARY)
        else:
            ax2.set_yscale("linear")
            ax2.set_ylim(0.0, max(125.0, max_u * 1.32))
        ax2.legend(loc="upper right", fontsize=6.1, ncol=2, **_LEGEND_KW)
        self._cursor_util = ax2.axvline(self._pending_time, color="#991b1b", ls="--", lw=1.15, alpha=0.85, animated=True)
        self._bg = None
        self._last_cursor_draw = time.monotonic()
        self.canvas.draw_idle()
