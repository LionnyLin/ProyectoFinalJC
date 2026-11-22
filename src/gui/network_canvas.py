"""Lienzo cartográfico interactivo en 2 fases para la red de alcantarillado.

Fase A (`rebuild_geometry`): crea y posiciona todos los ítems (incluidos los auxiliares ocultos: halos,
anillos de rebose, pulsos, barras de obstrucción, marcas) solo al cargar el grafo, hacer zoom/paneo/resize
o cambiar la forma (intervenciones). Fase B (`update_visuals`): únicamente `itemconfigure`/`coords` sobre
los ítems cacheados, sin borrar el canvas.
"""

from __future__ import annotations

import math
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import font as tkfont
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from src.algorithms.analysis import classify_overload_persistence, classify_utilization
from src.data_structures import DirectedGraph
from src.simulation.models import PipeIntervention, TimeStepSnapshot, resolve_pipe_hydraulics
from . import theme

_DEFAULT_FONTS: Dict[str, Tuple[str, int, str]] = {
    "headline": ("TkDefaultFont", 13, "bold"), "title": ("TkDefaultFont", 10, "bold"),
    "body": ("TkDefaultFont", 9, "normal"), "label": ("TkDefaultFont", 9, "bold"),
    "mono": ("TkFixedFont", 9, "normal"), "mono_bold": ("TkFixedFont", 9, "bold"), "small": ("TkDefaultFont", 8, "normal"),
}
_NODE_TYPE_ES = {"source": "Alcantarilla Fuente", "sink": "Sumidero / PTAR Punta Canoa", "manhole": "Pozo de inspección"}
_NODE_BASE_STYLE = {
    "source": (theme.NODE_SOURCE_FILL, theme.NODE_SOURCE_OUTLINE, theme.NODE_SOURCE_TEXT, 2.0),
    "sink": (theme.NODE_SINK_FILL, theme.NODE_SINK_OUTLINE, theme.NODE_SINK_TEXT, 2.2),
    "manhole": (theme.NODE_MANHOLE_FILL, theme.NODE_MANHOLE_OUTLINE, theme.NODE_MANHOLE_TEXT, 1.5),
}
_ZOOM_MIN, _ZOOM_MAX, _DRAG_PX, _RESIZE_MS = 0.55, 4.50, 4.0, 80
_PULSE_TICK_MS, _BASE_PX_PER_MPS = 55, 28.0
_Box = Tuple[float, float, float, float]

# Colores y constantes propios del lienzo (theme.py pertenece a otro paquete)
_FLOW_EPS = 1e-5
_OVERLOAD_HALO = "#FECACA"
_FLOOD_STORAGE, _FLOOD_SURFACE, _FLOOD_DEEP = "#F97316", "#EF4444", "#991B1B"
_OV_BADGE_BORDER, _OV_LABEL_BG, _OV_LABEL_BORDER, _OV_LABEL_FG = "#EF4444", "#FEF2F2", "#FCA5A5", "#991B1B"
_BARRIER_COLOR = theme.INK_PRIMARY
_DOUBLE_LINE_COLOR = theme.ACCENT_PRIMARY
_FOCUS_DIM_PIPE, _FOCUS_DIM_NODE_OUT, _FOCUS_DIM_NODE_TXT = theme.DOCK_BG, theme.DOCK_BG, theme.DOCK_DIVIDER
_SEL_RING_COLOR = theme.ACCENT_PRIMARY


def _edge_id(item: object) -> str:
    return item.pipe_id if hasattr(item, "pipe_id") else str(item)


def _fmt_pct(u: float) -> str:
    return f"{u / 1000.0:.1f}k%" if u >= 1000.0 else f"{u:.0f}%"


def _boxes_overlap(a: _Box, b: _Box) -> bool:
    return not (a[2] < b[0] or a[0] > b[2] or a[3] < b[1] or a[1] > b[3])


def _box_hits_segment(box: _Box, x1: float, y1: float, x2: float, y2: float) -> bool:
    """Liang-Barsky: ¿el segmento atraviesa el rectángulo?"""
    bx0, by0, bx1, by1 = box
    if max(x1, x2) < bx0 or min(x1, x2) > bx1 or max(y1, y2) < by0 or min(y1, y2) > by1:
        return False
    dx, dy, t0, t1 = x2 - x1, y2 - y1, 0.0, 1.0
    for p, q in ((-dx, x1 - bx0), (dx, bx1 - x1), (-dy, y1 - by0), (dy, by1 - y1)):
        if abs(p) < 1e-9:
            if q < 0.0: return False
            continue
        r = q / p
        if p < 0.0:
            if r > t1: return False
            t0 = max(t0, r)
        else:
            if r < t0: return False
            t1 = min(t1, r)
    return t0 <= t1


@dataclass(slots=True)
class _PulseMeta:
    """Marcador direccional ▸ que recorre una tubería a velocidad proporcional a la de Manning."""

    item_id: int
    pipe_id: str
    sx1: float
    sy1: float
    ux: float
    uy: float
    usable_len: float
    phase_offset: float
    chevron_size: float
    velocity_ms: float = 0.0


@dataclass(slots=True)
class _PipeGeom:
    """Ítems y geometría de una tubería (Fase A) más cachés de estilo (Fase B)."""

    pid: str
    sx1: float
    sy1: float
    sx2: float
    sy2: float
    dist: float
    ux: float
    uy: float
    seg_len: float
    width: float
    inv: Optional[PipeIntervention]
    closed: bool
    obstructed: bool
    enlarged: bool
    eff_diam: float
    vel_ref: float
    line: int = 0
    halo: int = 0
    extras: List[int] = field(default_factory=list)
    pulses: List[_PulseMeta] = field(default_factory=list)
    lbl_rect: Optional[int] = None
    lbl_txt: Optional[int] = None
    slot: Optional[Tuple[float, float, str]] = None
    lbl_ok: bool = False
    has_mark: bool = False
    c_line: object = None
    c_halo: object = None
    c_extras: object = None
    c_lbl: object = None
    c_pulse: object = None


@dataclass(slots=True)
class _NodeGeom:
    """Ítems de un nodo (Fase A) y cachés de estilo (Fase B)."""

    nid: str
    node_type: str
    x: float
    y: float
    r: float
    oval: int = 0
    text: int = 0
    rings: Tuple[int, int] = (0, 0)
    badge: Optional[Tuple[int, int]] = None
    iso_tag: Optional[Tuple[int, int]] = None
    iso_cut: bool = False
    c_node: object = None
    c_ring: object = None
    c_badge: object = None
    c_iso: object = None


