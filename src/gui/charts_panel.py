"""Paneles de gráficas Matplotlib estilizados y adaptables a cualquier tamaño de panel."""

import time
import tkinter as tk
import warnings
from typing import Dict, List, Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from src.data_structures import PipeEdge
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


def _safe_tight_layout(fig: Figure, widget: Optional[tk.Misc] = None) -> None:
    """Aplica tight_layout de forma segura adaptándose al tamaño real del panel sin recortes."""
    if widget is not None:
        try:
            w, h = widget.winfo_width(), widget.winfo_height()
            if (w > 1 and w < 180) or (h > 1 and h < 180):
                return
        except tk.TclError:
            return
    w_px = fig.get_figwidth() * fig.dpi
    h_px = fig.get_figheight() * fig.dpi
    if w_px < 180 or h_px < 180:
        return
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        try:
            fig.tight_layout(pad=0.85, h_pad=1.05, w_pad=0.65)
            has_warn = any("Tight layout not applied" in str(w.message) for w in caught)
        except Exception:
            has_warn = True
    if has_warn:
        try:
            fig.subplots_adjust(left=0.16, right=0.96, top=0.91, bottom=0.14, hspace=0.46, wspace=0.28)
        except Exception:
            pass


def _lock_tkagg_dpi(canvas: FigureCanvasTkAgg, container: tk.Misc) -> None:
    """Fija el DPI lógico del lienzo embebido evitando que <Map> en HiDPI agrande el bitmap 1.5x."""
    try:
        container.pack_propagate(False)
    except tk.TclError:
        pass
    try:
        tkw = canvas.get_tk_widget()
        tkw.unbind("<Map>")
        canvas._set_device_pixel_ratio = lambda _ratio: False  # type: ignore[attr-defined]
    except Exception:
        pass


