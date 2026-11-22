"""Pestaña Comparación: botón de recálculo con estado dirty, tabla de 8+ columnas con scroll y gráficas."""

import time
import tkinter as tk
from tkinter import font as tkfont, ttk
from typing import Callable, Dict, List, Optional, Tuple

from src.simulation.comparison import ScenarioSummary
from . import theme
from .charts_panel import ComparisonChartsPanel

# (id, encabezado, ancla, texto de muestra para medir el ancho mínimo)
_COLUMNS: Tuple[Tuple[str, str, str, str], ...] = (
    ("esc", "Escenario", "w", "E3 Lluvia moderada"),
    ("int", "mm/h", "center", "100"),
    ("max_u", "Máx %", "e", "1000.0%"),
    ("ratio", "Razón Máx", "e", "1000.0%"),
    ("crit_p", "Crítica", "center", "P000"),
    ("n_crit", ">75–100%", "center", ">75–100%"),
    ("n_over", ">100%", "center", ">100%"),
    ("ptar", "Pico PTAR", "e", "0.0000"),
    ("flood", "Rebose (m³)", "e", "1,000,000.0"),
)
_BTN_CLEAN, _BTN_DIRTY = "Recalcular 5 Escenarios", "Recalcular 5 Escenarios *"
_HINT_DEFAULT = "Doble clic activa escenario"