class NetworkCanvas(tk.Canvas):
    """Canvas cartográfico en 2 fases: geometría cacheada (A) y actualización sin borrado (B)."""

    def __init__(
        self,
        parent: tk.Misc,
        fonts: Optional[Dict[str, Tuple[str, int, str]]] = None,
        on_select: Optional[Callable[[Optional[str], Optional[str]], None]] = None,
        **kwargs,
    ) -> None:
        for k, v in (("bg", theme.CANVAS_BG), ("highlightthickness", 1), ("highlightbackground", theme.PAPER_RULE), ("bd", 0)):
            kwargs.setdefault(k, v)
        super().__init__(parent, **kwargs)

        self._fonts: Dict[str, Tuple[str, int, str]] = {**_DEFAULT_FONTS, **(fonts or {})}
        self._on_select = on_select
        self._graph: Optional[DirectedGraph] = None
        self._snapshot: Optional[TimeStepSnapshot] = None
        self._selected_kind, self._selected_id, self._show_pipe_labels, self._show_util_labels = None, None, True, True
        self._visited_nodes, self._visited_edges, self._path_nodes, self._path_edges = set(), set(), set(), set()
        self._active_nodes, self._active_edges, self._backtracked_nodes, self._backtracked_edges = set(), set(), set(), set()
        self._current_node, self._active_edge = None, None
        self._traversal_mode: Optional[str] = None
        self._origin_node: Optional[str] = None
        self._banner_text: str = ""
        self._zoom, self._pan_x, self._pan_y = 1.0, 0.0, 0.0
        self._drag_start, self._drag_pan_origin = None, (0.0, 0.0)
        self._dragged, self._resize_after, self._last_size = False, None, (0, 0)

        # Mapas de estrés, intervenciones y foco
        self.map_mode: str = "instant"
        self._peak_util: Dict[str, float] = {}
        self._overload_min: Dict[str, float] = {}
        self._total_duration_min = 90.0
        self._interventions: Dict[str, PipeIntervention] = {}
        self._isolated_nodes: Set[str] = set()
        self._isolated_pipes: Set[str] = set()
        self._basin_active, self._basin_nodes, self._basin_pipes = False, set(), set()
        self._tour_active, self._tour_nodes, self._tour_pipes = False, set(), set()

        # Pulsos de flujo y animación de cámara
        self._playing, self._speed_factor, self._pulse_time_s = False, 1.0, 0.0
        self._pulse_after_id: Optional[str] = None
        self._active_pulses: List[_PulseMeta] = []
        self._cam_after: Optional[str] = None

        # Registro de ítems del Canvas (Fase A)
        self._geoms: Dict[str, _PipeGeom] = {}
        self._ngeoms: Dict[str, _NodeGeom] = {}
        self._node_coords: Dict[str, Tuple[float, float]] = {}
        self._node_radii: Dict[str, float] = {}
        self._origin_ring: Optional[int] = None
        self._sel_ring: Optional[int] = None
        self._empty_text: Optional[int] = None
        self._item_to_entity: Dict[int, Tuple[str, str]] = {}
        self._font_cache: Dict[Tuple[str, int, str], tkfont.Font] = {}
        self._char_w: Dict[Tuple[str, int, str], Dict[str, float]] = {}
        self._line_h: Dict[Tuple[str, int, str], float] = {}
        self._sf, self._node_r, self._dense = 1.0, 9.0, False
        self._lbl_font_px = 9
        self._stamp_cache: Optional[str] = None
        self._sel_cache: object = None
        self._origin_cache: object = None

        self._tooltip_lbl = tk.Label(
            self, text="", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, font=self._fonts["small"],
            justify="left", anchor="w", padx=8, pady=5, bd=0, highlightthickness=1, highlightbackground=theme.ACCENT_PRIMARY,
        )
        self._hover_entity: Optional[Tuple[str, str]] = None
        self._banner_lbl = tk.Label(self, text="", font=self._fonts["label"], padx=10, pady=4, bd=0, highlightthickness=2)
        self._build_overlays()

        for seq, cb in (
            ("<Configure>", self._on_configure), ("<MouseWheel>", self._on_mouse_wheel),
            ("<Button-4>", lambda e: self._wheel_zoom(e, 1.12)), ("<Button-5>", lambda e: self._wheel_zoom(e, 1.0 / 1.12)),
            ("<ButtonPress-1>", self._on_left_press), ("<B1-Motion>", self._on_left_drag),
            ("<ButtonRelease-1>", self._on_left_release), ("<Double-Button-1>", lambda _e: self.reset_view()),
            ("<Motion>", self._on_motion), ("<Leave>", lambda _e: self._hide_tooltip()), ("<Destroy>", self._on_destroy),
        ):
            self.bind(seq, cb)

    # ── Overlays (widgets sobre el canvas) ───────────────────────────────────

    def _build_overlays(self) -> None:
        ui, mono = self._fonts["small"][0], self._fonts["mono"][0]
        self._stamp_lbl = tk.Label(
            self, text="PLANO HIDRÁULICO", bg=theme.DOCK_BG, fg=theme.INK_PRIMARY, highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER, padx=9, pady=4, font=(mono, -11, "bold"),
        )
        self._zoom_bar = tk.Frame(self, bg=theme.SHELL_BG, highlightthickness=1, highlightbackground=theme.SHELL_BORDER)

        def mini(txt: str, cmd: Callable[[], None]) -> tk.Button:
            b = tk.Button(self._zoom_bar, text=txt, command=cmd, bg=theme.SHELL_BG, fg=theme.SHELL_TEXT,
                          activebackground=theme.SHELL_HOVER, activeforeground=theme.SHELL_TEXT, relief="flat", bd=0,
                          padx=8, pady=3, font=(ui, -12, "bold"), cursor="hand2", takefocus=0)
            b.bind("<Enter>", lambda _e: b.configure(bg=theme.SHELL_HOVER))
            b.bind("<Leave>", lambda _e: b.configure(bg=theme.SHELL_BG))
            return b

        mini("+", self.zoom_in).pack(side=tk.LEFT)
        self._lbl_zoom = tk.Label(self._zoom_bar, text="100%", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, font=(mono, -11, "bold"), width=5)
        self._lbl_zoom.pack(side=tk.LEFT)
        mini("−", self.zoom_out).pack(side=tk.LEFT)
        mini("⟲", self.reset_view).pack(side=tk.LEFT)
        self._hint_bar = tk.Label(
            self, text="Arrastrar: mover  ·  Rueda: zoom  ·  Clic: inspeccionar  ·  Doble clic: ajustar",
            bg=theme.DOCK_BG, fg=theme.INK_PRIMARY, highlightthickness=1, highlightbackground=theme.DOCK_BORDER,
            padx=9, pady=4, font=(ui, -11),
        )
        self._zoom_bar.place(relx=1.0, rely=0.0, x=-12, y=12, anchor="ne")

    def _overlay_flags(self, w: float, h: float) -> Tuple[bool, bool]:
        return (w >= 520 and h >= 340), (w >= 480 and h >= 340 and not self._tour_active)

    def _layout_overlays(self, w: float, h: float) -> None:
        show_stamp, show_hint = self._overlay_flags(w, h)
        if show_stamp: self._stamp_lbl.place(x=12, y=12, anchor="nw")
        else: self._stamp_lbl.place_forget()
        if show_hint: self._hint_bar.place(relx=1.0, rely=1.0, x=-12, y=-12, anchor="se")
        else: self._hint_bar.place_forget()

    def _overlay_boxes(self, w: float, h: float) -> List[_Box]:
        """Cajas reservadas por los overlays (analíticas: no dependen de que estén mapeados)."""
        boxes: List[_Box] = []
        show_stamp, show_hint = self._overlay_flags(w, h)
        if show_stamp:
            rw, rh = self._stamp_lbl.winfo_reqwidth(), self._stamp_lbl.winfo_reqheight()
            boxes.append((8.0, 8.0, 16.0 + rw, 16.0 + rh))
        rw, rh = self._zoom_bar.winfo_reqwidth(), self._zoom_bar.winfo_reqheight()
        boxes.append((w - 16.0 - rw, 8.0, w - 8.0, 16.0 + rh))
        if show_hint:
            rw, rh = self._hint_bar.winfo_reqwidth(), self._hint_bar.winfo_reqheight()
            boxes.append((w - 16.0 - rw, h - 16.0 - rh, w - 8.0, h - 8.0))
        return boxes

    def _update_stamp(self) -> None:
        if self._graph is None:
            txt = "PLANO HIDRÁULICO"
        else:
            nn, npipes = self._graph.num_nodes, self._graph.num_pipes
            dur = f"0–{self._total_duration_min:.0f} min"
            if self._snapshot is None:
                txt = f"PLANO HIDRÁULICO · {nn} NODOS · {npipes} TRAMOS"
            elif self.map_mode == "peak":
                txt = f"PICO MÁXIMO ACUMULADO · {dur}"
            elif self.map_mode == "overload_minutes":
                txt = f"MINUTOS EN SOBRECARGA (>100%) · {dur}"
            else:
                txt = f"PLANO HIDRÁULICO · {nn} NODOS · {npipes} TRAMOS · t = {self._snapshot.time_min:.1f} min"
        if txt != self._stamp_cache:
            self._stamp_cache = txt
            self._stamp_lbl.configure(text=txt)

    def _update_zoom_label(self) -> None:
        self._lbl_zoom.configure(text=f"{int(round(self._zoom * 100))}%")

    # ── API pública: datos y estado ──────────────────────────────────────────

    @property
    def map_mode_name(self) -> str:
        return self.map_mode

    def set_graph(self, graph: DirectedGraph) -> None:
        self.stop_pulse_animation()
        self._stop_camera_animation()
        self._graph, self._selected_kind, self._selected_id, self._snapshot = graph, None, None, None
        self._interventions, self._isolated_nodes, self._isolated_pipes = {}, set(), set()
        self._basin_active = self._tour_active = False
        self._basin_nodes, self._basin_pipes, self._tour_nodes, self._tour_pipes = set(), set(), set(), set()
        self._peak_util, self._overload_min = {}, {}
        self._hide_tooltip()
        self._update_stamp()
        self.rebuild_geometry()

    def set_snapshot(self, snapshot: Optional[TimeStepSnapshot]) -> None:
        self._snapshot = snapshot
        self._update_stamp()
        self.update_visuals()
        if self._hover_entity is not None:
            self._tooltip_lbl.configure(text=self._format_tooltip(*self._hover_entity))

    def set_selected(self, kind: Optional[str], entity_id: Optional[str]) -> None:
        self._selected_kind, self._selected_id = (kind, entity_id) if kind in ("pipe", "node") and entity_id else (None, None)
        self.update_visuals()

    def select_pipe(self, pid: Optional[str]) -> None:
        self.set_selected("pipe", pid)

    def select_node(self, nid: Optional[str]) -> None:
        self.set_selected("node", nid)

    def set_traversal_highlight(
        self, visited_nodes: Optional[Iterable[str]] = None, visited_edges: Optional[Iterable[object]] = None,
        path_nodes: Optional[Iterable[str]] = None, path_edges: Optional[Iterable[object]] = None,
        current_node: Optional[str] = None, active_edge: Optional[object] = None,
        mode: Optional[str] = None, origin_node: Optional[str] = None, banner_text: str = "",
        active_nodes: Optional[Iterable[str]] = None, active_edges: Optional[Iterable[object]] = None,
        backtracked_nodes: Optional[Iterable[str]] = None, backtracked_edges: Optional[Iterable[object]] = None,
    ) -> None:
        self._visited_nodes = set(visited_nodes) if visited_nodes else set()
        self._visited_edges = {_edge_id(e) for e in visited_edges} if visited_edges else set()
        self._path_nodes = set(path_nodes) if path_nodes else set()
        self._path_edges = {_edge_id(e) for e in path_edges} if path_edges else set()
        self._active_nodes = set(active_nodes) if active_nodes else set()
        self._active_edges = {_edge_id(e) for e in active_edges} if active_edges else set()
        self._backtracked_nodes = set(backtracked_nodes) if backtracked_nodes else set()
        self._backtracked_edges = {_edge_id(e) for e in backtracked_edges} if backtracked_edges else set()
        self._current_node, self._active_edge = current_node, (_edge_id(active_edge) if active_edge is not None else None)
        self._traversal_mode = mode.lower() if mode else None
        self._origin_node = origin_node
        self._banner_text = banner_text or ""
        self.update_visuals()

    def clear_traversal_highlight(self) -> None:
        self.set_traversal_highlight()

    def set_label_options(self, show_pipe_labels: bool = True, show_util_labels: bool = True) -> None:
        self._show_pipe_labels, self._show_util_labels = bool(show_pipe_labels), bool(show_util_labels)
        self.update_visuals()

    def set_map_mode(
        self, mode: str, peak_util: Optional[Dict[str, float]] = None,
        overload_minutes: Optional[Dict[str, float]] = None, total_duration_min: float = 90.0,
    ) -> None:
        """Alterna entre Instantáneo, Pico Máximo y Minutos en Sobrecarga."""
        self.map_mode = mode if mode in ("instant", "peak", "overload_minutes") else "instant"
        if peak_util is not None: self._peak_util = dict(peak_util)
        if overload_minutes is not None: self._overload_min = dict(overload_minutes)
        self._total_duration_min = max(1.0, float(total_duration_min))
        self._update_stamp()
        self.update_visuals()

    def set_stress_maps(
        self, peak_util: Optional[Dict[str, float]] = None, overload_minutes: Optional[Dict[str, float]] = None,
        total_duration_min: float = 90.0,
    ) -> None:
        """Actualiza los mapas acumulados; solo repinta si el modo activo los usa."""
        if peak_util is not None: self._peak_util = dict(peak_util)
        if overload_minutes is not None: self._overload_min = dict(overload_minutes)
        self._total_duration_min = max(1.0, float(total_duration_min))
        if self.map_mode != "instant":
            self._update_stamp()
            self.update_visuals()

    def set_interventions(
        self, interventions: Optional[Dict[str, PipeIntervention]] = None,
        isolated_nodes: Optional[Iterable[str]] = None, isolated_pipes: Optional[Iterable[str]] = None,
    ) -> None:
        """Cambia la forma (doble línea, barras, ×, marcas): reconstruye la Fase A."""
        self._interventions = dict(interventions or {})
        self._isolated_nodes, self._isolated_pipes = set(isolated_nodes or ()), set(isolated_pipes or ())
        self.rebuild_geometry()

    def set_basin_focus(self, node_ids: Optional[Iterable[str]], pipe_ids: Optional[Iterable[str]]) -> None:
        if node_ids is None or pipe_ids is None:
            self._basin_active, self._basin_nodes, self._basin_pipes = False, set(), set()
        else:
            self._basin_active, self._basin_nodes, self._basin_pipes = True, set(node_ids), set(pipe_ids)
        self.update_visuals()

    def set_tour_focus(self, node_ids: Optional[Iterable[str]], pipe_ids: Optional[Iterable[str]]) -> None:
        if node_ids is None or pipe_ids is None:
            self._tour_active, self._tour_nodes, self._tour_pipes = False, set(), set()
        else:
            self._tour_active, self._tour_nodes, self._tour_pipes = True, set(node_ids), set(pipe_ids)
        w, h = self._canvas_dims()
        self._layout_overlays(w, h)
        self.update_visuals()

    # ── Pulsos de flujo ──────────────────────────────────────────────────────

    def set_playing(self, playing: bool, speed_factor: float = 1.0) -> None:
        self._speed_factor = max(0.5, min(3.5, float(speed_factor)))
        playing = bool(playing)
        if playing == self._playing:
            return
        if playing:
            self._playing = True
            self.update_visuals()
            self._schedule_pulse_tick()
        else:
            self.stop_pulse_animation()

    def stop_pulse_animation(self) -> None:
        """Detiene el temporizador y oculta los pulsos (reutiliza los ítems)."""
        was_playing, self._playing = self._playing, False
        if self._pulse_after_id is not None:
            try: self.after_cancel(self._pulse_after_id)
            except tk.TclError: pass
            self._pulse_after_id = None
        if was_playing and self._graph is not None and self._geoms:
            try: self.update_visuals()
            except tk.TclError: pass

    def _schedule_pulse_tick(self) -> None:
        if self._playing and self._pulse_after_id is None:
            self._pulse_after_id = self.after(_PULSE_TICK_MS, self._tick_flow_pulses)

    def _tick_flow_pulses(self) -> None:
        self._pulse_after_id = None
        if not self._playing:
            return
        self._pulse_time_s += (_PULSE_TICK_MS / 1000.0) * self._speed_factor
        try:
            if self.winfo_viewable():
                for m in self._active_pulses:
                    self.coords(m.item_id, *self._chevron_coords(m))
            self._schedule_pulse_tick()
        except tk.TclError:
            self._pulse_after_id = None

    def _chevron_coords(self, m: _PulseMeta) -> Tuple[float, ...]:
        travel = (self._pulse_time_s * m.velocity_ms * _BASE_PX_PER_MPS * math.sqrt(self._zoom)
                  + m.phase_offset * m.usable_len) % m.usable_len
        d = 5.0 + travel
        tx, ty = m.sx1 + m.ux * d, m.sy1 + m.uy * d
        nx, ny, sz = -m.uy, m.ux, m.chevron_size
        bx, by = tx - m.ux * sz, ty - m.uy * sz
        return (bx + nx * sz * 0.72, by + ny * sz * 0.72, tx, ty, bx - nx * sz * 0.72, by - ny * sz * 0.72)

    # ── Cámara ───────────────────────────────────────────────────────────────

    def reset_view(self) -> None:
        self._stop_camera_animation()
        self._zoom, self._pan_x, self._pan_y = 1.0, 0.0, 0.0
        self._hide_tooltip()
        self.rebuild_geometry()

    def zoom_by(self, factor: float) -> None:
        w, h = self._canvas_dims()
        self._zoom_at(w * 0.5, h * 0.5, factor)

    def zoom_in(self) -> None:
        self.zoom_by(1.18)

    def zoom_out(self) -> None:
        self.zoom_by(1.0 / 1.18)

    def cancel_pending(self) -> None:
        """Cancela redibujado diferido, pulsos y animación de cámara."""
        if self._resize_after is not None:
            try: self.after_cancel(self._resize_after)
            except tk.TclError: pass
            self._resize_after = None
        self._stop_camera_animation()
        self._playing = False
        if self._pulse_after_id is not None:
            try: self.after_cancel(self._pulse_after_id)
            except tk.TclError: pass
            self._pulse_after_id = None

    def _stop_camera_animation(self) -> None:
        if self._cam_after is not None:
            try: self.after_cancel(self._cam_after)
            except tk.TclError: pass
            self._cam_after = None

    def _base_point(self, nx: float, ny: float, w: float, h: float) -> Tuple[float, float]:
        px, py = max(56.0, w * 0.068), max(44.0, h * 0.068)
        return px + nx * max(120.0, w - 2.0 * px), py + ny * max(120.0, h - 2.0 * py)

    def animate_reset_view(self, steps: int = 10, step_ms: int = 18) -> None:
        """Devuelve la cámara al encuadre general de forma interpolada."""
        self._animate_camera_to(1.0, 0.0, 0.0, steps, step_ms)

    def animate_focus_region(
        self, node_ids: Iterable[str], pipe_ids: Optional[Iterable[str]] = None,
        left_reserve_px: float = 0.0, steps: int = 12, step_ms: int = 18,
    ) -> None:
        """Acerca la cámara a una región dejando libre el margen izquierdo (ficha flotante)."""
        if self._graph is None: return
        pts: List[Tuple[float, float]] = []
        for nid in node_ids or ():
            n = self._graph.get_node(nid)
            if n is not None: pts.append((n.x, n.y))
        for pid in pipe_ids or ():
            e = self._graph.get_pipe(pid)
            for nid in ((e.from_node, e.to_node) if e is not None else ()):
                n = self._graph.get_node(nid)
                if n is not None: pts.append((n.x, n.y))
        if not pts: return
        w, h = self._canvas_dims()
        x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts)
        y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
        bx0, by0 = self._base_point(x0, y0, w, h)
        bx1, by1 = self._base_point(x1, y1, w, h)
        span_x, span_y = max(28.0, bx1 - bx0), max(28.0, by1 - by0)
        safe_left = min(float(left_reserve_px), w * 0.42)
        avail_w, avail_h = max(180.0, w - safe_left - 44.0), max(160.0, h - 68.0)
        zoom = max(1.05, min(2.55, avail_w * 0.72 / span_x, avail_h * 0.72 / span_y))
        cx, cy = w * 0.5, h * 0.5
        mx, my = 0.5 * (bx0 + bx1), 0.5 * (by0 + by1)
        tcx, tcy = safe_left + avail_w * 0.5, h * 0.48
        self._animate_camera_to(zoom, (tcx - cx) - (mx - cx) * zoom, (tcy - cy) - (my - cy) * zoom, steps, step_ms)

    def _animate_camera_to(self, tz: float, tpx: float, tpy: float, steps: int = 12, step_ms: int = 18) -> None:
        self._stop_camera_animation()
        tz = max(_ZOOM_MIN, min(_ZOOM_MAX, tz))
        z0, px0, py0, total = self._zoom, self._pan_x, self._pan_y, max(1, int(steps))
        self._hide_tooltip()

        def tick(i: int) -> None:
            self._cam_after = None
            t = i / float(total)
            e = 1.0 - (1.0 - t) * (1.0 - t)
            self._zoom, self._pan_x, self._pan_y = z0 + (tz - z0) * e, px0 + (tpx - px0) * e, py0 + (tpy - py0) * e
            self.rebuild_geometry()
            if i < total:
                try: self._cam_after = self.after(step_ms, lambda: tick(i + 1))
                except tk.TclError: self._cam_after = None

        tick(1)

    def _center_world_point(self, nx: float, ny: float) -> None:
        self._stop_camera_animation()
        w, h = self._canvas_dims()
        bx, by = self._base_point(nx, ny, w, h)
        self._pan_x, self._pan_y = -(bx - w * 0.5) * self._zoom, -(by - h * 0.5) * self._zoom
        self.rebuild_geometry()

    def focus_node(self, node_id: str) -> None:
        n = self._graph.get_node(node_id) if self._graph else None
        if n is not None: self._center_world_point(n.x, n.y)

    def focus_pipe(self, pipe_id: str) -> None:
        e = self._graph.get_pipe(pipe_id) if self._graph else None
        if e is None: return
        a, b = self._graph.get_node(e.from_node), self._graph.get_node(e.to_node)
        if a is not None and b is not None: self._center_world_point((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)

    # ── Utilidades de texto ──────────────────────────────────────────────────

    def _font(self, spec: Tuple[str, int, str]) -> tkfont.Font:
        f = self._font_cache.get(spec)
        if f is None:
            f = self._font_cache[spec] = tkfont.Font(root=self, font=spec)
        return f

    def _text_size(self, text: str, spec: Tuple[str, int, str]) -> Tuple[float, float]:
        """Ancho/alto estimados sumando anchos de glifo cacheados (Font.measure por texto es muy lento)."""
        cw = self._char_w.setdefault(spec, {})
        f, total = self._font(spec), 0.0
        for ch in text:
            v = cw.get(ch)
            if v is None:
                v = cw[ch] = float(f.measure(ch))
            total += v
        lh = self._line_h.get(spec)
        if lh is None:
            lh = self._line_h[spec] = float(f.metrics("linespace"))
        return total, lh

    # ── Fase A: reconstrucción geométrica ────────────────────────────────────

    def _canvas_dims(self) -> Tuple[float, float]:
        w, h = float(self.winfo_width()), float(self.winfo_height())
        return (max(w if w > 1.0 else float(self.winfo_reqwidth() or 760), 260.0),
                max(h if h > 1.0 else float(self.winfo_reqheight() or 520), 200.0))

    def _project(self, nx: float, ny: float, w: float, h: float) -> Tuple[float, float]:
        bx, by = self._base_point(nx, ny, w, h)
        cx, cy = w * 0.5, h * 0.5
        return cx + (bx - cx) * self._zoom + self._pan_x, cy + (by - cy) * self._zoom + self._pan_y

    def _draw_grid(self, w: float, h: float) -> None:
        step = max(22.0, 34.0 * self._zoom)
        cx, cy = w * 0.5 + self._pan_x, h * 0.5 + self._pan_y
        for i in range(math.floor(-cx / step), math.ceil((w - cx) / step) + 1):
            self.create_line(cx + i * step, 0, cx + i * step, h, fill=theme.CANVAS_GRID_MAJOR if i % 4 == 0 else theme.CANVAS_GRID_MINOR)
        for j in range(math.floor(-cy / step), math.ceil((h - cy) / step) + 1):
            self.create_line(0, cy + j * step, w, cy + j * step, fill=theme.CANVAS_GRID_MAJOR if j % 4 == 0 else theme.CANVAS_GRID_MINOR)

    def _reg(self, items: Iterable[int], kind: str, eid: str) -> None:
        for i in items: self._item_to_entity[i] = (kind, eid)

    def rebuild_geometry(self) -> None:
        """Fase A: crea retícula e ítems (visibles y auxiliares ocultos) y guarda sus IDs."""
        self.delete("all")
        self._geoms.clear(); self._ngeoms.clear(); self._item_to_entity.clear()
        self._node_coords.clear(); self._node_radii.clear(); self._active_pulses = []
        self._origin_ring = self._sel_ring = self._empty_text = None
        self._sel_cache = self._origin_cache = None
        w, h = self._canvas_dims()
        self._layout_overlays(w, h)
        self._update_zoom_label()
        self._draw_grid(w, h)
        if self._graph is None:
            self._empty_text = self.create_text(w / 2, h / 2, text="Cargue un archivo Excel o carpeta CSV para visualizar la red.",
                                                fill=theme.INK_MUTED, font=self._fonts["body"])
            return

        graph, ui, mono = self._graph, self._fonts["label"][0], self._fonts["mono"][0]
        nodes = graph.nodes()
        coords = {n.node_id: self._project(n.x, n.y, w, h) for n in nodes}
        # Escala y radio responsivos según distancia mínima entre nodos y zoom
        sf = self._sf = max(0.72, min(1.22, min(w, h) / 560.0))
        pts, min_d = list(coords.values()), 999.0
        for i in range(len(pts)):
            xi, yi = pts[i]
            for j in range(i + 1, len(pts)):
                d = math.hypot(pts[j][0] - xi, pts[j][1] - yi)
                if 1e-3 < d < min_d: min_d = d
        base_r = 10.4 * sf * math.sqrt(self._zoom)
        safe_r = min_d * 0.30 if min_d < 900.0 else 16.5
        r_node = self._node_r = max(2.8, min(16.5, base_r, safe_r))
        sink_extra = min(3.5, max(1.4, r_node * 0.26))
        dense = self._dense = (w < 500 or self._zoom < 0.78)
        radii = {n.node_id: r_node + (sink_extra if n.node_type == "sink" else 0.0) for n in nodes}
        self._node_coords, self._node_radii = coords, radii
        self._lbl_font_px = max(8, min(11, int(round((9.2 if (self._zoom < 1.15 or dense) else 10.6) * min(1.12, max(0.86, sf))))))
        zf = min(1.45, max(0.78, math.sqrt(self._zoom) * sf))

        # Pasada 0: geometría de tuberías
        plans: List[_PipeGeom] = []
        pipe_segments: List[_Box] = []
        for pipe in graph.pipes():
            p1, p2 = coords.get(pipe.from_node), coords.get(pipe.to_node)
            if p1 is None or p2 is None: continue
            dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
            if dist < 1e-3: continue
            ux, uy = (p2[0] - p1[0]) / dist, (p2[1] - p1[1]) / dist
            g1, g2 = min(1.5, r_node * 0.14), min(3.0, r_node * 0.24)
            c1 = min(radii[pipe.from_node] + g1, dist * 0.35)
            c2 = min(radii[pipe.to_node] + g2, dist * 0.40)
            sx1, sy1, sx2, sy2 = p1[0] + ux * c1, p1[1] + uy * c1, p2[0] - ux * c2, p2[1] - uy * c2
            pipe_segments.append((p1[0], p1[1], p2[0], p2[1]))
            inv = self._interventions.get(pipe.pipe_id)
            q_eff, vel_eff, _tr, d_eff = resolve_pipe_hydraulics(pipe, inv)
            enlarged = inv is not None and inv.diameter_in_override is not None and inv.diameter_in_override > pipe.diameter_in + 1e-6
            width = max(1.4, (2.0 + (d_eff - 8.0) * 0.24) * zf)
            width = max(1.2, min(width, max(2.4, r_node * 0.55)))
            g = _PipeGeom(
                pipe.pipe_id, sx1, sy1, sx2, sy2, dist, ux, uy, math.hypot(sx2 - sx1, sy2 - sy1), width, inv,
                bool(inv is not None and inv.is_closed), bool(inv is not None and inv.has_obstruction), enlarged, d_eff, vel_eff,
            )
            g.has_mark = g.obstructed or g.enlarged
            plans.append(g)

        arr = max(0.85, min(1.35, sf * min(1.2, self._zoom ** 0.3)))
        arrow_scale = max(0.38, min(1.0, r_node / 8.0))
        arrowshape = (max(3.2, round(8 * arr * arrow_scale, 1)), max(4.0, round(10 * arr * arrow_scale, 1)), max(1.5, round(3.8 * arr * arrow_scale, 1)))
        pipes_by_id = {g.pid: g for g in plans}

        # Pasada 1: halos y líneas
        for g in plans:
            sx2, sy2 = g.sx2, g.sy2
            g.halo = self.create_line(g.sx1, g.sy1, sx2, sy2, fill=_OVERLOAD_HALO, width=g.width + 4.0, capstyle=tk.ROUND, state="hidden")
        for g in plans:
            sx2, sy2 = g.sx2, g.sy2
            if g.enlarged and g.seg_len > 10.0:
                nx, ny, off = -g.uy, g.ux, g.width / 2.0 + 2.8
                for sign in (-1.0, 1.0):
                    g.extras.append(self.create_line(
                        g.sx1 + nx * off * sign, g.sy1 + ny * off * sign, sx2 + nx * off * sign, sy2 + ny * off * sign,
                        fill=_DOUBLE_LINE_COLOR, width=1.4))
        for g in plans:
            sx2, sy2 = g.sx2, g.sy2
            kw = {"arrow": tk.LAST, "arrowshape": arrowshape} if g.seg_len > 2.5 else {}
            g.line = self.create_line(g.sx1, g.sy1, sx2, sy2, fill=theme.PIPE_IDLE_COLOR, width=g.width, capstyle=tk.ROUND, joinstyle=tk.ROUND, **kw)
            self._reg((g.line, g.halo), "pipe", g.pid)
        # Pasada 2: barras de obstrucción / × de cierre y pulsos
        for g in plans:
            sx2, sy2 = g.sx2, g.sy2
            mx, my = (g.sx1 + sx2) / 2.0, (g.sy1 + sy2) / 2.0
            if g.seg_len > 12.0 and g.closed:
                half = max(6.0, g.width * 1.4)
                for sx, sy in ((1.0, 1.0), (1.0, -1.0)):
                    g.extras.append(self.create_line(mx - half * sx, my - half * sy, mx + half * sx, my + half * sy,
                                                     fill=_BARRIER_COLOR, width=2.4, capstyle=tk.ROUND))
            elif g.seg_len > 12.0 and g.obstructed:
                nx, ny, half = -g.uy, g.ux, max(6.5, g.width * 1.45)
                for off in (-3.0, 3.0):
                    cx, cy = mx + g.ux * off, my + g.uy * off
                    g.extras.append(self.create_line(cx - nx * half, cy - ny * half, cx + nx * half, cy + ny * half,
                                                     fill=_BARRIER_COLOR, width=2.0))
            self._reg([i for i in g.extras if i], "pipe", g.pid)
        for g in plans:
            if g.seg_len < 20.0: continue
            n_p, usable = (3 if g.seg_len > 115.0 else 2), max(8.0, g.seg_len - 13.0)
            for k in range(n_p):
                m = _PulseMeta(-1, g.pid, g.sx1, g.sy1, g.ux, g.uy, usable, k / float(n_p), max(3.6, min(5.4, g.width * 0.88)), g.vel_ref)
                m.item_id = self.create_line(*self._chevron_coords(m), fill=theme.INK_PRIMARY, width=max(1.4, min(2.2, g.width * 0.42)),
                                             capstyle=tk.ROUND, joinstyle=tk.ROUND, state="hidden")
                g.pulses.append(m)

        # Pasada 3: etiquetas sin colisión (cola de prioridad + cajas ocupadas)
        r_box = max(3.0, r_node * 0.8)
        node_boxes: List[_Box] = [(x - r_box, y - r_box, x + r_box, y + r_box) for x, y in pts]
        circle_boxes: List[_Box] = [(x - r_node - 1.5, y - r_node - 1.5, x + r_node + 1.5, y + r_node + 1.5) for x, y in pts]
        overlay_boxes = self._overlay_boxes(w, h)
        placed: List[_Box] = node_boxes + overlay_boxes

        # Insignias (PTAR primero: tiene prioridad de ubicación)
        badge_font_px = max(7, min(10, int(round(9.0 * sf * min(1.08, math.sqrt(self._zoom))))))
        ptar_px = max(8, min(11, int(round(10.5 * sf * min(1.12, math.sqrt(self._zoom))))))
        badge_plan: Dict[str, Tuple[float, float, str, int, _Box]] = {}
        for n in nodes:
            x, y = coords[n.node_id]
            if n.node_type == "sink":
                rs = radii[n.node_id]
                chosen = fallback = None
                for txt in ("PTAR Punta Canoa · 31", "PTAR · 31"):
                    bw, bh = self._text_size(txt, (ui, -ptar_px, "bold"))
                    bw, bh = bw + 10.0, bh + 4.0
                    cx = max(bw / 2.0 + 6.0, min(w - bw / 2.0 - 6.0, x))
                    for cy in (y - rs - bh / 2.0 - 4.0, y + rs + bh / 2.0 + 4.0):
                        cyc = max(bh / 2.0 + 4.0, min(h - bh / 2.0 - 4.0, cy))
                        box = (cx - bw / 2.0, cyc - bh / 2.0, cx + bw / 2.0, cyc + bh / 2.0)
                        if fallback is None or txt == "PTAR · 31": fallback = (cx, cyc, txt, ptar_px, box)
                        if not any(_boxes_overlap(box, b) for b in circle_boxes + overlay_boxes):
                            chosen = (cx, cyc, txt, ptar_px, box); break
                    if chosen: break
                pick = chosen or fallback
                if pick: badge_plan[n.node_id] = pick; placed.append(pick[4])
            elif n.node_type == "source" and not dense and r_node >= 6.0:
                bw, bh = self._text_size("Fuente", (ui, -badge_font_px, "bold"))
                bw, bh = bw + 8.0, bh + 2.0
                rs = radii[n.node_id]
                vs = (-1.0, 1.0) if n.y >= 0.30 else (1.0, -1.0)
                cands = [(x, y + vs[0] * (rs + bh / 2.0 + 3.0)), (x + rs + bw / 2.0 + 4.0, y),
                         (x - rs - bw / 2.0 - 4.0, y), (x, y + vs[1] * (rs + bh / 2.0 + 3.0))]
                for cx, cy in cands:
                    box = (cx - bw / 2.0, cy - bh / 2.0, cx + bw / 2.0, cy + bh / 2.0)
                    if box[0] < 4.0 or box[2] > w - 4.0 or box[1] < 4.0 or box[3] > h - 4.0: continue
                    if any(_boxes_overlap(box, b) for b in placed): continue
                    if any(_box_hits_segment(box, *s) for s in pipe_segments): continue
                    badge_plan[n.node_id] = (cx, cy, "Fuente", badge_font_px, box); placed.append(box); break

        lbl_spec = (mono, -self._lbl_font_px, "bold")
        queue = []
        snap_ps = self._snapshot.pipe_states if self._snapshot else {}
        for g in plans:
            if g.dist <= 26.0: continue
            ps = snap_ps.get(g.pid)
            u = max(ps.utilization_pct if ps else 0.0, self._peak_util.get(g.pid, 0.0))
            prio = (6 if g.has_mark else 0) + (4 if (self._selected_kind == "pipe" and self._selected_id == g.pid) else 0) \
                + (2 if u > 100.0 else (1 if u > 75.0 else 0))
            if dense and prio == 0: continue
            queue.append((prio, u, g))
        queue.sort(key=lambda it: (it[0], it[1]), reverse=True)
        for prio, _u, g in queue:
            sx2, sy2 = g.sx2, g.sy2
            mx, my = (g.sx1 + sx2) / 2.0, (g.sy1 + sy2) / 2.0
            txt = ("[OBST 100%] " if g.obstructed else "") + ('[Ø99"] ' if g.enlarged else "") + f"{g.pid} · 100%"
            tw, th = self._text_size(txt, lbl_spec)
            nx_p, ny_p = -g.uy, g.ux
            if ny_p > 0.35: nx_p, ny_p = -nx_p, -ny_p
            if abs(g.ux) < 0.35:
                side = -1.0 if mx > w * 0.72 else 1.0
                cands = [(mx + side * 9.0, my, "w" if side > 0 else "e")]
                cands.append((mx - side * 9.0, my, "e" if side > 0 else "w"))
            else:
                cands = [(mx + nx_p * off, my + ny_p * off, "center") for off in (13.0, 17.0, 20.0)]
                cands += [(mx - nx_p * off, my - ny_p * off, "center") for off in (13.0, 17.0)]
            for lx, ly, anchor in cands:
                x0 = lx - tw / 2.0 if anchor == "center" else (lx if anchor == "w" else lx - tw)
                box = (x0 - 3.0, ly - th / 2.0 - 1.0, x0 + tw + 3.0, ly + th / 2.0 + 1.0)
                if box[0] < 2.0 or box[2] > w - 2.0 or box[1] < 2.0 or box[3] > h - 2.0: continue
                if any(_boxes_overlap(box, b) for b in placed): continue
                g.slot, g.lbl_ok = (lx, ly, anchor), True
                placed.append(box)
                break
            else:
                g.slot = cands[0]  # sin hueco libre: solo se muestra si está seleccionada o marcada
        for g in plans:
            if g.slot is None: continue
            g.lbl_rect = self.create_rectangle(0, 0, 0, 0, fill=theme.PAPER_BG, outline=theme.PAPER_BORDER, state="hidden")
            g.lbl_txt = self.create_text(g.slot[0], g.slot[1], text="", fill=theme.INK_PRIMARY, font=lbl_spec, anchor=g.slot[2], state="hidden")
            self._reg((g.lbl_rect, g.lbl_txt), "pipe", g.pid)
        self._geoms = pipes_by_id

        # Pasada 4: nodos (anillos de rebose, óvalo, ID), insignias y marca de aislamiento
        cut_nodes: Set[str] = set()
        for pid, inv in self._interventions.items():
            e = graph.get_pipe(pid)
            if inv.is_closed and e is not None and e.from_node in self._isolated_nodes: cut_nodes.add(e.from_node)
        node_font_px = lambda r: max(7, min(14, int(round(r * 1.12))))  # noqa: E731
        for n in nodes:
            x, y = coords[n.node_id]
            r = radii[n.node_id]
            ng = _NodeGeom(n.node_id, n.node_type, x, y, r)
            ng.rings = (
                self.create_oval(x - r, y - r, x + r, y + r, fill="", outline=_FLOOD_STORAGE, width=1.25, state="hidden"),
                self.create_oval(x - r, y - r, x + r, y + r, fill="", outline=_FLOOD_STORAGE, width=1.25, dash=(3, 3), state="hidden"),
            )
            fill, out, tfill, ow = _NODE_BASE_STYLE.get(n.node_type, _NODE_BASE_STYLE["manhole"])
            ow = max(1.1, min(ow, r * 0.18 + 0.4))
            ng.oval = self.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline=out, width=ow)
            ng.text = self.create_text(x, y, text=n.node_id, fill=tfill, font=(ui, -node_font_px(r), "bold"), state="normal" if (r_node >= 5.6 or n.node_type == "sink") else "hidden")
            self._reg((ng.oval, ng.text), "node", n.node_id)
            bp = badge_plan.get(n.node_id)
            if bp is not None:
                cx, cy, txt, px, box = bp
                sink = n.node_type == "sink"
                rect = self.create_rectangle(*box, fill=theme.SHELL_BG if sink else theme.DOCK_BG,
                                             outline=theme.ACCENT_PRIMARY if sink else theme.INK_PRIMARY, width=1.5 if sink else 1)
                tid = self.create_text(cx, cy, text=txt, fill=theme.SHELL_TEXT if sink else theme.INK_PRIMARY, font=(ui, -px, "bold"))
                ng.badge = (rect, tid)
                self._reg((rect, tid), "node", n.node_id)
            if n.node_id in self._isolated_nodes:
                spec = (mono, -max(8, min(10, badge_font_px)), "bold")
                tw, th = self._text_size("[AISLADO DE 31]", spec)
                iy = max(12.0, y - r - 12.0)
                rect = self.create_rectangle(x - tw / 2 - 4, iy - th / 2 - 1, x + tw / 2 + 4, iy + th / 2 + 1, fill=theme.DOCK_BG, outline=theme.INK_PRIMARY, state="hidden")
                tid = self.create_text(x, iy, text="[AISLADO DE 31]", fill=theme.INK_PRIMARY, font=spec, state="hidden")
                ng.iso_tag, ng.iso_cut = (rect, tid), n.node_id in cut_nodes
                self._reg((rect, tid), "node", n.node_id)
            self._ngeoms[n.node_id] = ng
        self._sel_ring = self.create_oval(0, 0, 0, 0, fill="", outline=_SEL_RING_COLOR, width=2.2, state="hidden")
        self._origin_ring = self.create_oval(0, 0, 0, 0, fill="", outline=theme.TRAV_BFS_EDGE, width=3.6, state="hidden")
        self.update_visuals(force=True)

    # ── Fase B: actualización visual incremental ─────────────────────────────

    def _resolve(self, pid: str, ps, closed: bool) -> Tuple[str, int, bool, bool, float, str]:
        """(color, tier, sobrecargada, crítica, valor, etiqueta) según el modo de mapa."""
        if self.map_mode == "overload_minutes":
            ov = self._overload_min.get(pid, 0.0)
            tier, col, _ = classify_overload_persistence(ov, self._total_duration_min)
            return (theme.INK_PRIMARY if closed else col, tier, tier >= 3 and not closed, tier >= 2 and not closed,
                    ov, f"{ov:.0f}m" if ov >= 0.5 else "0m")
        if closed:
            return theme.INK_PRIMARY, 0, False, False, 0.0, ""
        if self.map_mode == "peak":
            u = self._peak_util.get(pid, ps.utilization_pct if ps is not None else None)
            if u is not None:
                cat = classify_utilization(u)
                return cat.color_hex, cat.tier_index, cat.is_overloaded, u > 75.0, u, _fmt_pct(u)
        if ps is None:
            return theme.PIPE_IDLE_COLOR, 0, False, False, 0.0, ""
        u = ps.utilization_pct
        return ps.category.color_hex, ps.category.tier_index, ps.category.is_overloaded, u > 75.0, u, _fmt_pct(u)

    @staticmethod
    def _trav_palette(mode: Optional[str]):
        if mode == "downstream":
            return (theme.TRAV_DOWNSTREAM_EDGE, theme.TRAV_DOWNSTREAM_NODE, theme.TRAV_DOWNSTREAM_OUTLINE,
                    theme.TRAV_DOWNSTREAM_EDGE, (), "#E0F2FE", "#0369A1")
        if mode == "upstream":
            return (theme.TRAV_UPSTREAM_EDGE, theme.TRAV_UPSTREAM_NODE, theme.TRAV_UPSTREAM_OUTLINE,
                    theme.TRAV_UPSTREAM_EDGE, (8, 4), "#F3E8FF", "#5B21B6")
        if mode == "dfs":
            return (theme.TRAV_DFS_EDGE, theme.TRAV_DFS_NODE, theme.TRAV_DFS_OUTLINE, theme.TRAV_DFS_PATH, (6, 3), "#E0E7FF", "#3730A3")
        return (theme.TRAV_BFS_EDGE, theme.TRAV_BFS_NODE, theme.TRAV_BFS_OUTLINE, theme.TRAV_BFS_PATH, (6, 3), "#CCFBF1", "#0F766E")

    def update_visuals(self, force: bool = False) -> None:
        """Fase B: solo itemconfigure/coords sobre ítems cacheados (sin delete ni bbox)."""
        if self._graph is None or not self._geoms and not self._ngeoms: return
        snap = self._snapshot
        pstates = snap.pipe_states if snap else {}
        nstates = snap.node_states if snap else {}
        sel_k, sel_id = self._selected_kind, self._selected_id
        bd, td = self._basin_active, self._tour_active
        has_trav = bool(
            self._traversal_mode or self._visited_nodes or self._visited_edges or self._path_nodes or self._path_edges
            or self._current_node or self._origin_node or self._active_nodes or self._active_edges
            or self._active_edge or self._backtracked_nodes or self._backtracked_edges
        )
        edge_col, node_fill, node_out, path_col, edge_dash, b_bg, b_fg = self._trav_palette(self._traversal_mode)
        playing, ov_mode = self._playing, self.map_mode == "overload_minutes"
        ic = self.itemconfigure
        active_pulses: List[_PulseMeta] = []
        show_ids, show_util = self._show_pipe_labels, self._show_util_labels

        for pid, g in self._geoms.items():
            ps = pstates.get(pid)
            closed = g.closed or (ps is not None and ps.is_closed)
            color, tier, over, crit, val, suf = self._resolve(pid, ps, closed)
            dim = (bd and pid not in self._basin_pipes) or (td and pid not in self._tour_pipes)
            iso = pid in self._isolated_pipes and not closed
            sel = sel_k == "pipe" and sel_id == pid
            active = pid == self._active_edge or pid in self._active_edges
            path, visited, back = pid in self._path_edges, pid in self._visited_edges, pid in self._backtracked_edges
            in_focus = active or path or visited
            width, dash, faded = g.width, (), False
            if has_trav:
                if active: color, width = theme.TRAV_ACTIVE_COLOR, g.width + 2.4
                elif back: color, width, dash, faded = theme.TRAV_DIM_OUTLINE, max(1.4, g.width * 0.72), (5, 4), True
                elif path: color, width = path_col, g.width + 2.0
                elif visited: color, width, dash = edge_col, g.width + 1.4, edge_dash
                else: color, width, faded = theme.TRAV_DIM_PIPE, 1.2, True
            elif dim or iso:
                color, width, dash, faded = _FOCUS_DIM_PIPE, max(1.4, g.width * 0.72), ((5, 4) if iso else ()), True
            else:
                if over and not closed: width += 1.5
                if closed: dash = (3, 3)
            if dim and has_trav: faded = True
            if sel: width = max(width, g.width + 1.2)
            spec = (color, width, dash)
            if force or g.c_line != spec:
                ic(g.line, fill=color, width=width, dash=dash); g.c_line = spec

            if sel: hs = ("normal", theme.SELECTED_HALO, width + 6.0)
            elif over and not closed and not faded and not has_trav: hs = ("normal", _OVERLOAD_HALO, width + 4.0)
            else: hs = ("hidden", _OVERLOAD_HALO, 0.0)
            if force or g.c_halo != hs:
                ic(g.halo, state=hs[0], fill=hs[1], width=max(1.0, hs[2])); g.c_halo = hs

            if g.extras:
                es = "hidden" if faded else "normal"
                if force or g.c_extras != es:
                    for i in g.extras: ic(i, state=es)
                    g.c_extras = es

            if g.pulses:
                want = playing and ps is not None and not closed and not faded and not has_trav and ps.flow_m3s > _FLOW_EPS
                col = theme.INK_PRIMARY if tier in (0, 1) else theme.PAPER_BG
                vel = ps.effective_velocity_ms if (ps is not None and ps.effective_velocity_ms is not None) else g.vel_ref
                pspec = (want, col)
                if force or g.c_pulse != pspec:
                    for m in g.pulses:
                        ic(m.item_id, state="normal" if want else "hidden", fill=col)
                        if want: self.coords(m.item_id, *self._chevron_coords(m))
                    g.c_pulse = pspec
                if want:
                    for m in g.pulses: m.velocity_ms = vel
                    active_pulses.extend(g.pulses)

            if g.lbl_txt is not None:
                ov_badge = ov_mode and not closed and val >= 0.5 and not faded
                if has_trav: show = sel or in_focus or g.has_mark
                elif dim: show = sel
                else: show = g.lbl_ok or sel or g.has_mark or ov_badge
                marks = []
                if g.obstructed and g.inv is not None: marks.append(f"[OBST {g.inv.obstruction_pct:.0f}%]")
                if g.enlarged: marks.append(f'[Ø{g.eff_diam:.0f}"]')
                head = " ".join(marks + ([pid] if show_ids else []))
                if ov_badge: tail = f"{val:.0f}m >100%"
                elif show_util and (snap is not None or self.map_mode != "instant") and not closed and suf: tail = suf
                else: tail = ""
                text = f"{head} · {tail}" if (head and tail) else (head or tail)
                bold = bool(over or sel or in_focus or g.has_mark or ov_badge)
                if sel: fg, bg, bd_c = theme.ACCENT_INK, theme.ACCENT_PRIMARY, theme.INK_PRIMARY
                elif ov_badge: fg, bg, bd_c = theme.SHELL_TEXT, theme.SHELL_BG, _OV_BADGE_BORDER
                elif over: fg, bg, bd_c = _OV_LABEL_FG, _OV_LABEL_BG, theme.INK_PRIMARY if g.has_mark else _OV_LABEL_BORDER
                elif in_focus: fg, bg, bd_c = theme.ACCENT_TEXT, theme.ACCENT_SOFT, theme.HIGHLIGHT_PATH_COLOR
                else: fg, bg, bd_c = theme.INK_PRIMARY, theme.PAPER_BG, theme.INK_PRIMARY if g.has_mark else theme.PAPER_BORDER
                st = "normal" if (show and text) else "hidden"
                lspec = (text if st == "normal" else "", fg, bg, bd_c, bold, st)
                if force or g.c_lbl != lspec:
                    prev = g.c_lbl
                    if st == "normal":
                        spec_f = (self._fonts["mono"][0], -self._lbl_font_px, "bold" if bold else "normal")
                        ic(g.lbl_txt, text=text, fill=fg, state="normal", font=spec_f)
                        if prev is None or prev[0] != text or prev[4] != bold:
                            tw, th = self._text_size(text, spec_f)
                            lx, ly, anchor = g.slot
                            x0 = lx - tw / 2.0 if anchor == "center" else (lx if anchor == "w" else lx - tw)
                            self.coords(g.lbl_rect, x0 - 3.0, ly - th / 2.0 - 1.0, x0 + tw + 3.0, ly + th / 2.0 + 1.0)
                        ic(g.lbl_rect, fill=bg, outline=bd_c, state="normal")
                    else:
                        ic(g.lbl_txt, state="hidden"); ic(g.lbl_rect, state="hidden")
                    g.c_lbl = lspec
        self._active_pulses = active_pulses

        sqrt_z, sf = math.sqrt(self._zoom), self._sf
        for nid, ng in self._ngeoms.items():
            n_type = ng.node_type
            fill, out, tfill, ow = _NODE_BASE_STYLE.get(n_type, _NODE_BASE_STYLE["manhole"])
            ow = max(1.1, min(ow, ng.r * 0.18 + 0.4))
            is_man = n_type == "manhole"
            dim = (bd and nid not in self._basin_nodes) or (td and nid not in self._tour_nodes)
            iso = nid in self._isolated_nodes
            sel = sel_k == "node" and sel_id == nid
            dash = ()
            faded = False
            if dim:
                fill, out, tfill, faded = theme.PAPER_SUBTLE, _FOCUS_DIM_NODE_OUT, _FOCUS_DIM_NODE_TXT, True
            elif iso:
                fill, out, tfill, dash, faded = theme.PAPER_SUBTLE, theme.DOCK_BG, theme.INK_MUTED, (3, 2), True
            elif has_trav:
                if nid == self._current_node or nid in self._active_nodes:
                    out, ow = theme.TRAV_ACTIVE_COLOR, 3.8
                    if is_man: fill, tfill = theme.TRAV_ACTIVE_COLOR, "#FFFFFF"
                elif nid in self._backtracked_nodes:
                    fill, out, tfill, dash, faded = theme.TRAV_DIM_NODE, theme.TRAV_DIM_OUTLINE, theme.TRAV_DIM_TEXT, (3, 2), True
                elif nid in self._path_nodes:
                    out, ow = path_col, 3.2
                    if is_man: fill, tfill = node_fill, theme.INK_PRIMARY
                elif nid in self._visited_nodes:
                    out, ow = node_out, (2.8 if is_man else 3.4)
                    if is_man: fill, tfill = node_fill, theme.INK_PRIMARY
                else:
                    faded = True
                    if is_man: fill, out, ow, tfill = theme.TRAV_DIM_NODE, theme.TRAV_DIM_OUTLINE, 1.1, theme.TRAV_DIM_TEXT
                    else: out = theme.TRAV_DIM_OUTLINE
            if sel and not dim: out, ow = theme.SELECTED_HALO, max(ow, 3.0)
            show_txt = "normal" if (self._node_r >= 5.6 or n_type == "sink" or sel) else "hidden"
            nspec = (fill, out, ow, tfill, dash, show_txt)
            if force or ng.c_node != nspec:
                ic(ng.oval, fill=fill, outline=out, width=ow, dash=dash)
                ic(ng.text, fill=tfill, state=show_txt)
                ng.c_node = nspec

            ns = nstates.get(nid)
            vol = (ns.stored_volume_m3 + ns.surface_flooding_m3) if ns is not None else 0.0
            if vol > 1e-3 and not dim and not has_trav:
                flood = ns.surface_flooding_m3 > 1e-9 or ns.flooding_rate_m3s > 1e-9
                n_r = 1 if vol < 5.0 else 2
                extra = min(14.5, 2.6 + 3.4 * math.log10(1.0 + vol)) * sf * sqrt_z
                extra = round(min(extra, max(2.8, ng.r * 1.15)), 1)
                rspec = (n_r, extra, flood, vol >= 25.0)
            else:
                rspec = None
            if force or ng.c_ring != rspec:
                if rspec is None:
                    ic(ng.rings[0], state="hidden"); ic(ng.rings[1], state="hidden")
                else:
                    n_r, extra, flood, deep = rspec
                    base_c = _FLOOD_SURFACE if flood else _FLOOD_STORAGE
                    r1 = ng.r + extra / n_r
                    self.coords(ng.rings[0], ng.x - r1, ng.y - r1, ng.x + r1, ng.y + r1)
                    ic(ng.rings[0], state="normal", outline=_FLOOD_DEEP if (flood and deep) else base_c, width=1.5 if deep else 1.25)
                    if n_r == 2:
                        r2 = ng.r + extra
                        self.coords(ng.rings[1], ng.x - r2, ng.y - r2, ng.x + r2, ng.y + r2)
                        ic(ng.rings[1], state="normal", outline=base_c)
                    else:
                        ic(ng.rings[1], state="hidden")
                ng.c_ring = rspec

            if ng.badge is not None:
                bs = "hidden" if dim else "normal"
                tx_c = (theme.INK_MUTED if iso else (theme.SHELL_TEXT if n_type == "sink" else theme.INK_PRIMARY))
                bspec = (bs, tx_c)
                if force or ng.c_badge != bspec:
                    ic(ng.badge[0], state=bs); ic(ng.badge[1], state=bs, fill=tx_c)
                    ng.c_badge = bspec
            if ng.iso_tag is not None:
                is_ = "normal" if ((ng.iso_cut or sel) and not (bd and nid not in self._basin_nodes) and not (td and nid not in self._tour_nodes)) else "hidden"
                if force or ng.c_iso != is_:
                    ic(ng.iso_tag[0], state=is_); ic(ng.iso_tag[1], state=is_)
                    ng.c_iso = is_

        # Anillo de nodo seleccionado
        sspec = None
        if sel_k == "node" and sel_id in self._ngeoms and not (bd and sel_id not in self._basin_nodes):
            ng = self._ngeoms[sel_id]
            sspec = (ng.x, ng.y, ng.r)
        if self._sel_ring is not None and (force or sspec != self._sel_cache):
            if sspec is None: ic(self._sel_ring, state="hidden")
            else:
                rr = sspec[2] + max(1.8, min(3.5, sspec[2] * 0.32))
                self.coords(self._sel_ring, sspec[0] - rr, sspec[1] - rr, sspec[0] + rr, sspec[1] + rr)
                ic(self._sel_ring, state="normal")
            self._sel_cache = sspec

        if self._origin_ring is not None:
            ospec = None
            if has_trav and self._origin_node and self._origin_node in self._node_coords:
                ospec = (self._origin_node, edge_col)
            if force or ospec != self._origin_cache:
                if ospec is None: ic(self._origin_ring, state="hidden")
                else:
                    ox, oy = self._node_coords[ospec[0]]
                    orr = self._node_radii[ospec[0]] + 6.5
                    self.coords(self._origin_ring, ox - orr, oy - orr, ox + orr, oy + orr)
                    ic(self._origin_ring, outline=edge_col, width=3.6, state="normal")
                self._origin_cache = ospec

        if has_trav and self._banner_text:
            self._banner_lbl.configure(text=self._banner_text, bg=b_bg, fg=b_fg, highlightbackground=edge_col)
            self._banner_lbl.place(x=12, y=48)
        else:
            self._banner_lbl.place_forget()

    # ── Interacción: zoom, pan, selección, resize y tooltip ──────────────────

    def _on_destroy(self, e: tk.Event) -> None:
        if e.widget is self:
            self.cancel_pending()

    def _on_configure(self, e: tk.Event) -> None:
        size = (int(e.width), int(e.height))
        if size != self._last_size:
            self._last_size = size
            self._layout_overlays(float(e.width), float(e.height))
            if self._resize_after is not None:
                try: self.after_cancel(self._resize_after)
                except tk.TclError: pass
            self._resize_after = self.after(_RESIZE_MS, self._on_resize_debounced)

    def _on_resize_debounced(self) -> None:
        self._resize_after = None
        self.rebuild_geometry()

    def _on_mouse_wheel(self, e: tk.Event) -> None:
        if getattr(e, "delta", 0): self._wheel_zoom(e, 1.12 if e.delta > 0 else 1.0 / 1.12)

    def _wheel_zoom(self, e: tk.Event, factor: float) -> None:
        self._stop_camera_animation()
        self._zoom_at(e.x, e.y, factor)

    def _zoom_at(self, mx: float, my: float, factor: float) -> None:
        nz = max(_ZOOM_MIN, min(_ZOOM_MAX, self._zoom * factor))
        if abs(nz - self._zoom) < 1e-4: return
        w, h = self._canvas_dims()
        cx, cy, r = w * 0.5, h * 0.5, nz / self._zoom
        self._pan_x, self._pan_y, self._zoom = (mx - cx) - (mx - cx - self._pan_x) * r, (my - cy) - (my - cy - self._pan_y) * r, nz
        self._hide_tooltip()
        self.rebuild_geometry()

    def _on_left_press(self, e: tk.Event) -> None:
        self._stop_camera_animation()
        self._drag_start, self._drag_pan_origin, self._dragged = (e.x, e.y), (self._pan_x, self._pan_y), False

    def _on_left_drag(self, e: tk.Event) -> None:
        if self._drag_start is None: return
        dx, dy = e.x - self._drag_start[0], e.y - self._drag_start[1]
        if not self._dragged and math.hypot(dx, dy) > _DRAG_PX:
            self._dragged = True
            self._hide_tooltip()
            self.configure(cursor="fleur")
        if self._dragged:
            self._pan_x, self._pan_y = self._drag_pan_origin[0] + dx, self._drag_pan_origin[1] + dy
            self.rebuild_geometry()

    def _on_left_release(self, e: tk.Event) -> None:
        self.configure(cursor="")
        was_drag, self._drag_start, self._dragged = self._dragged, None, False
        if was_drag: return
        kind, eid = self._hit_test(e.x, e.y) or (None, None)
        self.set_selected(kind, eid)
        if self._on_select is not None: self._on_select(kind, eid)

    def _hit_test(self, x: float, y: float) -> Optional[Tuple[str, str]]:
        pipe_hit: Optional[Tuple[str, str]] = None
        for iid in reversed(self.find_overlapping(x - 6, y - 6, x + 6, y + 6)):
            ent = self._item_to_entity.get(iid)
            if ent is None or self.itemcget(iid, "state") == "hidden": continue
            if ent[0] == "node": return ent
            if pipe_hit is None: pipe_hit = ent
        return pipe_hit

    def _on_motion(self, e: tk.Event) -> None:
        if self._dragged or self._graph is None: return
        hit = self._hit_test(e.x, e.y)
        if hit is None:
            self._hide_tooltip()
            return
        if hit != self._hover_entity:
            self._hover_entity = hit
            self._tooltip_lbl.configure(text=self._format_tooltip(*hit))
        w, h = self._canvas_dims()
        tw = max(160, self._tooltip_lbl.winfo_reqwidth())
        th = max(50, self._tooltip_lbl.winfo_reqheight())
        self._tooltip_lbl.place(x=min(max(8, e.x + 14), max(8, int(w) - tw)), y=min(max(8, e.y + 14), max(8, int(h) - th)))

    def _hide_tooltip(self) -> None:
        if self._hover_entity is not None:
            self._hover_entity = None
            self._tooltip_lbl.place_forget()

    def _format_tooltip(self, kind: str, entity_id: str) -> str:
        return self._build_pipe_tooltip(entity_id) if kind == "pipe" else self._build_node_tooltip(entity_id)

    def _build_node_tooltip(self, node_id: str) -> str:
        n = self._graph.get_node(node_id) if self._graph else None
        if n is None: return node_id
        lines = [f"Nodo {n.node_id} · {_NODE_TYPE_ES.get(n.node_type, n.node_type)}"]
        if n.node_id in self._isolated_nodes:
            lines.append("[AISLADO DE 31] Sin ruta hidráulica activa hacia la PTAR")
        ns = self._snapshot.node_states.get(node_id) if self._snapshot else None
        if ns is not None:
            lines.append(f"Entrada: {ns.inflow_m3s:.4f} m³/s  |  Salida: {ns.outflow_m3s:.4f} m³/s")
            if ns.stored_volume_m3 > 1e-4: lines.append(f"En pozo: {ns.stored_volume_m3:.2f} m³")
            if ns.surface_flooding_m3 > 1e-4: lines.append(f"Rebose superficial: {ns.surface_flooding_m3:.2f} m³")
        return "\n".join(lines)

    def _build_pipe_tooltip(self, pipe_id: str) -> str:
        p = self._graph.get_pipe(pipe_id) if self._graph else None
        if p is None: return pipe_id
        inv = self._interventions.get(pipe_id)
        ps = self._snapshot.pipe_states.get(pipe_id) if self._snapshot else None
        q_eff, v_eff, _tr, d_eff = resolve_pipe_hydraulics(p, inv)
        if ps is not None:
            if ps.effective_q_max_m3s is not None: q_eff = ps.effective_q_max_m3s
            if ps.effective_velocity_ms is not None: v_eff = ps.effective_velocity_ms
        lines = [f"Tubería {p.pipe_id}: {p.from_node} → {p.to_node}",
                 f'Ø {d_eff:g}" · L {p.length_m:.1f} m · V {v_eff:.3f} m/s · Qmax {q_eff:.4f} m³/s']
        if inv is not None:
            marks = []
            if inv.has_obstruction: marks.append(f"OBST {inv.obstruction_pct:.0f}%")
            if inv.diameter_in_override is not None and abs(inv.diameter_in_override - p.diameter_in) > 1e-3:
                marks.append(f'Ø {p.diameter_in:g}"→{inv.diameter_in_override:g}"')
            if marks: lines.append("Intervención: " + " · ".join(marks))
        if pipe_id in self._isolated_pipes:
            lines.append("[AISLADO DE 31] Aguas arriba de un cierre al 100%")
        if ps is not None:
            t = self._snapshot.time_min
            if ps.is_closed or (inv is not None and inv.is_closed):
                lines.append(f"Estado (t={t:.0f} min): CERRADA 100% · Caudal conducido: 0.0000 m³/s")
            else:
                lines.append(f"Q {ps.flow_m3s:.4f} m³/s · Utilización {ps.utilization_pct:.1f}% ({ps.category.label})")
                lines.append(f"Demanda {ps.demand_flow_m3s:.4f} m³/s ({ps.utilization_pct / 100.0:.2f}× Qmax)"
                             + (f" · Exceso {ps.excess_flow_m3s:.4f} m³/s" if ps.excess_flow_m3s > 1e-9 else ""))
            lines.append(f"Tránsito: {ps.volume_in_transit_m3:.2f} m³")
        dur = f"0–{self._total_duration_min:.0f} min"
        if pipe_id in self._peak_util: lines.append(f"Pico máximo ({dur}): {self._peak_util[pipe_id]:.1f}%")
        if pipe_id in self._overload_min:
            ov = self._overload_min[pipe_id]
            lines.append(f"Sobrecarga total ({dur}): {ov:.0f} min >100% ({classify_overload_persistence(ov, self._total_duration_min)[2]})")
        return "\n".join(lines)
