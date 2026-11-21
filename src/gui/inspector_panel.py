"""Pestañas del panel derecho: Inspector de entidad y Ranking de tuberías críticas."""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from src.algorithms.analysis import classify_utilization, rank_critical_pipes
from src.algorithms.queries import get_node_details, get_pipe_details
from src.data_structures import DirectedGraph
from src.simulation.models import SimulationResult, TimeStepSnapshot
from . import theme

_EMPTY_MSG = "Haz clic en una tubería o pozo del plano, o usa el buscador O(1)."
_NODE_LABELS = {"source": "Alcantarilla Fuente", "sink": "PTAR Punta Canoa", "manhole": "Pozo"}
_FILTER_MODES = ("Todas", "Críticas (>75–100%)", "Sobrecargadas (>100%)", "En alerta (>75%)")
_TIER_NAMES = tuple(label for _, _, label in theme.COLOR_SCALE_LEGEND)
_SUM_KEYS = (
    "Escenario", "Intensidad", "Q total entrada", "PTAR 31 pico / acum.",
    "Almacenamiento pozos", "Rebose total", "Críticas (>75–100%)", "Sobrecargadas (>100%)", "Err. masa / Cómputo",
)
_COLS = (("#", 28, "e", False), ("ID", 44, "center", False), ("Tramo", 62, "center", True), ("Q (m³/s)", 66, "e", False), ("Qmax", 58, "e", False), ("Util. %", 56, "e", False), ("Estado", 86, "w", True))


def _fmt_edges(edges: List) -> str:
    return "Ninguna" if not edges else (", ".join(e.pipe_id for e in edges[:4]) + (f" (+{len(edges) - 4})" if len(edges) > 4 else ""))


