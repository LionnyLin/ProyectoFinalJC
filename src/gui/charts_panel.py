"""Paneles de gráficas: evolución temporal (hidrograma, utilización, perfil longitudinal) y comparación."""

import bisect
import math
import time
import tkinter as tk
from typing import Any, Dict, List, Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

from src.algorithms.analysis import classify_utilization
from src.algorithms.queries import build_route_to_sink
from src.data_structures import PipeEdge
from src.simulation.comparison import ScenarioSummary
from src.simulation.models import PipeIntervention, SimulationResult, compute_symlog_ticks
from . import theme

_CURSOR_THROTTLE_S = 0.08
_PROFILE_THROTTLE_S = 0.14
_MIN_PX = 180
_TOP3_STYLES: Tuple[Tuple[str, str, float], ...] = (
    ("#991b1b", "-", 2.3), ("#ea580c", "--", 1.9), ("#1d4ed8", "-.", 1.6),
)
_LEGEND_KW = dict(frameon=True, facecolor=theme.PAPER_BG, edgecolor=theme.PAPER_BORDER, framealpha=0.94)
_CURSOR_KW = dict(color="#991b1b", ls="--", lw=1.15, alpha=0.85, animated=True)
_PTAR_COLOR, _BEFORE_COLOR, _AFTER_COLOR = "#0F766E", "#6B7280", "#1D4ED8"
_PROFILE_MODES = {"pct": "pct", "flow": "flow", "q": "flow"}


# --------------------------------------------------------------------------- utilidades de figura
def _style_axis(ax, title: str = "", ylabel: str = "") -> None:
    """Aplica la estética editorial vitela/grafito a un eje Matplotlib."""
    ax.set_facecolor(theme.PAPER_BG)
    if title:
        ax.set_title(title, fontsize=8.5, fontweight="bold", color=theme.INK_PRIMARY, loc="left", pad=4)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=7.5, color=theme.INK_PRIMARY)
    ax.tick_params(colors=theme.INK_PRIMARY, labelsize=7.2)
    for name, spine in ax.spines.items():
        spine.set_color(theme.INK_PRIMARY)
        spine.set_linewidth(0.8 if name in ("left", "bottom") else 0.45)
    ax.grid(True, linestyle="--", linewidth=0.6, color=theme.CANVAS_GRID_MAJOR, alpha=0.85)
    ax.set_axisbelow(True)


def _lock_tkagg_dpi(canvas: FigureCanvasTkAgg, container: tk.Misc) -> None:
    """Fija el DPI lógico del lienzo embebido (evita que <Map> en HiDPI agrande el bitmap 1.5x)."""
    try:
        container.pack_propagate(False)
    except tk.TclError:
        pass
    try:
        canvas.get_tk_widget().unbind("<Map>")
        canvas._set_device_pixel_ratio = lambda _ratio: False  # type: ignore[attr-defined]
    except Exception:
        pass


def _sync_figure_to_widget(canvas: FigureCanvasTkAgg, fig: Figure) -> Tuple[int, int]:
    """Sincroniza pulgadas de la figura y PhotoImage exactamente al tamaño actual del widget."""
    try:
        tkw = canvas.get_tk_widget()
        w, h = int(tkw.winfo_width()), int(tkw.winfo_height())
    except tk.TclError:
        return (0, 0)
    if w < _MIN_PX or h < _MIN_PX:
        return (0, 0)
    dpi = float(fig.dpi)
    if dpi > 0.0:
        cur_w, cur_h = fig.get_size_inches()
        if abs(cur_w - w / dpi) > 0.01 or abs(cur_h - h / dpi) > 0.01:
            fig.set_size_inches(w / dpi, h / dpi, forward=False)
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


def _fmt_pct_compact(val: float) -> str:
    if val >= 10000.0:
        return f"{val / 1000.0:.1f}k%"
    if val >= 1000.0:
        return f"{val:,.0f}%"
    return f"{val:.0f}%"


def _fmt_vol_compact(val: float) -> str:
    if val >= 100000.0:
        return f"{val / 1000.0:.0f}k"
    if val >= 1000.0:
        return f"{val / 1000.0:.1f}k"
    return f"{val:.0f}"


def _format_intervention_summary(
    interventions: Dict[str, PipeIntervention], diameter_overrides: Optional[Dict[str, float]] = None,
) -> str:
    """Título del banner de impacto según las intervenciones activas."""
    if not interventions:
        return "Comparación: Antes (Base) vs. Después (Actual)"
    diameter_overrides = diameter_overrides or {}
    if len(interventions) == 1:
        pid, inv = next(iter(interventions.items()))
        parts: List[str] = []
        if inv.diameter_in_override is not None:
            parts.append(f"Ø {inv.diameter_in_override:.0f}\"")
        elif pid in diameter_overrides:
            parts.append(f"Ø {diameter_overrides[pid]:.0f}\"")
        if inv.obstruction_pct > 1e-6:
            parts.append(f"Obstr. {inv.obstruction_pct:.0f}%")
        return f"Intervención: {pid} ({' · '.join(parts) if parts else 'Modificada'})"
    pids = ", ".join(sorted(interventions)[:4])
    extra = f" (+{len(interventions) - 4})" if len(interventions) > 4 else ""
    return f"{len(interventions)} intervenciones activas: {pids}{extra}"


def _tab_button(parent: tk.Misc, text: str, command, font: tuple, padx: int, pady: int) -> tk.Button:
    return tk.Button(
        parent, text=text, command=command, relief="flat", bd=0, padx=padx, pady=pady, font=font,
        cursor="hand2", highlightthickness=1, highlightbackground=theme.DOCK_BORDER,
        activebackground=theme.ACCENT_HOVER, activeforeground=theme.ACCENT_INK,
    )


def _set_active(btn: tk.Button, active: bool, size: int, family: str) -> None:
    if active:
        btn.configure(bg=theme.ACCENT_PRIMARY, fg=theme.ACCENT_INK, font=(family, size, "bold"))
    else:
        btn.configure(bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY, font=(family, size, "normal"))


