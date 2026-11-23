"""Pestañas del panel derecho: Inspector (acciones, intervención en vivo, fuentes, ficha) y Tuberías Críticas."""

import math
import tkinter as tk
from tkinter import font as tkfont, ttk
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from src.algorithms.analysis import classify_overload_persistence, classify_utilization, rank_critical_pipes
from src.algorithms.queries import get_node_details, get_pipe_details
from src.data_structures import DirectedGraph, PipeEdge
from src.simulation.models import PipeIntervention, SimulationResult, TimeStepSnapshot, resolve_pipe_hydraulics
from . import theme
from .widgets import COMMERCIAL_DIAMETERS_IN, _ScenarioMenuButton

_EMPTY_MSG = "Haz clic en una tubería o pozo del plano, o usa el buscador."
_NODE_LABELS = {"source": "Alcantarilla Fuente", "sink": "PTAR Punta Canoa", "manhole": "Pozo"}
_NODE_TYPES_ES = {"source": "FUENTE", "sink": "SUMIDERO PTAR", "manhole": "POZO DE INSPECCIÓN"}
_FILTER_MODES = ("Todas", "Resto (≤75%)", "Críticas (>75–100%)", "Sobrec. (>100%)")
# (utilización mínima, máxima, mínima exclusiva). Se aceptan los nombres antiguos de filtro.
_FILTER_RULES: Dict[str, Tuple[float, Optional[float], bool]] = {
    "Todas": (0.0, None, False), "Resto (≤75%)": (0.0, 75.0, False),
    "Críticas (>75–100%)": (75.0, 100.0, True), "Sobrec. (>100%)": (100.0, None, True),
    "Sobrecargadas (>100%)": (100.0, None, True), "En alerta (>75%)": (75.0, None, True),
}
_EMPTY_FILTER_MSG = {
    "Resto (≤75%)": "Ninguna tubería está en ≤75% en este instante.",
    "Críticas (>75–100%)": "Ninguna tubería está en >75–100% en este instante.",
    "Sobrec. (>100%)": "Ninguna tubería supera el 100% en este instante.",
}
_TIER_NAMES = tuple(label for _, _, label in theme.COLOR_SCALE_LEGEND)
_SUM_KEYS = (
    "Escenario", "Cuenca", "Ingreso / Fuent.", "Entrada acum.", "Descarga PTAR 31 (pico)", "Pozos / Tránsito",
    "Rebose superf.", "Error balance", "Críticas (>75–100%)", "Sobrec. (>100%)", "Intervenciones",
)
_COLS = (
    ("#", 26, "e", False), ("ID", 40, "center", False), ("Tramo", 56, "center", True), ("Q (m³/s)", 58, "e", False),
    ("Qmax", 54, "e", False), ("Util. %", 52, "e", False), ("Razón", 46, "e", False), ("Estado", 80, "w", True),
)
_COMPACT_STATE = {"Baja": "Baja", "Moderada": "Mod.", "Alta": "Alta", "Cercana máx.": "Cerc.", "Excedida": "Exc.", "Cerrada 100%": "Cerr."}
_COL_PAD = 12
_MONO_TONES = ("#4A4A4A", "#6D8196", "#5A6570", "#9BA5B0", "#CBCBCB", "#7D8E9F", "#3A3A3A", "#B3B8BE")
_LIGHT_TONES = ("#CBCBCB", "#B3B8BE", "#9BA5B0")
_RED = "#991b1b"
_KvPair = Tuple[str, str, Optional[str]]


def _fmt_edges(edges: List) -> str:
    return "Ninguna" if not edges else (", ".join(e.pipe_id for e in edges[:4]) + (f" (+{len(edges) - 4})" if len(edges) > 4 else ""))