class InspectorTab(tk.Frame):
    """Ficha de entidad seleccionada (tubería/pozo) y resumen global hasta PTAR 31."""

    def __init__(self, parent: tk.Misc, fonts: Dict[str, Tuple[str, int, str]]) -> None:
        super().__init__(parent, bg=theme.PAPER_BG)
        self._fonts = fonts
        self._canvas = tk.Canvas(self, bg=theme.PAPER_BG, highlightthickness=0, bd=0, takefocus=False)
        self._vscroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vscroll.set)
        self._vscroll.pack(side=tk.RIGHT, fill=tk.Y); self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._inner = tk.Frame(self._canvas, bg=theme.PAPER_BG)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>", lambda _e: self.after_idle(self._sync_scroll))
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._wheel_active = False
        self._needs_scroll = False
        self._canvas.bind("<Enter>", lambda _e: self._toggle_wheel(True))
        self._canvas.bind("<Leave>", lambda _e: self._toggle_wheel(False))
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._canvas.bind(seq, self._on_wheel)

        self._header("ENTIDAD SELECCIONADA")
        hdr = tk.Frame(self._inner, bg=theme.PAPER_BG); hdr.pack(fill=tk.X, padx=10, pady=(0, 4))
        self._ent_title = tk.Label(hdr, text="Sin selección", bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=fonts["title"], anchor="w")
        self._ent_title.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._badge = tk.Label(hdr, text="", bg=theme.PAPER_BG, fg=theme.INK_MUTED, font=fonts["mono_bold"], padx=6, pady=2)
        self._badge.pack(side=tk.RIGHT)

        self._ent_slot = tk.Frame(self._inner, bg=theme.PAPER_BG); self._ent_slot.pack(fill=tk.X, padx=10, pady=(0, 4))
        self._empty_lbl = tk.Label(self._ent_slot, text=_EMPTY_MSG, bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED, font=fonts["small"], justify="left", anchor="w", padx=8, pady=8, wraplength=240)
        self._empty_lbl.pack(fill=tk.X)
        self._ent_box = tk.Frame(self._ent_slot, bg=theme.PAPER_BG, highlightbackground=theme.PAPER_BORDER, highlightthickness=1)
        self._ent_rows = self._kv_pool(self._ent_box, 12)

        self._header("RESUMEN GLOBAL HASTA PTAR 31")
        sum_box = tk.Frame(self._inner, bg=theme.PAPER_BG, highlightbackground=theme.PAPER_BORDER, highlightthickness=1)
        sum_box.pack(fill=tk.X, padx=10, pady=(0, 10))
        self._sum_rows = self._kv_pool(sum_box, len(_SUM_KEYS))
        for (_, kl, vl), key in zip(self._sum_rows, _SUM_KEYS):
            kl.configure(text=key); vl.configure(text="—")

    def _sync_scroll(self) -> None:
        view_h = self._canvas.winfo_height()
        if view_h <= 1:
            return
        content_h = self._inner.winfo_reqheight()
        self._canvas.configure(scrollregion=(0, 0, max(1, self._canvas.winfo_width()), max(content_h, view_h)))
        needs_scroll = content_h > view_h + 2
        self._needs_scroll = needs_scroll
        if needs_scroll:
            if not self._vscroll.winfo_ismapped():
                self._vscroll.pack(side=tk.RIGHT, fill=tk.Y, before=self._canvas)
        else:
            if self._vscroll.winfo_ismapped():
                self._vscroll.pack_forget()
            self._canvas.yview_moveto(0.0)

    def _on_canvas_resize(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._win_id, width=event.width)
        self._empty_lbl.configure(wraplength=max(160, event.width - 28))
        self.after_idle(self._sync_scroll)

    def _toggle_wheel(self, active: bool) -> None:
        self._wheel_active = active

    def _on_wheel(self, e: tk.Event) -> None:
        if not self._wheel_active or not getattr(self, "_needs_scroll", False):
            return
        self._canvas.yview_scroll(-1 if (e.num == 4 or (e.delta and e.delta > 0)) else 1, "units")

    def _header(self, title: str) -> None:
        tk.Label(self._inner, text=title, bg=theme.PAPER_BG, fg=theme.ACCENT_TEXT, font=self._fonts["label"], anchor="w").pack(fill=tk.X, padx=10, pady=(8, 2))
        tk.Frame(self._inner, bg=theme.PAPER_RULE, height=1).pack(fill=tk.X, padx=10, pady=(0, 5))

    def _kv_pool(self, parent: tk.Misc, count: int) -> List[Tuple[tk.Frame, tk.Label, tk.Label]]:
        parent.columnconfigure(0, weight=1)
        rows: List[Tuple[tk.Frame, tk.Label, tk.Label]] = []
        for idx in range(count):
            bg = theme.PAPER_BG if idx % 2 == 0 else theme.PAPER_ALT_ROW
            row = tk.Frame(parent, bg=bg); row.grid(row=idx, column=0, sticky="ew"); row.columnconfigure(1, weight=1)
            kl = tk.Label(row, text="", bg=bg, fg=theme.INK_MUTED, font=self._fonts["small"], anchor="w", padx=6, pady=2)
            vl = tk.Label(row, text="", bg=bg, fg=theme.INK_PRIMARY, font=self._fonts["mono"], anchor="e", padx=6, pady=2)
            kl.grid(row=0, column=0, sticky="w"); vl.grid(row=0, column=1, sticky="e")
            rows.append((row, kl, vl))
        return rows

    def _set_entity(self, pairs: List[Tuple[str, str, Optional[str]]]) -> None:
        self._empty_lbl.pack_forget()
        if not self._ent_box.winfo_ismapped():
            self._ent_box.pack(fill=tk.X)
        for idx, (row, kl, vl) in enumerate(self._ent_rows):
            if idx < len(pairs):
                k, v, fg = pairs[idx]
                kl.configure(text=k); vl.configure(text=v, fg=fg or theme.INK_PRIMARY, font=self._fonts["mono_bold"] if fg else self._fonts["mono"]); row.grid()
            else:
                row.grid_remove()

    def _show_empty(self) -> None:
        self._ent_title.configure(text="Sin selección"); self._badge.configure(text="", bg=theme.PAPER_BG, fg=theme.INK_MUTED)
        self._ent_box.pack_forget()
        if not self._empty_lbl.winfo_ismapped():
            self._empty_lbl.pack(fill=tk.X)

    def update_view(
        self, graph: Optional[DirectedGraph], snapshot: Optional[TimeStepSnapshot],
        result: Optional[SimulationResult], selected_kind: Optional[str], selected_id: Optional[str],
    ) -> None:
        """Actualiza la ficha de entidad seleccionada y el resumen global."""
        if graph is None or not selected_kind or not selected_id:
            self._show_empty()
        elif selected_kind == "pipe" and (det := get_pipe_details(graph, selected_id)) is not None:
            p, ps = det.pipe, (snapshot.pipe_states.get(selected_id) if snapshot else None)
            self._ent_title.configure(text=f"Tubería {p.pipe_id}")
            if ps is not None:
                ch = ps.category.color_hex.lower()
                u_fg = theme.TIER_TEXT_ON_LIGHT.get(ch, theme.INK_PRIMARY)
                self._badge.configure(text=f"{ps.utilization_pct:.1f}%", bg=ch, fg="#1f2937" if ch in ("#22c55e", "#eab308") else "#ffffff")
            else:
                u_fg = None; self._badge.configure(text="Sin sim.", bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED)
            self._set_entity([
                ("De → A", f"{p.from_node} → {p.to_node}", None), ("Diámetro", f"{p.diameter_in:.1f} in / {p.diameter_m:.3f} m", None),
                ("Longitud", f"{p.length_m:.2f} m", None), ("Pendiente / n", f"{p.slope:.4f} / {p.manning_n:.4f}", None),
                ("Q_max", f"{p.q_max_m3s:.4f} m³/s", None), ("Velocidad", f"{det.velocity_ms:.3f} m/s", None),
                ("Tiempo tránsito", f"{det.transit_time_s:.1f} s ({det.transit_time_min:.2f} min)", None),
                ("Q conducido", f"{ps.flow_m3s:.4f} m³/s" if ps else "—", None), ("Q demanda", f"{ps.demand_flow_m3s:.4f} m³/s" if ps else "—", None),
                ("Utilización", f"{ps.utilization_pct:.1f} %" if ps else "—", u_fg),
                ("Exceso", f"{ps.excess_flow_m3s:.4f} m³/s" if ps else "—", u_fg if (ps and ps.excess_flow_m3s > 0) else None),
                ("Vol. en tránsito", f"{ps.volume_in_transit_m3:.3f} m³" if ps else "—", None),
            ])
        elif selected_kind == "node" and (nd := get_node_details(graph, selected_id)) is not None:
            node, ns = nd.node, (snapshot.node_states.get(selected_id) if snapshot else None)
            kind_lbl = _NODE_LABELS.get(node.node_type, "Pozo")
            self._ent_title.configure(text=f"{kind_lbl} {node.node_id}")
            b = ("REBOSE", "#991b1b", "#ffffff") if (ns and ns.surface_flooding_m3 > 1e-6) else (("RETENCIÓN", "#f97316", "#ffffff") if (ns and ns.stored_volume_m3 > 1e-6) else (node.node_type.upper(), theme.ACCENT_PRIMARY, theme.ACCENT_INK))
            self._badge.configure(text=b[0], bg=b[1], fg=b[2])
            self._set_entity([
                ("Tipo", kind_lbl, None), ("Entradas", _fmt_edges(nd.incoming), None),
                ("Salidas", _fmt_edges(nd.outgoing), None), ("Cap. saliente", f"{nd.total_outgoing_capacity_m3s:.4f} m³/s", None),
                ("Q ent. / sal.", f"{ns.inflow_m3s:.4f} / {ns.outflow_m3s:.4f} m³/s" if ns else "—", None),
                ("Almac. pozo", f"{ns.stored_volume_m3:.3f} m³" if ns else "—", None),
                ("Rebose sup.", f"{ns.surface_flooding_m3:.3f} m³" if ns else "—", "#991b1b" if (ns and ns.surface_flooding_m3 > 1e-6) else None),
            ])
        else:
            self._show_empty()

        if result is None or snapshot is None:
            for _, _, vl in self._sum_rows:
                vl.configure(text="—", fg=theme.INK_PRIMARY)
            return
        cfg = result.config
        vals = (
            (f"Esc. {cfg.scenario_id} — {theme.translate_scenario_name(cfg.scenario_name)}", None),
            (f"{cfg.intensity_mm_h:.1f} mm/h (t={snapshot.time_min:.1f}m)", None),
            (f"{snapshot.total_source_inflow_m3s:.4f} m³/s", None),
            (f"{result.peak_sink_discharge_m3s:.4f} m³/s | {result.total_sink_discharge_m3:,.1f} m³", None),
            (f"{snapshot.total_manhole_storage_m3:.2f} m³", None),
            (f"{result.total_surface_flooding_m3:,.2f} m³", "#991b1b" if result.total_surface_flooding_m3 > 1e-6 else None),
            (f"{len(snapshot.near_capacity_pipe_ids)} act. / {len(result.ever_near_capacity_pipes)} pico", "#dc2626" if result.ever_near_capacity_pipes else None),
            (f"{len(snapshot.overloaded_pipe_ids)} act. / {len(result.ever_overloaded_pipes)} pico", "#991b1b" if result.ever_overloaded_pipes else None),
            (f"{result.max_mass_balance_error_m3:.2e} m³ | {result.execution_time_ms:.1f} ms", None),
        )
        for (_, _, vl), (txt, fg) in zip(self._sum_rows, vals):
            vl.configure(text=txt, fg=fg or theme.INK_PRIMARY)