# --------------------------------------------------------------------------- panel de evolución
class ChartsPanel(tk.Frame):
    """Pestaña Evolución: `Hidrograma y %` y `Perfil longitudinal` sincronizados con el paso actual."""

    def __init__(self, parent: tk.Misc, fonts: Optional[Dict[str, Tuple[str, int, str]]] = None) -> None:
        super().__init__(parent, bg=theme.PAPER_BG)
        self._fonts = fonts or {}
        ui = self._fonts.get("body", ("TkDefaultFont", 9, "normal"))[0]
        self._ui = ui
        self._mono = self._fonts.get("mono", ("TkFixedFont", 9, "normal"))[0]
        self._subtab = "hydro"
        self._profile_mode = "pct"
        self._result: Optional[SimulationResult] = None
        self._prev: Optional[SimulationResult] = None
        self._graph: Any = None
        self._focus_pipe: Optional[str] = None
        self._focus_node: Optional[str] = None
        self._times: List[float] = []
        self._route: List[PipeEdge] = []
        self._route_key: Optional[tuple] = None
        self._route_override: Optional[List[PipeEdge]] = None   # ruta activa del recorrido (prioridad sobre la selección)
        self._step_index = 0
        self._pending_time = 0.0
        self._is_visible = True
        self._dirty = False            # redibujo completo del hidrograma pendiente
        self._profile_dirty = False    # redibujo del perfil pendiente
        self._cursor_dirty = False
        self._last_cursor_draw = 0.0
        self._last_profile_draw = 0.0
        self._cursor_after_id: Optional[str] = None
        self._profile_after_id: Optional[str] = None
        self._resize_after: Optional[str] = None
        self._cursor_hydro = self._cursor_util = None
        self._bg = None
        self._banner_visible = False
        self._note_visible = False

        # Barra de sub-pestañas
        subbar = tk.Frame(self, bg=theme.DOCK_BG)
        subbar.pack(side=tk.TOP, fill=tk.X)
        tk.Frame(self, bg=theme.DOCK_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)
        self._btn_hydro = _tab_button(subbar, "Hidrograma y %", lambda: self.set_subtab("hydro"), (ui, 8, "bold"), 10, 4)
        self._btn_profile = _tab_button(subbar, "Perfil longitudinal", lambda: self.set_subtab("profile"), (ui, 8, "normal"), 10, 4)
        self._btn_hydro.pack(side=tk.LEFT, padx=(6, 3), pady=4)
        self._btn_profile.pack(side=tk.LEFT, padx=(3, 6), pady=4)

        self._container = tk.Frame(self, bg=theme.PAPER_BG)
        self._container.pack(fill=tk.BOTH, expand=True)

        # Banner de impacto Antes vs. Después
        self._banner = tk.Frame(self, bg="#EEF2F6", highlightthickness=1, highlightbackground="#94A3B8")
        tk.Frame(self._banner, bg="#1D4ED8", width=4).pack(side=tk.LEFT, fill=tk.Y)
        body = tk.Frame(self._banner, bg="#EEF2F6")
        body.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6, pady=4)
        self._lbl_impact_title = tk.Label(body, bg="#EEF2F6", fg="#1E3A8A", font=(ui, 8, "bold"), anchor="w", justify=tk.LEFT)
        self._lbl_impact_title.pack(fill=tk.X)
        self._lbl_impact_metrics = tk.Label(body, bg="#EEF2F6", fg=theme.INK_PRIMARY, font=(self._mono, 7),
                                            anchor="w", justify=tk.LEFT, wraplength=310)
        self._lbl_impact_metrics.pack(fill=tk.X)
        self._banner.bind("<Configure>", lambda e: self._lbl_impact_metrics.configure(wraplength=max(200, e.width - 20)))

        # Sub-vista 1: hidrograma + utilización
        self._hydro_frame = tk.Frame(self._container, bg=theme.PAPER_BG)
        self.fig = Figure(figsize=(4.4, 5.4), dpi=96, facecolor=theme.PAPER_BG, constrained_layout=True)
        self.ax_hydro, self.ax_util = self.fig.subplots(2, 1)
        self.ax_hydro_ptar = self.ax_hydro.twinx()
        self.canvas = FigureCanvasTkAgg(self.fig, master=self._hydro_frame)
        self.canvas.mpl_connect("draw_event", self._on_mpl_draw)
        self.canvas.get_tk_widget().configure(bg=theme.PAPER_BG, highlightthickness=0, bd=0, width=320, height=340)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        _lock_tkagg_dpi(self.canvas, self._hydro_frame)
        self._hydro_frame.pack(fill=tk.BOTH, expand=True)

        # Sub-vista 2: perfil longitudinal
        self._profile_frame = tk.Frame(self._container, bg=theme.PAPER_BG)
        prof_bar = tk.Frame(self._profile_frame, bg=theme.PAPER_SUBTLE)
        prof_bar.pack(side=tk.TOP, fill=tk.X)
        tk.Label(prof_bar, text="Vista:", bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED, font=(ui, 7, "bold")).pack(side=tk.LEFT, padx=(6, 4), pady=3)
        self._btn_prof_pct = _tab_button(prof_bar, "% Uso vs Cap. (100%)", lambda: self.set_profile_mode("pct"), (ui, 7, "bold"), 7, 2)
        self._btn_prof_flow = _tab_button(prof_bar, "Caudal (m³/s)", lambda: self.set_profile_mode("flow"), (ui, 7, "normal"), 7, 2)
        self._btn_prof_pct.pack(side=tk.LEFT, padx=2, pady=3)
        self._btn_prof_flow.pack(side=tk.LEFT, padx=2, pady=3)
        tk.Frame(self._profile_frame, bg=theme.PAPER_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)
        self._lbl_note = tk.Label(self._profile_frame, bg="#FEF2F2", fg="#7F1D1D", font=(ui, 7), anchor="w", justify=tk.LEFT,
                                  wraplength=310, padx=6, pady=3, highlightthickness=1, highlightbackground="#FCA5A5")
        self._prof_wrap = tk.Frame(self._profile_frame, bg=theme.PAPER_BG)
        self._prof_wrap.pack(fill=tk.BOTH, expand=True)
        self._profile_frame.bind("<Configure>", lambda e: self._lbl_note.configure(wraplength=max(200, e.width - 18)))
        self.profile_fig = Figure(figsize=(4.4, 5.4), dpi=96, facecolor=theme.PAPER_BG, constrained_layout=True)
        self.ax_profile = self.profile_fig.add_subplot(111)
        self.profile_canvas = FigureCanvasTkAgg(self.profile_fig, master=self._prof_wrap)
        self.profile_canvas.get_tk_widget().configure(bg=theme.PAPER_BG, highlightthickness=0, bd=0, width=320, height=340)
        self.profile_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        _lock_tkagg_dpi(self.profile_canvas, self._prof_wrap)
        self._style_prof_buttons()

        self.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._on_destroy)
        self._draw_empty()

    # ----------------------------------------------------------------------- API pública
    def set_graph(self, graph: Any) -> None:
        """Define el grafo para calcular la ruta del perfil longitudinal."""
        if graph is not self._graph:
            self._graph = graph
            self._route_key = None
            self._profile_dirty = True
            if self._subtab == "profile" and self._is_visible:
                self._redraw_profile()

    def set_route(self, edges: Optional[List[PipeEdge]]) -> None:
        """Fija la ruta activa (p. ej. de un recorrido BFS/DFS con destino); `None` vuelve a la ruta por selección."""
        new = list(edges) if edges else None
        if [e.pipe_id for e in new or []] == [e.pipe_id for e in self._route_override or []]:
            self._route_override = new
            return
        self._route_override, self._route_key = new, None
        self._profile_dirty = True
        if self._subtab == "profile" and self._is_visible:
            self._redraw_profile()

    def set_result(
        self, result: Optional[SimulationResult], focus_pipe_id: Optional[str] = None, is_visible: bool = True,
        previous_result: Optional[SimulationResult] = None, graph: Any = None, focus_node_id: Optional[str] = None,
    ) -> None:
        """Actualiza resultados; difiere el redibujo (dirty) si el panel está oculto."""
        self._result, self._prev = result, previous_result
        self._focus_pipe, self._focus_node = focus_pipe_id, focus_node_id
        if graph is not None and graph is not self._graph:
            self._graph, self._route_key = graph, None
        self._is_visible = bool(is_visible)
        if result is not None and result.snapshots:
            self._times = [s.time_min for s in result.snapshots]
            self._pending_time = min(max(self._pending_time, self._times[0]), self._times[-1])
            self._step_index = self._nearest_step(self._pending_time)
        else:
            self._times, self._pending_time, self._step_index = [], 0.0, 0
        self._dirty = self._profile_dirty = True
        self._cursor_dirty = False
        if not self._is_visible:
            self._sync_banner()
            return
        self._redraw_active()

    def update_cursor(self, time_min: float, is_visible: bool = True, step_index: Optional[int] = None) -> None:
        """Mueve el cursor temporal (blitting + throttle) y refresca el perfil al paso actual."""
        self._pending_time = float(time_min)
        n = len(self._times)
        self._step_index = max(0, min(n - 1, int(step_index))) if (step_index is not None and n) else self._nearest_step(self._pending_time)
        self._is_visible = bool(is_visible)
        self._profile_dirty = True
        if not self._is_visible:
            self._cursor_dirty = True
            return
        if self._subtab == "profile":
            self._cursor_dirty = True
            self._schedule_profile()
            return
        if self._dirty:
            self._redraw_active()
            return
        if self._cursor_hydro is None:
            return
        now = time.monotonic()
        elapsed = now - self._last_cursor_draw
        if elapsed < _CURSOR_THROTTLE_S:
            self._cursor_dirty = True
            if self._cursor_after_id is None:
                self._cursor_after_id = self.after(max(20, int((_CURSOR_THROTTLE_S - elapsed) * 1000) + 5), self._flush_cursor)
            return
        self._apply_cursor(now)

    def set_subtab(self, tab_id: str) -> None:
        """Alterna entre `hydro` (Hidrograma y %) y `profile` (Perfil longitudinal)."""
        if tab_id not in ("hydro", "profile") or tab_id == self._subtab:
            return
        self._subtab = tab_id
        self._hydro_frame.pack_forget()
        self._profile_frame.pack_forget()
        frame = self._profile_frame if tab_id == "profile" else self._hydro_frame
        frame.pack(fill=tk.BOTH, expand=True)
        _set_active(self._btn_hydro, tab_id == "hydro", 8, self._ui)
        _set_active(self._btn_profile, tab_id == "profile", 8, self._ui)
        if self._is_visible:
            self._redraw_active()

    def set_profile_mode(self, mode: str) -> None:
        """Modo del perfil: `pct` (% uso vs Qmax) o `flow` (Q vs capacidad en m³/s)."""
        mode = _PROFILE_MODES.get(mode, "")
        if not mode or mode == self._profile_mode:
            return
        self._profile_mode = mode
        self._style_prof_buttons()
        self._profile_dirty = True
        if self._subtab == "profile" and self._is_visible:
            self._redraw_profile()

    def mark_visible(self) -> None:
        """Ejecuta el redibujo o cursor pendientes al hacerse visible el panel."""
        self._is_visible = True
        if self._subtab == "profile":
            if self._profile_dirty or self._cursor_dirty:
                self._redraw_profile()
        elif self._dirty:
            self._redraw()
        elif self._cursor_dirty:
            self._apply_cursor(time.monotonic())

    def _cancel_cursor_timer(self) -> None:
        for attr in ("_cursor_after_id", "_profile_after_id", "_resize_after"):
            aid = getattr(self, attr)
            if aid is not None:
                try:
                    self.after_cancel(aid)
                except tk.TclError:
                    pass
                setattr(self, attr, None)

    # ----------------------------------------------------------------------- utilidades internas
    def _style_prof_buttons(self) -> None:
        pct = self._profile_mode == "pct"
        for btn, on in ((self._btn_prof_pct, pct), (self._btn_prof_flow, not pct)):
            btn.configure(bg=theme.ACCENT_PRIMARY if on else theme.PAPER_BG, fg=theme.ACCENT_INK if on else theme.INK_PRIMARY,
                          font=(self._ui, 7, "bold" if on else "normal"))

    def _nearest_step(self, t: float) -> int:
        if not self._times:
            return 0
        i = bisect.bisect_left(self._times, t)
        if i <= 0:
            return 0
        if i >= len(self._times):
            return len(self._times) - 1
        return i if self._times[i] - t < t - self._times[i - 1] else i - 1

    def _redraw_active(self) -> None:
        self._sync_banner()
        if self._subtab == "profile":
            self._redraw_profile()
        else:
            self._redraw()

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self:
            self._cancel_cursor_timer()

    def _on_resize(self, event: tk.Event) -> None:
        if event.width < 160 or event.height < 160:
            return
        if self._resize_after is not None:
            try:
                self.after_cancel(self._resize_after)
            except tk.TclError:
                pass
        self._resize_after = self.after(120, self._refit)

    def _refit(self) -> None:
        self._resize_after = None
        self._bg = None
        if self._subtab == "profile":
            _sync_figure_to_widget(self.profile_canvas, self.profile_fig)
            self.profile_canvas.draw_idle()
        else:
            _sync_figure_to_widget(self.canvas, self.fig)
            self.canvas.draw_idle()

    def _interventions(self) -> Dict[str, PipeIntervention]:
        return dict(self._result.config.interventions) if self._result is not None else {}

    def _has_prev(self) -> bool:
        r, p = self._result, self._prev
        return r is not None and p is not None and p is not r and bool(p.snapshots) and bool(r.snapshots)

    def _focus_pipes(self) -> List[str]:
        """Tubería seleccionada, o la intervenida de mayor cambio, o el top-3 por pico."""
        res, prev, ivs = self._result, self._prev, self._interventions()
        if res is None:
            return []
        peaks = res.peak_pipe_utilization
        if self._focus_pipe and self._focus_pipe in peaks:
            return [self._focus_pipe]
        if self._has_prev() and ivs:
            cand = [p for p in ivs if p in peaks]
            if cand:
                cand.sort(key=lambda p: (abs(peaks.get(p, 0.0) - prev.peak_pipe_utilization.get(p, 0.0)), peaks.get(p, 0.0)), reverse=True)
                return [cand[0]]
        ranked = sorted(peaks.items(), key=lambda kv: (kv[1], res.peak_pipe_demand_ratio.get(kv[0], 0.0)), reverse=True)
        return [pid for pid, _ in ranked[:3]]

    def _sync_banner(self) -> None:
        """Muestra/oculta el banner de impacto de intervención."""
        if not self._has_prev():
            if self._banner_visible:
                self._banner.pack_forget()
                self._banner_visible = False
            return
        res, prev = self._result, self._prev
        pids = self._focus_pipes()
        focus = pids[0] if pids else None
        p0, p1 = prev.peak_sink_discharge_m3s, res.peak_sink_discharge_m3s
        delta = (p1 - p0) / p0 * 100.0 if p0 > 1e-6 else 0.0
        parts = [f"PTAR: {p0:.2f}→{p1:.2f} m³/s ({delta:+.0f}%)"]
        if focus:
            parts.append(f"Uso {focus}: {_fmt_pct_compact(prev.peak_pipe_utilization.get(focus, 0.0))}→"
                         f"{_fmt_pct_compact(res.peak_pipe_utilization.get(focus, 0.0))}")
        d_flood = res.total_surface_flooding_m3 - prev.total_surface_flooding_m3
        parts.append(f"Rebose: {d_flood:+,.0f} m³" if abs(d_flood) >= 1.0 else f"Rebose: {res.total_surface_flooding_m3:,.0f} m³")
        self._lbl_impact_title.configure(text=_format_intervention_summary(self._interventions()))
        self._lbl_impact_metrics.configure(text=" · ".join(parts))
        if not self._banner_visible:
            self._banner.pack(side=tk.TOP, fill=tk.X, before=self._container, padx=4, pady=(4, 0))
            self._banner_visible = True

    # ----------------------------------------------------------------------- cursor rápido
    def _flush_cursor(self) -> None:
        self._cursor_after_id = None
        if self._is_visible and not self._dirty and self._cursor_dirty and self._subtab == "hydro":
            self._apply_cursor(time.monotonic())

    def _on_mpl_draw(self, _event) -> None:
        if self._cursor_hydro is None or self._cursor_util is None:
            self._bg = None
            return
        try:
            self._bg = self.canvas.copy_from_bbox(self.fig.bbox)
            self.ax_hydro.draw_artist(self._cursor_hydro)
            self.ax_util.draw_artist(self._cursor_util)
        except Exception:
            self._bg = None

    def _apply_cursor(self, now: float) -> None:
        if self._cursor_after_id is not None:
            try:
                self.after_cancel(self._cursor_after_id)
            except tk.TclError:
                pass
            self._cursor_after_id = None
        for cur in (self._cursor_hydro, self._cursor_util):
            if cur is not None:
                cur.set_xdata([self._pending_time, self._pending_time])
        self._last_cursor_draw = now
        self._cursor_dirty = False
        if self._bg is not None and self._cursor_hydro is not None and self._cursor_util is not None:
            try:
                self.canvas.restore_region(self._bg)
                self.ax_hydro.draw_artist(self._cursor_hydro)
                self.ax_util.draw_artist(self._cursor_util)
                self.canvas.blit(self.fig.bbox)
                return
            except Exception:
                self._bg = None
        self.canvas.draw_idle()

    def _schedule_profile(self) -> None:
        """Redibuja el perfil con throttle (el cursor del hidrograma se actualiza al volver a esa vista)."""
        elapsed = time.monotonic() - self._last_profile_draw
        if elapsed >= _PROFILE_THROTTLE_S:
            self._redraw_profile()
        elif self._profile_after_id is None:
            self._profile_after_id = self.after(int((_PROFILE_THROTTLE_S - elapsed) * 1000) + 5, self._flush_profile)

    def _flush_profile(self) -> None:
        self._profile_after_id = None
        if self._is_visible and self._subtab == "profile" and self._profile_dirty:
            self._redraw_profile()

    # ----------------------------------------------------------------------- hidrograma + utilización
    def _draw_empty(self) -> None:
        self._cursor_hydro = self._cursor_util = self._bg = None
        self.ax_hydro_ptar.clear()
        self.ax_hydro_ptar.set_visible(False)
        for ax, title, ylabel in ((self.ax_hydro, "Hidrograma de red", "Caudal (m³/s)"),
                                  (self.ax_util, "Utilización hidráulica", "Utilización (%)")):
            ax.clear()
            _style_axis(ax, title, ylabel)
            ax.text(0.5, 0.5, "Sin datos de simulación", transform=ax.transAxes, ha="center", va="center",
                    fontsize=8.5, color=theme.INK_MUTED)
            ax.set_xticks([])
            ax.set_yticks([])
        self.ax_util.set_xlabel("Tiempo (min)", fontsize=7.5, color=theme.INK_PRIMARY)
        self._dirty = False
        self.canvas.draw_idle()

    def _redraw(self) -> None:
        """Redibujo completo del hidrograma y la utilización."""
        self._cancel_cursor_timer()
        self._dirty = self._cursor_dirty = False
        res = self._result
        if res is None or not res.snapshots:
            self._draw_empty()
            return
        snaps = res.snapshots
        times = [s.time_min for s in snaps]
        x_end = times[-1] if times[-1] > times[0] else times[0] + 1.0
        has_prev = self._has_prev()
        ax1, ax1r = self.ax_hydro, self.ax_hydro_ptar
        ax1.clear()
        ax1r.clear()
        ax1r.set_visible(False)
        _style_axis(ax1, "", "Caudal (m³/s)")
        inflows = [s.total_source_inflow_m3s for s in snaps]
        ptar = [s.total_sink_discharge_m3s for s in snaps]
        if has_prev:
            self._draw_hydro_compare(ax1, times, ptar)
        else:
            self._draw_hydro_single(ax1, ax1r, times, inflows, ptar, snaps)
        ax1.set_xlim(times[0], x_end)
        self._cursor_hydro = ax1.axvline(self._pending_time, **_CURSOR_KW)

        pids = self._focus_pipes()
        self._draw_util(self.ax_util, times, x_end, pids, has_prev)
        self._cursor_util = self.ax_util.axvline(self._pending_time, **_CURSOR_KW)
        self._bg = None
        self._last_cursor_draw = time.monotonic()
        self.canvas.draw_idle()

    def _draw_hydro_single(self, ax1, ax1r, times, inflows, ptar, snaps) -> None:
        floods = [sum(ns.flooding_rate_m3s for ns in s.node_states.values()) for s in snaps]
        has_flood = any(r > 1e-9 for r in floods)
        max_in, max_out = max(inflows, default=0.0), max(ptar, default=0.0)
        split = max_in > 0.0 and max_out > 0.0 and max_in > 5.0 * max_out
        handles = ax1.plot(times, inflows, color=theme.INK_PRIMARY, lw=1.75, alpha=0.9, zorder=3,
                           label="Entrada total (izq.)" if split else "Entrada total")
        if has_flood:
            handles += ax1.plot(times, floods, color="#DC2626", ls="--", lw=1.4, zorder=3.5,
                                label="Rebose (izq.)" if split else "Rebose superf.")
        if split:
            ax1r.set_visible(True)
            handles += ax1r.plot(times, ptar, color=_PTAR_COLOR, lw=2.2, zorder=4, label="PTAR 31 (der.)")
            ax1r.fill_between(times, 0.0, ptar, color=_PTAR_COLOR, alpha=0.14, zorder=1)
            ax1r.yaxis.tick_right()
            ax1r.yaxis.set_label_position("right")
            ax1r.set_ylabel("PTAR 31 (m³/s)", fontsize=7.4, color=_PTAR_COLOR)
            ax1r.tick_params(axis="y", colors=_PTAR_COLOR, labelsize=7.1)
            ax1r.set_ylim(0.0, max_out * 2.35)
            ax1r.spines["right"].set_color(_PTAR_COLOR)
            ax1r.spines["right"].set_linewidth(1.3)
            for side in ("left", "top", "bottom"):
                ax1r.spines[side].set_visible(False)
            left_top = max(max_in, max(floods) if has_flood else 0.0, 0.05)
            ax1.set_ylim(0.0, left_top * 1.26)
            ax1.set_ylabel("Entrada / Rebose (m³/s)", fontsize=7.3, color=theme.INK_PRIMARY)
        else:
            handles += ax1.plot(times, ptar, color=_PTAR_COLOR, lw=2.2, zorder=4, label="PTAR 31")
            ax1.fill_between(times, 0.0, ptar, color=_PTAR_COLOR, alpha=0.14, zorder=1)
            ax1.set_ylim(0.0, max(0.05, max_in, max_out, max(floods) if has_flood else 0.0) * 1.28)
        ax1.set_title("Balance de caudales (m³/s)", fontsize=8.5, fontweight="bold", color=theme.INK_PRIMARY, loc="left", pad=4)
        ax1.legend(handles, [h.get_label() for h in handles], loc="upper right", fontsize=6.4, **_LEGEND_KW)

    def _draw_hydro_compare(self, ax1, times, ptar) -> None:
        prev = self._prev
        p_times = [s.time_min for s in prev.snapshots]
        p_ptar = [s.total_sink_discharge_m3s for s in prev.snapshots]
        l_prev = ax1.plot(p_times, p_ptar, color=_BEFORE_COLOR, ls="--", lw=1.85, zorder=2, label="Antes (PTAR)")[0]
        l_cur = ax1.plot(times, ptar, color=_AFTER_COLOR, lw=2.3, zorder=4, label="Después (PTAR)")[0]
        handles: List[Any] = [l_prev, l_cur]
        if len(p_ptar) == len(ptar):
            for where, col, lab in (([c >= p for c, p in zip(ptar, p_ptar)], "#16A34A", "+ Flujo PTAR"),
                                    ([c < p for c, p in zip(ptar, p_ptar)], "#DC2626", "− Pérdida PTAR")):
                ax1.fill_between(times, p_ptar, ptar, where=where, interpolate=True, color=col, alpha=0.16, zorder=1)
                if any(c > p + 1e-5 if col == "#16A34A" else c < p - 1e-5 for c, p in zip(ptar, p_ptar)):
                    handles.append(Patch(facecolor=col, alpha=0.28, edgecolor="none", label=lab))
        pk_prev, pk_cur = max(p_ptar, default=0.0), max(ptar, default=0.0)
        if pk_prev > 1e-6:
            ax1.annotate(f"{pk_prev:.2f}", xy=(p_times[p_ptar.index(pk_prev)], pk_prev), xytext=(0, 3), textcoords="offset points",
                         ha="center", va="bottom", fontsize=6.5, color="#4B5563", fontweight="bold")
        if pk_cur > 1e-6 and abs(pk_cur - pk_prev) > 0.01:
            below = pk_cur < pk_prev
            ax1.annotate(f"{pk_cur:.2f}", xy=(times[ptar.index(pk_cur)], pk_cur), xytext=(0, -9 if below else 3),
                         textcoords="offset points", ha="center", va="top" if below else "bottom",
                         fontsize=6.5, color=_AFTER_COLOR, fontweight="bold")
        delta = ""
        if pk_prev > 1e-6:
            dp = (pk_cur - pk_prev) / pk_prev * 100.0
            delta = f" ({dp:+.0f}% pico)" if abs(dp) >= 0.5 else " (sin cambio)"
        ax1.set_ylim(0.0, max(ptar + p_ptar + [0.05]) * 1.3)
        ax1.set_ylabel("PTAR 31 (m³/s)", fontsize=7.4, color=theme.INK_PRIMARY)
        ax1.set_title(f"PTAR 31: Antes vs. Después{delta}", fontsize=8.5, fontweight="bold", color=theme.INK_PRIMARY, loc="left", pad=4)
        ax1.legend(handles=handles, loc="upper right", fontsize=6.3, ncol=2, **_LEGEND_KW)

    def _draw_util(self, ax, times, x_end, pids, has_prev) -> None:
        res, prev = self._result, self._prev
        snaps = res.snapshots
        ax.clear()
        _style_axis(ax, "", "% Cap.")
        max_u = 105.0
        tie_note = ""
        focus = pids[0] if pids else None
        series = lambda r, pid: [s.pipe_states[pid].utilization_pct if pid in s.pipe_states else 0.0 for s in r.snapshots]
        if self._focus_pipe and focus == self._focus_pipe or (has_prev and focus and len(pids) == 1):
            cur = series(res, focus)
            pk_cur = res.peak_pipe_utilization.get(focus, max(cur, default=0.0))
            max_u = max(max_u, max(cur, default=0.0))
            if has_prev:
                pk_prev = prev.peak_pipe_utilization.get(focus, 0.0)
                ps = series(prev, focus)
                max_u = max(max_u, max(ps, default=0.0))
                ax.plot([s.time_min for s in prev.snapshots], ps, color=_BEFORE_COLOR, ls="--", lw=1.8, zorder=3,
                        label=f"Antes ({_fmt_pct_compact(pk_prev)})")
                color = "#DC2626" if pk_cur > pk_prev + 0.5 else ("#059669" if pk_cur < pk_prev - 0.5 else _AFTER_COLOR)
                ax.plot(times, cur, color=color, lw=2.3, zorder=4, label=f"Después ({_fmt_pct_compact(pk_cur)})")
                title = f"Utilización {focus}: Antes vs. Después"
            else:
                ax.plot(times, cur, color=theme.ACCENT_PRIMARY, lw=2.1, zorder=4, label=f"{focus} ({_fmt_pct_compact(pk_cur)})")
                ax.fill_between(times, cur, 0.0, color=theme.ACCENT_PRIMARY, alpha=0.12)
                title = f"Utilización — {focus}"
            demand = max(res.peak_pipe_demand_ratio.get(focus, 0.0), max(cur, default=0.0))
            if demand > 100.5:
                conv = []
                for sn in snaps:
                    ps_ = sn.pipe_states.get(focus)
                    eff = (ps_.effective_q_max_m3s if ps_ is not None and ps_.effective_q_max_m3s else None)
                    conv.append(0.0 if ps_ is None else (min(100.0, ps_.flow_m3s / eff * 100.0) if eff else min(100.0, ps_.utilization_pct)))
                ax.plot(times, conv, color="#7C3AED", ls=":", lw=1.5, zorder=3.5, label="Conducido (≤100%)")
                ax.lines[-2].set_label(f"{ax.lines[-2].get_label()} · Dem. ×{demand / 100.0:.1f}")
        else:
            peaks_seen: List[float] = []
            for idx, pid in enumerate(pids):
                col, ls, lw = _TOP3_STYLES[idx % 3]
                vals = series(res, pid)
                pk = res.peak_pipe_utilization.get(pid, 0.0)
                peaks_seen.append(pk)
                max_u = max(max_u, max(vals, default=0.0))
                ax.plot(times, vals, color=col, ls=ls, lw=lw, zorder=4 - idx * 0.2, label=f"{pid} ({_fmt_pct_compact(pk)})")
            title = "Utilización — Top 3 críticas"
            if len(peaks_seen) >= 2 and max(peaks_seen) > 5.0:
                tied = [p for p, k in zip(pids, peaks_seen) if abs(k - peaks_seen[0]) <= 1.0]
                if len(tied) >= 2:
                    tie_note = f"Empate en pico: {' = '.join(tied)} ({_fmt_pct_compact(peaks_seen[0])})"
        ax.set_title(title, fontsize=8.5, fontweight="bold", color=theme.INK_PRIMARY, loc="left", pad=4)
        self._configure_util_axis(ax, max_u)
        ax.set_xlabel(f"Tiempo (min)  ·  {tie_note}" if tie_note else "Tiempo (min)", fontsize=7.5, color=theme.INK_PRIMARY)
        ax.set_xlim(times[0], x_end)
        ax.legend(loc="upper left", fontsize=6.1, ncol=2, **_LEGEND_KW)

    @staticmethod
    def _configure_util_axis(ax, max_u: float) -> None:
        """Bandas de criticidad, líneas 75/100 % y eje symlog con marcas legibles."""
        ax.axhspan(0.0, 75.0, color="#22c55e", alpha=0.06, zorder=0)
        ax.axhspan(75.0, 100.0, color="#f97316", alpha=0.09, zorder=0)
        if max_u > 100.0:
            ax.axhspan(100.0, max_u * 1.45, color="#dc2626", alpha=0.04, zorder=0)
        ax.axhline(75.0, color="#f97316", ls=":", lw=1.0, label="Crít. 75%", zorder=2)
        ax.axhline(100.0, color="#dc2626", ls="--", lw=1.25, label="Cap. 100%", zorder=2)
        if max_u > 250.0:
            ax.set_yscale("symlog", linthresh=100.0, linscale=0.85)
            ax.set_ylim(0.0, max_u * 2.15)
            ax.set_yticks(compute_symlog_ticks(max_u))
            ax.minorticks_off()
            ax.set_ylabel("% Cap. (symlog >100%)", fontsize=7.1, color=theme.INK_PRIMARY)
        else:
            ax.set_yscale("linear")
            ax.set_ylim(0.0, max(115.0, max_u * 1.22))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(round(v)):,}%" if v >= 1 else "0%"))

    # ----------------------------------------------------------------------- perfil longitudinal
    def _resolve_route(self) -> List[PipeEdge]:
        ov = tuple(e.pipe_id for e in self._route_override) if self._route_override else None
        key = (id(self._graph), self._focus_pipe, self._focus_node, ov)
        if key == self._route_key:
            return self._route
        route: List[PipeEdge] = []
        g = self._graph
        if ov:
            route = list(self._route_override)
        elif g is not None:
            if self._focus_pipe:
                route = build_route_to_sink(g, pipe_id=self._focus_pipe)
            if not route and self._focus_node:
                route = build_route_to_sink(g, node_id=self._focus_node)
            if not route:
                route = build_route_to_sink(g, pipe_id="P31")
        self._route, self._route_key = route, key
        return route

    @staticmethod
    def _bottleneck_note(route: List[PipeEdge], fill: List[float], dem: List[float], diams: List[float], qmax: List[float]) -> str:
        """Nota de cuello de botella: primer tramo con demanda > 105 % y tramos aguas abajo holgados."""
        choked = next((i for i, d in enumerate(dem) if d > 105.0), None)
        if choked is None:
            return ""
        low = [route[j] for j in range(choked + 1, len(route)) if fill[j] < 92.0 and qmax[j] > 1e-12]
        if not low:
            return ""
        names = ", ".join(p.pipe_id for p in low[:3])
        return (f"Cuello de botella en {route[choked].pipe_id} ({diams[choked]:.0f}\"): rebosa exceso; "
                f"{names} reciben caudal estrangulado.")

    def _redraw_profile(self) -> None:
        """Perfil longitudinal ruta → PTAR en el paso actual (Qmax vs Q(t) coloreado por utilización)."""
        if self._profile_after_id is not None:
            try:
                self.after_cancel(self._profile_after_id)
            except tk.TclError:
                pass
            self._profile_after_id = None
        self._profile_dirty = False
        self._cursor_dirty = False
        self._last_profile_draw = time.monotonic()
        ax = self.ax_profile
        ax.clear()
        _style_axis(ax)
        res = self._result
        route = self._resolve_route() if res is not None and res.snapshots else []
        if res is None or not res.snapshots or not route:
            ax.set_xticks([])
            ax.set_yticks([])
            ax.text(0.5, 0.5, "Sin ruta disponible hacia PTAR 31.\nEjecute la simulación o seleccione una tubería.",
                    ha="center", va="center", color=theme.INK_MUTED, fontsize=8.0, transform=ax.transAxes)
            self._set_note("")
            self.profile_canvas.draw_idle()
            return
        step = max(0, min(len(res.snapshots) - 1, self._step_index))
        snap = res.snapshots[step]
        prev_snap = (self._prev.snapshots[min(step, len(self._prev.snapshots) - 1)] if self._has_prev() else None)
        ivs = self._interventions()
        xs = list(range(len(route)))
        q_live, q_dem, q_max, fill, dem, colors, diams, closed, labels = ([] for _ in range(9))
        for pipe in route:
            ps = snap.pipe_states.get(pipe.pipe_id)
            eff = ps.effective_q_max_m3s if (ps is not None and ps.effective_q_max_m3s is not None) else pipe.q_max_m3s
            q = ps.flow_m3s if ps is not None else 0.0
            cl = bool(ps.is_closed) if ps is not None else eff <= 1e-12
            d = ps.utilization_pct if ps is not None else 0.0
            inv = ivs.get(pipe.pipe_id)
            diam = inv.diameter_in_override if (inv is not None and inv.diameter_in_override) else pipe.diameter_in
            q_live.append(q)
            q_dem.append(ps.demand_flow_m3s if ps is not None else q)
            q_max.append(eff)
            fill.append(q / eff * 100.0 if (not cl and eff > 1e-12) else 0.0)
            dem.append(d)
            colors.append(theme.INK_MUTED if cl else classify_utilization(d).color_hex)
            diams.append(diam)
            closed.append(cl)
            tag = "*" if pipe.pipe_id in ivs else ""
            labels.append(f"{pipe.pipe_id}{tag}\n{pipe.from_node}→{pipe.to_node}" if len(route) <= 6 else f"{pipe.pipe_id}{tag}")
        fs = 6.0 if len(route) >= 9 else (6.5 if len(route) >= 7 else 7.1)
        legend: List[Any] = []

        def anno(i: int) -> str:
            if closed[i]:
                return "CERRADA"
            if dem[i] > 100.5:
                return f"Dem. {dem[i] / 100.0:.1f}×"
            return f"{fill[i]:.0f}%"

        if self._profile_mode == "pct":
            bars = [0.0 if c else min(100.0, f) for f, c in zip(fill, closed)]
            ax.bar(xs, bars, width=0.6, color=colors, edgecolor=theme.INK_PRIMARY, linewidth=0.8, zorder=3)
            top, overflow = 115.0, False
            for i, pipe in enumerate(route):
                y, tcol = bars[i] + 3.0, theme.INK_PRIMARY
                if closed[i]:
                    ax.bar([i], [28.0], width=0.6, facecolor="#E5E7EB", edgecolor="#374151", hatch="xxx", linewidth=1.1, zorder=3.5)
                    y, tcol = 31.0, "#374151"
                elif dem[i] > 100.5:
                    overflow = True
                    ext = min(62.0, 16.0 + 18.0 * math.log10(max(1.0, dem[i] / 100.0)))
                    ax.bar([i], [ext], bottom=[100.0], width=0.6, facecolor="#FEE2E2", edgecolor="#991B1B", hatch="///", linewidth=1.1, zorder=3.5)
                    y, tcol = 100.0 + ext + 3.0, "#991B1B"
                    top = max(top, y + 27.0)
                ax.text(i, y, ("MOD\n" if pipe.pipe_id in ivs else "") + anno(i), ha="center", va="bottom", fontsize=fs, color=tcol, zorder=6,
                        fontweight="bold" if (dem[i] > 100.5 or pipe.pipe_id in ivs or pipe.pipe_id == self._focus_pipe) else "normal")
            if prev_snap is not None:
                ys = []
                for pipe in route:
                    pps = prev_snap.pipe_states.get(pipe.pipe_id)
                    pu = pps.utilization_pct if pps is not None else 0.0
                    ys.append(100.0 + min(62.0, 16.0 + 18.0 * math.log10(max(1.0, pu / 100.0))) if pu > 100.5 else pu)
                ax.scatter(xs, ys, marker="_", s=170, linewidths=2.0, color=_AFTER_COLOR, zorder=5)
            ax.axhspan(0.0, 75.0, color="#22c55e", alpha=0.05, zorder=0)
            ax.axhspan(75.0, 100.0, color="#f97316", alpha=0.08, zorder=0)
            ax.axhline(75.0, color="#F97316", ls=":", lw=1.0, zorder=2)
            ax.axhline(100.0, color="#DC2626", ls="--", lw=1.4, zorder=4)
            ax.set_ylim(0.0, max(top, 178.0 if overflow else 118.0))
            ticks, tl = [0, 25, 50, 75, 100], ["0%", "25%", "50%", "75%", "100%\nQmax"]
            if overflow:
                ticks, tl = ticks + [138], tl + ["Rebose\n>100%"]
            ax.set_yticks(ticks)
            ax.set_yticklabels(tl)
            ax.set_ylabel("% Uso vs. Qmax", fontsize=7.5, color=theme.INK_PRIMARY)
            legend = [Patch(facecolor=theme.ACCENT_PRIMARY, edgecolor=theme.INK_PRIMARY, label="Llenado (≤100%)"),
                      Line2D([0], [0], color="#DC2626", ls="--", lw=1.4, label="Cap. 100%")]
            if overflow:
                legend.append(Patch(facecolor="#FEE2E2", edgecolor="#991B1B", hatch="///", label="Exceso/Rebose"))
        else:
            ax.bar(xs, q_live, width=0.62, color=colors, zorder=3)
            ax.bar(xs, q_max, width=0.7, facecolor="none", edgecolor=theme.INK_PRIMARY, linewidth=1.6, zorder=4)
            if prev_snap is not None:
                pq = [prev_snap.pipe_states[p.pipe_id].flow_m3s if p.pipe_id in prev_snap.pipe_states else 0.0 for p in route]
                ax.scatter(xs, pq, marker="_", s=160, linewidths=2.0, color=_AFTER_COLOR, zorder=5)
            top_y = max(q_live + q_max + [0.05])
            ax.set_ylim(0.0, top_y * 1.4)
            for i, pipe in enumerate(route):
                sel = pipe.pipe_id == self._focus_pipe
                ax.text(i, max(q_live[i], q_max[i]) + top_y * 0.025, f"{diams[i]:.0f}\"\n{anno(i)}", ha="center", va="bottom", fontsize=fs,
                        fontweight="bold" if (sel or dem[i] > 100.5) else "normal",
                        color=theme.ACCENT_TEXT if sel else theme.INK_PRIMARY)
            ax.set_ylabel("Caudal (m³/s)", fontsize=7.6, color=theme.INK_PRIMARY)
            legend = [Patch(facecolor="none", edgecolor=theme.INK_PRIMARY, linewidth=1.6, label="Capacidad Qmax"),
                      Patch(facecolor=theme.ACCENT_PRIMARY, edgecolor="none", label="Q(t)")]
        if prev_snap is not None:
            legend.append(Line2D([0], [0], color=_AFTER_COLOR, marker="_", ls="None", markersize=9, markeredgewidth=2.0, label="Antes"))
        self._set_note(self._bottleneck_note(route, fill, dem, diams, q_max))
        ax.set_xticks(xs)
        ax.set_xticklabels(labels, fontsize=6.5 if len(route) > 6 else 7.1, rotation=28 if len(route) > 5 else 0,
                           ha="right" if len(route) > 5 else "center")
        ax.set_title(f"Perfil ({route[0].from_node} → {route[-1].to_node}) · t={snap.time_min:.0f} min",
                     fontsize=8.6, fontweight="bold", color=theme.INK_PRIMARY, loc="left", pad=4)
        ax.legend(handles=legend, loc="upper left", ncol=min(3, len(legend)), fontsize=6.2, **_LEGEND_KW)
        self.profile_canvas.draw_idle()

    def _set_note(self, text: str) -> None:
        if text:
            self._lbl_note.configure(text=text)
            if not self._note_visible:
                self._lbl_note.pack(side=tk.TOP, fill=tk.X, before=self._prof_wrap, padx=4, pady=(4, 0))
                self._note_visible = True
        elif self._note_visible:
            self._lbl_note.pack_forget()
            self._note_visible = False


