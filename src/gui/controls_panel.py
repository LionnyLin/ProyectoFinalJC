"""Panel izquierdo: pestañas Simulación / Recorridos, parámetros, búsqueda y bitácora de recorrido."""

import math
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from src.algorithms.traversals import TraversalFrame
from src.io.data_loader import NetworkDataset, PrecipitationScenario
from src.simulation.models import SimulationConfig
from . import theme
from .widgets import _ScenarioMenuButton

_NONE_TARGET = "(Ninguno)"
_RERUN_DEBOUNCE_MS = 140
_STRIP_MAX_CELLS = 6
# (clave, etiqueta, mínimo, máximo, incremento, valor por defecto, formato)
_PARAM_SPECS: Tuple[Tuple[str, str, float, float, float, str], ...] = (
    ("duration", "Duración simulación (min)", 10.0, 360.0, 10.0, "90"),
    ("storm", "Duración lluvia (min)", 0.0, 360.0, 5.0, "60"),
    ("dt", "Paso temporal Δt (min)", 0.5, 10.0, 0.5, "1.0"),
    ("ingress", "Ingreso pluvial (%)", 0.5, 100.0, 0.5, "100"),
    ("dry", "Caudal sanitario (m³/s)", 0.0, 0.05, 0.001, "0.000"),
)
PRESETS: Dict[str, Tuple[float, float]] = {
    "Oficial Guía (100%)": (100.0, 0.0),
    "Calibrado (2.5% + Q_san)": (2.5, 0.003),
}


