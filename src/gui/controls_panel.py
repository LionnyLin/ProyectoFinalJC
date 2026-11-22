"""Módulo del panel izquierdo de controles (Simulación, Recorridos BFS/DFS, Leyenda y Scroll)."""

import tkinter as tk
from tkinter import messagebox, ttk
from typing import List, Optional

from src.algorithms import (
    OVERLOAD_PERSISTENCE_LEVELS,
    bfs_anim_frames,
    classify_overload_persistence,
    classify_utilization,
    dfs_anim_frames,
    search_entities,
    trace_downstream,
    trace_upstream,
)
from src.simulation import TimeStepSnapshot
from . import theme
from .widgets import _ScenarioMenuButton


class ControlsPanelMixin:
    """Construye y controla el muelle izquierdo (parámetros, leyenda, búsqueda y recorridos)."""

    def _update_left_scrollregion(self, event: Optional[tk.Event] = None) -> None:
        if not hasattr(self, "left_canvas") or not self.left_canvas.winfo_exists():
            return
        try:
            cw = (
                event.width
                if (event is not None and event.widget is self.left_canvas and event.width > 1)
                else self.left_canvas.winfo_width()
            )
            cw = max(1, cw)
            ch = max(1, self.left_canvas.winfo_height())
            self.left_canvas.itemconfigure(self._left_window_id, width=cw)
            req_h = max(1, self.left_frame.winfo_reqheight())
            sr_h = max(ch, req_h)
            self.left_canvas.configure(scrollregion=(0, 0, cw, sr_h))
            if req_h <= ch:
                self.left_canvas.yview_moveto(0.0)
        except tk.TclError:
            pass

    def _scroll_left_canvas(self, units: int) -> None:
        if units == 0 or not hasattr(self, "left_canvas") or not self.left_canvas.winfo_exists():
            return
        try:
            req_h = self.left_frame.winfo_reqheight()
            ch = self.left_canvas.winfo_height()
            if req_h <= ch:
                self.left_canvas.yview_moveto(0.0)
                return
            top, bottom = self.left_canvas.yview()
            if units < 0 and top <= 0.0:
                self.left_canvas.yview_moveto(0.0)
                return
            if units > 0 and bottom >= 1.0:
                return
            self.left_canvas.yview_scroll(units, "units")
        except tk.TclError:
            pass

    def _on_left_panel_leave(self, event: tk.Event) -> None:
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
            if widget is not None and (
                self._is_descendant(widget, self.left_panel)
                or widget.winfo_class() in ("Menu", "Listbox", "ComboboxPopdownFrame")
            ):
                return
        except (KeyError, tk.TclError):
            pass
        self._bind_left_mousewheel(False)

    def _bind_left_mousewheel(self, active: bool) -> None:
        if not hasattr(self, "left_canvas") or not self.left_canvas.winfo_exists():
            return
        if active:
            self.left_canvas.bind_all("<MouseWheel>", self._on_left_wheel)
            self.left_canvas.bind_all("<Button-4>", lambda e: self._on_left_wheel_linux(e, -1))
            self.left_canvas.bind_all("<Button-5>", lambda e: self._on_left_wheel_linux(e, 1))
        else:
            self.left_canvas.unbind_all("<MouseWheel>")
            self.left_canvas.unbind_all("<Button-4>")
            self.left_canvas.unbind_all("<Button-5>")

    def _on_left_wheel_linux(self, event: tk.Event, units: int) -> None:
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        if widget is not None and self._is_descendant(widget, self.left_panel):
            self._scroll_left_canvas(units)

    def _on_left_wheel(self, event: tk.Event) -> None:
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
        except (KeyError, tk.TclError):
            return
        if widget is not None and self._is_descendant(widget, self.left_panel):
            delta = getattr(event, "delta", 0)
            if delta == 0:
                return
            if abs(delta) >= 120:
                steps = int(-1 * (delta / 120))
            else:
                steps = -1 if delta > 0 else 1
            self._scroll_left_canvas(steps)

    @staticmethod
    def _is_descendant(widget: tk.Misc, ancestor: tk.Misc) -> bool:
        cur: Optional[tk.Misc] = widget
        while cur is not None:
            if cur is ancestor:
                return True
            cur = getattr(cur, "master", None)
        return False

    def _make_rail_section(
        self,
        parent: tk.Misc,
        title: str,
        dark_header: bool = True,
    ) -> tk.Frame:
        """Crea una lámina estructurada (#FFFFE3) enmarcada en grafito (#4A4A4A) sobre el muelle plata."""
        sheet = tk.Frame(
            parent,
            bg=theme.PAPER_BG,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )
        sheet.pack(fill=tk.X, padx=10, pady=(6, 4))

        hdr_bg = theme.SHELL_BG if dark_header else theme.ACCENT_PRIMARY
        hdr = tk.Frame(sheet, bg=hdr_bg)
        hdr.pack(fill=tk.X)
        hdr_lbl = tk.Label(
            hdr,
            text=title,
            bg=hdr_bg,
            fg=theme.SHELL_TEXT,
            font=(self.display_font, 9, "bold"),
            anchor="w",
            padx=10,
            pady=5,
        )
        hdr_lbl.pack(fill=tk.X)
        tk.Frame(sheet, bg=theme.ACCENT_PRIMARY if dark_header else theme.DOCK_BORDER, height=2).pack(fill=tk.X)

        body = tk.Frame(sheet, bg=theme.PAPER_BG)
        body.pack(fill=tk.X, padx=10, pady=8)
        body._header_lbl = hdr_lbl  # type: ignore[attr-defined]
        return body

    def _switch_rail_tab(self, tab_id: str) -> None:
        self._rail_tab = tab_id
        self._rail_sim_container.pack_forget()
        self._rail_trav_container.pack_forget()
        if tab_id == "trav":
            self._rail_trav_container.pack(fill=tk.X)
            self._set_btn_variant(self.btn_rail_sim, "light_secondary")
            self._set_btn_variant(self.btn_rail_trav, "primary")
        else:
            self._rail_sim_container.pack(fill=tk.X)
            self._set_btn_variant(self.btn_rail_sim, "primary")
            self._set_btn_variant(self.btn_rail_trav, "light_secondary")
        self.left_frame.update_idletasks()
        self._update_left_scrollregion()
        self.left_canvas.yview_moveto(0.0)

    def _build_left_controls(self, parent: tk.Frame) -> None:
        self._rail_sim_container = tk.Frame(parent, bg=theme.DOCK_BG)
        self._rail_trav_container = tk.Frame(parent, bg=theme.DOCK_BG)

        # Lámina 1 (Tab Simulación): Escenario y parámetros hidráulicos
        sec_sim = self._make_rail_section(
            self._rail_sim_container, "Escenario y parámetros", dark_header=True
        )

        tk.Label(
            sec_sim,
            text="Escenario de precipitación",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8, "bold"),
        ).pack(anchor="w", pady=(0, 3))
        self.combo_scenario = _ScenarioMenuButton(
            sec_sim,
            textvariable=self.var_scenario,
            on_select=lambda: self._on_simulation_option_changed(mark_comp=False),
            on_before_open=self._player_pause,
            ui_font=self.ui_font,
        )
        self.combo_scenario.pack(fill=tk.X, pady=(0, 8))

        grid = tk.Frame(sec_sim, bg=theme.PAPER_BG)
        grid.pack(fill=tk.X)
        fields = [
            ("Duración simulación (min)", self.var_duration, 10, 360, 10),
            ("Duración lluvia (min)", self.var_storm_dur, 0, 360, 5),
            ("Paso temporal Δt (min)", self.var_dt, 0.5, 10.0, 0.5),
            ("Ingreso pluvial (%)", self.var_ingress_pct, 0.5, 100.0, 0.5),
            ("Caudal sanitario (m³/s)", self.var_dry_flow, 0.0, 0.05, 0.001),
        ]
        for row_i, (label, var, frm, to, inc) in enumerate(fields):
            tk.Label(
                grid,
                text=label,
                bg=theme.PAPER_BG,
                fg=theme.INK_PRIMARY,
                font=(self.ui_font, 8),
            ).grid(row=row_i, column=0, sticky="w", pady=2)
            sb = tk.Spinbox(
                grid,
                textvariable=var,
                from_=frm,
                to=to,
                increment=inc,
                command=self._schedule_param_rerun,
                width=8,
                bg=theme.PAPER_BG,
                fg=theme.INK_PRIMARY,
                buttonbackground=theme.DOCK_BG,
                insertbackground=theme.ACCENT_PRIMARY,
                highlightthickness=1,
                highlightbackground=theme.DOCK_BORDER,
                highlightcolor=theme.ACCENT_PRIMARY,
                relief="flat",
                font=(self.mono_font, 9),
            )
            sb.grid(row=row_i, column=1, sticky="e", pady=2)
            sb.bind("<Return>", lambda _e: self._on_simulation_option_changed(mark_comp=True))
            sb.bind("<FocusOut>", lambda _e: self._schedule_param_rerun())
        grid.columnconfigure(0, weight=1)

        preset_row = tk.Frame(sec_sim, bg=theme.PAPER_BG)
        preset_row.pack(fill=tk.X, pady=(8, 4))
        self._make_btn(
            preset_row,
            "Oficial Guía (100%)",
            lambda: self._apply_preset(100.0, 0.0),
            variant="dock_secondary",
            padx=6,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        self._make_btn(
            preset_row,
            "Calibrado (2.5% + Q_san)",
            lambda: self._apply_preset(2.5, 0.003),
            variant="dock_secondary",
            padx=6,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        row_rules = tk.Frame(sec_sim, bg=theme.PAPER_BG)
        row_rules.pack(fill=tk.X, pady=3)
        tk.Label(
            row_rules,
            text="Bifurcación",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8),
        ).pack(side=tk.LEFT)
        self.combo_split_rule = _ScenarioMenuButton(
            row_rules,
            textvariable=self.var_split_rule_es,
            values=list(theme.SPLIT_RULE_TO_ES.values()),
            on_select=lambda: self._on_simulation_option_changed(mark_comp=True),
            on_before_open=self._player_pause,
            width=15,
            padx=6,
            pady=3,
            ui_font=self.ui_font,
        )
        self.combo_split_rule.pack(side=tk.RIGHT)

        row_src_dist = tk.Frame(sec_sim, bg=theme.PAPER_BG)
        row_src_dist.pack(fill=tk.X, pady=3)
        tk.Label(
            row_src_dist,
            text="Reparto fuentes",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8),
        ).pack(side=tk.LEFT)
        self.combo_source_dist = _ScenarioMenuButton(
            row_src_dist,
            textvariable=self.var_source_dist_es,
            values=list(theme.SOURCE_DIST_TO_ES.values()),
            on_select=lambda: self._on_simulation_option_changed(mark_comp=True),
            on_before_open=self._player_pause,
            width=15,
            padx=6,
            pady=3,
            ui_font=self.ui_font,
        )
        self.combo_source_dist.pack(side=tk.RIGHT)

        self.btn_run_sim = self._make_btn(
            sec_sim,
            " Ejecutar simulación",
            self._action_execute_simulation,
            variant="primary",
            pady=6,
            font_size=9,
            image=self._icons["play_on_accent"],
            compound=tk.LEFT,
        )
        self.btn_run_sim.pack(fill=tk.X, pady=(8, 0))

        # Lámina 2 (Tab Simulación): Escala oficial de utilización (Sección 7) / Estrés acumulado
        sec_leg = self._make_rail_section(
            self._rail_sim_container, "Escala oficial de utilización", dark_header=False
        )
        self._legend_header_label = getattr(sec_leg, "_header_lbl", None)
        self._legend_count_labels.clear()
        self._legend_text_labels.clear()
        short_desc = {
            "Cercana a capacidad máxima": "Cercana a cap. máx.",
        }
        for rng, color_hex, desc in theme.COLOR_SCALE_LEGEND:
            row = tk.Frame(sec_leg, bg=theme.PAPER_BG)
            row.pack(fill=tk.X, pady=2)
            swatch = tk.Frame(
                row,
                width=self._px(12),
                height=self._px(12),
                bg=color_hex,
                highlightthickness=1,
                highlightbackground=theme.DOCK_BORDER,
            )
            swatch.pack(side=tk.LEFT, padx=(0, 7))
            swatch.pack_propagate(False)
            cnt_lbl = tk.Label(
                row,
                text="0",
                bg=theme.DOCK_BG,
                fg=theme.INK_PRIMARY,
                font=(self.mono_font, 8, "bold"),
                width=3,
                anchor="center",
            )
            cnt_lbl.pack(side=tk.RIGHT, padx=(6, 0))
            txt_lbl = tk.Label(
                row,
                text=f"{rng} · {short_desc.get(desc, desc)}",
                bg=theme.PAPER_BG,
                fg=theme.INK_PRIMARY,
                font=(self.ui_font, 8),
                anchor="w",
            )
            txt_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self._legend_count_labels.append(cnt_lbl)
            self._legend_text_labels.append(txt_lbl)

        # Lámina 3 (Tab Recorridos): Consultas y recorridos BFS / DFS / Trazado
        sec_alg = self._make_rail_section(
            self._rail_trav_container, "Búsqueda y recorridos", dark_header=True
        )

        search_row = tk.Frame(sec_alg, bg=theme.PAPER_BG)
        search_row.pack(fill=tk.X, pady=(0, 8))
        self.entry_search = tk.Entry(
            search_row,
            textvariable=self.var_search,
            width=12,
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            insertbackground=theme.ACCENT_PRIMARY,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
            highlightcolor=theme.ACCENT_PRIMARY,
            relief="flat",
            font=(self.ui_font, 9),
        )
        self.entry_search.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        self.entry_search.bind("<Return>", lambda _e: self._action_search())
        self._make_btn(
            search_row,
            " Buscar",
            self._action_search,
            variant="primary",
            padx=9,
            pady=4,
            font_size=8,
            image=self._icons["search_ink"],
            compound=tk.LEFT,
        ).pack(side=tk.RIGHT, padx=(6, 0))

        trav_grid = tk.Frame(sec_alg, bg=theme.PAPER_BG)
        trav_grid.pack(fill=tk.X, pady=2)
        tk.Label(
            trav_grid,
            text="Nodo origen",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8),
        ).grid(row=0, column=0, sticky="w", pady=2)
        self.combo_bfs_start = ttk.Combobox(
            trav_grid, textvariable=self.var_bfs_start, width=10, style="Light.TCombobox"
        )
        self.combo_bfs_start.grid(row=0, column=1, sticky="e", pady=2)
        tk.Label(
            trav_grid,
            text="Nodo destino",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8),
        ).grid(row=1, column=0, sticky="w", pady=2)
        self.combo_bfs_target = ttk.Combobox(
            trav_grid, textvariable=self.var_bfs_target, width=10, style="Light.TCombobox"
        )
        self.combo_bfs_target.grid(row=1, column=1, sticky="e", pady=2)
        trav_grid.columnconfigure(0, weight=1)

        btn_trav_row1 = tk.Frame(sec_alg, bg=theme.PAPER_BG)
        btn_trav_row1.pack(fill=tk.X, pady=(8, 3))
        self._make_btn(
            btn_trav_row1,
            "BFS",
            lambda: self._run_traversal("BFS"),
            variant="dock_secondary",
            padx=6,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        self._make_btn(
            btn_trav_row1,
            "DFS",
            lambda: self._run_traversal("DFS"),
            variant="dock_secondary",
            padx=6,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        self._make_btn(
            btn_trav_row1,
            "Limpiar",
            self._clear_highlights,
            variant="dock_secondary",
            padx=6,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 0))

        self.btn_anim_traversal = self._make_btn(
            sec_alg,
            "Animar recorrido",
            self._action_toggle_traversal_anim,
            variant="primary",
            padx=8,
            pady=4,
            font_size=8,
        )
        self.btn_anim_traversal.pack(fill=tk.X, pady=(2, 3))

        btn_trav_row2 = tk.Frame(sec_alg, bg=theme.PAPER_BG)
        btn_trav_row2.pack(fill=tk.X, pady=(0, 2))
        for text, cmd in [
            ("Aguas abajo", lambda: self._run_trace("down")),
            ("Aguas arriba", lambda: self._run_trace("up")),
        ]:
            self._make_btn(
                btn_trav_row2, text, cmd, variant="dock_secondary", padx=5, pady=4, font_size=8
            ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)

        # Bitácora oscura (#4A4A4A) + Tira visual de Queue / Stack
        sec_log = self._make_rail_section(
            self._rail_trav_container, "Bitácora de recorrido", dark_header=False
        )

        self._struct_strip_box = tk.Frame(
            sec_log,
            bg=theme.PAPER_SUBTLE,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )
        self._struct_strip_box.pack(fill=tk.X, pady=(0, 6))
        self._lbl_struct_header = tk.Label(
            self._struct_strip_box,
            text="Queue (BFS) · FRENTE → FINAL",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_PRIMARY,
            font=(self.mono_font, 7, "bold"),
            anchor="w",
            padx=6,
            pady=3,
        )
        self._lbl_struct_header.pack(fill=tk.X)
        self._struct_cells_row = tk.Frame(self._struct_strip_box, bg=theme.PAPER_SUBTLE)
        self._struct_cells_row.pack(fill=tk.X, padx=5, pady=(0, 5))
        self._render_structure_strip("Queue", [])

        self.txt_traversal = tk.Text(
            sec_log,
            height=6,
            bg=theme.SHELL_BG,
            fg=theme.SHELL_TEXT,
            highlightthickness=1,
            highlightbackground=theme.ACCENT_PRIMARY,
            relief="flat",
            font=(self.mono_font, 8),
            wrap=tk.WORD,
            padx=8,
            pady=6,
        )
        self.txt_traversal.pack(fill=tk.X)
        self.txt_traversal.configure(state=tk.DISABLED)

        self._switch_rail_tab("sim")

    def _render_structure_strip(self, structure_name: str, items: List[str], step_text: str = "") -> None:
        for child in list(self._struct_cells_row.winfo_children()):
            child.destroy()

        if structure_name == "Stack":
            hdr = "Pila (Stack) · TOPE ↑"
        else:
            hdr = "Cola (Queue) · FRENTE → FINAL"
        if step_text:
            hdr = f"{hdr}  [{step_text}]"
        self._lbl_struct_header.configure(text=hdr)

        if not items:
            tk.Label(
                self._struct_cells_row,
                text="(vacía)",
                bg=theme.PAPER_BG,
                fg=theme.INK_MUTED,
                font=(self.mono_font, 7),
                padx=6,
                pady=2,
                highlightthickness=1,
                highlightbackground=theme.PAPER_BORDER,
            ).pack(side=tk.LEFT)
            return

        max_cells = 6
        shown = items[:max_cells]
        for idx, val in enumerate(shown):
            is_head = idx == 0
            tk.Label(
                self._struct_cells_row,
                text=str(val),
                bg=theme.ACCENT_PRIMARY if is_head else theme.PAPER_BG,
                fg=theme.ACCENT_INK if is_head else theme.INK_PRIMARY,
                font=(self.mono_font, 7, "bold"),
                padx=5,
                pady=2,
                highlightthickness=1,
                highlightbackground=theme.DOCK_BORDER,
            ).pack(side=tk.LEFT, padx=(0, 2))
        if len(items) > max_cells:
            tk.Label(
                self._struct_cells_row,
                text=f"+{len(items) - max_cells}",
                bg=theme.DOCK_BG,
                fg=theme.INK_PRIMARY,
                font=(self.mono_font, 7, "bold"),
                padx=4,
                pady=2,
                highlightthickness=1,
                highlightbackground=theme.DOCK_BORDER,
            ).pack(side=tk.LEFT)

    def _apply_preset(self, ingress_pct: float, dry_flow: float) -> None:
        self.var_ingress_pct.set(ingress_pct)
        self.var_dry_flow.set(dry_flow)
        self._on_simulation_option_changed(mark_comp=True)

    def _update_legend_counts(self, snap: TimeStepSnapshot) -> None:
        counts = [0, 0, 0, 0, 0]
        peak_all, ov_all, dur_total = self._global_stress_maps()
        if self._map_mode == "overload_minutes" and self.result is not None:
            if self._legend_header_label is not None:
                self._legend_header_label.configure(
                    text=f"Sobrecarga acumulada · 0–{dur_total:.0f} min"
                )
            for idx, (rng, _col, desc) in enumerate(OVERLOAD_PERSISTENCE_LEVELS):
                if idx < len(self._legend_text_labels):
                    self._legend_text_labels[idx].configure(text=f"{rng} · {desc}")
            for pid in snap.pipe_states:
                ov_m = ov_all.get(pid, 0.0)
                tier, _, _ = classify_overload_persistence(ov_m, dur_total)
                counts[tier] += 1
        else:
            if self._legend_header_label is not None:
                title = (
                    f"Escala oficial · t = {snap.time_min:.0f} min"
                    if self._map_mode == "instant"
                    else f"Pico máximo · 0–{dur_total:.0f} min"
                )
                self._legend_header_label.configure(text=title)
            short_desc = {"Cercana a capacidad máxima": "Cercana a cap. máx."}
            for idx, (rng, _col, desc) in enumerate(theme.COLOR_SCALE_LEGEND):
                if idx < len(self._legend_text_labels):
                    self._legend_text_labels[idx].configure(
                        text=f"{rng} · {short_desc.get(desc, desc)}"
                    )
            if self._map_mode == "peak" and self.result is not None:
                for pid in snap.pipe_states:
                    u = peak_all.get(pid, 0.0)
                    counts[classify_utilization(u).tier_index] += 1
            else:
                for ps in snap.pipe_states.values():
                    counts[ps.category.tier_index] += 1
        for lbl, c in zip(self._legend_count_labels, counts):
            lbl.configure(text=str(c))

    def _deactivate_focus_filters_for_traversal(self) -> None:
        """Limpia enfoque de guía o aislamiento de cuenca para que los recorridos/búsquedas sean visibles."""
        if self._tour_active:
            self._close_guided_tour(reset_view=False)
        if self._basin_isolated:
            self._basin_isolated = False
            self.network_canvas.set_basin_focus(None, None)
            if hasattr(self, "btn_isolate_basin"):
                self._set_btn_variant(self.btn_isolate_basin, "light_secondary")

    def _action_search(self) -> None:
        if self.dataset is None:
            return
        q = self.var_search.get().strip()
        if not q:
            return
        nodes, pipes = search_entities(self.dataset.graph, q)
        if not nodes and not pipes:
            messagebox.showinfo("Sin resultados", f"No se encontró nodo o tubería para '{q}'.")
            return

        self._inspector_trace_state = None
        self._sync_inspector_trace_buttons()
        self._stop_traversal_anim(clear_canvas=False)
        self._deactivate_focus_filters_for_traversal()
        exact_pipe = self.dataset.graph.get_pipe(q.upper()) or self.dataset.graph.get_pipe(q)
        exact_node = self.dataset.graph.get_node(q.upper()) or self.dataset.graph.get_node(q)
        if exact_pipe is not None:
            self.network_canvas.select_pipe(exact_pipe.pipe_id)
            self._on_pipe_selected(exact_pipe.pipe_id)
            self.network_canvas.focus_pipe(exact_pipe.pipe_id)
        elif exact_node is not None:
            self.network_canvas.select_node(exact_node.node_id)
            self._on_node_selected(exact_node.node_id)
            self.network_canvas.focus_node(exact_node.node_id)
        elif pipes:
            self.network_canvas.select_pipe(pipes[0].pipe_id)
            self._on_pipe_selected(pipes[0].pipe_id)
            self.network_canvas.focus_pipe(pipes[0].pipe_id)
        elif nodes:
            self.network_canvas.select_node(nodes[0].node_id)
            self._on_node_selected(nodes[0].node_id)
            self.network_canvas.focus_node(nodes[0].node_id)

        self.network_canvas.set_highlights(
            pipe_ids={p.pipe_id for p in pipes},
            node_ids={n.node_id for n in nodes},
        )
        self._set_traversal_text(
            f"[Búsqueda '{q}']\n"
            f"Nodos ({len(nodes)}): {', '.join(n.node_id for n in nodes[:12]) or '-'}\n"
            f"Tuberías ({len(pipes)}): {', '.join(p.pipe_id for p in pipes[:12]) or '-'}"
        )
        self.status_var.set(f"Búsqueda '{q}': {len(nodes)} nodo(s), {len(pipes)} tubería(s).")

    def _run_traversal(self, alg: str) -> None:
        if self.dataset is None:
            return
        self._inspector_trace_state = None
        self._sync_inspector_trace_buttons()
        self._stop_traversal_anim(clear_canvas=True)
        self._deactivate_focus_filters_for_traversal()
        self._last_traversal_alg = alg
        start = self.var_bfs_start.get().strip()
        target = self.var_bfs_target.get().strip() or None
        try:
            res, frames = (
                bfs_anim_frames(self.dataset.graph, start, target)
                if alg == "BFS"
                else dfs_anim_frames(self.dataset.graph, start, target)
            )
        except KeyError as exc:
            messagebox.showwarning("Nodo inválido", str(exc))
            return

        if res.path_pipes:
            hl_pipes = {p.pipe_id for p in res.path_pipes}
            hl_nodes = set(res.path_nodes)
            self._active_route_pipes = list(res.path_pipes)
        else:
            hl_pipes = {p.pipe_id for p in res.traversed_edges}
            hl_nodes = set(res.visited_order)
            self._active_route_pipes = []

        self.network_canvas.set_highlights(hl_pipes, hl_nodes)
        if frames:
            mid_fr = frames[min(1, len(frames) - 1)]
            self._render_structure_strip(
                mid_fr.structure_name,
                mid_fr.structure_items,
                f"muestra {res.algorithm}",
            )

        lines = [
            f"[{res.algorithm}] {start} → {target or 'toda la red'}",
            f"Visitados ({len(res.visited_order)}): {' → '.join(res.visited_order[:14])}"
            + (" ..." if len(res.visited_order) > 14 else ""),
        ]
        if target:
            if res.target_reached:
                lines.append(f"Ruta ({len(res.path_pipes)} tramos): {' → '.join(res.path_nodes)}")
                lines.append(f"Tuberías: {', '.join(p.pipe_id for p in res.path_pipes)}")
                total_t = sum(p.transit_time_min for p in res.path_pipes)
                lines.append(f"Tránsito acumulado: {total_t:.1f} min")
            else:
                lines.append(f"Sin camino dirigido desde {start} hasta {target}.")

        self._set_traversal_text("\n".join(lines))
        if self.result is not None and self.result.snapshots:
            self._push_temporal_charts(throttle_draw=False)

    def _action_toggle_traversal_anim(self) -> None:
        if self.dataset is None:
            return
        if self._is_animating_traversal:
            self._stop_traversal_anim(clear_canvas=False)
            return

        self._player_pause()
        self._deactivate_focus_filters_for_traversal()
        start = self.var_bfs_start.get().strip()
        target = self.var_bfs_target.get().strip() or None
        alg = self._last_traversal_alg
        try:
            res, frames = (
                bfs_anim_frames(self.dataset.graph, start, target)
                if alg == "BFS"
                else dfs_anim_frames(self.dataset.graph, start, target)
            )
        except KeyError as exc:
            messagebox.showwarning("Nodo inválido", str(exc))
            return

        if res.path_pipes:
            self._active_route_pipes = list(res.path_pipes)
        self._anim_frames = frames
        self._anim_idx = 0
        self._is_animating_traversal = True
        self.btn_anim_traversal.configure(text="Detener anim.")
        self._step_traversal_anim()

    def _step_traversal_anim(self) -> None:
        self._anim_after_id = None
        if not self._is_animating_traversal or not self._anim_frames:
            self._stop_traversal_anim(clear_canvas=False)
            return

        fr = self._anim_frames[self._anim_idx]
        self.network_canvas.set_traversal_frame(fr)
        self._render_structure_strip(
            fr.structure_name,
            fr.structure_items,
            f"{fr.step_index + 1}/{fr.total_steps}",
        )
        self._set_traversal_text(
            f"[{fr.algorithm} · Paso {fr.step_index + 1}/{fr.total_steps}]\n"
            f"{fr.note}\n"
            f"{fr.structure_name}: {', '.join(fr.structure_items[:10]) or '(vacía)'}"
        )

        self._anim_idx += 1
        if self._anim_idx >= len(self._anim_frames):
            self._is_animating_traversal = False
            self.btn_anim_traversal.configure(text="Animar recorrido")
            return
        delay = 560 if fr.algorithm == "BFS" else 340
        self._anim_after_id = self.after(delay, self._step_traversal_anim)

    def _stop_traversal_anim(self, clear_canvas: bool = True) -> None:
        self._is_animating_traversal = False
        if self._anim_after_id is not None:
            try:
                self.after_cancel(self._anim_after_id)
            except tk.TclError:
                pass
            self._anim_after_id = None
        if hasattr(self, "btn_anim_traversal"):
            self.btn_anim_traversal.configure(text="Animar recorrido")
        if clear_canvas and hasattr(self, "network_canvas"):
            self.network_canvas.set_traversal_frame(None)

    def _run_trace(self, direction: str) -> None:
        if self.dataset is None:
            return
        self._stop_traversal_anim(clear_canvas=True)
        self._deactivate_focus_filters_for_traversal()
        nid = self.var_bfs_start.get().strip()
        try:
            nodes, pipes = (
                trace_downstream(self.dataset.graph, nid)
                if direction == "down"
                else trace_upstream(self.dataset.graph, nid)
            )
        except KeyError as exc:
            messagebox.showwarning("Nodo inválido", str(exc))
            return
        self.network_canvas.set_highlights({p.pipe_id for p in pipes}, set(nodes))
        label = "Aguas abajo" if direction == "down" else "Aguas arriba"
        self._set_traversal_text(
            f"[{label} desde {nid}]\n"
            f"Nodos ({len(nodes)}): {', '.join(nodes)}\n"
            f"Tuberías ({len(pipes)}): {', '.join(p.pipe_id for p in pipes)}"
        )
        self.status_var.set(f"{label} desde {nid}: {len(nodes)} nodo(s), {len(pipes)} tubería(s).")

    def _clear_highlights(self) -> None:
        self._inspector_trace_state = None
        self._sync_inspector_trace_buttons()
        self._stop_traversal_anim(clear_canvas=True)
        self._active_route_pipes = []
        self._basin_isolated = False
        self.network_canvas.set_basin_focus(None, None)
        self.network_canvas.set_highlights(set(), set())
        self._render_structure_strip("Queue", [])
        self._set_traversal_text("")
        self._charts_tab_dirty = True
        if self._active_right_tab() == 2 and self.result is not None and self.result.snapshots:
            self._charts_tab_dirty = False
            self._push_temporal_charts(throttle_draw=False)
        self._refresh_inspector()

    def _set_traversal_text(self, text: str) -> None:
        self.txt_traversal.configure(state=tk.NORMAL)
        self.txt_traversal.delete("1.0", tk.END)
        self.txt_traversal.insert("1.0", text)
        self.txt_traversal.configure(state=tk.DISABLED)
