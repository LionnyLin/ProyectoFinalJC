"""Motor de cálculo geométrico y colocación sin solapamientos para NetworkCanvas."""

from dataclasses import dataclass, field
import math
from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtGui import QFont, QFontMetricsF

from src.algorithms.analysis import classify_overload_persistence, classify_utilization
from src.algorithms.traversals import TraversalAnimFrame
from src.data_structures import DirectedGraph, PipeEdge
from src.simulation.models import PipeIntervention, TimeStepSnapshot
from .. import theme


def blend_hex(hex_fg: str, hex_bg: str, t: float) -> str:
    """Interpola linealmente entre dos colores hexadecimales (#RRGGBB)."""
    fg = hex_fg.lstrip("#")
    bg = hex_bg.lstrip("#")
    if len(fg) != 6 or len(bg) != 6:
        return hex_fg
    t = max(0.0, min(1.0, t))
    r = int(round(int(fg[0:2], 16) * (1.0 - t) + int(bg[0:2], 16) * t))
    g = int(round(int(fg[2:4], 16) * (1.0 - t) + int(bg[2:4], 16) * t))
    b = int(round(int(fg[4:6], 16) * (1.0 - t) + int(bg[4:6], 16) * t))
    return f"#{r:02x}{g:02x}{b:02x}"


@dataclass(frozen=True)
class PipeVisual:
    pipe_id: str
    sx1: float
    sy1: float
    sx2: float
    sy2: float
    ux: float
    uy: float
    seg_len: float
    draw_width: float
    color: str
    dashed: bool = False
    draw_arrow: bool = True
    arrow_len: float = 10.0
    arrow_wing: float = 3.8
    glow_color: Optional[str] = None
    glow_width: float = 0.0
    halo_color: Optional[str] = None
    halo_width: float = 0.0
    has_cushion: bool = False
    halo_end_x: float = 0.0
    halo_end_y: float = 0.0
    parallel_offset: float = 0.0
    obstruction_bars: Tuple[Tuple[float, float, float, float, float], ...] = ()
    is_focus: bool = False
    is_dimmed: bool = False
    is_overloaded: bool = False
    utilization_tier: int = 0
    route_index: int = -1
    route_total: int = 0


@dataclass(frozen=True)
class PulseTrack:
    pipe_id: str
    sx1: float
    sy1: float
    ux: float
    uy: float
    usable_len: float
    velocity_ms: float
    n_pulses: int
    color: str
    chevron_size: float
    line_width: float
    is_focus: bool = False
    is_dimmed: bool = False
    tier_idx: int = 0
    utilization_pct: float = 0.0
    route_offset_px: float = -1.0
    glow_color: str = ""


@dataclass(frozen=True)
class FloodRingVisual:
    node_id: str
    x: float
    y: float
    radius: float
    color: str
    width: float
    dashed: bool = False


@dataclass(frozen=True)
class NodeVisual:
    node_id: str
    x: float
    y: float
    radius: float
    fill: str
    outline: str
    outline_width: float
    dashed: bool
    text_color: str
    font_px: int
    show_label: bool
    outer_ring_color: Optional[str] = None
    outer_ring_radius: float = 0.0
    outer_ring_width: float = 0.0
    is_focus: bool = False
    is_route_endpoint: bool = False
    focus_order_idx: int = -1


@dataclass(frozen=True)
class BadgeVisual:
    entity_kind: str
    entity_id: str
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    fg: str
    bg: str
    border: str
    border_width: float
    font_family: str
    font_px: int
    bold: bool
    kind: str


@dataclass
class CanvasScene:
    width: int
    height: int
    scale_factor: float
    node_radius: float
    dense_mode: bool
    pipes: List[PipeVisual] = field(default_factory=list)
    pulse_tracks: List[PulseTrack] = field(default_factory=list)
    route_tracks: List[PulseTrack] = field(default_factory=list)
    flood_rings: List[FloodRingVisual] = field(default_factory=list)
    nodes: List[NodeVisual] = field(default_factory=list)
    badges: List[BadgeVisual] = field(default_factory=list)
    empty_message: Optional[str] = None


