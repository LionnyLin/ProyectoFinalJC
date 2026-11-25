"""Widget interactivo NetworkCanvas en PySide6 con overlays, tooltips y animaciones."""

import math
from typing import Callable, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QPoint, QPointF, QRect, Qt, QTimer, Signal
from PySide6.QtGui import QFont, QGuiApplication, QMouseEvent, QPainter, QWheelEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QWidget,
)

from src.algorithms.analysis import classify_overload_persistence
from src.algorithms.traversals import TraversalAnimFrame
from src.data_structures import DirectedGraph, ManholeNode, PipeEdge
from src.simulation.models import PipeIntervention, TimeStepSnapshot
from .. import theme
from ..widgets import make_separator
from .layout import CanvasLayoutEngine, CanvasScene, blend_hex
from .renderer import CanvasRenderer


class _TooltipPopup(QLabel):
    """Tooltip cartográfico flotante en Grafito (#4A4A4A) y Vitela (#FFFFE3)."""

    def __init__(self, ui_font: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFont(QFont(ui_font, 8))
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setStyleSheet(
            f"background-color: {theme.SHELL_BG}; color: {theme.SHELL_TEXT}; "
            f"border: 1px solid {theme.ACCENT_ON_DARK}; padding: 6px 10px;"
        )


class NetworkCanvas(QWidget):
    """Lienzo cartográfico interactivo con zoom, paneo, pulsos de Manning y tooltips."""

    pipeSelected = Signal(str)
    nodeSelected = Signal(str)

    _PULSE_TICK_MS = 32

    def __init__(
        self,
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        dpi_scale: float = 1.0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.ui_font = ui_font
        self.mono_font = mono_font
        self.dpi_scale = max(1.0, float(dpi_scale))

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(220, 200)

        self.graph: Optional[DirectedGraph] = None
        self.snapshot: Optional[TimeStepSnapshot] = None

        self.selected_pipe_id: Optional[str] = None
        self.selected_node_id: Optional[str] = None
        self.highlight_pipe_ids: Set[str] = set()
        self.highlight_node_ids: Set[str] = set()
        self.show_pipe_labels: bool = True
        self.show_util_labels: bool = True

        self._interventions: Dict[str, PipeIntervention] = {}
        self._isolated_nodes: Set[str] = set()
        self._isolated_pipes: Set[str] = set()
        self._basin_active: bool = False
        self._basin_nodes: Set[str] = set()
        self._basin_pipes: Set[str] = set()
        self._tour_active: bool = False
        self._tour_nodes: Set[str] = set()
        self._tour_pipes: Set[str] = set()
        self._map_mode: str = "instant"
        self._peak_util_map: Dict[str, float] = {}
        self._overload_minutes_map: Dict[str, float] = {}
        self._total_duration_min: float = 90.0
        self._traversal_frame: Optional[TraversalAnimFrame] = None

        self._is_playing: bool = False
        self._playback_speed_factor: float = 1.0
        self._pulse_time_s: float = 0.0
        self._effect_time_s: float = 0.0
        self._ordered_route_pipes: List[str] = []
        self._prev_pipe_colors: Dict[str, str] = {}
        self._color_lerp_t: float = 1.0
        self._route_transition_t: float = 1.0
        self._color_lerp_duration_s: float = 0.20
        self._route_transition_duration_s: float = 0.45

        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._drag_start: Optional[Tuple[float, float]] = None
        self._dragged: bool = False
        self._last_hover_key: Optional[str] = None
        self._tooltip: Optional[_TooltipPopup] = None

        self._layout_engine = CanvasLayoutEngine(ui_font=ui_font, mono_font=mono_font, dpi_scale=self.dpi_scale)
        self._renderer = CanvasRenderer(ui_font=ui_font)
        self._scene: CanvasScene = CanvasScene(width=400, height=300, scale_factor=1.0, node_radius=10.0, dense_mode=False)
        self._scene_dirty: bool = True

        self._tour_card_widget: Optional[QWidget] = None

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(self._PULSE_TICK_MS)
        self._pulse_timer.timeout.connect(self._tick_flow_pulses)

        self._cam_timer = QTimer(self)
        self._cam_timer.timeout.connect(self._tick_camera_anim)
        self._cam_anim_state: Optional[Tuple[float, float, float, float, float, float, int, int]] = None

        self._build_overlays()
        self._position_overlays()

    @property
    def current_scene(self) -> CanvasScene:
        if self._scene_dirty:
            self._rebuild_scene()
        return self._scene

    def attach_tour_card(self, card: QWidget) -> None:
        """Asocia una tarjeta flotante de recorrido guiado sobre el lienzo."""
        card.setParent(self)
        self._tour_card_widget = card
        card.raise_()
        self._position_overlays()

    def reposition_tour_card(self) -> None:
        """Recalcula la posición de la tarjeta flotante de recorrido si está visible."""
        if self._tour_card_widget is None or not self._tour_card_widget.isVisible():
            return
        w = max(220, self.width())
        h = max(200, self.height())
        preferred = max(290, min(int(round(310 * self.dpi_scale)), int(w * 0.54)))
        card_w = max(200, min(w - 24, preferred))
        self._tour_card_widget.setFixedWidth(card_w)
        self._tour_card_widget.adjustSize()
        ch = min(h - 24, self._tour_card_widget.sizeHint().height())
        self._tour_card_widget.setGeometry(12, max(12, h - ch - 12), card_w, ch)
        self._tour_card_widget.raise_()

    def _build_overlays(self) -> None:
        self._stamp_lbl = QLabel("PLANO HIDRÁULICO · 46 NODOS · 59 TRAMOS", self)
        self._stamp_lbl.setFont(QFont(self.mono_font, 7, QFont.Weight.Bold))
        self._stamp_lbl.setStyleSheet(
            f"background-color: {theme.DOCK_BG}; color: {theme.INK_PRIMARY}; "
            f"border: 1px solid {theme.DOCK_BORDER}; padding: 4px 9px;"
        )

        self._zoom_bar = QFrame(self)
        self._zoom_bar.setStyleSheet(
            f"QFrame {{ background-color: {theme.CANVAS_FLOAT_BG}; "
            f"border: 1px solid {theme.CANVAS_FLOAT_BORDER}; }}"
        )
        zb_lay = QHBoxLayout(self._zoom_bar)
        zb_lay.setContentsMargins(2, 1, 2, 1)
        zb_lay.setSpacing(0)

        def _make_mini_btn(txt: str, slot: Callable[[], None]) -> QPushButton:
            b = QPushButton(txt, self._zoom_bar)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(QFont(self.ui_font, 8, QFont.Weight.Bold))
            b.setStyleSheet(
                f"QPushButton {{ background-color: {theme.CANVAS_FLOAT_BG}; "
                f"color: {theme.CANVAS_FLOAT_FG}; border: none; padding: 4px 8px; }}"
                f"QPushButton:hover {{ background-color: {theme.CANVAS_FLOAT_HOVER}; }}"
            )
            b.clicked.connect(slot)
            return b

        zb_lay.addWidget(_make_mini_btn("−", self.zoom_out))
        zb_lay.addWidget(make_separator("v", theme.ACCENT_PRIMARY, 1, self._zoom_bar))

        self._lbl_zoom = QLabel("100%", self._zoom_bar)
        self._lbl_zoom.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_zoom.setFont(QFont(self.mono_font, 8, QFont.Weight.Bold))
        self._lbl_zoom.setStyleSheet(
            f"background: transparent; color: {theme.CANVAS_FLOAT_FG}; border: none; padding: 0 6px;"
        )
        self._lbl_zoom.setMinimumWidth(44)
        zb_lay.addWidget(self._lbl_zoom)

        zb_lay.addWidget(make_separator("v", theme.ACCENT_PRIMARY, 1, self._zoom_bar))
        zb_lay.addWidget(_make_mini_btn("+", self.zoom_in))
        zb_lay.addWidget(make_separator("v", theme.ACCENT_PRIMARY, 1, self._zoom_bar))
        zb_lay.addWidget(_make_mini_btn("Ajustar", self.reset_view))

        self._hint_bar = QLabel(
            "Arrastrar: mover  ·  Rueda: zoom  ·  Clic: inspeccionar  ·  Doble clic: ajustar",
            self,
        )
        self._hint_bar.setFont(QFont(self.ui_font, 8))
        self._hint_bar.setStyleSheet(
            f"background-color: {theme.DOCK_BG}; color: {theme.INK_PRIMARY}; "
            f"border: 1px solid {theme.DOCK_BORDER}; padding: 4px 9px;"
        )

    def _position_overlays(self) -> None:
        w = max(200, self.width())
        h = max(200, self.height())
        min_stamp_w = int(520 * min(1.25, self.dpi_scale))
        min_stamp_h = int(340 * min(1.25, self.dpi_scale))

        if w >= min_stamp_w and h >= min_stamp_h:
            self._stamp_lbl.adjustSize()
            sh = self._stamp_lbl.sizeHint()
            self._stamp_lbl.setGeometry(12, 12, sh.width(), sh.height())
            self._stamp_lbl.show()
        else:
            self._stamp_lbl.hide()

        self._zoom_bar.adjustSize()
        zh = self._zoom_bar.sizeHint()
        self._zoom_bar.setGeometry(max(12, w - zh.width() - 12), 12, zh.width(), zh.height())
        self._zoom_bar.show()

        if (
            not self._tour_active
            and w >= int(480 * min(1.25, self.dpi_scale))
            and h >= min_stamp_h
        ):
            self._hint_bar.adjustSize()
            hh = self._hint_bar.sizeHint()
            self._hint_bar.setGeometry(12, max(12, h - hh.height() - 12), hh.width(), hh.height())
            self._hint_bar.show()
        else:
            self._hint_bar.hide()

        self.reposition_tour_card()

    def overlay_boxes(self) -> List[Tuple[float, float, float, float]]:
        boxes: List[Tuple[float, float, float, float]] = []
        for widget in (self._stamp_lbl, self._zoom_bar, self._hint_bar):
            if widget.isVisible() or widget.width() > 2:
                if not widget.isHidden():
                    g = widget.geometry()
                    if g.width() > 2 and g.height() > 2:
                        boxes.append(
                            (float(g.x() - 4), float(g.y() - 4), float(g.right() + 5), float(g.bottom() + 5))
                        )
        return boxes

    def set_graph(self, graph: DirectedGraph) -> None:
        self.stop_pulse_animation()
        self._stop_camera_animation()
        self.graph = graph
        self.snapshot = None
        self.selected_pipe_id = None
        self.selected_node_id = None
        self.highlight_pipe_ids.clear()
        self.highlight_node_ids.clear()
        self._interventions.clear()
        self._isolated_nodes.clear()
        self._isolated_pipes.clear()
        self._basin_active = False
        self._basin_nodes.clear()
        self._basin_pipes.clear()
        self._tour_active = False
        self._tour_nodes.clear()
        self._tour_pipes.clear()
        self._peak_util_map.clear()
        self._overload_minutes_map.clear()
        self._traversal_frame = None
        self._ordered_route_pipes.clear()
        self._prev_pipe_colors.clear()
        self._color_lerp_t = 1.0
        self._route_transition_t = 1.0
        self._update_stamp_label()
        self.reset_view()

    def _update_stamp_label(self) -> None:
        if self.graph is None:
            return
        n_nodes, n_pipes, *_ = self.graph.summary()
        if self.snapshot is None:
            txt = f"PLANO HIDRÁULICO · {n_nodes} NODOS · {n_pipes} TRAMOS"
        else:
            t_min = self.snapshot.time_min
            dur_lbl = f"0–{self._total_duration_min:.0f} min"
            if self._map_mode == "peak":
                txt = f"PICO MÁXIMO ACUMULADO · {dur_lbl}"
            elif self._map_mode == "overload_minutes":
                txt = f"MINUTOS EN SOBRECARGA (>100%) · {dur_lbl}"
            else:
                txt = f"PLANO HIDRÁULICO · {n_nodes} NODOS · {n_pipes} TRAMOS · t = {t_min:.1f} min"
        self._stamp_lbl.setText(txt)
        self._stamp_lbl.adjustSize()
        self._position_overlays()

    def set_stress_maps(
        self,
        peak_util: Optional[Dict[str, float]] = None,
        overload_minutes: Optional[Dict[str, float]] = None,
        total_duration_min: float = 90.0,
    ) -> None:
        if peak_util is not None:
            self._peak_util_map = dict(peak_util)
        if overload_minutes is not None:
            self._overload_minutes_map = dict(overload_minutes)
        self._total_duration_min = max(1.0, float(total_duration_min))

    def set_snapshot(self, snapshot: Optional[TimeStepSnapshot]) -> None:
        had_snap = self.snapshot is not None and not self._scene_dirty
        if had_snap and snapshot is not None:
            self._prev_pipe_colors = self._capture_current_pipe_colors()
            self._color_lerp_t = 0.0
        else:
            self._prev_pipe_colors.clear()
            self._color_lerp_t = 1.0
        self.snapshot = snapshot
        self._update_stamp_label()
        self.redraw()
        self._sync_effect_timer()

    def set_interventions(
        self,
        interventions: Optional[Dict[str, PipeIntervention]] = None,
        isolated_nodes: Optional[Set[str]] = None,
        isolated_pipes: Optional[Set[str]] = None,
    ) -> None:
        self._interventions = dict(interventions or {})
        self._isolated_nodes = set(isolated_nodes or ())
        self._isolated_pipes = set(isolated_pipes or ())
        self.redraw()

    def set_basin_focus(
        self,
        node_ids: Optional[Set[str]],
        pipe_ids: Optional[Set[str]],
    ) -> None:
        if node_ids is None or pipe_ids is None:
            self._basin_active = False
            self._basin_nodes.clear()
            self._basin_pipes.clear()
        else:
            self._basin_active = True
            self._basin_nodes = set(node_ids)
            self._basin_pipes = set(pipe_ids)
        self.redraw()

    def set_tour_focus(
        self,
        node_ids: Optional[Set[str]],
        pipe_ids: Optional[Set[str]],
    ) -> None:
        if node_ids is None or pipe_ids is None:
            self._tour_active = False
            self._tour_nodes.clear()
            self._tour_pipes.clear()
        else:
            self._tour_active = True
            self._tour_nodes = set(node_ids)
            self._tour_pipes = set(pipe_ids)
        self._position_overlays()
        self.redraw()

    def set_map_mode(
        self,
        mode: str,
        peak_util: Optional[Dict[str, float]] = None,
        overload_minutes: Optional[Dict[str, float]] = None,
        total_duration_min: float = 90.0,
    ) -> None:
        if mode not in ("instant", "peak", "overload_minutes"):
            mode = "instant"
        self._map_mode = mode
        if peak_util is not None:
            self._peak_util_map = dict(peak_util)
        if overload_minutes is not None:
            self._overload_minutes_map = dict(overload_minutes)
        self._total_duration_min = max(1.0, float(total_duration_min))
        self._update_stamp_label()
        self.redraw()

    def set_traversal_frame(self, frame: Optional[TraversalAnimFrame]) -> None:
        if not self._scene_dirty and frame is not None:
            self._prev_pipe_colors = self._capture_current_pipe_colors()
            self._color_lerp_t = 0.0
        else:
            self._prev_pipe_colors.clear()
            self._color_lerp_t = 1.0
        self._traversal_frame = frame
        self.redraw()
        self._sync_effect_timer()

    def set_highlights(
        self,
        pipe_ids: Optional[Set[str]] = None,
        node_ids: Optional[Set[str]] = None,
        ordered_route_pipes: Optional[List[str]] = None,
        animate_transition: bool = True,
    ) -> None:
        pipes_set = set(pipe_ids or ())
        nodes_set = set(node_ids or ())
        ordered_list = list(ordered_route_pipes or ())
        if not self._scene_dirty and (pipes_set or self.highlight_pipe_ids):
            self._prev_pipe_colors = self._capture_current_pipe_colors()
            self._color_lerp_t = 0.0
        else:
            self._prev_pipe_colors.clear()
            self._color_lerp_t = 1.0
        self.highlight_pipe_ids = pipes_set
        self.highlight_node_ids = nodes_set
        self._ordered_route_pipes = ordered_list if pipes_set else []
        if pipes_set and animate_transition:
            self._route_transition_t = 0.0
        else:
            self._route_transition_t = 1.0
        self.redraw()
        self._sync_effect_timer()

    def promote_traversal_to_highlights(
        self,
        pipe_ids: Optional[Set[str]],
        node_ids: Optional[Set[str]],
        ordered_route_pipes: Optional[List[str]] = None,
    ) -> None:
        """Consolida un recorrido animado hacia la vista resaltada en vivo con transición."""
        if not self._scene_dirty:
            self._prev_pipe_colors = self._capture_current_pipe_colors()
            self._color_lerp_t = 0.0
        self._traversal_frame = None
        pipes_set = set(pipe_ids or ())
        self.highlight_pipe_ids = pipes_set
        self.highlight_node_ids = set(node_ids or ())
        self._ordered_route_pipes = list(ordered_route_pipes or ()) if pipes_set else []
        self._route_transition_t = 0.0 if pipes_set else 1.0
        self.redraw()
        self._sync_effect_timer()

    def select_pipe(self, pipe_id: Optional[str]) -> None:
        self.selected_pipe_id = pipe_id
        self.selected_node_id = None
        self.redraw()

    def select_node(self, node_id: Optional[str]) -> None:
        self.selected_node_id = node_id
        self.selected_pipe_id = None
        self.redraw()

    def _capture_current_pipe_colors(self) -> Dict[str, str]:
        if self._scene_dirty or not self._scene.pipes:
            return {}
        overrides = self._interpolated_pipe_colors() or {}
        return {pv.pipe_id: overrides.get(pv.pipe_id, pv.color) for pv in self._scene.pipes}

    def _interpolated_pipe_colors(self) -> Optional[Dict[str, str]]:
        if self._color_lerp_t >= 0.999 or not self._prev_pipe_colors:
            return None
        t = max(0.0, min(1.0, self._color_lerp_t))
        eased = 1.0 - (1.0 - t) ** 3
        out: Dict[str, str] = {}
        for pv in self._scene.pipes:
            prev_c = self._prev_pipe_colors.get(pv.pipe_id)
            if prev_c and prev_c.lower() != pv.color.lower():
                out[pv.pipe_id] = blend_hex(prev_c, pv.color, eased)
        return out or None

    def _needs_effect_timer(self) -> bool:
        return (
            self._is_playing
            or (self._traversal_frame is not None)
            or bool(self.highlight_pipe_ids)
            or (self._color_lerp_t < 0.999)
            or (self._route_transition_t < 0.999)
        )

    def _sync_effect_timer(self) -> None:
        if self._needs_effect_timer() and self.isVisible():
            if not self._pulse_timer.isActive():
                self._pulse_timer.start()
        elif self._pulse_timer.isActive():
            self._pulse_timer.stop()

    def set_playing(self, playing: bool, speed_factor: float = 1.0) -> None:
        self._playback_speed_factor = max(0.5, min(3.5, float(speed_factor)))
        was_playing = self._is_playing
        self._is_playing = bool(playing)
        self._sync_effect_timer()
        if self._is_playing and not was_playing:
            self.redraw()
        elif not self._is_playing and was_playing:
            self.update()

    def stop_pulse_animation(self) -> None:
        self._is_playing = False
        self._color_lerp_t = 1.0
        self._route_transition_t = 1.0
        self._prev_pipe_colors.clear()
        if self._pulse_timer.isActive():
            self._pulse_timer.stop()

    def _tick_flow_pulses(self) -> None:
        if not self._needs_effect_timer():
            self._pulse_timer.stop()
            return
        dt_real_s = self._PULSE_TICK_MS / 1000.0
        self._effect_time_s += dt_real_s
        if self._is_playing:
            self._pulse_time_s += dt_real_s * self._playback_speed_factor
        if self._color_lerp_t < 1.0:
            dur = max(0.06, self._color_lerp_duration_s / max(1.0, self._playback_speed_factor * 0.7))
            self._color_lerp_t = min(1.0, self._color_lerp_t + dt_real_s / dur)
            if self._color_lerp_t >= 1.0:
                self._prev_pipe_colors.clear()
        if self._route_transition_t < 1.0:
            self._route_transition_t = min(
                1.0, self._route_transition_t + dt_real_s / self._route_transition_duration_s
            )
        self.update()
        if not self._needs_effect_timer():
            self._pulse_timer.stop()

    def zoom_in(self) -> None:
        w = max(200, self.width())
        h = max(200, self.height())
        self._zoom_at(w / 2.0, h / 2.0, 1.18)

    def zoom_out(self) -> None:
        w = max(200, self.width())
        h = max(200, self.height())
        self._zoom_at(w / 2.0, h / 2.0, 1.0 / 1.18)

    def reset_view(self) -> None:
        self._stop_camera_animation()
        self._hide_tooltip()
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._update_zoom_label()
        self.redraw()

    def _stop_camera_animation(self) -> None:
        if self._cam_timer.isActive():
            self._cam_timer.stop()
        self._cam_anim_state = None

    def animate_reset_view(self, steps: int = 10, step_ms: int = 18) -> None:
        self._animate_camera_to(1.0, 0.0, 0.0, steps=steps, step_ms=step_ms)

    def animate_focus_region(
        self,
        node_ids: Set[str],
        pipe_ids: Optional[Set[str]] = None,
        left_reserve_px: float = 0.0,
        steps: int = 12,
        step_ms: int = 18,
    ) -> None:
        if self.graph is None:
            return
        pts: List[Tuple[float, float]] = []
        for nid in node_ids:
            node = self.graph.get_node(nid)
            if node is not None:
                pts.append((node.x, node.y))
        for pid in (pipe_ids or ()):
            edge = self.graph.get_pipe(pid)
            if edge is not None:
                n1 = self.graph.get_node(edge.from_node)
                n2 = self.graph.get_node(edge.to_node)
                if n1 is not None:
                    pts.append((n1.x, n1.y))
                if n2 is not None:
                    pts.append((n2.x, n2.y))
        if not pts:
            return

        w = max(320, self.width())
        h = max(240, self.height())
        pad_x, pad_y = CanvasLayoutEngine.compute_padding(w, h)
        min_nx = min(p[0] for p in pts)
        max_nx = max(p[0] for p in pts)
        min_ny = min(p[1] for p in pts)
        max_ny = max(p[1] for p in pts)
        mid_nx = (min_nx + max_nx) / 2.0
        mid_ny = (min_ny + max_ny) / 2.0

        base_w = max(80.0, w - 2.0 * pad_x)
        base_h = max(80.0, h - 2.0 * pad_y)
        span_x = max(28.0, (max_nx - min_nx) * base_w)
        span_y = max(28.0, (max_ny - min_ny) * base_h)

        safe_left = min(float(left_reserve_px), w * 0.42)
        avail_w = max(180.0, w - safe_left - 44.0)
        avail_h = max(160.0, h - 68.0)

        zoom_x = (avail_w * 0.72) / span_x
        zoom_y = (avail_h * 0.72) / span_y
        target_zoom = max(1.05, min(2.55, min(zoom_x, zoom_y)))

        target_cx = safe_left + avail_w * 0.50
        target_cy = h * 0.48
        cx, cy = w / 2.0, h / 2.0
        base_mx = pad_x + mid_nx * base_w
        base_my = pad_y + mid_ny * base_h

        target_pan_x = (target_cx - cx) - (base_mx - cx) * target_zoom
        target_pan_y = (target_cy - cy) - (base_my - cy) * target_zoom
        self._animate_camera_to(target_zoom, target_pan_x, target_pan_y, steps=steps, step_ms=step_ms)

    def _animate_camera_to(
        self,
        target_zoom: float,
        target_pan_x: float,
        target_pan_y: float,
        steps: int = 12,
        step_ms: int = 18,
    ) -> None:
        self._stop_camera_animation()
        start_zoom = self._zoom
        start_px = self._pan_x
        start_py = self._pan_y
        total_steps = max(1, int(steps))

        if (
            abs(target_zoom - start_zoom) < 1e-3
            and abs(target_pan_x - start_px) < 1.0
            and abs(target_pan_y - start_py) < 1.0
        ):
            self._zoom = target_zoom
            self._pan_x = target_pan_x
            self._pan_y = target_pan_y
            self._update_zoom_label()
            self.redraw()
            return

        self._cam_anim_state = (
            start_zoom,
            start_px,
            start_py,
            target_zoom,
            target_pan_x,
            target_pan_y,
            1,
            total_steps,
        )
        self._tick_camera_anim()
        if self._cam_anim_state is not None:
            self._cam_timer.start(max(10, int(step_ms)))

    def _tick_camera_anim(self) -> None:
        if self._cam_anim_state is None:
            self._cam_timer.stop()
            return
        sz, spx, spy, tz, tpx, tpy, step_idx, total_steps = self._cam_anim_state
        t = step_idx / float(total_steps)
        eased = 1.0 - (1.0 - t) * (1.0 - t)
        self._zoom = sz + (tz - sz) * eased
        self._pan_x = spx + (tpx - spx) * eased
        self._pan_y = spy + (tpy - spy) * eased
        self._update_zoom_label()
        self.redraw()
        if step_idx >= total_steps:
            self._stop_camera_animation()
        else:
            self._cam_anim_state = (sz, spx, spy, tz, tpx, tpy, step_idx + 1, total_steps)

    def focus_node(self, node_id: str) -> None:
        if self.graph is None:
            return
        node = self.graph.get_node(node_id)
        if node is not None:
            self._center_world_point(node.x, node.y)

    def focus_pipe(self, pipe_id: str) -> None:
        if self.graph is None:
            return
        pipe = self.graph.get_pipe(pipe_id)
        if pipe is None:
            return
        n1 = self.graph.get_node(pipe.from_node)
        n2 = self.graph.get_node(pipe.to_node)
        if n1 and n2:
            self._center_world_point((n1.x + n2.x) / 2.0, (n1.y + n2.y) / 2.0)

    def _center_world_point(self, nx: float, ny: float) -> None:
        w = max(200, self.width())
        h = max(200, self.height())
        pad_x, pad_y = CanvasLayoutEngine.compute_padding(w, h)
        base_x = pad_x + nx * (w - 2.0 * pad_x)
        base_y = pad_y + ny * (h - 2.0 * pad_y)
        cx, cy = w / 2.0, h / 2.0
        self._pan_x = -(base_x - cx) * self._zoom
        self._pan_y = -(base_y - cy) * self._zoom
        self.redraw()

    def _update_zoom_label(self) -> None:
        self._lbl_zoom.setText(f"{int(round(self._zoom * 100))}%")

    def _zoom_at(self, mx: float, my: float, factor: float) -> None:
        new_zoom = max(0.55, min(4.5, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-6:
            return
        self._hide_tooltip()
        w = max(200, self.width())
        h = max(200, self.height())
        cx, cy = w / 2.0, h / 2.0
        scale_ratio = new_zoom / self._zoom
        self._pan_x = (mx - cx) - scale_ratio * (mx - cx - self._pan_x)
        self._pan_y = (my - cy) - scale_ratio * (my - cy - self._pan_y)
        self._zoom = new_zoom
        self._update_zoom_label()
        self.redraw()

    def _rebuild_scene(self) -> None:
        self._scene = self._layout_engine.build_scene(
            graph=self.graph,
            snapshot=self.snapshot,
            width=max(200, self.width()),
            height=max(200, self.height()),
            zoom=self._zoom,
            pan_x=self._pan_x,
            pan_y=self._pan_y,
            selected_pipe_id=self.selected_pipe_id,
            selected_node_id=self.selected_node_id,
            highlight_pipe_ids=self.highlight_pipe_ids,
            highlight_node_ids=self.highlight_node_ids,
            show_pipe_labels=self.show_pipe_labels,
            show_util_labels=self.show_util_labels,
            interventions=self._interventions,
            isolated_nodes=self._isolated_nodes,
            isolated_pipes=self._isolated_pipes,
            basin_active=self._basin_active,
            basin_nodes=self._basin_nodes,
            basin_pipes=self._basin_pipes,
            tour_active=self._tour_active,
            tour_nodes=self._tour_nodes,
            tour_pipes=self._tour_pipes,
            map_mode=self._map_mode,
            peak_util_map=self._peak_util_map,
            overload_minutes_map=self._overload_minutes_map,
            total_duration_min=self._total_duration_min,
            traversal_frame=self._traversal_frame,
            overlay_boxes=self.overlay_boxes(),
            ordered_route_pipe_ids=self._ordered_route_pipes,
        )
        self._scene_dirty = False

    def redraw(self) -> None:
        self._scene_dirty = True
        self._rebuild_scene()
        self.update()

    def _hit_test(self, px: float, py: float) -> Optional[Tuple[str, str]]:
        scene = self.current_scene
        best_node = None
        best_nd = 1e9
        for n in scene.nodes:
            d = math.hypot(px - n.x, py - n.y)
            if d <= n.radius + 5.0 and d < best_nd:
                best_nd = d
                best_node = n.node_id
        if best_node is not None:
            return ("node", best_node)

        for b in reversed(scene.badges):
            if b.x0 - 3.0 <= px <= b.x1 + 3.0 and b.y0 - 3.0 <= py <= b.y1 + 3.0:
                return (b.entity_kind, b.entity_id)

        best_pipe = None
        best_pd = 1e9
        for p in scene.pipes:
            vx = p.sx2 - p.sx1
            vy = p.sy2 - p.sy1
            seg_sq = vx * vx + vy * vy
            if seg_sq <= 1e-6:
                continue
            t = max(0.0, min(1.0, ((px - p.sx1) * vx + (py - p.sy1) * vy) / seg_sq))
            proj_x = p.sx1 + t * vx
            proj_y = p.sy1 + t * vy
            d = math.hypot(px - proj_x, py - proj_y)
            tol = max(6.0, p.draw_width * 0.6 + 4.0)
            if d <= tol and d < best_pd:
                best_pd = d
                best_pipe = p.pipe_id
        if best_pipe is not None:
            return ("pipe", best_pipe)
        return None

    def _build_node_tooltip(self, node: ManholeNode) -> str:
        role = {"source": "Alcantarilla Fuente", "sink": "Sumidero / PTAR Punta Canoa"}.get(
            node.node_type, "Pozo de Inspección"
        )
        lines = [f"Nodo {node.node_id} · {role}"]
        if node.node_id in self._isolated_nodes:
            lines.append("[AISLADO DE 31] Sin ruta hidráulica activa hacia la PTAR")
        if self.snapshot and node.node_id in self.snapshot.node_states:
            st = self.snapshot.node_states[node.node_id]
            lines.append(f"Entrada: {st.inflow_m3s:.4f} m³/s  |  Salida: {st.outflow_m3s:.4f} m³/s")
            if st.stored_volume_m3 > 1e-4:
                lines.append(f"En pozo: {st.stored_volume_m3:.2f} m³")
            if st.surface_flooding_m3 > 1e-4:
                lines.append(f"Rebose superficial (vía): {st.surface_flooding_m3:.2f} m³")
        return "\n".join(lines)

    def _build_pipe_tooltip(self, pipe: PipeEdge) -> str:
        inv = self._interventions.get(pipe.pipe_id)
        eff_qmax = pipe.q_max_m3s
        eff_vel = pipe.reference_velocity_ms
        eff_diam = pipe.diameter_in
        if self.snapshot and pipe.pipe_id in self.snapshot.pipe_states:
            ps = self.snapshot.pipe_states[pipe.pipe_id]
            if ps.effective_q_max_m3s is not None:
                eff_qmax = ps.effective_q_max_m3s
            if ps.effective_velocity_ms is not None:
                eff_vel = ps.effective_velocity_ms
        if inv and inv.diameter_in_override is not None:
            eff_diam = inv.diameter_in_override

        lines = [
            f"Tubería {pipe.pipe_id}: {pipe.from_node} → {pipe.to_node}",
            f"Ø {eff_diam:.0f}\"  ·  L = {pipe.length_m:.1f} m  ·  V = {eff_vel:.3f} m/s  ·  Qmax = {eff_qmax:.4f} m³/s",
        ]
        if inv:
            marks = []
            if inv.has_obstruction:
                marks.append(f"OBST {inv.obstruction_pct:.0f}%")
            if inv.diameter_in_override is not None and abs(inv.diameter_in_override - pipe.diameter_in) > 1e-3:
                marks.append(f"Ø {pipe.diameter_in:.0f}\"→{inv.diameter_in_override:.0f}\"")
            if marks:
                lines.append("Intervención: " + " · ".join(marks))
        if pipe.pipe_id in self._isolated_pipes:
            lines.append("[AISLADO DE 31] Aguas arriba de un cierre al 100%")
        if self.snapshot and pipe.pipe_id in self.snapshot.pipe_states:
            ps = self.snapshot.pipe_states[pipe.pipe_id]
            if ps.in_min_cut:
                lines.append("[CORTE MÍNIMO FORD-FULKERSON] Cuello del flujo máximo")
            if ps.is_closed:
                lines.append(
                    f"Estado (t={self.snapshot.time_min:.0f}m): CERRADA 100%  ·  Caudal conducido: 0.0000 m³/s"
                )
            else:
                cap_tag = " (Tope rebose)" if ps.is_overflow_capped else ""
                lines.append(
                    f"Caudal conducido (t={self.snapshot.time_min:.0f}m): {ps.flow_m3s:.4f} m³/s  ·  Utilización: {ps.utilization_pct:.1f}%{cap_tag} ({ps.category.label})"
                )
                if ps.demand_ratio_pct > 100.5:
                    lines.append(
                        f"Demanda: {ps.demand_flow_m3s:.4f} m³/s ({ps.demand_ratio_pct / 100.0:.2f}× Qmax)  ·  Exceso: {ps.excess_flow_m3s:.4f} m³/s"
                    )
        dur_lbl = f"0–{self._total_duration_min:.0f} min"
        if self.snapshot and pipe.pipe_id in self._peak_util_map:
            pk = self._peak_util_map[pipe.pipe_id]
            lines.append(f"Pico máximo ({dur_lbl}): {pk:.1f}%")
        if pipe.pipe_id in self._overload_minutes_map:
            ov_min = self._overload_minutes_map[pipe.pipe_id]
            _, _, ov_desc = classify_overload_persistence(ov_min, self._total_duration_min)
            lines.append(f"Sobrecarga total ({dur_lbl}): {ov_min:.0f} min >100% ({ov_desc})")
        return "\n".join(lines)

    def _show_tooltip(self, global_pos: QPoint, text: str) -> None:
        if self._tooltip is None:
            self._tooltip = _TooltipPopup(self.ui_font, self)
        self._tooltip.setText(text)
        self._tooltip.adjustSize()
        sz = self._tooltip.sizeHint()
        screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen is not None else QRect(0, 0, 1920, 1080)
        px = global_pos.x() + 14
        py = global_pos.y() + 14
        if px + sz.width() + 12 > geo.right():
            px = max(geo.left() + 8, global_pos.x() - sz.width() - 14)
        if py + sz.height() + 12 > geo.bottom():
            py = max(geo.top() + 8, global_pos.y() - sz.height() - 14)
        self._tooltip.move(px, py)
        self._tooltip.show()

    def _hide_tooltip(self) -> None:
        self._last_hover_key = None
        if self._tooltip is not None:
            self._tooltip.hide()

    def close_overlays(self) -> None:
        self._hide_tooltip()
        self.stop_pulse_animation()
        self._stop_camera_animation()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_overlays()
        self.redraw()

    def wheelEvent(self, event: QWheelEvent) -> None:
        self._stop_camera_animation()
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = 1.12 if delta > 0 else (1.0 / 1.12)
        pos = event.position()
        self._zoom_at(pos.x(), pos.y(), factor)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._stop_camera_animation()
            p = event.position()
            self._drag_start = (p.x(), p.y())
            self._dragged = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        p = event.position()
        if self._drag_start is not None:
            dx = p.x() - self._drag_start[0]
            dy = p.y() - self._drag_start[1]
            if abs(dx) > 3.0 or abs(dy) > 3.0:
                self._dragged = True
            if self._dragged:
                self._pan_x += dx
                self._pan_y += dy
                self._drag_start = (p.x(), p.y())
                self._hide_tooltip()
                self.redraw()
            event.accept()
            return

        if self.graph is None:
            return
        hit = self._hit_test(p.x(), p.y())
        hover_key = None
        tooltip_text = None
        if hit is not None:
            kind, eid = hit
            if kind == "node":
                node = self.graph.get_node(eid)
                if node is not None:
                    hover_key = f"node:{eid}"
                    tooltip_text = self._build_node_tooltip(node)
            else:
                pipe = self.graph.get_pipe(eid)
                if pipe is not None:
                    hover_key = f"pipe:{eid}"
                    tooltip_text = self._build_pipe_tooltip(pipe)

        if tooltip_text and hover_key != self._last_hover_key:
            self._last_hover_key = hover_key
            self._show_tooltip(event.globalPosition().toPoint(), tooltip_text)
        elif not tooltip_text:
            self._hide_tooltip()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_start is not None:
            was_dragged = self._dragged
            self._drag_start = None
            self._dragged = False
            if was_dragged:
                event.accept()
                return
            p = event.position()
            hit = self._hit_test(p.x(), p.y())
            if hit is not None:
                kind, eid = hit
                if kind == "node":
                    self.select_node(eid)
                    self.nodeSelected.emit(eid)
                else:
                    self.select_pipe(eid)
                    self.pipeSelected.emit(eid)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            p = event.position()
            if self._hit_test(p.x(), p.y()) is None:
                self.reset_view()
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event) -> None:
        self._hide_tooltip()
        super().leaveEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_effect_timer()

    def hideEvent(self, event) -> None:
        if self._pulse_timer.isActive():
            self._pulse_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, _event) -> None:
        if self._scene_dirty:
            self._rebuild_scene()
        painter = QPainter(self)
        self._renderer.paint(
            painter,
            self._scene,
            pulse_time_s=self._pulse_time_s,
            is_playing=self._is_playing,
            zoom=self._zoom,
            pipe_color_overrides=self._interpolated_pipe_colors(),
            route_transition_t=self._route_transition_t,
            effect_time_s=self._effect_time_s,
            has_active_traversal_anim=(self._traversal_frame is not None),
        )
        painter.setPen(theme.CANVAS_BORDER)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(0, 0, max(1, self.width() - 1), max(1, self.height() - 1))
        painter.end()