class ControlsPanel(tk.Frame):
    """Panel lateral desplazable con pestañas Simulación y Recorridos (tarjetas planas)."""

    def __init__(self, parent: tk.Misc, fonts: Dict[str, Tuple[str, int, str]], callbacks: Dict[str, Callable]) -> None:
        super().__init__(parent, bg=theme.DOCK_BG)
        self._fonts, self._callbacks = fonts, callbacks
        self._label_to_scenario: Dict[str, PrecipitationScenario] = {}
        self._id_to_label: Dict[int, str] = {}
        self._playing = False
        self._wheel_active = False
        self._needs_scroll = False
        self._btn_styles: Dict[tk.Button, Tuple[str, str, str, str]] = {}
        self._rerun_after_id: Optional[str] = None
        self._applied_sig: Optional[tuple] = None
        self.rail_tab = "sim"

        self._build_tab_bar()
        self._canvas = tk.Canvas(self, bg=theme.DOCK_BG, highlightthickness=0, bd=0, takefocus=False)
        self._vscroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._vscroll.set)
        self._vscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._canvas, bg=theme.DOCK_BG)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")
        self._inner.bind("<Configure>", lambda _e: self.after_idle(self._sync_scroll))
        self._canvas.bind("<Configure>", self._on_canvas_resize)
        self._canvas.bind("<Enter>", lambda _e: self._toggle_wheel(True))
        self._canvas.bind("<Leave>", lambda _e: self._toggle_wheel(False))

        self._sim_page = tk.Frame(self._inner, bg=theme.DOCK_BG)
        self._trav_page = tk.Frame(self._inner, bg=theme.DOCK_BG)
        self._build_scenario_card()
        self._build_traversal_card()
        self._build_log_card()
        self._bind_wheel_recursive(self._inner)
        self.switch_tab("sim")

    # ── Pestañas ─────────────────────────────────────────────────────────────

    def _build_tab_bar(self) -> None:
        bar = tk.Frame(self, bg=theme.DOCK_BG)
        bar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 6))
        self.btn_tab_sim = self._btn(bar, "Simulación", lambda: self.switch_tab("sim"), primary=True, pady=5)
        self.btn_tab_sim.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        self.btn_tab_trav = self._btn(bar, "Recorridos", lambda: self.switch_tab("trav"), pady=5)
        self.btn_tab_trav.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
        tk.Frame(self, bg=theme.DOCK_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

    def _restyle(self, btn: tk.Button, primary: bool) -> None:
        bg, hov, fg, bdr = (
            (theme.ACCENT_PRIMARY, theme.ACCENT_HOVER, theme.ACCENT_INK, theme.ACCENT_HOVER) if primary
            else (theme.PAPER_SUBTLE, theme.PAPER_HOVER, theme.INK_PRIMARY, theme.PAPER_BORDER)
        )
        self._btn_styles[btn] = (bg, hov, fg, bdr)
        btn.configure(bg=bg, fg=fg, activebackground=hov, activeforeground=fg, highlightbackground=bdr)

    def switch_tab(self, tab_id: str) -> None:
        """Muestra la pestaña «sim» (Simulación) o «trav» (Recorridos)."""
        self.rail_tab = tab_id = "trav" if tab_id == "trav" else "sim"
        self._sim_page.pack_forget()
        self._trav_page.pack_forget()
        (self._trav_page if tab_id == "trav" else self._sim_page).pack(fill=tk.X)
        self._restyle(self.btn_tab_sim, tab_id == "sim")
        self._restyle(self.btn_tab_trav, tab_id == "trav")
        self._canvas.yview_moveto(0.0)
        self.after_idle(self._sync_scroll)

    def focus_search(self) -> None:
        """Abre la pestaña Recorridos y enfoca el campo de búsqueda (Ctrl+F)."""
        self.switch_tab("trav")
        self._search_entry.focus_set()
        self._search_entry.select_range(0, tk.END)

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
        wrap = max(160, event.width - 42)
        for name in ("_search_feedback", "_param_error"):
            if hasattr(self, name):
                getattr(self, name).configure(wraplength=wrap)
        self.after_idle(self._sync_scroll)

    def _on_wheel(self, event: tk.Event) -> None:
        if not self._wheel_active or not getattr(self, "_needs_scroll", False):
            return
        step = -1 if (event.num == 4 or (event.delta and event.delta > 0)) else 1
        self._canvas.yview_scroll(step, "units")

    def _bind_wheel_recursive(self, widget: tk.Misc) -> None:
        if isinstance(widget, (ttk.Combobox, tk.Text)):
            return
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            widget.bind(seq, self._on_wheel, add="+")
        for child in widget.winfo_children():
            self._bind_wheel_recursive(child)

    def _toggle_wheel(self, active: bool) -> None:
        self._wheel_active = active
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self._canvas.bind(seq, self._on_wheel) if active else self._canvas.unbind(seq)

    def _cb(self, key: str, *args: object) -> None:
        if (fn := self._callbacks.get(key)) is not None:
            fn(*args)

    def _make_card(self, parent: tk.Misc, title: str, bottom_pad: int = 0) -> tk.Frame:
        card = tk.Frame(parent, bg=theme.PAPER_BG, highlightbackground=theme.PAPER_RULE, highlightthickness=1, bd=0)
        card.pack(fill=tk.X, padx=6, pady=(6, bottom_pad))
        tk.Label(card, text=title, bg=theme.PAPER_BG, fg=theme.ACCENT_TEXT, font=self._fonts["label"], anchor="w").pack(fill=tk.X, padx=8, pady=(6, 3))
        tk.Frame(card, bg=theme.PAPER_BORDER, height=1).pack(fill=tk.X, padx=8, pady=(0, 5))
        body = tk.Frame(card, bg=theme.PAPER_BG)
        body.pack(fill=tk.X, padx=8, pady=(0, 7))
        return body

    def _lbl(self, parent: tk.Misc, text: str) -> tk.Label:
        return tk.Label(parent, text=text, bg=theme.PAPER_BG, fg=theme.INK_MUTED, font=self._fonts["small"], anchor="w")

    def _btn(
        self, parent: tk.Misc, text: str, command: Callable[[], None],
        primary: bool = False, dark: bool = False, pady: int = 4,
        bg: Optional[str] = None, hov: Optional[str] = None,
        fg: Optional[str] = None, bdr: Optional[str] = None,
    ) -> tk.Button:
        if bg is not None and hov is not None and fg is not None and bdr is not None:
            fnt = self._fonts["small"]
        elif primary:
            bg, hov, fg, bdr, fnt = theme.ACCENT_PRIMARY, theme.ACCENT_HOVER, theme.ACCENT_INK, theme.ACCENT_HOVER, self._fonts["label"]
        elif dark:
            bg, hov, fg, bdr, fnt = theme.SHELL_ELEVATED, theme.SHELL_HOVER, theme.SHELL_TEXT, theme.SHELL_BORDER, self._fonts["small"]
        else:
            bg, hov, fg, bdr, fnt = theme.PAPER_SUBTLE, theme.PAPER_HOVER, theme.INK_PRIMARY, theme.PAPER_BORDER, self._fonts["small"]
        btn = tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg, activebackground=hov, activeforeground=fg,
            relief="flat", bd=0, padx=6, pady=pady, font=fnt, cursor="hand2", highlightthickness=1, highlightbackground=bdr,
        )
        self._btn_styles[btn] = (bg, hov, fg, bdr)
        btn.bind("<Enter>", lambda _e, b=btn: str(b.cget("state")) != "disabled" and b.configure(bg=self._btn_styles[b][1]))
        btn.bind("<Leave>", lambda _e, b=btn: str(b.cget("state")) != "disabled" and b.configure(bg=self._btn_styles[b][0]))
        return btn

    def _set_btn_enabled(self, btn: tk.Button, enabled: bool) -> None:
        if enabled:
            bg, _hov, fg, bdr = self._btn_styles.get(
                btn, (theme.PAPER_SUBTLE, theme.PAPER_HOVER, theme.INK_PRIMARY, theme.PAPER_BORDER)
            )
            btn.configure(state="normal", cursor="hand2", bg=bg, fg=fg, highlightbackground=bdr)
        else:
            btn.configure(
                state="disabled", cursor="arrow", bg=theme.DISABLED_BG, fg=theme.DISABLED_FG,
                disabledforeground=theme.DISABLED_FG, highlightbackground=theme.PAPER_BORDER,
            )

    def _entry(self, parent: tk.Misc, var: tk.StringVar, justify: str = "center") -> tk.Entry:
        return tk.Entry(
            parent, textvariable=var, bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY, insertbackground=theme.INK_PRIMARY,
            relief="flat", bd=0, justify=justify, font=self._fonts["mono"], highlightthickness=1,
            highlightbackground=theme.PAPER_BORDER, highlightcolor=theme.ACCENT_PRIMARY,
        )

    def _menu_select(self, parent: tk.Misc, var: tk.StringVar, values: Tuple[str, ...] = (), pady: int = 4) -> _ScenarioMenuButton:
        return _ScenarioMenuButton(
            parent, textvariable=var, values=values, on_select=self._schedule_param_rerun,
            on_before_open=lambda: self._cb("pause_playback"), padx=6, pady=pady, ui_font=self._fonts["body"][0],
        )

    def _build_scenario_card(self) -> None:
        body = self._make_card(self._sim_page, "ESCENARIO Y PARÁMETROS")
        self._lbl(body, "Escenario de precipitación").pack(fill=tk.X)
        self._scenario_var = tk.StringVar()
        self._scenario_combo = self._menu_select(body, self._scenario_var, pady=5)
        self._scenario_combo.pack(fill=tk.X, pady=(2, 6))

        grid = tk.Frame(body, bg=theme.PAPER_BG)
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1)
        self._param_vars: Dict[str, tk.StringVar] = {}
        self._param_spins: Dict[str, tk.Spinbox] = {}
        for row, (key, label, lo, hi, inc, default) in enumerate(_PARAM_SPECS):
            var = self._param_vars[key] = tk.StringVar(value=default)
            tk.Label(grid, text=label, bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=self._fonts["small"], anchor="w").grid(row=row, column=0, sticky="w", pady=2)
            sb = tk.Spinbox(
                grid, textvariable=var, from_=lo, to=hi, increment=inc, command=self._schedule_param_rerun, width=8,
                bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, buttonbackground=theme.DOCK_BG, insertbackground=theme.ACCENT_PRIMARY,
                highlightthickness=1, highlightbackground=theme.DOCK_BORDER, highlightcolor=theme.ACCENT_PRIMARY,
                relief="flat", font=self._fonts["mono"], justify="right",
            )
            sb.grid(row=row, column=1, sticky="e", pady=2)
            sb.bind("<Return>", lambda _e: self._schedule_param_rerun())
            sb.bind("<FocusOut>", lambda _e: self._schedule_param_rerun())
            self._param_spins[key] = sb
        self._duration_var, self._storm_var, self._dt_var = (self._param_vars[k] for k in ("duration", "storm", "dt"))
        self._ingress_var, self._dry_var = self._param_vars["ingress"], self._param_vars["dry"]
        self._param_error = tk.Label(body, text="", bg=theme.ERROR_BG, fg=theme.ERROR_TEXT, font=self._fonts["small"], anchor="w", justify="left", wraplength=240, padx=5, pady=2)

        prow = tk.Frame(body, bg=theme.PAPER_BG)
        prow.pack(fill=tk.X, pady=(8, 4))
        for c, (name, (pct, dry)) in enumerate(PRESETS.items()):
            prow.columnconfigure(c, weight=1)
            self._btn(prow, name, lambda p=pct, d=dry: self.apply_preset(p, d), pady=4).grid(row=0, column=c, sticky="ew", padx=(0 if c == 0 else 3, 0))

        self._split_var = tk.StringVar(value=theme.SPLIT_RULE_TO_ES["proportional"])
        self._source_var = tk.StringVar(value=theme.SOURCE_DIST_TO_ES["capacity"])
        self._split_combo = self._source_combo = None
        for lbl, var, vals, attr in (
            ("Bifurcación", self._split_var, tuple(theme.SPLIT_RULE_TO_ES.values()), "_split_combo"),
            ("Reparto fuentes", self._source_var, tuple(theme.SOURCE_DIST_TO_ES.values()), "_source_combo"),
        ):
            row = tk.Frame(body, bg=theme.PAPER_BG)
            row.pack(fill=tk.X, pady=3)
            tk.Label(row, text=lbl, bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=self._fonts["small"]).pack(side=tk.LEFT)
            w = self._menu_select(row, var, vals, pady=3)
            w.configure(width=15)
            w.pack(side=tk.RIGHT)
            setattr(self, attr, w)

        self._btn_run = self._btn(body, "Ejecutar simulación", lambda: self._cb("run_simulation"), primary=True, pady=6)
        self._btn_run.pack(fill=tk.X, pady=(8, 0))

    def _build_traversal_card(self) -> None:
        body = self._make_card(self._trav_page, "BÚSQUEDA Y RECORRIDOS")
        self._lbl(body, "Búsqueda (ID exacto O(1) o texto parcial)").pack(fill=tk.X)
        srow = tk.Frame(body, bg=theme.PAPER_BG)
        srow.pack(fill=tk.X, pady=(2, 6))
        self._search_row = srow
        self._search_var = tk.StringVar()
        sentry = self._entry(srow, self._search_var, justify="left")
        sentry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        sentry.bind("<Return>", lambda _e: self._emit_search())
        sentry.bind("<KeyRelease>", lambda e: None if e.keysym == "Return" else self.clear_search_feedback())
        self._search_entry = sentry
        self._btn(srow, "Buscar", self._emit_search, pady=3).pack(side=tk.RIGHT, padx=(4, 0))
        self._search_feedback = tk.Label(
            body, text="", bg=theme.PAPER_BG, fg=theme.ERROR_TEXT,
            font=self._fonts["small"], anchor="w", justify="left", wraplength=240,
        )

        ngrid = tk.Frame(body, bg=theme.PAPER_BG)
        ngrid.pack(fill=tk.X, pady=(0, 3))
        self._start_var, self._target_var = tk.StringVar(value="6"), tk.StringVar(value="31")
        self._start_combo = ttk.Combobox(ngrid, textvariable=self._start_var, state="readonly", font=self._fonts["mono"])
        self._target_combo = ttk.Combobox(ngrid, textvariable=self._target_var, state="readonly", font=self._fonts["mono"])
        for c, (lbl, cb) in enumerate((("Inicio", self._start_combo), ("Destino", self._target_combo))):
            ngrid.columnconfigure(c, weight=1)
            pad = (0 if c == 0 else 4, 0)
            self._lbl(ngrid, lbl).grid(row=0, column=c, sticky="ew", padx=pad)
            cb.grid(row=1, column=c, sticky="ew", padx=pad, pady=(2, 0))

        self._lbl(body, "Aguas abajo y aguas arriba usan el nodo «Inicio».").pack(fill=tk.X, pady=(0, 5))

        row1 = tk.Frame(body, bg=theme.PAPER_BG)
        row1.pack(fill=tk.X, pady=(0, 3))
        for c, (lbl, cmd) in enumerate((
            ("BFS", lambda: self._emit_traversal("BFS", False)),
            ("DFS", lambda: self._emit_traversal("DFS", False)),
            ("Limpiar", lambda: self._cb("clear_traversal")),
        )):
            row1.columnconfigure(c, weight=1)
            self._btn(row1, lbl, cmd).grid(row=0, column=c, sticky="ew", padx=(0 if c == 0 else 3, 0))

        self.btn_anim = self._btn(body, "Animar recorrido", lambda: self._cb("toggle_anim"), primary=True, pady=4)
        self.btn_anim.pack(fill=tk.X, pady=(0, 3))

        row2 = tk.Frame(body, bg=theme.PAPER_BG)
        row2.pack(fill=tk.X)
        for c, (lbl, key, bg, hov, fg, bdr) in enumerate((
            ("▼ Aguas abajo", "trace_downstream", "#E0F2FE", "#BAE6FD", theme.TRAV_DOWNSTREAM_OUTLINE, theme.TRAV_DOWNSTREAM_EDGE),
            ("▲ Aguas arriba", "trace_upstream", "#F3E8FF", "#EDE9FE", theme.TRAV_UPSTREAM_OUTLINE, theme.TRAV_UPSTREAM_EDGE),
        )):
            row2.columnconfigure(c, weight=1)
            self._btn(row2, lbl, lambda k=key: self._emit_trace(k), bg=bg, hov=hov, fg=fg, bdr=bdr).grid(row=0, column=c, sticky="ew", padx=(0 if c == 0 else 3, 0))

    def _build_log_card(self) -> None:
        body = self._make_card(self._trav_page, "BITÁCORA DE RECORRIDO", bottom_pad=6)
        self._struct_box = tk.Frame(body, bg=theme.PAPER_SUBTLE, highlightthickness=1, highlightbackground=theme.DOCK_BORDER)
        self._struct_box.pack(fill=tk.X, pady=(0, 6))
        self._struct_header = tk.Label(
            self._struct_box, text="", bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY,
            font=self._fonts["mono_bold"], anchor="w", padx=6, pady=3,
        )
        self._struct_header.pack(fill=tk.X)
        self._struct_cells = tk.Frame(self._struct_box, bg=theme.PAPER_SUBTLE)
        self._struct_cells.pack(fill=tk.X, padx=5, pady=(0, 5))
        self._log_text = tk.Text(
            body, height=8, bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, highlightthickness=1,
            highlightbackground=theme.ACCENT_PRIMARY, relief="flat", font=self._fonts["mono"],
            wrap=tk.WORD, padx=8, pady=6, state=tk.DISABLED, takefocus=False,
        )
        self._log_text.pack(fill=tk.X)
        self.render_structure_strip("Queue", [])

    # ── Bitácora de recorrido ────────────────────────────────────────────────

    def render_structure_strip(self, structure_name: str, items: List[str], step_text: str = "") -> None:
        """Dibuja la tira de la estructura activa: primeros 6 elementos, cabeza resaltada."""
        for child in self._struct_cells.winfo_children():
            child.destroy()
        hdr = "Pila (Stack) · TOPE ↑" if structure_name == "Stack" else "Cola (Queue) · FRENTE → FINAL"
        self._struct_header.configure(text=f"{hdr}  [{step_text}]" if step_text else hdr)
        mono = self._fonts["mono"]

        def cell(text: str, bg: str, fg: str, bold: bool = True) -> None:
            tk.Label(
                self._struct_cells, text=text, bg=bg, fg=fg, font=self._fonts["mono_bold"] if bold else mono,
                padx=5, pady=2, highlightthickness=1, highlightbackground=theme.PAPER_BORDER if not bold else theme.DOCK_BORDER,
            ).pack(side=tk.LEFT, padx=(0, 2))

        if not items:
            cell("(vacía)", theme.PAPER_BG, theme.INK_MUTED, bold=False)
            return
        for idx, val in enumerate(items[:_STRIP_MAX_CELLS]):
            head = idx == 0
            cell(str(val), theme.ACCENT_PRIMARY if head else theme.PAPER_BG, theme.ACCENT_INK if head else theme.INK_PRIMARY)
        if len(items) > _STRIP_MAX_CELLS:
            cell(f"+{len(items) - _STRIP_MAX_CELLS}", theme.DOCK_BG, theme.INK_PRIMARY)

    def strip_items(self) -> List[str]:
        """Textos de las celdas de la tira (para pruebas y diagnóstico)."""
        return [w.cget("text") for w in self._struct_cells.winfo_children()]

    def strip_header(self) -> str:
        return str(self._struct_header.cget("text"))

    def set_traversal_log(self, text: str) -> None:
        self._log_text.configure(state=tk.NORMAL)
        self._log_text.delete("1.0", tk.END)
        self._log_text.insert("1.0", text)
        self._log_text.configure(state=tk.DISABLED)

    def get_traversal_log(self) -> str:
        return self._log_text.get("1.0", "end-1c")

    def update_traversal_view(
        self, frame: Optional[TraversalFrame] = None, summary_text: str = "", playing: bool = False,
        mode: Optional[str] = None, has_frames: Optional[bool] = None, step_text: Optional[str] = None,
    ) -> None:
        """Actualiza la tira Cola/Pila y el registro; sin fotograma ni texto restablece la bitácora."""
        self.set_traversal_playing(playing)
        if frame is not None:
            self.render_structure_strip(
                frame.structure_name, frame.structure_items,
                step_text if step_text is not None else f"{frame.step_index + 1}/{frame.total_steps}",
            )
            self.set_traversal_log(summary_text or (
                f"[{frame.algorithm} · Paso {frame.step_index + 1}/{frame.total_steps}]\n{frame.note}\n"
                f"{frame.structure_name}: {', '.join(frame.structure_items[:10]) or '(vacía)'}"
            ))
        else:
            self.render_structure_strip("Queue", [])
            self.set_traversal_log(summary_text)

    def set_traversal_playing(self, playing: bool) -> None:
        """Actualiza el estado de reproducción del recorrido y el rótulo del botón."""
        self._playing = bool(playing)
        self.btn_anim.configure(text="Detener animación" if self._playing else "Animar recorrido")

    # ── Parámetros y re-simulación ───────────────────────────────────────────

    def _param_sig(self) -> tuple:
        return (self._scenario_var.get(), self._split_var.get(), self._source_var.get(),
                *(self._param_vars[k].get().strip() for k, *_ in _PARAM_SPECS))

    def _schedule_param_rerun(self) -> None:
        """Re-simulación automática con debounce de 140 ms al cambiar parámetros."""
        if self._rerun_after_id is not None:
            self.after_cancel(self._rerun_after_id)
        self._rerun_after_id = self.after(_RERUN_DEBOUNCE_MS, self._fire_param_rerun)

    def _fire_param_rerun(self) -> None:
        self._rerun_after_id = None
        if self._param_sig() == self._applied_sig:
            return
        try:
            self.get_simulation_config()
        except ValueError as exc:
            self._param_error.configure(text=str(exc))
            self._param_error.pack(fill=tk.X, pady=(4, 0), after=self._param_spins["dry"].master)
            return
        self._cb("param_changed")

    def cancel_pending(self) -> None:
        if self._rerun_after_id is not None:
            try:
                self.after_cancel(self._rerun_after_id)
            except tk.TclError:
                pass
            self._rerun_after_id = None

    def apply_preset(self, ingress_pct: float, dry_flow: float) -> None:
        """Aplica un preset de calibración (ingreso pluvial % y Q sanitario) y re-simula."""
        self._ingress_var.set(f"{ingress_pct:g}")
        self._dry_var.set(f"{dry_flow:.3f}")
        self._schedule_param_rerun()

    def show_search_feedback(self, message: str, is_error: bool = False) -> None:
        if is_error:
            self._search_entry.configure(highlightbackground=theme.ERROR_TEXT)
            self._search_feedback.configure(text=message, fg=theme.ERROR_TEXT, bg=theme.ERROR_BG, padx=5, pady=2)
        else:
            self._search_entry.configure(highlightbackground=theme.PAPER_BORDER)
            self._search_feedback.configure(text=message, fg=theme.OK_TEXT, bg=theme.PAPER_BG, padx=0, pady=0)
        self._search_feedback.pack(fill=tk.X, pady=(0, 5), after=self._search_row)

    def clear_search_feedback(self) -> None:
        self._search_entry.configure(highlightbackground=theme.PAPER_BORDER)
        self._search_feedback.pack_forget()

    def _emit_search(self) -> None:
        if q := self._search_var.get().strip():
            self.clear_search_feedback()
            self._cb("search", q)
        else:
            self.show_search_feedback("Ingresa un ID (ej. 17, P30) o parte del texto (ej. PTAR).", is_error=True)
            self._search_entry.focus_set()

    def _emit_traversal(self, algo: str, animate: bool) -> None:
        start_id = self._start_var.get().strip()
        if not start_id:
            self.show_search_feedback("Selecciona un nodo de inicio primero.", is_error=True)
            return
        raw_t = self._target_var.get().strip()
        target_id = None if (not raw_t or raw_t == _NONE_TARGET) else raw_t
        self._cb("run_traversal", algo, start_id, target_id, animate)

    def _emit_trace(self, key: str) -> None:
        start_id = self._start_var.get().strip()
        if not start_id:
            self.show_search_feedback("Selecciona un nodo de inicio primero.", is_error=True)
            return
        self._cb(key, start_id)

    def populate_dataset(self, dataset: NetworkDataset) -> None:
        """Carga escenarios y nodos del dataset en los selectores del panel."""
        self._label_to_scenario.clear()
        self._id_to_label.clear()
        labels: List[str] = []
        for sc in dataset.scenarios:
            lbl = theme.format_scenario_label(sc.scenario_id, sc.condition, sc.intensity_mm_h)
            self._label_to_scenario[lbl] = sc
            self._id_to_label[sc.scenario_id] = lbl
            labels.append(lbl)
        self._scenario_combo.set_values(labels)
        if labels:
            self._scenario_var.set(labels[0])

        node_ids, sources, sinks = dataset.graph.node_ids(), dataset.graph.source_ids(), dataset.graph.sink_ids()
        self._start_combo.configure(values=node_ids)
        self._start_var.set("6" if "6" in node_ids else (sources[0] if sources else (node_ids[0] if node_ids else "")))
        self._target_combo.configure(values=[_NONE_TARGET] + node_ids)
        self._target_var.set("31" if "31" in sinks else (sinks[0] if sinks else _NONE_TARGET))

    def set_start_node(self, node_id: str) -> None:
        """Fija el nodo «Inicio» de recorridos/trazas (p. ej. al inspeccionar un nodo)."""
        self._start_var.set(node_id)

    def select_scenario_by_id(self, scenario_id: int) -> None:
        """Selecciona un escenario en el desplegable por su identificador."""
        if (label := self._id_to_label.get(scenario_id)) is not None:
            self._scenario_var.set(label)

    def get_simulation_config(self) -> SimulationConfig:
        """Valida los parámetros (rangos de la interfaz) y construye SimulationConfig."""
        if (sc := self._label_to_scenario.get(self._scenario_var.get())) is None:
            raise ValueError("Seleccione un escenario de precipitación válido.")
        vals: Dict[str, float] = {}
        for key, label, lo, hi, _inc, _d in _PARAM_SPECS:
            raw = self._param_vars[key].get().strip().replace(",", ".")
            try:
                v = float(raw)
            except ValueError as exc:
                raise ValueError(f"«{label}» debe ser un número válido.") from exc
            if not math.isfinite(v) or not (lo - 1e-12 <= v <= hi + 1e-12):
                raise ValueError(f"«{label}» debe estar entre {lo:g} y {hi:g}.")
            vals[key] = v
        duration, storm, dt = vals["duration"], vals["storm"], vals["dt"]
        if dt > duration:
            raise ValueError("El paso temporal Δt no puede superar la duración total.")
        if storm > duration:
            storm = duration
            self._storm_var.set(f"{storm:g}")
        cfg = SimulationConfig(
            scenario_id=sc.scenario_id, scenario_name=sc.condition, intensity_mm_h=sc.intensity_mm_h,
            duration_min=duration, storm_duration_min=storm, dt_min=dt,
            split_rule=theme.SPLIT_RULE_FROM_ES.get(self._split_var.get(), "proportional"),
            source_distribution=theme.SOURCE_DIST_FROM_ES.get(self._source_var.get(), "capacity"),
            ingress_factor=vals["ingress"] / 100.0, dry_weather_flow_per_source_m3s=vals["dry"],
        )
        self._applied_sig = self._param_sig()
        self._param_error.pack_forget()
        return cfg

    def get_traversal_endpoints(self) -> Tuple[str, Optional[str]]:
        """Nodo de inicio y destino (None si «(Ninguno)») seleccionados en el panel."""
        raw_t = self._target_var.get().strip()
        return self._start_var.get().strip(), (None if (not raw_t or raw_t == _NONE_TARGET) else raw_t)