def _sync_figure_to_widget(canvas: FigureCanvasTkAgg, fig: Figure) -> Tuple[int, int]:
    """Sincroniza pulgadas de la figura y PhotoImage exactamente al tamaño actual del widget."""
    try:
        tkw = canvas.get_tk_widget()
        w = int(tkw.winfo_width())
        h = int(tkw.winfo_height())
    except tk.TclError:
        return (0, 0)
    if w < 180 or h < 180:
        return (0, 0)
    dpival = float(fig.dpi)
    if dpival > 0.0:
        cur_w, cur_h = fig.get_size_inches()
        target_w = w / dpival
        target_h = h / dpival
        if abs(cur_w - target_w) > 0.01 or abs(cur_h - target_h) > 0.01:
            fig.set_size_inches(target_w, target_h, forward=False)
    try:
        photo = getattr(canvas, "_tkphoto", None)
        if photo is not None and (photo.width() != w or photo.height() != h):
            photo.configure(width=w, height=h)
        img_id = getattr(canvas, "_tkcanvas_image_region", None)
        if img_id is not None:
            tkw.coords(img_id, w // 2, h // 2)
    except Exception:
        pass
    return (w, h)


class TemporalChartsPanel(tk.Frame):
    """Gráfica temporal (hidrograma Antes vs. Después + % uso) y perfil longitudinal Q vs Qmax."""

    def __init__(
        self,
        master: tk.Misc,
        dpi: int = 96,
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
    ) -> None:
        super().__init__(master, bg=theme.PAPER_BG)
        self._dpi = max(72, int(dpi))
        self._ui_font = ui_font
        self._mono_font = mono_font
        self._subtab: str = "hydro"

        # Barra compacta de subpestañas
        subbar = tk.Frame(self, bg=theme.DOCK_BG)
        subbar.pack(side=tk.TOP, fill=tk.X)
        tk.Frame(self, bg=theme.DOCK_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

        self._btn_hydro = tk.Button(
            subbar,
            text="Hidrograma y %",
            command=lambda: self.set_subtab("hydro"),
            bg=theme.ACCENT_PRIMARY,
            fg=theme.ACCENT_INK,
            activebackground=theme.ACCENT_HOVER,
            activeforeground=theme.ACCENT_INK,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            font=(self._ui_font, 8, "bold"),
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )
        self._btn_hydro.pack(side=tk.LEFT, padx=(6, 3), pady=4)

        self._btn_profile = tk.Button(
            subbar,
            text="Perfil longitudinal (Q vs Qmax)",
            command=lambda: self.set_subtab("profile"),
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_PRIMARY,
            activebackground=theme.PAPER_HOVER,
            activeforeground=theme.INK_PRIMARY,
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            font=(self._ui_font, 8, "normal"),
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )
        self._btn_profile.pack(side=tk.LEFT, padx=(3, 6), pady=4)

        self._container = tk.Frame(self, bg=theme.PAPER_BG)
        self._container.pack(fill=tk.BOTH, expand=True)

        # Subvista 1: Hidrograma + Utilización temporal
        self._hydro_frame = tk.Frame(self._container, bg=theme.PAPER_BG)
        self.figure = Figure(figsize=(4.0, 5.2), dpi=self._dpi, facecolor=theme.PAPER_BG)
        self.ax_flow = self.figure.add_subplot(211)
        self.ax_util = self.figure.add_subplot(212)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self._hydro_frame)
        self.canvas.get_tk_widget().configure(width=320, height=340)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        _lock_tkagg_dpi(self.canvas, self._hydro_frame)
        self._hydro_frame.pack(fill=tk.BOTH, expand=True)

        # Subvista 2: Perfil longitudinal escalonado (Q_actual vs Q_max)
        self._profile_frame = tk.Frame(self._container, bg=theme.PAPER_BG)
        self.profile_figure = Figure(figsize=(4.0, 5.2), dpi=self._dpi, facecolor=theme.PAPER_BG)
        self.ax_profile = self.profile_figure.add_subplot(111)

        self.profile_canvas = FigureCanvasTkAgg(self.profile_figure, master=self._profile_frame)
        self.profile_canvas.get_tk_widget().configure(width=320, height=340)
        self.profile_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        _lock_tkagg_dpi(self.profile_canvas, self._profile_frame)

        self._cached_key: Optional[Tuple[int, int, Optional[str]]] = None
        self._cursor_flow: Optional[Line2D] = None
        self._cursor_util: Optional[Line2D] = None
        self._resize_after: Optional[str] = None
        self._last_draw_ts: float = 0.0

        self._last_result: Optional[SimulationResult] = None
        self._last_prev_result: Optional[SimulationResult] = None
        self._last_pipe_id: Optional[str] = None
        self._last_time_min: Optional[float] = None
        self._last_route_pipes: List[PipeEdge] = []
        self._last_step_idx: int = 0
        self._last_diam_overrides: Dict[str, float] = {}

        _apply_axis_style(self.ax_flow)
        _apply_axis_style(self.ax_util)
        _apply_axis_style(self.ax_profile)
        self.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._on_destroy)

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self and self._resize_after is not None:
            try:
                self.after_cancel(self._resize_after)
            except tk.TclError:
                pass
            self._resize_after = None

    def _on_resize(self, event: tk.Event) -> None:
        if event.width < 160 or event.height < 160:
            return
        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(120, self._refit_layout)

    def _refit_layout(self) -> None:
        self._resize_after = None
        if self._subtab == "profile":
            _sync_figure_to_widget(self.profile_canvas, self.profile_figure)
            _safe_tight_layout(self.profile_figure, self.profile_canvas.get_tk_widget())
            self.profile_canvas.draw_idle()
        else:
            _sync_figure_to_widget(self.canvas, self.figure)
            _safe_tight_layout(self.figure, self.canvas.get_tk_widget())
            self.canvas.draw_idle()

    def set_subtab(self, tab_id: str) -> None:
        if tab_id not in ("hydro", "profile"):
            return
        self._subtab = tab_id
        self._hydro_frame.pack_forget()
        self._profile_frame.pack_forget()
        if tab_id == "profile":
            self._profile_frame.pack(fill=tk.BOTH, expand=True)
            self._btn_profile.configure(
                bg=theme.ACCENT_PRIMARY,
                fg=theme.ACCENT_INK,
                font=(self._ui_font, 8, "bold"),
            )
            self._btn_hydro.configure(
                bg=theme.PAPER_SUBTLE,
                fg=theme.INK_PRIMARY,
                font=(self._ui_font, 8, "normal"),
            )
            self._redraw_profile()
        else:
            self._hydro_frame.pack(fill=tk.BOTH, expand=True)
            self._btn_hydro.configure(
                bg=theme.ACCENT_PRIMARY,
                fg=theme.ACCENT_INK,
                font=(self._ui_font, 8, "bold"),
            )
            self._btn_profile.configure(
                bg=theme.PAPER_SUBTLE,
                fg=theme.INK_PRIMARY,
                font=(self._ui_font, 8, "normal"),
            )
            _safe_tight_layout(self.figure, self.canvas.get_tk_widget())
            self.canvas.draw_idle()

    def update_plots(
        self,
        result: Optional[SimulationResult],
        selected_pipe_id: Optional[str] = None,
        current_time_min: Optional[float] = None,
        previous_result: Optional[SimulationResult] = None,
        route_pipes: Optional[List[PipeEdge]] = None,
        current_step_index: int = 0,
        diameter_overrides: Optional[Dict[str, float]] = None,
        throttle_draw: bool = False,
    ) -> None:
        self._last_result = result
        self._last_prev_result = previous_result
        self._last_pipe_id = selected_pipe_id
        self._last_time_min = current_time_min
        if route_pipes is not None:
            self._last_route_pipes = list(route_pipes)
        self._last_step_idx = current_step_index
        self._last_diam_overrides = dict(diameter_overrides or {})

        now = time.perf_counter()
        if self._subtab == "profile":
            if not throttle_draw or (now - self._last_draw_ts) >= 0.14:
                self._last_draw_ts = now
                self._redraw_profile()

        prev_id = id(previous_result) if (previous_result is not None and previous_result is not result) else 0
        cache_key = (id(result), prev_id, selected_pipe_id) if result is not None else None
        if cache_key is not None and cache_key == self._cached_key:
            # Actualización rápida en reproducción: solo desplaza las líneas de tiempo
            if current_time_min is not None:
                if self._cursor_flow is not None:
                    self._cursor_flow.set_xdata([current_time_min, current_time_min])
                if self._cursor_util is not None:
                    self._cursor_util.set_xdata([current_time_min, current_time_min])
                if self._subtab == "hydro":
                    if not throttle_draw or (now - self._last_draw_ts) >= 0.14:
                        self._last_draw_ts = now
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
            self.ax_flow.set_title("Sin simulación ejecutada", color=theme.INK_PRIMARY, fontsize=8.5)
            _safe_tight_layout(self.figure, self.canvas.get_tk_widget())
            self.canvas.draw_idle()
            return

        times = [s.time_min for s in result.snapshots]
        inflows = [s.total_source_inflow_m3s for s in result.snapshots]
        ptar_out = [s.total_sink_discharge_m3s for s in result.snapshots]

        has_prev = (
            previous_result is not None
            and previous_result is not result
            and bool(previous_result.snapshots)
        )
        max_q_val = max(inflows + ptar_out + [0.05])
        if has_prev:
            prev_times = [s.time_min for s in previous_result.snapshots]
            prev_ptar = [s.total_sink_discharge_m3s for s in previous_result.snapshots]
            if prev_ptar:
                max_q_val = max(max_q_val, max(prev_ptar))
            self.ax_flow.plot(
                prev_times,
                prev_ptar,
                label="Antes",
                color=theme.INK_MUTED,
                linestyle=":",
                linewidth=1.9,
                zorder=2,
            )

        self.ax_flow.plot(
            times,
            inflows,
            label="Entrada",
            color=theme.INK_PRIMARY,
            linewidth=1.7,
            alpha=0.88,
            zorder=3,
        )
        self.ax_flow.plot(
            times,
            ptar_out,
            label="PTAR 31",
            color=theme.ACCENT_PRIMARY,
            linewidth=2.3,
            zorder=4,
        )
        self.ax_flow.set_ylim(0.0, max_q_val * 1.38)
        t_cur = current_time_min if current_time_min is not None else times[0]
        self._cursor_flow = self.ax_flow.axvline(
            t_cur, color=theme.ACCENT_PRIMARY, linestyle=":", linewidth=1.4, alpha=0.9
        )
        self.ax_flow.set_title(
            "Caudal: Antes vs. Después (m³/s)" if has_prev else "Balance de Caudales (m³/s)",
            color=theme.INK_PRIMARY,
            fontsize=8.8,
            fontweight="bold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=5,
        )
        self.ax_flow.set_ylabel("m³/s", color=theme.INK_PRIMARY, fontsize=7.6)
        self.ax_flow.legend(
            loc="upper center",
            ncol=3 if has_prev else 2,
            frameon=True,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.94,
            fontsize=6.8,
            borderpad=0.28,
            labelspacing=0.25,
            columnspacing=0.65,
            handlelength=1.25,
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
        max_u_val = 105.0
        for idx, pid in enumerate(target_pids):
            utils = [
                s.pipe_states[pid].utilization_pct if pid in s.pipe_states else 0.0
                for s in result.snapshots
            ]
            if utils:
                max_u_val = max(max_u_val, max(utils))
            self.ax_util.plot(
                times,
                utils,
                label=f"{pid} ({result.peak_pipe_utilization.get(pid, 0.0):.0f}%)",
                color=palette[idx % len(palette)],
                linewidth=1.9,
            )

        self.ax_util.axhline(
            100.0, color="#dc2626", linestyle="--", linewidth=1.1, label="Cap. 100%"
        )
        self.ax_util.set_ylim(0.0, max_u_val * 1.32)
        self._cursor_util = self.ax_util.axvline(
            t_cur, color=theme.ACCENT_PRIMARY, linestyle=":", linewidth=1.4, alpha=0.9
        )
        title_u = (
            f"Utilización — {selected_pipe_id}"
            if selected_pipe_id
            else "Utilización — Top 3 Críticas"
        )
        self.ax_util.set_title(
            title_u,
            color=theme.INK_PRIMARY,
            fontsize=8.8,
            fontweight="bold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=5,
        )
        self.ax_util.set_xlabel("Tiempo (min)", color=theme.INK_SECONDARY, fontsize=7.6)
        self.ax_util.set_ylabel("% Cap.", color=theme.INK_SECONDARY, fontsize=7.6)
        self.ax_util.legend(
            loc="upper center",
            ncol=2,
            frameon=True,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.94,
            fontsize=6.8,
            borderpad=0.28,
            labelspacing=0.25,
            columnspacing=0.75,
            handlelength=1.25,
            labelcolor=theme.INK_PRIMARY,
        )

        self._last_draw_ts = now
        _sync_figure_to_widget(self.canvas, self.figure)
        _safe_tight_layout(self.figure, self.canvas.get_tk_widget())
        self.canvas.draw_idle()

    def _redraw_profile(self) -> None:
        _sync_figure_to_widget(self.profile_canvas, self.profile_figure)
        self.ax_profile.clear()
        _apply_axis_style(self.ax_profile)

        result = self._last_result
        route = self._last_route_pipes
        if result is None or not result.snapshots or not route:
            self.ax_profile.set_xticks([])
            self.ax_profile.set_yticks([])
            self.ax_profile.text(
                0.5,
                0.5,
                "Seleccione una tubería o trace una ruta (BFS/DFS)\npara inspeccionar Q(t) vs. Qmax hacia PTAR 31.",
                ha="center",
                va="center",
                color=theme.INK_MUTED,
                fontsize=8.0,
                transform=self.ax_profile.transAxes,
            )
            _safe_tight_layout(self.profile_figure, self.profile_canvas.get_tk_widget())
            self.profile_canvas.draw_idle()
            return

        step_idx = max(0, min(len(result.snapshots) - 1, self._last_step_idx))
        snap = result.snapshots[step_idx]

        xs = list(range(len(route)))
        q_lives: List[float] = []
        q_maxs: List[float] = []
        bar_colors: List[str] = []
        diams: List[float] = []
        x_labels: List[str] = []

        for pipe in route:
            ps = snap.pipe_states.get(pipe.pipe_id)
            eff_qmax = (
                ps.effective_q_max_m3s
                if (ps is not None and ps.effective_q_max_m3s is not None)
                else pipe.q_max_m3s
            )
            q_live = ps.flow_m3s if ps is not None else 0.0
            col = (
                ("#991b1b" if ps.category.is_overloaded else ps.category.color_hex)
                if ps is not None
                else theme.ACCENT_PRIMARY
            )
            diam = self._last_diam_overrides.get(pipe.pipe_id, pipe.diameter_in)
            q_lives.append(q_live)
            q_maxs.append(eff_qmax)
            bar_colors.append(col)
            diams.append(diam)
            if len(route) <= 6:
                x_labels.append(f"{pipe.pipe_id}\n{pipe.from_node}→{pipe.to_node}")
            else:
                x_labels.append(pipe.pipe_id)

        self.ax_profile.bar(xs, q_lives, width=0.64, color=bar_colors, zorder=3)
        self.ax_profile.bar(
            xs,
            q_maxs,
            width=0.72,
            facecolor="none",
            edgecolor=theme.INK_PRIMARY,
            linewidth=1.6,
            zorder=4,
        )

        top_y = max(q_lives + q_maxs + [0.05])
        self.ax_profile.set_ylim(0.0, top_y * 1.36)

        tag_fs = 6.2 if len(route) >= 9 else (6.8 if len(route) >= 7 else 7.4)
        for idx, (pipe, q_live, q_mx, diam) in enumerate(zip(route, q_lives, q_maxs, diams)):
            y_pos = max(q_live, q_mx) + top_y * 0.025
            tag = f"{diam:.0f}\"" if q_mx > 1e-9 else "OBST"
            is_sel = pipe.pipe_id == self._last_pipe_id
            self.ax_profile.text(
                idx,
                y_pos,
                tag,
                ha="center",
                va="bottom",
                fontsize=tag_fs,
                fontweight="bold" if is_sel else "normal",
                color=theme.ACCENT_TEXT_ON_LIGHT if is_sel else theme.INK_PRIMARY,
            )

        self.ax_profile.set_xticks(xs)
        self.ax_profile.set_xticklabels(
            x_labels,
            fontsize=6.8 if len(route) > 6 else 7.5,
            rotation=30 if len(route) > 5 else 0,
            ha="right" if len(route) > 5 else "center",
        )
        self.ax_profile.set_ylabel("Caudal (m³/s)", color=theme.INK_PRIMARY, fontsize=7.6)
        start_n = route[0].from_node
        end_n = route[-1].to_node
        self.ax_profile.set_title(
            f"Perfil ({start_n} → {end_n}) · t={snap.time_min:.0f}m",
            color=theme.INK_PRIMARY,
            fontsize=8.8,
            fontweight="bold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=5,
        )
        legend_handles = [
            Patch(facecolor="none", edgecolor=theme.INK_PRIMARY, linewidth=1.6, label="Cap. Qmax"),
            Patch(facecolor=theme.ACCENT_PRIMARY, edgecolor="none", label="Caudal Q(t)"),
        ]
        self.ax_profile.legend(
            handles=legend_handles,
            loc="upper right",
            ncol=2,
            frameon=True,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.94,
            fontsize=6.8,
            borderpad=0.28,
            columnspacing=0.75,
            handlelength=1.25,
            labelcolor=theme.INK_PRIMARY,
        )
        _safe_tight_layout(self.profile_figure, self.profile_canvas.get_tk_widget())
        self.profile_canvas.draw_idle()


class ComparisonChartsPanel(tk.Frame):
    """Gráfica comparativa de los escenarios de precipitación con disposición adaptativa."""

    def __init__(self, master: tk.Misc, dpi: int = 96) -> None:
        super().__init__(master, bg=theme.PAPER_BG)
        self._dpi = max(72, int(dpi))
        self.figure = Figure(figsize=(4.0, 4.4), dpi=self._dpi, facecolor=theme.PAPER_BG)
        self._layout_mode: str = "stacked"  # 'stacked' (2x1) o 'side' (1x2)
        self._last_summaries: List[ScenarioSummary] = []
        self._resize_after: Optional[str] = None

        self.ax_bar = self.figure.add_subplot(211)
        self.ax_ptar = self.figure.add_subplot(212)

        self.canvas = FigureCanvasTkAgg(self.figure, master=self)
        self.canvas.get_tk_widget().configure(width=320, height=300)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        _lock_tkagg_dpi(self.canvas, self)
        self.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._on_destroy)
        self._draw_empty()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self and self._resize_after is not None:
            try:
                self.after_cancel(self._resize_after)
            except tk.TclError:
                pass
            self._resize_after = None

    def _on_resize(self, event: tk.Event) -> None:
        if event.width < 180 or event.height < 180:
            return
        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(100, self._reflow)

    def _reflow(self, width: Optional[int] = None, height: Optional[int] = None) -> None:
        self._resize_after = None
        w = width if width is not None else max(1, self.winfo_width())
        h = height if height is not None else max(1, self.winfo_height())
        if w < 180 or h < 180:
            return
        _sync_figure_to_widget(self.canvas, self.figure)
        new_mode = "side" if (w >= 560 and h < 480) else "stacked"
        if new_mode != self._layout_mode or self._last_summaries:
            self._layout_mode = new_mode
            if self._last_summaries:
                self.update_comparison(self._last_summaries)
                return
        _safe_tight_layout(self.figure, self.canvas.get_tk_widget())
        self.canvas.draw_idle()

    def _draw_empty(self) -> None:
        _sync_figure_to_widget(self.canvas, self.figure)
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
            "Presione 'Comparar 5 Escenarios'\npara generar la comparativa hidráulica.",
            ha="center",
            va="center",
            color=theme.INK_MUTED,
            fontsize=8.5,
            transform=ax.transAxes,
        )
        _safe_tight_layout(self.figure, self.canvas.get_tk_widget())
        self.canvas.draw_idle()

    def update_comparison(self, summaries: List[ScenarioSummary]) -> None:
        self._last_summaries = list(summaries)
        if not summaries:
            self._draw_empty()
            return

        _, h_px = _sync_figure_to_widget(self.canvas, self.figure)
        if h_px <= 0:
            h_px = max(360, int(round(self.figure.get_figheight() * self.figure.dpi)))

        self.figure.clear()
        if self._layout_mode == "side":
            self.ax_bar = self.figure.add_subplot(121)
            self.ax_ptar = self.figure.add_subplot(122)
        else:
            self.ax_bar = self.figure.add_subplot(211)
            self.ax_ptar = self.figure.add_subplot(212)

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
            label="Críticas ≥75%",
            color="#ef4444",
        )
        self.ax_bar.bar(
            [i + width / 2 for i in x],
            over_counts,
            width=width,
            label="Sobrec. >100%",
            color="#991b1b",
        )
        self.ax_bar.set_ylim(0, max_c * 1.58)
        self.ax_bar.set_xticks(x)
        self.ax_bar.set_xticklabels(labels)
        self.ax_bar.set_ylabel("Tuberías", color=theme.INK_SECONDARY, fontsize=7.6)
        self.ax_bar.set_title(
            "Tuberías Críticas",
            color=theme.INK_PRIMARY,
            fontsize=8.8,
            fontweight="bold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=4,
        )
        self.ax_bar.legend(
            loc="upper center",
            ncol=2,
            fontsize=6.5,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.95,
            borderpad=0.26,
            columnspacing=0.65,
            handlelength=1.15,
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
        self.ax_ptar.set_ylim(0, max_q * 1.22)
        self.ax_ptar.set_title(
            "Descarga PTAR 31 (m³/s)",
            color=theme.INK_PRIMARY,
            fontsize=8.8,
            fontweight="bold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=4,
        )
        self.ax_ptar.set_xlabel("Tiempo (min)", color=theme.INK_SECONDARY, fontsize=7.4, labelpad=1)
        self.ax_ptar.set_ylabel("m³/s", color=theme.INK_SECONDARY, fontsize=7.6)
        anchor_y = -min(0.56, max(0.18, 210.0 / float(h_px))) if self._layout_mode == "stacked" else -0.24
        self.ax_ptar.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, anchor_y),
            fontsize=6.5,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.95,
            ncol=3 if self._layout_mode == "stacked" else 2,
            borderpad=0.26,
            columnspacing=0.55,
            handlelength=1.1,
            labelcolor=theme.INK_PRIMARY,
        )

        _safe_tight_layout(self.figure, self.canvas.get_tk_widget())
        self.canvas.draw_idle()