class InspectorTab(tk.Frame):
    """Inspector: acciones, intervención en vivo, composición por fuente, ficha técnica y resumen del escenario."""

    def __init__(
        self, parent: tk.Misc, fonts: Dict[str, Tuple[str, int, str]], callbacks: Optional[Dict[str, Callable]] = None,
    ) -> None:
        super().__init__(parent, bg=theme.PAPER_BG)
        self._fonts, self._callbacks = fonts, callbacks or {}
        self._btn_styles: Dict[tk.Button, Tuple[str, str, str, str]] = {}
        self._ctx_sig: Optional[tuple] = None
        self._edge_sig: Optional[tuple] = None
        self.source_shares: List[Tuple[str, float]] = []
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

        # Ranuras fijas (en orden): al ocultar su contenido colapsan, sin reordenar widgets
        self._actions_slot = tk.Frame(self._inner, bg=theme.PAPER_BG); self._actions_slot.pack(fill=tk.X, padx=10)
        self._ent_slot = tk.Frame(self._inner, bg=theme.PAPER_BG); self._ent_slot.pack(fill=tk.X, padx=10, pady=(0, 4))
        self._interv_slot = tk.Frame(self._inner, bg=theme.PAPER_BG); self._interv_slot.pack(fill=tk.X, padx=10)
        self._source_slot = tk.Frame(self._inner, bg=theme.PAPER_BG); self._source_slot.pack(fill=tk.X, padx=10)
        self._slot_end = tk.Frame(self._inner, bg=theme.PAPER_BG, height=0); self._slot_end.pack(fill=tk.X)
        self._slot_sig: Tuple[bool, ...] = (True, True, True, True)
        self._build_actions()
        self._empty_lbl = tk.Label(self._ent_slot, text=_EMPTY_MSG, bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED, font=fonts["small"], justify="left", anchor="w", padx=8, pady=8, wraplength=240)
        self._empty_lbl.pack(fill=tk.X)
        self._ent_box = tk.Frame(self._ent_slot, bg=theme.PAPER_BG, highlightbackground=theme.PAPER_BORDER, highlightthickness=1)
        self._ent_rows = self._kv_pool(self._ent_box, 20)
        self._build_intervention_card()
        self._build_source_card()

        self._header("RESUMEN DEL ESCENARIO")
        sum_box = tk.Frame(self._inner, bg=theme.PAPER_BG, highlightbackground=theme.PAPER_BORDER, highlightthickness=1)
        sum_box.pack(fill=tk.X, padx=10, pady=(0, 10))
        self._sum_rows = self._kv_pool(sum_box, len(_SUM_KEYS))
        for (row, kl, vl), key in zip(self._sum_rows, _SUM_KEYS):
            kl.configure(text=key); vl.configure(text="—")
        self._sum_rows[-1][0].grid_remove()

    # ── Construcción ─────────────────────────────────────────────────────────

    def _cb(self, key: str, *args: object) -> None:
        if (fn := self._callbacks.get(key)) is not None:
            fn(*args)

    def _btn(self, parent: tk.Misc, text: str, command: Callable[[], None], primary: bool = False, pady: int = 3) -> tk.Button:
        btn = tk.Button(parent, text=text, command=command, relief="flat", bd=0, padx=7, pady=pady, font=self._fonts["small"], cursor="hand2", highlightthickness=1)
        self._style_btn(btn, primary)
        btn.bind("<Enter>", lambda _e, b=btn: b.configure(bg=self._btn_styles[b][1]))
        btn.bind("<Leave>", lambda _e, b=btn: b.configure(bg=self._btn_styles[b][0]))
        return btn

    def _style_btn(self, btn: tk.Button, primary: bool) -> None:
        bg, hov, fg, bdr = (
            (theme.ACCENT_PRIMARY, theme.ACCENT_HOVER, theme.ACCENT_INK, theme.ACCENT_HOVER) if primary
            else (theme.PAPER_SUBTLE, theme.PAPER_HOVER, theme.INK_PRIMARY, theme.PAPER_BORDER)
        )
        self._btn_styles[btn] = (bg, hov, fg, bdr)
        btn.configure(bg=bg, fg=fg, activebackground=hov, activeforeground=fg, highlightbackground=bdr)

    def _card(self, parent: tk.Misc, title: str) -> Tuple[tk.Frame, tk.Frame, tk.Frame]:
        card = tk.Frame(parent, bg=theme.PAPER_BG, highlightbackground=theme.PAPER_RULE, highlightthickness=1, bd=0)
        top = tk.Frame(card, bg=theme.PAPER_BG); top.pack(fill=tk.X, padx=8, pady=(6, 3))
        tk.Label(top, text=title, bg=theme.PAPER_BG, fg=theme.ACCENT_TEXT, font=self._fonts["label"], anchor="w").pack(side=tk.LEFT)
        tk.Frame(card, bg=theme.PAPER_BORDER, height=1).pack(fill=tk.X, padx=8, pady=(0, 5))
        body = tk.Frame(card, bg=theme.PAPER_BG); body.pack(fill=tk.X, padx=8, pady=(0, 7))
        return card, body, top

    def _build_actions(self) -> None:
        self._actions_bar = tk.Frame(self._actions_slot, bg=theme.PAPER_BG)
        self.btn_focus = self._btn(self._actions_bar, "Centrar", lambda: self._cb("focus"))
        self.btn_basin = self._btn(self._actions_bar, "Aislar cuenca", lambda: self._cb("basin"))
        self.btn_up = self._btn(self._actions_bar, "Aguas arriba", lambda: self._cb("trace", "up"))
        self.btn_down = self._btn(self._actions_bar, "Aguas abajo", lambda: self._cb("trace", "down"))

    def _build_intervention_card(self) -> None:
        self._interv_card, body, top = self._card(self._interv_slot, "INTERVENCIÓN EN VIVO")
        f = self._fonts
        self.lbl_active = tk.Label(top, text="", bg=theme.PAPER_BG, fg=theme.INK_MUTED, font=f["mono_bold"])
        self.lbl_active.pack(side=tk.RIGHT)
        self.btn_restore_all = self._btn(top, "Restaurar red", lambda: self._cb("restore_all"), pady=1)
        row = tk.Frame(body, bg=theme.PAPER_BG); row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="Obstrucción", bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=f["small"]).pack(side=tk.LEFT)
        self.lbl_obst = tk.Label(row, text="0%", bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=f["mono_bold"], width=5, highlightthickness=1, highlightbackground=theme.PAPER_BORDER)
        self.lbl_obst.pack(side=tk.RIGHT)
        self.var_obst = tk.DoubleVar(value=0.0)
        self.scale_obst = tk.Scale(
            row, from_=0, to=100, resolution=5, orient=tk.HORIZONTAL, showvalue=False, variable=self.var_obst,
            command=lambda v: self.lbl_obst.configure(text=f"{float(v):.0f}%"), bg=theme.PAPER_BG, troughcolor=theme.DOCK_BG,
            activebackground=theme.ACCENT_PRIMARY, highlightthickness=0, bd=0, sliderlength=16, width=10,
        )
        self.scale_obst.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=6)
        row = tk.Frame(body, bg=theme.PAPER_BG); row.pack(fill=tk.X, pady=2)
        tk.Label(row, text="Diámetro", bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=f["small"]).pack(side=tk.LEFT)
        self.lbl_diam_now = tk.Label(row, text="Actual: —", bg=theme.PAPER_BG, fg=theme.ACCENT_TEXT, font=f["mono"])
        self.lbl_diam_now.pack(side=tk.LEFT, padx=(8, 0))
        self.var_diam = tk.StringVar(value=COMMERCIAL_DIAMETERS_IN[0])
        self.menu_diam = _ScenarioMenuButton(
            row, textvariable=self.var_diam, values=COMMERCIAL_DIAMETERS_IN, on_select=lambda: None,
            width=11, padx=6, pady=2, ui_font=f["body"][0],
        )
        self.menu_diam.pack(side=tk.RIGHT)
        self.lbl_int_error = tk.Label(body, text="", bg=theme.ERROR_BG, fg=theme.ERROR_TEXT, font=f["small"], anchor="w", justify="left", wraplength=240, padx=5, pady=2)
        row = self._int_btn_row = tk.Frame(body, bg=theme.PAPER_BG); row.pack(fill=tk.X, pady=(5, 0))
        self._btn(row, "Aplicar y re-simular", self._emit_apply, primary=True).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        self._btn(row, "Restaurar tramo", lambda: self._cb("restore_pipe")).pack(side=tk.LEFT)

    def _build_source_card(self) -> None:
        self._source_card, body, top = self._card(self._source_slot, "COMPOSICIÓN POR FUENTE APORTANTE")
        self.lbl_source_entity = tk.Label(top, text="", bg=theme.PAPER_BG, fg=theme.INK_MUTED, font=self._fonts["mono_bold"])
        self.lbl_source_entity.pack(side=tk.RIGHT)
        self.source_bar = tk.Canvas(body, height=18, bg=theme.PAPER_BG, highlightthickness=1, highlightbackground=theme.DOCK_BORDER, bd=0)
        self.source_bar.pack(fill=tk.X, pady=(0, 3))
        self.source_bar.bind("<Configure>", lambda _e: self._redraw_source_bar())
        self.lbl_source_text = tk.Label(body, text="", bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=self._fonts["mono"], justify="left", anchor="w", wraplength=330)
        self.lbl_source_text.pack(fill=tk.X)

    # ── Desplazamiento y utilidades ──────────────────────────────────────────

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
        wrap = max(160, event.width - 28)
        self._empty_lbl.configure(wraplength=wrap)
        for lbl in (self.lbl_int_error, self.lbl_source_text):
            lbl.configure(wraplength=max(160, event.width - 48))
        vwrap = max(110, int(event.width * 0.58))
        for pool in (self._ent_rows, self._sum_rows):
            for _, _, vl in pool:
                vl.configure(wraplength=vwrap, justify="right")
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

    def _sync_slots(self) -> None:
        """Quita del layout las ranuras sin contenido (un Frame vacío conserva su última altura) y las recoloca en orden."""
        slots = (self._actions_slot, self._ent_slot, self._interv_slot, self._source_slot)
        sig = tuple(bool(sl.pack_slaves()) for sl in slots)
        if sig == self._slot_sig:
            return
        self._slot_sig = sig
        pads = ({"padx": 10}, {"padx": 10, "pady": (0, 4)}, {"padx": 10}, {"padx": 10})
        for sl in slots:
            sl.pack_forget()
        for sl, used, kw in zip(slots, sig, pads):
            if used:
                sl.pack(fill=tk.X, before=self._slot_end, **kw)

    def _set_entity(self, pairs: List[_KvPair]) -> None:
        self._empty_lbl.pack_forget()
        if not self._ent_box.winfo_ismapped():
            self._ent_box.pack(fill=tk.X)
        for idx, (row, kl, vl) in enumerate(self._ent_rows):
            if idx < len(pairs):
                k, v, fg = pairs[idx]
                kl.configure(text=k); vl.configure(text=v, fg=fg or theme.INK_PRIMARY, font=self._fonts["mono_bold"] if fg else self._fonts["mono"]); row.grid()
            else:
                row.grid_remove()
        self._sync_slots()

    def entity_values(self) -> Dict[str, str]:
        """Pares clave-valor visibles de la ficha técnica (para pruebas y diagnóstico)."""
        return {str(kl.cget("text")): str(vl.cget("text")) for row, kl, vl in self._ent_rows if row.winfo_manager()}

    def summary_values(self) -> Dict[str, str]:
        """Pares clave-valor visibles del resumen del escenario."""
        return {str(kl.cget("text")): str(vl.cget("text")) for row, kl, vl in self._sum_rows if row.winfo_manager()}

    def _show_empty(self) -> None:
        self._ent_title.configure(text="Sin selección"); self._badge.configure(text="", bg=theme.PAPER_BG, fg=theme.INK_MUTED)
        self._ent_box.pack_forget()
        if not self._empty_lbl.winfo_ismapped():
            self._empty_lbl.pack(fill=tk.X)
        self._sync_slots()

    # ── Acciones, intervención y composición (estado empujado por la app) ────

    def set_context(
        self, kind: Optional[str], edge: Optional[PipeEdge] = None, intervention: Optional[PipeIntervention] = None,
        n_interventions: int = 0, basin_on: bool = False, trace_dir: Optional[str] = None,
    ) -> None:
        """Muestra/oculta la barra de acciones y tarjetas según la selección y sincroniza sus controles."""
        sig = (kind, n_interventions > 0, basin_on, trace_dir)
        if sig != self._ctx_sig:
            prev_kind = self._ctx_sig[0] if self._ctx_sig else None
            self._ctx_sig = sig
            if kind != prev_kind:
                for w in (self.btn_focus, self.btn_basin, self.btn_up, self.btn_down):
                    w.pack_forget()
                for w in (self._actions_bar, self._interv_card, self._source_card):
                    w.pack_forget()
                if kind in ("pipe", "node"):
                    self._actions_bar.pack(fill=tk.X, pady=(0, 5))
                    self.btn_focus.pack(side=tk.LEFT, padx=(0, 3))
                    self.btn_basin.pack(side=tk.LEFT, padx=3)
                    if kind == "node":
                        self.btn_up.pack(side=tk.LEFT, padx=3); self.btn_down.pack(side=tk.LEFT, padx=3)
                    if kind == "pipe":
                        self._interv_card.pack(fill=tk.X, pady=(0, 5))
                    self._source_card.pack(fill=tk.X, pady=(0, 5))
            self._style_btn(self.btn_basin, basin_on)
            self._style_btn(self.btn_up, trace_dir == "up")
            self._style_btn(self.btn_down, trace_dir == "down")
            self.lbl_active.configure(text=f"{n_interventions} act." if n_interventions else "")
            if n_interventions:
                self.btn_restore_all.pack(side=tk.RIGHT, padx=(0, 6))
            else:
                self.btn_restore_all.pack_forget()
            self._sync_slots()
        if kind == "pipe" and edge is not None:
            esig = (edge.pipe_id, intervention)
            if esig != self._edge_sig:
                self._edge_sig = esig
                self._sync_intervention(edge, intervention)
        else:
            self._edge_sig = None

    def _sync_intervention(self, edge: PipeEdge, inv: Optional[PipeIntervention]) -> None:
        eff = inv.diameter_in_override if (inv is not None and inv.diameter_in_override is not None) else edge.diameter_in
        self.lbl_diam_now.configure(text=f"Actual: {eff:g}\"")
        orig = f"Original ({edge.diameter_in:g}\")"
        self.menu_diam.set_values([orig] + COMMERCIAL_DIAMETERS_IN[1:])
        self.var_diam.set(orig if (inv is None or inv.diameter_in_override is None) else f"{inv.diameter_in_override:g}\"")
        obst = round(inv.obstruction_pct) if inv is not None else 0
        self.var_obst.set(float(obst)); self.lbl_obst.configure(text=f"{obst:.0f}%")
        self.show_intervention_error("")
        self._base_diam_in = edge.diameter_in

    def show_intervention_error(self, message: str) -> None:
        if message:
            self.lbl_int_error.configure(text=message)
            self.lbl_int_error.pack(fill=tk.X, pady=(3, 0), before=self._int_btn_row)
        else:
            self.lbl_int_error.pack_forget()

    def _parse_diameter(self, raw: str) -> Optional[float]:
        text = raw.strip()
        if not text or text.lower().startswith("original"):
            return None
        try:
            val = float(text.replace('"', "").replace("pulg", "").strip())
        except ValueError as exc:
            raise ValueError(f"Diámetro inválido «{raw}». Elija «Original» o un diámetro comercial.") from exc
        if not math.isfinite(val) or not (0.0 < val <= 120.0):
            raise ValueError("El diámetro debe estar entre 0 (excluido) y 120 pulgadas.")
        return None if abs(val - getattr(self, "_base_diam_in", -1.0)) < 1e-6 else val

    def _emit_apply(self) -> None:
        try:
            obst = float(self.var_obst.get())
            if not math.isfinite(obst) or not (0.0 <= obst <= 100.0):
                raise ValueError("La obstrucción debe estar entre 0 % y 100 %.")
            diam = self._parse_diameter(self.var_diam.get())
        except (ValueError, tk.TclError) as exc:
            self.show_intervention_error(str(exc))
            return
        self.show_intervention_error("")
        self._cb("apply", obst, diam)

    def set_source_composition(self, entity_label: str, shares: List[Tuple[str, float]], split_rule: str = "proportional") -> None:
        """Actualiza la barra apilada monocromática y el desglose porcentual por fuente."""
        self.source_shares = list(shares)
        self.lbl_source_entity.configure(text=entity_label)
        if not shares:
            self.lbl_source_text.configure(text="Sin aporte de fuentes hacia esta entidad.")
        else:
            split_es = "Proporcional" if split_rule == "proportional" else "Equitativa"
            self.lbl_source_text.configure(text=" · ".join(f"F{s}: {f * 100.0:.1f}%" for s, f in shares) + f"\nBifurcación: {split_es}")
        self._redraw_source_bar()

    def _redraw_source_bar(self) -> None:
        c = self.source_bar
        c.delete("all")
        w = c.winfo_width() if c.winfo_width() > 10 else 320
        h = c.winfo_height() if c.winfo_height() > 8 else 18
        if not self.source_shares:
            c.create_text(w / 2.0, h / 2.0, text="Sin mezcla activa", fill=theme.INK_MUTED, font=(self._fonts["mono"][0], 7))
            return
        x0, n = 0.0, len(self.source_shares)
        for idx, (src, frac) in enumerate(self.source_shares):
            seg = (w - x0) if idx == n - 1 else w * frac
            if seg < 1.0:
                continue
            tone, x1 = _MONO_TONES[idx % len(_MONO_TONES)], x0 + seg
            c.create_rectangle(x0, 0, x1, h, fill=tone, outline="")
            if idx < n - 1:
                c.create_line(x1, 0, x1, h, fill=theme.PAPER_BG, width=1.5)
            if seg >= 34:
                c.create_text((x0 + x1) / 2.0, h / 2.0, text=f"F{src} {frac * 100.0:.0f}%", fill=theme.INK_PRIMARY if tone in _LIGHT_TONES else theme.PAPER_BG, font=(self._fonts["mono"][0], 7, "bold"))
            x0 = x1

    # ── Ficha técnica y resumen ──────────────────────────────────────────────

    def update_view(
        self, graph: Optional[DirectedGraph], snapshot: Optional[TimeStepSnapshot],
        result: Optional[SimulationResult], selected_kind: Optional[str], selected_id: Optional[str],
        interventions: Optional[Dict[str, PipeIntervention]] = None, isolated_nodes: Iterable[str] = (),
        isolated_pipes: Iterable[str] = (), basin: object = None,
    ) -> None:
        """Actualiza la ficha de entidad seleccionada y el resumen del escenario."""
        ints = interventions or {}
        iso_n, iso_p = set(isolated_nodes), set(isolated_pipes)
        if graph is None or not selected_kind or not selected_id:
            self._show_empty()
        elif selected_kind == "pipe" and (det := get_pipe_details(graph, selected_id)) is not None:
            self._show_pipe(det.pipe, snapshot, result, ints.get(selected_id), selected_id in iso_p)
        elif selected_kind == "node" and (nd := get_node_details(graph, selected_id)) is not None:
            self._show_node(nd, snapshot, result, ints, selected_id in iso_n)
        else:
            self._show_empty()
        self._update_summary(snapshot, result, basin, ints, iso_n)

    def _show_pipe(self, p: PipeEdge, snapshot: Optional[TimeStepSnapshot], result: Optional[SimulationResult], inv: Optional[PipeIntervention], isolated: bool) -> None:
        ps = snapshot.pipe_states.get(p.pipe_id) if snapshot else None
        q_eff, v_eff, t_eff_s, d_eff = resolve_pipe_hydraulics(p, inv)
        self._ent_title.configure(text=f"Tubería {p.pipe_id}")
        if ps is not None and ps.is_closed:
            u_fg = _RED; self._badge.configure(text="CERRADA", bg=_RED, fg="#ffffff")
        elif ps is not None:
            ch = ps.category.color_hex.lower()
            u_fg = theme.TIER_TEXT_ON_LIGHT.get(ch, theme.INK_PRIMARY)
            self._badge.configure(text=f"{ps.utilization_pct:.1f}%", bg=ch, fg="#1f2937" if ch in ("#22c55e", "#eab308") else "#ffffff")
        else:
            u_fg = None; self._badge.configure(text="Sin sim.", bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED)
        pairs: List[_KvPair] = []
        if inv is not None:
            pairs.append(("Intervención", f"OBST {inv.obstruction_pct:.0f}% · Ø {d_eff:g}\" (orig. {p.diameter_in:g}\")", _RED))
        if isolated:
            pairs.append(("[AISLADO DE 31]", "Tramo sin conexión a PTAR", _RED))
        pairs += [
            ("De → A", f"{p.from_node} → {p.to_node}", None), ("Diámetro", f"{d_eff:.1f} in / {d_eff * 0.0254:.3f} m", None),
            ("Longitud", f"{p.length_m:.2f} m", None), ("Pendiente / n", f"{p.slope:.4f} / {p.manning_n:.4f}", None),
            ("Q_max", f"{q_eff:.4f} m³/s", None),
        ]
        if inv is not None:
            pairs.append(("Q_max base", f"{p.q_max_m3s:.4f} m³/s", None))
        pairs += [("Velocidad", f"{v_eff:.3f} m/s", None), ("Tiempo tránsito", f"{t_eff_s:.1f} s ({t_eff_s / 60.0:.2f} min)", None)]
        if p.note:
            pairs.append(("Marca dataset", p.note, None))
        if ps is not None:
            if ps.is_closed:
                pairs += [("Q conducido", "CERRADA 100% (nulo)", _RED), ("Q demanda retenida", f"{ps.demand_flow_m3s:.4f} m³/s", None)]
            else:
                over = ps.excess_flow_m3s > 0
                pairs += [
                    ("Q conducido", f"{ps.flow_m3s:.4f} m³/s", None),
                    ("Q demanda", f"{ps.demand_flow_m3s:.4f} m³/s ({ps.utilization_pct / 100.0:.2f}×Qmax)", None),
                    ("Utilización", f"{ps.utilization_pct:.1f} %", u_fg),
                    ("Exceso", f"{ps.excess_flow_m3s:.4f} m³/s", u_fg if over else None),
                    ("Vol. en tránsito", f"{ps.volume_in_transit_m3:.3f} m³", None),
                ]
        else:
            pairs += [("Q conducido", "—", None), ("Utilización", "—", None)]
        if result is not None:
            pk = result.peak_pipe_utilization.get(p.pipe_id, 0.0)
            ov = result.pipe_overloaded_minutes.get(p.pipe_id, 0.0)
            desc = classify_overload_persistence(ov, result.config.duration_min)[2]
            pairs += [("Pico utilización", f"{pk:.1f} % ({pk / 100.0:.2f}×)", None), ("Estrés >100%", f"{ov:.0f} min ({desc})", _RED if ov > 0 else None)]
        self._set_entity(pairs)

    def _show_node(self, nd, snapshot: Optional[TimeStepSnapshot], result: Optional[SimulationResult], ints: Dict[str, PipeIntervention], isolated: bool) -> None:
        node, ns = nd.node, (snapshot.node_states.get(nd.node.node_id) if snapshot else None)
        kind_lbl = _NODE_LABELS.get(node.node_type, "Pozo")
        self._ent_title.configure(text=f"{kind_lbl} {node.node_id}")
        b = ("REBOSE", _RED, "#ffffff") if (ns and ns.surface_flooding_m3 > 1e-6) else (("RETENCIÓN", "#f97316", "#ffffff") if (ns and ns.stored_volume_m3 > 1e-6) else (node.node_type.upper(), theme.ACCENT_PRIMARY, theme.ACCENT_INK))
        self._badge.configure(text=b[0], bg=b[1], fg=b[2])
        cap_out = sum(resolve_pipe_hydraulics(e, ints.get(e.pipe_id))[0] for e in nd.outgoing)
        cap_w = result.config.max_manhole_storage_m3 if result else 4.0
        pairs: List[_KvPair] = []
        if isolated:
            pairs.append(("[AISLADO DE 31]", "Sin ruta activa a la PTAR", _RED))
        pairs += [
            ("Tipo", _NODE_TYPES_ES.get(node.node_type, kind_lbl), None), ("Entradas", _fmt_edges(nd.incoming), None),
            ("Salidas", _fmt_edges(nd.outgoing), None), ("Cap. saliente", f"{cap_out:.4f} m³/s", None),
            ("Q ent. / sal.", f"{ns.inflow_m3s:.4f} / {ns.outflow_m3s:.4f} m³/s" if ns else "—", None),
            ("Vol. en pozo", f"{ns.stored_volume_m3:.3f} m³ (máx {cap_w:.1f})" if ns else "—", "#f97316" if (ns and ns.stored_volume_m3 > 1e-3) else None),
            ("Rebose sup.", f"{ns.surface_flooding_m3:.3f} m³" if ns else "—", _RED if (ns and ns.surface_flooding_m3 > 1e-3) else None),
        ]
        self._set_entity(pairs)

    def _update_summary(self, snapshot: Optional[TimeStepSnapshot], result: Optional[SimulationResult], basin: object, ints: Dict[str, PipeIntervention], iso_n: set) -> None:
        if result is None or snapshot is None:
            for row, _, vl in self._sum_rows:
                vl.configure(text="—", fg=theme.INK_PRIMARY)
            self._sum_rows[-1][0].grid_remove()
            return
        cfg = result.config
        src_es = theme.SOURCE_DIST_TO_ES.get(cfg.source_distribution, cfg.source_distribution)
        flood = snapshot.total_surface_flooding_m3
        vals: List[Tuple[str, Optional[str]]] = [
            (f"{cfg.scenario_id} — {theme.translate_scenario_name(cfg.scenario_name)} ({cfg.intensity_mm_h:.0f} mm/h)", None),
            (f"C={basin.runoff_coefficient_c:g}, A={basin.area_ha:g} ha" if basin is not None else "—", None),
            (f"{cfg.ingress_factor * 100:.1f}% · {src_es} | Q_san={cfg.dry_weather_flow_per_source_m3s:.4f}", None),
            (f"{snapshot.cumulative_inflow_m3:,.2f} m³", None),
            (f"{snapshot.cumulative_sink_discharge_m3:,.2f} m³ ({result.peak_sink_discharge_m3s:.4f} m³/s)", None),
            (f"{snapshot.total_manhole_storage_m3:,.2f} / {snapshot.total_pipe_transit_m3:,.2f} m³", None),
            (f"{flood:,.2f} m³", _RED if flood > 1e-3 else None),
            (f"{result.max_mass_balance_error_m3:.3e} m³", None),
            (f"{len(result.ever_near_capacity_pipes)} tuberías", "#dc2626" if result.ever_near_capacity_pipes else None),
            (f"{len(result.ever_overloaded_pipes)} tuberías", _RED if result.ever_overloaded_pipes else None),
        ]
        for (_, _, vl), (txt, fg) in zip(self._sum_rows, vals):
            vl.configure(text=txt, fg=fg or theme.INK_PRIMARY)
        row, _, vl = self._sum_rows[-1]
        if ints:
            names = ", ".join(sorted(ints)[:6]) + (f" (+{len(ints) - 6})" if len(ints) > 6 else "")
            vl.configure(text=f"{names} ({len(iso_n)} aislados)", fg=_RED if iso_n else theme.INK_PRIMARY)
            row.grid()
        else:
            row.grid_remove()


