"""Lienzo cartográfico interactivo para el grafo dirigido de la red de alcantarillado."""

from dataclasses import dataclass
import math
import tkinter as tk
from typing import Callable, Dict, List, Optional, Set, Tuple

from src.algorithms.analysis import classify_overload_persistence, classify_utilization
from src.algorithms.traversals import TraversalAnimFrame
from src.data_structures import DirectedGraph, ManholeNode, PipeEdge
from src.simulation.models import PipeIntervention, TimeStepSnapshot
from . import theme


def _blend_hex(hex_fg: str, hex_bg: str, t: float) -> str:
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


@dataclass
class _PulseMeta:
    """Metadatos geométricos de un marcador direccional animado por velocidad de Manning."""

    item_id: int
    pipe_id: str
    sx1: float
    sy1: float
    ux: float
    uy: float
    usable_len: float
    velocity_ms: float
    phase_offset: float
    chevron_size: float
    line_width: float


class NetworkCanvas(tk.Canvas):
    """Canvas interactivo con retícula técnica, cirugía cartográfica, pulsos de Manning y tooltips."""

    _PULSE_TICK_MS = 55
    _BASE_PX_PER_MPS = 28.0

    def __init__(
        self,
        master: tk.Misc,
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
        dpi_scale: float = 1.0,
        on_select_pipe: Optional[Callable[[str], None]] = None,
        on_select_node: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            bg=theme.CANVAS_BG,
            highlightthickness=1,
            highlightbackground=theme.CANVAS_BORDER,
            bd=0,
            **kwargs,
        )
        self.ui_font = ui_font
        self.mono_font = mono_font
        self.dpi_scale = max(1.0, float(dpi_scale))
        self.graph: Optional[DirectedGraph] = None
        self.snapshot: Optional[TimeStepSnapshot] = None
        self.on_select_pipe = on_select_pipe
        self.on_select_node = on_select_node

        self.selected_pipe_id: Optional[str] = None
        self.selected_node_id: Optional[str] = None
        self.highlight_pipe_ids: Set[str] = set()
        self.highlight_node_ids: Set[str] = set()
        self.show_pipe_labels: bool = True
        self.show_util_labels: bool = True

        # Capas de cirugía cartográfica, cuenca aportante, guía de sustentación, mapa de estrés y pulsos
        self._interventions: Dict[str, PipeIntervention] = {}
        self._isolated_nodes: Set[str] = set()
        self._isolated_pipes: Set[str] = set()
        self._basin_active: bool = False
        self._basin_nodes: Set[str] = set()
        self._basin_pipes: Set[str] = set()
        self._tour_active: bool = False
        self._tour_nodes: Set[str] = set()
        self._tour_pipes: Set[str] = set()
        self._cam_anim_after: Optional[str] = None
        self._map_mode: str = "instant"
        self._peak_util_map: Dict[str, float] = {}
        self._overload_minutes_map: Dict[str, float] = {}
        self._total_duration_min: float = 90.0
        self._traversal_frame: Optional[TraversalAnimFrame] = None

        self._is_playing: bool = False
        self._playback_speed_factor: float = 1.0
        self._pulse_time_s: float = 0.0
        self._pulse_after_id: Optional[str] = None
        self._pulse_items: List[_PulseMeta] = []

        # Caché de actualización rápida en reproducción (sin reconstruir todo el Canvas)
        self._fast_cache_valid: bool = False
        self._pipe_draw_refs: Dict[str, tuple] = {}
        self._pipe_label_refs: Dict[str, tuple] = {}
        self._node_ring_refs: List[tuple] = []
        self._pulse_geom_refs: Dict[str, tuple] = {}
        self._scale_factor_cache: float = 1.0

        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._drag_start: Optional[Tuple[int, int]] = None
        self._dragged: bool = False
        self._resize_after: Optional[str] = None

        self._item_to_pipe: Dict[int, str] = {}
        self._item_to_node: Dict[int, str] = {}
        self._tooltip_window: Optional[tk.Toplevel] = None
        self._last_hover_key: Optional[str] = None

        self._build_overlays()

        self.bind("<Configure>", self._on_configure)
        self.bind("<MouseWheel>", self._on_mouse_wheel)
        self.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, 1.12))
        self.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / 1.12))
        self.bind("<ButtonPress-1>", self._on_left_press)
        self.bind("<B1-Motion>", self._on_left_drag)
        self.bind("<ButtonRelease-1>", self._on_left_release)
        self.bind("<Double-Button-1>", self._on_double_click)
        self.bind("<Motion>", self._on_mouse_move)
        self.bind("<Leave>", lambda _e: self._hide_tooltip())
        self.bind("<Destroy>", self._on_destroy)

    def _build_overlays(self) -> None:
        """Crea controles flotantes de zoom/vista, sello cartográfico y guía de interacción."""
        self._stamp_lbl = tk.Label(
            self,
            text="PLANO HIDRÁULICO · 46 NODOS · 59 TRAMOS",
            bg=theme.DOCK_BG,
            fg=theme.INK_PRIMARY,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
            padx=9,
            pady=4,
            font=(self.mono_font, 7, "bold"),
        )
        self._stamp_lbl.place(relx=0.0, rely=0.0, x=12, y=12, anchor="nw")

        self._zoom_bar = tk.Frame(
            self,
            bg=theme.CANVAS_FLOAT_BG,
            highlightthickness=1,
            highlightbackground=theme.CANVAS_FLOAT_BORDER,
        )
        self._zoom_bar.place(relx=1.0, rely=0.0, x=-12, y=12, anchor="ne")

        def _make_mini_btn(txt: str, cmd: Callable[[], None]) -> tk.Button:
            b = tk.Button(
                self._zoom_bar,
                text=txt,
                command=cmd,
                bg=theme.CANVAS_FLOAT_BG,
                fg=theme.CANVAS_FLOAT_FG,
                activebackground=theme.CANVAS_FLOAT_HOVER,
                activeforeground=theme.CANVAS_FLOAT_FG,
                relief="flat",
                bd=0,
                padx=8,
                pady=4,
                font=(self.ui_font, 8, "bold"),
                cursor="hand2",
            )
            b.bind("<Enter>", lambda _e: b.configure(bg=theme.CANVAS_FLOAT_HOVER))
            b.bind("<Leave>", lambda _e: b.configure(bg=theme.CANVAS_FLOAT_BG))
            return b

        _make_mini_btn("−", self.zoom_out).pack(side=tk.LEFT)
        tk.Frame(self._zoom_bar, bg=theme.ACCENT_PRIMARY, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=4)
        self._lbl_zoom = tk.Label(
            self._zoom_bar,
            text="100%",
            bg=theme.CANVAS_FLOAT_BG,
            fg=theme.CANVAS_FLOAT_FG,
            font=(self.mono_font, 8, "bold"),
            width=5,
        )
        self._lbl_zoom.pack(side=tk.LEFT, padx=2)
        tk.Frame(self._zoom_bar, bg=theme.ACCENT_PRIMARY, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=4)
        _make_mini_btn("+", self.zoom_in).pack(side=tk.LEFT)
        tk.Frame(self._zoom_bar, bg=theme.ACCENT_PRIMARY, width=1).pack(side=tk.LEFT, fill=tk.Y, pady=4)
        _make_mini_btn("Ajustar", self.reset_view).pack(side=tk.LEFT)

        self._hint_bar = tk.Label(
            self,
            text="Arrastrar: mover  ·  Rueda: zoom  ·  Clic: inspeccionar  ·  Doble clic: ajustar",
            bg=theme.DOCK_BG,
            fg=theme.INK_PRIMARY,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
            padx=9,
            pady=4,
            font=(self.ui_font, 8),
        )
        self._hint_bar.place(relx=0.0, rely=1.0, x=12, y=-12, anchor="sw")

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self:
            self._hide_tooltip()
            self.stop_pulse_animation()
            self._stop_camera_animation()
            if self._resize_after is not None:
                try:
                    self.after_cancel(self._resize_after)
                except tk.TclError:
                    pass
                self._resize_after = None

    def _on_configure(self, event: tk.Event) -> None:
        min_stamp_w = int(520 * min(1.25, self.dpi_scale))
        min_stamp_h = int(340 * min(1.25, self.dpi_scale))
        if event.width >= min_stamp_w and event.height >= min_stamp_h:
            self._stamp_lbl.place(relx=0.0, rely=0.0, x=12, y=12, anchor="nw")
        else:
            self._stamp_lbl.place_forget()

        if (
            not self._tour_active
            and event.width >= int(480 * min(1.25, self.dpi_scale))
            and event.height >= min_stamp_h
        ):
            self._hint_bar.place(relx=0.0, rely=1.0, x=12, y=-12, anchor="sw")
        else:
            self._hint_bar.place_forget()

        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(30, self._handle_deferred_resize)

    def _handle_deferred_resize(self) -> None:
        self._resize_after = None
        self.redraw()

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
        self._fast_cache_valid = False
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
            if self._map_mode == "peak":
                txt = f"PICO MÁXIMO ACUMULADO · HASTA t = {t_min:.1f} min"
            elif self._map_mode == "overload_minutes":
                txt = f"MINUTOS EN SOBRECARGA (>100%) · HASTA t = {t_min:.1f} min"
            else:
                txt = f"PLANO HIDRÁULICO · {n_nodes} NODOS · {n_pipes} TRAMOS · t = {t_min:.1f} min"
        self._stamp_lbl.configure(text=txt)

    def set_stress_maps(
        self,
        peak_util: Optional[Dict[str, float]] = None,
        overload_minutes: Optional[Dict[str, float]] = None,
        total_duration_min: float = 90.0,
    ) -> None:
        """Actualiza los mapas acumulados hasta el instante actual sin forzar redibujo inmediato."""
        if peak_util is not None:
            self._peak_util_map = dict(peak_util)
        if overload_minutes is not None:
            new_ov = dict(overload_minutes)
            if self._map_mode == "overload_minutes":
                prev_badges = {pid for pid, v in self._overload_minutes_map.items() if v >= 0.5}
                new_badges = {pid for pid, v in new_ov.items() if v >= 0.5}
                if prev_badges != new_badges:
                    self._fast_cache_valid = False
            self._overload_minutes_map = new_ov
        self._total_duration_min = max(1.0, float(total_duration_min))

    def set_snapshot(self, snapshot: Optional[TimeStepSnapshot]) -> None:
        self.snapshot = snapshot
        self._update_stamp_label()
        has_traversal = bool(
            self._traversal_frame is not None
            or self.highlight_pipe_ids
            or self.highlight_node_ids
        )
        if self._fast_cache_valid and snapshot is not None and not has_traversal:
            self._fast_update_snapshot(snapshot)
        else:
            self.redraw()

    def set_interventions(
        self,
        interventions: Optional[Dict[str, PipeIntervention]] = None,
        isolated_nodes: Optional[Set[str]] = None,
        isolated_pipes: Optional[Set[str]] = None,
    ) -> None:
        self._interventions = dict(interventions or {})
        self._isolated_nodes = set(isolated_nodes or ())
        self._isolated_pipes = set(isolated_pipes or ())
        self._fast_cache_valid = False
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
        self._fast_cache_valid = False
        self.redraw()

    def set_tour_focus(
        self,
        node_ids: Optional[Set[str]],
        pipe_ids: Optional[Set[str]],
    ) -> None:
        """Activa o desactiva el enfoque visual de la Guía de Sustentación."""
        if node_ids is None or pipe_ids is None:
            self._tour_active = False
            self._tour_nodes.clear()
            self._tour_pipes.clear()
            w = self.winfo_width()
            h = self.winfo_height()
            min_h = int(340 * min(1.25, self.dpi_scale))
            if w >= int(480 * min(1.25, self.dpi_scale)) and h >= min_h:
                self._hint_bar.place(relx=0.0, rely=1.0, x=12, y=-12, anchor="sw")
        else:
            self._tour_active = True
            self._tour_nodes = set(node_ids)
            self._tour_pipes = set(pipe_ids)
            self._hint_bar.place_forget()
        self._fast_cache_valid = False
        self.redraw()

    def set_map_mode(
        self,
        mode: str,
        peak_util: Optional[Dict[str, float]] = None,
        overload_minutes: Optional[Dict[str, float]] = None,
        total_duration_min: float = 90.0,
    ) -> None:
        """Alterna entre visualización Instantánea, Pico Máximo y Minutos en Sobrecarga."""
        if mode not in ("instant", "peak", "overload_minutes"):
            mode = "instant"
        self._map_mode = mode
        if peak_util is not None:
            self._peak_util_map = dict(peak_util)
        if overload_minutes is not None:
            self._overload_minutes_map = dict(overload_minutes)
        self._total_duration_min = max(1.0, float(total_duration_min))
        self._fast_cache_valid = False
        self._update_stamp_label()
        self.redraw()

    def _resolve_pipe_visual_state(
        self,
        pipe_id: str,
        ps,
        is_closed: bool,
    ) -> Tuple[str, int, bool, bool, float, str]:
        """Retorna (color_hex, tier_idx, is_overloaded, is_critical, display_val, suffix_lbl) según modo activo."""
        if self._map_mode == "overload_minutes":
            ov_min = self._overload_minutes_map.get(pipe_id, 0.0)
            tier, col, _ = classify_overload_persistence(ov_min, self._total_duration_min)
            is_over = (tier >= 3) and not is_closed
            is_crit = (tier >= 2) and not is_closed
            lbl = f"{ov_min:.0f}m" if ov_min >= 0.5 else "0m"
            return (theme.INK_PRIMARY if is_closed else col, tier, is_over, is_crit, ov_min, lbl)

        if is_closed:
            return (theme.INK_PRIMARY, 0, False, False, 0.0, "CERRADA")

        if self._map_mode == "peak":
            u = self._peak_util_map.get(pipe_id, ps.utilization_pct if ps is not None else 0.0)
            cat = classify_utilization(u)
            col = "#991b1b" if cat.is_overloaded else cat.color_hex
            lbl_u = f"{u / 1000.0:.1f}k%" if u >= 1000.0 else f"{u:.0f}%"
            return (
                col,
                cat.tier_index,
                cat.is_overloaded,
                u > 75.0,
                u,
                lbl_u,
            )

        if ps is None:
            return (theme.PIPE_IDLE_COLOR, 0, False, False, 0.0, "")
        col = "#991b1b" if ps.category.is_overloaded else ps.category.color_hex
        u_inst = ps.utilization_pct
        lbl_inst = f"{u_inst / 1000.0:.1f}k%" if u_inst >= 1000.0 else f"{u_inst:.0f}%"
        return (
            col,
            ps.category.tier_index,
            ps.category.is_overloaded,
            u_inst > 75.0,
            u_inst,
            lbl_inst,
        )

    def set_traversal_frame(self, frame: Optional[TraversalAnimFrame]) -> None:
        self._traversal_frame = frame
        self._fast_cache_valid = False
        self.redraw()

    def set_playing(self, playing: bool, speed_factor: float = 1.0) -> None:
        self._playback_speed_factor = max(0.5, min(3.5, float(speed_factor)))
        if playing and not self._is_playing:
            self._is_playing = True
            self._rebuild_pulses_from_cache() if self._fast_cache_valid else self.redraw()
            self._schedule_pulse_tick()
        elif not playing and self._is_playing:
            self.stop_pulse_animation()
            for meta in self._pulse_items:
                self._item_to_pipe.pop(meta.item_id, None)
            self.delete("flow_pulse")
            self._pulse_items.clear()

    def stop_pulse_animation(self) -> None:
        self._is_playing = False
        if self._pulse_after_id is not None:
            try:
                self.after_cancel(self._pulse_after_id)
            except tk.TclError:
                pass
            self._pulse_after_id = None

    def _schedule_pulse_tick(self) -> None:
        if not self._is_playing:
            return
        if self._pulse_after_id is not None:
            try:
                self.after_cancel(self._pulse_after_id)
            except tk.TclError:
                pass
        self._pulse_after_id = self.after(self._PULSE_TICK_MS, self._tick_flow_pulses)

    def _tick_flow_pulses(self) -> None:
        self._pulse_after_id = None
        if not self._is_playing:
            return
        dt_s = (self._PULSE_TICK_MS / 1000.0) * self._playback_speed_factor
        self._pulse_time_s += dt_s
        for meta in self._pulse_items:
            pts = self._chevron_coords(meta)
            try:
                self.coords(meta.item_id, *pts)
            except tk.TclError:
                pass
        self._schedule_pulse_tick()

    def _chevron_coords(self, meta: _PulseMeta) -> Tuple[float, ...]:
        travel = (
            self._pulse_time_s * meta.velocity_ms * self._BASE_PX_PER_MPS * math.sqrt(self._zoom)
            + meta.phase_offset * meta.usable_len
        ) % meta.usable_len
        dist_along = 5.0 + travel
        tx = meta.sx1 + meta.ux * dist_along
        ty = meta.sy1 + meta.uy * dist_along
        nx_p, ny_p = -meta.uy, meta.ux
        sz = meta.chevron_size
        bx = tx - meta.ux * sz
        by = ty - meta.uy * sz
        return (
            bx + nx_p * (sz * 0.72),
            by + ny_p * (sz * 0.72),
            tx,
            ty,
            bx - nx_p * (sz * 0.72),
            by - ny_p * (sz * 0.72),
        )

    def _rebuild_pulses_from_cache(self) -> None:
        for meta in self._pulse_items:
            self._item_to_pipe.pop(meta.item_id, None)
        self.delete("flow_pulse")
        self._pulse_items.clear()
        if not self._is_playing or self.snapshot is None or self._traversal_frame is not None:
            return

        for pid, geom in self._pulse_geom_refs.items():
            sx1, sy1, ux, uy, seg_len, base_w, vel_ms = geom
            ps = self.snapshot.pipe_states.get(pid)
            if ps is None or ps.flow_m3s <= 1e-5 or ps.conveyed_flow_m3s <= 1e-5:
                continue
            if ps.effective_velocity_ms is not None:
                vel_ms = ps.effective_velocity_ms
            _col, tier_idx, is_overloaded, *_ = self._resolve_pipe_visual_state(
                pid, ps, False
            )
            usable = max(8.0, seg_len - 13.0)
            n_pulses = 3 if (seg_len > 115.0 or is_overloaded) else 2
            chev_col = theme.INK_PRIMARY if tier_idx in (0, 1) else theme.PAPER_BG
            chev_sz = max(3.6, min(5.4, base_w * 0.88))
            lw = max(1.4, min(2.2, base_w * 0.42))
            for p_idx in range(n_pulses):
                meta = _PulseMeta(
                    item_id=-1,
                    pipe_id=pid,
                    sx1=sx1,
                    sy1=sy1,
                    ux=ux,
                    uy=uy,
                    usable_len=usable,
                    velocity_ms=vel_ms,
                    phase_offset=p_idx / float(n_pulses),
                    chevron_size=chev_sz,
                    line_width=lw,
                )
                pts = self._chevron_coords(meta)
                cid = self.create_line(
                    *pts,
                    fill=chev_col,
                    width=lw,
                    capstyle=tk.ROUND,
                    joinstyle=tk.ROUND,
                    tags=("flow_pulse",),
                )
                meta.item_id = cid
                self._pulse_items.append(meta)
                self._item_to_pipe[cid] = pid

        if self._pulse_items:
            try:
                self.tag_lower("flow_pulse", "node_layer")
            except tk.TclError:
                pass

    def _fast_update_snapshot(self, snap: TimeStepSnapshot) -> None:
        # 1. Actualizar color, ancho y halo de sobrecarga de tuberías en sitio (< 1 ms)
        active_pulse_sig: Dict[str, Tuple[int, str]] = {}
        for pid, (line_id, glow_id, base_width, is_closed) in self._pipe_draw_refs.items():
            ps = snap.pipe_states.get(pid)
            if ps is None:
                continue
            color, tier_idx, is_over, _is_crit, _disp_val, _suf = self._resolve_pipe_visual_state(
                pid, ps, is_closed
            )
            w = base_width + (1.5 if is_over else 0.0)
            self.itemconfigure(line_id, fill=color, width=w)
            if glow_id is not None:
                self.itemconfigure(glow_id, state=tk.NORMAL if is_over else tk.HIDDEN, width=w + 4.0)

            if self._is_playing and not is_closed and ps.flow_m3s > 1e-5 and ps.conveyed_flow_m3s > 1e-5 and pid in self._pulse_geom_refs:
                seg_len = self._pulse_geom_refs[pid][4]
                n_pulses = 3 if (seg_len > 115.0 or is_over) else 2
                chev_col = theme.INK_PRIMARY if tier_idx in (0, 1) else theme.PAPER_BG
                active_pulse_sig[pid] = (n_pulses, chev_col)

        # 2. Actualizar etiquetas en sitio sin re-calcular bbox salvo cambio de longitud o peso tipográfico
        new_label_refs: Dict[str, tuple] = {}
        for pid, (rect_id, txt_id, prefix_parts, is_sel, is_hl, has_mark, is_closed, last_len, font_sz, last_bold) in self._pipe_label_refs.items():
            ps = snap.pipe_states.get(pid)
            if ps is None:
                new_label_refs[pid] = (rect_id, txt_id, prefix_parts, is_sel, is_hl, has_mark, is_closed, last_len, font_sz, last_bold)
                continue
            _col, _tier, is_over, _is_crit, ov_or_u, suf_lbl = self._resolve_pipe_visual_state(
                pid, ps, is_closed
            )
            has_ov_badge = (
                self._map_mode == "overload_minutes"
                and not is_closed
                and ov_or_u >= 0.5
            )
            if has_ov_badge:
                ov_badge_lbl = f"{ov_or_u:.0f}m >100%"
                if prefix_parts:
                    if self.show_pipe_labels and prefix_parts[-1] == pid:
                        text_lbl = " ".join(prefix_parts[:-1] + [f"{pid} · {ov_badge_lbl}"])
                    else:
                        text_lbl = " ".join(prefix_parts + [ov_badge_lbl])
                else:
                    text_lbl = f"{pid} · {ov_badge_lbl}" if self.show_pipe_labels else ov_badge_lbl
                if is_sel:
                    fg = theme.ACCENT_INK
                    bg = theme.ACCENT_PRIMARY
                    border = theme.INK_PRIMARY
                else:
                    fg = theme.SHELL_TEXT
                    bg = theme.SHELL_BG
                    border = "#ef4444"
            else:
                parts = list(prefix_parts)
                if self.show_util_labels and not is_closed and suf_lbl:
                    parts.append(suf_lbl)
                text_lbl = " ".join(parts)
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
            new_bold = bool(is_over or is_sel or is_hl or has_mark or has_ov_badge)
            if new_bold != last_bold:
                self.itemconfigure(
                    txt_id,
                    text=text_lbl,
                    fill=fg,
                    font=(self.mono_font, font_sz, "bold" if new_bold else "normal"),
                )
            else:
                self.itemconfigure(txt_id, text=text_lbl, fill=fg)
            if len(text_lbl) != last_len or new_bold != last_bold:
                bbox = self.bbox(txt_id)
                if bbox is not None:
                    self.coords(rect_id, bbox[0] - 3, bbox[1] - 1, bbox[2] + 3, bbox[3] + 1)
                last_len = len(text_lbl)
                last_bold = new_bold
            self.itemconfigure(rect_id, fill=bg, outline=border)
            new_label_refs[pid] = (rect_id, txt_id, prefix_parts, is_sel, is_hl, has_mark, is_closed, last_len, font_sz, last_bold)
        self._pipe_label_refs = new_label_refs

        # 3. Actualizar anillos topográficos de inundación en pozos
        for fid in self.find_withtag("flood_ring"):
            self._item_to_node.pop(fid, None)
        self.delete("flood_ring")
        sf = self._scale_factor_cache
        sqrt_z = math.sqrt(self._zoom)
        created_rings = False
        for nid, x, y, r in self._node_ring_refs:
            ns = snap.node_states.get(nid)
            surcharge_vol = (
                (ns.stored_volume_m3 + ns.surface_flooding_m3) if ns is not None else 0.0
            )
            if self._draw_flood_rings(nid, x, y, r, surcharge_vol, sf, sqrt_z):
                created_rings = True
        if created_rings:
            try:
                self.tag_lower("flood_ring", "node_layer")
            except tk.TclError:
                pass

        # 4. Actualizar pulsos solo si cambió el conjunto activo o cantidad de pulsos
        if self._is_playing:
            cur_counts: Dict[str, int] = {}
            for m in self._pulse_items:
                cur_counts[m.pipe_id] = cur_counts.get(m.pipe_id, 0) + 1
            desired_counts = {pid: sig[0] for pid, sig in active_pulse_sig.items()}
            if cur_counts != desired_counts:
                self._rebuild_pulses_from_cache()
            else:
                for m in self._pulse_items:
                    sig = active_pulse_sig.get(m.pipe_id)
                    if sig is not None:
                        self.itemconfigure(m.item_id, fill=sig[1])

    def _draw_flood_rings(
        self,
        nid: str,
        x: float,
        y: float,
        r: float,
        surcharge_vol: float,
        sf: float,
        sqrt_z: float,
    ) -> bool:
        if surcharge_vol <= 1e-3:
            return False
        n_rings = 1 if surcharge_vol < 5.0 else (2 if surcharge_vol < 60.0 else 3)
        max_extra = min(14.5, 2.6 + 3.4 * math.log10(1.0 + surcharge_vol)) * sf * sqrt_z
        for k in range(n_rings, 0, -1):
            ring_r = r + (max_extra * k / n_rings)
            is_inner_intense = k == 1 and surcharge_vol >= 25.0
            ring_col = (
                theme.NODE_SURCHARGE_RING_DEEP if is_inner_intense else theme.NODE_SURCHARGE_RING
            )
            ring_kw = {
                "outline": ring_col,
                "width": 1.5 if is_inner_intense else 1.25,
                "tags": ("flood_ring",),
            }
            if k == n_rings and n_rings >= 2:
                ring_kw["dash"] = (3, 3)
            ring_id = self.create_oval(
                x - ring_r,
                y - ring_r,
                x + ring_r,
                y + ring_r,
                **ring_kw,
            )
            self._item_to_node[ring_id] = nid
        return True

    def set_highlights(
        self,
        pipe_ids: Optional[Set[str]] = None,
        node_ids: Optional[Set[str]] = None,
    ) -> None:
        self.highlight_pipe_ids = set(pipe_ids or ())
        self.highlight_node_ids = set(node_ids or ())
        self._fast_cache_valid = False
        self.redraw()

    def select_pipe(self, pipe_id: Optional[str]) -> None:
        self.selected_pipe_id = pipe_id
        self.selected_node_id = None
        self._fast_cache_valid = False
        self.redraw()

    def select_node(self, node_id: Optional[str]) -> None:
        self.selected_node_id = node_id
        self.selected_pipe_id = None
        self._fast_cache_valid = False
        self.redraw()

    def zoom_in(self) -> None:
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        self._zoom_at(w / 2.0, h / 2.0, 1.18)

    def zoom_out(self) -> None:
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        self._zoom_at(w / 2.0, h / 2.0, 1.0 / 1.18)

    def reset_view(self) -> None:
        self._stop_camera_animation()
        self._hide_tooltip()
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._update_zoom_label()
        self._fast_cache_valid = False
        self.redraw()

    def _stop_camera_animation(self) -> None:
        if self._cam_anim_after is not None:
            try:
                self.after_cancel(self._cam_anim_after)
            except tk.TclError:
                pass
            self._cam_anim_after = None

    def animate_reset_view(self, steps: int = 10, step_ms: int = 18) -> None:
        """Devuelve la cámara al encuadre general de los 46 nodos de forma interpolada."""
        self._animate_camera_to(1.0, 0.0, 0.0, steps=steps, step_ms=step_ms)

    def animate_focus_region(
        self,
        node_ids: Set[str],
        pipe_ids: Optional[Set[str]] = None,
        left_reserve_px: float = 0.0,
        steps: int = 12,
        step_ms: int = 18,
    ) -> None:
        """Desplaza y acerca suavemente la cámara sobre los nodos del hallazgo dejando margen izquierdo."""
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

        w = max(320, self.winfo_width())
        h = max(240, self.winfo_height())
        pad_x, pad_y = self._compute_padding(w, h)
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

        # Dejar libre el margen izquierdo donde vive la ficha flotante de hallazgo
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
            self._fast_cache_valid = False
            self.redraw()
            return

        def _tick(step_idx: int) -> None:
            self._cam_anim_after = None
            t = step_idx / float(total_steps)
            eased = 1.0 - (1.0 - t) * (1.0 - t)
            self._zoom = start_zoom + (target_zoom - start_zoom) * eased
            self._pan_x = start_px + (target_pan_x - start_px) * eased
            self._pan_y = start_py + (target_pan_y - start_py) * eased
            self._update_zoom_label()
            self._fast_cache_valid = False
            self.redraw()
            if step_idx < total_steps:
                try:
                    self._cam_anim_after = self.after(step_ms, lambda: _tick(step_idx + 1))
                except tk.TclError:
                    self._cam_anim_after = None

        _tick(1)

    def focus_node(self, node_id: str) -> None:
        """Centra el lienzo sobre el nodo indicado manteniendo el nivel de zoom actual."""
        if self.graph is None:
            return
        node = self.graph.get_node(node_id)
        if node is None:
            return
        self._center_world_point(node.x, node.y)

    def focus_pipe(self, pipe_id: str) -> None:
        """Centra el lienzo sobre el punto medio de la tubería indicada."""
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
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        pad_x, pad_y = self._compute_padding(w, h)
        base_x = pad_x + nx * (w - 2 * pad_x)
        base_y = pad_y + ny * (h - 2 * pad_y)
        cx, cy = w / 2.0, h / 2.0
        self._pan_x = -(base_x - cx) * self._zoom
        self._pan_y = -(base_y - cy) * self._zoom
        self._fast_cache_valid = False
        self.redraw()

    def _update_zoom_label(self) -> None:
        self._lbl_zoom.configure(text=f"{int(round(self._zoom * 100))}%")

    def _compute_padding(self, w: int, h: int) -> Tuple[float, float]:
        pad_x = max(28.0, min(68.0, w * 0.08))
        pad_y = max(32.0, min(64.0, h * 0.11))
        return pad_x, pad_y

    def _world_to_screen(self, nx: float, ny: float) -> Tuple[float, float]:
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        pad_x, pad_y = self._compute_padding(w, h)
        base_x = pad_x + nx * (w - 2 * pad_x)
        base_y = pad_y + ny * (h - 2 * pad_y)
        cx, cy = w / 2.0, h / 2.0
        sx = cx + (base_x - cx) * self._zoom + self._pan_x
        sy = cy + (base_y - cy) * self._zoom + self._pan_y
        return sx, sy

    def _on_mouse_wheel(self, event: tk.Event) -> None:
        self._stop_camera_animation()
        factor = 1.12 if event.delta > 0 else 1.0 / 1.12
        self._zoom_at(event.x, event.y, factor)

    def _zoom_at(self, mx: float, my: float, factor: float) -> None:
        new_zoom = max(0.55, min(4.5, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-6:
            return
        self._hide_tooltip()
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        cx, cy = w / 2.0, h / 2.0
        scale_ratio = new_zoom / self._zoom
        self._pan_x = (mx - cx) - scale_ratio * (mx - cx - self._pan_x)
        self._pan_y = (my - cy) - scale_ratio * (my - cy - self._pan_y)
        self._zoom = new_zoom
        self._update_zoom_label()
        self._fast_cache_valid = False
        self.redraw()

    def _on_left_press(self, event: tk.Event) -> None:
        self._stop_camera_animation()
        self._drag_start = (event.x, event.y)
        self._dragged = False

    def _on_left_drag(self, event: tk.Event) -> None:
        if self._drag_start is None:
            return
        dx = event.x - self._drag_start[0]
        dy = event.y - self._drag_start[1]
        if abs(dx) > 3 or abs(dy) > 3:
            self._dragged = True
        if self._dragged:
            self._pan_x += dx
            self._pan_y += dy
            self._drag_start = (event.x, event.y)
            self._hide_tooltip()
            self._fast_cache_valid = False
            self.redraw()

    def _on_left_release(self, event: tk.Event) -> None:
        was_dragged = self._dragged
        self._drag_start = None
        self._dragged = False
        if was_dragged:
            return

        clicked = self.find_overlapping(event.x - 5, event.y - 5, event.x + 5, event.y + 5)
        for item in reversed(clicked):
            if item in self._item_to_node:
                nid = self._item_to_node[item]
                self.select_node(nid)
                if self.on_select_node:
                    self.on_select_node(nid)
                return
        for item in reversed(clicked):
            if item in self._item_to_pipe:
                pid = self._item_to_pipe[item]
                self.select_pipe(pid)
                if self.on_select_pipe:
                    self.on_select_pipe(pid)
                return

    def _on_double_click(self, event: tk.Event) -> None:
        clicked = self.find_overlapping(event.x - 4, event.y - 4, event.x + 4, event.y + 4)
        for item in clicked:
            if item in self._item_to_node or item in self._item_to_pipe:
                return
        self.reset_view()

    def _on_mouse_move(self, event: tk.Event) -> None:
        if self.graph is None or self._drag_start is not None:
            return
        items = self.find_overlapping(event.x - 4, event.y - 4, event.x + 4, event.y + 4)
        hover_key = None
        tooltip_text = None
        for item in reversed(items):
            if item in self._item_to_node:
                nid = self._item_to_node[item]
                node = self.graph.get_node(nid)
                if node:
                    hover_key = f"node:{nid}"
                    tooltip_text = self._build_node_tooltip(node)
                    break
            if item in self._item_to_pipe:
                pid = self._item_to_pipe[item]
                pipe = self.graph.get_pipe(pid)
                if pipe:
                    hover_key = f"pipe:{pid}"
                    tooltip_text = self._build_pipe_tooltip(pipe)
                    break

        if tooltip_text and hover_key != self._last_hover_key:
            self._last_hover_key = hover_key
            self._show_tooltip(event.x_root + 14, event.y_root + 14, tooltip_text)
        elif not tooltip_text:
            self._last_hover_key = None
            self._hide_tooltip()

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
            if ps.is_closed:
                lines.append(
                    f"Estado (t={self.snapshot.time_min:.0f}m): CERRADA 100%  ·  Caudal conducido: 0.0000 m³/s"
                )
            else:
                lines.append(
                    f"Caudal conducido (t={self.snapshot.time_min:.0f}m): {ps.flow_m3s:.4f} m³/s  ·  Utilización: {ps.utilization_pct:.1f}% ({ps.category.label})"
                )
                if ps.utilization_pct > 100.5:
                    lines.append(
                        f"Demanda: {ps.demand_flow_m3s:.4f} m³/s ({ps.utilization_pct / 100.0:.2f}× Qmax)  ·  Exceso: {ps.excess_flow_m3s:.4f} m³/s"
                    )
        if self.snapshot and pipe.pipe_id in self._peak_util_map:
            pk = self._peak_util_map[pipe.pipe_id]
            lines.append(f"Pico hasta t = {self.snapshot.time_min:.0f} min: {pk:.1f}%")
        if pipe.pipe_id in self._overload_minutes_map:
            ov_min = self._overload_minutes_map[pipe.pipe_id]
            _, _, ov_desc = classify_overload_persistence(ov_min, self._total_duration_min)
            t_lbl = f" (t ≤ {self.snapshot.time_min:.0f}m)" if self.snapshot else ""
            lines.append(f"Sobrecarga acumulada{t_lbl}: {ov_min:.0f} min >100% ({ov_desc})")
        return "\n".join(lines)

    def _show_tooltip(self, x_root: int, y_root: int, text: str) -> None:
        self._hide_tooltip()
        tw = tk.Toplevel(self)
        tw.wm_overrideredirect(True)
        lbl = tk.Label(
            tw,
            text=text,
            justify="left",
            background=theme.SHELL_BG,
            foreground=theme.SHELL_TEXT,
            highlightthickness=1,
            highlightbackground=theme.ACCENT_ON_DARK,
            padx=10,
            pady=6,
            font=(self.ui_font, 8),
        )
        lbl.pack()
        tw.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        tw_w = tw.winfo_reqwidth()
        tw_h = tw.winfo_reqheight()
        px = x_root if x_root + tw_w + 12 <= sw else max(8, x_root - tw_w - 24)
        py = y_root if y_root + tw_h + 12 <= sh else max(8, y_root - tw_h - 24)
        tw.wm_geometry(f"+{px}+{py}")
        self._tooltip_window = tw

    def _hide_tooltip(self) -> None:
        self._last_hover_key = None
        if self._tooltip_window is not None:
            try:
                self._tooltip_window.destroy()
            except tk.TclError:
                pass
            self._tooltip_window = None

    def _draw_drafting_grid(self) -> None:
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        minor = 36
        major = 144
        for gx in range(0, w, minor):
            col = theme.CANVAS_GRID_MAJOR if gx % major == 0 else theme.CANVAS_GRID_MINOR
            self.create_line(gx, 0, gx, h, fill=col, width=1)
        for gy in range(0, h, minor):
            col = theme.CANVAS_GRID_MAJOR if gy % major == 0 else theme.CANVAS_GRID_MINOR
            self.create_line(0, gy, w, gy, fill=col, width=1)

    def _draw_obstruction_bars(
        self,
        pipe_id: str,
        mx: float,
        my: float,
        ux: float,
        uy: float,
        width: float,
        is_closed: bool,
    ) -> None:
        """Dibuja barras transversales de cierre en grafito (#4A4A4A) sobre el tramo intervenido."""
        nx_p, ny_p = -uy, ux
        half_bar = max(6.5, width * 1.45)
        offsets = (-4.5, 0.0, 4.5) if is_closed else (-3.0, 3.0)
        for off in offsets:
            cx = mx + ux * off
            cy = my + uy * off
            bar_id = self.create_line(
                cx - nx_p * half_bar,
                cy - ny_p * half_bar,
                cx + nx_p * half_bar,
                cy + ny_p * half_bar,
                fill=theme.INK_PRIMARY,
                width=2.3 if is_closed else 2.0,
            )
            self._item_to_pipe[bar_id] = pipe_id

    def redraw(self) -> None:
        self.delete("all")
        self._item_to_pipe.clear()
        self._item_to_node.clear()
        self._pulse_items.clear()
        self._pipe_draw_refs.clear()
        self._pipe_label_refs.clear()
        self._node_ring_refs.clear()
        self._pulse_geom_refs.clear()
        self._fast_cache_valid = False
        self._draw_drafting_grid()

        if self.graph is None:
            w = max(200, self.winfo_width())
            h = max(200, self.winfo_height())
            self.create_text(
                w / 2.0,
                h / 2.0,
                text="Cargue un archivo Excel o carpeta CSV para visualizar la red.",
                fill=theme.INK_MUTED,
                font=(self.ui_font, 10),
            )
            return

        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        min_dim = min(w, h)
        scale_factor = max(0.72, min(1.22, min_dim / 560.0))
        self._scale_factor_cache = scale_factor

        positions: Dict[str, Tuple[float, float]] = {
            node.node_id: self._world_to_screen(node.x, node.y)
            for node in self.graph.nodes()
        }

        min_edge_dist = 999.0
        for pipe in self.graph.pipes():
            p1 = positions.get(pipe.from_node)
            p2 = positions.get(pipe.to_node)
            if p1 is not None and p2 is not None:
                d = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
                if d > 1e-3:
                    min_edge_dist = min(min_edge_dist, d)

        dpi_r_boost = min(1.30, self.dpi_scale)
        base_radius = 10.4 * scale_factor * math.sqrt(self._zoom) * dpi_r_boost
        max_safe_r = max(5.2, min_edge_dist * 0.24) if min_edge_dist < 900.0 else 16.5
        node_radius = max(5.2, min(16.5, base_radius, max_safe_r))
        dense_mode = (w < 500 or self._zoom < 0.78)

        anim = self._traversal_frame
        has_traversal_focus = (
            anim is not None
            or bool(self.highlight_pipe_ids)
            or bool(self.highlight_node_ids)
        )
        label_queue = []

        # Identificar nodos frontera del corte topológico (aguas arriba de tramos cerrados 100%)
        cut_boundary_nodes: Set[str] = set()
        for pid, inv in self._interventions.items():
            if inv.is_closed:
                edge = self.graph.get_pipe(pid)
                if edge and edge.from_node in self._isolated_nodes:
                    cut_boundary_nodes.add(edge.from_node)

        # 1. Tuberías dirigidas
        for pipe in self.graph.pipes():
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

            sx1 = x1 + ux * (node_radius + 1.5)
            sy1 = y1 + uy * (node_radius + 1.5)
            sx2 = x2 - ux * (node_radius + 3.0)
            sy2 = y2 - uy * (node_radius + 3.0)

            inv = self._interventions.get(pipe.pipe_id)
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
                (self._basin_active and (pipe.pipe_id not in self._basin_pipes))
                or (self._tour_active and (pipe.pipe_id not in self._tour_pipes))
            )
            is_isolated = pipe.pipe_id in self._isolated_pipes
            is_anim_backtrack = anim is not None and (pipe.pipe_id in anim.backtracked_edges)
            is_anim_active = anim is not None and (pipe.pipe_id in anim.active_edges)
            is_anim_visited = (
                anim is not None
                and (pipe.pipe_id in anim.visited_edges)
                and not is_anim_active
            )

            ps = self.snapshot.pipe_states.get(pipe.pipe_id) if self.snapshot else None
            vel_ms = pipe.reference_velocity_ms
            if ps is not None and ps.effective_velocity_ms is not None:
                vel_ms = ps.effective_velocity_ms
            color, _tier, is_overloaded, is_critical, disp_val, suf_lbl = self._resolve_pipe_visual_state(
                pipe.pipe_id, ps, is_closed
            )
            util_pct = disp_val

            base_width = 2.0 + (eff_diam_in - 8.0) * 0.24
            geom_width = base_width * min(1.45, max(0.78, math.sqrt(self._zoom) * scale_factor))
            width = geom_width + (1.5 if (is_overloaded and not is_closed and anim is None) else 0.0)
            is_selected = pipe.pipe_id == self.selected_pipe_id
            is_highlighted = pipe.pipe_id in self.highlight_pipe_ids
            is_focus_pipe = is_anim_active if anim is not None else is_highlighted
            is_dimmed_context = has_traversal_focus and not (
                is_focus_pipe or is_anim_visited or is_selected
            )

            if is_dimmed_basin or is_isolated or is_anim_backtrack:
                line_kw = {
                    "fill": theme.DOCK_BG,
                    "width": max(1.4, geom_width * 0.72),
                    "arrow": tk.LAST,
                    "arrowshape": (6, 8, 2.8),
                    "capstyle": tk.ROUND,
                }
                if is_isolated or is_anim_backtrack:
                    line_kw["dash"] = (5, 4)
                line_id = self.create_line(sx1, sy1, sx2, sy2, **line_kw)
                self._item_to_pipe[line_id] = pipe.pipe_id
                if is_selected or (is_focus_pipe and not is_dimmed_basin):
                    halo_col = theme.PIPE_SELECTED_HALO if is_selected else theme.ACCENT_PRIMARY
                    halo_id = self.create_line(
                        sx1, sy1, sx2, sy2, fill=halo_col, width=geom_width + 5.0, capstyle=tk.ROUND
                    )
                    self.tag_lower(halo_id, line_id)
                    self._item_to_pipe[halo_id] = pipe.pipe_id
                continue

            glow_id: Optional[int] = None
            if anim is None and not is_closed:
                glow_id = self.create_line(
                    sx1, sy1, sx2, sy2,
                    fill=theme.PIPE_OVERLOAD_HALO,
                    width=width + 4.0,
                    capstyle=tk.ROUND,
                    state=tk.NORMAL if (is_overloaded and not is_dimmed_context) else tk.HIDDEN,
                )
                self._item_to_pipe[glow_id] = pipe.pipe_id

            seg_len = math.hypot(sx2 - sx1, sy2 - sy1)
            draw_width = width
            draw_arrow = (8, 10, 3.8)
            if is_dimmed_context:
                draw_width = max(1.3, geom_width * 0.72)
                draw_arrow = (6, 8, 2.8)
            elif is_anim_visited and not is_focus_pipe and not is_selected:
                draw_width = max(1.8, geom_width * 0.92)
                draw_arrow = (7, 9, 3.2)
            elif is_focus_pipe or is_selected:
                draw_width = max(2.6, width + (0.6 if is_focus_pipe else 0.0))
                draw_arrow = (9, 11, 4.2) if is_focus_pipe else (8, 10, 3.8)

            if (is_selected or is_focus_pipe or is_anim_visited) and seg_len > 6.0:
                trim_tip = min(seg_len * 0.45, 7.5)
                hx2 = sx2 - ux * trim_tip
                hy2 = sy2 - uy * trim_tip
                if is_selected or is_focus_pipe:
                    halo_color = theme.PIPE_SELECTED_HALO if is_selected else theme.ACCENT_PRIMARY
                    halo_width = draw_width + (8.0 if (is_selected and not is_focus_pipe) else 8.8)
                    halo_id = self.create_line(
                        sx1, sy1, hx2, hy2,
                        fill=halo_color,
                        width=halo_width,
                        capstyle=tk.BUTT,
                    )
                    self._item_to_pipe[halo_id] = pipe.pipe_id
                    cushion_id = self.create_line(
                        sx1, sy1, hx2, hy2,
                        fill=theme.CANVAS_BG,
                        width=draw_width + 3.4,
                        capstyle=tk.BUTT,
                    )
                    self._item_to_pipe[cushion_id] = pipe.pipe_id
                else:
                    halo_id = self.create_line(
                        sx1, sy1, hx2, hy2,
                        fill="#B8C2CC",
                        width=draw_width + 3.8,
                        capstyle=tk.BUTT,
                    )
                    self._item_to_pipe[halo_id] = pipe.pipe_id

            # Doble línea paralela en azul pizarra (#6D8196) al ampliar diámetro
            if is_enlarged and dist > 16.0:
                nx_p, ny_p = -uy, ux
                offset = draw_width / 2.0 + (4.6 if (is_selected or is_focus_pipe) else 2.8)
                for sign in (-1.0, 1.0):
                    par_id = self.create_line(
                        sx1 + nx_p * offset * sign,
                        sy1 + ny_p * offset * sign,
                        sx2 + nx_p * offset * sign,
                        sy2 + ny_p * offset * sign,
                        fill=theme.ACCENT_PRIMARY,
                        width=1.4,
                    )
                    self._item_to_pipe[par_id] = pipe.pipe_id

            base_line_fill = theme.INK_PRIMARY if is_closed else color
            if is_dimmed_context:
                line_fill = _blend_hex(base_line_fill, theme.CANVAS_BG, 0.68)
            elif is_anim_visited and not is_focus_pipe and not is_selected:
                line_fill = _blend_hex(base_line_fill, theme.CANVAS_BG, 0.30)
            else:
                line_fill = base_line_fill
            line_dash = (3, 3) if is_closed else ()
            line_kw = {
                "fill": line_fill,
                "width": draw_width,
                "arrow": tk.LAST,
                "arrowshape": draw_arrow,
                "capstyle": tk.ROUND,
            }
            if line_dash:
                line_kw["dash"] = line_dash
            line_id = self.create_line(sx1, sy1, sx2, sy2, **line_kw)
            self._item_to_pipe[line_id] = pipe.pipe_id
            self._pipe_draw_refs[pipe.pipe_id] = (line_id, glow_id, geom_width, is_closed)

            # Marcadores de cierre / obstrucción sobre el tramo
            mx, my = (sx1 + sx2) / 2.0, (sy1 + sy2) / 2.0
            if is_obstructed and dist > 14.0:
                self._draw_obstruction_bars(pipe.pipe_id, mx, my, ux, uy, geom_width, is_closed)

            if anim is None and not is_closed and seg_len >= 20.0:
                self._pulse_geom_refs[pipe.pipe_id] = (sx1, sy1, ux, uy, seg_len, geom_width, vel_ms)

            # Cola de etiquetas de tuberías + marcas técnicas [OBST XX%] / [ØXX"] / [XXm >100%]
            has_mark = is_obstructed or is_enlarged
            has_ov_badge = (
                self._map_mode == "overload_minutes"
                and not is_closed
                and disp_val >= 0.5
                and anim is None
                and not is_dimmed_context
            )
            if (self.show_pipe_labels or self.show_util_labels or has_mark or has_ov_badge) and dist > 26:
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
                    if self.show_pipe_labels:
                        prefix_parts.append(pipe.pipe_id)
                    if has_ov_badge:
                        ov_txt = f"{disp_val:.0f}m >100%"
                        if prefix_parts:
                            if self.show_pipe_labels and prefix_parts[-1] == pipe.pipe_id:
                                lbl_full = " ".join(prefix_parts[:-1] + [f"{pipe.pipe_id} · {ov_txt}"])
                            else:
                                lbl_full = " ".join(prefix_parts + [ov_txt])
                        else:
                            lbl_full = f"{pipe.pipe_id} · {ov_txt}" if self.show_pipe_labels else ov_txt
                    else:
                        parts = list(prefix_parts)
                        if self.show_util_labels and self.snapshot is not None and not is_closed and suf_lbl:
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
                            (priority, util_pct, pipe.pipe_id, lx, ly, mx, is_vert, side, lbl_full, prefix_parts, is_selected, is_overloaded, is_focus_pipe, has_mark, has_ov_badge, is_closed, nx_perp, ny_perp)
                        )

        r_box = max(4.0, node_radius * 0.78)
        placed_boxes = [
            (nx - r_box, ny - r_box, nx + r_box, ny + r_box)
            for nx, ny in positions.values()
        ]
        for node in self.graph.nodes():
            nx, ny = positions[node.node_id]
            if node.node_type == "sink":
                px = max(68.0, nx)
                py = ny - node_radius - 15
                placed_boxes.append((px - 70, py - 10, px + 70, py + 10))
            elif node.node_type == "source" and not dense_mode:
                ty = (ny - node_radius - 12) if node.y < 0.2 else (ny + node_radius + 12)
                placed_boxes.append((nx - 26, ty - 8, nx + 26, ty + 8))

        label_queue.sort(
            key=lambda item: (item[0], item[1], self._peak_util_map.get(item[2], 0.0)),
            reverse=True,
        )

        font_sz = 7 if (self._zoom < 1.15 or dense_mode) else 8
        for priority, _u, pid, lx, ly, mx, is_vert, side, text_lbl, prefix_parts, is_sel, is_over, is_hl, has_mark, has_ov_badge, is_closed, nx_perp, ny_perp in label_queue:
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
            font_spec = (
                self.mono_font,
                font_sz,
                "bold" if is_bold else "normal",
            )
            txt_id = self.create_text(lx, ly, text=text_lbl, fill=fg, font=font_spec)
            bbox = self.bbox(txt_id)
            if bbox is None:
                self.delete(txt_id)
                continue
            if is_vert:
                half_w = (bbox[2] - bbox[0]) / 2.0
                target_lx = mx + side * (half_w + 9.0)
                target_lx = max(half_w + 6.0, min(w - half_w - 6.0, target_lx))
                dx_shift = target_lx - lx
                if abs(dx_shift) > 0.5:
                    self.move(txt_id, dx_shift, 0.0)
                    bbox = self.bbox(txt_id)
                    if bbox is None:
                        self.delete(txt_id)
                        continue
            bx0, by0, bx1, by1 = bbox[0] - 3, bbox[1] - 1, bbox[2] + 3, bbox[3] + 1
            overlaps = any(
                not (bx1 < ox0 or bx0 > ox1 or by1 < oy0 or by0 > oy1)
                for ox0, oy0, ox1, oy1 in placed_boxes
            )
            if overlaps and not is_vert:
                for nudge in (3.5, 6.0):
                    ndx, ndy = nx_perp * nudge, ny_perp * nudge
                    nbx0, nby0, nbx1, nby1 = bx0 + ndx, by0 + ndy, bx1 + ndx, by1 + ndy
                    if not any(
                        not (nbx1 < ox0 or nbx0 > ox1 or nby1 < oy0 or nby0 > oy1)
                        for ox0, oy0, ox1, oy1 in placed_boxes
                    ):
                        self.move(txt_id, ndx, ndy)
                        bx0, by0, bx1, by1 = nbx0, nby0, nbx1, nby1
                        overlaps = False
                        break
            if overlaps and not is_sel and not has_mark:
                self.delete(txt_id)
                continue

            placed_boxes.append((bx0, by0, bx1, by1))
            rect_id = self.create_rectangle(
                bx0, by0, bx1, by1,
                fill=bg,
                outline=border,
                width=1,
            )
            self.tag_lower(rect_id, txt_id)
            self._item_to_pipe[rect_id] = pid
            self._item_to_pipe[txt_id] = pid
            self._pipe_label_refs[pid] = (rect_id, txt_id, prefix_parts, is_sel, is_hl, has_mark, is_closed, len(text_lbl), font_sz, is_bold)

        # 2. Vértices (alcantarillas fuente, pozos de inspección, sumidero PTAR)
        for node in self.graph.nodes():
            x, y = positions[node.node_id]
            r = node_radius
            is_dimmed_basin = (
                (self._basin_active and (node.node_id not in self._basin_nodes))
                or (self._tour_active and (node.node_id not in self._tour_nodes))
            )
            is_isolated = node.node_id in self._isolated_nodes
            is_hl_node = node.node_id in self.highlight_node_ids
            is_anim_wave = anim is not None and (node.node_id in anim.active_nodes)
            is_anim_cursor = anim is not None and (node.node_id == anim.cursor_node)
            is_anim_visited = anim is not None and (node.node_id in anim.visited_nodes)
            is_anim_backtrack = anim is not None and (node.node_id in anim.backtracked_nodes)

            if node.node_type == "sink":
                r += 3.5
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
                elif node.node_id != self.selected_node_id:
                    fill = theme.PAPER_SUBTLE
                    outline = theme.DOCK_BG
                    txt_fill = theme.INK_MUTED
            elif has_traversal_focus:
                if is_hl_node:
                    if node.node_type == "manhole":
                        fill = theme.ACCENT_PRIMARY
                        outline = theme.INK_PRIMARY
                        txt_fill = theme.ACCENT_INK
                elif node.node_id != self.selected_node_id:
                    fill = theme.PAPER_SUBTLE
                    outline = theme.DOCK_BG
                    txt_fill = theme.INK_MUTED

            if not is_dimmed_basin and anim is None and (not has_traversal_focus or is_hl_node or node.node_id == self.selected_node_id):
                self._node_ring_refs.append((node.node_id, x, y, r))

            surcharge_vol = 0.0
            if self.snapshot and node.node_id in self.snapshot.node_states:
                ns = self.snapshot.node_states[node.node_id]
                surcharge_vol = ns.stored_volume_m3 + ns.surface_flooding_m3

            if not is_dimmed_basin and anim is None and (not has_traversal_focus or is_hl_node or node.node_id == self.selected_node_id):
                self._draw_flood_rings(
                    node.node_id, x, y, r, surcharge_vol, scale_factor, math.sqrt(self._zoom)
                )

            if is_anim_wave or is_anim_cursor:
                radar_r = r + (5.5 if is_anim_cursor else 4.2)
                radar_ring = self.create_oval(
                    x - radar_r, y - radar_r, x + radar_r, y + radar_r,
                    outline=theme.ACCENT_PRIMARY,
                    width=2.8 if is_anim_cursor else 2.2,
                    tags=("node_layer",),
                )
                self._item_to_node[radar_ring] = node.node_id
            elif (
                node.node_id == self.selected_node_id
                or (anim is None and node.node_id in self.highlight_node_ids)
            ) and not is_dimmed_basin:
                sel_col = (
                    theme.ACCENT_PRIMARY
                    if node.node_id == self.selected_node_id
                    else theme.PIPE_HIGHLIGHT_PATH
                )
                ring2 = self.create_oval(
                    x - r - 3.5, y - r - 3.5, x + r + 3.5, y + r + 3.5,
                    outline=sel_col,
                    width=2.6,
                    tags=("node_layer",),
                )
                self._item_to_node[ring2] = node.node_id

            oval_kw = {
                "fill": fill,
                "outline": outline,
                "width": 2.0,
                "tags": ("node_layer",),
            }
            if is_isolated and not is_dimmed_basin:
                oval_kw["dash"] = (3, 2)
            oval_id = self.create_oval(x - r, y - r, x + r, y + r, **oval_kw)
            self._item_to_node[oval_id] = node.node_id

            txt_id = self.create_text(
                x,
                y,
                text=node.node_id,
                fill=txt_fill,
                font=(self.ui_font, 7 if dense_mode else (8 if self._zoom < 1.2 else 9), "bold"),
                tags=("node_layer",),
            )
            self._item_to_node[txt_id] = node.node_id

            if is_isolated and not is_dimmed_basin and (
                node.node_id in cut_boundary_nodes or node.node_id == self.selected_node_id
            ):
                iso_y = y - r - 13
                iso_txt = self.create_text(
                    x,
                    iso_y,
                    text="[AISLADO DE 31]",
                    fill=theme.INK_PRIMARY,
                    font=(self.mono_font, 7, "bold"),
                )
                ib = self.bbox(iso_txt)
                if ib is not None:
                    ibg = self.create_rectangle(
                        ib[0] - 4, ib[1] - 1, ib[2] + 4, ib[3] + 1,
                        fill=theme.DOCK_BG,
                        outline=theme.INK_PRIMARY,
                        width=1,
                    )
                    self.tag_lower(ibg, iso_txt)
                    self._item_to_node[ibg] = node.node_id
                self._item_to_node[iso_txt] = node.node_id

            if node.node_type == "sink":
                ptar_x = max(68.0, x)
                ptar_y = y - r - 15
                ptar_id = self.create_text(
                    ptar_x,
                    ptar_y,
                    text="PTAR Punta Canoa · 31",
                    fill=theme.SHELL_TEXT,
                    font=(self.ui_font, 8, "bold"),
                )
                pb = self.bbox(ptar_id)
                if pb is not None:
                    pbg = self.create_rectangle(
                        pb[0] - 5, pb[1] - 2, pb[2] + 5, pb[3] + 2,
                        fill=theme.SHELL_BG,
                        outline=theme.ACCENT_PRIMARY,
                        width=1.5,
                    )
                    self.tag_lower(pbg, ptar_id)
                    self._item_to_node[pbg] = node.node_id
                self._item_to_node[ptar_id] = node.node_id
            elif node.node_type == "source" and not dense_mode and not is_dimmed_basin:
                tag_y = (y - r - 12) if node.y < 0.2 else (y + r + 12)
                src_tag = self.create_text(
                    x,
                    tag_y,
                    text="Fuente",
                    fill=theme.INK_MUTED if is_isolated else theme.INK_PRIMARY,
                    font=(self.ui_font, 7, "bold"),
                )
                sb = self.bbox(src_tag)
                if sb is not None:
                    sbg = self.create_rectangle(
                        sb[0] - 4, sb[1] - 1, sb[2] + 4, sb[3] + 1,
                        fill=theme.DOCK_BG,
                        outline=theme.DOCK_DIVIDER if is_isolated else theme.INK_PRIMARY,
                        width=1,
                    )
                    self.tag_lower(sbg, src_tag)
                    self._item_to_node[sbg] = node.node_id
                self._item_to_node[src_tag] = node.node_id

        self._fast_cache_valid = (not dense_mode) and (anim is None)
        if self._is_playing:
            self._rebuild_pulses_from_cache()