class CanvasLayoutEngine:
    """Calcula coordenadas de pantalla, estados visuales y etiquetas sin colisiones."""

    def __init__(self, ui_font: str, mono_font: str, dpi_scale: float = 1.0) -> None:
        self.ui_font = ui_font
        self.mono_font = mono_font
        self.dpi_scale = max(1.0, float(dpi_scale))

    @staticmethod
    def compute_padding(w: int, h: int) -> Tuple[float, float]:
        pad_x = max(28.0, min(68.0, w * 0.08))
        pad_y = max(34.0, min(64.0, h * 0.11))
        return pad_x, pad_y

    @classmethod
    def world_to_screen(
        cls,
        nx: float,
        ny: float,
        w: int,
        h: int,
        zoom: float,
        pan_x: float,
        pan_y: float,
    ) -> Tuple[float, float]:
        w = max(200, w)
        h = max(200, h)
        pad_x, pad_y = cls.compute_padding(w, h)
        base_x = pad_x + nx * (w - 2.0 * pad_x)
        base_y = pad_y + ny * (h - 2.0 * pad_y)
        cx, cy = w / 2.0, h / 2.0
        sx = cx + (base_x - cx) * zoom + pan_x
        sy = cy + (base_y - cy) * zoom + pan_y
        return sx, sy

    @staticmethod
    def boxes_overlap(
        a: Tuple[float, float, float, float],
        b: Tuple[float, float, float, float],
    ) -> bool:
        return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])

    @staticmethod
    def box_hits_segment(
        box: Tuple[float, float, float, float],
        x1: float,
        y1: float,
        x2: float,
        y2: float,
    ) -> bool:
        bx0, by0, bx1, by1 = box
        if max(x1, x2) < bx0 or min(x1, x2) > bx1 or max(y1, y2) < by0 or min(y1, y2) > by1:
            return False
        dx = x2 - x1
        dy = y2 - y1
        t0, t1 = 0.0, 1.0
        for p, q in ((-dx, x1 - bx0), (dx, bx1 - x1), (-dy, y1 - by0), (dy, by1 - y1)):
            if abs(p) < 1e-9:
                if q < 0.0:
                    return False
            else:
                r = q / p
                if p < 0.0:
                    if r > t1:
                        return False
                    if r > t0:
                        t0 = r
                else:
                    if r < t0:
                        return False
                    if r < t1:
                        t1 = r
        return t0 <= t1

    @staticmethod
    def resolve_pipe_visual_state(
        map_mode: str,
        pipe_id: str,
        ps,
        is_closed: bool,
        peak_util_map: Dict[str, float],
        overload_minutes_map: Dict[str, float],
        total_duration_min: float,
    ) -> Tuple[str, int, bool, bool, float, str]:
        """Retorna `(color_hex, tier_idx, is_overloaded, is_critical, display_val, suffix_lbl)`."""
        if map_mode == "overload_minutes":
            ov_min = overload_minutes_map.get(pipe_id, 0.0)
            tier, col, _ = classify_overload_persistence(ov_min, total_duration_min)
            is_over = (tier >= 3) and not is_closed
            is_crit = (tier >= 2) and not is_closed
            lbl = f"{ov_min:.0f}m" if ov_min >= 0.5 else "0m"
            return (theme.INK_PRIMARY if is_closed else col, tier, is_over, is_crit, ov_min, lbl)

        if is_closed:
            return (theme.INK_PRIMARY, 0, False, False, 0.0, "CERRADA")

        if map_mode == "peak":
            u = peak_util_map.get(pipe_id, ps.utilization_pct if ps is not None else 0.0)
            cat = classify_utilization(u)
            col = "#991b1b" if cat.is_overloaded else cat.color_hex
            lbl_u = f"{u / 1000.0:.1f}k%" if u >= 1000.0 else f"{u:.0f}%"
            return (col, cat.tier_index, cat.is_overloaded, u > 75.0, u, lbl_u)

        if ps is None:
            return (theme.PIPE_IDLE_COLOR, 0, False, False, 0.0, "")
        col = "#991b1b" if ps.category.is_overloaded else ps.category.color_hex
        u_inst = ps.utilization_pct
        lbl_inst = f"{u_inst / 1000.0:.1f}k%" if u_inst >= 1000.0 else f"{u_inst:.0f}%"
        return (col, ps.category.tier_index, ps.category.is_overloaded, u_inst > 75.0, u_inst, lbl_inst)

    @staticmethod
    def _measure_text(text: str, family: str, pixel_size: int, bold: bool) -> Tuple[float, float]:
        font = QFont(family)
        font.setPixelSize(max(6, pixel_size))
        font.setBold(bold)
        fm = QFontMetricsF(font)
        rect = fm.tightBoundingRect(text)
        w = max(fm.horizontalAdvance(text), rect.width())
        h = max(fm.height() * 0.85, rect.height())
        return (float(w), float(h))

    @classmethod
    def _fit_node_font_px(cls, text: str, family: str, radius: float) -> int:
        base_px = max(6, min(14, int(round(radius * 1.12))))
        max_w = max(4.0, (radius * 2.0) - 2.0)
        max_h = max(4.0, (radius * 2.0) - 2.0)
        for px in range(base_px, 5, -1):
            tw, th = cls._measure_text(text, family, px, True)
            if tw <= max_w and th <= max_h:
                return px
        return 6

    @staticmethod
    def _build_obstruction_bars(
        mx: float,
        my: float,
        ux: float,
        uy: float,
        width: float,
        is_closed: bool,
    ) -> Tuple[Tuple[float, float, float, float, float], ...]:
        nx_p, ny_p = -uy, ux
        half_bar = max(6.5, width * 1.45)
        offsets = (-4.5, 0.0, 4.5) if is_closed else (-3.0, 3.0)
        bar_w = 2.3 if is_closed else 2.0
        bars: List[Tuple[float, float, float, float, float]] = []
        for off in offsets:
            cx = mx + ux * off
            cy = my + uy * off
            bars.append(
                (
                    cx - nx_p * half_bar,
                    cy - ny_p * half_bar,
                    cx + nx_p * half_bar,
                    cy + ny_p * half_bar,
                    bar_w,
                )
            )
        return tuple(bars)

    @staticmethod
    def _build_flood_rings(
        nid: str,
        x: float,
        y: float,
        r: float,
        surcharge_vol: float,
        sf: float,
        sqrt_z: float,
    ) -> List[FloodRingVisual]:
        if surcharge_vol <= 1e-3:
            return []
        n_rings = 1 if surcharge_vol < 5.0 else (2 if surcharge_vol < 60.0 else 3)
        max_extra = min(14.5, 2.6 + 3.4 * math.log10(1.0 + surcharge_vol)) * sf * sqrt_z
        max_extra = min(max_extra, max(2.8, r * 1.15))
        out: List[FloodRingVisual] = []
        for k in range(n_rings, 0, -1):
            ring_r = r + (max_extra * k / n_rings)
            is_inner_intense = k == 1 and surcharge_vol >= 25.0
            ring_col = (
                theme.NODE_SURCHARGE_RING_DEEP if is_inner_intense else theme.NODE_SURCHARGE_RING
            )
            out.append(
                FloodRingVisual(
                    node_id=nid,
                    x=x,
                    y=y,
                    radius=ring_r,
                    color=ring_col,
                    width=1.5 if is_inner_intense else 1.25,
                    dashed=(k == n_rings and n_rings >= 2),
                )
            )
        return out

    def build_scene(
        self,
        *,
        graph: Optional[DirectedGraph],
        snapshot: Optional[TimeStepSnapshot],
        width: int,
        height: int,
        zoom: float,
        pan_x: float,
        pan_y: float,
        selected_pipe_id: Optional[str],
        selected_node_id: Optional[str],
        highlight_pipe_ids: Set[str],
        highlight_node_ids: Set[str],
        show_pipe_labels: bool,
        show_util_labels: bool,
        interventions: Dict[str, PipeIntervention],
        isolated_nodes: Set[str],
        isolated_pipes: Set[str],
        basin_active: bool,
        basin_nodes: Set[str],
        basin_pipes: Set[str],
        tour_active: bool,
        tour_nodes: Set[str],
        tour_pipes: Set[str],
        map_mode: str,
        peak_util_map: Dict[str, float],
        overload_minutes_map: Dict[str, float],
        total_duration_min: float,
        traversal_frame: Optional[TraversalAnimFrame],
        overlay_boxes: List[Tuple[float, float, float, float]],
        ordered_route_pipe_ids: Optional[List[str]] = None,
    ) -> CanvasScene:
        w = max(200, width)
        h = max(200, height)
        if graph is None:
            return CanvasScene(
                width=w,
                height=h,
                scale_factor=1.0,
                node_radius=10.0,
                dense_mode=False,
                empty_message="Cargue un archivo Excel o carpeta CSV para visualizar la red.",
            )

        min_dim = min(w, h)
        scale_factor = max(0.72, min(1.22, min_dim / 560.0))
        sqrt_z = math.sqrt(zoom)

        positions: Dict[str, Tuple[float, float]] = {
            node.node_id: self.world_to_screen(node.x, node.y, w, h, zoom, pan_x, pan_y)
            for node in graph.nodes()
        }

        min_node_dist = 999.0
        pos_list = list(positions.values())
        for i in range(len(pos_list)):
            x1, y1 = pos_list[i]
            for j in range(i + 1, len(pos_list)):
                x2, y2 = pos_list[j]
                d = math.hypot(x2 - x1, y2 - y1)
                if d > 1e-3 and d < min_node_dist:
                    min_node_dist = d

        dpi_r_boost = min(1.30, self.dpi_scale)
        base_radius = 10.4 * scale_factor * sqrt_z * dpi_r_boost
        max_safe_r = (min_node_dist * 0.30) if min_node_dist < 900.0 else 16.5
        node_radius = max(2.8, min(16.5, base_radius, max_safe_r))
        dense_mode = (w < 500 or zoom < 0.78)

        scene = CanvasScene(
            width=w,
            height=h,
            scale_factor=scale_factor,
            node_radius=node_radius,
            dense_mode=dense_mode,
        )

        anim = traversal_frame
        has_traversal_focus = (
            anim is not None or bool(highlight_pipe_ids) or bool(highlight_node_ids)
        )

        cut_boundary_nodes: Set[str] = set()
        for pid, inv in interventions.items():
            if inv.is_closed:
                edge = graph.get_pipe(pid)
                if edge and edge.from_node in isolated_nodes:
                    cut_boundary_nodes.add(edge.from_node)

        route_index_map: Dict[str, int] = {}
        route_offset_map: Dict[str, float] = {}
        route_endpoints: Set[str] = set()
        ordered_list = [pid for pid in (ordered_route_pipe_ids or ()) if graph.get_pipe(pid) is not None]
        if ordered_list:
            cum_px = 0.0
            for idx_r, pid_r in enumerate(ordered_list):
                if pid_r in route_index_map:
                    continue
                edge_r = graph.get_pipe(pid_r)
                if edge_r is None:
                    continue
                p1_r = positions.get(edge_r.from_node)
                p2_r = positions.get(edge_r.to_node)
                route_index_map[pid_r] = idx_r
                route_offset_map[pid_r] = cum_px
                if p1_r is not None and p2_r is not None:
                    dist_r = math.hypot(p2_r[0] - p1_r[0], p2_r[1] - p1_r[1])
                    start_gap_r = min(1.5, node_radius * 0.14)
                    end_gap_r = min(3.0, node_radius * 0.24)
                    seg_len_r = max(8.0, dist_r - 2.0 * node_radius - start_gap_r - end_gap_r)
                    cum_px += max(8.0, seg_len_r - 13.0)
            first_e = graph.get_pipe(ordered_list[0])
            last_e = graph.get_pipe(ordered_list[-1])
            if first_e is not None:
                route_endpoints.add(first_e.from_node)
            if last_e is not None:
                route_endpoints.add(last_e.to_node)
        route_total = len(route_index_map) if route_index_map else len(highlight_pipe_ids)
        fallback_focus_idx = 0

        label_queue = []
        pipe_segments: List[Tuple[float, float, float, float]] = []

        for pipe in graph.pipes():
            p1 = positions.get(pipe.from_node)
            p2 = positions.get(pipe.to_node)
            if p1 is None or p2 is None:
                continue

            x1, y1 = p1
            x2, y2 = p2
            dx, dy = x2 - x1, y2 - y1
            dist = math.hypot(dx, dy)
            if dist < 1e-3:
                continue
            ux, uy = dx / dist, dy / dist

            start_gap = min(1.5, node_radius * 0.14)
            end_gap = min(3.0, node_radius * 0.24)
            sx1 = x1 + ux * (node_radius + start_gap)
            sy1 = y1 + uy * (node_radius + start_gap)
            sx2 = x2 - ux * (node_radius + end_gap)
            sy2 = y2 - uy * (node_radius + end_gap)
            pipe_segments.append((x1, y1, x2, y2))

            inv = interventions.get(pipe.pipe_id)
            is_closed = inv is not None and inv.is_closed
            is_obstructed = inv is not None and inv.has_obstruction
            eff_diam_in = (
                inv.diameter_in_override
                if (inv is not None and inv.diameter_in_override is not None)
                else pipe.diameter_in
            )
            is_enlarged = (
                inv is not None
                and inv.diameter_in_override is not None
                and inv.diameter_in_override > pipe.diameter_in + 1e-6
            )

            is_dimmed_basin = (
                (basin_active and (pipe.pipe_id not in basin_pipes))
                or (tour_active and (pipe.pipe_id not in tour_pipes))
            )
            is_isolated = pipe.pipe_id in isolated_pipes
            is_anim_backtrack = anim is not None and (pipe.pipe_id in anim.backtracked_edges)
            is_anim_active = anim is not None and (pipe.pipe_id in anim.active_edges)
            is_anim_visited = (
                anim is not None
                and (pipe.pipe_id in anim.visited_edges)
                and not is_anim_active
            )

            ps = snapshot.pipe_states.get(pipe.pipe_id) if snapshot else None
            vel_ms = pipe.reference_velocity_ms
            if ps is not None and ps.effective_velocity_ms is not None:
                vel_ms = ps.effective_velocity_ms
            color, tier_idx, is_overloaded, is_critical, disp_val, suf_lbl = (
                self.resolve_pipe_visual_state(
                    map_mode,
                    pipe.pipe_id,
                    ps,
                    is_closed,
                    peak_util_map,
                    overload_minutes_map,
                    total_duration_min,
                )
            )

            base_width = 2.0 + (eff_diam_in - 8.0) * 0.24
            geom_width = base_width * min(1.45, max(0.78, sqrt_z * scale_factor))
            width_eff = geom_width + (1.5 if (is_overloaded and not is_closed and anim is None) else 0.0)
            is_selected = pipe.pipe_id == selected_pipe_id
            is_highlighted = pipe.pipe_id in highlight_pipe_ids
            is_focus_pipe = is_anim_active if anim is not None else is_highlighted
            is_dimmed_context = has_traversal_focus and not (
                is_focus_pipe or is_anim_visited or is_selected
            )

            seg_len = math.hypot(sx2 - sx1, sy2 - sy1)
            arrow_scale = max(0.38, min(1.0, seg_len / 14.0, node_radius / 8.0))

            if is_dimmed_basin or is_isolated or is_anim_backtrack:
                halo_col = None
                halo_w = 0.0
                if is_selected or (is_focus_pipe and not is_dimmed_basin):
                    halo_col = theme.PIPE_SELECTED_HALO if is_selected else theme.ACCENT_PRIMARY
                    halo_w = geom_width + 5.0
                scene.pipes.append(
                    PipeVisual(
                        pipe_id=pipe.pipe_id,
                        sx1=sx1,
                        sy1=sy1,
                        sx2=sx2,
                        sy2=sy2,
                        ux=ux,
                        uy=uy,
                        seg_len=seg_len,
                        draw_width=max(1.4, geom_width * 0.72),
                        color=theme.DOCK_BG,
                        dashed=(is_isolated or is_anim_backtrack),
                        draw_arrow=seg_len > 2.5,
                        arrow_len=max(4.0, 8.0 * arrow_scale),
                        arrow_wing=max(1.5, 2.8 * arrow_scale),
                        halo_color=halo_col,
                        halo_width=halo_w,
                        halo_end_x=sx2,
                        halo_end_y=sy2,
                    )
                )
                continue

            draw_width = max(1.0, min(width_eff, max(1.2, node_radius * 0.42)))
            arrow_len = max(4.0, 10.0 * arrow_scale)
            arrow_wing = max(1.5, 3.8 * arrow_scale)
            if is_dimmed_context:
                draw_width = max(1.0, min(draw_width, geom_width * 0.72))
                arrow_len = max(4.0, 8.0 * arrow_scale)
                arrow_wing = max(1.5, 2.8 * arrow_scale)
            elif is_anim_visited and not is_focus_pipe and not is_selected:
                draw_width = max(1.3, min(draw_width, geom_width * 0.92))
                arrow_len = max(4.0, 9.0 * arrow_scale)
                arrow_wing = max(1.5, 3.2 * arrow_scale)
            elif is_focus_pipe or is_selected:
                draw_width = max(
                    1.8,
                    min(width_eff + (0.6 if is_focus_pipe else 0.0), max(2.0, node_radius * 0.50)),
                )
                arrow_len = max(4.0, (11.0 if is_focus_pipe else 10.0) * arrow_scale)
                arrow_wing = max(1.5, (4.2 if is_focus_pipe else 3.8) * arrow_scale)

            halo_color = None
            halo_width = 0.0
            has_cushion = False
            halo_end_x, halo_end_y = sx2, sy2
            if (is_selected or is_focus_pipe or is_anim_visited) and seg_len > 6.0:
                trim_tip = min(seg_len * 0.45, 7.5)
                halo_end_x = sx2 - ux * trim_tip
                halo_end_y = sy2 - uy * trim_tip
                if is_selected or is_focus_pipe:
                    halo_color = theme.PIPE_SELECTED_HALO if is_selected else theme.ACCENT_PRIMARY
                    halo_width = draw_width + (8.0 if (is_selected and not is_focus_pipe) else 8.8)
                    has_cushion = True
                else:
                    halo_color = "#B8C2CC"
                    halo_width = draw_width + 3.8

            par_offset = 0.0
            if is_enlarged and dist > 16.0:
                par_offset = draw_width / 2.0 + (4.6 if (is_selected or is_focus_pipe) else 2.8)

            base_line_fill = theme.INK_PRIMARY if is_closed else color
            if is_dimmed_context:
                line_fill = blend_hex(base_line_fill, theme.CANVAS_BG, 0.68)
            elif is_anim_visited and not is_focus_pipe and not is_selected:
                line_fill = blend_hex(base_line_fill, theme.CANVAS_BG, 0.30)
            else:
                line_fill = base_line_fill

            glow_color = (
                theme.PIPE_OVERLOAD_HALO
                if (anim is None and not is_closed and is_overloaded and not is_dimmed_context)
                else None
            )
            pipe_route_idx = -1
            if is_focus_pipe:
                if pipe.pipe_id in route_index_map:
                    pipe_route_idx = route_index_map[pipe.pipe_id]
                else:
                    pipe_route_idx = fallback_focus_idx
                    fallback_focus_idx += 1
            pipe_route_tot = route_total if route_total > 0 else max(1, fallback_focus_idx)

            mx, my = (sx1 + sx2) / 2.0, (sy1 + sy2) / 2.0
            obst_bars = (
                self._build_obstruction_bars(mx, my, ux, uy, geom_width, is_closed)
                if (is_obstructed and dist > 14.0)
                else ()
            )

            scene.pipes.append(
                PipeVisual(
                    pipe_id=pipe.pipe_id,
                    sx1=sx1,
                    sy1=sy1,
                    sx2=sx2,
                    sy2=sy2,
                    ux=ux,
                    uy=uy,
                    seg_len=seg_len,
                    draw_width=draw_width,
                    color=line_fill,
                    dashed=is_closed,
                    draw_arrow=seg_len > 2.5,
                    arrow_len=arrow_len,
                    arrow_wing=arrow_wing,
                    glow_color=glow_color,
                    glow_width=width_eff + 4.0,
                    halo_color=halo_color,
                    halo_width=halo_width,
                    has_cushion=has_cushion,
                    halo_end_x=halo_end_x,
                    halo_end_y=halo_end_y,
                    parallel_offset=par_offset,
                    obstruction_bars=obst_bars,
                    is_focus=is_focus_pipe,
                    is_dimmed=is_dimmed_context,
                    is_overloaded=is_overloaded,
                    utilization_tier=tier_idx,
                    route_index=pipe_route_idx,
                    route_total=pipe_route_tot,
                )
            )

            if (
                anim is None
                and not is_closed
                and seg_len >= 20.0
                and ps is not None
                and ps.flow_m3s > 1e-5
                and ps.conveyed_flow_m3s > 1e-5
            ):
                usable = max(8.0, seg_len - 13.0)
                if is_focus_pipe and seg_len > 70.0:
                    n_pulses = 4
                elif is_focus_pipe or seg_len > 110.0 or is_overloaded:
                    n_pulses = 3
                else:
                    n_pulses = 2
                chev_col = theme.INK_PRIMARY if tier_idx in (0, 1) else theme.PAPER_BG
                track_glow = (
                    "#FCA5A5"
                    if is_overloaded
                    else (theme.ACCENT_PRIMARY if is_focus_pipe else color)
                )
                scene.pulse_tracks.append(
                    PulseTrack(
                        pipe_id=pipe.pipe_id,
                        sx1=sx1,
                        sy1=sy1,
                        ux=ux,
                        uy=uy,
                        usable_len=usable,
                        velocity_ms=vel_ms,
                        n_pulses=n_pulses,
                        color=chev_col,
                        chevron_size=max(3.6, min(5.4, geom_width * 0.88)),
                        line_width=max(1.4, min(2.2, geom_width * 0.42)),
                        is_focus=is_focus_pipe,
                        is_dimmed=is_dimmed_context,
                        tier_idx=tier_idx,
                        utilization_pct=ps.utilization_pct,
                        route_offset_px=route_offset_map.get(pipe.pipe_id, -1.0),
                        glow_color=track_glow,
                    )
                )

            if is_focus_pipe and not is_closed and seg_len >= 16.0:
                r_usable = max(8.0, seg_len - 10.0)
                r_vel = 2.05 if anim is not None else max(1.35, min(2.4, vel_ms))
                r_pulses = 4 if seg_len > 85.0 else (3 if seg_len > 42.0 else 2)
                scene.route_tracks.append(
                    PulseTrack(
                        pipe_id=pipe.pipe_id,
                        sx1=sx1,
                        sy1=sy1,
                        ux=ux,
                        uy=uy,
                        usable_len=r_usable,
                        velocity_ms=r_vel,
                        n_pulses=r_pulses,
                        color=theme.PAPER_BG,
                        chevron_size=max(3.8, min(5.2, geom_width * 0.85)),
                        line_width=max(1.5, min(2.2, geom_width * 0.44)),
                        is_focus=True,
                        is_dimmed=False,
                        tier_idx=tier_idx,
                        utilization_pct=ps.utilization_pct if ps is not None else 0.0,
                        route_offset_px=route_offset_map.get(pipe.pipe_id, -1.0),
                        glow_color=theme.ACCENT_PRIMARY,
                    )
                )

            has_mark = is_obstructed or is_enlarged
            has_ov_badge = (
                map_mode == "overload_minutes"
                and not is_closed
                and disp_val >= 0.5
                and anim is None
                and not is_dimmed_context
            )
            if (show_pipe_labels or show_util_labels or has_mark or has_ov_badge) and dist > 26:
                if has_traversal_focus:
                    show_this = is_selected or is_focus_pipe or has_mark
                else:
                    show_this = (
                        (not dense_mode)
                        or is_selected
                        or is_highlighted
                        or is_critical
                        or has_mark
                        or has_ov_badge
                    )
                if show_this:
                    prefix_parts = []
                    if is_obstructed and inv is not None:
                        prefix_parts.append(f"[OBST {inv.obstruction_pct:.0f}%]")
                    if is_enlarged:
                        prefix_parts.append(f"[Ø{eff_diam_in:.0f}\"]")
                    if show_pipe_labels:
                        prefix_parts.append(pipe.pipe_id)
                    if has_ov_badge:
                        ov_txt = f"{disp_val:.0f}m >100%"
                        if prefix_parts:
                            if show_pipe_labels and prefix_parts[-1] == pipe.pipe_id:
                                lbl_full = " ".join(prefix_parts[:-1] + [f"{pipe.pipe_id} · {ov_txt}"])
                            else:
                                lbl_full = " ".join(prefix_parts + [ov_txt])
                        else:
                            lbl_full = f"{pipe.pipe_id} · {ov_txt}" if show_pipe_labels else ov_txt
                    else:
                        parts = list(prefix_parts)
                        if show_util_labels and snapshot is not None and not is_closed and suf_lbl:
                            if not dense_mode or is_selected or is_focus_pipe or is_critical or has_mark:
                                parts.append(suf_lbl)
                        lbl_full = " ".join(parts)
                    if lbl_full:
                        nx_perp, ny_perp = -uy, ux
                        is_vert = abs(ux) < 0.35
                        if is_vert:
                            side = -1.0 if mx > w * 0.72 else 1.0
                            lx = mx + side * 26.0
                            ly = my
                        else:
                            side = 1.0
                            perp_off = 17.0 if (is_focus_pipe or is_selected) else 13.0
                            lx = mx + nx_perp * perp_off
                            ly = my + ny_perp * perp_off
                        priority = (
                            (6 if has_mark else 0)
                            + (5 if has_ov_badge else 0)
                            + (4 if is_selected else 0)
                            + (4 if is_focus_pipe else 0)
                            + (2 if is_overloaded else 0)
                            + (1 if is_critical else 0)
                        )
                        label_queue.append(
                            (
                                priority,
                                disp_val,
                                pipe.pipe_id,
                                lx,
                                ly,
                                mx,
                                is_vert,
                                side,
                                lbl_full,
                                is_selected,
                                is_overloaded,
                                is_focus_pipe,
                                has_mark,
                                has_ov_badge,
                                nx_perp,
                                ny_perp,
                            )
                        )

        r_box = max(3.0, node_radius * 0.80)
        r_badge_box = max(3.2, node_radius + 1.5)
        node_circle_boxes = [
            (nx - r_badge_box, ny - r_badge_box, nx + r_badge_box, ny + r_badge_box)
            for nx, ny in positions.values()
        ]
        node_label_boxes = [
            (nx - r_box, ny - r_box, nx + r_box, ny + r_box)
            for nx, ny in positions.values()
        ]
        placed_boxes: List[Tuple[float, float, float, float]] = list(node_label_boxes) + list(overlay_boxes)

        ptar_font_px = max(8, min(11, int(round(10.5 * scale_factor * min(1.12, sqrt_z)))))
        src_font_px = max(7, min(10, int(round(9.0 * scale_factor * min(1.08, sqrt_z)))))
        sink_extra_r = min(3.5, max(1.4, node_radius * 0.26))

        for node in graph.nodes():
            nx, ny = positions[node.node_id]
            is_dimmed_node = (
                (basin_active and (node.node_id not in basin_nodes))
                or (tour_active and (node.node_id not in tour_nodes))
            )
            if node.node_type == "sink":
                r_sink = node_radius + sink_extra_r
                chosen_sink = None
                fallback_sink = None
                for cand_txt in ("PTAR Punta Canoa · 31", "PTAR · 31"):
                    tw, th = self._measure_text(cand_txt, self.ui_font, ptar_font_px, True)
                    bw, bh = tw + 10.0, th + 4.0
                    cx = max(bw / 2.0 + 6.0, min(w - bw / 2.0 - 6.0, nx))
                    for cy in (ny - r_sink - bh / 2.0 - 4.0, ny + r_sink + bh / 2.0 + 4.0):
                        cy_c = max(bh / 2.0 + 4.0, min(h - bh / 2.0 - 4.0, cy))
                        cbox = (cx - bw / 2.0, cy_c - bh / 2.0, cx + bw / 2.0, cy_c + bh / 2.0)
                        if fallback_sink is None or cand_txt == "PTAR · 31":
                            fallback_sink = (cand_txt, cbox)
                        hits_node = any(self.boxes_overlap(cbox, nb) for nb in node_circle_boxes)
                        hits_ov = any(self.boxes_overlap(cbox, ob) for ob in overlay_boxes)
                        if not hits_node and not hits_ov:
                            chosen_sink = (cand_txt, cbox)
                            break
                    if chosen_sink is not None:
                        break
                pick = chosen_sink or fallback_sink
                if pick is not None:
                    cand_txt, cbox = pick
                    scene.badges.append(
                        BadgeVisual(
                            entity_kind="node",
                            entity_id=node.node_id,
                            x0=cbox[0],
                            y0=cbox[1],
                            x1=cbox[2],
                            y1=cbox[3],
                            text=cand_txt,
                            fg=theme.SHELL_TEXT,
                            bg=theme.SHELL_BG,
                            border=theme.ACCENT_PRIMARY,
                            border_width=1.5,
                            font_family=self.ui_font,
                            font_px=ptar_font_px,
                            bold=True,
                            kind="sink",
                        )
                    )
                    placed_boxes.append(cbox)
            elif node.node_type == "source" and not dense_mode and not is_dimmed_node and node_radius >= 6.0:
                tw, th = self._measure_text("Fuente", self.ui_font, src_font_px, True)
                bw, bh = tw + 8.0, th + 2.0
                if node.y < 0.30:
                    cands = [
                        (nx, ny - node_radius - bh / 2.0 - 3.0),
                        (nx + node_radius + bw / 2.0 + 4.0, ny),
                        (nx - node_radius - bw / 2.0 - 4.0, ny),
                        (nx, ny + node_radius + bh / 2.0 + 3.0),
                    ]
                else:
                    cands = [
                        (nx, ny + node_radius + bh / 2.0 + 3.0),
                        (nx + node_radius + bw / 2.0 + 4.0, ny),
                        (nx - node_radius - bw / 2.0 - 4.0, ny),
                        (nx, ny - node_radius - bh / 2.0 - 3.0),
                    ]
                is_iso = node.node_id in isolated_nodes
                for cx, cy in cands:
                    cbox = (cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0)
                    if cbox[0] < 4.0 or cbox[2] > w - 4.0 or cbox[1] < 4.0 or cbox[3] > h - 4.0:
                        continue
                    if any(self.boxes_overlap(cbox, pb) for pb in placed_boxes):
                        continue
                    if any(self.box_hits_segment(cbox, xa, ya, xb, yb) for xa, ya, xb, yb in pipe_segments):
                        continue
                    scene.badges.append(
                        BadgeVisual(
                            entity_kind="node",
                            entity_id=node.node_id,
                            x0=cbox[0],
                            y0=cbox[1],
                            x1=cbox[2],
                            y1=cbox[3],
                            text="Fuente",
                            fg=theme.INK_MUTED if is_iso else theme.INK_PRIMARY,
                            bg=theme.DOCK_BG,
                            border=theme.DOCK_DIVIDER if is_iso else theme.INK_PRIMARY,
                            border_width=1.0,
                            font_family=self.ui_font,
                            font_px=src_font_px,
                            bold=True,
                            kind="source",
                        )
                    )
                    placed_boxes.append(cbox)
                    break

        label_queue.sort(
            key=lambda item: (item[0], item[1], peak_util_map.get(item[2], 0.0)),
            reverse=True,
        )
        pipe_font_px = max(
            8,
            min(
                11,
                int(round((9.2 if (zoom < 1.15 or dense_mode) else 10.6) * min(1.12, max(0.86, scale_factor)))),
            ),
        )
        for (
            _priority,
            _u,
            pid,
            lx,
            ly,
            mx,
            is_vert,
            side,
            text_lbl,
            is_sel,
            is_over,
            is_hl,
            has_mark,
            has_ov_badge,
            nx_perp,
            ny_perp,
        ) in label_queue:
            if has_ov_badge and not is_sel:
                fg = theme.SHELL_TEXT
                bg = theme.SHELL_BG
                border = "#ef4444"
            else:
                fg = (
                    theme.ACCENT_INK
                    if is_sel
                    else ("#991b1b" if is_over else (theme.ACCENT_TEXT_ON_LIGHT if is_hl else theme.INK_PRIMARY))
                )
                bg = (
                    theme.ACCENT_PRIMARY
                    if is_sel
                    else ("#FEF2F2" if is_over else (theme.ACCENT_SOFT if is_hl else theme.PAPER_BG))
                )
                border = (
                    theme.INK_PRIMARY
                    if (is_sel or has_mark)
                    else ("#FCA5A5" if is_over else (theme.PIPE_HIGHLIGHT_PATH if is_hl else theme.PAPER_BORDER))
                )
            is_bold = bool(is_over or is_sel or is_hl or has_mark or has_ov_badge)
            tw, th = self._measure_text(text_lbl, self.mono_font, pipe_font_px, is_bold)
            bw, bh = tw + 6.0, th + 2.0
            cx, cy = lx, ly
            if is_vert:
                half_w = tw / 2.0
                cx = max(half_w + 6.0, min(w - half_w - 6.0, mx + side * (half_w + 9.0)))
            bx0, by0, bx1, by1 = cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0
            overlaps = any(
                self.boxes_overlap((bx0, by0, bx1, by1), pb) for pb in placed_boxes
            )
            if overlaps and not is_vert:
                for nudge in (3.5, 6.0):
                    ndx, ndy = nx_perp * nudge, ny_perp * nudge
                    cand = (bx0 + ndx, by0 + ndy, bx1 + ndx, by1 + ndy)
                    if not any(self.boxes_overlap(cand, pb) for pb in placed_boxes):
                        bx0, by0, bx1, by1 = cand
                        overlaps = False
                        break
            if overlaps and not is_sel and not has_mark:
                continue
            placed_boxes.append((bx0, by0, bx1, by1))
            scene.badges.append(
                BadgeVisual(
                    entity_kind="pipe",
                    entity_id=pid,
                    x0=bx0,
                    y0=by0,
                    x1=bx1,
                    y1=by1,
                    text=text_lbl,
                    fg=fg,
                    bg=bg,
                    border=border,
                    border_width=1.0,
                    font_family=self.mono_font,
                    font_px=pipe_font_px,
                    bold=is_bold,
                    kind="pipe_label",
                )
            )

        for node in graph.nodes():
            x, y = positions[node.node_id]
            r = node_radius
            is_dimmed_basin = (
                (basin_active and (node.node_id not in basin_nodes))
                or (tour_active and (node.node_id not in tour_nodes))
            )
            is_isolated = node.node_id in isolated_nodes
            is_hl_node = node.node_id in highlight_node_ids
            is_anim_wave = anim is not None and (node.node_id in anim.active_nodes)
            is_anim_cursor = anim is not None and (node.node_id == anim.cursor_node)
            is_anim_visited = anim is not None and (node.node_id in anim.visited_nodes)
            is_anim_backtrack = anim is not None and (node.node_id in anim.backtracked_nodes)

            if node.node_type == "sink":
                r += sink_extra_r
                fill = theme.NODE_SINK_FILL
                outline = theme.NODE_SINK_BORDER
                txt_fill = theme.NODE_SINK_TEXT
            elif node.node_type == "source":
                fill = theme.NODE_SOURCE_FILL
                outline = theme.NODE_SOURCE_BORDER
                txt_fill = theme.NODE_SOURCE_TEXT
            else:
                fill = theme.NODE_MANHOLE_FILL
                outline = theme.NODE_MANHOLE_BORDER
                txt_fill = theme.NODE_MANHOLE_TEXT

            if is_dimmed_basin:
                fill = theme.PAPER_SUBTLE
                outline = theme.DOCK_BG
                txt_fill = theme.DOCK_DIVIDER
            elif is_isolated:
                fill = theme.PAPER_SUBTLE
                outline = theme.DOCK_BG
                txt_fill = theme.INK_MUTED
            elif anim is not None:
                if is_anim_wave or is_anim_cursor:
                    fill = theme.ACCENT_PRIMARY
                    outline = theme.INK_PRIMARY
                    txt_fill = theme.ACCENT_INK
                elif is_anim_backtrack:
                    fill = theme.DOCK_BG
                    outline = theme.DOCK_DIVIDER
                    txt_fill = theme.INK_MUTED
                elif is_anim_visited:
                    fill = theme.ACCENT_SOFT
                    outline = theme.ACCENT_PRIMARY
                    txt_fill = theme.INK_PRIMARY
                elif node.node_id != selected_node_id:
                    fill = theme.PAPER_SUBTLE
                    outline = theme.DOCK_BG
                    txt_fill = theme.INK_MUTED
            elif has_traversal_focus:
                if is_hl_node:
                    if node.node_type == "manhole":
                        fill = theme.ACCENT_PRIMARY
                        outline = theme.INK_PRIMARY
                        txt_fill = theme.ACCENT_INK
                elif node.node_id != selected_node_id:
                    fill = theme.PAPER_SUBTLE
                    outline = theme.DOCK_BG
                    txt_fill = theme.INK_MUTED

            surcharge_vol = 0.0
            if snapshot and node.node_id in snapshot.node_states:
                ns = snapshot.node_states[node.node_id]
                surcharge_vol = ns.stored_volume_m3 + ns.surface_flooding_m3
            if (
                not is_dimmed_basin
                and anim is None
                and (not has_traversal_focus or is_hl_node or node.node_id == selected_node_id)
            ):
                scene.flood_rings.extend(
                    self._build_flood_rings(
                        node.node_id, x, y, r, surcharge_vol, scale_factor, sqrt_z
                    )
                )

            outer_col = None
            outer_r = 0.0
            outer_w = 0.0
            if is_anim_wave or is_anim_cursor:
                radar_pad = max(2.2, min(5.5 if is_anim_cursor else 4.2, r * 0.45))
                outer_col = theme.ACCENT_PRIMARY
                outer_r = r + radar_pad
                outer_w = max(1.5, min(2.8 if is_anim_cursor else 2.2, r * 0.28))
            elif (
                node.node_id == selected_node_id
                or (anim is None and node.node_id in highlight_node_ids)
            ) and not is_dimmed_basin:
                outer_col = (
                    theme.ACCENT_PRIMARY
                    if node.node_id == selected_node_id
                    else theme.PIPE_HIGHLIGHT_PATH
                )
                ring_pad = max(1.8, min(3.5, r * 0.32))
                outer_r = r + ring_pad
                outer_w = max(1.5, min(2.6, r * 0.25))

            show_label = node_radius >= 5.6 or node.node_type == "sink" or node.node_id == selected_node_id
            node_font_px = self._fit_node_font_px(node.node_id, self.ui_font, r) if show_label else 6

            node_is_focus = (
                (not is_dimmed_basin)
                and (
                    (anim is not None and (is_anim_wave or is_anim_cursor))
                    or (anim is None and is_hl_node)
                )
            )
            node_is_endpoint = (
                (not is_dimmed_basin)
                and ((node.node_id in route_endpoints) or is_anim_cursor)
            )

            scene.nodes.append(
                NodeVisual(
                    node_id=node.node_id,
                    x=x,
                    y=y,
                    radius=r,
                    fill=fill,
                    outline=outline,
                    outline_width=max(1.1, min(2.0, r * 0.18)),
                    dashed=(is_isolated and not is_dimmed_basin),
                    text_color=txt_fill,
                    font_px=node_font_px,
                    show_label=show_label,
                    outer_ring_color=outer_col,
                    outer_ring_radius=outer_r,
                    outer_ring_width=outer_w,
                    is_focus=node_is_focus,
                    is_route_endpoint=node_is_endpoint,
                )
            )

            if (
                is_isolated
                and not is_dimmed_basin
                and (node.node_id in cut_boundary_nodes or node.node_id == selected_node_id)
            ):
                iso_font_px = max(8, min(10, src_font_px))
                tw, th = self._measure_text("[AISLADO DE 31]", self.mono_font, iso_font_px, True)
                bw, bh = tw + 8.0, th + 2.0
                iso_y = max(12.0, y - r - 12.0)
                scene.badges.append(
                    BadgeVisual(
                        entity_kind="node",
                        entity_id=node.node_id,
                        x0=x - bw / 2.0,
                        y0=iso_y - bh / 2.0,
                        x1=x + bw / 2.0,
                        y1=iso_y + bh / 2.0,
                        text="[AISLADO DE 31]",
                        fg=theme.INK_PRIMARY,
                        bg=theme.DOCK_BG,
                        border=theme.INK_PRIMARY,
                        border_width=1.0,
                        font_family=self.mono_font,
                        font_px=iso_font_px,
                        bold=True,
                        kind="isolated",
                    )
                )

        return scene
