"""Paneles de gráficas Matplotlib sobre FigureCanvasQTAgg (PySide6)."""

import math
import os
import time
import warnings
from typing import Dict, List, Optional, Tuple

os.environ.setdefault("QT_API", "pyside6")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QStackedWidget, QVBoxLayout, QWidget

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from matplotlib.ticker import FuncFormatter

from src.data_structures import PipeEdge
from src.simulation.comparison import ScenarioSummary
from src.simulation.models import PipeIntervention, SimulationResult, compute_symlog_ticks
from .. import theme
from ..widgets import LoadingOverlay, SegmentedControl, make_separator


def _apply_axis_style(ax) -> None:
    ax.set_facecolor(theme.PAPER_ALT_ROW)
    ax.tick_params(colors=theme.INK_PRIMARY, labelsize=7.5)
    for spine in ax.spines.values():
        spine.set_color(theme.INK_PRIMARY)
        spine.set_linewidth(0.85)
    ax.grid(True, linestyle="--", alpha=0.70, color=theme.PAPER_BORDER)


def _safe_tight_layout(fig: Figure, canvas: FigureCanvasQTAgg) -> None:
    """Aplica tight_layout adaptándose al tamaño real del lienzo Qt sin recortes."""
    w = canvas.width()
    h = canvas.height()
    if (w > 1 and w < 180) or (h > 1 and h < 180):
        return
    w_px = fig.get_figwidth() * fig.dpi
    h_px = fig.get_figheight() * fig.dpi
    if w_px < 180 or h_px < 180:
        return
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        try:
            fig.tight_layout(pad=0.85, h_pad=1.05, w_pad=0.65)
            has_warn = any("Tight layout not applied" in str(w_item.message) for w_item in caught)
        except Exception:
            has_warn = True
    if has_warn:
        try:
            fig.subplots_adjust(
                left=0.16, right=0.96, top=0.91, bottom=0.14, hspace=0.46, wspace=0.28
            )
        except Exception:
            pass


def _sync_figure_size(canvas: FigureCanvasQTAgg, fig: Figure) -> None:
    w = canvas.width()
    h = canvas.height()
    if w < 180 or h < 180:
        return
    dpr = float(canvas.devicePixelRatioF()) if hasattr(canvas, "devicePixelRatioF") else 1.0
    dpival = float(fig.dpi)
    if dpival > 0.0:
        target_w = (w * dpr) / dpival
        target_h = (h * dpr) / dpival
        cur_w, cur_h = fig.get_size_inches()
        if abs(cur_w - target_w) > 0.02 or abs(cur_h - target_h) > 0.02:
            fig.set_size_inches(target_w, target_h, forward=False)


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
    interventions: Dict[str, PipeIntervention],
    diameter_overrides: Dict[str, float],
) -> str:
    if not interventions:
        return "Comparación: Antes (Base) vs. Después (Actual)"
    if len(interventions) == 1:
        pid, inv = next(iter(interventions.items()))
        parts = []
        if inv.diameter_in_override is not None:
            parts.append(f'Ø {inv.diameter_in_override:.0f}"')
        elif pid in diameter_overrides:
            parts.append(f'Ø {diameter_overrides[pid]:.0f}"')
        if inv.obstruction_pct > 1e-6:
            parts.append(f"Obstr. {inv.obstruction_pct:.0f}%")
        detail = " · ".join(parts) if parts else "Modificada"
        return f"Intervención: {pid} ({detail})"
    pids = ", ".join(sorted(interventions.keys())[:4])
    extra = f" (+{len(interventions) - 4})" if len(interventions) > 4 else ""
    return f"{len(interventions)} intervenciones activas: {pids}{extra}"


