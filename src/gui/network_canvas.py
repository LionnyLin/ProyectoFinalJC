"""Lienzo interactivo para visualizar el grafo dirigido de la red de alcantarillado."""

import math
import tkinter as tk
from typing import Callable, Dict, List, Optional, Set, Tuple

from src.data_structures import DirectedGraph, ManholeNode, PipeEdge
from src.simulation.models import TimeStepSnapshot
from . import theme


class NetworkCanvas(tk.Canvas):
    """Canvas interactivo con zoom, paneo, tooltips y renderizado por escala de colores."""

    def __init__(
        self,
        master: tk.Misc,
        on_select_pipe: Optional[Callable[[str], None]] = None,
        on_select_node: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(
            master,
            bg=theme.BG_CANVAS,
            highlightthickness=1,
            highlightbackground=theme.BORDER_COLOR,
            **kwargs,
        )
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

        # Transformación de vista (zoom y paneo)
        self._zoom: float = 1.0
        self._pan_x: float = 0.0
        self._pan_y: float = 0.0
        self._drag_start: Optional[Tuple[int, int]] = None
        self._dragged: bool = False

        # Mapeos inversos de IDs de canvas a IDs del grafo
        self._item_to_pipe: Dict[int, str] = {}
        self._item_to_node: Dict[int, str] = {}
        self._tooltip_window: Optional[tk.Toplevel] = None
        self._last_hover_key: Optional[str] = None

        self.bind("<Configure>", lambda _e: self.redraw())
        self.bind("<MouseWheel>", self._on_mouse_wheel)
        self.bind("<Button-4>", lambda e: self._zoom_at(e.x, e.y, 1.12))
        self.bind("<Button-5>", lambda e: self._zoom_at(e.x, e.y, 1 / 1.12))
        self.bind("<ButtonPress-1>", self._on_left_press)
        self.bind("<B1-Motion>", self._on_left_drag)
        self.bind("<ButtonRelease-1>", self._on_left_release)
        self.bind("<Motion>", self._on_mouse_move)
        self.bind("<Leave>", lambda _e: self._hide_tooltip())

    def set_graph(self, graph: DirectedGraph) -> None:
        self.graph = graph
        self.snapshot = None
        self.selected_pipe_id = None
        self.selected_node_id = None
        self.highlight_pipe_ids.clear()
        self.highlight_node_ids.clear()
        self.reset_view()

    def set_snapshot(self, snapshot: Optional[TimeStepSnapshot]) -> None:
        self.snapshot = snapshot
        self.redraw()

    def set_highlights(
        self,
        pipe_ids: Optional[Set[str]] = None,
        node_ids: Optional[Set[str]] = None,
    ) -> None:
        self.highlight_pipe_ids = set(pipe_ids or ())
        self.highlight_node_ids = set(node_ids or ())
        self.redraw()

    def select_pipe(self, pipe_id: Optional[str]) -> None:
        self.selected_pipe_id = pipe_id
        self.selected_node_id = None
        self.redraw()

    def select_node(self, node_id: Optional[str]) -> None:
        self.selected_node_id = node_id
        self.selected_pipe_id = None
        self.redraw()

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self.redraw()

    def _world_to_screen(self, nx: float, ny: float) -> Tuple[float, float]:
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        pad_x = 56.0
        pad_y = 46.0
        base_x = pad_x + nx * (w - 2 * pad_x)
        base_y = pad_y + ny * (h - 2 * pad_y)
        cx, cy = w / 2.0, h / 2.0
        sx = cx + (base_x - cx) * self._zoom + self._pan_x
        sy = cy + (base_y - cy) * self._zoom + self._pan_y
        return sx, sy

    def _on_mouse_wheel(self, event: tk.Event) -> None:
        factor = 1.12 if event.delta > 0 else 1.0 / 1.12
        self._zoom_at(event.x, event.y, factor)

    def _zoom_at(self, mx: float, my: float, factor: float) -> None:
        new_zoom = max(0.55, min(4.5, self._zoom * factor))
        if abs(new_zoom - self._zoom) < 1e-6:
            return
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        cx, cy = w / 2.0, h / 2.0
        scale_ratio = new_zoom / self._zoom
        self._pan_x = (mx - cx) - scale_ratio * (mx - cx - self._pan_x)
        self._pan_y = (my - cy) - scale_ratio * (my - cy - self._pan_y)
        self._zoom = new_zoom
        self.redraw()

    def _on_left_press(self, event: tk.Event) -> None:
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
            self.redraw()

    def _on_left_release(self, event: tk.Event) -> None:
        was_dragged = self._dragged
        self._drag_start = None
        self._dragged = False
        if was_dragged:
            return

        # Detección de clic en nodo o tubería
        clicked = self.find_overlapping(
            event.x - 5, event.y - 5, event.x + 5, event.y + 5
        )
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

    def _on_mouse_move(self, event: tk.Event) -> None:
        if self.graph is None or self._drag_start is not None:
            return
        items = self.find_overlapping(
            event.x - 4, event.y - 4, event.x + 4, event.y + 4
        )
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
        lines = [f"Nodo {node.node_id} — {role}"]
        if self.snapshot and node.node_id in self.snapshot.node_states:
            st = self.snapshot.node_states[node.node_id]
            lines.append(f"Entrada: {st.inflow_m3s:.4f} m³/s | Salida: {st.outflow_m3s:.4f} m³/s")
            if st.stored_volume_m3 > 1e-4:
                lines.append(f"Almacenamiento por sobrecarga: {st.stored_volume_m3:.2f} m³")
        return "\n".join(lines)

    def _build_pipe_tooltip(self, pipe: PipeEdge) -> str:
        lines = [
            f"Tubería {pipe.pipe_id}: {pipe.from_node} → {pipe.to_node}",
            f"Ø {pipe.diameter_in:.0f}\" ({pipe.diameter_m:.4f} m) | L = {pipe.length_m:.1f} m | Qmax = {pipe.q_max_m3s:.4f} m³/s",
        ]
        if self.snapshot and pipe.pipe_id in self.snapshot.pipe_states:
            ps = self.snapshot.pipe_states[pipe.pipe_id]
            lines.append(
                f"Caudal: {ps.flow_m3s:.4f} m³/s | Utilización: {ps.utilization_pct:.1f}% ({ps.category.label})"
            )
        return "\n".join(lines)

    def _show_tooltip(self, x_root: int, y_root: int, text: str) -> None:
        self._hide_tooltip()
        tw = tk.Toplevel(self)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x_root}+{y_root}")
        lbl = tk.Label(
            tw,
            text=text,
            justify="left",
            background="#0f172a",
            foreground="#f8fafc",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=5,
            font=("Segoe UI", 9),
        )
        lbl.pack()
        self._tooltip_window = tw

    def _hide_tooltip(self) -> None:
        if self._tooltip_window is not None:
            self._tooltip_window.destroy()
            self._tooltip_window = None

    def redraw(self) -> None:
        self.delete("all")
        self._item_to_pipe.clear()
        self._item_to_node.clear()

        if self.graph is None:
            return

        node_radius = max(9.0, min(18.0, 12.0 * math.sqrt(self._zoom)))
        positions: Dict[str, Tuple[float, float]] = {}
        for node in self.graph.nodes():
            positions[node.node_id] = self._world_to_screen(node.x, node.y)

        # 1. Dibujar tuberías (aristas dirigidas)
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

            sx1 = x1 + ux * (node_radius + 1)
            sy1 = y1 + uy * (node_radius + 1)
            sx2 = x2 - ux * (node_radius + 3)
            sy2 = y2 - uy * (node_radius + 3)

            color = theme.PIPE_IDLE_COLOR
            util_pct = 0.0
            is_overloaded = False
            if self.snapshot and pipe.pipe_id in self.snapshot.pipe_states:
                ps = self.snapshot.pipe_states[pipe.pipe_id]
                color = ps.category.color_hex
                util_pct = ps.utilization_pct
                is_overloaded = ps.category.is_overloaded

            base_width = 2.0 + (pipe.diameter_in - 8.0) * 0.25
            width = base_width * min(1.5, max(0.85, math.sqrt(self._zoom)))
            if is_overloaded:
                width += 1.8

            is_selected = pipe.pipe_id == self.selected_pipe_id
            is_highlighted = pipe.pipe_id in self.highlight_pipe_ids

            # Halo de selección o recorrido BFS/DFS
            if is_selected or is_highlighted:
                halo_color = (
                    theme.PIPE_SELECTED_HALO if is_selected else theme.PIPE_HIGHLIGHT_PATH
                )
                halo_id = self.create_line(
                    sx1, sy1, sx2, sy2,
                    fill=halo_color,
                    width=width + 5.0,
                    capstyle=tk.ROUND,
                )
                self._item_to_pipe[halo_id] = pipe.pipe_id

            line_id = self.create_line(
                sx1,
                sy1,
                sx2,
                sy2,
                fill=color,
                width=width,
                arrow=tk.LAST,
                arrowshape=(9, 11, 4),
                capstyle=tk.ROUND,
            )
            self._item_to_pipe[line_id] = pipe.pipe_id

            # Etiqueta de tubería / % de utilización
            if self.show_pipe_labels or self.show_util_labels:
                mx, my = (sx1 + sx2) / 2.0, (sy1 + sy2) / 2.0
                # Desplazar ligeramente perpendicular para no tapar la línea
                nx_perp, ny_perp = -uy, ux
                lx = mx + nx_perp * 9.0
                ly = my + ny_perp * 9.0
                parts = []
                if self.show_pipe_labels:
                    parts.append(pipe.pipe_id)
                if self.show_util_labels and self.snapshot is not None:
                    parts.append(f"{util_pct:.0f}%")
                if parts:
                    lbl_id = self.create_text(
                        lx,
                        ly,
                        text=" ".join(parts),
                        fill="#e2e8f0" if is_overloaded or is_selected else "#94a3b8",
                        font=("Segoe UI", 7 if self._zoom < 1.2 else 8, "bold" if is_overloaded else "normal"),
                    )
                    self._item_to_pipe[lbl_id] = pipe.pipe_id

        # 2. Dibujar vértices (alcantarillas, pozos, sumidero PTAR)
        for node in self.graph.nodes():
            x, y = positions[node.node_id]
            r = node_radius
            if node.node_type == "sink":
                r += 3.5
                fill = theme.NODE_SINK_FILL
                outline = theme.NODE_SINK_BORDER
            elif node.node_type == "source":
                fill = theme.NODE_SOURCE_FILL
                outline = theme.NODE_SOURCE_BORDER
            else:
                fill = theme.NODE_MANHOLE_FILL
                outline = theme.NODE_MANHOLE_BORDER

            # Indicador de sobrecarga almacenada en el pozo
            stored_vol = 0.0
            if self.snapshot and node.node_id in self.snapshot.node_states:
                stored_vol = self.snapshot.node_states[node.node_id].stored_volume_m3

            if stored_vol > 1e-3:
                ring_id = self.create_oval(
                    x - r - 4, y - r - 4, x + r + 4, y + r + 4,
                    outline=theme.NODE_SURCHARGE_RING,
                    width=2.2,
                    dash=(3, 2),
                )
                self._item_to_node[ring_id] = node.node_id

            if node.node_id == self.selected_node_id or node.node_id in self.highlight_node_ids:
                sel_col = (
                    theme.PIPE_SELECTED_HALO
                    if node.node_id == self.selected_node_id
                    else theme.PIPE_HIGHLIGHT_PATH
                )
                ring2 = self.create_oval(
                    x - r - 3, y - r - 3, x + r + 3, y + r + 3,
                    outline=sel_col,
                    width=2.5,
                )
                self._item_to_node[ring2] = node.node_id

            oval_id = self.create_oval(
                x - r, y - r, x + r, y + r,
                fill=fill,
                outline=outline,
                width=2.0,
            )
            self._item_to_node[oval_id] = node.node_id

            txt_id = self.create_text(
                x,
                y,
                text=node.node_id,
                fill="#ffffff",
                font=("Segoe UI", 8 if self._zoom < 1.2 else 9, "bold"),
            )
            self._item_to_node[txt_id] = node.node_id

            if node.node_type == "sink":
                ptar_id = self.create_text(
                    x,
                    y + r + 11,
                    text="PTAR Punta Canoa",
                    fill=theme.NODE_SINK_BORDER,
                    font=("Segoe UI", 8, "bold"),
                )
                self._item_to_node[ptar_id] = node.node_id
            elif node.node_type == "source":
                src_tag = self.create_text(
                    x,
                    y + r + 9,
                    text="(S)",
                    fill=theme.NODE_SOURCE_BORDER,
                    font=("Segoe UI", 7, "bold"),
                )
                self._item_to_node[src_tag] = node.node_id
