"""Lienzo cartográfico interactivo para el grafo dirigido de la red de alcantarillado."""

import math
import tkinter as tk
from typing import Callable, Dict, Optional, Set, Tuple

from src.data_structures import DirectedGraph, ManholeNode, PipeEdge
from src.simulation.models import TimeStepSnapshot
from . import theme


class NetworkCanvas(tk.Canvas):
    """Canvas interactivo con retícula técnica, zoom/paneo, controles flotantes y tooltips."""

    def __init__(
        self,
        master: tk.Misc,
        ui_font: str = "Segoe UI",
        mono_font: str = "Consolas",
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

    def _on_configure(self, event: tk.Event) -> None:
        if event.width >= 580 and event.height >= 400:
            self._stamp_lbl.place(relx=0.0, rely=0.0, x=12, y=12, anchor="nw")
        else:
            self._stamp_lbl.place_forget()

        if event.width >= 520 and event.height >= 400:
            self._hint_bar.place(relx=0.0, rely=1.0, x=12, y=-12, anchor="sw")
        else:
            self._hint_bar.place_forget()

        if self._resize_after is not None:
            self.after_cancel(self._resize_after)
        self._resize_after = self.after(20, self._handle_deferred_resize)

    def _handle_deferred_resize(self) -> None:
        self._resize_after = None
        self.redraw()

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

    def zoom_in(self) -> None:
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        self._zoom_at(w / 2.0, h / 2.0, 1.18)

    def zoom_out(self) -> None:
        w = max(200, self.winfo_width())
        h = max(200, self.winfo_height())
        self._zoom_at(w / 2.0, h / 2.0, 1.0 / 1.18)

    def reset_view(self) -> None:
        self._zoom = 1.0
        self._pan_x = 0.0
        self._pan_y = 0.0
        self._update_zoom_label()
        self.redraw()

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
        self.redraw()

    def _update_zoom_label(self) -> None:
        self._lbl_zoom.configure(text=f"{int(round(self._zoom * 100))}%")

    def _compute_padding(self, w: int, h: int) -> Tuple[float, float]:
        pad_x = max(28.0, min(62.0, w * 0.08))
        pad_y = max(32.0, min(58.0, h * 0.11))
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
        self._update_zoom_label()
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
            self._hide_tooltip()
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
        if self.snapshot and node.node_id in self.snapshot.node_states:
            st = self.snapshot.node_states[node.node_id]
            lines.append(f"Entrada: {st.inflow_m3s:.4f} m³/s  |  Salida: {st.outflow_m3s:.4f} m³/s")
            if st.stored_volume_m3 > 1e-4:
                lines.append(f"Almacenamiento por sobrecarga: {st.stored_volume_m3:.2f} m³")
        return "\n".join(lines)

    def _build_pipe_tooltip(self, pipe: PipeEdge) -> str:
        lines = [
            f"Tubería {pipe.pipe_id}: {pipe.from_node} → {pipe.to_node}",
            f"Ø {pipe.diameter_in:.0f}\" ({pipe.diameter_m:.4f} m)  ·  L = {pipe.length_m:.1f} m  ·  Qmax = {pipe.q_max_m3s:.4f} m³/s",
        ]
        if self.snapshot and pipe.pipe_id in self.snapshot.pipe_states:
            ps = self.snapshot.pipe_states[pipe.pipe_id]
            lines.append(
                f"Caudal: {ps.flow_m3s:.4f} m³/s  ·  Utilización: {ps.utilization_pct:.1f}% ({ps.category.label})"
            )
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
        if self._tooltip_window is not None:
            self._tooltip_window.destroy()
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

    def redraw(self) -> None:
        self.delete("all")
        self._item_to_pipe.clear()
        self._item_to_node.clear()
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
        scale_factor = max(0.72, min(1.15, min_dim / 560.0))

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

        base_radius = 11.0 * scale_factor * math.sqrt(self._zoom)
        max_safe_r = max(5.2, min_edge_dist * 0.27) if min_edge_dist < 900.0 else 16.0
        node_radius = max(5.2, min(16.0, base_radius, max_safe_r))
        dense_mode = (w < 500 or self._zoom < 0.78)

        label_queue = []

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

            color = theme.PIPE_IDLE_COLOR
            util_pct = 0.0
            is_overloaded = False
            is_critical = False
            if self.snapshot and pipe.pipe_id in self.snapshot.pipe_states:
                ps = self.snapshot.pipe_states[pipe.pipe_id]
                color = "#991b1b" if ps.category.is_overloaded else ps.category.color_hex
                util_pct = ps.utilization_pct
                is_overloaded = ps.category.is_overloaded
                is_critical = util_pct >= 75.0

            base_width = 2.0 + (pipe.diameter_in - 8.0) * 0.24
            width = base_width * min(1.45, max(0.78, math.sqrt(self._zoom) * scale_factor))

            if is_overloaded:
                width += 1.5
                glow_id = self.create_line(
                    sx1, sy1, sx2, sy2,
                    fill=theme.PIPE_OVERLOAD_HALO,
                    width=width + 4.0,
                    capstyle=tk.ROUND,
                )
                self._item_to_pipe[glow_id] = pipe.pipe_id

            is_selected = pipe.pipe_id == self.selected_pipe_id
            is_highlighted = pipe.pipe_id in self.highlight_pipe_ids
            if is_selected or is_highlighted:
                halo_color = theme.PIPE_SELECTED_HALO if is_selected else theme.PIPE_HIGHLIGHT_HALO
                halo_width = width + (6.0 if is_selected else 7.5)
                halo_id = self.create_line(
                    sx1, sy1, sx2, sy2,
                    fill=halo_color,
                    width=halo_width,
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
                arrowshape=(8, 10, 3.8),
                capstyle=tk.ROUND,
            )
            self._item_to_pipe[line_id] = pipe.pipe_id

            if (self.show_pipe_labels or self.show_util_labels) and dist > 26:
                show_this = (not dense_mode) or is_selected or is_highlighted or is_critical
                if show_this:
                    parts = []
                    if self.show_pipe_labels:
                        parts.append(pipe.pipe_id)
                    if self.show_util_labels and self.snapshot is not None:
                        if not dense_mode or is_selected or is_critical:
                            parts.append(f"{util_pct:.0f}%")
                    if parts:
                        mx, my = (sx1 + sx2) / 2.0, (sy1 + sy2) / 2.0
                        nx_perp, ny_perp = -uy, ux
                        is_vert = abs(ux) < 0.35
                        if is_vert:
                            side = -1.0 if mx > w * 0.72 else 1.0
                            lx = mx + side * 26.0
                            ly = my
                        else:
                            side = 1.0
                            lx = mx + nx_perp * 13.0
                            ly = my + ny_perp * 13.0
                        priority = (
                            (4 if is_selected else 0)
                            + (3 if is_highlighted else 0)
                            + (2 if is_overloaded else 0)
                            + (1 if is_critical else 0)
                        )
                        label_queue.append(
                            (priority, util_pct, pipe.pipe_id, lx, ly, mx, is_vert, side, " ".join(parts), is_selected, is_overloaded, is_highlighted)
                        )

        # Cajas ocupadas por nodos y sus etiquetas fijas (PTAR / Fuente) para evitar colisiones
        placed_boxes = [
            (nx - node_radius - 2, ny - node_radius - 2, nx + node_radius + 2, ny + node_radius + 2)
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

        # Ordenar por prioridad: seleccionada > resaltada > sobrecargada > crítica > mayor %
        label_queue.sort(key=lambda item: (item[0], item[1]), reverse=True)

        for priority, _u, pid, lx, ly, mx, is_vert, side, text_lbl, is_sel, is_over, is_hl in label_queue:
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
                if is_sel
                else ("#FCA5A5" if is_over else (theme.PIPE_HIGHLIGHT_PATH if is_hl else theme.PAPER_BORDER))
            )
            font_spec = (
                self.mono_font,
                7 if (self._zoom < 1.15 or dense_mode) else 8,
                "bold" if (is_over or is_sel or is_hl) else "normal",
            )
            txt_id = self.create_text(lx, ly, text=text_lbl, fill=fg, font=font_spec)
            bbox = self.bbox(txt_id)
            if bbox is None:
                self.delete(txt_id)
                continue
            if is_vert:
                # Garantiza que las etiquetas de tramos verticales nunca pisen el eje de la tubería
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
            # Evitar superposición con nodos o etiquetas ya colocadas (si no es seleccionada)
            overlaps = any(
                not (bx1 < ox0 or bx0 > ox1 or by1 < oy0 or by0 > oy1)
                for ox0, oy0, ox1, oy1 in placed_boxes
            )
            if overlaps and not is_sel:
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

        # 2. Vértices (alcantarillas fuente, pozos de inspección, sumidero PTAR)
        for node in self.graph.nodes():
            x, y = positions[node.node_id]
            r = node_radius
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

            stored_vol = 0.0
            if self.snapshot and node.node_id in self.snapshot.node_states:
                stored_vol = self.snapshot.node_states[node.node_id].stored_volume_m3

            if stored_vol > 1e-3:
                ring_id = self.create_oval(
                    x - r - 4.5, y - r - 4.5, x + r + 4.5, y + r + 4.5,
                    outline=theme.NODE_SURCHARGE_RING,
                    width=2.2,
                    dash=(3, 2),
                )
                self._item_to_node[ring_id] = node.node_id

            if node.node_id == self.selected_node_id or node.node_id in self.highlight_node_ids:
                sel_col = (
                    theme.ACCENT_PRIMARY
                    if node.node_id == self.selected_node_id
                    else theme.PIPE_HIGHLIGHT_PATH
                )
                ring2 = self.create_oval(
                    x - r - 3.5, y - r - 3.5, x + r + 3.5, y + r + 3.5,
                    outline=sel_col,
                    width=2.6,
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
                fill=txt_fill,
                font=(self.ui_font, 7 if dense_mode else (8 if self._zoom < 1.2 else 9), "bold"),
            )
            self._item_to_node[txt_id] = node.node_id

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
            elif node.node_type == "source" and not dense_mode:
                tag_y = (y - r - 12) if node.y < 0.2 else (y + r + 12)
                src_tag = self.create_text(
                    x,
                    tag_y,
                    text="Fuente",
                    fill=theme.INK_PRIMARY,
                    font=(self.ui_font, 7, "bold"),
                )
                sb = self.bbox(src_tag)
                if sb is not None:
                    sbg = self.create_rectangle(
                        sb[0] - 4, sb[1] - 1, sb[2] + 4, sb[3] + 1,
                        fill=theme.DOCK_BG,
                        outline=theme.INK_PRIMARY,
                        width=1,
                    )
                    self.tag_lower(sbg, src_tag)
                    self._item_to_node[sbg] = node.node_id
                self._item_to_node[src_tag] = node.node_id