class CriticalPipesTab(tk.Frame):
    """Ranking interactivo de tuberías ordenado con PriorityQueue (rank_critical_pipes)."""

    def __init__(self, parent: tk.Misc, fonts: Dict[str, Tuple[str, int, str]], on_select_pipe: Callable[[str], None]) -> None:
        super().__init__(parent, bg=theme.PAPER_BG)
        self._on_select_pipe = on_select_pipe
        self._last_graph: Optional[DirectedGraph] = None
        self._last_snapshot: Optional[TimeStepSnapshot] = None
        self._dirty = self._suppress_select = False
        self._selected_pipe_id: Optional[str] = None
        self._row_iids: List[str] = []
        self._iid_to_pipe: Dict[str, str] = {}
        self._pipe_to_iid: Dict[str, str] = {}

        bar = tk.Frame(self, bg=theme.PAPER_SUBTLE, padx=8, pady=5); bar.pack(fill=tk.X)
        tk.Frame(self, bg=theme.PAPER_BORDER, height=1).pack(fill=tk.X)
        tk.Label(bar, text="Filtro:", bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED, font=fonts["small"]).pack(side=tk.LEFT)
        self._filter_var = tk.StringVar(value=_FILTER_MODES[0])
        cb = ttk.Combobox(bar, textvariable=self._filter_var, values=_FILTER_MODES, state="readonly", width=20, font=fonts["small"])
        cb.pack(side=tk.LEFT, padx=(4, 6)); cb.bind("<<ComboboxSelected>>", lambda _e: self._render())
        self._count_lbl = tk.Label(bar, text="0 tuberías", bg=theme.PAPER_SUBTLE, fg=theme.ACCENT_TEXT, font=fonts["mono_bold"])
        self._count_lbl.pack(side=tk.RIGHT)

        wrap = tk.Frame(self, bg=theme.PAPER_BG); wrap.pack(fill=tk.BOTH, expand=True)
        self._tree = ttk.Treeview(wrap, columns=tuple(c[0] for c in _COLS), show="headings", selectmode="browse")
        for col, w, anc, st in _COLS:
            self._tree.heading(col, text=col, anchor=anc); self._tree.column(col, width=w, minwidth=24, anchor=anc, stretch=st)
        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y); self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        for idx, (_, hex_c, _) in enumerate(theme.COLOR_SCALE_LEGEND):
            fg = theme.TIER_TEXT_ON_LIGHT.get(hex_c.lower(), theme.INK_PRIMARY)
            self._tree.tag_configure(f"t{idx}_0", foreground=fg, background=theme.PAPER_BG)
            self._tree.tag_configure(f"t{idx}_1", foreground=fg, background=theme.PAPER_ALT_ROW)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)

    def _render(self) -> None:
        self._dirty = False
        graph, snap = self._last_graph, self._last_snapshot
        if graph is None or snap is None:
            if self._row_iids:
                self._tree.delete(*self._row_iids)
                self._row_iids.clear(); self._iid_to_pipe.clear(); self._pipe_to_iid.clear()
            self._count_lbl.configure(text="0 tuberías")
            return
        mode = self._filter_var.get()
        if mode == "Críticas (>75–100%)":
            min_u, max_u, excl = 75.0, 100.0, True
        elif mode == "Sobrecargadas (>100%)":
            min_u, max_u, excl = 100.0, None, True
        elif mode == "En alerta (>75%)":
            min_u, max_u, excl = 75.0, None, True
        else:
            min_u, max_u, excl = 0.0, None, False
        flows = {pid: st.flow_m3s for pid, st in snap.pipe_states.items()}
        utils = {pid: st.utilization_pct for pid, st in snap.pipe_states.items()}
        records = rank_critical_pipes(graph, flows, utils, min_utilization_pct=min_u, max_utilization_pct=max_u, exclusive_min=excl)

        self._suppress_select = True
        try:
            self._iid_to_pipe.clear(); self._pipe_to_iid.clear()
            existing = len(self._row_iids)
            for idx, rec in enumerate(records):
                cat = rec.category or classify_utilization(rec.utilization_pct)
                tier_txt = _TIER_NAMES[cat.tier_index] if cat.tier_index < len(_TIER_NAMES) else cat.label
                vals = (rec.rank, rec.pipe_id, f"{rec.from_node}→{rec.to_node}", f"{rec.flow_m3s:.4f}", f"{rec.q_max_m3s:.4f}", f"{rec.utilization_pct:.1f}%", tier_txt)
                tag = (f"t{cat.tier_index}_{idx % 2}",)
                if idx < existing:
                    iid = self._row_iids[idx]; self._tree.item(iid, values=vals, tags=tag)
                else:
                    iid = self._tree.insert("", tk.END, values=vals, tags=tag); self._row_iids.append(iid)
                self._iid_to_pipe[iid], self._pipe_to_iid[rec.pipe_id] = rec.pipe_id, iid
            if existing > len(records):
                self._tree.delete(*self._row_iids[len(records):]); del self._row_iids[len(records):]
            self._count_lbl.configure(text=f"{len(records)} tubería{'s' if len(records) != 1 else ''}")
        finally:
            self._suppress_select = False

    def update_view(self, graph: Optional[DirectedGraph], snapshot: Optional[TimeStepSnapshot], is_visible: bool = True) -> None:
        """Actualiza la tabla o difiere el redibujo si la pestaña no está visible."""
        self._last_graph, self._last_snapshot = graph, snapshot
        if not is_visible:
            self._dirty = True
            return
        self._render()

    def mark_visible(self, graph: Optional[DirectedGraph], snapshot: Optional[TimeStepSnapshot]) -> None:
        """Sincroniza la pestaña al volverse visible si había cambios diferidos."""
        self._last_graph, self._last_snapshot = graph, snapshot
        if self._dirty or not self._row_iids:
            self._render()

    def _on_tree_select(self, _event: tk.Event) -> None:
        if self._suppress_select:
            return
        sel = self._tree.selection()
        pid = self._iid_to_pipe.get(sel[0]) if sel else None
        if pid is None or pid == self._selected_pipe_id:
            return
        self._selected_pipe_id = pid
        self._on_select_pipe(pid)

    def select_pipe(self, pipe_id: Optional[str]) -> None:
        """Resalta y desplaza hasta la fila de pipe_id sin bucle de eventos."""
        self._selected_pipe_id = pipe_id
        iid = self._pipe_to_iid.get(pipe_id) if pipe_id else None
        target = (iid,) if iid is not None else ()
        if tuple(self._tree.selection()) == target:
            if iid is not None:
                self._tree.see(iid)
            return
        self._suppress_select = True
        try:
            self._tree.selection_set(target)
            if iid is not None:
                self._tree.see(iid)
        finally:
            self._suppress_select = False
