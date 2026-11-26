"""Visor 3D compacto de corte longitudinal para una tubería y su pozo aguas arriba."""

import math
from typing import Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import QSizePolicy, QWidget

from src.data_structures import PipeEdge
from src.simulation.models import (
    NodeStepState,
    PipeIntervention,
    PipeStepState,
    resolve_pipe_hydraulics,
)
from .. import theme
from .projection import shade_color


class PipeInspector3DWidget(QWidget):
    """Corte longitudinal isométrico de una tubería, lámina de agua, obstrucción y pozo."""

    def __init__(
        self,
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._ui_font = ui_font
        self._mono_font = mono_font

        self.setMinimumHeight(128)
        self.setMaximumHeight(132)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.OpenHandCursor)

        self._edge: Optional[PipeEdge] = None
        self._pipe_state: Optional[PipeStepState] = None
        self._upstream_state: Optional[NodeStepState] = None
        self._intervention: Optional[PipeIntervention] = None
        self._max_manhole_storage_m3: float = 4.0

        self._yaw_offset: float = 0.0
        self._pitch_offset: float = 0.0
        self._drag_pos: Optional[QPointF] = None

        # Estado calculado expuesto para render y pruebas
        self._render_mode: str = "empty"
        self._fill_ratio: float = 0.0
        self._has_backwater: bool = False
        self._status_badge_text: str = "Sin selección"
        self._eff_diam_in: float = 0.0
        self._eff_q_max: float = 0.0
        self._obstruction_pct: float = 0.0
        self._is_closed: bool = False
        self._manhole_fill_ratio: float = 0.0
        self._manhole_overflowing: bool = False
        self._fluid_color: QColor = QColor("#2563EB")

    @property
    def render_mode(self) -> str:
        return self._render_mode

    @property
    def fill_ratio(self) -> float:
        return self._fill_ratio

    @property
    def has_backwater(self) -> bool:
        return self._has_backwater

    @property
    def status_badge_text(self) -> str:
        return self._status_badge_text

    def reset_view(self) -> None:
        self._yaw_offset = 0.0
        self._pitch_offset = 0.0
        self.update()

    def update_state(
        self,
        edge: Optional[PipeEdge],
        pipe_state: Optional[PipeStepState],
        upstream_node_state: Optional[NodeStepState],
        intervention: Optional[PipeIntervention],
        max_manhole_storage_m3: float = 4.0,
    ) -> None:
        self._edge = edge
        self._pipe_state = pipe_state
        self._upstream_state = upstream_node_state
        self._intervention = intervention
        self._max_manhole_storage_m3 = max(1e-6, float(max_manhole_storage_m3))
        self._recompute_visual_state()
        self.update()

    def _recompute_visual_state(self) -> None:
        edge = self._edge
        ps = self._pipe_state
        ups = self._upstream_state
        inv = self._intervention

        if edge is None:
            self._render_mode = "empty"
            self._fill_ratio = 0.0
            self._has_backwater = False
            self._status_badge_text = "Seleccione una tubería"
            self._eff_diam_in = 0.0
            self._eff_q_max = 0.0
            self._obstruction_pct = 0.0
            self._is_closed = False
            self._manhole_fill_ratio = 0.0
            self._manhole_overflowing = False
            return

        eff_qmax, _eff_vel, _eff_t, eff_diam_in = resolve_pipe_hydraulics(edge, inv)
        if ps is not None and ps.effective_q_max_m3s is not None:
            eff_qmax = float(ps.effective_q_max_m3s)

        obst_pct = float(inv.obstruction_pct) if inv is not None else 0.0
        is_closed = bool(
            (ps is not None and ps.is_closed)
            or (inv is not None and inv.is_closed)
            or (eff_qmax <= 1e-12)
        )

        upstream_stored_m3 = float(ups.stored_volume_m3) if ups is not None else 0.0
        upstream_flooding_m3 = float(ups.surface_flooding_m3) if ups is not None else 0.0
        upstream_flooding_rate_m3s = float(ups.flooding_rate_m3s) if ups is not None else 0.0

        self._eff_diam_in = float(eff_diam_in)
        self._eff_q_max = float(eff_qmax)
        self._obstruction_pct = max(0.0, min(100.0, obst_pct))
        self._is_closed = is_closed

        if is_closed:
            has_backwater = bool(
                (ps is not None and ps.demand_flow_m3s > 1e-9)
                or (ps is not None and ps.excess_flow_m3s > 1e-9)
                or (upstream_stored_m3 > 1e-6)
                or (upstream_flooding_m3 > 1e-6)
                or (upstream_flooding_rate_m3s > 1e-9)
            )
            self._has_backwater = has_backwater
            if has_backwater:
                self._render_mode = "blocked_backwater"
                self._fill_ratio = 1.0
                self._manhole_fill_ratio = 1.0
                self._manhole_overflowing = True
                self._fluid_color = QColor("#DC2626")
                self._status_badge_text = "BLOQUEADA 100% · REPRESADA"
            else:
                self._render_mode = "blocked_dry"
                self._fill_ratio = 0.0
                self._manhole_fill_ratio = 0.0
                self._manhole_overflowing = False
                self._fluid_color = QColor("#64748B")
                self._status_badge_text = "BLOQUEADA 100% · SIN DEMANDA"
            return

        # Caso normal o con obstrucción parcial (nunca dividir entre eff_q_max)
        u_pct = float(ps.utilization_pct) if ps is not None else 0.0
        rho = min(1.0, max(0.0, u_pct / 100.0))
        self._has_backwater = False
        self._render_mode = "normal"
        self._fill_ratio = rho
        self._manhole_fill_ratio = min(
            1.0, max(0.0, upstream_stored_m3 / self._max_manhole_storage_m3)
        )
        self._manhole_overflowing = bool(
            u_pct > 100.0
            or upstream_flooding_m3 > 1e-6
            or upstream_flooding_rate_m3s > 1e-9
        )
        if u_pct > 100.0:
            self._fluid_color = QColor("#DC2626")
        elif u_pct > 75.0:
            self._fluid_color = QColor("#D97706")
        else:
            self._fluid_color = QColor("#2563EB")

        flow_val = float(ps.flow_m3s) if ps is not None else 0.0
        self._status_badge_text = f"U {u_pct:.0f}% · Q {flow_val:.3f} m³/s"

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_pos is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.position() - self._drag_pos
            self._drag_pos = event.position()
            self._yaw_offset = max(-0.55, min(0.55, self._yaw_offset + delta.x() * 0.006))
            self._pitch_offset = max(
                -0.25, min(0.25, self._pitch_offset + delta.y() * 0.004)
            )
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self._drag_pos = None
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_view()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        w = float(self.width())
        h = float(self.height())
        painter.fillRect(QRectF(0, 0, w, h), QColor(theme.CANVAS_BG))
        painter.setPen(QPen(QColor(theme.DOCK_BORDER), 1.0))
        painter.drawRect(QRectF(0.5, 0.5, max(1.0, w - 1.0), max(1.0, h - 1.0)))

        if self._edge is None:
            painter.setFont(QFont(self._ui_font, 8))
            painter.setPen(QColor(theme.INK_MUTED))
            painter.drawText(
                QRectF(8, 8, w - 16, h - 16),
                Qt.AlignmentFlag.AlignCenter,
                "Seleccione una tubería para ver su corte 3D.",
            )
            painter.end()
            return

        edge = self._edge
        ps = self._pipe_state

        # Geometría isométrica inclinada según pendiente real y ángulo de rotación
        slope_raw = float(edge.slope) if math.isfinite(edge.slope) else 0.01
        slope_norm = slope_raw / 100.0 if slope_raw > 0.25 else max(0.0, slope_raw)
        slope_drop_px = min(14.0, max(3.5, slope_norm * 550.0)) + self._pitch_offset * 14.0

        left_shift = self._yaw_offset * 16.0
        mh_cx = max(44.0, w * 0.16 + left_shift * 0.4)
        mh_w = 24.0
        ground_y = 30.0
        pipe_left_x = mh_cx + mh_w * 0.5
        pipe_right_x = max(pipe_left_x + 70.0, w - 26.0 + left_shift * 0.25)

        diam_factor = max(0.70, min(1.38, self._eff_diam_in / 14.0))
        pipe_r = max(12.0, min(20.0, 15.5 * diam_factor))
        inlet_cy = h * 0.62 - slope_drop_px * 0.5
        outlet_cy = inlet_cy + slope_drop_px
        ell_rx = max(4.5, pipe_r * 0.36 * (1.0 - abs(self._yaw_offset) * 0.35))

        # 1. Línea de rasante y sombreado de suelo sobre el pozo aguas arriba
        painter.setPen(QPen(QColor(theme.INK_MUTED), 1.0, Qt.PenStyle.DashLine))
        painter.drawLine(QPointF(10.0, ground_y), QPointF(w - 10.0, ground_y + slope_drop_px * 0.35))

        # 2. Pozo aguas arriba (from_node)
        mh_x0 = mh_cx - mh_w * 0.5
        mh_bot_y = inlet_cy + pipe_r + 3.0
        mh_rect = QRectF(mh_x0, ground_y, mh_w, mh_bot_y - ground_y)
        painter.setPen(QPen(QColor(theme.INK_PRIMARY), 1.3))
        painter.setBrush(QBrush(QColor(theme.PAPER_SUBTLE)))
        painter.drawRect(mh_rect)

        if self._manhole_fill_ratio > 0.01 or self._manhole_overflowing:
            fill_col = (
                QColor("#DC2626")
                if self._manhole_overflowing
                else (QColor("#D97706") if self._manhole_fill_ratio >= 0.75 else QColor("#3B82F6"))
            )
            fill_h = (mh_bot_y - ground_y) * min(1.0, max(0.12, self._manhole_fill_ratio))
            water_y0 = ground_y if self._manhole_overflowing else (mh_bot_y - fill_h)
            wgrad = QLinearGradient(mh_x0, water_y0, mh_x0 + mh_w, water_y0)
            wgrad.setColorAt(0.0, shade_color(fill_col, 1.18, 210))
            wgrad.setColorAt(1.0, shade_color(fill_col, 0.78, 225))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(wgrad))
            painter.drawRect(QRectF(mh_x0 + 1.0, water_y0, mh_w - 2.0, mh_bot_y - water_y0 - 0.5))

            if self._manhole_overflowing:
                plume_col = QColor("#EF4444")
                plume_col.setAlpha(205)
                painter.setBrush(QBrush(plume_col))
                painter.setPen(QPen(QColor("#991B1B"), 1.0))
                painter.drawEllipse(QPointF(mh_cx, ground_y - 1.5), mh_w * 0.85, 4.2)

        # 3. Cuerpo exterior de la tubería en corte longitudinal
        top_l = QPointF(pipe_left_x, inlet_cy - pipe_r)
        top_r = QPointF(pipe_right_x, outlet_cy - pipe_r)
        bot_l = QPointF(pipe_left_x, inlet_cy + pipe_r)
        bot_r = QPointF(pipe_right_x, outlet_cy + pipe_r)

        barrel_poly = QPolygonF([top_l, top_r, bot_r, bot_l])
        bgrad = QLinearGradient(0.0, inlet_cy - pipe_r, 0.0, inlet_cy + pipe_r)
        bgrad.setColorAt(0.0, QColor("#E2E4D5"))
        bgrad.setColorAt(0.5, QColor("#F5F5E1"))
        bgrad.setColorAt(1.0, QColor("#C6C9BA"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(bgrad))
        painter.drawPolygon(barrel_poly)

        # 4. Relleno hidráulico dentro del tubo (normal / parcial / bloqueo 100%)
        mid_x = 0.5 * (pipe_left_x + pipe_right_x)
        mid_cy = 0.5 * (inlet_cy + outlet_cy)

        if self._is_closed:
            if self._has_backwater:
                # Mitad aguas arriba represada al 100% en rojo alerta; aguas abajo vacía
                up_poly = QPolygonF(
                    [
                        top_l,
                        QPointF(mid_x, mid_cy - pipe_r),
                        QPointF(mid_x, mid_cy + pipe_r),
                        bot_l,
                    ]
                )
                ugrad = QLinearGradient(0.0, inlet_cy - pipe_r, 0.0, inlet_cy + pipe_r)
                ugrad.setColorAt(0.0, QColor(239, 68, 68, 225))
                ugrad.setColorAt(1.0, QColor(153, 27, 27, 240))
                painter.setBrush(QBrush(ugrad))
                painter.drawPolygon(up_poly)

            # Tapón / compuerta física rayada al centro del tramo
            plug_w = 12.0
            plug_poly = QPolygonF(
                [
                    QPointF(mid_x - plug_w * 0.5, mid_cy - pipe_r - 1.5),
                    QPointF(mid_x + plug_w * 0.5, mid_cy - pipe_r - 1.5),
                    QPointF(mid_x + plug_w * 0.5, mid_cy + pipe_r + 1.5),
                    QPointF(mid_x - plug_w * 0.5, mid_cy + pipe_r + 1.5),
                ]
            )
            painter.setPen(QPen(QColor("#7F1D1D"), 1.5))
            painter.setBrush(QBrush(QColor("#3F3F46")))
            painter.drawPolygon(plug_poly)

            hatch_pen = QPen(QColor("#EF4444"), 1.6)
            painter.setPen(hatch_pen)
            for off in (-pipe_r * 0.55, 0.0, pipe_r * 0.55):
                painter.drawLine(
                    QPointF(mid_x - plug_w * 0.42, mid_cy + off - 3.5),
                    QPointF(mid_x + plug_w * 0.42, mid_cy + off + 3.5),
                )
        else:
            # Obstrucción parcial en la solera si 0 < obstruction_pct < 100
            obst_h = 0.0
            if self._obstruction_pct > 1e-3:
                obst_h = (2.0 * pipe_r) * (self._obstruction_pct / 100.0) * 0.85
                sed_poly = QPolygonF(
                    [
                        QPointF(pipe_left_x + (pipe_right_x - pipe_left_x) * 0.25, inlet_cy + pipe_r + (outlet_cy - inlet_cy) * 0.25 - obst_h),
                        QPointF(pipe_left_x + (pipe_right_x - pipe_left_x) * 0.75, inlet_cy + pipe_r + (outlet_cy - inlet_cy) * 0.75 - obst_h),
                        QPointF(pipe_left_x + (pipe_right_x - pipe_left_x) * 0.75, inlet_cy + pipe_r + (outlet_cy - inlet_cy) * 0.75),
                        QPointF(pipe_left_x + (pipe_right_x - pipe_left_x) * 0.25, inlet_cy + pipe_r + (outlet_cy - inlet_cy) * 0.25),
                    ]
                )
                painter.setPen(QPen(QColor(theme.INK_PRIMARY), 1.0))
                painter.setBrush(QBrush(QColor("#78716C")))
                painter.drawPolygon(sed_poly)

            # Lámina de agua proporcional a rho = min(1.0, utilization_pct / 100.0)
            if self._fill_ratio > 0.01:
                water_h = max(2.5, (2.0 * pipe_r) * self._fill_ratio)
                w_poly = QPolygonF(
                    [
                        QPointF(pipe_left_x, inlet_cy + pipe_r - water_h),
                        QPointF(pipe_right_x, outlet_cy + pipe_r - water_h),
                        bot_r,
                        bot_l,
                    ]
                )
                fgrad = QLinearGradient(0.0, inlet_cy + pipe_r - water_h, 0.0, inlet_cy + pipe_r)
                fgrad.setColorAt(0.0, shade_color(self._fluid_color, 1.18, 215))
                fgrad.setColorAt(1.0, shade_color(self._fluid_color, 0.78, 235))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(fgrad))
                painter.drawPolygon(w_poly)

        # 5. Contornos del tubo y sección de salida elíptica
        painter.setPen(QPen(QColor(theme.INK_PRIMARY), 1.4))
        painter.drawLine(top_l, top_r)
        painter.drawLine(bot_l, bot_r)

        painter.setBrush(QBrush(QColor(theme.PAPER_SUBTLE)))
        painter.drawEllipse(QPointF(pipe_right_x, outlet_cy), ell_rx, pipe_r)
        if not self._is_closed and self._fill_ratio > 0.01:
            clip_h = (2.0 * pipe_r) * self._fill_ratio
            painter.save()
            painter.setClipRect(
                QRectF(
                    pipe_right_x - ell_rx - 1.0,
                    outlet_cy + pipe_r - clip_h,
                    ell_rx * 2.0 + 2.0,
                    clip_h + 1.0,
                )
            )
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(shade_color(self._fluid_color, 0.92, 230)))
            painter.drawEllipse(QPointF(pipe_right_x, outlet_cy), ell_rx - 0.5, pipe_r - 0.5)
            painter.restore()

        # Flecha direccional de caudal cuando hay flujo conducido
        if not self._is_closed and ps is not None and ps.flow_m3s > 1e-6:
            ax1 = pipe_left_x + (pipe_right_x - pipe_left_x) * 0.38
            ay1 = inlet_cy + (outlet_cy - inlet_cy) * 0.38
            ax2 = pipe_left_x + (pipe_right_x - pipe_left_x) * 0.62
            ay2 = inlet_cy + (outlet_cy - inlet_cy) * 0.62
            apen = QPen(QColor(theme.PAPER_BG if self._fill_ratio >= 0.55 else theme.INK_PRIMARY), 1.6)
            painter.setPen(apen)
            painter.drawLine(QPointF(ax1, ay1), QPointF(ax2, ay2))
            painter.drawLine(QPointF(ax2 - 5.0, ay2 - 3.5), QPointF(ax2, ay2))
            painter.drawLine(QPointF(ax2 - 5.0, ay2 + 3.5), QPointF(ax2, ay2))

        # 6. Etiquetas compactas y distintivo de estado
        painter.setFont(QFont(self._mono_font, 7, QFont.Weight.Bold))
        painter.setPen(QColor(theme.INK_PRIMARY))
        painter.drawText(
            QRectF(8.0, 4.0, w - 16.0, 14.0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
            f"{edge.pipe_id} ({edge.from_node}→{edge.to_node}) · Ø{self._eff_diam_in:.0f}\" · S={slope_norm * 100:.1f}%",
        )

        painter.setPen(QColor(theme.INK_MUTED))
        painter.drawText(
            QRectF(max(4.0, mh_cx - 20.0), 17.0, 40.0, 12.0),
            Qt.AlignmentFlag.AlignCenter,
            edge.from_node,
        )

        # Insignia inferior derecha de estado hidráulico
        badge_bg = (
            QColor("#991B1B")
            if (self._is_closed and self._has_backwater) or (self._fill_ratio >= 1.0 and not self._is_closed and ps is not None and ps.utilization_pct > 100.0)
            else (QColor(theme.SHELL_BG) if self._is_closed else QColor(theme.ACCENT_PRIMARY))
        )
        badge_w = min(w - 16.0, 186.0)
        badge_rect = QRectF(w - badge_w - 6.0, h - 20.0, badge_w, 15.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(badge_bg))
        painter.drawRect(badge_rect)
        painter.setPen(QColor(theme.PALETTE_IVORY))
        painter.setFont(QFont(self._mono_font, 7, QFont.Weight.Bold))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self._status_badge_text)

        painter.end()
