"""Escena 3D interactiva de la cuenca hidráulica con QPainter puro y Z-sorting."""

import math
from typing import Callable, Dict, List, Optional, Set, Tuple

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPen,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.algorithms.analysis import classify_overload_persistence, classify_utilization
from src.algorithms.traversals import TraversalAnimFrame
from src.data_structures import DirectedGraph
from src.simulation.models import (
    PipeIntervention,
    SimulationResult,
    TimeStepSnapshot,
    resolve_pipe_hydraulics,
)
from .. import theme
from ..widgets import make_separator
from .elevation import ElevationProfile, compute_network_elevations
from .projection import (
    OrbitCamera,
    ProjectedPoint,
    draw_capsule_3d,
    draw_projected_ellipse_3d,
    draw_terrain_quad,
    draw_vertical_cylinder_3d,
    point_to_segment_distance_sq,
    shade_color,
)


class _Tooltip3DPopup(QLabel):
    """Tooltip flotante en Grafito (#4A4A4A) y Vitela (#FFFFE3) para la vista 3D."""

    def __init__(self, ui_font: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFont(QFont(ui_font, 8))
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setStyleSheet(
            f"background-color: {theme.SHELL_BG}; color: {theme.SHELL_TEXT}; "
            f"border: 1px solid {theme.ACCENT_ON_DARK}; padding: 6px 10px;"
        )


class Basin3DWidget(QWidget):
    """Renderizador 3D orbital nativo sobre QPainter con columnas piezométricas y picking."""

    pipeSelected = Signal(str)
    nodeSelected = Signal(str)

    _GROUND_LEVELS = (0.0, 0.45, 1.0)
    _Z_EXAG_LEVELS = (1.0, 3.0, 5.0)

    def __init__(
        self,
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        dpi_scale: float = 1.0,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ui_font = ui_font
        self._mono_font = mono_font
        self._dpi_scale = max(1.0, float(dpi_scale))

        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(220, 200)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._graph: Optional[DirectedGraph] = None
        self._profile: Optional[ElevationProfile] = None
        self._snapshot: Optional[TimeStepSnapshot] = None
        self._result: Optional[SimulationResult] = None

        self._map_mode: str = "instant"
        self._peak_util_map: Dict[str, float] = {}
        self._overload_minutes_map: Dict[str, float] = {}
        self._total_duration_min: float = 90.0

        self._interventions: Dict[str, PipeIntervention] = {}
        self._isolated_nodes: Set[str] = set()
        self._isolated_pipes: Set[str] = set()
        self._basin_active: bool = False
        self._basin_nodes: Set[str] = set()
        self._basin_pipes: Set[str] = set()
        self._highlight_pipe_ids: Set[str] = set()
        self._highlight_node_ids: Set[str] = set()
        self._ordered_route_pipes: List[str] = []
        self._highlight_mode: str = "route"
        self._traversal_frame: Optional[TraversalAnimFrame] = None
        self._selected_pipe_id: Optional[str] = None
        self._selected_node_id: Optional[str] = None
        self._show_pipe_labels: bool = True
        self._show_util_labels: bool = True

        self._is_playing: bool = False
        self._playback_speed_factor: float = 1.0
        self._pulse_time_s: float = 0.0
        self._effect_time_s: float = 0.0
        self._effect_timer = QTimer(self)
        self._effect_timer.setInterval(33)
        self._effect_timer.timeout.connect(self._tick_effects)

        self._camera = OrbitCamera()
        self._ground_opacity: float = 0.45
        self._z_exag: float = 3.0

        self._drag_start: Optional[QPointF] = None
        self._drag_last: Optional[QPointF] = None
        self._drag_mode: Optional[str] = None
        self._drag_moved: bool = False

        self._hover_kind: Optional[str] = None
        self._hover_id: Optional[str] = None
        self._last_hover_key: Optional[str] = None
        self._tooltip: Optional[_Tooltip3DPopup] = None

        # Caché de geometría proyectada del último frame para picking O(N + E)
        self._hit_nodes: List[Tuple[str, float, float, float, float]] = []
        self._hit_pipes: List[Tuple[str, float, float, float, float, float]] = []

        self._build_overlays()
        self._position_overlays()

    @property
    def elevation_profile(self) -> Optional[ElevationProfile]:
        return self._profile

    @property
    def camera(self) -> OrbitCamera:
        return self._camera

    @property
    def ground_opacity(self) -> float:
        return self._ground_opacity

    @property
    def z_exag(self) -> float:
        return self._z_exag

    @property
    def map_mode(self) -> str:
        return self._map_mode

    def _build_overlays(self) -> None:
        self._stamp_lbl = QLabel("VISTA 3D · 0 NODOS · 0 TRAMOS", self)
        self._stamp_lbl.setFont(QFont(self._mono_font, 7, QFont.Weight.Bold))
        self._stamp_lbl.setStyleSheet(
            f"background-color: {theme.DOCK_BG}; color: {theme.INK_PRIMARY}; "
            f"border: 1px solid {theme.DOCK_BORDER}; padding: 4px 9px;"
        )

        self._surface_note_lbl = QLabel(
            "Rasante hidráulica de referencia (planta esquemática)", self
        )
        self._surface_note_lbl.setFont(QFont(self._ui_font, 7))
        self._surface_note_lbl.setStyleSheet(
            f"background-color: {theme.PAPER_SUBTLE}; color: {theme.INK_MUTED}; "
            f"border: 1px solid {theme.PAPER_BORDER}; padding: 2px 7px;"
        )

        self._hud_bar = QFrame(self)
        self._hud_bar.setStyleSheet(
            f"QFrame {{ background-color: {theme.CANVAS_FLOAT_BG}; "
            f"border: 1px solid {theme.CANVAS_FLOAT_BORDER}; }}"
        )
        hud_lay = QHBoxLayout(self._hud_bar)
        hud_lay.setContentsMargins(2, 1, 2, 1)
        hud_lay.setSpacing(0)

        def _make_hud_btn(txt: str, slot: Callable[[], None]) -> QPushButton:
            b = QPushButton(txt, self._hud_bar)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFont(QFont(self._ui_font, 8, QFont.Weight.Bold))
            b.setStyleSheet(
                f"QPushButton {{ background-color: {theme.CANVAS_FLOAT_BG}; "
                f"color: {theme.CANVAS_FLOAT_FG}; border: none; padding: 4px 8px; }}"
                f"QPushButton:hover {{ background-color: {theme.CANVAS_FLOAT_HOVER}; }}"
            )
            b.clicked.connect(slot)
            return b

        self._btn_reset_cam = _make_hud_btn("Resetear cámara", self.reset_camera)
        self._btn_ground = _make_hud_btn("Suelo: 45%", self.cycle_ground_opacity)
        self._btn_z_exag = _make_hud_btn("Escala Z: 3x", self.cycle_z_exag)

        hud_lay.addWidget(self._btn_reset_cam)
        hud_lay.addWidget(make_separator("v", theme.ACCENT_PRIMARY, 1, self._hud_bar))
        hud_lay.addWidget(self._btn_ground)
        hud_lay.addWidget(make_separator("v", theme.ACCENT_PRIMARY, 1, self._hud_bar))
        hud_lay.addWidget(self._btn_z_exag)

        self._legend_bar = QLabel(
            "■ Red enterrada  ·  ■ Rasante ref.  ·  ■ Columna piezométrica  ·  "
            "● Rebose  ·  ✕ Bloqueada\n"
            "Arrastrar: orbitar  ·  Shift/Der.: mover  ·  Rueda: zoom  ·  Clic: inspeccionar",
            self,
        )
        self._legend_bar.setFont(QFont(self._ui_font, 7))
        self._legend_bar.setStyleSheet(
            f"background-color: {theme.DOCK_BG}; color: {theme.INK_PRIMARY}; "
            f"border: 1px solid {theme.DOCK_BORDER}; padding: 4px 9px;"
        )

    def _position_overlays(self) -> None:
        w = max(220, self.width())
        h = max(200, self.height())
        show_top = w >= int(460 * min(1.2, self._dpi_scale)) and h >= 260

        if show_top:
            self._stamp_lbl.adjustSize()
            sh = self._stamp_lbl.sizeHint()
            self._stamp_lbl.setGeometry(12, 12, sh.width(), sh.height())
            self._stamp_lbl.show()

            self._surface_note_lbl.adjustSize()
            nh = self._surface_note_lbl.sizeHint()
            self._surface_note_lbl.setGeometry(
                12, 12 + sh.height() + 4, min(w - 24, nh.width()), nh.height()
            )
            self._surface_note_lbl.show()
        else:
            self._stamp_lbl.hide()
            self._surface_note_lbl.hide()

        self._hud_bar.adjustSize()
        hh = self._hud_bar.sizeHint()
        self._hud_bar.setGeometry(max(12, w - hh.width() - 12), 12, hh.width(), hh.height())
        self._hud_bar.show()

        if w >= 520 and h >= 300:
            self._legend_bar.adjustSize()
            lh = self._legend_bar.sizeHint()
            self._legend_bar.setGeometry(12, max(12, h - lh.height() - 12), min(w - 24, lh.width()), lh.height())
            self._legend_bar.show()
        else:
            self._legend_bar.hide()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_overlays()

    def set_graph(self, graph: DirectedGraph) -> None:
        self._graph = graph
        self._profile = compute_network_elevations(graph, grid_n=10)
        self._snapshot = None
        self._result = None
        self._selected_pipe_id = None
        self._selected_node_id = None
        self._interventions.clear()
        self._isolated_nodes.clear()
        self._isolated_pipes.clear()
        self._basin_active = False
        self._basin_nodes.clear()
        self._basin_pipes.clear()
        self._highlight_pipe_ids.clear()
        self._highlight_node_ids.clear()
        self._ordered_route_pipes.clear()
        self._highlight_mode = "route"
        self._traversal_frame = None
        self._is_playing = False
        self._sync_effect_timer()
        self._camera.reset()
        self._update_stamp_label()
        self.update()

    def set_snapshot(
        self,
        snapshot: Optional[TimeStepSnapshot],
        result: Optional[SimulationResult] = None,
    ) -> None:
        self._snapshot = snapshot
        if result is not None:
            self._result = result
        self._update_stamp_label()
        self.update()

    def set_map_mode(
        self,
        mode: str,
        peak_util: Optional[Dict[str, float]] = None,
        overload_minutes: Optional[Dict[str, float]] = None,
        total_duration_min: float = 90.0,
    ) -> None:
        norm = "overload_minutes" if mode in ("overload", "overload_minutes") else mode
        if norm not in ("instant", "peak", "overload_minutes"):
            norm = "instant"
        self._map_mode = norm
        if peak_util is not None:
            self._peak_util_map = dict(peak_util)
        if overload_minutes is not None:
            self._overload_minutes_map = dict(overload_minutes)
        self._total_duration_min = max(1.0, float(total_duration_min))
        self._update_stamp_label()
        self.update()

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

    def set_interventions(
        self,
        interventions: Optional[Dict[str, PipeIntervention]] = None,
        isolated_nodes: Optional[Set[str]] = None,
        isolated_pipes: Optional[Set[str]] = None,
    ) -> None:
        self._interventions = dict(interventions or {})
        self._isolated_nodes = set(isolated_nodes or ())
        self._isolated_pipes = set(isolated_pipes or ())
        self.update()

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
        self.update()

    def set_highlights(
        self,
        pipe_ids: Optional[Set[str]] = None,
        node_ids: Optional[Set[str]] = None,
        ordered_route_pipes: Optional[List[str]] = None,
        highlight_mode: str = "route",
    ) -> None:
        self._highlight_pipe_ids = set(pipe_ids or ())
        self._highlight_node_ids = set(node_ids or ())
        self._ordered_route_pipes = list(ordered_route_pipes or ()) if self._highlight_pipe_ids else []
        self._highlight_mode = highlight_mode or "route"
        self._sync_effect_timer()
        self.update()

    def set_traversal_frame(self, frame: Optional[TraversalAnimFrame]) -> None:
        self._traversal_frame = frame
        self._sync_effect_timer()
        self.update()

    def promote_traversal_to_highlights(
        self,
        pipe_ids: Optional[Set[str]] = None,
        node_ids: Optional[Set[str]] = None,
        ordered_route_pipes: Optional[List[str]] = None,
        highlight_mode: str = "route",
    ) -> None:
        self._traversal_frame = None
        self.set_highlights(
            pipe_ids,
            node_ids,
            ordered_route_pipes=ordered_route_pipes,
            highlight_mode=highlight_mode,
        )

    def set_playing(self, playing: bool, speed_factor: float = 1.0) -> None:
        self._playback_speed_factor = max(0.5, min(3.5, float(speed_factor)))
        self._is_playing = bool(playing)
        self._sync_effect_timer()
        self.update()

    def _needs_effect_timer(self) -> bool:
        return (
            self._is_playing
            or (self._traversal_frame is not None)
            or bool(self._highlight_pipe_ids)
        )

    def _sync_effect_timer(self) -> None:
        if self._needs_effect_timer() and self.isVisible():
            if not self._effect_timer.isActive():
                self._effect_timer.start()
        elif self._effect_timer.isActive():
            self._effect_timer.stop()

    def _tick_effects(self) -> None:
        if not self._needs_effect_timer() or not self.isVisible():
            self._effect_timer.stop()
            return
        dt_s = 0.033
        self._effect_time_s += dt_s
        if self._is_playing:
            self._pulse_time_s += dt_s * self._playback_speed_factor
        self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._sync_effect_timer()

    def hideEvent(self, event) -> None:
        super().hideEvent(event)
        if self._effect_timer.isActive():
            self._effect_timer.stop()

    def select_pipe(self, pipe_id: Optional[str]) -> None:
        self._selected_pipe_id = pipe_id
        self._selected_node_id = None
        self.update()

    def select_node(self, node_id: Optional[str]) -> None:
        self._selected_node_id = node_id
        self._selected_pipe_id = None
        self.update()

    def set_labels_visible(self, show_ids: bool, show_util: bool) -> None:
        self._show_pipe_labels = bool(show_ids)
        self._show_util_labels = bool(show_util)
        self.update()

    def set_ground_opacity(self, opacity: float) -> None:
        self._ground_opacity = max(0.0, min(1.0, float(opacity)))
        self._btn_ground.setText(f"Suelo: {int(round(self._ground_opacity * 100))}%")
        self._position_overlays()
        self.update()

    def cycle_ground_opacity(self) -> None:
        cur = self._ground_opacity
        if cur < 0.2:
            nxt = 0.45
        elif cur < 0.75:
            nxt = 1.0
        else:
            nxt = 0.0
        self.set_ground_opacity(nxt)

    def set_z_exag(self, exag: float) -> None:
        self._z_exag = max(0.5, min(8.0, float(exag)))
        self._btn_z_exag.setText(f"Escala Z: {self._z_exag:g}x")
        self._position_overlays()
        self.update()

    def cycle_z_exag(self) -> None:
        cur = self._z_exag
        if cur < 2.0:
            nxt = 3.0
        elif cur < 4.0:
            nxt = 5.0
        else:
            nxt = 1.0
        self.set_z_exag(nxt)

    def reset_camera(self) -> None:
        self._camera.reset()
        self.update()

    def close_overlays(self) -> None:
        self._hide_tooltip()

    def _update_stamp_label(self) -> None:
        if self._graph is None:
            txt = "VISTA 3D · SIN DATOS"
        else:
            n_nodes, n_pipes, *_ = self._graph.summary()
            dur_lbl = f"0–{self._total_duration_min:.0f} min"
            if self._map_mode == "peak":
                txt = f"VISTA 3D · PICO MÁXIMO · {dur_lbl}"
            elif self._map_mode == "overload_minutes":
                txt = f"VISTA 3D · MINUTOS SOBRECARGA · {dur_lbl}"
            elif self._snapshot is not None:
                txt = (
                    f"VISTA 3D · {n_nodes} NODOS · {n_pipes} TRAMOS · "
                    f"t = {self._snapshot.time_min:.1f} min"
                )
            else:
                txt = f"VISTA 3D · {n_nodes} NODOS · {n_pipes} TRAMOS"
        self._stamp_lbl.setText(txt)
        self._position_overlays()

    def _z_to_world(self, z_m: float) -> float:
        prof = self._profile
        if prof is None:
            return 0.0
        z_span = max(2.0, prof.max_z - prof.min_z)
        return ((z_m - prof.min_z) / z_span) * 0.16 * self._z_exag - 0.12

    def _resolve_pipe_color_and_flags(
        self, pipe_id: str, ps, is_closed: bool
    ) -> Tuple[QColor, bool, bool]:
        """Retorna `(color, is_overloaded, is_blocked)` con paridad exacta al mapa 2D."""
        if is_closed or (ps is not None and ps.is_closed):
            return QColor("#3F3F46"), False, True

        if self._map_mode == "overload_minutes":
            ov_min = self._overload_minutes_map.get(pipe_id, 0.0)
            if ov_min <= 0.0 and self._result is not None:
                ov_min = self._result.pipe_overloaded_minutes.get(pipe_id, 0.0)
            tier, col_hex, _ = classify_overload_persistence(ov_min, self._total_duration_min)
            return QColor(col_hex), (tier >= 3), False

        if self._map_mode == "peak":
            u = self._peak_util_map.get(
                pipe_id,
                self._result.peak_pipe_utilization.get(pipe_id, 0.0)
                if self._result is not None
                else (ps.utilization_pct if ps is not None else 0.0),
            )
            cat = classify_utilization(u)
            return QColor("#991b1b" if cat.is_overloaded else cat.color_hex), cat.is_overloaded, False

        if ps is None:
            return QColor(theme.PIPE_IDLE_COLOR), False, False
        col_hex = "#991b1b" if ps.category.is_overloaded else ps.category.color_hex
        return QColor(col_hex), ps.category.is_overloaded, False

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w = float(self.width())
        h = float(self.height())
        painter.fillRect(QRectF(0, 0, w, h), QColor(theme.CANVAS_BG))

        if self._graph is None or self._profile is None:
            painter.setFont(QFont(self._ui_font, 10))
            painter.setPen(QColor(theme.INK_MUTED))
            painter.drawText(
                QRectF(0, 0, w, h),
                Qt.AlignmentFlag.AlignCenter,
                "Cargue un archivo Excel o carpeta CSV para visualizar en 3D.",
            )
            painter.end()
            return

        graph = self._graph
        prof = self._profile
        snap = self._snapshot
        res = self._result
        cam = self._camera

        # Proyectar nodos y rasantes una sola vez por frame
        node_proj: Dict[str, ProjectedPoint] = {}
        ground_proj: Dict[str, ProjectedPoint] = {}
        for nid, (wx, wy) in prof.node_xy.items():
            zw = self._z_to_world(prof.node_z.get(nid, 0.0))
            gzw = self._z_to_world(prof.ground_z.get(nid, 1.5))
            node_proj[nid] = cam.project_point(wx, wy, zw, w, h)
            ground_proj[nid] = cam.project_point(wx, wy, gzw, w, h)

        # Cola de primitivas para Z-sorting: (depth, layer_order, draw_fn)
        render_queue: List[Tuple[float, int, Callable[[], None]]] = []

        # 1. Malla de rasante de referencia 10x10
        if self._ground_opacity > 0.01:
            alpha_fill = max(12, min(200, int(round(self._ground_opacity * 170))))
            alpha_grid = max(25, min(210, int(round(40 + self._ground_opacity * 145))))
            grid_pen = QPen(QColor(109, 129, 150, alpha_grid), 0.75)
            z_range = max(1.0, prof.max_z - prof.min_z)

            for cell in prof.grid_cells:
                pts_2d: List[QPointF] = []
                d_sum = 0.0
                for cx, cy, cz in cell.corners:
                    pr = cam.project_point(cx, cy, self._z_to_world(cz), w, h)
                    pts_2d.append(QPointF(pr.x, pr.y))
                    d_sum += pr.depth
                avg_d = d_sum * 0.25
                elev_t = max(0.0, min(1.0, (cell.center_z - prof.min_z) / z_range))
                # Tinte mineral sutil según cota sobre vitela
                shade_r = int(round(244 - elev_t * 16))
                shade_g = int(round(244 - elev_t * 16))
                shade_b = int(round(218 - elev_t * 14))
                fill_col = QColor(shade_r, shade_g, shade_b, alpha_fill)

                def _draw_cell(
                    p2d: List[QPointF] = pts_2d,
                    fc: QColor = fill_col,
                    gp: QPen = grid_pen,
                ) -> None:
                    draw_terrain_quad(painter, p2d, fc, gp)

                render_queue.append((avg_d, 0, _draw_cell))

        # Caché de picking
        hit_pipes: List[Tuple[str, float, float, float, float, float]] = []
        hit_nodes: List[Tuple[str, float, float, float, float]] = []

        anim = self._traversal_frame
        has_hl_focus = (anim is not None) or bool(self._highlight_pipe_ids) or bool(self._highlight_node_ids)
        is_min_cut_mode = (anim is None) and (self._highlight_mode == "min_cut") and bool(self._highlight_pipe_ids)
        route_idx_map = {pid: idx for idx, pid in enumerate(self._ordered_route_pipes)}
        min_cut_badges: List[Tuple[float, float, str]] = []

        # 2. Tuberías enterradas y partículas 3D de flujo
        for pipe in graph.pipes():
            p1 = node_proj.get(pipe.from_node)
            p2 = node_proj.get(pipe.to_node)
            if p1 is None or p2 is None:
                continue

            inv = self._interventions.get(pipe.pipe_id)
            _qmax, eff_vel_ms, _ts, eff_diam_in = resolve_pipe_hydraulics(pipe, inv)
            is_closed_inv = inv is not None and inv.is_closed
            ps = snap.pipe_states.get(pipe.pipe_id) if snap is not None else None

            pipe_col, is_overloaded, is_blocked = self._resolve_pipe_color_and_flags(
                pipe.pipe_id, ps, is_closed_inv
            )

            is_anim_active = anim is not None and pipe.pipe_id in anim.active_edges
            is_anim_visited = anim is not None and pipe.pipe_id in anim.visited_edges
            is_anim_backtrack = anim is not None and pipe.pipe_id in anim.backtracked_edges
            is_highlighted = pipe.pipe_id in self._highlight_pipe_ids
            is_focus_pipe = is_anim_active if anim is not None else is_highlighted
            is_selected = pipe.pipe_id == self._selected_pipe_id
            is_hovered = self._hover_kind == "pipe" and self._hover_id == pipe.pipe_id

            is_dimmed_basin = (
                (self._basin_active and pipe.pipe_id not in self._basin_pipes)
                or (pipe.pipe_id in self._isolated_pipes)
            )
            is_dimmed_context = has_hl_focus and not (
                is_focus_pipe or is_anim_visited or is_selected
            )
            is_dimmed = is_dimmed_basin or is_dimmed_context or is_anim_backtrack

            if is_dimmed and not is_blocked:
                pipe_col = QColor(theme.DOCK_BG)
                pipe_col.setAlpha(95 if is_dimmed_context else 155)
            elif is_anim_visited and not is_focus_pipe and not is_selected and not is_blocked:
                pipe_col = QColor(theme.ACCENT_PRIMARY)
                pipe_col.setAlpha(185)

            avg_scale = 0.5 * (p1.scale + p2.scale)
            persp_w = max(0.75, min(1.75, avg_scale / 220.0))
            radius_px = max(1.8, (1.65 + (eff_diam_in - 8.0) * 0.22) * persp_w)
            if is_dimmed_context:
                radius_px = max(1.3, radius_px * 0.72)
            elif is_focus_pipe:
                radius_px += 1.15
            elif is_overloaded and not is_blocked:
                radius_px += 0.85

            hl_col: Optional[QColor] = None
            if is_selected:
                hl_col = QColor(theme.PIPE_SELECTED_HALO)
            elif is_focus_pipe:
                hl_col = QColor("#DC2626" if is_min_cut_mode else theme.ACCENT_PRIMARY)
            elif is_anim_visited:
                hl_col = QColor(94, 154, 158, 175)
            elif is_hovered:
                hl_col = QColor(theme.PALETTE_SLATE)

            pt1 = QPointF(p1.x, p1.y)
            pt2 = QPointF(p2.x, p2.y)
            avg_d = 0.5 * (p1.depth + p2.depth)
            hit_pipes.append((pipe.pipe_id, p1.x, p1.y, p2.x, p2.y, avg_d))

            if is_min_cut_mode and is_focus_pipe:
                min_cut_badges.append((0.5 * (p1.x + p2.x), 0.5 * (p1.y + p2.y), pipe.pipe_id))

            def _draw_pipe(
                a: QPointF = pt1,
                b: QPointF = pt2,
                rad: float = radius_px,
                col: QColor = pipe_col,
                hl: Optional[QColor] = hl_col,
                blocked: bool = is_blocked,
                dashed_flag: bool = (pipe.pipe_id in self._isolated_pipes) or is_anim_backtrack,
                cut_mark: bool = (is_min_cut_mode and is_focus_pipe),
                dimmed_ctx: bool = is_dimmed_context,
            ) -> None:
                outline_c = (
                    QColor("#7F1D1D")
                    if blocked
                    else (QColor(110, 120, 130, 110) if dimmed_ctx else QColor(theme.INK_PRIMARY))
                )
                draw_capsule_3d(
                    painter,
                    a,
                    b,
                    rad,
                    col,
                    outline_color=outline_c,
                    highlight_color=hl,
                    dashed=(dashed_flag and not blocked),
                )
                if cut_mark:
                    mx = 0.5 * (a.x() + b.x())
                    my = 0.5 * (a.y() + b.y())
                    dx_s = b.x() - a.x()
                    dy_s = b.y() - a.y()
                    slen = max(1.0, math.hypot(dx_s, dy_s))
                    nx_p = -dy_s / slen
                    ny_p = dx_s / slen
                    bar_len = max(7.0, rad + 4.5)
                    painter.setPen(QPen(QColor("#F59E0B"), 3.2))
                    painter.drawLine(
                        QPointF(mx - nx_p * bar_len, my - ny_p * bar_len),
                        QPointF(mx + nx_p * bar_len, my + ny_p * bar_len),
                    )
                if blocked:
                    mx = 0.5 * (a.x() + b.x())
                    my = 0.5 * (a.y() + b.y())
                    s = max(4.0, rad + 2.5)
                    painter.setPen(QPen(QColor("#EF4444"), 2.2))
                    painter.drawLine(QPointF(mx - s, my - s), QPointF(mx + s, my + s))
                    painter.drawLine(QPointF(mx - s, my + s), QPointF(mx + s, my - s))

            render_queue.append((avg_d, 1 if not is_focus_pipe else 3, _draw_pipe))

            # Partículas 3D de flujo en vivo o trazadores de ruta
            has_live_flow = (
                self._is_playing
                and self._map_mode == "instant"
                and anim is None
                and not is_blocked
                and ps is not None
                and ps.flow_m3s > 1e-5
                and ps.conveyed_flow_m3s > 1e-5
            )
            has_route_pulse = (
                is_focus_pipe
                and not is_blocked
                and not is_min_cut_mode
                and (self._is_playing or anim is not None or bool(self._ordered_route_pipes))
            )
            if (has_live_flow or has_route_pulse) and pipe.from_node in prof.node_xy and pipe.to_node in prof.node_xy:
                fx, fy = prof.node_xy[pipe.from_node]
                tx, ty = prof.node_xy[pipe.to_node]
                fz = self._z_to_world(prof.node_z.get(pipe.from_node, 0.0))
                tz = self._z_to_world(prof.node_z.get(pipe.to_node, 0.0))

                seg_px = math.hypot(pt2.x() - pt1.x(), pt2.y() - pt1.y())
                n_particles = 3 if (is_focus_pipe or seg_px > 65.0 or is_overloaded) else 2
                vel_eff = max(0.6, min(3.2, eff_vel_ms if ps is None else max(eff_vel_ms, ps.effective_velocity_ms)))
                base_t = self._effect_time_s if has_route_pulse and not self._is_playing else self._pulse_time_s
                phase_off = (route_idx_map.get(pipe.pipe_id, 0) * 0.17) if is_focus_pipe else 0.0
                speed_norm = (0.38 if has_route_pulse else 0.24) * vel_eff

                p_color = (
                    QColor("#FFFFFF")
                    if is_focus_pipe
                    else (QColor("#FEF08A") if is_overloaded else QColor("#E0F2FE"))
                )
                p_alpha = 240 if is_focus_pipe else (110 if is_dimmed_context else 210)
                p_color.setAlpha(p_alpha)
                p_rad = max(1.8, min(3.6, radius_px * (0.78 if is_focus_pipe else 0.62)))

                for k_p in range(n_particles):
                    t_pos = (base_t * speed_norm + phase_off + k_p / float(n_particles)) % 1.0
                    t_tail = max(0.0, t_pos - 0.12)
                    px_w = fx + (tx - fx) * t_pos
                    py_w = fy + (ty - fy) * t_pos
                    pz_w = fz + (tz - fz) * t_pos
                    tx_w = fx + (tx - fx) * t_tail
                    ty_w = fy + (ty - fy) * t_tail
                    tz_w = fz + (tz - fz) * t_tail
                    pr_head = cam.project_point(px_w, py_w, pz_w, w, h)
                    pr_tail = cam.project_point(tx_w, ty_w, tz_w, w, h)

                    def _draw_particle(
                        hp: QPointF = QPointF(pr_head.x, pr_head.y),
                        tp: QPointF = QPointF(pr_tail.x, pr_tail.y),
                        rad_p: float = p_rad,
                        col_p: QColor = p_color,
                        glow_c: Optional[QColor] = QColor(theme.ACCENT_PRIMARY) if is_focus_pipe else None,
                    ) -> None:
                        if glow_c is not None:
                            painter.setPen(QPen(glow_c, rad_p * 1.9, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                            painter.drawLine(tp, hp)
                        painter.setPen(QPen(col_p, rad_p * 1.25, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                        painter.drawLine(tp, hp)
                        painter.setPen(Qt.PenStyle.NoPen)
                        painter.setBrush(QBrush(col_p))
                        painter.drawEllipse(hp, rad_p, rad_p)

                    render_queue.append((pr_head.depth - 0.008, 3, _draw_particle))

        # 3. Nodos, columnas piezométricas y charcos de rebose
        v_max = res.config.max_manhole_storage_m3 if res is not None else 4.0
        v_max = max(1e-6, float(v_max))
        use_global_mode = self._map_mode in ("peak", "overload_minutes")

        for node in graph.nodes():
            nid = node.node_id
            np_pt = node_proj.get(nid)
            gp_pt = ground_proj.get(nid)
            if np_pt is None or gp_pt is None:
                continue

            wx, wy = prof.node_xy[nid]
            node_z_m = prof.node_z.get(nid, 0.0)
            ground_z_m = prof.ground_z.get(nid, 1.5)

            persp_w = max(0.75, min(1.8, np_pt.scale / 220.0))
            base_nr = 5.8 if node.node_type in ("source", "sink") else 4.2
            nr = base_nr * persp_w
            hit_nodes.append((nid, np_pt.x, np_pt.y, nr, np_pt.depth))

            is_selected = nid == self._selected_node_id
            is_hovered = self._hover_kind == "node" and self._hover_id == nid
            is_anim_cur = anim is not None and nid == anim.cursor_node
            is_anim_front = anim is not None and nid in anim.active_nodes
            is_anim_vis = anim is not None and nid in anim.visited_nodes
            is_hl = (
                is_anim_cur
                or is_anim_front
                or (nid in self._highlight_node_ids if anim is None else is_anim_vis)
            )
            is_dimmed_ctx = has_hl_focus and not (is_hl or is_anim_vis or is_selected)
            is_dimmed = (
                (self._basin_active and nid not in self._basin_nodes)
                or (nid in self._isolated_nodes)
                or is_dimmed_ctx
            )

            if node.node_type == "source":
                n_fill = QColor(theme.NODE_SOURCE_FILL)
                n_edge = QColor(theme.NODE_SOURCE_BORDER)
            elif node.node_type == "sink":
                n_fill = QColor(theme.NODE_SINK_FILL)
                n_edge = QColor(theme.NODE_SINK_BORDER)
            else:
                n_fill = QColor(theme.NODE_MANHOLE_FILL)
                n_edge = QColor(theme.NODE_MANHOLE_BORDER)

            if is_dimmed:
                n_fill.setAlpha(95 if is_dimmed_ctx else 140)
                n_edge.setAlpha(95 if is_dimmed_ctx else 140)

            pulse_phase = (self._effect_time_s * 1.4) % 1.0

            def _draw_node(
                pt: ProjectedPoint = np_pt,
                rad: float = nr,
                fc: QColor = n_fill,
                ec: QColor = n_edge,
                sel: bool = is_selected,
                hov: bool = is_hovered,
                hl: bool = is_hl,
                cur: bool = is_anim_cur,
                front: bool = is_anim_front,
                vis: bool = is_anim_vis,
                p_ph: float = pulse_phase,
            ) -> None:
                center = QPointF(pt.x, pt.y)
                if cur or front or sel or hl or hov or vis:
                    if sel:
                        ring_col = QColor(theme.PIPE_SELECTED_HALO)
                    elif cur:
                        ring_col = QColor("#F59E0B")
                    elif front:
                        ring_col = QColor("#0EA5E9")
                    elif is_min_cut_mode and hl:
                        ring_col = QColor("#DC2626")
                    else:
                        ring_col = QColor(theme.ACCENT_PRIMARY)
                    painter.setPen(QPen(ring_col, 2.6 if (cur or front or sel) else 2.0))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawEllipse(center, rad + 3.2, rad + 3.2)
                    if cur:
                        ripple_r = rad + 3.5 + p_ph * 8.5
                        rc = QColor("#F59E0B")
                        rc.setAlpha(int(190 * (1.0 - p_ph)))
                        painter.setPen(QPen(rc, 1.8))
                        painter.drawEllipse(center, ripple_r, ripple_r)
                painter.setPen(QPen(ec, 1.3))
                painter.setBrush(QBrush(fc))
                painter.drawEllipse(center, rad, rad)

            render_queue.append((np_pt.depth, 2 if not is_hl else 3, _draw_node))

            # Estado piezométrico y rebose del pozo / fuente
            stored_m3 = 0.0
            flood_m3 = 0.0
            flood_rate_m3s = 0.0
            active_ponding_m3 = 0.0
            if use_global_mode and res is not None:
                stored_m3 = float(res.max_manhole_storage_m3.get(nid, 0.0))
                flood_m3 = float(res.max_node_flooding_m3.get(nid, 0.0))
                active_ponding_m3 = flood_m3
            elif snap is not None and nid in snap.node_states:
                ns = snap.node_states[nid]
                stored_m3 = float(ns.stored_volume_m3)
                flood_m3 = float(ns.surface_flooding_m3)
                flood_rate_m3s = float(ns.flooding_rate_m3s)
                # En modo instantáneo, la lámina superficial se disipa tras la lluvia
                active_ponding_m3 = float(getattr(ns, "active_surface_ponding_m3", 0.0))
                if active_ponding_m3 <= 0.0 and flood_rate_m3s > 1e-9:
                    active_ponding_m3 = flood_m3

            # En modo instantáneo, la columna piezométrica solo supera la rasante si hay rebose activo
            is_active_overflow = (
                (flood_m3 > 1e-6) if use_global_mode else (flood_rate_m3s > 1e-9)
            )
            has_surface_puddle = (
                (flood_m3 > 1e-6)
                if use_global_mode
                else (is_active_overflow or active_ponding_m3 > 1e-3)
            )

            if is_active_overflow:
                ref_vol = flood_m3 if use_global_mode else max(1.0, active_ponding_m3)
                extra_m = min(6.0, 0.9 + 0.65 * math.log10(1.0 + max(0.0, ref_vol)))
                top_z_m = ground_z_m + extra_m
                col_color = QColor("#EF4444")
            elif stored_m3 > 1e-4:
                fill_frac = max(0.0, min(1.0, stored_m3 / v_max))
                top_z_m = node_z_m + fill_frac * (ground_z_m - node_z_m)
                col_color = QColor("#F59E0B") if fill_frac >= 0.75 else QColor("#3B82F6")
            else:
                top_z_m = node_z_m
                col_color = None

            if col_color is not None and top_z_m > node_z_m + 1e-4:
                top_pt = cam.project_point(wx, wy, self._z_to_world(top_z_m), w, h)
                col_r = max(2.6, nr * 0.62)
                col_depth = 0.5 * (np_pt.depth + top_pt.depth)

                def _draw_piezo(
                    b_pt: QPointF = QPointF(np_pt.x, np_pt.y),
                    t_pt: QPointF = QPointF(top_pt.x, top_pt.y),
                    rad: float = col_r,
                    cc: QColor = col_color,
                ) -> None:
                    draw_vertical_cylinder_3d(painter, b_pt, t_pt, rad, cc, alpha=220)

                render_queue.append((col_depth, 3, _draw_piezo))

            if has_surface_puddle:
                puddle_vol = flood_m3 if use_global_mode else active_ponding_m3
                puddle_r_w = min(0.14, 0.026 + 0.0020 * math.sqrt(max(0.0, puddle_vol)))
                puddle_z_w = self._z_to_world(ground_z_m + 0.05)
                pulse_r = (
                    puddle_r_w * (1.0 + 0.14 * math.sin(self._effect_time_s * 4.5))
                    if (self._is_playing and is_active_overflow)
                    else puddle_r_w
                )

                def _draw_puddle(
                    cx: float = wx,
                    cy: float = wy,
                    cz: float = puddle_z_w,
                    rw: float = pulse_r,
                    intense: bool = puddle_vol >= 25.0 and is_active_overflow,
                    active_ov: bool = is_active_overflow or use_global_mode,
                ) -> None:
                    alpha_p = (125 if intense else 100) if active_ov else 90
                    fill = QColor(239, 68, 68, alpha_p)
                    border = QColor("#991B1B" if intense else ("#EF4444" if active_ov else "#DC2626"))
                    draw_projected_ellipse_3d(
                        painter,
                        cam,
                        (cx, cy, cz),
                        rw,
                        rw,
                        w,
                        h,
                        fill,
                        border,
                        border_width=1.35 if active_ov else 1.15,
                        segments=18,
                    )

                render_queue.append((gp_pt.depth, 4, _draw_puddle))

        # Ordenar pintor: mayor profundidad primero, luego orden de capa
        render_queue.sort(key=lambda item: (-item[0], item[1]))
        for _d, _layer, fn in render_queue:
            fn()

        self._hit_nodes = hit_nodes
        self._hit_pipes = hit_pipes

        # 4. Etiquetas de nodos esenciales sobre la escena ordenada
        if self._show_pipe_labels:
            painter.setFont(QFont(self._mono_font, 7, QFont.Weight.Bold))
            placed: List[QRectF] = []
            for node in graph.nodes():
                nid = node.node_id
                pt = node_proj.get(nid)
                if pt is None:
                    continue
                is_key = (
                    node.node_type in ("source", "sink")
                    or nid == self._selected_node_id
                    or nid == self._hover_id
                    or nid in self._highlight_node_ids
                    or (anim is not None and (nid == anim.cursor_node or nid in anim.active_nodes))
                )
                if not is_key and cam.zoom < 1.15:
                    continue
                lbl = f"PTAR {nid}" if node.node_type == "sink" else nid
                bw = 44.0 if node.node_type == "sink" else 22.0
                rect = QRectF(pt.x - bw * 0.5, pt.y - 17.0, bw, 13.0)
                if any(rect.intersects(r) for r in placed):
                    continue
                placed.append(rect)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(255, 255, 227, 225)))
                painter.drawRect(rect)
                painter.setPen(QColor(theme.INK_PRIMARY))
                painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, lbl)

        if min_cut_badges:
            painter.setFont(QFont(self._mono_font, 7, QFont.Weight.Bold))
            for bx, by, pid in min_cut_badges:
                badge = QRectF(bx - 34.0, by - 18.0, 68.0, 14.0)
                painter.setPen(QPen(QColor("#F59E0B"), 1.0))
                painter.setBrush(QBrush(QColor("#991B1B")))
                painter.drawRect(badge)
                painter.setPen(QColor("#FFFFFF"))
                painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, f"{pid} CORTE")

        painter.setPen(QPen(QColor(theme.DOCK_BORDER), 1.0))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(0.5, 0.5, max(1.0, w - 1.0), max(1.0, h - 1.0)))
        painter.end()

    # ------------------------------------------------------------------
    # Picking 3D, órbita, paneo, zoom y tooltip
    # ------------------------------------------------------------------

    def _hit_test(self, px: float, py: float) -> Tuple[Optional[str], Optional[str]]:
        best_node: Optional[Tuple[float, str]] = None
        for nid, nx, ny, nr, depth in self._hit_nodes:
            r_hit = max(10.0, nr + 4.0)
            dist_sq = (px - nx) ** 2 + (py - ny) ** 2
            if dist_sq <= r_hit * r_hit:
                if best_node is None or depth < best_node[0]:
                    best_node = (depth, nid)
        if best_node is not None:
            return "node", best_node[1]

        best_pipe: Optional[Tuple[float, str]] = None
        max_d2 = 8.0 * 8.0
        for pid, x1, y1, x2, y2, depth in self._hit_pipes:
            d2 = point_to_segment_distance_sq(px, py, x1, y1, x2, y2)
            if d2 <= max_d2:
                if best_pipe is None or depth < best_pipe[0]:
                    best_pipe = (depth, pid)
        if best_pipe is not None:
            return "pipe", best_pipe[1]

        return None, None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if event.button() == Qt.MouseButton.RightButton or (
            event.button() == Qt.MouseButton.LeftButton
            and (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        ):
            self._drag_mode = "pan"
            self._drag_start = pos
            self._drag_last = pos
            self._drag_moved = False
            self.setCursor(Qt.CursorShape.SizeAllCursor)
            self._hide_tooltip()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_mode = "orbit"
            self._drag_start = pos
            self._drag_last = pos
            self._drag_moved = False
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self._hide_tooltip()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        pos = event.position()
        if self._drag_mode is not None and self._drag_last is not None:
            dx = pos.x() - self._drag_last.x()
            dy = pos.y() - self._drag_last.y()
            self._drag_last = pos
            if self._drag_start is not None:
                total_move = math.hypot(
                    pos.x() - self._drag_start.x(), pos.y() - self._drag_start.y()
                )
                if total_move > 4.0:
                    self._drag_moved = True
            if self._drag_mode == "pan":
                self._camera.pan(dx, dy)
            else:
                self._camera.orbit(dx, dy)
            self.update()
            event.accept()
            return

        kind, eid = self._hit_test(pos.x(), pos.y())
        if kind != self._hover_kind or eid != self._hover_id:
            self._hover_kind = kind
            self._hover_id = eid
            self.update()
        if kind and eid:
            self._show_tooltip(kind, eid, event.globalPosition().toPoint())
        else:
            self._hide_tooltip()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode is not None:
            was_click = not self._drag_moved and event.button() == Qt.MouseButton.LeftButton
            self._drag_mode = None
            self._drag_start = None
            self._drag_last = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            if was_click:
                pos = event.position()
                kind, eid = self._hit_test(pos.x(), pos.y())
                if kind == "node" and eid is not None:
                    self.select_node(eid)
                    self.nodeSelected.emit(eid)
                elif kind == "pipe" and eid is not None:
                    self.select_pipe(eid)
                    self.pipeSelected.emit(eid)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_camera()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.12 if delta > 0 else (1.0 / 1.12)
        self._camera.zoom_by(factor)
        self.update()
        event.accept()

    def leaveEvent(self, event) -> None:
        self._hover_kind = None
        self._hover_id = None
        self._hide_tooltip()
        super().leaveEvent(event)

    def _show_tooltip(self, kind: str, eid: str, global_pos: QPoint) -> None:
        if self._graph is None or self._profile is None:
            return
        key = f"{kind}:{eid}:{self._map_mode}:{id(self._snapshot)}"
        if key != self._last_hover_key:
            self._last_hover_key = key
            lines: List[str] = []
            if kind == "node":
                node = self._graph.get_node(eid)
                if node is not None:
                    z_m = self._profile.node_z.get(eid, 0.0)
                    gz_m = self._profile.ground_z.get(eid, 1.5)
                    lines.append(f"NODO {eid} ({node.node_type.upper()})")
                    lines.append(f"Cota z: {z_m:.2f} m · Rasante ref.: {gz_m:.2f} m")
                    if self._map_mode in ("peak", "overload_minutes") and self._result is not None:
                        st = self._result.max_manhole_storage_m3.get(eid, 0.0)
                        fl = self._result.max_node_flooding_m3.get(eid, 0.0)
                        lines.append(f"Pozo máx.: {st:.2f} m³ · Rebose máx.: {fl:.2f} m³")
                    elif self._snapshot is not None and eid in self._snapshot.node_states:
                        ns = self._snapshot.node_states[eid]
                        pond = getattr(ns, "active_surface_ponding_m3", 0.0)
                        lines.append(
                            f"Pozo: {ns.stored_volume_m3:.2f} m³ · Charco vía: {pond:.2f} m³"
                        )
                        lines.append(
                            f"Rebose activo: {ns.flooding_rate_m3s:.4f} m³/s · Acum.: {ns.surface_flooding_m3:.2f} m³"
                        )
            else:
                pipe = self._graph.get_pipe(eid)
                if pipe is not None:
                    inv = self._interventions.get(eid)
                    _qm, _v, _t, eff_d = resolve_pipe_hydraulics(pipe, inv)
                    lines.append(f"TUBERÍA {eid} ({pipe.from_node} → {pipe.to_node})")
                    lines.append(f"Ø {eff_d:.0f}\" · L={pipe.length_m:.1f} m · S={pipe.slope:.4f}")
                    ps = self._snapshot.pipe_states.get(eid) if self._snapshot is not None else None
                    if (inv and inv.is_closed) or (ps and ps.is_closed):
                        lines.append("Estado: BLOQUEADA 100%")
                    elif self._map_mode == "peak" and self._result is not None:
                        pk = self._result.peak_pipe_utilization.get(eid, 0.0)
                        lines.append(f"Pico utilización: {pk:.1f}%")
                    elif self._map_mode == "overload_minutes" and self._result is not None:
                        ov = self._result.pipe_overloaded_minutes.get(eid, 0.0)
                        lines.append(f"Sobrecarga acumulada: {ov:.0f} min")
                    elif ps is not None:
                        lines.append(f"Caudal: {ps.flow_m3s:.4f} m³/s · Uso: {ps.utilization_pct:.1f}%")

            if not lines:
                self._hide_tooltip()
                return
            if self._tooltip is None:
                self._tooltip = _Tooltip3DPopup(self._ui_font, self)
            self._tooltip.setText("\n".join(lines))
            self._tooltip.adjustSize()

        if self._tooltip is not None:
            screen = QGuiApplication.screenAt(global_pos) or QGuiApplication.primaryScreen()
            x = global_pos.x() + 14
            y = global_pos.y() + 14
            if screen is not None:
                ag = screen.availableGeometry()
                tw = self._tooltip.width()
                th = self._tooltip.height()
                x = min(x, ag.right() - tw - 8)
                y = min(y, ag.bottom() - th - 8)
            self._tooltip.move(x, y)
            self._tooltip.show()

    def _hide_tooltip(self) -> None:
        self._last_hover_key = None
        if self._tooltip is not None and self._tooltip.isVisible():
            self._tooltip.hide()