class TemporalChartsPanel(QWidget):
    """Gráfica temporal (hidrograma Antes vs. Después + % uso) y perfil longitudinal."""

    def __init__(
        self,
        dpi: int = 96,
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._dpi = max(72, int(dpi))
        self._ui_font = ui_font
        self._mono_font = mono_font
        self._subtab: str = "hydro"
        self._profile_mode: str = "pct"
        self._banner_visible: bool = False
        self._prof_note_visible: bool = False

        self.setObjectName("ChartsHost")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # Barra superior de subpestañas
        subbar = QFrame(self)
        subbar.setObjectName("DockSubBar")
        sb_lay = QHBoxLayout(subbar)
        sb_lay.setContentsMargins(6, 4, 6, 4)
        self._seg_subtabs = SegmentedControl(
            [("hydro", "Hidrograma y %"), ("profile", "Perfil (Uso vs Cap.)")],
            initial_key="hydro",
            inactive_variant="light_secondary",
            font_pt=8,
            pad_x=10,
            pad_y=4,
            spacing=6,
            framed=False,
            parent=subbar,
        )
        self._seg_subtabs.selectionChanged.connect(self.set_subtab)
        sb_lay.addWidget(self._seg_subtabs)
        sb_lay.addStretch(1)
        lay.addWidget(subbar)
        lay.addWidget(make_separator("h", theme.DOCK_BORDER, 1, self))

        # Banner de impacto Antes vs. Después
        self._impact_banner = QFrame(self)
        self._impact_banner.setObjectName("ImpactBanner")
        ib_lay = QHBoxLayout(self._impact_banner)
        ib_lay.setContentsMargins(0, 0, 6, 0)
        ib_lay.setSpacing(6)
        stripe = QFrame(self._impact_banner)
        stripe.setObjectName("ImpactStripe")
        stripe.setFixedWidth(4)
        ib_lay.addWidget(stripe)

        ib_body = QVBoxLayout()
        ib_body.setContentsMargins(0, 4, 0, 4)
        ib_body.setSpacing(1)
        self._lbl_impact_title = QLabel("", self._impact_banner)
        self._lbl_impact_title.setFont(QFont(ui_font, 8, QFont.Weight.Bold))
        self._lbl_impact_title.setStyleSheet("color: #1E3A8A; background: transparent;")
        self._lbl_impact_metrics = QLabel("", self._impact_banner)
        self._lbl_impact_metrics.setWordWrap(True)
        self._lbl_impact_metrics.setFont(QFont(mono_font, 7))
        self._lbl_impact_metrics.setStyleSheet(f"color: {theme.INK_PRIMARY}; background: transparent;")
        ib_body.addWidget(self._lbl_impact_title)
        ib_body.addWidget(self._lbl_impact_metrics)
        ib_lay.addLayout(ib_body, 1)

        banner_wrap = QWidget(self)
        bw_lay = QVBoxLayout(banner_wrap)
        bw_lay.setContentsMargins(4, 4, 4, 0)
        bw_lay.addWidget(self._impact_banner)
        self._impact_banner_wrap = banner_wrap
        self._impact_banner_wrap.setVisible(False)
        lay.addWidget(self._impact_banner_wrap)

        # Stack de subvistas
        self._stack = QStackedWidget(self)

        # Subvista 1: Hidrograma + Utilización temporal
        self._hydro_frame = QWidget(self._stack)
        hydro_lay = QVBoxLayout(self._hydro_frame)
        hydro_lay.setContentsMargins(0, 0, 0, 0)
        self.figure = Figure(figsize=(4.0, 5.2), dpi=self._dpi, facecolor=theme.PAPER_BG)
        self.ax_flow = self.figure.add_subplot(211)
        self.ax_util = self.figure.add_subplot(212)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.setMinimumSize(220, 220)
        hydro_lay.addWidget(self.canvas)
        self._stack.addWidget(self._hydro_frame)

        # Subvista 2: Perfil longitudinal
        self._profile_frame = QWidget(self._stack)
        prof_lay = QVBoxLayout(self._profile_frame)
        prof_lay.setContentsMargins(0, 0, 0, 0)
        prof_lay.setSpacing(0)

        prof_bar = QFrame(self._profile_frame)
        prof_bar.setObjectName("SubBar")
        pb_lay = QHBoxLayout(prof_bar)
        pb_lay.setContentsMargins(6, 3, 6, 3)
        pb_lay.setSpacing(4)

        lbl_vista = QLabel("Vista:", prof_bar)
        lbl_vista.setFont(QFont(ui_font, 7, QFont.Weight.Bold))
        lbl_vista.setStyleSheet(f"color: {theme.INK_MUTED}; background: transparent;")
        pb_lay.addWidget(lbl_vista)

        self._seg_profile_mode = SegmentedControl(
            [("pct", "% Uso vs Cap. (100%)"), ("flow", "Caudal (m³/s)")],
            initial_key="pct",
            inactive_variant="light_secondary",
            font_pt=7,
            pad_x=7,
            pad_y=2,
            spacing=4,
            framed=False,
            parent=prof_bar,
        )
        self._seg_profile_mode.selectionChanged.connect(self.set_profile_mode)
        pb_lay.addWidget(self._seg_profile_mode)
        pb_lay.addStretch(1)
        prof_lay.addWidget(prof_bar)
        prof_lay.addWidget(make_separator("h", theme.PAPER_BORDER, 1, self._profile_frame))

        self._lbl_prof_note = QLabel("", self._profile_frame)
        self._lbl_prof_note.setWordWrap(True)
        self._lbl_prof_note.setFont(QFont(ui_font, 7))
        self._lbl_prof_note.setStyleSheet(
            "background-color: #FEF2F2; color: #7F1D1D; "
            "border: 1px solid #FCA5A5; padding: 3px 6px; margin: 4px 4px 0 4px;"
        )
        self._lbl_prof_note.setVisible(False)
        prof_lay.addWidget(self._lbl_prof_note)

        self.profile_figure = Figure(figsize=(4.0, 5.2), dpi=self._dpi, facecolor=theme.PAPER_BG)
        self.ax_profile = self.profile_figure.add_subplot(111)
        self.profile_canvas = FigureCanvasQTAgg(self.profile_figure)
        self.profile_canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.profile_canvas.setMinimumSize(220, 220)
        prof_lay.addWidget(self.profile_canvas, 1)
        self._stack.addWidget(self._profile_frame)

        lay.addWidget(self._stack, 1)
        self.loading_overlay = LoadingOverlay(self._stack, ui_font=ui_font)

        self._cached_key: Optional[tuple] = None
        self._last_hydro_size: Tuple[int, int] = (0, 0)
        self._last_profile_size: Tuple[int, int] = (0, 0)
        self._has_drawn_hydro: bool = False
        self._has_drawn_profile: bool = False
        self._ax_flow_ptar = None
        self._cursor_flow: Optional[Line2D] = None
        self._cursor_util: Optional[Line2D] = None
        self._blit_bg = None
        self._last_draw_ts: float = 0.0
        self.canvas.mpl_connect("draw_event", self._on_mpl_draw)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(120)
        self._resize_timer.timeout.connect(self._refit_layout)

        self._last_result: Optional[SimulationResult] = None
        self._last_prev_result: Optional[SimulationResult] = None
        self._last_pipe_id: Optional[str] = None
        self._last_time_min: Optional[float] = None
        self._last_route_pipes: List[PipeEdge] = []
        self._last_step_idx: int = 0
        self._last_diam_overrides: Dict[str, float] = {}
        self._last_interventions: Dict[str, PipeIntervention] = {}

        _apply_axis_style(self.ax_flow)
        _apply_axis_style(self.ax_util)
        _apply_axis_style(self.ax_profile)

    def set_loading(self, active: bool, message: str = "Generando gráficas...") -> None:
        self.loading_overlay.set_active(active, message)

    def stop_timers(self) -> None:
        self.loading_overlay.stop()
        if self._resize_timer.isActive():
            self._resize_timer.stop()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.width() >= 160 and self.height() >= 160:
            self._resize_timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._refit_layout)

    def _on_mpl_draw(self, _event) -> None:
        try:
            self._blit_bg = self.canvas.copy_from_bbox(self.figure.bbox)
            if self._cursor_flow is not None:
                self.ax_flow.draw_artist(self._cursor_flow)
            if self._cursor_util is not None:
                self.ax_util.draw_artist(self._cursor_util)
        except Exception:
            self._blit_bg = None

    def _refit_layout(self) -> None:
        self._blit_bg = None
        if self._subtab == "profile":
            cw, ch = self.profile_canvas.width(), self.profile_canvas.height()
            lw, lh = self._last_profile_size
            if self._has_drawn_profile and abs(cw - lw) <= 8 and abs(ch - lh) <= 8:
                return
            self._last_profile_size = (cw, ch)
            self._has_drawn_profile = True
            _sync_figure_size(self.profile_canvas, self.profile_figure)
            _safe_tight_layout(self.profile_figure, self.profile_canvas)
            self.profile_canvas.draw_idle()
        else:
            cw, ch = self.canvas.width(), self.canvas.height()
            lw, lh = self._last_hydro_size
            if self._has_drawn_hydro and abs(cw - lw) <= 8 and abs(ch - lh) <= 8:
                return
            self._last_hydro_size = (cw, ch)
            self._has_drawn_hydro = True
            _sync_figure_size(self.canvas, self.figure)
            _safe_tight_layout(self.figure, self.canvas)
            self.canvas.draw_idle()

    def set_profile_mode(self, mode: str) -> None:
        if mode not in ("pct", "flow") or mode == self._profile_mode:
            return
        self._profile_mode = mode
        self._seg_profile_mode.set_current(mode)
        if self._subtab == "profile":
            self._redraw_profile()

    def set_subtab(self, tab_id: str) -> None:
        if tab_id not in ("hydro", "profile"):
            return
        self._subtab = tab_id
        self._seg_subtabs.set_current(tab_id)
        if tab_id == "profile":
            self._stack.setCurrentWidget(self._profile_frame)
            self._redraw_profile()
        else:
            self._stack.setCurrentWidget(self._hydro_frame)
            _sync_figure_size(self.canvas, self.figure)
            _safe_tight_layout(self.figure, self.canvas)
            self.canvas.draw_idle()

    def _resolve_focus_pipes(
        self,
        result: SimulationResult,
        previous_result: Optional[SimulationResult],
        selected_pipe_id: Optional[str],
        interventions: Dict[str, PipeIntervention],
    ) -> List[str]:
        if selected_pipe_id and selected_pipe_id in result.peak_pipe_utilization:
            return [selected_pipe_id]
        if previous_result is not None and previous_result is not result and interventions:
            cand = [pid for pid in interventions if pid in result.peak_pipe_utilization]
            if cand:
                cand.sort(
                    key=lambda pid: (
                        abs(
                            result.peak_pipe_utilization.get(pid, 0.0)
                            - previous_result.peak_pipe_utilization.get(pid, 0.0)
                        ),
                        result.peak_pipe_utilization.get(pid, 0.0),
                    ),
                    reverse=True,
                )
                return [cand[0]]
        sorted_p = sorted(
            result.peak_pipe_utilization.items(),
            key=lambda kv: (kv[1], result.peak_pipe_demand_ratio.get(kv[0], 0.0)),
            reverse=True,
        )
        return [pid for pid, _ in sorted_p[:3]]

    def _sync_impact_banner(
        self,
        has_prev: bool,
        result: Optional[SimulationResult],
        previous_result: Optional[SimulationResult],
        focus_pid: Optional[str],
        interventions: Dict[str, PipeIntervention],
        diameter_overrides: Dict[str, float],
    ) -> None:
        if not has_prev or result is None or previous_result is None:
            if self._banner_visible:
                self._impact_banner_wrap.setVisible(False)
                self._banner_visible = False
            return

        title_txt = _format_intervention_summary(interventions, diameter_overrides)
        prev_ptar = previous_result.peak_sink_discharge_m3s
        cur_ptar = result.peak_sink_discharge_m3s
        ptar_delta_pct = (
            ((cur_ptar - prev_ptar) / prev_ptar) * 100.0 if prev_ptar > 1e-6 else 0.0
        )
        parts = [f"PTAR: {prev_ptar:.2f}→{cur_ptar:.2f} m³/s ({ptar_delta_pct:+.0f}%)"]
        if focus_pid:
            prev_u = previous_result.peak_pipe_utilization.get(focus_pid, 0.0)
            cur_u = result.peak_pipe_utilization.get(focus_pid, 0.0)
            parts.append(f"Uso {focus_pid}: {_fmt_pct_compact(prev_u)}→{_fmt_pct_compact(cur_u)}")
        d_flood = result.total_surface_flooding_m3 - previous_result.total_surface_flooding_m3
        if abs(d_flood) >= 1.0:
            parts.append(f"Rebose: {d_flood:+,.0f} m³")
        else:
            parts.append(f"Rebose: {result.total_surface_flooding_m3:,.0f} m³")

        self._lbl_impact_title.setText(title_txt)
        self._lbl_impact_metrics.setText(" · ".join(parts))

        if not self._banner_visible:
            self._impact_banner_wrap.setVisible(True)
            self._banner_visible = True

    def _configure_util_axis(
        self, ax, max_u_val: float, cap_pct: Optional[float] = None
    ) -> None:
        ax.axhspan(0.0, 75.0, color="#22c55e", alpha=0.06, zorder=0)
        ax.axhspan(75.0, 100.0, color="#f97316", alpha=0.09, zorder=0)
        top_ref = max(max_u_val, cap_pct or 100.0)
        if top_ref > 100.0:
            ax.axhspan(100.0, top_ref * 1.45, color="#dc2626", alpha=0.04, zorder=0)

        ax.axhline(75.0, color="#f97316", linestyle=":", linewidth=1.0, label="Crít. 75%", zorder=2)
        ax.axhline(100.0, color="#dc2626", linestyle="--", linewidth=1.25, label="Cap. 100%", zorder=2)
        if cap_pct is not None:
            ax.axhline(
                cap_pct,
                color="#7F1D1D",
                linestyle="-.",
                linewidth=1.25,
                label=f"Tope rebose {cap_pct:.0f}%",
                zorder=2.5,
            )

        if max_u_val > 250.0:
            ax.set_yscale("symlog", linthresh=100.0, linscale=0.85)
            ax.set_ylim(0.0, max_u_val * 2.15)
            ax.set_yticks(compute_symlog_ticks(max_u_val))
            ax.minorticks_off()
        else:
            ax.set_yscale("linear")
            ax.set_ylim(0.0, max(115.0, (cap_pct or 100.0) * 1.15, max_u_val * 1.22))

        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda v, _: f"{int(round(v)):,}%" if v >= 1 else "0%")
        )

    def update_plots(
        self,
        result: Optional[SimulationResult],
        selected_pipe_id: Optional[str] = None,
        current_time_min: Optional[float] = None,
        previous_result: Optional[SimulationResult] = None,
        route_pipes: Optional[List[PipeEdge]] = None,
        current_step_index: int = 0,
        diameter_overrides: Optional[Dict[str, float]] = None,
        interventions: Optional[Dict[str, PipeIntervention]] = None,
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
        self._last_interventions = dict(interventions or {})

        has_prev = (
            result is not None
            and previous_result is not None
            and previous_result is not result
            and bool(previous_result.snapshots)
            and bool(result.snapshots)
        )
        target_pids = (
            self._resolve_focus_pipes(
                result, previous_result, selected_pipe_id, self._last_interventions
            )
            if result is not None
            else []
        )
        focus_pid = target_pids[0] if target_pids else None
        self._sync_impact_banner(
            has_prev,
            result,
            previous_result,
            focus_pid,
            self._last_interventions,
            self._last_diam_overrides,
        )

        now = time.perf_counter()
        if self._subtab == "profile":
            if not throttle_draw or (now - self._last_draw_ts) >= 0.14:
                self._last_draw_ts = now
                self._redraw_profile()

        prev_id = id(previous_result) if has_prev else 0
        int_sig = tuple(sorted(self._last_interventions.keys()))
        cache_key = (
            (id(result), prev_id, focus_pid if has_prev else selected_pipe_id, int_sig)
            if result is not None
            else None
        )
        if cache_key is not None and cache_key == self._cached_key:
            if current_time_min is not None:
                if self._cursor_flow is not None:
                    self._cursor_flow.set_xdata([current_time_min, current_time_min])
                if self._cursor_util is not None:
                    self._cursor_util.set_xdata([current_time_min, current_time_min])
                if self._subtab == "hydro":
                    if self._blit_bg is not None:
                        try:
                            self.canvas.restore_region(self._blit_bg)
                            if self._cursor_flow is not None:
                                self.ax_flow.draw_artist(self._cursor_flow)
                            if self._cursor_util is not None:
                                self.ax_util.draw_artist(self._cursor_util)
                            self.canvas.blit(self.figure.bbox)
                            return
                        except Exception:
                            self._blit_bg = None
                    if not throttle_draw or (now - self._last_draw_ts) >= 0.14:
                        self._last_draw_ts = now
                        self.canvas.draw_idle()
            return

        self._cached_key = cache_key
        self._cursor_flow = None
        self._cursor_util = None
        self._blit_bg = None
        if self._ax_flow_ptar is not None:
            try:
                self._ax_flow_ptar.remove()
            except Exception:
                pass
            self._ax_flow_ptar = None

        self.ax_flow.clear()
        self.ax_util.clear()
        _apply_axis_style(self.ax_flow)
        _apply_axis_style(self.ax_util)

        if result is None or not result.snapshots:
            self.ax_flow.set_title("Sin simulación ejecutada", color=theme.INK_PRIMARY, fontsize=8.5)
            _sync_figure_size(self.canvas, self.figure)
            _safe_tight_layout(self.figure, self.canvas)
            self.canvas.draw_idle()
            return

        times = [s.time_min for s in result.snapshots]
        inflows = [s.total_source_inflow_m3s for s in result.snapshots]
        ptar_out = [s.total_sink_discharge_m3s for s in result.snapshots]
        flood_rates: List[float] = []
        for idx, s in enumerate(result.snapshots):
            if idx == 0:
                flood_rates.append(0.0)
            else:
                prev_s = result.snapshots[idx - 1]
                dt_sec = max((s.time_min - prev_s.time_min) * 60.0, 1e-6)
                dv_flood = max(0.0, s.total_surface_flooding_m3 - prev_s.total_surface_flooding_m3)
                flood_rates.append(dv_flood / dt_sec)
        has_flood = any(r > 1e-6 for r in flood_rates)
        t_cur = current_time_min if current_time_min is not None else times[0]

        if has_prev and previous_result is not None:
            prev_times = [s.time_min for s in previous_result.snapshots]
            prev_ptar = [s.total_sink_discharge_m3s for s in previous_result.snapshots]
            max_ptar_q = max(ptar_out + prev_ptar + [0.05])

            l_prev = self.ax_flow.plot(
                prev_times,
                prev_ptar,
                label="Antes (Original)",
                color="#6B7280",
                linestyle="--",
                linewidth=1.85,
                zorder=2,
            )[0]
            l_cur = self.ax_flow.plot(
                times,
                ptar_out,
                label="Después (Actual)",
                color="#1D4ED8",
                linewidth=2.35,
                zorder=4,
            )[0]
            legend_handles = [l_prev, l_cur]
            if len(prev_ptar) == len(ptar_out) and len(times) == len(prev_times):
                has_gain = any(c > p + 1e-5 for c, p in zip(ptar_out, prev_ptar))
                has_loss = any(c < p - 1e-5 for c, p in zip(ptar_out, prev_ptar))
                self.ax_flow.fill_between(
                    times,
                    prev_ptar,
                    ptar_out,
                    where=[c >= p for c, p in zip(ptar_out, prev_ptar)],
                    interpolate=True,
                    color="#16A34A",
                    alpha=0.16,
                    zorder=1,
                )
                self.ax_flow.fill_between(
                    times,
                    prev_ptar,
                    ptar_out,
                    where=[c < p for c, p in zip(ptar_out, prev_ptar)],
                    interpolate=True,
                    color="#DC2626",
                    alpha=0.16,
                    zorder=1,
                )
                if has_gain:
                    legend_handles.append(
                        Patch(facecolor="#16A34A", alpha=0.28, edgecolor="none", label="+ Flujo PTAR")
                    )
                if has_loss:
                    legend_handles.append(
                        Patch(facecolor="#DC2626", alpha=0.28, edgecolor="none", label="− Pérdida PTAR")
                    )

            peak_prev = max(prev_ptar, default=0.0)
            peak_cur = max(ptar_out, default=0.0)
            if peak_prev > 1e-6:
                i_prev = prev_ptar.index(peak_prev)
                self.ax_flow.annotate(
                    f"{peak_prev:.2f}",
                    xy=(prev_times[i_prev], peak_prev),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=6.5,
                    color="#4B5563",
                    fontweight="bold",
                )
            if peak_cur > 1e-6 and abs(peak_cur - peak_prev) > 0.01:
                i_cur = ptar_out.index(peak_cur)
                self.ax_flow.annotate(
                    f"{peak_cur:.2f}",
                    xy=(times[i_cur], peak_cur),
                    xytext=(0, -9 if peak_cur < peak_prev else 3),
                    textcoords="offset points",
                    ha="center",
                    va="top" if peak_cur < peak_prev else "bottom",
                    fontsize=6.5,
                    color="#1D4ED8",
                    fontweight="bold",
                )

            delta_str = ""
            if peak_prev > 1e-6:
                delta_pct = ((peak_cur - peak_prev) / peak_prev) * 100.0
                delta_str = f" ({delta_pct:+.0f}% pico)" if abs(delta_pct) >= 0.5 else " (sin cambio)"

            self.ax_flow.set_ylim(0.0, max_ptar_q * 1.28)
            self.ax_flow.set_ylabel("PTAR 31 (m³/s)", color=theme.INK_PRIMARY, fontsize=7.4)
            self.ax_flow.set_title(
                f"PTAR 31: Antes vs. Después{delta_str}",
                color=theme.INK_PRIMARY,
                fontsize=8.5,
                fontweight="bold",
                fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
                pad=24 if len(legend_handles) <= 2 else 30,
            )
            self.ax_flow.legend(
                handles=legend_handles,
                loc="lower center",
                bbox_to_anchor=(0.5, 1.01),
                ncol=2,
                frameon=True,
                facecolor=theme.PAPER_BG,
                edgecolor=theme.PAPER_BORDER,
                framealpha=0.95,
                fontsize=6.4,
                borderpad=0.22,
                columnspacing=0.75,
                handlelength=1.3,
                labelcolor=theme.INK_PRIMARY,
            )
        else:
            admitted = [s.admitted_inflow_m3s for s in result.snapshots]
            has_admission_cap = any(abs(a - i) > 1e-5 for a, i in zip(admitted, inflows))
            f_max = float(result.system_max_flow_m3s)
            max_left_q = max(inflows + (flood_rates if has_flood else []) + [0.05])
            max_ptar_q = max(ptar_out + (admitted if has_admission_cap else []) + [f_max, 0.05])
            use_split_scale = max_left_q > max_ptar_q * 5.0

            lines_all = []
            lines_all.extend(
                self.ax_flow.plot(
                    times,
                    inflows,
                    label="Entrada (izq.)" if use_split_scale else "Entrada fuentes",
                    color=theme.INK_PRIMARY,
                    linewidth=1.75,
                    alpha=0.90,
                    zorder=3,
                )
            )
            if has_flood:
                lines_all.extend(
                    self.ax_flow.plot(
                        times,
                        flood_rates,
                        label="Rebose (izq.)" if use_split_scale else "Rebose superf.",
                        color="#DC2626",
                        linestyle="--",
                        linewidth=1.5,
                        alpha=0.92,
                        zorder=3.5,
                    )
                )

            if use_split_scale:
                self._ax_flow_ptar = self.ax_flow.twinx()
                ax_ptar = self._ax_flow_ptar
                ax_ptar.tick_params(colors="#0F766E", labelsize=7.1)
                for spine in ax_ptar.spines.values():
                    spine.set_color(theme.INK_PRIMARY)
                    spine.set_linewidth(0.85)
                ax_ptar.spines["right"].set_color("#0F766E")
                ax_ptar.spines["right"].set_linewidth(1.3)
                ax_ptar.set_ylabel("PTAR 31 / F_max (der., m³/s)", color="#0F766E", fontsize=7.0)

                if has_admission_cap:
                    lines_all.extend(
                        ax_ptar.plot(
                            times,
                            admitted,
                            label="Admitido (der. →)",
                            color="#1D4ED8",
                            linestyle="-.",
                            linewidth=1.45,
                            zorder=3.5,
                        )
                    )
                if f_max > 1e-6:
                    lines_all.append(
                        ax_ptar.axhline(
                            f_max,
                            color="#6B7280",
                            linestyle=":",
                            linewidth=1.1,
                            label=f"F_max ({f_max:.2f})",
                            zorder=2.5,
                        )
                    )
                lines_all.extend(
                    ax_ptar.plot(
                        times,
                        ptar_out,
                        label="PTAR 31 (der. →)",
                        color="#0F766E",
                        linewidth=2.25,
                        zorder=4,
                    )
                )
                ax_ptar.fill_between(times, 0.0, ptar_out, color="#0F766E", alpha=0.14, zorder=1)
                self.ax_flow.set_ylim(0.0, max_left_q * 1.26)
                ax_ptar.set_ylim(0.0, max_ptar_q * 2.15)
                self.ax_flow.set_ylabel("Entrada / Rebose (izq.)", color=theme.INK_PRIMARY, fontsize=7.2)
                self.ax_flow.text(
                    0.02,
                    0.95,
                    f"Izq ≤ {max_left_q:.1f} m³/s · F_max = {f_max:.2f} · PTAR ≤ {max(ptar_out, default=0.0):.2f}",
                    transform=self.ax_flow.transAxes,
                    ha="left",
                    va="top",
                    fontsize=5.9,
                    color="#0F766E",
                    bbox=dict(
                        boxstyle="round,pad=0.18",
                        facecolor=theme.PAPER_BG,
                        edgecolor=theme.PAPER_BORDER,
                        alpha=0.92,
                    ),
                    zorder=6,
                )
            else:
                max_shared = max(max_left_q, max_ptar_q)
                if has_admission_cap:
                    lines_all.extend(
                        self.ax_flow.plot(
                            times,
                            admitted,
                            label="Admitido",
                            color="#1D4ED8",
                            linestyle="-.",
                            linewidth=1.45,
                            zorder=3.5,
                        )
                    )
                if f_max > 1e-6:
                    lines_all.append(
                        self.ax_flow.axhline(
                            f_max,
                            color="#6B7280",
                            linestyle=":",
                            linewidth=1.1,
                            label=f"F_max ({f_max:.2f})",
                            zorder=2.5,
                        )
                    )
                lines_all.extend(
                    self.ax_flow.plot(
                        times,
                        ptar_out,
                        label="PTAR 31",
                        color="#0F766E",
                        linewidth=2.25,
                        zorder=4,
                    )
                )
                self.ax_flow.fill_between(times, 0.0, ptar_out, color="#0F766E", alpha=0.14, zorder=1)
                self.ax_flow.set_ylim(0.0, max_shared * 1.24)
                self.ax_flow.set_ylabel("Caudal (m³/s)", color=theme.INK_PRIMARY, fontsize=7.3)

            self.ax_flow.set_title(
                "Balance de Caudales (m³/s)",
                color=theme.INK_PRIMARY,
                fontsize=8.5,
                fontweight="bold",
                fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
                pad=22 if len(lines_all) <= 3 else 30,
            )
            self.ax_flow.legend(
                lines_all,
                [l.get_label() for l in lines_all],
                loc="lower center",
                bbox_to_anchor=(0.5, 1.01),
                ncol=min(3, max(2, len(lines_all))),
                frameon=True,
                facecolor=theme.PAPER_BG,
                edgecolor=theme.PAPER_BORDER,
                framealpha=0.95,
                fontsize=6.3,
                borderpad=0.20,
                columnspacing=0.55,
                handlelength=1.2,
                labelcolor=theme.INK_PRIMARY,
            )

        self._cursor_flow = self.ax_flow.axvline(
            t_cur,
            color="#334155",
            linestyle="-.",
            linewidth=1.3,
            alpha=0.9,
            animated=True,
        )

        # Panel inferior: Utilización % Cap.
        max_u_val = 105.0
        tied_note = ""
        if has_prev and previous_result is not None and focus_pid:
            prev_times = [s.time_min for s in previous_result.snapshots]
            prev_utils = [
                s.pipe_states[focus_pid].utilization_pct if focus_pid in s.pipe_states else 0.0
                for s in previous_result.snapshots
            ]
            cur_utils = [
                s.pipe_states[focus_pid].utilization_pct if focus_pid in s.pipe_states else 0.0
                for s in result.snapshots
            ]
            pk_prev_u = previous_result.peak_pipe_utilization.get(focus_pid, 0.0)
            pk_cur_u = result.peak_pipe_utilization.get(focus_pid, 0.0)
            cur_color = (
                "#DC2626"
                if pk_cur_u > pk_prev_u + 0.5
                else ("#059669" if pk_cur_u < pk_prev_u - 0.5 else "#1D4ED8")
            )
            if prev_utils:
                max_u_val = max(max_u_val, max(prev_utils))
                self.ax_util.plot(
                    prev_times,
                    prev_utils,
                    label=f"Antes ({_fmt_pct_compact(pk_prev_u)})",
                    color="#6B7280",
                    linestyle="--",
                    linewidth=1.8,
                    zorder=3,
                )
            if cur_utils:
                max_u_val = max(max_u_val, max(cur_utils))
            self.ax_util.plot(
                times,
                cur_utils,
                label=f"Después ({_fmt_pct_compact(pk_cur_u)})",
                color=cur_color,
                linewidth=2.3,
                zorder=4,
            )
        else:
            palette = ["#991B1B", "#EA580C", "#1D4ED8"]
            styles = ["-", "--", "-."]
            widths = [2.4, 1.9, 1.55]
            peaks_seen: List[float] = []
            for idx, pid in enumerate(target_pids):
                utils = [
                    s.pipe_states[pid].utilization_pct if pid in s.pipe_states else 0.0
                    for s in result.snapshots
                ]
                pk_u = result.peak_pipe_utilization.get(pid, 0.0)
                peaks_seen.append(pk_u)
                if utils:
                    max_u_val = max(max_u_val, max(utils))
                self.ax_util.plot(
                    times,
                    utils,
                    label=f"{pid} ({_fmt_pct_compact(pk_u)})",
                    color=palette[idx % len(palette)],
                    linestyle=styles[idx % len(styles)],
                    linewidth=widths[idx % len(widths)],
                    zorder=4 - idx * 0.2,
                )
            if len(peaks_seen) >= 2 and max(peaks_seen) > 5.0:
                tied = [
                    pid
                    for pid, pk in zip(target_pids, peaks_seen)
                    if abs(pk - peaks_seen[0]) <= 1.0
                ]
                if len(tied) >= 2:
                    tied_note = (
                        f"Empate en pico: {' = '.join(tied)} ({_fmt_pct_compact(peaks_seen[0])})"
                    )

        self._configure_util_axis(
            self.ax_util, max_u_val, cap_pct=result.utilization_cap_pct
        )

        if tied_note:
            self.ax_util.text(
                0.02,
                0.94,
                tied_note,
                transform=self.ax_util.transAxes,
                ha="left",
                va="top",
                fontsize=6.1,
                color=theme.INK_PRIMARY,
                bbox=dict(
                    boxstyle="round,pad=0.18",
                    facecolor=theme.PAPER_BG,
                    edgecolor=theme.PAPER_BORDER,
                    alpha=0.92,
                ),
                zorder=6,
            )

        self._cursor_util = self.ax_util.axvline(
            t_cur,
            color="#334155",
            linestyle="-.",
            linewidth=1.3,
            alpha=0.9,
            animated=True,
        )

        if has_prev and focus_pid:
            title_u = f"Utilización {focus_pid}: Antes vs. Después"
        elif selected_pipe_id:
            title_u = f"Utilización — {selected_pipe_id}"
        else:
            title_u = "Utilización — Top 3 Críticas"
        self.ax_util.set_title(
            title_u,
            color=theme.INK_PRIMARY,
            fontsize=8.5,
            fontweight="bold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=38,
        )
        self.ax_util.set_xlabel("Tiempo (min)", color=theme.INK_SECONDARY, fontsize=7.6)
        self.ax_util.set_ylabel("% Cap.", color=theme.INK_SECONDARY, fontsize=7.6)
        self.ax_util.legend(
            loc="lower center",
            bbox_to_anchor=(0.5, 1.01),
            ncol=2,
            frameon=True,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.95,
            fontsize=6.3,
            borderpad=0.20,
            columnspacing=0.65,
            handlelength=1.25,
            labelcolor=theme.INK_PRIMARY,
        )

        self._last_draw_ts = now
        self._last_hydro_size = (self.canvas.width(), self.canvas.height())
        self._has_drawn_hydro = True
        _sync_figure_size(self.canvas, self.figure)
        _safe_tight_layout(self.figure, self.canvas)
        self.canvas.draw_idle()

    @staticmethod
    def _compute_bottleneck_note(
        route: List[PipeEdge],
        fill_pcts: List[float],
        dem_pcts: List[float],
        diams: List[float],
        q_maxs: List[float],
    ) -> str:
        choked_idx = None
        for idx, dem_p in enumerate(dem_pcts):
            if dem_p > 105.0:
                choked_idx = idx
                break
        if choked_idx is None:
            return ""
        downstream_low = [
            (route[j], diams[j])
            for j in range(choked_idx + 1, len(route))
            if fill_pcts[j] < 92.0 and q_maxs[j] > 1e-12
        ]
        if not downstream_low:
            return ""
        bn_pipe = route[choked_idx]
        bn_diam = diams[choked_idx]
        dn_names = ", ".join(p.pipe_id for p, _ in downstream_low[:3])
        return (
            f'Cuello de botella en {bn_pipe.pipe_id} ({bn_diam:.0f}"): rebosa exceso; '
            f"{dn_names} reciben caudal estrangulado."
        )

    def _redraw_profile(self) -> None:
        _sync_figure_size(self.profile_canvas, self.profile_figure)
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
                "Seleccione una tubería o trace una ruta (BFS/DFS)\npara inspeccionar Uso vs. Capacidad hacia PTAR 31.",
                ha="center",
                va="center",
                color=theme.INK_MUTED,
                fontsize=8.0,
                transform=self.ax_profile.transAxes,
            )
            _safe_tight_layout(self.profile_figure, self.profile_canvas)
            self.profile_canvas.draw_idle()
            return

        step_idx = max(0, min(len(result.snapshots) - 1, self._last_step_idx))
        snap = result.snapshots[step_idx]
        prev_res = self._last_prev_result
        has_prev = (
            prev_res is not None and prev_res is not result and bool(prev_res.snapshots)
        )
        prev_snap = (
            prev_res.snapshots[min(step_idx, len(prev_res.snapshots) - 1)]
            if has_prev and prev_res is not None
            else None
        )

        xs = list(range(len(route)))
        q_lives: List[float] = []
        q_dems: List[float] = []
        q_maxs: List[float] = []
        fill_pcts: List[float] = []
        dem_pcts: List[float] = []
        bar_colors: List[str] = []
        diams: List[float] = []
        closed_flags: List[bool] = []
        x_labels: List[str] = []

        for pipe in route:
            ps = snap.pipe_states.get(pipe.pipe_id)
            eff_qmax = (
                ps.effective_q_max_m3s
                if (ps is not None and ps.effective_q_max_m3s is not None)
                else pipe.q_max_m3s
            )
            q_live = ps.flow_m3s if ps is not None else 0.0
            q_dem = ps.demand_flow_m3s if ps is not None else q_live
            is_closed = bool(ps.is_closed) if ps is not None else (eff_qmax <= 1e-12)
            fill_pct = (
                (q_live / eff_qmax * 100.0) if (not is_closed and eff_qmax > 1e-12) else 0.0
            )
            dem_pct = ps.utilization_pct if ps is not None else fill_pct
            col = (
                (
                    theme.INK_MUTED
                    if is_closed
                    else ("#991b1b" if ps.category.is_overloaded else ps.category.color_hex)
                )
                if ps is not None
                else theme.ACCENT_PRIMARY
            )
            diam = self._last_diam_overrides.get(pipe.pipe_id, pipe.diameter_in)
            q_lives.append(q_live)
            q_dems.append(q_dem)
            q_maxs.append(eff_qmax)
            fill_pcts.append(fill_pct)
            dem_pcts.append(dem_pct)
            bar_colors.append(col)
            diams.append(diam)
            closed_flags.append(is_closed)
            mod_tag = "*" if pipe.pipe_id in self._last_interventions else ""
            if len(route) <= 6:
                x_labels.append(
                    f'{pipe.pipe_id}{mod_tag}\n{pipe.from_node}→{pipe.to_node} ({diam:.0f}")'
                )
            else:
                x_labels.append(f"{pipe.pipe_id}{mod_tag}")

        bn_note = self._compute_bottleneck_note(route, fill_pcts, dem_pcts, diams, q_maxs)
        tag_fs = 6.0 if len(route) >= 9 else (6.5 if len(route) >= 7 else 7.1)

        if self._profile_mode == "pct":
            phys_bars = [
                0.0 if cl else min(100.0, fp) for fp, cl in zip(fill_pcts, closed_flags)
            ]
            self.ax_profile.bar(
                xs,
                phys_bars,
                width=0.60,
                color=bar_colors,
                edgecolor=theme.INK_PRIMARY,
                linewidth=0.8,
                zorder=3,
            )

            has_overflow = False
            max_vis_y = 115.0
            for idx, (pipe, fp, dp, cl, _qd) in enumerate(
                zip(route, fill_pcts, dem_pcts, closed_flags, q_dems)
            ):
                ps_cur = snap.pipe_states.get(pipe.pipe_id)
                raw_dem_pct = ps_cur.demand_ratio_pct if ps_cur is not None else dp
                is_capped = bool(ps_cur.is_overflow_capped) if ps_cur is not None else False
                if cl:
                    self.ax_profile.bar(
                        [idx],
                        [28.0],
                        bottom=[0.0],
                        width=0.60,
                        facecolor="#E5E7EB",
                        edgecolor="#374151",
                        hatch="xxx",
                        linewidth=1.1,
                        zorder=3.5,
                    )
                    max_vis_y = max(max_vis_y, 50.0)
                    tag = "CERRADA"
                    y_pos = 31.0
                    tag_col = "#374151"
                elif dp > 100.5:
                    has_overflow = True
                    ext = min(62.0, 16.0 + 18.0 * math.log10(max(1.0, raw_dem_pct / 100.0)))
                    self.ax_profile.bar(
                        [idx],
                        [ext],
                        bottom=[100.0],
                        width=0.60,
                        facecolor="#FEE2E2",
                        edgecolor="#991B1B",
                        hatch="///",
                        linewidth=1.1,
                        zorder=3.5,
                    )
                    top_b = 100.0 + ext
                    max_vis_y = max(max_vis_y, top_b + 30.0)
                    mult = raw_dem_pct / 100.0
                    mult_s = f"×{mult:.0f}" if mult >= 10.0 else f"×{mult:.1f}"
                    tag = f"{_fmt_pct_compact(dp)}\n(Tope {mult_s})" if is_capped else f"{_fmt_pct_compact(dp)}\n({mult_s})"
                    y_pos = top_b + 3.0
                    tag_col = "#991B1B"
                else:
                    tag = f"{fp:.0f}%"
                    y_pos = phys_bars[idx] + 3.0
                    tag_col = (
                        theme.ACCENT_TEXT_ON_LIGHT
                        if pipe.pipe_id == self._last_pipe_id
                        else theme.INK_PRIMARY
                    )

                if pipe.pipe_id in self._last_interventions:
                    tag = f"MOD\n{tag}"

                self.ax_profile.text(
                    idx,
                    y_pos,
                    tag,
                    ha="center",
                    va="bottom",
                    fontsize=tag_fs,
                    fontweight="bold"
                    if (
                        dp > 100.5
                        or pipe.pipe_id == self._last_pipe_id
                        or pipe.pipe_id in self._last_interventions
                    )
                    else "normal",
                    color=tag_col,
                    zorder=6,
                )

            if prev_snap is not None:
                prev_ys = []
                for pipe in route:
                    pps = prev_snap.pipe_states.get(pipe.pipe_id)
                    pu = pps.utilization_pct if pps is not None else 0.0
                    if pu > 100.5:
                        prev_ys.append(
                            100.0 + min(62.0, 16.0 + 18.0 * math.log10(max(1.0, pu / 100.0)))
                        )
                    else:
                        prev_ys.append(pu)
                self.ax_profile.scatter(
                    xs,
                    prev_ys,
                    marker="_",
                    s=170,
                    linewidths=2.0,
                    color="#1D4ED8",
                    zorder=5,
                    label="Antes",
                )

            self.ax_profile.axhspan(0.0, 75.0, color="#22c55e", alpha=0.05, zorder=0)
            self.ax_profile.axhspan(75.0, 100.0, color="#f97316", alpha=0.08, zorder=0)
            self.ax_profile.axhline(75.0, color="#F97316", linestyle=":", linewidth=1.0, zorder=2)
            self.ax_profile.axhline(100.0, color="#DC2626", linestyle="--", linewidth=1.4, zorder=4)

            top_ylim = max(max_vis_y, 178.0 if has_overflow else 118.0)
            self.ax_profile.set_ylim(0.0, top_ylim)
            if has_overflow:
                cap_lbl = (
                    f"{result.utilization_cap_pct:.0f}%\nRebose"
                    if result.utilization_cap_pct is not None
                    else "Rebose\n>100%"
                )
                self.ax_profile.set_yticks([0, 25, 50, 75, 100, 138])
                self.ax_profile.set_yticklabels(
                    ["0%", "25%", "50%", "75%", "100%\nQmax", cap_lbl]
                )
            else:
                self.ax_profile.set_yticks([0, 25, 50, 75, 100])
                self.ax_profile.set_yticklabels(["0%", "25%", "50%", "75%", "100%\nQmax"])
            self.ax_profile.set_ylabel("% Uso vs. Qmax", color=theme.INK_PRIMARY, fontsize=7.5)

            legend_handles = [
                Patch(
                    facecolor=theme.ACCENT_PRIMARY,
                    edgecolor=theme.INK_PRIMARY,
                    label="Llenado (≤100%)",
                ),
                Line2D([0], [0], color="#DC2626", linestyle="--", linewidth=1.4, label="Cap. 100%"),
            ]
            if has_overflow:
                legend_handles.append(
                    Patch(
                        facecolor="#FEE2E2",
                        edgecolor="#991B1B",
                        hatch="///",
                        label="Exceso/Rebose",
                    )
                )
            if prev_snap is not None:
                legend_handles.append(
                    Line2D(
                        [0],
                        [0],
                        color="#1D4ED8",
                        marker="_",
                        linestyle="None",
                        markersize=9,
                        markeredgewidth=2.0,
                        label="Antes",
                    )
                )
        else:
            self.ax_profile.bar(xs, q_lives, width=0.62, color=bar_colors, zorder=3)
            self.ax_profile.bar(
                xs,
                q_maxs,
                width=0.70,
                facecolor="none",
                edgecolor=theme.INK_PRIMARY,
                linewidth=1.6,
                zorder=4,
            )
            if prev_snap is not None:
                prev_qs = [
                    prev_snap.pipe_states[p.pipe_id].flow_m3s
                    if p.pipe_id in prev_snap.pipe_states
                    else 0.0
                    for p in route
                ]
                self.ax_profile.scatter(
                    xs,
                    prev_qs,
                    marker="_",
                    s=160,
                    linewidths=2.0,
                    color="#1D4ED8",
                    zorder=5,
                    label="Antes",
                )
            top_y = max(q_lives + q_maxs + [0.05])
            self.ax_profile.set_ylim(0.0, top_y * 1.40)
            for idx, (pipe, q_live, _q_dem, q_mx, diam, fp, dp) in enumerate(
                zip(route, q_lives, q_dems, q_maxs, diams, fill_pcts, dem_pcts)
            ):
                y_pos = max(q_live, q_mx) + top_y * 0.025
                if q_mx <= 1e-9:
                    tag = "CERRADA"
                elif dp > 100.5:
                    tag = f'{diam:.0f}"\n×{dp / 100.0:.1f}'
                else:
                    tag = f'{diam:.0f}"\n{fp:.0f}%'
                is_sel = pipe.pipe_id == self._last_pipe_id
                self.ax_profile.text(
                    idx,
                    y_pos,
                    tag,
                    ha="center",
                    va="bottom",
                    fontsize=tag_fs,
                    fontweight="bold" if (is_sel or dp > 100.5) else "normal",
                    color=theme.ACCENT_TEXT_ON_LIGHT if is_sel else theme.INK_PRIMARY,
                )
            self.ax_profile.set_ylabel("Caudal (m³/s)", color=theme.INK_PRIMARY, fontsize=7.6)
            legend_handles = [
                Patch(
                    facecolor="none",
                    edgecolor=theme.INK_PRIMARY,
                    linewidth=1.6,
                    label="Cap. Qmax",
                ),
                Patch(
                    facecolor=theme.ACCENT_PRIMARY,
                    edgecolor="none",
                    label="Caudal Q(t)",
                ),
            ]
            if prev_snap is not None:
                legend_handles.append(
                    Line2D(
                        [0],
                        [0],
                        color="#1D4ED8",
                        marker="_",
                        linestyle="None",
                        markersize=9,
                        markeredgewidth=2.0,
                        label="Antes",
                    )
                )

        if bn_note:
            self._lbl_prof_note.setText(bn_note)
            if not self._prof_note_visible:
                self._lbl_prof_note.setVisible(True)
                self._prof_note_visible = True
        elif self._prof_note_visible:
            self._lbl_prof_note.setVisible(False)
            self._prof_note_visible = False

        self.ax_profile.set_xticks(xs)
        self.ax_profile.set_xticklabels(
            x_labels,
            fontsize=6.5 if len(route) > 6 else 7.1,
            rotation=28 if len(route) > 5 else 0,
            ha="right" if len(route) > 5 else "center",
        )
        start_n = route[0].from_node
        end_n = route[-1].to_node
        self.ax_profile.set_title(
            f"Perfil ({start_n} → {end_n}) · t={snap.time_min:.0f}m",
            color=theme.INK_PRIMARY,
            fontsize=8.6,
            fontweight="bold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=22,
        )
        self.ax_profile.legend(
            handles=legend_handles,
            loc="lower center",
            bbox_to_anchor=(0.5, 1.01),
            ncol=min(3, len(legend_handles)),
            frameon=True,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.95,
            fontsize=6.3,
            borderpad=0.20,
            columnspacing=0.60,
            handlelength=1.2,
            labelcolor=theme.INK_PRIMARY,
        )
        self._last_profile_size = (self.profile_canvas.width(), self.profile_canvas.height())
        self._has_drawn_profile = True
        _safe_tight_layout(self.profile_figure, self.profile_canvas)
        self.profile_canvas.draw_idle()