class ComparisonPanel(tk.Frame):
    """Comparativa de los 5 escenarios: recálculo bajo demanda, tabla desplazable y gráficas comparativas."""

    def __init__(
        self, parent: tk.Misc, fonts: Dict[str, Tuple[str, int, str]],
        on_recalc: Callable[[], None], on_activate_scenario: Callable[[int], None],
    ) -> None:
        super().__init__(parent, bg=theme.PAPER_BG)
        self._fonts = fonts
        self._on_recalc = on_recalc
        self._on_activate = on_activate_scenario
        self._summaries: Optional[List[ScenarioSummary]] = None
        self._elapsed_ms: Optional[float] = None
        self._computed_at: Optional[str] = None
        self._dirty = False
        self._render_pending = False
        self._is_visible = True
        self._recalculating = False
        self._row_scenario: Dict[str, int] = {}

        small = fonts.get("small", ("TkDefaultFont", 8, "normal"))
        label = fonts.get("label", ("TkDefaultFont", 9, "bold"))
        body = fonts.get("body", ("TkDefaultFont", 9, "normal"))
        self._cell_font = tkfont.Font(family=body[0], size=abs(int(body[1])))
        self._head_font = tkfont.Font(family=label[0], size=abs(int(label[1])), weight="bold")

        top = tk.Frame(self, bg=theme.PAPER_SUBTLE)
        top.pack(side=tk.TOP, fill=tk.X)
        tk.Frame(self, bg=theme.DOCK_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)
        self._btn = tk.Button(top, text=_BTN_CLEAN, command=self._recalc_clicked, relief="flat", bd=0, padx=10, pady=4,
                              cursor="hand2", font=small, highlightthickness=1, highlightbackground=theme.DOCK_BORDER)
        self._btn.pack(side=tk.LEFT, padx=8, pady=6)
        self._hint = tk.Label(top, text=_HINT_DEFAULT, bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED, font=small, anchor="e")
        self._hint.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=8)
        self._style_button()

        wrap = tk.Frame(self, bg=theme.PAPER_BG)
        wrap.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(4, 4))
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        self._col_min: Dict[str, int] = {}
        self._tree = ttk.Treeview(wrap, columns=[c[0] for c in _COLUMNS], show="headings", height=5, selectmode="browse")
        for cid, head, anchor, sample in _COLUMNS:
            self._col_min[cid] = max(self._head_font.measure(head), self._cell_font.measure(sample)) + 20
            self._tree.heading(cid, text=head, anchor=anchor)
            self._tree.column(cid, width=self._col_min[cid], minwidth=self._col_min[cid], stretch=False, anchor=anchor)
        self._yscroll = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self._tree.yview)
        self._xscroll = ttk.Scrollbar(wrap, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(xscrollcommand=self._xscroll.set, yscrollcommand=self._yscroll.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        self._yscroll.grid(row=0, column=1, sticky="ns")
        self._xscroll.grid(row=1, column=0, sticky="ew")
        self._tree.tag_configure("odd", background=theme.PAPER_ALT_ROW)
        self._tree.tag_configure("crit", foreground=theme.TIER_TEXT_ON_LIGHT["#ef4444"])
        self._tree.tag_configure("over", foreground=theme.TIER_TEXT_ON_LIGHT["#991b1b"])
        self._tree.bind("<Double-1>", self._on_row_activate)
        self._tree.bind("<Return>", self._on_row_activate)
        self._tree.bind("<Configure>", self._resize_columns)
        self._tree.bind("<Shift-MouseWheel>", self._on_shift_wheel)
        self._tree.bind("<Shift-Button-4>", lambda e: self._on_shift_wheel(e, -1))
        self._tree.bind("<Shift-Button-5>", lambda e: self._on_shift_wheel(e, 1))

        self.charts = ComparisonChartsPanel(self, fonts)
        self.charts.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

    # ----------------------------------------------------------------------- API pública
    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def tree(self) -> ttk.Treeview:
        return self._tree

    def set_dirty(self, dirty: bool) -> None:
        """Marca (o limpia) cambios de parámetros pendientes; resalta el botón de recálculo."""
        self._dirty = bool(dirty)
        self._style_button()
        if self._dirty and self._summaries:
            self._hint.configure(text="Parámetros modificados · Recalcular", fg=theme.TIER_TEXT_ON_LIGHT["#f97316"])
        elif not self._dirty:
            self._refresh_hint()

    def set_comparisons(
        self, summaries: Optional[List[ScenarioSummary]], elapsed_ms: Optional[float] = None, is_visible: bool = True,
    ) -> None:
        """Actualiza resultados; difiere el render (tabla y gráficas) si el panel está oculto."""
        self._summaries = list(summaries) if summaries else None
        self._elapsed_ms = elapsed_ms
        self._is_visible = bool(is_visible)
        if self._summaries:
            self._computed_at = time.strftime("%H:%M:%S")
        else:
            self._computed_at = None
        self.set_dirty(self._summaries is None)
        if not self._summaries:
            self._hint.configure(text=_HINT_DEFAULT, fg=theme.INK_MUTED)
        if not self._is_visible:
            self._render_pending = True
            return
        self._render()

    def invalidate(self) -> None:
        """Cambiaron los parámetros base: la comparación debe recalcularse."""
        self.set_dirty(True)
        if not self._summaries:
            self._hint.configure(text="Sin comparar · se calcula al entrar", fg=theme.INK_MUTED)

    def mark_visible(self) -> None:
        """Al hacerse visible: auto-recalcula si hay cambios pendientes o no hay datos; renderiza lo diferido."""
        self._is_visible = True
        if (self._dirty or not self._summaries) and not self._recalculating:
            self._recalculating = True
            try:
                self._on_recalc()
            finally:
                self._recalculating = False
        if self._render_pending:
            self._render()

    # ----------------------------------------------------------------------- internos
    def _recalc_clicked(self) -> None:
        self._on_recalc()

    def _style_button(self) -> None:
        if self._dirty and self._summaries:
            self._btn.configure(text=_BTN_DIRTY, bg=theme.ACCENT_PRIMARY, fg=theme.ACCENT_INK,
                                activebackground=theme.ACCENT_HOVER, activeforeground=theme.ACCENT_INK)
        else:
            self._btn.configure(text=_BTN_CLEAN, bg=theme.PAPER_BG, fg=theme.INK_PRIMARY,
                                activebackground=theme.PAPER_HOVER, activeforeground=theme.INK_PRIMARY)

    def _refresh_hint(self) -> None:
        if self._summaries and self._computed_at:
            dur = f" · {self._elapsed_ms:.0f} ms" if self._elapsed_ms is not None else ""
            self._hint.configure(text=f"Calculado {self._computed_at}{dur} · Doble clic activa", fg=theme.INK_MUTED)
        else:
            self._hint.configure(text=_HINT_DEFAULT, fg=theme.INK_MUTED)

    def _on_row_activate(self, event: Optional[tk.Event] = None) -> None:
        iid = ""
        if event is not None and getattr(event, "y", None) is not None and getattr(event, "type", None) is not None:
            try:
                iid = self._tree.identify_row(event.y)
            except tk.TclError:
                iid = ""
        if not iid:
            sel = self._tree.selection()
            iid = sel[0] if sel else ""
        sc_id = self._row_scenario.get(iid)
        if sc_id is not None:
            self._on_activate(sc_id)

    def _on_shift_wheel(self, event: tk.Event, direction: int = 0) -> str:
        """Shift + rueda = desplazamiento horizontal de la tabla."""
        delta = getattr(event, "delta", 0) or 0
        if direction:
            steps = direction
        elif delta:
            steps = int(-delta / 120) if abs(delta) >= 120 else (-1 if delta > 0 else 1)
        else:
            steps = 0
        if steps:
            self._tree.xview_scroll(steps, "units")
        return "break"

    def _resize_columns(self, event: tk.Event) -> None:
        """Reparte el ancho sobrante proporcionalmente sin bajar nunca del mínimo medido."""
        total = sum(self._col_min.values())
        extra = max(0, event.width - 2 - total)
        for cid, _h, anchor, _s in _COLUMNS:
            w = self._col_min[cid] + int(extra * self._col_min[cid] / total)
            self._tree.column(cid, width=w, minwidth=self._col_min[cid], stretch=False, anchor=anchor)

    def _fit_columns_to_values(self, rows: List[Tuple[str, ...]]) -> None:
        """Ajusta el mínimo de cada columna al texto real (nombres de escenario sin recortes)."""
        for i, (cid, head, _a, sample) in enumerate(_COLUMNS):
            widest = max([self._cell_font.measure(sample)] + [self._cell_font.measure(r[i]) for r in rows])
            self._col_min[cid] = max(self._head_font.measure(head), widest) + 20
            self._tree.column(cid, minwidth=self._col_min[cid], width=max(int(self._tree.column(cid, "width")), self._col_min[cid]))

    def _populate_table(self, summaries: List[ScenarioSummary]) -> None:
        self._tree.delete(*self._tree.get_children())
        self._row_scenario.clear()
        rows: List[Tuple[str, ...]] = []
        for s in summaries:
            cond = theme.translate_scenario_name(s.condition)
            ratio = max(s.max_demand_ratio_pct, s.max_utilization_pct)
            rows.append((
                f"E{s.scenario_id} {cond}", f"{s.intensity_mm_h:.0f}", f"{s.max_utilization_pct:.1f}%", f"{ratio:.1f}%",
                s.most_critical_pipe, str(s.num_near_capacity_pipes), str(s.num_overloaded_pipes),
                f"{s.peak_sink_discharge_m3s:.4f}", f"{s.total_surface_flooding_m3:,.1f}",
            ))
        self._fit_columns_to_values(rows)
        for idx, (s, vals) in enumerate(zip(summaries, rows)):
            tags = ["odd"] if idx % 2 else []
            if s.num_overloaded_pipes > 0:
                tags.append("over")
            elif s.num_near_capacity_pipes > 0:
                tags.append("crit")
            iid = f"sc_{s.scenario_id}"
            self._row_scenario[iid] = s.scenario_id
            self._tree.insert("", tk.END, iid=iid, tags=tuple(tags), values=vals)

    def _render(self) -> None:
        self._render_pending = False
        self._populate_table(self._summaries or [])
        self.charts.update_comparison(self._summaries)
