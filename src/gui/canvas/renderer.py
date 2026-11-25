"""Renderizador puro con QPainter a partir de una escena calculada (CanvasScene)."""

import math
from typing import Dict, Optional

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPolygonF

from .. import theme
from .layout import CanvasScene, PipeVisual, PulseTrack


class CanvasRenderer:
    """Dibuja las 6 capas visuales del lienzo cartográfico sin estado propio."""

    _BASE_PX_PER_MPS = 28.0

    def __init__(self, ui_font: str = "Segoe UI") -> None:
        self.ui_font = ui_font

    def paint(
        self,
        painter: QPainter,
        scene: CanvasScene,
        *,
        pulse_time_s: float = 0.0,
        is_playing: bool = False,
        zoom: float = 1.0,
        pipe_color_overrides: Optional[Dict[str, str]] = None,
        route_transition_t: float = 1.0,
        effect_time_s: float = 0.0,
        has_active_traversal_anim: bool = False,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        self._draw_drafting_grid(painter, scene.width, scene.height)

        if scene.empty_message:
            font = QFont(self.ui_font)
            font.setPointSize(10)
            painter.setFont(font)
            painter.setPen(QColor(theme.INK_MUTED))
            painter.drawText(
                QRectF(0, 0, scene.width, scene.height),
                Qt.AlignmentFlag.AlignCenter,
                scene.empty_message,
            )
            return

        self._draw_pipes(
            painter,
            scene,
            pipe_color_overrides=pipe_color_overrides,
            route_transition_t=route_transition_t,
            effect_time_s=effect_time_s,
            is_playing=is_playing,
        )
        self._draw_particles(
            painter,
            scene,
            pulse_time_s=pulse_time_s,
            effect_time_s=effect_time_s,
            is_playing=is_playing,
            has_active_traversal_anim=has_active_traversal_anim,
            zoom=zoom,
        )
        self._draw_flood_rings(
            painter,
            scene,
            effect_time_s=effect_time_s,
            is_playing=is_playing,
        )
        self._draw_node_ripples(
            painter,
            scene,
            effect_time_s=effect_time_s,
            is_playing=is_playing,
            route_transition_t=route_transition_t,
            has_active_traversal_anim=has_active_traversal_anim,
        )
        self._draw_nodes(painter, scene)
        self._draw_badges(painter, scene)

    @staticmethod
    def _draw_drafting_grid(painter: QPainter, w: int, h: int) -> None:
        painter.fillRect(0, 0, w, h, QColor(theme.CANVAS_BG))
        minor = 36
        major = 144
        minor_pen = QPen(QColor(theme.CANVAS_GRID_MINOR), 1.0)
        major_pen = QPen(QColor(theme.CANVAS_GRID_MAJOR), 1.0)
        for gx in range(0, w, minor):
            painter.setPen(major_pen if gx % major == 0 else minor_pen)
            painter.drawLine(gx, 0, gx, h)
        for gy in range(0, h, minor):
            painter.setPen(major_pen if gy % major == 0 else minor_pen)
            painter.drawLine(0, gy, w, gy)

    @staticmethod
    def _draw_pipe_halo(
        painter: QPainter,
        p: PipeVisual,
        *,
        route_transition_t: float,
        effect_time_s: float,
        is_playing: bool,
    ) -> None:
        if not p.halo_color:
            return
        if not p.is_focus:
            pen = QPen(QColor(p.halo_color), p.halo_width)
            pen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(pen)
            painter.drawLine(QPointF(p.sx1, p.sy1), QPointF(p.halo_end_x, p.halo_end_y))
            if p.has_cushion:
                cpen = QPen(QColor(theme.CANVAS_BG), p.draw_width + 3.4)
                cpen.setCapStyle(Qt.PenCapStyle.FlatCap)
                painter.setPen(cpen)
                painter.drawLine(QPointF(p.sx1, p.sy1), QPointF(p.halo_end_x, p.halo_end_y))
            return

        t_clamped = max(0.0, min(1.0, route_transition_t))
        if t_clamped < 0.999 and p.route_total > 1 and p.route_index >= 0:
            start_f = (p.route_index / float(max(1, p.route_total))) * 0.55
            local_t = max(0.0, min(1.0, (t_clamped - start_f) / 0.45))
        else:
            local_t = t_clamped

        if local_t <= 0.01:
            return

        eased = 1.0 - (1.0 - local_t) ** 3
        cur_hx = p.sx1 + (p.halo_end_x - p.sx1) * eased
        cur_hy = p.sy1 + (p.halo_end_y - p.sy1) * eased

        halo_col = QColor(p.halo_color)
        if local_t >= 0.999 and is_playing:
            pulse = 0.5 + 0.5 * math.sin(effect_time_s * 3.2)
            halo_col.setAlpha(int(180 + 60 * pulse))
            w_eff = p.halo_width + 0.8 * pulse
        else:
            halo_col.setAlpha(int(165 + 85 * eased))
            w_eff = p.halo_width

        pen = QPen(halo_col, w_eff)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(p.sx1, p.sy1), QPointF(cur_hx, cur_hy))
        if p.has_cushion:
            cpen = QPen(QColor(theme.CANVAS_BG), p.draw_width + 3.4)
            cpen.setCapStyle(Qt.PenCapStyle.FlatCap)
            painter.setPen(cpen)
            painter.drawLine(QPointF(p.sx1, p.sy1), QPointF(cur_hx, cur_hy))

        if local_t < 0.98:
            # Destello de frente de onda al consolidar cada tramo del recorrido
            wave_glow = QColor(theme.ACCENT_PRIMARY)
            wave_glow.setAlpha(155)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(wave_glow))
            painter.drawEllipse(QPointF(cur_hx, cur_hy), p.draw_width * 1.45, p.draw_width * 1.45)
            wave_core = QColor(theme.PAPER_BG)
            wave_core.setAlpha(235)
            painter.setBrush(QBrush(wave_core))
            painter.drawEllipse(QPointF(cur_hx, cur_hy), max(2.0, p.draw_width * 0.65), max(2.0, p.draw_width * 0.65))

    @classmethod
    def _draw_pipes(
        cls,
        painter: QPainter,
        scene: CanvasScene,
        *,
        pipe_color_overrides: Optional[Dict[str, str]],
        route_transition_t: float,
        effect_time_s: float,
        is_playing: bool,
    ) -> None:
        for p in scene.pipes:
            pipe_color = (
                pipe_color_overrides.get(p.pipe_id, p.color)
                if pipe_color_overrides
                else p.color
            )
            if p.glow_color:
                glow_col = QColor(p.glow_color)
                glow_w = p.glow_width
                if is_playing:
                    breathe = 0.5 + 0.5 * math.sin(effect_time_s * 4.4)
                    glow_col.setAlpha(int(105 + 75 * breathe))
                    glow_w += 1.6 * breathe
                pen = QPen(glow_col, glow_w)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(pen)
                painter.drawLine(QPointF(p.sx1, p.sy1), QPointF(p.sx2, p.sy2))

            cls._draw_pipe_halo(
                painter,
                p,
                route_transition_t=route_transition_t,
                effect_time_s=effect_time_s,
                is_playing=is_playing,
            )

            if p.parallel_offset > 0.0:
                nx_p, ny_p = -p.uy, p.ux
                par_pen = QPen(QColor(theme.ACCENT_PRIMARY), 1.4)
                painter.setPen(par_pen)
                for sign in (-1.0, 1.0):
                    ox = nx_p * p.parallel_offset * sign
                    oy = ny_p * p.parallel_offset * sign
                    painter.drawLine(
                        QPointF(p.sx1 + ox, p.sy1 + oy),
                        QPointF(p.sx2 + ox, p.sy2 + oy),
                    )

            shaft_end_x = p.sx2 - p.ux * (p.arrow_len * 0.65) if p.draw_arrow else p.sx2
            shaft_end_y = p.sy2 - p.uy * (p.arrow_len * 0.65) if p.draw_arrow else p.sy2
            pen = QPen(QColor(pipe_color), p.draw_width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            if p.dashed:
                pen.setStyle(Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([3.0, 3.0])
            painter.setPen(pen)
            painter.drawLine(QPointF(p.sx1, p.sy1), QPointF(shaft_end_x, shaft_end_y))

            if p.draw_arrow:
                nx_p, ny_p = -p.uy, p.ux
                bx = p.sx2 - p.ux * p.arrow_len
                by = p.sy2 - p.uy * p.arrow_len
                arrow_poly = QPolygonF(
                    [
                        QPointF(p.sx2, p.sy2),
                        QPointF(bx + nx_p * p.arrow_wing, by + ny_p * p.arrow_wing),
                        QPointF(bx - nx_p * p.arrow_wing, by - ny_p * p.arrow_wing),
                    ]
                )
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(QColor(pipe_color)))
                painter.drawPolygon(arrow_poly)

            for x1, y1, x2, y2, bw in p.obstruction_bars:
                bpen = QPen(QColor(theme.INK_PRIMARY), bw)
                bpen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(bpen)
                painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))

    @staticmethod
    def _paint_comet_particle(
        painter: QPainter,
        *,
        px: float,
        py: float,
        ux: float,
        uy: float,
        sz: float,
        lw: float,
        core_hex: str,
        glow_hex: str,
        alpha_scale: float,
        tail_max_len: float,
    ) -> None:
        if alpha_scale <= 0.02:
            return
        tail_len = min(tail_max_len, max(6.0, sz * 3.1))
        seg_steps = ((0.0, 0.34, 0.44, 1.10), (0.34, 0.68, 0.25, 0.78), (0.68, 1.0, 0.10, 0.48))
        for f0, f1, a_fac, w_fac in seg_steps:
            t_col = QColor(glow_hex)
            t_col.setAlpha(int(255 * a_fac * alpha_scale))
            t_pen = QPen(t_col, max(0.8, lw * w_fac))
            t_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(t_pen)
            painter.drawLine(
                QPointF(px - ux * tail_len * f0, py - uy * tail_len * f0),
                QPointF(px - ux * tail_len * f1, py - uy * tail_len * f1),
            )

        painter.setPen(Qt.PenStyle.NoPen)
        g_col = QColor(glow_hex)
        g_col.setAlpha(int(120 * alpha_scale))
        painter.setBrush(QBrush(g_col))
        glow_r = max(2.3, sz * 0.80)
        painter.drawEllipse(QPointF(px, py), glow_r, glow_r)

        c_col = QColor(core_hex)
        c_col.setAlpha(int(245 * alpha_scale))
        painter.setBrush(QBrush(c_col))
        core_r = max(1.4, sz * 0.42)
        painter.drawEllipse(QPointF(px, py), core_r, core_r)

    @classmethod
    def _draw_track_particles(
        cls,
        painter: QPainter,
        tr: PulseTrack,
        *,
        time_s: float,
        effect_time_s: float,
        sqrt_z: float,
        core_hex: str,
        glow_hex: str,
        alpha_scale: float,
        with_sparkle: bool,
    ) -> None:
        if tr.usable_len <= 2.0:
            return
        nx_p, ny_p = -tr.uy, tr.ux
        raw_dist = time_s * tr.velocity_ms * cls._BASE_PX_PER_MPS * sqrt_z
        offset = tr.route_offset_px if (tr.is_focus and tr.route_offset_px >= 0.0) else 0.0
        for idx in range(tr.n_pulses):
            phase = idx / float(tr.n_pulses)
            travel = (raw_dist - offset + phase * tr.usable_len) % tr.usable_len
            dist_along = 5.0 + travel
            wobble = (
                math.sin(effect_time_s * 5.2 + idx * 2.1) * 1.05
                if with_sparkle
                else 0.0
            )
            px = tr.sx1 + tr.ux * dist_along + nx_p * wobble
            py = tr.sy1 + tr.uy * dist_along + ny_p * wobble
            cls._paint_comet_particle(
                painter,
                px=px,
                py=py,
                ux=tr.ux,
                uy=tr.uy,
                sz=tr.chevron_size,
                lw=tr.line_width,
                core_hex=core_hex,
                glow_hex=glow_hex,
                alpha_scale=alpha_scale,
                tail_max_len=max(5.0, travel * 0.72),
            )
            if with_sparkle and travel > 7.5:
                sx = px - tr.ux * 6.5 - nx_p * (wobble * 1.4)
                sy = py - tr.uy * 6.5 - ny_p * (wobble * 1.4)
                sp_col = QColor(theme.PAPER_BG)
                sp_col.setAlpha(int(175 * alpha_scale))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(sp_col))
                painter.drawEllipse(QPointF(sx, sy), max(1.0, tr.chevron_size * 0.24), max(1.0, tr.chevron_size * 0.24))

    @classmethod
    def _draw_particles(
        cls,
        painter: QPainter,
        scene: CanvasScene,
        *,
        pulse_time_s: float,
        effect_time_s: float,
        is_playing: bool,
        has_active_traversal_anim: bool,
        zoom: float,
    ) -> None:
        sqrt_z = math.sqrt(max(0.1, zoom))
        if is_playing:
            active_pulse_pids = set()
            for tr in scene.pulse_tracks:
                active_pulse_pids.add(tr.pipe_id)
                if tr.is_dimmed:
                    cls._draw_track_particles(
                        painter,
                        tr,
                        time_s=pulse_time_s,
                        effect_time_s=effect_time_s,
                        sqrt_z=sqrt_z,
                        core_hex=tr.color,
                        glow_hex=tr.glow_color or theme.DOCK_BG,
                        alpha_scale=0.28,
                        with_sparkle=False,
                    )
                elif tr.is_focus:
                    focus_glow = (
                        "#FCA5A5"
                        if tr.tier_idx >= 4
                        else (theme.ACCENT_PRIMARY if tr.tier_idx <= 1 else (tr.glow_color or theme.ACCENT_PRIMARY))
                    )
                    cls._draw_track_particles(
                        painter,
                        tr,
                        time_s=pulse_time_s,
                        effect_time_s=effect_time_s,
                        sqrt_z=sqrt_z,
                        core_hex=theme.PAPER_BG,
                        glow_hex=focus_glow,
                        alpha_scale=0.96,
                        with_sparkle=True,
                    )
                else:
                    cls._draw_track_particles(
                        painter,
                        tr,
                        time_s=pulse_time_s,
                        effect_time_s=effect_time_s,
                        sqrt_z=sqrt_z,
                        core_hex=tr.color,
                        glow_hex=tr.glow_color or tr.color,
                        alpha_scale=0.84,
                        with_sparkle=False,
                    )

            # Trazadores tenues en tramos de ruta enfocada aún secos al inicio de la lluvia
            for rtr in scene.route_tracks:
                if rtr.pipe_id in active_pulse_pids:
                    continue
                cls._draw_track_particles(
                    painter,
                    rtr,
                    time_s=effect_time_s,
                    effect_time_s=effect_time_s,
                    sqrt_z=sqrt_z,
                    core_hex=theme.PAPER_BG,
                    glow_hex=theme.ACCENT_PRIMARY,
                    alpha_scale=0.58,
                    with_sparkle=False,
                )
        elif scene.route_tracks:
            alpha_s = 0.92 if has_active_traversal_anim else 0.72
            for rtr in scene.route_tracks:
                cls._draw_track_particles(
                    painter,
                    rtr,
                    time_s=effect_time_s,
                    effect_time_s=effect_time_s,
                    sqrt_z=sqrt_z,
                    core_hex=theme.PAPER_BG,
                    glow_hex=theme.ACCENT_PRIMARY,
                    alpha_scale=alpha_s,
                    with_sparkle=has_active_traversal_anim,
                )

    @staticmethod
    def _draw_flood_rings(
        painter: QPainter,
        scene: CanvasScene,
        *,
        effect_time_s: float = 0.0,
        is_playing: bool = False,
    ) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for fr in scene.flood_rings:
            dr = 1.1 * math.sin(effect_time_s * 4.0 + fr.x * 0.04) if is_playing else 0.0
            pen = QPen(QColor(fr.color), fr.width)
            if fr.dashed:
                pen.setStyle(Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([3.0, 3.0])
            painter.setPen(pen)
            painter.drawEllipse(QPointF(fr.x, fr.y), max(2.0, fr.radius + dr), max(2.0, fr.radius + dr))

    @staticmethod
    def _draw_node_ripples(
        painter: QPainter,
        scene: CanvasScene,
        *,
        effect_time_s: float,
        is_playing: bool,
        route_transition_t: float,
        has_active_traversal_anim: bool,
    ) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)
        is_burst = route_transition_t < 0.999
        for n in scene.nodes:
            if not n.is_focus:
                continue
            if not (n.is_route_endpoint or has_active_traversal_anim or is_burst):
                continue

            if is_burst:
                burst_r = n.radius + 3.0 + route_transition_t * max(11.0, n.radius * 1.15)
                b_col = QColor(theme.ACCENT_PRIMARY)
                b_col.setAlpha(int(210 * (1.0 - route_transition_t) ** 1.4))
                painter.setPen(QPen(b_col, 2.0))
                painter.drawEllipse(QPointF(n.x, n.y), burst_r, burst_r)

            if is_playing or has_active_traversal_anim or n.is_route_endpoint:
                phase_off = 0.35 if n.is_route_endpoint else 0.0
                cycle = (effect_time_s * 0.75 + phase_off) % 1.0
                ripple_r = n.radius + 2.5 + cycle * max(8.5, n.radius * 0.85)
                r_col = QColor(theme.ACCENT_PRIMARY)
                base_a = 175 if (is_playing or has_active_traversal_anim) else 125
                r_col.setAlpha(int(base_a * ((1.0 - cycle) ** 2)))
                painter.setPen(QPen(r_col, 1.5))
                painter.drawEllipse(QPointF(n.x, n.y), ripple_r, ripple_r)

    def _draw_nodes(self, painter: QPainter, scene: CanvasScene) -> None:
        for n in scene.nodes:
            if n.outer_ring_color:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor(n.outer_ring_color), n.outer_ring_width))
                painter.drawEllipse(
                    QPointF(n.x, n.y), n.outer_ring_radius, n.outer_ring_radius
                )

            pen = QPen(QColor(n.outline), n.outline_width)
            if n.dashed:
                pen.setStyle(Qt.PenStyle.CustomDashLine)
                pen.setDashPattern([3.0, 2.0])
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(n.fill)))
            painter.drawEllipse(QPointF(n.x, n.y), n.radius, n.radius)

            if n.show_label:
                font = QFont(self.ui_font)
                font.setPixelSize(n.font_px)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(QColor(n.text_color))
                painter.drawText(
                    QRectF(n.x - n.radius, n.y - n.radius, n.radius * 2.0, n.radius * 2.0),
                    Qt.AlignmentFlag.AlignCenter,
                    n.node_id,
                )

    @staticmethod
    def _draw_badges(painter: QPainter, scene: CanvasScene) -> None:
        for b in scene.badges:
            rect = QRectF(b.x0, b.y0, b.x1 - b.x0, b.y1 - b.y0)
            painter.setPen(QPen(QColor(b.border), b.border_width))
            painter.setBrush(QBrush(QColor(b.bg)))
            painter.drawRect(rect)

            font = QFont(b.font_family)
            font.setPixelSize(b.font_px)
            font.setBold(b.bold)
            painter.setFont(font)
            painter.setPen(QColor(b.fg))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, b.text)