class ComparisonChartsPanel(QWidget):
    """Gráfica comparativa de los escenarios con etiquetas de valor y selector Rebose / PTAR."""

    def __init__(
        self,
        dpi: int = 96,
        ui_font: str = "Segoe UI",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._dpi = max(72, int(dpi))
        self._metric_mode: str = "flood"
        self._layout_mode: str = "stacked"
        self._last_drawn_mode: str = ""
        self._last_drawn_size: Tuple[int, int] = (0, 0)
        self._last_summaries: List[ScenarioSummary] = []

        self.setObjectName("ChartsHost")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        mbar = QFrame(self)
        mbar.setObjectName("SubBar")
        mb_lay = QHBoxLayout(mbar)
        mb_lay.setContentsMargins(6, 3, 6, 3)
        mb_lay.setSpacing(4)

        lbl = QLabel("Serie 2:", mbar)
        lbl.setFont(QFont(ui_font, 7, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {theme.INK_MUTED}; background: transparent;")
        mb_lay.addWidget(lbl)

        self._seg_metric = SegmentedControl(
            [("flood", "Rebose (m³)"), ("ptar", "PTAR 31 (m³/s)")],
            initial_key="flood",
            inactive_variant="light_secondary",
            font_pt=7,
            pad_x=7,
            pad_y=2,
            spacing=4,
            framed=False,
            parent=mbar,
        )
        self._seg_metric.selectionChanged.connect(self.set_metric_mode)
        mb_lay.addWidget(self._seg_metric)
        mb_lay.addStretch(1)
        lay.addWidget(mbar)
        lay.addWidget(make_separator("h", theme.PAPER_BORDER, 1, self))

        self.figure = Figure(figsize=(4.0, 4.4), dpi=self._dpi, facecolor=theme.PAPER_BG)
        self.ax_bar = self.figure.add_subplot(211)
        self.ax_ptar = self.figure.add_subplot(212)

        self.canvas = FigureCanvasQTAgg(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.setMinimumSize(220, 200)
        lay.addWidget(self.canvas, 1)

        self._resize_timer = QTimer(self)
        self._resize_timer.setSingleShot(True)
        self._resize_timer.setInterval(100)
        self._resize_timer.timeout.connect(self._reflow)

        self._draw_empty()

    def stop_timers(self) -> None:
        if self._resize_timer.isActive():
            self._resize_timer.stop()

    def set_metric_mode(self, mode: str) -> None:
        if mode not in ("flood", "ptar") or mode == self._metric_mode:
            return
        self._metric_mode = mode
        self._seg_metric.set_current(mode)
        if self._last_summaries:
            self.update_comparison(self._last_summaries)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self.width() >= 180 and self.height() >= 180:
            self._resize_timer.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self._reflow)

    def _reflow(self) -> None:
        w = max(1, self.width())
        h = max(1, self.height())
        if w < 180 or h < 180:
            return
        cw = self.canvas.width()
        ch = self.canvas.height()
        lw, lh = self._last_drawn_size
        size_changed = abs(cw - lw) > 8 or abs(ch - lh) > 8
        new_mode = "side" if (w >= 560 and h < 480) else "stacked"
        if self._last_summaries:
            if new_mode == self._last_drawn_mode and not size_changed:
                return
            self._layout_mode = new_mode
            self.update_comparison(self._last_summaries)
            return
        if not size_changed and self._last_drawn_mode == new_mode:
            return
        self._layout_mode = new_mode
        self._last_drawn_mode = new_mode
        self._last_drawn_size = (cw, ch)
        _sync_figure_size(self.canvas, self.figure)
        _safe_tight_layout(self.figure, self.canvas)
        self.canvas.draw_idle()

    def _draw_empty(self) -> None:
        _sync_figure_size(self.canvas, self.figure)
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
            "Presione 'Recalcular 5 Escenarios'\npara generar la comparativa hidráulica.",
            ha="center",
            va="center",
            color=theme.INK_MUTED,
            fontsize=8.5,
            transform=ax.transAxes,
        )
        self._last_drawn_mode = self._layout_mode
        self._last_drawn_size = (self.canvas.width(), self.canvas.height())
        _safe_tight_layout(self.figure, self.canvas)
        self.canvas.draw_idle()

    def update_comparison(self, summaries: List[ScenarioSummary]) -> None:
        self._last_summaries = list(summaries)
        if not summaries:
            self._draw_empty()
            return

        _sync_figure_size(self.canvas, self.figure)
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
        near_counts = [s.num_near_capacity_pipes for s in summaries]
        over_counts = [s.num_overloaded_pipes for s in summaries]
        x = list(range(len(labels)))
        width = 0.36
        max_c = max(near_counts + over_counts + [4])

        bars_crit = self.ax_bar.bar(
            [i - width / 2 for i in x],
            near_counts,
            width=width,
            label="Críticas (>75–100%)",
            color="#ef4444",
        )
        bars_over = self.ax_bar.bar(
            [i + width / 2 for i in x],
            over_counts,
            width=width,
            label="Sobrec. (>100%)",
            color="#991b1b",
        )
        for rect in list(bars_crit) + list(bars_over):
            val = int(round(rect.get_height()))
            self.ax_bar.text(
                rect.get_x() + rect.get_width() / 2.0,
                rect.get_height() + max_c * 0.03,
                f"{val}",
                ha="center",
                va="bottom",
                fontsize=6.5,
                fontweight="bold" if val > 0 else "normal",
                color=theme.INK_PRIMARY,
            )

        self.ax_bar.set_ylim(0, max_c * 1.48)
        self.ax_bar.set_xticks(x)
        self.ax_bar.set_xticklabels(labels, fontsize=7.0)
        self.ax_bar.set_ylabel("Tuberías", color=theme.INK_SECONDARY, fontsize=7.4)
        self.ax_bar.set_title(
            "Tuberías Críticas y Sobrecargadas",
            color=theme.INK_PRIMARY,
            fontsize=8.2,
            fontweight="bold",
            fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
            pad=3,
        )
        self.ax_bar.legend(
            loc="upper center",
            ncol=2,
            fontsize=6.0,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.92,
            borderpad=0.18,
            columnspacing=0.60,
            handlelength=1.10,
            labelcolor=theme.INK_PRIMARY,
        )

        colors = ["#6B7280", "#0284C7", "#CA8A04", "#EA580C", "#DC2626"]
        styles = ["-", "--", "-.", ":", "-"]
        widths = [1.6, 1.8, 1.9, 2.0, 2.2]

        if self._metric_mode == "flood":
            max_f = 100.0
            for idx, s in enumerate(summaries):
                ts = [snap.time_min for snap in s.result.snapshots]
                fs = [snap.total_surface_flooding_m3 for snap in s.result.snapshots]
                if fs:
                    max_f = max(max_f, max(fs))
                end_v = fs[-1] if fs else 0.0
                self.ax_ptar.plot(
                    ts,
                    fs,
                    label=f"E{s.scenario_id}: {_fmt_vol_compact(end_v)}",
                    color=colors[idx % len(colors)],
                    linestyle=styles[idx % len(styles)],
                    linewidth=widths[idx % len(widths)],
                )
            self.ax_ptar.set_ylim(0.0, max_f * 1.24)
            self.ax_ptar.yaxis.set_major_formatter(
                FuncFormatter(lambda v, _: _fmt_vol_compact(v))
            )
            self.ax_ptar.set_title(
                "Rebose Superficial (m³)",
                color=theme.INK_PRIMARY,
                fontsize=8.2,
                fontweight="bold",
                fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
                pad=3,
            )
            self.ax_ptar.set_ylabel("Rebose (m³)", color=theme.INK_SECONDARY, fontsize=7.4)
        else:
            max_q = 0.01
            peaks = []
            for idx, s in enumerate(summaries):
                ts = [snap.time_min for snap in s.result.snapshots]
                qs = [snap.total_sink_discharge_m3s for snap in s.result.snapshots]
                pk = max(qs) if qs else 0.0
                peaks.append(pk)
                if qs:
                    max_q = max(max_q, pk)
                cond_es = theme.translate_scenario_name(s.condition, compact=True)
                self.ax_ptar.plot(
                    ts,
                    qs,
                    label=f"E{s.scenario_id} {cond_es}",
                    color=colors[idx % len(colors)],
                    linestyle=styles[idx % len(styles)],
                    linewidth=widths[len(widths) - 1 - (idx % len(widths))],
                )
            self.ax_ptar.set_ylim(0, max_q * 1.42)
            non_zero_pks = [p for p in peaks if p > 1e-4]
            if len(non_zero_pks) >= 2 and (max(non_zero_pks) - min(non_zero_pks)) < 0.005:
                self.ax_ptar.text(
                    0.98,
                    0.06,
                    f"E2–E5 tope: {max_q:.2f} m³/s",
                    transform=self.ax_ptar.transAxes,
                    ha="right",
                    va="bottom",
                    fontsize=5.9,
                    color=theme.INK_PRIMARY,
                    bbox=dict(
                        boxstyle="round,pad=0.16",
                        facecolor=theme.PAPER_BG,
                        edgecolor=theme.PAPER_BORDER,
                        alpha=0.90,
                    ),
                )
            self.ax_ptar.set_title(
                "Descarga PTAR 31 (m³/s)",
                color=theme.INK_PRIMARY,
                fontsize=8.2,
                fontweight="bold",
                fontfamily=["Inter", "Segoe UI", "DejaVu Sans"],
                pad=3,
            )
            self.ax_ptar.set_ylabel("m³/s", color=theme.INK_SECONDARY, fontsize=7.4)

        self.ax_ptar.set_xlabel("Tiempo (min)", color=theme.INK_SECONDARY, fontsize=7.2, labelpad=1)
        self.ax_ptar.legend(
            loc="upper left",
            fontsize=5.8,
            facecolor=theme.PAPER_BG,
            edgecolor=theme.PAPER_BORDER,
            framealpha=0.90,
            ncol=2,
            borderpad=0.18,
            columnspacing=0.50,
            handlelength=1.05,
            labelcolor=theme.INK_PRIMARY,
        )

        self._last_drawn_mode = self._layout_mode
        self._last_drawn_size = (self.canvas.width(), self.canvas.height())
        _safe_tight_layout(self.figure, self.canvas)
        self.canvas.draw_idle()
