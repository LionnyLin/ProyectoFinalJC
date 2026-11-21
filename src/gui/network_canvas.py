"""Lienzo cartográfico interactivo en 2 fases para la red de alcantarillado."""

from __future__ import annotations

import math
import tkinter as tk
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from src.data_structures import DirectedGraph
from src.simulation.models import TimeStepSnapshot
from . import theme

_DEFAULT_FONTS: Dict[str, Tuple[str, int, str]] = {
    "headline": ("TkDefaultFont", 13, "bold"), "title": ("TkDefaultFont", 10, "bold"),
    "body": ("TkDefaultFont", 9, "normal"), "label": ("TkDefaultFont", 9, "bold"),
    "mono": ("TkFixedFont", 9, "normal"), "mono_bold": ("TkFixedFont", 9, "bold"), "small": ("TkDefaultFont", 8, "normal"),
}
_NODE_TYPE_ES = {"source": "Fuente", "sink": "Sumidero (PTAR)", "manhole": "Pozo de inspección"}
_NODE_BASE_STYLE = {
    "source": (theme.NODE_SOURCE_FILL, theme.NODE_SOURCE_OUTLINE, theme.NODE_SOURCE_TEXT, 2.0),
    "sink": (theme.NODE_SINK_FILL, theme.NODE_SINK_OUTLINE, theme.NODE_SINK_TEXT, 2.2),
    "manhole": (theme.NODE_MANHOLE_FILL, theme.NODE_MANHOLE_OUTLINE, theme.NODE_MANHOLE_TEXT, 1.5),
}
_ZOOM_MIN, _ZOOM_MAX, _DRAG_PX, _RESIZE_MS = 0.55, 4.50, 4.0, 80


def _edge_id(item: object) -> str:
    return item.pipe_id if hasattr(item, "pipe_id") else str(item)


