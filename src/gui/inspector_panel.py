"""Módulo de las pestañas Inspector y Tuberías Críticas (incluye intervenciones y atribución)."""

import math
import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, Optional, Set

from src.algorithms import (
    classify_overload_persistence,
    compute_source_attribution,
    find_isolated_from_sinks,
    rank_critical_pipes,
    trace_downstream,
    trace_upstream,
)
from src.simulation import PipeIntervention, resolve_pipe_hydraulics
from . import theme
from .widgets import COMMERCIAL_DIAMETERS_IN


class InspectorPanelMixin:
    """Construye y actualiza Inspector (ficha, intervenciones, fuentes) y Tuberías Críticas."""

    def _build_inspector_tab(self, notebook: ttk.Notebook) -> None:
        tab_info = ttk.Frame(notebook)
        notebook.add(tab_info, text="Inspector")

        self.inspector_actions = tk.Frame(tab_info, bg=theme.DOCK_BG)
        self.btn_focus_selected = self._make_btn(
            self.inspector_actions,
            " Centrar",
            self._action_focus_selected,
            variant="light_secondary",
            padx=7,
            pady=3,
            font_size=8,
            image=self._icons["crosshair_light"],
            compound=tk.LEFT,
        )
        self.btn_isolate_basin = self._make_btn(
            self.inspector_actions,
            "Aislar cuenca",
            self._action_toggle_basin_isolation,
            variant="light_secondary",
            padx=8,
            pady=3,
            font_size=8,
        )
        self.btn_insp_upstream = self._make_btn(
            self.inspector_actions,
            "Aguas arriba",
            lambda: self._action_toggle_inspector_trace("up"),
            variant="light_secondary",
            padx=7,
            pady=3,
            font_size=8,
        )
        self.btn_insp_downstream = self._make_btn(
            self.inspector_actions,
            "Aguas abajo",
            lambda: self._action_toggle_inspector_trace("down"),
            variant="light_secondary",
            padx=7,
            pady=3,
            font_size=8,
        )
        self._inspector_actions_sep = tk.Frame(tab_info, bg=theme.DOCK_BORDER, height=1)

        # Tarjeta compacta de intervención en vivo sobre tubería
        self.pipe_intervention_card = tk.Frame(tab_info, bg=theme.PAPER_SUBTLE)
        self._pipe_intervention_sep = tk.Frame(tab_info, bg=theme.DOCK_BORDER, height=1)

        int_hdr = tk.Frame(self.pipe_intervention_card, bg=theme.PAPER_SUBTLE)
        int_hdr.pack(fill=tk.X, padx=8, pady=(6, 2))
        tk.Label(
            int_hdr,
            text="Intervención en vivo",
            bg=theme.PAPER_SUBTLE,
            fg=theme.ACCENT_TEXT_ON_LIGHT,
            font=(self.display_font, 8, "bold"),
        ).pack(side=tk.LEFT)
        self.btn_restore_all = self._make_btn(
            int_hdr,
            "Restaurar red",
            self._action_restore_all_interventions,
            variant="light_secondary",
            padx=6,
            pady=1,
            font_size=7,
        )
        self.lbl_active_interventions = tk.Label(
            int_hdr,
            text="",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_MUTED,
            font=(self.mono_font, 7, "bold"),
        )
        self.lbl_active_interventions.pack(side=tk.RIGHT, padx=(0, 4))

        row_obst = tk.Frame(self.pipe_intervention_card, bg=theme.PAPER_SUBTLE)
        row_obst.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(
            row_obst,
            text="Obstrucción (%)",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8),
        ).pack(side=tk.LEFT)
        self.lbl_obst_val = tk.Label(
            row_obst,
            text="0%",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.mono_font, 8, "bold"),
            width=5,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )
        self.lbl_obst_val.pack(side=tk.RIGHT, padx=(4, 0))
        self.scale_obstruction = tk.Scale(
            row_obst,
            from_=0,
            to=100,
            resolution=5,
            orient=tk.HORIZONTAL,
            showvalue=False,
            variable=self.var_obstruction_pct,
            command=lambda v: self.lbl_obst_val.configure(text=f"{float(v):.0f}%"),
            bg=theme.PAPER_SUBTLE,
            troughcolor=theme.DOCK_BG,
            activebackground=theme.ACCENT_PRIMARY,
            highlightthickness=0,
            bd=0,
            sliderlength=14,
            width=10,
        )
        self.scale_obstruction.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=6)

        row_diam = tk.Frame(self.pipe_intervention_card, bg=theme.PAPER_SUBTLE)
        row_diam.pack(fill=tk.X, padx=8, pady=2)
        tk.Label(
            row_diam,
            text="Diámetro",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8),
        ).pack(side=tk.LEFT)
        self.lbl_diam_current = tk.Label(
            row_diam,
            text="Actual: -",
            bg=theme.PAPER_BG,
            fg=theme.ACCENT_TEXT_ON_LIGHT,
            font=(self.mono_font, 7, "bold"),
            padx=5,
            pady=1,
            highlightthickness=1,
            highlightbackground=theme.PAPER_BORDER,
        )
        self.lbl_diam_current.pack(side=tk.LEFT, padx=(6, 4))
        self.combo_diam_override = ttk.Combobox(
            row_diam,
            textvariable=self.var_diam_override,
            values=COMMERCIAL_DIAMETERS_IN,
            width=11,
            style="Light.TCombobox",
        )
        self.combo_diam_override.pack(side=tk.RIGHT)

        row_int_btns = tk.Frame(self.pipe_intervention_card, bg=theme.PAPER_SUBTLE)
        row_int_btns.pack(fill=tk.X, padx=8, pady=(4, 6))
        self._make_btn(
            row_int_btns,
            "Aplicar y re-simular",
            self._action_apply_intervention,
            variant="primary",
            padx=8,
            pady=3,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        self._make_btn(
            row_int_btns,
            "Restaurar tramo",
            self._action_restore_pipe,
            variant="dock_secondary",
            padx=7,
            pady=3,
            font_size=8,
        ).pack(side=tk.LEFT)

        # Sección de Trazabilidad por Fuente Aportante
        self.source_attribution_card = tk.Frame(tab_info, bg=theme.PAPER_SUBTLE)
        self._source_attribution_sep = tk.Frame(tab_info, bg=theme.DOCK_BORDER, height=1)

        src_hdr = tk.Frame(self.source_attribution_card, bg=theme.PAPER_SUBTLE)
        src_hdr.pack(fill=tk.X, padx=8, pady=(6, 3))
        tk.Label(
            src_hdr,
            text="Composición por Fuente Aportante",
            bg=theme.PAPER_SUBTLE,
            fg=theme.ACCENT_TEXT_ON_LIGHT,
            font=(self.display_font, 8, "bold"),
        ).pack(side=tk.LEFT)
        self.lbl_source_entity = tk.Label(
            src_hdr,
            text="",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_MUTED,
            font=(self.mono_font, 7, "bold"),
        )
        self.lbl_source_entity.pack(side=tk.RIGHT)

        self.canvas_source_bar = tk.Canvas(
            self.source_attribution_card,
            height=self._px(18),
            bg=theme.PAPER_BG,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
            bd=0,
        )
        self.canvas_source_bar.pack(fill=tk.X, padx=8, pady=(0, 3))
        self.canvas_source_bar.bind("<Configure>", lambda _e: self._redraw_source_bar_canvas())

        self.lbl_source_breakdown = tk.Label(
            self.source_attribution_card,
            text="",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_PRIMARY,
            font=(self.mono_font, 8),
            justify="left",
            anchor="w",
            wraplength=self._px(330),
        )
        self.lbl_source_breakdown.pack(fill=tk.X, padx=8, pady=(0, 6))
        self._current_source_shares: List[tuple] = []

        self._inspector_wrap = tk.Frame(tab_info, bg=theme.PAPER_BG)
        self._inspector_wrap.pack(fill=tk.BOTH, expand=True)
        self.txt_inspector = tk.Text(
            self._inspector_wrap,
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            relief="flat",
            font=(self.mono_font, 9),
            wrap=tk.WORD,
            padx=12,
            pady=10,
        )
        insp_scroll = ttk.Scrollbar(
            self._inspector_wrap,
            orient=tk.VERTICAL,
            command=self.txt_inspector.yview,
            style="Light.Vertical.TScrollbar",
        )
        self.txt_inspector.configure(yscrollcommand=insp_scroll.set)
        self.txt_inspector.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        insp_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.txt_inspector.tag_configure(
            "heading", font=(self.display_font, 10, "bold"), foreground=theme.ACCENT_TEXT_ON_LIGHT
        )
        self.txt_inspector.tag_configure(
            "section", font=(self.display_font, 9, "bold"), foreground=theme.INK_PRIMARY
        )
        self.txt_inspector.tag_configure(
            "muted", font=(self.mono_font, 8), foreground=theme.INK_MUTED
        )
        self.txt_inspector.tag_configure(
            "alert", font=(self.mono_font, 9, "bold"), foreground=theme.STATUS_ERR_LIGHT
        )
        self.txt_inspector.configure(state=tk.DISABLED)

    def _build_critical_tab(self, notebook: ttk.Notebook) -> None:
        tab_crit = ttk.Frame(notebook)
        notebook.add(tab_crit, text="Tuberías Críticas")

        filter_bar = tk.Frame(tab_crit, bg=theme.PAPER_SUBTLE)
        filter_bar.pack(fill=tk.X)
        tk.Frame(tab_crit, bg=theme.DOCK_BORDER, height=1).pack(fill=tk.X)
        for text, val in [
            ("Todas", "all"),
            ("Resto (≤75%)", "rest"),
            ("Críticas (>75–100%)", "critical"),
            ("Sobrec. (>100%)", "overloaded"),
        ]:
            tk.Radiobutton(
                filter_bar,
                text=text,
                variable=self.var_crit_filter,
                value=val,
                command=self._refresh_critical_table,
                bg=theme.PAPER_SUBTLE,
                fg=theme.INK_PRIMARY,
                selectcolor=theme.PAPER_BG,
                activebackground=theme.PAPER_SUBTLE,
                activeforeground=theme.ACCENT_TEXT_ON_LIGHT,
                font=(self.ui_font, 8),
                cursor="hand2",
            ).pack(side=tk.LEFT, padx=4, pady=5)

        self.lbl_crit_count = tk.Label(
            filter_bar,
            text="",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_MUTED,
            font=(self.mono_font, 8, "bold"),
        )
        self.lbl_crit_count.pack(side=tk.RIGHT, padx=8)

        crit_table_wrap = tk.Frame(tab_crit, bg=theme.PAPER_BG)
        crit_table_wrap.pack(fill=tk.BOTH, expand=True)

        cols = ("rank", "pipe", "tramo", "q_curr", "q_max", "util", "estado")
        self._crit_tree_compact: Optional[bool] = None
        self.tree_critical = ttk.Treeview(
            crit_table_wrap, columns=cols, show="headings", selectmode="browse"
        )
        self.tree_critical.tag_configure("odd", background=theme.PAPER_ALT_ROW)
        crit_headers = [
            ("rank", "#", "center"),
            ("pipe", "Tub.", "center"),
            ("tramo", "Tramo", "center"),
            ("q_curr", "Q (m³/s)", "e"),
            ("q_max", "Qmax", "e"),
            ("util", "% Util", "e"),
            ("estado", "Estado", "w"),
        ]
        for cid, htext, anchor in crit_headers:
            self.tree_critical.heading(cid, text=htext)
            self.tree_critical.column(cid, width=56, minwidth=30, anchor=anchor)

        crit_scroll = ttk.Scrollbar(
            crit_table_wrap,
            orient=tk.VERTICAL,
            command=self.tree_critical.yview,
            style="Light.Vertical.TScrollbar",
        )
        self.tree_critical.configure(yscrollcommand=crit_scroll.set)
        self.tree_critical.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        crit_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_critical.bind("<<TreeviewSelect>>", self._on_critical_row_select)
        self.tree_critical.bind(
            "<Double-1>",
            lambda _e: self.network_canvas.focus_pipe(self._selected_pipe_id)
            if self._selected_pipe_id
            else None,
        )
        self.tree_critical.bind("<Configure>", self._resize_critical_columns)

        self.lbl_crit_empty = tk.Label(
            crit_table_wrap,
            text="",
            bg=theme.PAPER_BG,
            fg=theme.INK_MUTED,
            font=(self.ui_font, 9),
            justify="center",
        )

    def _resize_critical_columns(self, event: tk.Event) -> None:
        w = max(220, event.width - 4)
        compact = w < 365
        if compact != self._crit_tree_compact:
            self._crit_tree_compact = compact
            if compact:
                headers = [
                    ("rank", "#"),
                    ("pipe", "Tub."),
                    ("tramo", "Tramo"),
                    ("q_curr", "Q"),
                    ("q_max", "Qmax"),
                    ("util", "%"),
                    ("estado", "Estado"),
                ]
            else:
                headers = [
                    ("rank", "#"),
                    ("pipe", "Tub."),
                    ("tramo", "Tramo"),
                    ("q_curr", "Q (m³/s)"),
                    ("q_max", "Qmax"),
                    ("util", "% Util"),
                    ("estado", "Estado"),
                ]
            for cid, htext in headers:
                self.tree_critical.heading(cid, text=htext)
            if self.result is not None:
                self._refresh_critical_table()

        if compact:
            weights = [
                ("rank", 0.06, 22),
                ("pipe", 0.10, 34),
                ("tramo", 0.15, 46),
                ("q_curr", 0.14, 44),
                ("q_max", 0.14, 44),
                ("util", 0.16, 48),
                ("estado", 0.25, 76),
            ]
        else:
            weights = [
                ("rank", 0.06, 26),
                ("pipe", 0.10, 38),
                ("tramo", 0.14, 50),
                ("q_curr", 0.15, 54),
                ("q_max", 0.14, 52),
                ("util", 0.15, 52),
                ("estado", 0.26, 98),
            ]
        for cid, ratio, min_w in weights:
            self.tree_critical.column(cid, width=max(min_w, int(w * ratio)))

    def _on_pipe_selected(self, pipe_id: str) -> None:
        self._selected_pipe_id = pipe_id
        self._selected_node_id = None
        if self._inspector_trace_state is not None:
            self._inspector_trace_state = None
            self._sync_inspector_trace_buttons()
        self._sync_intervention_controls()
        if self._basin_isolated:
            self._apply_basin_isolation()
        if self._active_right_tab() == 1 and self.tree_critical.exists(pipe_id):
            self._suppress_tree_select = True
            try:
                if list(self.tree_critical.selection()) != [pipe_id]:
                    self.tree_critical.selection_set(pipe_id)
                if not self.is_playing:
                    self.tree_critical.see(pipe_id)
            finally:
                self._suppress_tree_select = False
        else:
            self._crit_tab_dirty = True
        self._refresh_inspector()
        if self.result is not None:
            self._push_temporal_charts(throttle_draw=False)

    def _on_node_selected(self, node_id: str) -> None:
        if self._inspector_trace_state is not None and self._inspector_trace_state[0] != node_id:
            self._inspector_trace_state = None
            self._sync_inspector_trace_buttons()
        self._selected_node_id = node_id
        self._selected_pipe_id = None
        self.var_bfs_start.set(node_id)
        if self._basin_isolated:
            self._apply_basin_isolation()
        self._crit_tab_dirty = True
        self._suppress_tree_select = True
        try:
            sel = self.tree_critical.selection()
            if sel:
                self.tree_critical.selection_remove(*sel)
        except tk.TclError:
            pass
        finally:
            self._suppress_tree_select = False
        self._refresh_inspector()
        if self.result is not None:
            self._push_temporal_charts(throttle_draw=False)

    def _action_focus_selected(self) -> None:
        if self._selected_pipe_id:
            self.network_canvas.focus_pipe(self._selected_pipe_id)
        elif self._selected_node_id:
            self.network_canvas.focus_node(self._selected_node_id)

    def _action_toggle_basin_isolation(self) -> None:
        if self.dataset is None or (not self._selected_pipe_id and not self._selected_node_id):
            messagebox.showinfo("Sin selección", "Seleccione primero un nodo o tubería del grafo.")
            return
        if self._tour_active:
            self._close_guided_tour()
        self._basin_isolated = not self._basin_isolated
        self._apply_basin_isolation()
        self._refresh_inspector()

    def _apply_basin_isolation(self) -> None:
        if not self._basin_isolated or self.dataset is None:
            self.network_canvas.set_basin_focus(None, None)
            self._set_btn_variant(self.btn_isolate_basin, "light_secondary")
            return

        g = self.dataset.graph
        focus_nodes: Set[str] = set()
        focus_pipes: Set[str] = set()

        if self._selected_pipe_id and g.has_pipe(self._selected_pipe_id):
            edge = g.get_pipe(self._selected_pipe_id)
            assert edge is not None
            up_n, up_p = trace_upstream(g, edge.from_node)
            dn_n, dn_p = trace_downstream(g, edge.to_node)
            focus_nodes = set(up_n) | set(dn_n)
            focus_pipes = {p.pipe_id for p in up_p} | {p.pipe_id for p in dn_p} | {edge.pipe_id}
        elif self._selected_node_id and g.has_node(self._selected_node_id):
            up_n, up_p = trace_upstream(g, self._selected_node_id)
            dn_n, dn_p = trace_downstream(g, self._selected_node_id)
            focus_nodes = set(up_n) | set(dn_n)
            focus_pipes = {p.pipe_id for p in up_p} | {p.pipe_id for p in dn_p}
        else:
            self._basin_isolated = False
            self.network_canvas.set_basin_focus(None, None)
            self._set_btn_variant(self.btn_isolate_basin, "light_secondary")
            return

        self.network_canvas.set_basin_focus(focus_nodes, focus_pipes)
        self._set_btn_variant(self.btn_isolate_basin, "primary")
        self.status_var.set(
            f"Cuenca aislada: {len(focus_nodes)} nodo(s) y {len(focus_pipes)} tramo(s) activos hacia PTAR 31."
        )

    def _sync_intervention_controls(self) -> None:
        if not self._selected_pipe_id or self.dataset is None:
            return
        edge = self.dataset.graph.get_pipe(self._selected_pipe_id)
        if edge is None:
            return
        inv = self._interventions.get(self._selected_pipe_id)
        eff_diam = (
            inv.diameter_in_override
            if (inv is not None and inv.diameter_in_override is not None)
            else edge.diameter_in
        )
        self.lbl_diam_current.configure(
            text=f"Actual: {eff_diam:.0f}\" ({eff_diam * 0.0254:.3f} m)"
        )
        orig_label = f"Original ({edge.diameter_in:.0f}\")"
        self.combo_diam_override.configure(values=[orig_label] + COMMERCIAL_DIAMETERS_IN[1:])
        if inv is None:
            self.var_obstruction_pct.set(0.0)
            self.lbl_obst_val.configure(text="0%")
            self.var_diam_override.set(orig_label)
        else:
            self.var_obstruction_pct.set(round(inv.obstruction_pct))
            self.lbl_obst_val.configure(text=f"{inv.obstruction_pct:.0f}%")
            if inv.diameter_in_override is None:
                self.var_diam_override.set(orig_label)
            else:
                self.var_diam_override.set(f"{inv.diameter_in_override:g}\"")

    def _parse_diameter_override(self, raw: str, base_diam_in: float) -> Optional[float]:
        text = raw.strip()
        if not text or text.lower().startswith("original"):
            return None
        cleaned = text.replace('"', "").replace("pulg", "").strip()
        val = float(cleaned)
        if not math.isfinite(val) or val <= 0.0 or val > 120.0:
            raise ValueError("El diámetro debe estar entre > 0 y 120 pulgadas.")
        if abs(val - base_diam_in) < 1e-6:
            return None
        return val

    def _sync_isolation_and_canvas(self) -> None:
        if self.dataset is None:
            return
        blocked = {pid for pid, inv in self._interventions.items() if inv.is_closed}
        self._isolated_nodes, self._isolated_pipes = find_isolated_from_sinks(
            self.dataset.graph, blocked
        )
        self.network_canvas.set_interventions(
            self._interventions, self._isolated_nodes, self._isolated_pipes
        )
        self._mark_comparisons_dirty()

    def _action_apply_intervention(self) -> None:
        if self.dataset is None or not self._selected_pipe_id:
            return
        edge = self.dataset.graph.get_pipe(self._selected_pipe_id)
        if edge is None:
            return

        try:
            obst = float(self.var_obstruction_pct.get())
            if not math.isfinite(obst) or obst < 0.0 or obst > 100.0:
                raise ValueError("La obstrucción debe estar entre 0 % y 100 %.")
            diam_override = self._parse_diameter_override(
                self.var_diam_override.get(), edge.diameter_in
            )
        except Exception as exc:
            messagebox.showwarning("Intervención inválida", str(exc))
            return

        if obst <= 1e-6 and diam_override is None:
            self._interventions.pop(edge.pipe_id, None)
        else:
            self._interventions[edge.pipe_id] = PipeIntervention(
                pipe_id=edge.pipe_id,
                obstruction_pct=obst,
                diameter_in_override=diam_override,
            )

        self._sync_intervention_controls()
        self._sync_isolation_and_canvas()
        self.run_simulation(preserve_previous=True)
        if self._isolated_nodes:
            self.status_var.set(
                f"Cirugía en {edge.pipe_id}: {len(self._isolated_nodes)} nodo(s) aislados de la PTAR 31."
            )

    def _action_restore_pipe(self) -> None:
        if not self._selected_pipe_id or self._selected_pipe_id not in self._interventions:
            return
        self._interventions.pop(self._selected_pipe_id, None)
        self._sync_intervention_controls()
        self._sync_isolation_and_canvas()
        self.run_simulation(preserve_previous=True)

    def _action_restore_all_interventions(self) -> None:
        if not self._interventions:
            return
        self._interventions.clear()
        self._sync_intervention_controls()
        self._sync_isolation_and_canvas()
        self.run_simulation(preserve_previous=True)

    def _sync_inspector_trace_buttons(self) -> None:
        up_on = (
            self._inspector_trace_state is not None
            and self._inspector_trace_state[0] == self._selected_node_id
            and self._inspector_trace_state[1] == "up"
        )
        dn_on = (
            self._inspector_trace_state is not None
            and self._inspector_trace_state[0] == self._selected_node_id
            and self._inspector_trace_state[1] == "down"
        )
        if hasattr(self, "btn_insp_upstream"):
            self._set_btn_variant(
                self.btn_insp_upstream, "primary" if up_on else "light_secondary"
            )
        if hasattr(self, "btn_insp_downstream"):
            self._set_btn_variant(
                self.btn_insp_downstream, "primary" if dn_on else "light_secondary"
            )

    def _action_toggle_inspector_trace(self, direction: str) -> None:
        if self.dataset is None or not self._selected_node_id:
            return
        if self._inspector_trace_state == (self._selected_node_id, direction):
            self._inspector_trace_state = None
            self.network_canvas.set_highlights(set(), set())
            self._sync_inspector_trace_buttons()
            self.status_var.set("Vista de red restaurada.")
            return
        self.var_bfs_start.set(self._selected_node_id)
        self._run_trace(direction)
        self._inspector_trace_state = (self._selected_node_id, direction)
        self._sync_inspector_trace_buttons()

    def _trace_from_selected(self, direction: str) -> None:
        self._action_toggle_inspector_trace(direction)

    def _refresh_critical_table(self) -> None:
        self._suppress_tree_select = True
        try:
            if self.dataset is None or self.result is None:
                for item in self.tree_critical.get_children():
                    self.tree_critical.delete(item)
                self.lbl_crit_count.configure(text="")
                self.lbl_crit_empty.place_forget()
                return

            snap = self.result.snapshots[self.current_step]
            flows = {pid: ps.flow_m3s for pid, ps in snap.pipe_states.items()}
            utils = {pid: ps.utilization_pct for pid, ps in snap.pipe_states.items()}
            demands = {pid: ps.demand_ratio_pct for pid, ps in snap.pipe_states.items()}
            excesses = {pid: ps.excess_flow_m3s for pid, ps in snap.pipe_states.items()}
            qmax_overrides = {
                pid: ps.effective_q_max_m3s
                for pid, ps in snap.pipe_states.items()
                if ps.effective_q_max_m3s is not None
            }

            flt = self.var_crit_filter.get()
            if flt == "rest":
                min_u, max_u, exc_min = 0.0, 75.0, False
            elif flt == "critical":
                min_u, max_u, exc_min = 75.0, 100.0, True
            elif flt == "overloaded":
                min_u, max_u, exc_min = 100.0, None, True
            else:
                min_u, max_u, exc_min = 0.0, None, False
            ranked = rank_critical_pipes(
                self.dataset.graph,
                flows,
                utils,
                min_utilization_pct=min_u,
                max_utilization_pct=max_u,
                exclusive_min=exc_min,
                pipe_qmax_overrides=qmax_overrides,
                pipe_demand_ratios_pct=demands,
                pipe_excess_flows_m3s=excesses,
            )
            self.lbl_crit_count.configure(text=f"{len(ranked)} reg.")

            short_estado = {
                "Baja utilización": "Baja",
                "Utilización moderada": "Moderada",
                "Utilización alta": "Alta",
                "Cercana a la capacidad máxima": "Cercana máx.",
                "Capacidad excedida": "Cap. excedida",
            }
            wide_estado = {
                "Baja utilización": "Baja util.",
                "Utilización moderada": "Moderada",
                "Utilización alta": "Alta",
                "Cercana a la capacidad máxima": "Cercana máx.",
                "Capacidad excedida": "Cap. excedida",
            }
            compact = bool(self._crit_tree_compact)
            desired_ids = [rec.pipe_id for rec in ranked]
            existing_ids = list(self.tree_critical.get_children())

            def _row_values(rec):
                if rec.q_max_m3s <= 1e-12:
                    estado_txt = "Cerrada 100%"
                    util_txt = "0.0%"
                else:
                    estado_txt = (
                        short_estado.get(rec.category.label, rec.category.label)
                        if compact
                        else wide_estado.get(rec.category.label, rec.category.label)
                    )
                    util_txt = (
                        f"{rec.utilization_pct:.1f}% ({rec.utilization_pct / 100.0:.1f}×)"
                        if rec.utilization_pct > 100.5
                        else f"{rec.utilization_pct:.1f}%"
                    )
                return (
                    rec.rank,
                    rec.pipe_id,
                    f"{rec.from_node}→{rec.to_node}",
                    f"{rec.flow_m3s:.4f}",
                    f"{rec.q_max_m3s:.4f}",
                    util_txt,
                    estado_txt,
                )

            if existing_ids == desired_ids:
                for idx, rec in enumerate(ranked):
                    self.tree_critical.item(
                        rec.pipe_id,
                        tags=("odd",) if idx % 2 == 1 else (),
                        values=_row_values(rec),
                    )
            else:
                for item in existing_ids:
                    self.tree_critical.delete(item)
                for idx, rec in enumerate(ranked):
                    self.tree_critical.insert(
                        "",
                        tk.END,
                        iid=rec.pipe_id,
                        tags=("odd",) if idx % 2 == 1 else (),
                        values=_row_values(rec),
                    )

            if not ranked:
                if flt == "overloaded":
                    msg = "Ninguna tubería supera el 100% en este instante."
                elif flt == "critical":
                    msg = "Ninguna tubería está en >75–100% en este instante."
                elif flt == "rest":
                    msg = "Ninguna tubería está en ≤75% en este instante."
                else:
                    msg = "Sin tuberías para mostrar."
                self.lbl_crit_empty.configure(text=msg)
                self.lbl_crit_empty.place(relx=0.5, rely=0.5, anchor="center")
            else:
                self.lbl_crit_empty.place_forget()
                if self._selected_pipe_id and self.tree_critical.exists(self._selected_pipe_id):
                    cur_sel = list(self.tree_critical.selection())
                    if cur_sel != [self._selected_pipe_id]:
                        self.tree_critical.selection_set(self._selected_pipe_id)
                    if not self.is_playing:
                        self.tree_critical.see(self._selected_pipe_id)
        finally:
            self._suppress_tree_select = False

    def _on_critical_row_select(self, _event: tk.Event) -> None:
        if self._suppress_tree_select:
            return
        sel = self.tree_critical.selection()
        if sel:
            pid = sel[0]
            if pid == self._selected_pipe_id:
                return
            self.network_canvas.select_pipe(pid)
            self._on_pipe_selected(pid)

    def _refresh_inspector(self) -> None:
        sel_kind = "pipe" if self._selected_pipe_id else ("node" if self._selected_node_id else "none")
        n_int = len(self._interventions)
        new_layout_state = (sel_kind, n_int > 0, bool(self._basin_isolated))

        if new_layout_state != self._inspector_layout_state:
            prev_sel, prev_has_int, prev_iso = self._inspector_layout_state or (None, False, False)
            self._inspector_layout_state = new_layout_state

            if sel_kind != prev_sel:
                for b in (
                    self.btn_focus_selected,
                    self.btn_isolate_basin,
                    self.btn_insp_upstream,
                    self.btn_insp_downstream,
                ):
                    b.pack_forget()
                self.inspector_actions.pack_forget()
                self._inspector_actions_sep.pack_forget()
                self.pipe_intervention_card.pack_forget()
                self._pipe_intervention_sep.pack_forget()
                self.source_attribution_card.pack_forget()
                self._source_attribution_sep.pack_forget()

                if sel_kind != "none":
                    self.inspector_actions.pack(fill=tk.X, before=self._inspector_wrap)
                    self._inspector_actions_sep.pack(fill=tk.X, before=self._inspector_wrap)
                    self.btn_focus_selected.pack(side=tk.LEFT, padx=(8, 3), pady=5)
                    self.btn_isolate_basin.pack(side=tk.LEFT, padx=3, pady=5)
                if sel_kind == "node":
                    self.btn_insp_upstream.pack(side=tk.LEFT, padx=3, pady=5)
                    self.btn_insp_downstream.pack(side=tk.LEFT, padx=3, pady=5)
                if sel_kind == "pipe":
                    self.pipe_intervention_card.pack(fill=tk.X, before=self._inspector_wrap)
                    self._pipe_intervention_sep.pack(fill=tk.X, before=self._inspector_wrap)
                if sel_kind != "none":
                    self.source_attribution_card.pack(fill=tk.X, before=self._inspector_wrap)
                    self._source_attribution_sep.pack(fill=tk.X, before=self._inspector_wrap)

            if sel_kind != "none" and (sel_kind != prev_sel or bool(self._basin_isolated) != prev_iso):
                self._set_btn_variant(
                    self.btn_isolate_basin, "primary" if self._basin_isolated else "light_secondary"
                )
            if sel_kind == "node":
                self._sync_inspector_trace_buttons()

            if sel_kind == "pipe" and (sel_kind != prev_sel or (n_int > 0) != prev_has_int):
                self.lbl_active_interventions.configure(
                    text=f"{n_int} act." if n_int else ""
                )
                if n_int:
                    self.btn_restore_all.pack(side=tk.RIGHT)
                else:
                    self.btn_restore_all.pack_forget()

        if sel_kind != "none":
            self._refresh_source_attribution_panel()

        self.txt_inspector.configure(state=tk.NORMAL)
        self.txt_inspector.delete("1.0", tk.END)

        def add_line(text: str, tag: Optional[str] = None) -> None:
            if tag:
                self.txt_inspector.insert(tk.END, text + "\n", tag)
            else:
                self.txt_inspector.insert(tk.END, text + "\n")

        if self.dataset is None:
            add_line("Cargue un archivo Excel o carpeta CSV para comenzar.", "muted")
        else:
            g = self.dataset.graph
            snap = self.result.snapshots[self.current_step] if self.result else None

            if self._selected_pipe_id and g.has_pipe(self._selected_pipe_id):
                p = g.get_pipe(self._selected_pipe_id)
                assert p is not None
                inv = self._interventions.get(p.pipe_id)
                eff_qmax, eff_vel, eff_t_s, eff_diam = resolve_pipe_hydraulics(p, inv)
                add_line(f"TUBERÍA {p.pipe_id}  ({p.from_node} → {p.to_node})", "heading")
                add_line("─" * 40, "muted")
                if inv:
                    add_line(
                        f"INTERVENCIÓN    : OBST {inv.obstruction_pct:.0f}% · Ø {eff_diam:.0f}\" (orig. {p.diameter_in:.0f}\")",
                        "alert",
                    )
                if p.pipe_id in self._isolated_pipes:
                    add_line("[AISLADO DE 31] : Tramo sin conexión hacia PTAR", "alert")
                add_line(f"Diámetro        : {eff_diam:.0f}\" ({eff_diam * 0.0254:.4f} m)")
                add_line(f"Longitud        : {p.length_m:.2f} m")
                add_line(f"Pendiente (S)   : {p.slope:.4f} m/m  |  n: {p.manning_n:.3f}")
                add_line(f"Capacidad Qmax  : {eff_qmax:.5f} m³/s (base {p.q_max_m3s:.5f})")
                add_line(f"Velocidad ref.  : {eff_vel:.3f} m/s")
                add_line(f"Tiempo tránsito : {eff_t_s / 60.0:.2f} min ({eff_t_s:.1f} s)")
                if p.note:
                    add_line(f"Marca dataset   : {p.note}")
                if snap and p.pipe_id in snap.pipe_states:
                    ps = snap.pipe_states[p.pipe_id]
                    add_line("")
                    add_line(f"Estado en t = {snap.time_min:.1f} min", "section")
                    if ps.is_closed:
                        add_line("Estado tramo    : CERRADA 100% (caudal nulo)", "alert")
                        add_line(f"Demanda retenida: {ps.demand_flow_m3s:.5f} m³/s")
                    else:
                        add_line(f"Caudal conducido: {ps.flow_m3s:.5f} m³/s")
                        add_line(f"Demanda entrante: {ps.demand_flow_m3s:.5f} m³/s ({ps.utilization_pct / 100.0:.2f}× Qmax)")
                        add_line(f"Vol. tránsito   : {ps.volume_in_transit_m3:.2f} m³")
                        add_line(
                            f"Utilización     : {ps.utilization_pct:.2f} %",
                            "alert" if ps.utilization_pct > 100.0 else None,
                        )
                        add_line(f"Clasificación   : {ps.category.label}")
                        add_line(f"Exceso no cond. : {ps.excess_flow_m3s:.5f} m³/s")
                if self.result:
                    pk_u = self.result.peak_pipe_utilization.get(p.pipe_id, 0.0)
                    add_line(
                        f"Pico utilización: {pk_u:.2f} % ({pk_u / 100.0:.2f}× Qmax)"
                    )
                    ov_m = self.result.pipe_overloaded_minutes.get(p.pipe_id, 0.0)
                    _, _, ov_desc = classify_overload_persistence(ov_m, self.result.config.duration_min)
                    add_line(
                        f"Estrés >100%    : {ov_m:.0f} min ({ov_desc})",
                        "alert" if ov_m > 0.0 else None,
                    )
            elif self._selected_node_id and g.has_node(self._selected_node_id):
                n = g.get_node(self._selected_node_id)
                assert n is not None
                out_p = [e.pipe_id for e in g.outgoing_pipes(n.node_id)]
                in_p = [e.pipe_id for e in g.incoming_pipes(n.node_id)]
                tipo_es = {
                    "source": "FUENTE",
                    "sink": "SUMIDERO PTAR",
                    "manhole": "POZO DE INSPECCIÓN",
                }.get(n.node_type, n.node_type.upper())
                add_line(f"NODO {n.node_id}  ({tipo_es})", "heading")
                add_line("─" * 40, "muted")
                if n.node_id in self._isolated_nodes:
                    add_line("[AISLADO DE 31] : Sin ruta activa hacia la PTAR", "alert")
                add_line(f"Tuberías entrantes : {', '.join(in_p) or 'Ninguna (Fuente)'}")
                add_line(f"Tuberías salientes : {', '.join(out_p) or 'Ninguna (PTAR 31)'}")
                if snap and n.node_id in snap.node_states:
                    ns = snap.node_states[n.node_id]
                    cap_p = self.result.config.max_manhole_storage_m3 if self.result else 4.0
                    add_line("")
                    add_line(f"Estado en t = {snap.time_min:.1f} min", "section")
                    add_line(f"Caudal entrada  : {ns.inflow_m3s:.5f} m³/s")
                    add_line(f"Caudal salida   : {ns.outflow_m3s:.5f} m³/s")
                    add_line(
                        f"Vol. en pozo    : {ns.stored_volume_m3:.3f} m³ (máx {cap_p:.1f} m³)",
                        "alert" if ns.stored_volume_m3 > 1e-3 else None,
                    )
                    add_line(
                        f"Rebose en vía   : {ns.surface_flooding_m3:.2f} m³",
                        "alert" if ns.surface_flooding_m3 > 1e-3 else None,
                    )
            else:
                add_line("Seleccione una tubería o pozo del grafo para inspeccionarlo.", "muted")

            add_line("")
            add_line("RESUMEN DEL ESCENARIO", "section")
            add_line("─" * 40, "muted")
            if self.result and snap:
                cfg = self.result.config
                scen_es = theme.translate_scenario_name(cfg.scenario_name)
                src_es = theme.SOURCE_DIST_TO_ES.get(cfg.source_distribution, cfg.source_distribution)
                add_line(f"Escenario       : {cfg.scenario_id} — {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)")
                add_line(f"Cuenca          : C={self.dataset.basin.runoff_coefficient_c}, A={self.dataset.basin.area_ha} ha")
                add_line(f"Ingreso / Fuent.: {cfg.ingress_factor*100:.1f}% · {src_es} | Q_san={cfg.dry_weather_flow_per_source_m3s:.4f}")
                add_line(f"Entrada acum.   : {snap.cumulative_inflow_m3:,.2f} m³")
                add_line(f"Descarga PTAR 31: {snap.cumulative_sink_discharge_m3:,.2f} m³ (pico {self.result.peak_sink_discharge_m3s:.4f} m³/s)")
                add_line(f"Pozos / Tránsito: {snap.total_manhole_storage_m3:,.2f} / {snap.total_pipe_transit_m3:,.2f} m³")
                add_line(
                    f"Rebose superf.  : {snap.total_surface_flooding_m3:,.2f} m³",
                    "alert" if snap.total_surface_flooding_m3 > 1e-3 else None,
                )
                add_line(f"Error balance   : {self.result.max_mass_balance_error_m3:.3e} m³")
                add_line(f"Crít. (>75–100%): {len(self.result.ever_near_capacity_pipes)} tuberías")
                add_line(f"Sobrec. (>100%) : {len(self.result.ever_overloaded_pipes)} tuberías")
                if self._interventions:
                    add_line(
                        f"Intervenciones  : {', '.join(sorted(self._interventions))} ({len(self._isolated_nodes)} aislados)",
                        "alert" if self._isolated_nodes else "section",
                    )

        self.txt_inspector.configure(state=tk.DISABLED)

    def _refresh_source_attribution_panel(self) -> None:
        if self.dataset is None or (not self._selected_pipe_id and not self._selected_node_id):
            self._current_source_shares = []
            return

        g = self.dataset.graph
        snap = self.result.snapshots[self.current_step] if self.result else None
        qmax_over = (
            {
                pid: ps.effective_q_max_m3s
                for pid, ps in snap.pipe_states.items()
                if ps.effective_q_max_m3s is not None
            }
            if snap is not None
            else None
        )
        split_rule = self.var_split_rule.get()
        source_dist = self.var_source_dist.get()
        entity_kind = "pipe" if self._selected_pipe_id else "node"
        entity_id = self._selected_pipe_id or self._selected_node_id or ""
        attr_key = (
            id(g),
            id(snap),
            split_rule,
            source_dist,
            entity_kind,
            entity_id,
            tuple(sorted(self._interventions.items(), key=lambda kv: kv[0])),
        )
        if attr_key == self._last_attr_key:
            return
        self._last_attr_key = attr_key

        attr = compute_source_attribution(
            g,
            snapshot=snap,
            split_rule=split_rule,
            pipe_qmax_overrides=qmax_over,
            source_distribution=source_dist,
        )
        self._source_attribution = attr
        if entity_kind == "pipe":
            shares = attr.pipe_shares.get(entity_id, [])
            ent_lbl = f"Tramo {entity_id}"
        else:
            shares = attr.node_shares.get(entity_id, [])
            ent_lbl = f"PTAR {entity_id}" if entity_id == "31" else f"Pozo {entity_id}"
        self.lbl_source_entity.configure(text=ent_lbl)
        self._current_source_shares = list(shares)

        if not shares:
            self.lbl_source_breakdown.configure(text="Sin aporte de fuentes hacia esta entidad.")
        else:
            split_es = "Proporcional" if split_rule == "proportional" else "Equitativa"
            parts = [f"F{src}: {frac * 100.0:.1f}%" for src, frac in shares]
            self.lbl_source_breakdown.configure(
                text=" · ".join(parts) + f"\nBifurcación: {split_es}"
            )
        self._redraw_source_bar_canvas()

    def _redraw_source_bar_canvas(self) -> None:
        c = self.canvas_source_bar
        c.delete("all")
        w = max(120, c.winfo_width() if c.winfo_width() > 10 else self._px(320))
        h = max(14, c.winfo_height() if c.winfo_height() > 8 else self._px(18))
        shares = self._current_source_shares
        if not shares:
            c.create_text(
                w / 2.0,
                h / 2.0,
                text="Sin mezcla activa",
                fill=theme.INK_MUTED,
                font=(self.mono_font, 7),
            )
            return

        mono_tones = [
            "#4A4A4A",
            "#6D8196",
            "#5A6570",
            "#9BA5B0",
            "#CBCBCB",
            "#7D8E9F",
            "#3A3A3A",
            "#B3B8BE",
        ]
        x_cur = 0.0
        for idx, (src_id, frac) in enumerate(shares):
            seg_w = (w - x_cur) if idx == len(shares) - 1 else (w * frac)
            if seg_w < 1.0:
                continue
            tone = mono_tones[idx % len(mono_tones)]
            x1 = x_cur + seg_w
            c.create_rectangle(x_cur, 0, x1, h, fill=tone, outline="")
            if idx < len(shares) - 1:
                c.create_line(x1, 0, x1, h, fill=theme.PAPER_BG, width=1.5)
            if seg_w >= 34:
                txt_col = theme.INK_PRIMARY if tone in ("#CBCBCB", "#B3B8BE") else theme.PAPER_BG
                c.create_text(
                    (x_cur + x1) / 2.0,
                    h / 2.0,
                    text=f"F{src_id} {frac * 100.0:.0f}%",
                    fill=txt_col,
                    font=(self.mono_font, 7, "bold"),
                )
            x_cur = x1