# --------------------------------------------------------------------------- gráficas de comparación
class ComparisonChartsPanel(tk.Frame):
    """Barras Críticas vs Sobrecargadas + hidrogramas/rebose de los escenarios, con reflujo 2×1 / 1×2."""

    def __init__(self, parent: tk.Misc, fonts: Optional[Dict[str, Tuple[str, int, str]]] = None) -> None:
        super().__init__(parent, bg=theme.PAPER_BG)
        self._ui = (fonts or {}).get("body", ("TkDefaultFont", 9, "normal"))[0]
        self._metric_mode = "flood"   # 'flood' (Rebose acumulado) | 'ptar' (hidrogramas PTAR 31)
        self._layout_mode = "stacked"  # 'stacked' (2×1) | 'side' (1×2)
        self._summaries: List[ScenarioSummary] = []
        self._resize_after: Optional[str] = None

        mbar = tk.Frame(self, bg=theme.PAPER_SUBTLE)
        mbar.pack(side=tk.TOP, fill=tk.X)
        tk.Frame(self, bg=theme.PAPER_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)
        tk.Label(mbar, text="Serie 2:", bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED, font=(self._ui, 7, "bold")).pack(side=tk.LEFT, padx=(6, 4), pady=3)
        self._btn_flood = _tab_button(mbar, "Rebose (m³)", lambda: self.set_metric_mode("flood"), (self._ui, 7, "bold"), 7, 2)
        self._btn_ptar = _tab_button(mbar, "PTAR 31 (m³/s)", lambda: self.set_metric_mode("ptar"), (self._ui, 7, "normal"), 7, 2)
        self._btn_flood.pack(side=tk.LEFT, padx=2, pady=3)
        self._btn_ptar.pack(side=tk.LEFT, padx=2, pady=3)
        self._style_buttons()

        wrap = tk.Frame(self, bg=theme.PAPER_BG)
        wrap.pack(fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(4.4, 4.4), dpi=96, facecolor=theme.PAPER_BG, constrained_layout=True)
        self.ax_bar = self.fig.add_subplot(211)
        self.ax_series = self.fig.add_subplot(212)
        self.canvas = FigureCanvasTkAgg(self.fig, master=wrap)
        self.canvas.get_tk_widget().configure(bg=theme.PAPER_BG, highlightthickness=0, bd=0, width=320, height=300)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        _lock_tkagg_dpi(self.canvas, wrap)
        self.bind("<Configure>", self._on_resize)
        self.bind("<Destroy>", self._on_destroy)
        self._draw_empty()

    @property
    def metric_mode(self) -> str:
        return self._metric_mode

    @property
    def layout_mode(self) -> str:
        return self._layout_mode

    def _style_buttons(self) -> None:
        fl = self._metric_mode == "flood"
        for btn, on in ((self._btn_flood, fl), (self._btn_ptar, not fl)):
            btn.configure(bg=theme.ACCENT_PRIMARY if on else theme.PAPER_BG, fg=theme.ACCENT_INK if on else theme.INK_PRIMARY,
                          font=(self._ui, 7, "bold" if on else "normal"))

    def set_metric_mode(self, mode: str) -> None:
        """Serie inferior: `flood` (rebose acumulado) o `ptar` (hidrograma PTAR 31)."""
        if mode not in ("flood", "ptar") or mode == self._metric_mode:
            return
        self._metric_mode = mode
        self._style_buttons()
        if self._summaries:
            self.update_comparison(self._summaries)

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self and self._resize_after is not None:
            try:
                self.after_cancel(self._resize_after)
            except tk.TclError:
                pass
            self._resize_after = None

    def _on_resize(self, event: tk.Event) -> None:
        if event.width < _MIN_PX or event.height < _MIN_PX:
            return
        if self._resize_after is not None:
            try:
                self.after_cancel(self._resize_after)
            except tk.TclError:
                pass
        self._resize_after = self.after(100, self._reflow)

    @staticmethod
    def layout_for(width: int, height: int) -> str:
        """Vertical 2×1 si el alto es >= 0.86 × ancho; horizontal 1×2 en caso contrario."""
        return "stacked" if height >= width * 0.86 else "side"

    def _reflow(self, width: Optional[int] = None, height: Optional[int] = None) -> None:
        self._resize_after = None
        w = width if width is not None else max(1, self.winfo_width())
        h = height if height is not None else max(1, self.winfo_height())
        if w < _MIN_PX or h < _MIN_PX:
            return
        _sync_figure_to_widget(self.canvas, self.fig)
        new_mode = self.layout_for(w, h)
        if new_mode != self._layout_mode:
            self._layout_mode = new_mode
            if self._summaries:
                self.update_comparison(self._summaries)
                return
            self._draw_empty()
            return
        self.canvas.draw_idle()

    def _rebuild_axes(self) -> None:
        self.fig.clear()
        side = self._layout_mode == "side"
        self.ax_bar = self.fig.add_subplot(121 if side else 211)
        self.ax_series = self.fig.add_subplot(122 if side else 212)

    def _draw_empty(self) -> None:
        self._rebuild_axes()
        for ax in (self.ax_bar, self.ax_series):
            _style_axis(ax)
            ax.text(0.5, 0.5, "Presione «Recalcular 5 Escenarios»\npara generar la comparativa.", ha="center", va="center",
                    color=theme.INK_MUTED, fontsize=8.0, transform=ax.transAxes)
            ax.set_xticks([])
            ax.set_yticks([])
        self.canvas.draw_idle()

    def update_comparison(self, summaries: Optional[List[ScenarioSummary]]) -> None:
        """Dibuja barras agrupadas (críticas vs sobrecargadas) y la serie temporal seleccionada."""
        self._summaries = list(summaries or [])
        if not self._summaries:
            self._draw_empty()
            return
        _sync_figure_to_widget(self.canvas, self.fig)
        self._rebuild_axes()
        sm = self._summaries
        labels = [f"E{s.scenario_id}" for s in sm]
        x = list(range(len(sm)))
        near, over = [s.num_near_capacity_pipes for s in sm], [s.num_overloaded_pipes for s in sm]
        max_c = max(near + over + [4])
        ax = self.ax_bar
        _style_axis(ax, "Tuberías críticas y sobrecargadas", "Tuberías")
        w = 0.36
        b1 = ax.bar([i - w / 2 for i in x], near, width=w, color="#ef4444", edgecolor=theme.INK_PRIMARY, lw=0.5, label="Críticas (>75–100%)")
        b2 = ax.bar([i + w / 2 for i in x], over, width=w, color="#991b1b", edgecolor=theme.INK_PRIMARY, lw=0.5, label="Sobrec. (>100%)")
        for rect in list(b1) + list(b2):
            v = int(round(rect.get_height()))
            ax.text(rect.get_x() + rect.get_width() / 2.0, rect.get_height() + max_c * 0.03, str(v), ha="center", va="bottom",
                    fontsize=6.5, fontweight="bold" if v else "normal", color=theme.INK_PRIMARY)
        ax.set_ylim(0, max_c * 1.5)
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=7.0)
        ax.legend(loc="upper center", ncol=2, fontsize=6.0, **_LEGEND_KW)

        colors = ["#6B7280", "#0284C7", "#CA8A04", "#EA580C", "#DC2626"]
        styles = ["-", "--", "-.", ":", "-"]
        ax2 = self.ax_series
        if self._metric_mode == "flood":
            _style_axis(ax2, "Rebose superficial acumulado (m³)", "Rebose (m³)")
            max_f = 100.0
            for i, s in enumerate(sm):
                ts = [sn.time_min for sn in s.result.snapshots]
                fs = [sn.total_surface_flooding_m3 for sn in s.result.snapshots]
                max_f = max(max_f, max(fs, default=0.0))
                ax2.plot(ts, fs, color=colors[i % 5], ls=styles[i % 5], lw=1.6 + 0.15 * (i % 5),
                         label=f"E{s.scenario_id}: {_fmt_vol_compact(fs[-1] if fs else 0.0)}")
            ax2.set_ylim(0.0, max_f * 1.24)
            ax2.yaxis.set_major_formatter(FuncFormatter(lambda v, _: _fmt_vol_compact(v)))
        else:
            _style_axis(ax2, "Hidrograma PTAR 31 (m³/s)", "m³/s")
            max_q = 0.01
            for i, s in enumerate(sm):
                ts = [sn.time_min for sn in s.result.snapshots]
                qs = [sn.total_sink_discharge_m3s for sn in s.result.snapshots]
                max_q = max(max_q, max(qs, default=0.0))
                ax2.plot(ts, qs, color=colors[i % 5], ls=styles[i % 5], lw=1.6 + 0.15 * (i % 5),
                         label=f"E{s.scenario_id} {theme.translate_scenario_name(s.condition, short=True)}")
            ax2.set_ylim(0.0, max_q * 1.42)
        ax2.set_xlabel("Tiempo (min)", fontsize=7.2, color=theme.INK_PRIMARY)
        ax2.legend(loc="upper left", fontsize=5.9, ncol=2, **_LEGEND_KW)
        self.canvas.draw_idle()
