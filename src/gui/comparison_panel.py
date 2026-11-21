"""Panel de comparación multiescenario (tabla sin recortes + 2 gráficas comparativas)."""

import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from src.simulation.comparison import ScenarioSummary
from . import theme

_COLUMNS: Tuple[Tuple[str, str, int, str], ...] = (
    ("esc", "Esc.", 30, "center"), ("escenario", "Escenario", 62, "w"),
    ("intensidad", "I mm/h", 44, "e"), ("max_pct", "Máx.%", 52, "e"),
    ("crit", "Crít.", 34, "e"), ("sobr", "Sobr.", 36, "e"),
    ("pico", "PTAR", 46, "e"), ("rebose", "Rebose", 54, "e"),
)


def _fmt_pct(val: float) -> str:
    if val >= 10000.0:
        return f"{val / 1000.0:.1f}k%"
    if val >= 1000.0:
        return f"{val:.0f}%"
    return f"{val:.1f}%"


def _fmt_m3(val: float) -> str:
    if val >= 1000.0:
        return f"{val / 1000.0:.1f}k"
    return f"{val:.0f}"


def _style_sub(ax, title: str, ylabel: str) -> None:
    ax.set_facecolor(theme.PAPER_BG)
    ax.set_title(title, fontsize=8.0, fontweight="bold", color=theme.INK_PRIMARY, loc="left", pad=4)
    ax.set_ylabel(ylabel, fontsize=7.2, color=theme.INK_PRIMARY)
    ax.tick_params(axis="y", colors=theme.INK_PRIMARY, labelsize=6.9)
    ax.grid(True, axis="y", ls="--", lw=0.6, color=theme.CANVAS_GRID_MAJOR, alpha=0.85)
    ax.set_axisbelow(True)
    for name, sp in ax.spines.items():
        sp.set_color(theme.INK_PRIMARY)
        sp.set_linewidth(0.8 if name in ("left", "bottom") else 0.45)


