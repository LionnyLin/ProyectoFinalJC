"""Módulo de la pestaña Comparación de Escenarios (tabla + gráficas comparativas)."""

import time
import tkinter as tk
from tkinter import font as tkfont, messagebox, ttk
from typing import List, Tuple

from src.simulation import compare_all_scenarios
from . import theme
from .charts_panel import ComparisonChartsPanel


class ComparisonPanelMixin:
    """Construye y actualiza la pestaña Comparación entre los 5 escenarios."""

    def _build_comparison_tab(self, notebook: ttk.Notebook) -> None:
        tab_comp = ttk.Frame(notebook)
        notebook.add(tab_comp, text="Comparación")

        comp_top = tk.Frame(tab_comp, bg=theme.PAPER_SUBTLE)
        comp_top.pack(fill=tk.X)
        tk.Frame(tab_comp, bg=theme.DOCK_BORDER, height=1).pack(fill=tk.X)
        self.btn_compare_scenarios = self._make_btn(
            comp_top,
            "Recalcular 5 Escenarios",
            self._action_compare_scenarios,
            variant="light_secondary",
            padx=10,
            pady=4,
            font_size=8,
        )
        self.btn_compare_scenarios.pack(side=tk.LEFT, padx=8, pady=6)
        self.lbl_comp_hint = tk.Label(
            comp_top,
            text="Doble clic activa escenario",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_MUTED,
            font=(self.ui_font, 8),
        )
        self.lbl_comp_hint.pack(side=tk.RIGHT, padx=8)

        comp_font = tkfont.Font(family=self.ui_font, size=9)
        self._comp_col_specs: List[Tuple[str, str, str, int]] = [
            ("esc", "Escenario", "w", max(155, comp_font.measure("E3 Lluvia moderada") + 24)),
            ("int", "mm/h", "center", max(52, comp_font.measure("mm/h") + 18)),
            ("max_u", "Máx %", "e", max(68, comp_font.measure("1000.0%") + 18)),
            ("crit_p", "Crítica", "center", max(56, comp_font.measure("Crítica") + 18)),
            ("n_crit", ">75–100%", "center", max(74, comp_font.measure(">75–100%") + 18)),
            ("n_over", ">100%", "center", max(62, comp_font.measure(">100%") + 18)),
            ("ptar", "Pico PTAR", "e", max(80, comp_font.measure("Pico PTAR") + 18)),
            ("flood", "Rebose (m³)", "e", max(92, comp_font.measure("Rebose (m³)") + 18)),
        ]
        comp_cols = tuple(cid for cid, _, _, _ in self._comp_col_specs)
        self._comp_tree_compact = False

        comp_table_wrap = tk.Frame(tab_comp, bg=theme.PAPER_BG)
        comp_table_wrap.pack(fill=tk.X, padx=6, pady=(4, 4))
        comp_table_wrap.columnconfigure(0, weight=1)
        comp_table_wrap.rowconfigure(0, weight=1)

        self.tree_comp = ttk.Treeview(
            comp_table_wrap, columns=comp_cols, show="headings", height=5
        )
        self.tree_comp.tag_configure("odd", background=theme.PAPER_ALT_ROW)
        for cid, htext, anchor, min_w in self._comp_col_specs:
            self.tree_comp.heading(cid, text=htext)
            self.tree_comp.column(
                cid, width=min_w, minwidth=min_w, stretch=False, anchor=anchor
            )

        self.comp_yscroll = ttk.Scrollbar(
            comp_table_wrap,
            orient=tk.VERTICAL,
            command=self.tree_comp.yview,
            style="Light.Vertical.TScrollbar",
        )
        self.comp_xscroll = ttk.Scrollbar(
            comp_table_wrap,
            orient=tk.HORIZONTAL,
            command=self.tree_comp.xview,
            style="Light.Horizontal.TScrollbar",
        )
        self.tree_comp.configure(
            xscrollcommand=self.comp_xscroll.set,
            yscrollcommand=self.comp_yscroll.set,
        )
        self.tree_comp.grid(row=0, column=0, sticky="nsew")
        self.comp_yscroll.grid(row=0, column=1, sticky="ns")
        self.comp_xscroll.grid(row=1, column=0, sticky="ew")

        self.tree_comp.bind("<Double-1>", self._on_comparison_row_activate)
        self.tree_comp.bind("<Configure>", self._resize_comp_columns)
        self.tree_comp.bind("<Shift-MouseWheel>", self._on_comp_shift_wheel)

        self.comparison_charts = ComparisonChartsPanel(tab_comp, dpi=self._mpl_dpi)
        self.comparison_charts.pack(fill=tk.BOTH, expand=True)

    def _resize_comp_columns(self, event: tk.Event) -> None:
        if not hasattr(self, "_comp_col_specs"):
            return
        avail_w = max(220, event.width - 2)
        total_min = sum(min_w for _, _, _, min_w in self._comp_col_specs)
        extra = max(0, avail_w - total_min)
        for cid, _htext, anchor, min_w in self._comp_col_specs:
            share = int(extra * (min_w / total_min)) if extra > 0 else 0
            col_w = min_w + share
            self.tree_comp.column(
                cid, width=col_w, minwidth=min_w, stretch=False, anchor=anchor
            )

    def _on_comp_shift_wheel(self, event: tk.Event) -> str:
        delta = getattr(event, "delta", 0)
        if delta != 0:
            steps = int(-1 * (delta / 120)) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
            self.tree_comp.xview_scroll(steps, "units")
        return "break"

    def _mark_comparisons_dirty(self) -> None:
        self._comparisons_dirty = True
        if hasattr(self, "btn_compare_scenarios") and self.comparisons:
            self.btn_compare_scenarios.configure(text="Recalcular 5 Escenarios *")
            self._set_btn_variant(self.btn_compare_scenarios, "primary")
        if hasattr(self, "lbl_comp_hint") and self.comparisons:
            self.lbl_comp_hint.configure(
                text="Parámetros modificados · Recalcular", fg=theme.STATUS_WARN_LIGHT
            )

    def _populate_comp_tree(self) -> None:
        for item in self.tree_comp.get_children():
            self.tree_comp.delete(item)
        for idx, s in enumerate(self.comparisons):
            cond = theme.translate_scenario_name(s.condition, compact=False)
            self.tree_comp.insert(
                "",
                tk.END,
                iid=str(s.scenario_id),
                tags=("odd",) if idx % 2 == 1 else (),
                values=(
                    f"E{s.scenario_id} {cond}",
                    f"{s.intensity_mm_h:.0f}",
                    f"{s.max_utilization_pct:.1f}%",
                    s.most_critical_pipe,
                    s.num_near_capacity_pipes,
                    s.num_overloaded_pipes,
                    f"{s.peak_sink_discharge_m3s:.4f}",
                    f"{s.total_surface_flooding_m3:,.1f}",
                ),
            )

    def _action_compare_scenarios(self) -> None:
        if self.dataset is None:
            return
        try:
            cfg = self._build_sim_config()
        except Exception as exc:
            messagebox.showerror("Parámetros inválidos", f"Revise los parámetros numéricos: {exc}")
            return

        t_start = time.perf_counter()
        self.comparisons = compare_all_scenarios(self.dataset, cfg)
        elapsed_ms = (time.perf_counter() - t_start) * 1000.0
        self._comparisons_dirty = False
        if hasattr(self, "btn_compare_scenarios"):
            self.btn_compare_scenarios.configure(text="Recalcular 5 Escenarios")
            self._set_btn_variant(self.btn_compare_scenarios, "light_secondary")
        self.lbl_comp_hint.configure(
            text=f"Al día ({elapsed_ms:.0f} ms) · Doble clic activa",
            fg=theme.INK_MUTED,
        )

        self._populate_comp_tree()
        self.comparison_charts.update_comparison(self.comparisons)
        self.status_var.set(f"Comparación de los 5 escenarios recalculada en {elapsed_ms:.0f} ms.")

    def _on_comparison_row_activate(self, _event: tk.Event) -> None:
        if self.dataset is None:
            return
        sel = self.tree_comp.selection()
        if not sel:
            return
        try:
            sid = int(sel[0])
        except ValueError:
            return
        for sc in self.dataset.scenarios:
            if sc.scenario_id == sid:
                self.var_scenario.set(
                    theme.format_scenario_display(sc.scenario_id, sc.condition, sc.intensity_mm_h)
                )
                self.run_simulation()
                return