class CriticalPipesTab(tk.Frame):
    """Ranking interactivo de tuberías ordenado con PriorityQueue (rank_critical_pipes)."""

    def __init__(
        self, parent: tk.Misc, fonts: Dict[str, Tuple[str, int, str]], on_select_pipe: Callable[[str], None],
        on_focus_pipe: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent, bg=theme.PAPER_BG)
        self._on_select_pipe, self._on_focus_pipe = on_select_pipe, on_focus_pipe
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
        cb = ttk.Combobox(bar, textvariable=self._filter_var, values=_FILTER_MODES, state="readonly", width=19, font=fonts["small"])
        cb.pack(side=tk.LEFT, padx=(4, 6)); cb.bind("<<ComboboxSelected>>", lambda _e: self._render())
        self._count_lbl = tk.Label(bar, text="0 tuberías", bg=theme.PAPER_SUBTLE, fg=theme.ACCENT_TEXT, font=fonts["mono_bold"])
        self._count_lbl.pack(side=tk.RIGHT)

        wrap = tk.Frame(self, bg=theme.PAPER_BG); wrap.pack(fill=tk.BOTH, expand=True)
        self._tree = ttk.Treeview(wrap, columns=tuple(c[0] for c in _COLS), show="headings", selectmode="browse")
        for col, w, anc, st in _COLS:
            self._tree.heading(col, text=col, anchor=anc); self._tree.column(col, width=w, minwidth=24, anchor=anc, stretch=st)
        vsb = ttk.Scrollbar(wrap, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._hsb = ttk.Scrollbar(wrap, orient=tk.HORIZONTAL, command=self._tree.xview)
        self._tree.configure(xscrollcommand=self._on_xscroll)
        vsb.pack(side=tk.RIGHT, fill=tk.Y); self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._rows_full: List[Tuple] = []
        self._compact_state = False
        self._tree.bind("<Configure>", lambda _e: self._fit_columns())
        self._empty_lbl = tk.Label(wrap, text="", bg=theme.PAPER_BG, fg=theme.INK_MUTED, font=fonts["body"], justify="center")
        for idx, (_, hex_c, _) in enumerate(theme.COLOR_SCALE_LEGEND):
            fg = theme.TIER_TEXT_ON_LIGHT.get(hex_c.lower(), theme.INK_PRIMARY)
            self._tree.tag_configure(f"t{idx}_0", foreground=fg, background=theme.PAPER_BG)
            self._tree.tag_configure(f"t{idx}_1", foreground=fg, background=theme.PAPER_ALT_ROW)
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-1>", self._on_double_click)

    def _render(self) -> None:
        self._dirty = False
        graph, snap = self._last_graph, self._last_snapshot
        if graph is None or snap is None:
            if self._row_iids:
                self._tree.delete(*self._row_iids)
                self._row_iids.clear(); self._iid_to_pipe.clear(); self._pipe_to_iid.clear()
            self._count_lbl.configure(text="0 tuberías"); self._empty_lbl.place_forget()
            return
        mode = self._filter_var.get()
        min_u, max_u, excl = _FILTER_RULES.get(mode, _FILTER_RULES["Todas"])
        states = snap.pipe_states
        records = rank_critical_pipes(
            graph, {p: s.flow_m3s for p, s in states.items()}, {p: s.utilization_pct for p, s in states.items()},
            min_utilization_pct=min_u, max_utilization_pct=max_u, exclusive_min=excl,
            pipe_qmax_overrides={p: s.effective_q_max_m3s for p, s in states.items() if s.effective_q_max_m3s is not None},
            pipe_demand_ratios_pct={p: s.demand_ratio_pct for p, s in states.items()},
            pipe_excess_flows_m3s={p: s.excess_flow_m3s for p, s in states.items()},
        )
        self._suppress_select = True
        try:
            self._iid_to_pipe.clear(); self._pipe_to_iid.clear()
            existing = len(self._row_iids)
            full_rows: List[Tuple] = []
            for idx, rec in enumerate(records):
                cat = rec.category or classify_utilization(rec.utilization_pct)
                if rec.q_max_m3s <= 1e-12:
                    tier_txt = "Cerrada 100%"
                else:
                    tier_txt = _TIER_NAMES[cat.tier_index] if cat.tier_index < len(_TIER_NAMES) else cat.label
                vals = (rec.rank, rec.pipe_id, f"{rec.from_node}→{rec.to_node}", f"{rec.flow_m3s:.4f}", f"{rec.q_max_m3s:.4f}",
                        f"{rec.utilization_pct:.1f}%", f"{rec.demand_ratio_pct / 100.0:.2f}×", tier_txt)
                tag = (f"t{cat.tier_index}_{idx % 2}",)
                full_rows.append(vals)
                vals = self._shown(vals)
                if idx < existing:
                    iid = self._row_iids[idx]; self._tree.item(iid, values=vals, tags=tag)
                else:
                    iid = self._tree.insert("", tk.END, values=vals, tags=tag); self._row_iids.append(iid)
                self._iid_to_pipe[iid], self._pipe_to_iid[rec.pipe_id] = rec.pipe_id, iid
            if existing > len(records):
                self._tree.delete(*self._row_iids[len(records):]); del self._row_iids[len(records):]
            self._rows_full = full_rows
            self._count_lbl.configure(text=f"{len(records)} tubería{'s' if len(records) != 1 else ''}")
            if records:
                self._empty_lbl.place_forget()
            else:
                self._empty_lbl.configure(text=_EMPTY_FILTER_MSG.get(mode, "Sin tuberías para mostrar."))
                self._empty_lbl.place(relx=0.5, rely=0.5, anchor="center")
            sel_iid = self._pipe_to_iid.get(self._selected_pipe_id) if self._selected_pipe_id else None
            target = (sel_iid,) if sel_iid is not None else ()
            if tuple(self._tree.selection()) != target:
                self._tree.selection_set(target)
        finally:
            self._suppress_select = False
        self._fit_columns()

    def _shown(self, vals: Tuple) -> Tuple:
        """Valores a mostrar: etiqueta de estado compacta cuando el panel es estrecho."""
        return vals[:-1] + (_COMPACT_STATE.get(vals[-1], vals[-1]),) if self._compact_state else vals

    def _on_xscroll(self, lo: str, hi: str) -> None:
        """Scrollbar horizontal que se oculta sola cuando todo el contenido cabe."""
        self._hsb.set(lo, hi)
        if float(lo) <= 0.0 and float(hi) >= 1.0:
            if self._hsb.winfo_manager():
                self._hsb.pack_forget()
        elif not self._hsb.winfo_manager():
            self._hsb.pack(side=tk.BOTTOM, fill=tk.X, before=self._tree)

    def _needed_widths(self, compact: bool) -> List[int]:
        """Ancho mínimo por columna midiendo encabezado y contenido real con la fuente del Treeview."""
        style = ttk.Style()
        body = tkfont.Font(font=style.lookup("Treeview", "font") or "TkDefaultFont")
        head = tkfont.Font(font=style.lookup("Treeview.Heading", "font") or style.lookup("Treeview", "font") or "TkDefaultFont")
        widths = [head.measure(c[0]) + _COL_PAD for c in _COLS]
        for vals in self._rows_full:
            vals = vals[:-1] + (_COMPACT_STATE.get(vals[-1], vals[-1]),) if compact else vals
            for i, v in enumerate(vals):
                widths[i] = max(widths[i], body.measure(str(v)) + _COL_PAD)
        return widths

    def _fit_columns(self) -> None:
        """Dimensiona columnas al contenido; si no cabe usa estados compactos y, de último, scroll horizontal."""
        avail = self._tree.winfo_width()
        if avail <= 1:
            avail = 420
        compact = self._compact_state
        widths = self._needed_widths(False)
        if sum(widths) > avail:
            compact, widths = True, self._needed_widths(True)
        if compact != self._compact_state:
            self._compact_state = compact
            self._suppress_select = True
            try:
                for iid, vals in zip(self._row_iids, self._rows_full):
                    self._tree.item(iid, values=self._shown(vals))
            finally:
                self._suppress_select = False
        spare = max(0, avail - sum(widths))
        for i, ((col, _w, anc, _st), w) in enumerate(zip(_COLS, widths)):
            extra = spare // 2 if col in ("Tramo", "Estado") else 0
            self._tree.column(col, width=w + extra, minwidth=w, stretch=False)

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

    def _on_double_click(self, event: tk.Event) -> None:
        """Doble clic en una fila: selecciona la tubería y centra la cámara en ella."""
        row = self._tree.identify_row(getattr(event, "y", 0))
        pid = self._iid_to_pipe.get(row) if row else self._selected_pipe_id
        if pid is None:
            return
        self._selected_pipe_id = pid
        self._on_select_pipe(pid)  # idempotente en la app
        if self._on_focus_pipe is not None:
            self._on_focus_pipe(pid)

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