class ComparisonPanel(tk.Frame):
    """Comparativa de los 5 escenarios de lluvia con carga rápida al visor principal."""

    def __init__(
        self, parent: tk.Misc, fonts: Dict[str, Tuple[str, int, str]],
        on_compare_clicked: Callable[[], None], on_select_scenario: Callable[[int], None],
    ) -> None:
        super().__init__(parent, bg=theme.PAPER_BG)
        self._fonts = fonts
        self._on_compare_clicked = on_compare_clicked
        self._on_select_scenario = on_select_scenario
        self._summaries: Optional[List[ScenarioSummary]] = None
        self._elapsed_ms: Optional[float] = None
        self._dirty = False
        self._is_visible = True
        self._populating = False
        self._row_scenario: Dict[str, int] = {}

        small_font = fonts.get("small", ("TkDefaultFont", 8, "normal"))
        label_font = fonts.get("label", ("TkDefaultFont", 9, "bold"))

        header = tk.Frame(self, bg=theme.PAPER_BG)
        header.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(6, 4))
        self._btn_compare = tk.Button(
            header, text="Comparar 5 escenarios", command=self._on_compare_clicked,
            bg=theme.ACCENT_PRIMARY, fg=theme.ACCENT_INK,
            activebackground=theme.ACCENT_HOVER, activeforeground=theme.ACCENT_INK,
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2", font=label_font,
        )
        self._btn_compare.pack(side=tk.LEFT)
        self._btn_compare.bind("<Enter>", lambda _e: self._btn_compare.configure(bg=theme.ACCENT_HOVER))
        self._btn_compare.bind("<Leave>", lambda _e: self._btn_compare.configure(bg=theme.ACCENT_PRIMARY))
        self._status_lbl = tk.Label(
            header, text="Sin comparar", bg=theme.PAPER_BG, fg=theme.INK_MUTED, font=small_font, anchor="e",
        )
        self._status_lbl.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(8, 0))
        tk.Frame(self, bg=theme.PAPER_BORDER, height=1).pack(side=tk.TOP, fill=tk.X, padx=6)

        table_wrap = tk.Frame(self, bg=theme.PAPER_BG)
        table_wrap.pack(side=tk.TOP, fill=tk.X, padx=6, pady=(5, 2))
        self._tree = ttk.Treeview(
            table_wrap, columns=[c[0] for c in _COLUMNS], show="headings", height=5, selectmode="browse",
        )
        for cid, heading, width, anchor in _COLUMNS:
            self._tree.heading(cid, text=heading, anchor=anchor)
            self._tree.column(cid, width=width, minwidth=26, anchor=anchor, stretch=(cid in ("escenario", "rebose")))
        self._tree.pack(fill=tk.X, expand=True)
        self._tree.tag_configure("even", background=theme.PAPER_BG, foreground=theme.INK_PRIMARY)
        self._tree.tag_configure("odd", background=theme.PAPER_ALT_ROW, foreground=theme.INK_PRIMARY)
        self._tree.tag_configure("crit", foreground=theme.TIER_TEXT_ON_LIGHT["#ef4444"])
        self._tree.tag_configure("over", foreground=theme.TIER_TEXT_ON_LIGHT["#991b1b"])
        for seq in ("<<TreeviewSelect>>", "<Return>"):
            self._tree.bind(seq, self._on_row_action)

        tk.Label(
            self, text="Clic en una fila para cargar ese escenario (Rebose en m³, PTAR en m³/s)",
            bg=theme.PAPER_BG, fg=theme.INK_MUTED, font=small_font, anchor="w",
        ).pack(side=tk.TOP, fill=tk.X, padx=6, pady=(0, 3))

        # 2 subgráficas: (1) Críticas/Sobrecargadas + Pico PTAR 31, (2) Rebose superficial acumulado
        self.fig = Figure(figsize=(4.4, 4.4), dpi=96, facecolor=theme.PAPER_BG, constrained_layout=True)
        self.ax_bars, self.ax_flood = self.fig.subplots(2, 1)
        self.ax_peak = self.ax_bars.twinx()
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        tk_w = self.canvas.get_tk_widget()
        tk_w.configure(bg=theme.PAPER_BG, highlightthickness=0, bd=0)
        tk_w.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        self._draw_empty()

    def set_comparisons(
        self, summaries: Optional[List[ScenarioSummary]],
        elapsed_ms: Optional[float] = None, is_visible: bool = True,
    ) -> None:
        """Actualiza resultados comparativos; difiere el render si el panel está oculto."""
        self._summaries = list(summaries) if summaries else None
        self._elapsed_ms = elapsed_ms
        self._is_visible = bool(is_visible)
        if self._summaries:
            suffix = f" ({elapsed_ms:.0f} ms)" if elapsed_ms is not None else ""
            self._status_lbl.configure(text=f"{len(self._summaries)} escenarios{suffix}", fg=theme.ACCENT_TEXT)
        else:
            self._status_lbl.configure(text="Sin comparar", fg=theme.INK_MUTED)
        if not self._is_visible:
            self._dirty = True
            return
        self._render()

    def invalidate(self) -> None:
        """Indica que cambiaron parámetros base y la comparación debe recalcularse."""
        msg = "Parámetros cambiados — recalcular" if self._summaries else "Sin comparar — presione el botón"
        fg = theme.TIER_TEXT_ON_LIGHT["#f97316"] if self._summaries else theme.INK_MUTED
        self._status_lbl.configure(text=msg, fg=fg)

    def mark_visible(self) -> None:
        """Renderiza tabla y gráficas si hubo cambios mientras el panel estuvo oculto."""
        self._is_visible = True
        if self._dirty:
            self._render()

    def _on_row_action(self, _event: tk.Event) -> None:
        if self._populating:
            return
        sel = self._tree.selection()
        sc_id = self._row_scenario.get(sel[0]) if sel else None
        if sc_id is not None:
            self._on_select_scenario(sc_id)

    def _draw_empty(self) -> None:
        self.ax_peak.clear()
        self.ax_peak.set_visible(False)
        for ax, title, ylabel in (
            (self.ax_bars, "Tuberías críticas vs. pico PTAR 31", "N.º tuberías"),
            (self.ax_flood, "Rebose superficial acumulado", "Volumen (×10³ m³)"),
        ):
            ax.clear()
            _style_sub(ax, title, ylabel)
            ax.text(0.5, 0.5, "Presione «Comparar 5 escenarios»", transform=ax.transAxes,
                    ha="center", va="center", fontsize=8.0, color=theme.INK_MUTED)
            ax.set_xticks([])
            ax.set_yticks([])
        self.canvas.draw_idle()

    def _populate_table(self, summaries: List[ScenarioSummary]) -> None:
        self._populating = True
        try:
            self._tree.delete(*self._tree.get_children())
            self._row_scenario.clear()
            for idx, s in enumerate(summaries):
                base = "even" if idx % 2 == 0 else "odd"
                tags = (base, "over") if s.num_overloaded_pipes > 0 else ((base, "crit") if s.num_critical_pipes > 0 else (base,))
                iid = f"sc_{s.scenario_id}"
                self._row_scenario[iid] = s.scenario_id
                vals = (
                    f"E{s.scenario_id}", theme.translate_scenario_name(s.condition, short=True),
                    f"{s.intensity_mm_h:.0f}", _fmt_pct(s.max_utilization_pct),
                    str(s.num_critical_pipes), str(s.num_overloaded_pipes),
                    f"{s.peak_sink_discharge_m3s:.3f}", _fmt_m3(s.total_surface_flooding_m3),
                )
                self._tree.insert("", tk.END, iid=iid, tags=tags, values=vals)
        finally:
            self._populating = False

    def _render(self) -> None:
        self._dirty = False
        if not self._summaries:
            self._populate_table([])
            self._draw_empty()
            return
        summaries = self._summaries
        self._populate_table(summaries)

        xs, w = list(range(len(summaries))), 0.34
        crit = [s.num_critical_pipes for s in summaries]
        over = [s.num_overloaded_pipes for s in summaries]
        peaks = [s.peak_sink_discharge_m3s for s in summaries]
        floods_k = [s.total_surface_flooding_m3 / 1000.0 for s in summaries]
        labels = [f"E{s.scenario_id}\n{theme.translate_scenario_name(s.condition, short=True)}" for s in summaries]

        # Subgráfica 1: Críticas / Sobrecargadas + Pico PTAR 31
        ax1, ax2 = self.ax_bars, self.ax_peak
        ax1.clear()
        ax2.clear()
        ax2.set_visible(True)
        _style_sub(ax1, "Tuberías críticas vs. pico PTAR 31", "N.º tuberías")
        ax1.bar([x - w / 2 for x in xs], crit, width=w, color="#ef4444", edgecolor=theme.INK_PRIMARY, lw=0.5, label="Crít. (>75%)")
        ax1.bar([x + w / 2 for x in xs], over, width=w, color="#991b1b", edgecolor=theme.INK_PRIMARY, lw=0.5, label="Sobr. (>100%)")
        ax1.set_xticks(xs)
        ax1.set_xticklabels(labels, fontsize=6.7, color=theme.INK_PRIMARY)
        ax1.set_ylim(0, max(5, max(crit + over, default=0) * 1.42))

        ax2.plot(xs, peaks, color="#6D8196", marker="o", lw=1.8, ms=4.2, label="Pico PTAR (m³/s)")
        ax2.yaxis.tick_right()
        ax2.yaxis.set_label_position("right")
        ax2.set_ylabel("PTAR (m³/s)", fontsize=7.2, color=theme.ACCENT_TEXT)
        ax2.tick_params(axis="y", colors=theme.ACCENT_TEXT, labelsize=6.9)
        ax2.set_ylim(0.0, max(0.05, max(peaks, default=0.0) * 1.42))
        ax2.spines["right"].set_color(theme.INK_PRIMARY)
        ax2.spines["right"].set_linewidth(0.8)
        for side in ("left", "top", "bottom"):
            ax2.spines[side].set_visible(False)

        h1, l1 = ax1.get_legend_handles_labels()
        h2, l2 = ax2.get_legend_handles_labels()
        ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=6.0, ncol=2, frameon=True,
                   facecolor=theme.PAPER_BG, edgecolor=theme.PAPER_BORDER, framealpha=0.94)

        # Subgráfica 2: Rebose superficial acumulado (×10³ m³)
        ax3 = self.ax_flood
        ax3.clear()
        _style_sub(ax3, "Rebose superficial acumulado", "×10³ m³")
        bar_colors = [theme.ACCENT_PRIMARY if v <= 0 else "#991b1b" for v in floods_k]
        bars = ax3.bar(xs, floods_k, width=0.52, color=bar_colors, edgecolor=theme.INK_PRIMARY, lw=0.5)
        max_fk = max(floods_k, default=0.0)
        ax3.set_ylim(0.0, max(1.0, max_fk * 1.26))
        ax3.set_xticks(xs)
        ax3.set_xticklabels(labels, fontsize=6.7, color=theme.INK_PRIMARY)
        for bar, val in zip(bars, floods_k):
            lbl = f"{val:.1f}k" if val >= 0.1 else "0"
            ax3.text(bar.get_x() + bar.get_width() / 2.0, bar.get_height() + max(0.02, max_fk * 0.03),
                     lbl, ha="center", va="bottom", fontsize=6.7, fontweight="bold", color=theme.INK_PRIMARY)

        self.canvas.draw_idle()