class NetworkCanvas(tk.Canvas):
    """Canvas cartográfico en 2 fases: geometría cacheada (A) y actualización O(V+E) sin borrado (B)."""

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
        self._current_node, self._active_edge = None, None
        self._traversal_mode: Optional[str] = None
        self._origin_node: Optional[str] = None
        self._banner_text: str = ""
        self._zoom, self._pan_x, self._pan_y = 1.0, 0.0, 0.0
        self._drag_start, self._drag_pan_origin = None, (0.0, 0.0)
        self._dragged, self._resize_after, self._last_size = False, None, (0, 0)

        # Registro de ítems del Canvas (Fase A) y cachés de estilo (Fase B)
        self._pipe_lines, self._pipe_labels, self._node_ovals, self._node_texts, self._node_rings = {}, {}, {}, {}, {}
        self._node_coords: Dict[str, Tuple[float, float]] = {}
        self._node_radii: Dict[str, float] = {}
        self._origin_ring: Optional[int] = None
        self._badge_items: List[int] = []
        self._item_to_entity: Dict[int, Tuple[str, str]] = {}
        self._pipe_cache, self._pipe_label_cache, self._node_cache, self._ring_cache = {}, {}, {}, {}

        # Tooltip ligero reutilizado dentro del Canvas (sin Toplevel ni flicker X11)
        self._tooltip_lbl = tk.Label(
            self, text="", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, font=self._fonts["small"],
            justify="left", anchor="w", padx=8, pady=5, bd=0, highlightthickness=1, highlightbackground=theme.ACCENT_PRIMARY,
        )
        self._hover_entity: Optional[Tuple[str, str]] = None
        self._banner_lbl = tk.Label(
            self, text="", font=self._fonts["label"], padx=10, pady=4, bd=0, highlightthickness=2,
        )

        for seq, cb in (
            ("<Configure>", self._on_configure), ("<MouseWheel>", self._on_mouse_wheel),
            ("<Button-4>", lambda e: self._zoom_at(e.x, e.y, 1.12)), ("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1.0 / 1.12)),
            ("<ButtonPress-1>", self._on_left_press), ("<B1-Motion>", self._on_left_drag),
            ("<ButtonRelease-1>", self._on_left_release), ("<Double-Button-1>", lambda _e: self.reset_view()),
            ("<Motion>", self._on_motion), ("<Leave>", lambda _e: self._hide_tooltip()), ("<Destroy>", lambda _e: self.cancel_pending()),
        ):
            self.bind(seq, cb)

    # ── API pública ──────────────────────────────────────────────────────────

    def set_graph(self, graph: DirectedGraph) -> None:
        self._graph, self._selected_kind, self._selected_id = graph, None, None
        self._hide_tooltip()
        self.rebuild_geometry()

    def set_snapshot(self, snapshot: Optional[TimeStepSnapshot]) -> None:
        self._snapshot = snapshot
        self.update_visuals()
        if self._hover_entity is not None:
            self._tooltip_lbl.configure(text=self._format_tooltip(*self._hover_entity))

    def set_selected(self, kind: Optional[str], entity_id: Optional[str]) -> None:
        self._selected_kind, self._selected_id = (kind, entity_id) if kind in ("pipe", "node") and entity_id else (None, None)
        self.update_visuals()

    def set_traversal_highlight(
        self, visited_nodes: Optional[Iterable[str]] = None, visited_edges: Optional[Iterable[object]] = None,
        path_nodes: Optional[Iterable[str]] = None, path_edges: Optional[Iterable[object]] = None,
        current_node: Optional[str] = None, active_edge: Optional[object] = None,
        mode: Optional[str] = None, origin_node: Optional[str] = None, banner_text: str = "",
    ) -> None:
        self._visited_nodes = set(visited_nodes) if visited_nodes else set()
        self._visited_edges = {_edge_id(e) for e in visited_edges} if visited_edges else set()
        self._path_nodes = set(path_nodes) if path_nodes else set()
        self._path_edges = {_edge_id(e) for e in path_edges} if path_edges else set()
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

    def reset_view(self) -> None:
        self._zoom, self._pan_x, self._pan_y = 1.0, 0.0, 0.0
        self._hide_tooltip()
        self.rebuild_geometry()

    def zoom_by(self, factor: float) -> None:
        w, h = self._canvas_dims()
        self._zoom_at(w * 0.5, h * 0.5, factor)

    def cancel_pending(self) -> None:
        if self._resize_after is not None:
            try: self.after_cancel(self._resize_after)
            except tk.TclError: pass
            self._resize_after = None

    # ── Fase A: reconstrucción geométrica ────────────────────────────────────

    def _canvas_dims(self) -> Tuple[float, float]:
        w, h = float(self.winfo_width()), float(self.winfo_height())
        return (max(w if w > 1.0 else float(self.winfo_reqwidth() or 760), 260.0),
                max(h if h > 1.0 else float(self.winfo_reqheight() or 520), 200.0))

    def _project(self, nx: float, ny: float, w: float, h: float) -> Tuple[float, float]:
        px, py = max(56.0, w * 0.068), max(44.0, h * 0.068)
        bx, by = px + nx * max(120.0, w - 2.0 * px), py + ny * max(120.0, h - 2.0 * py)
        cx, cy = w * 0.5, h * 0.5
        return cx + (bx - cx) * self._zoom + self._pan_x, cy + (by - cy) * self._zoom + self._pan_y

    def _draw_grid(self, w: float, h: float) -> None:
        step = max(22.0, 34.0 * self._zoom)
        cx, cy = w * 0.5 + self._pan_x, h * 0.5 + self._pan_y
        for i in range(math.floor(-cx / step), math.ceil((w - cx) / step) + 1):
            self.create_line(cx + i * step, 0, cx + i * step, h, fill=theme.CANVAS_GRID_MAJOR if i % 4 == 0 else theme.CANVAS_GRID_MINOR)
        for j in range(math.floor(-cy / step), math.ceil((h - cy) / step) + 1):
            self.create_line(0, cy + j * step, w, cy + j * step, fill=theme.CANVAS_GRID_MAJOR if j % 4 == 0 else theme.CANVAS_GRID_MINOR)

    def rebuild_geometry(self) -> None:
        """Fase A: crea retícula e ítems del grafo una vez y guarda sus IDs."""
        self.delete("all")
        for d in (self._pipe_lines, self._pipe_labels, self._node_ovals, self._node_texts, self._node_rings,
                  self._item_to_entity, self._pipe_cache, self._pipe_label_cache, self._node_cache, self._ring_cache):
            d.clear()
        self._node_coords.clear()
        self._node_radii.clear()
        self._origin_ring = None
        self._badge_items.clear()
        w, h = self._canvas_dims()
        self._draw_grid(w, h)
        if self._graph is None: return

        scale = min(w / 960.0, h / 640.0) * (self._zoom ** 0.55)
        r_man = max(9.0, min(18.0, 11.5 * scale))
        r_map = {"source": r_man * 1.15, "sink": r_man * 1.28, "manhole": r_man}
        nodes = self._graph.nodes()
        coords = {n.node_id: self._project(n.x, n.y, w, h) for n in nodes}
        radii = {n.node_id: r_map.get(n.node_type, r_man) for n in nodes}
        self._node_coords, self._node_radii = coords, radii
        self._origin_ring = self.create_oval(0, 0, 0, 0, fill="", outline=theme.TRAV_BFS_EDGE, width=3.6, state="hidden")
        arr = max(0.85, min(1.35, scale))
        arrowshape = (round(8 * arr, 1), round(10 * arr, 1), round(3.8 * arr, 1))
        lbl_off = max(9.0, 10.5 * min(1.35, self._zoom ** 0.35))
        pipe_font = (self._fonts["mono"][0], max(7, min(10, int(round(7.5 * (self._zoom ** 0.25))))), "normal")
        node_font = (self._fonts["label"][0], max(7, min(11, int(round(8.2 * (self._zoom ** 0.28))))), "bold")
        badge_font = (self._fonts["small"][0], max(7, min(9, int(round(7.5 * (self._zoom ** 0.2))))), "bold")

        for pipe in self._graph.pipes():
            p1, p2 = coords.get(pipe.from_node), coords.get(pipe.to_node)
            if p1 is None or p2 is None: continue
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            dist = math.hypot(dx, dy)
            if dist < 1e-3: continue
            ux, uy = dx / dist, dy / dist
            c1, c2 = min(radii[pipe.from_node] + 2.0, dist * 0.35), min(radii[pipe.to_node] + 3.0, dist * 0.40)
            sx1, sy1, sx2, sy2 = p1[0] + ux * c1, p1[1] + uy * c1, p2[0] - ux * c2, p2[1] - uy * c2
            lid = self.create_line(sx1, sy1, sx2, sy2, fill=theme.PIPE_IDLE_COLOR, width=1.8,
                                   arrow=tk.LAST, arrowshape=arrowshape, capstyle=tk.ROUND, joinstyle=tk.ROUND)
            nx_p, ny_p = -uy, ux
            if ny_p > 0.35: nx_p, ny_p = -nx_p, -ny_p
            if abs(ux) < 0.45:
                off, anchor = max(6.0, lbl_off * 0.65), ("w" if nx_p >= 0 else "e")
            else:
                off, anchor = lbl_off, "center"
            tid = self.create_text(0.5 * (sx1 + sx2) + nx_p * off, 0.5 * (sy1 + sy2) + ny_p * off,
                                   text=pipe.pipe_id, fill=theme.INK_MUTED, font=pipe_font, anchor=anchor)
            self._pipe_lines[pipe.pipe_id], self._pipe_labels[pipe.pipe_id] = lid, tid
            self._item_to_entity[lid] = self._item_to_entity[tid] = ("pipe", pipe.pipe_id)

        for node in nodes:
            x, y = coords[node.node_id]
            r, rr = radii[node.node_id], radii[node.node_id] + 4.5
            self._node_rings[node.node_id] = self.create_oval(
                x - rr, y - rr, x + rr, y + rr, fill="", outline=theme.OVERLOAD_RING_COLOR, width=2.4, state="hidden")
            oid = self.create_oval(x - r, y - r, x + r, y + r, fill=theme.NODE_MANHOLE_FILL, outline=theme.NODE_MANHOLE_OUTLINE, width=1.5)
            tid = self.create_text(x, y, text=node.node_id, fill=theme.NODE_MANHOLE_TEXT, font=node_font)
            self._node_ovals[node.node_id], self._node_texts[node.node_id] = oid, tid
            self._item_to_entity[oid] = self._item_to_entity[tid] = ("node", node.node_id)
            if node.node_type == "source":
                by = y + r + 11.0 if node.y > 0.5 else y - r - 11.0
                self._badge_items.extend((
                    self.create_rectangle(x - 22.0, by - 7.5, x + 22.0, by + 7.5, fill=theme.DOCK_BG, outline=theme.DOCK_BORDER),
                    self.create_text(x, by, text="Fuente", fill=theme.INK_PRIMARY, font=badge_font),
                ))
            elif node.node_type == "sink":
                label = f"PTAR Punta Canoa · {node.node_id}"
                bx, by, pw, ph = max(8.0, x - r), y + r + 9.0, max(124.0, len(label) * 5.8 + 12.0), 16.0
                self._badge_items.extend((
                    self.create_rectangle(bx, by, bx + pw, by + ph, fill=theme.NODE_SINK_FILL, outline=theme.NODE_SINK_OUTLINE),
                    self.create_text(bx + pw * 0.5, by + ph * 0.5, text=label, fill=theme.NODE_SINK_TEXT, font=badge_font),
                ))
        self.update_visuals(force=True)

    # ── Fase B: actualización visual incremental (< 2 ms) ────────────────────

    def update_visuals(self, force: bool = False) -> None:
        """Fase B: actualiza estilos solo en ítems modificados (sin delete ni bbox)."""
        if self._graph is None or not self._pipe_lines: return
        pstates = self._snapshot.pipe_states if self._snapshot else None
        nstates = self._snapshot.node_states if self._snapshot else None
        sel_k, sel_id = self._selected_kind, self._selected_id

        has_trav = bool(
            self._traversal_mode or self._visited_nodes or self._visited_edges
            or self._path_nodes or self._path_edges or self._current_node or self._origin_node
        )
        mode = self._traversal_mode
        if mode == "downstream":
            edge_col, node_fill, node_out, path_col, edge_dash = (
                theme.TRAV_DOWNSTREAM_EDGE, theme.TRAV_DOWNSTREAM_NODE, theme.TRAV_DOWNSTREAM_OUTLINE,
                theme.TRAV_DOWNSTREAM_EDGE, (),
            )
            b_bg, b_fg, b_bd = "#E0F2FE", "#0369A1", theme.TRAV_DOWNSTREAM_EDGE
        elif mode == "upstream":
            edge_col, node_fill, node_out, path_col, edge_dash = (
                theme.TRAV_UPSTREAM_EDGE, theme.TRAV_UPSTREAM_NODE, theme.TRAV_UPSTREAM_OUTLINE,
                theme.TRAV_UPSTREAM_EDGE, (8, 4),
            )
            b_bg, b_fg, b_bd = "#F3E8FF", "#5B21B6", theme.TRAV_UPSTREAM_EDGE
        elif mode == "dfs":
            edge_col, node_fill, node_out, path_col, edge_dash = (
                theme.TRAV_DFS_EDGE, theme.TRAV_DFS_NODE, theme.TRAV_DFS_OUTLINE,
                theme.TRAV_DFS_PATH, (6, 3),
            )
            b_bg, b_fg, b_bd = "#E0E7FF", "#3730A3", theme.TRAV_DFS_EDGE
        else:
            edge_col, node_fill, node_out, path_col, edge_dash = (
                theme.TRAV_BFS_EDGE, theme.TRAV_BFS_NODE, theme.TRAV_BFS_OUTLINE,
                theme.TRAV_BFS_PATH, (6, 3),
            )
            b_bg, b_fg, b_bd = "#CCFBF1", "#0F766E", theme.TRAV_BFS_EDGE

        for pid, lid in self._pipe_lines.items():
            ps = pstates.get(pid) if pstates else None
            is_active = pid == self._active_edge
            is_path = pid in self._path_edges
            is_visited = pid in self._visited_edges
            if has_trav:
                if is_active:
                    color, width, dash = theme.TRAV_ACTIVE_COLOR, 4.6, ()
                elif is_path:
                    color, width, dash = path_col, 4.2, ()
                elif is_visited:
                    color, width, dash = edge_col, 3.5, edge_dash
                else:
                    color, width, dash = theme.TRAV_DIM_PIPE, 1.2, ()
            else:
                color = ps.category.color_hex if ps else theme.PIPE_IDLE_COLOR
                width = (3.2 if ps.utilization_pct > 100.0 else (2.6 if ps.utilization_pct > 75.0 else 2.0)) if ps else 1.8
                dash = ()
            if sel_k == "pipe" and sel_id == pid:
                color, width, dash = theme.SELECTED_HALO, max(width, 4.4), ()
            spec = (color, width, dash)
            if force or self._pipe_cache.get(pid) != spec:
                self.itemconfigure(lid, fill=color, width=width, dash=dash)
                self._pipe_cache[pid] = spec

            lbl_id = self._pipe_labels.get(pid)
            if lbl_id is not None:
                ut = f"{ps.utilization_pct:.0f}%" if (self._show_util_labels and ps) else ""
                lt = f"{pid} · {ut}" if (self._show_pipe_labels and ut) else (pid if self._show_pipe_labels else ut)
                if sel_k == "pipe" and sel_id == pid:
                    lf = theme.SELECTED_HALO
                elif has_trav and not (is_active or is_path or is_visited):
                    lf = theme.TRAV_DIM_TEXT
                else:
                    lf = theme.TIER_TEXT_ON_LIGHT.get(ps.category.color_hex.lower(), theme.INK_PRIMARY) if ps else theme.INK_MUTED
                lspec = (lt, lf, "normal" if lt else "hidden")
                if force or self._pipe_label_cache.get(pid) != lspec:
                    self.itemconfigure(lbl_id, text=lt, fill=lf, state=lspec[2])
                    self._pipe_label_cache[pid] = lspec

        for node in self._graph.nodes():
            nid, oid = node.node_id, self._node_ovals.get(node.node_id)
            if oid is None: continue
            fill, out, tfill, w = _NODE_BASE_STYLE.get(node.node_type, _NODE_BASE_STYLE["manhole"])
            is_man = node.node_type == "manhole"
            if has_trav:
                if nid == self._current_node:
                    out, w = theme.TRAV_ACTIVE_COLOR, 3.8
                    if is_man: fill, tfill = theme.TRAV_ACTIVE_COLOR, "#FFFFFF"
                elif nid in self._path_nodes:
                    out, w = path_col, 3.2
                    if is_man: fill, tfill = node_fill, theme.INK_PRIMARY
                elif nid in self._visited_nodes:
                    out, w = node_out, (2.8 if is_man else 3.4)
                    if is_man: fill, tfill = node_fill, theme.INK_PRIMARY
                else:
                    if is_man:
                        fill, out, w, tfill = theme.TRAV_DIM_NODE, theme.TRAV_DIM_OUTLINE, 1.1, theme.TRAV_DIM_TEXT
                    else:
                        out = theme.TRAV_DIM_OUTLINE
            if sel_k == "node" and sel_id == nid:
                out, w = theme.SELECTED_HALO, 3.6
            nspec = (fill, out, w, tfill)
            if force or self._node_cache.get(nid) != nspec:
                self.itemconfigure(oid, fill=fill, outline=out, width=w)
                self.itemconfigure(self._node_texts[nid], fill=tfill)
                self._node_cache[nid] = nspec

            rid = self._node_rings.get(nid)
            if rid is not None:
                ns = nstates.get(nid) if nstates else None
                rspec = (("normal", theme.OVERLOAD_RING_SEVERE, 3.0)
                         if (ns and (ns.surface_flooding_m3 > 1e-9 or ns.flooding_rate_m3s > 1e-9))
                         else (("normal", theme.OVERLOAD_RING_COLOR, 2.4) if (ns and ns.stored_volume_m3 > 1e-9)
                               else ("hidden", theme.OVERLOAD_RING_COLOR, 2.4)))
                if force or self._ring_cache.get(nid) != rspec:
                    self.itemconfigure(rid, state=rspec[0], outline=rspec[1], width=rspec[2])
                    self._ring_cache[nid] = rspec

        if self._origin_ring is not None:
            if has_trav and self._origin_node and self._origin_node in self._node_coords:
                ox, oy = self._node_coords[self._origin_node]
                orr = self._node_radii[self._origin_node] + 6.5
                self.coords(self._origin_ring, ox - orr, oy - orr, ox + orr, oy + orr)
                self.itemconfigure(self._origin_ring, outline=edge_col, width=3.6, state="normal")
            else:
                self.itemconfigure(self._origin_ring, state="hidden")

        if has_trav and self._banner_text:
            self._banner_lbl.configure(text=self._banner_text, bg=b_bg, fg=b_fg, highlightbackground=b_bd)
            self._banner_lbl.place(x=10, y=10)
        else:
            self._banner_lbl.place_forget()

    # ── Interacción: zoom, pan, selección, resize y tooltip ──────────────────

    def _on_configure(self, e: tk.Event) -> None:
        size = (int(e.width), int(e.height))
        if size != self._last_size:
            self._last_size = size
            self.cancel_pending()
            self._resize_after = self.after(_RESIZE_MS, self._on_resize_debounced)

    def _on_resize_debounced(self) -> None:
        self._resize_after = None
        self.rebuild_geometry()

    def _on_mouse_wheel(self, e: tk.Event) -> None:
        if getattr(e, "delta", 0): self._zoom_at(e.x, e.y, 1.12 if e.delta > 0 else 1.0 / 1.12)

    def _zoom_at(self, mx: float, my: float, factor: float) -> None:
        nz = max(_ZOOM_MIN, min(_ZOOM_MAX, self._zoom * factor))
        if abs(nz - self._zoom) < 1e-4: return
        w, h = self._canvas_dims()
        cx, cy, r = w * 0.5, h * 0.5, nz / self._zoom
        self._pan_x, self._pan_y, self._zoom = (mx - cx) - (mx - cx - self._pan_x) * r, (my - cy) - (my - cy - self._pan_y) * r, nz
        self._hide_tooltip()
        self.rebuild_geometry()

    def _on_left_press(self, e: tk.Event) -> None:
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
            if ent is None: continue
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
        if self._graph is None: return ""
        if kind == "pipe":
            p = self._graph.get_pipe(entity_id)
            if p is None: return entity_id
            lines = [f"Tubería {p.pipe_id} ({p.from_node} → {p.to_node})",
                     f'Ø {p.diameter_in:g}" · L {p.length_m:.0f} m · Qmax {p.q_max_m3s:.4f} m³/s']
            if self._snapshot and entity_id in self._snapshot.pipe_states:
                ps = self._snapshot.pipe_states[entity_id]
                lines.append(f"Q {ps.flow_m3s:.4f} m³/s · O {ps.utilization_pct:.1f}% ({ps.category.label})")
            return "\n".join(lines)
        n = self._graph.get_node(entity_id)
        if n is None: return entity_id
        lines = [f"Nodo {n.node_id} · {_NODE_TYPE_ES.get(n.node_type, n.node_type)}"]
        if self._snapshot and entity_id in self._snapshot.node_states:
            ns = self._snapshot.node_states[entity_id]
            lines.append(f"Ent. {ns.inflow_m3s:.4f} · Sal. {ns.outflow_m3s:.4f} m³/s")
            if ns.stored_volume_m3 > 1e-9 or ns.surface_flooding_m3 > 1e-9:
                lines.append(f"Almac. {ns.stored_volume_m3:.2f} m³ · Rebose {ns.surface_flooding_m3:.2f} m³")
        return "\n".join(lines)
