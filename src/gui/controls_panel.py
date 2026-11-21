"""Panel izquierdo de controles, escenarios, recorridos BFS/DFS y visor de Cola/Pila."""

import math
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from src.algorithms.traversals import TraversalFrame
from src.io.data_loader import NetworkDataset, PrecipitationScenario
from src.simulation.models import SimulationConfig
from . import theme

_NONE_TARGET = "(Ninguno)"


class ControlsPanel(tk.Frame):
    """Panel lateral desplazable con tarjetas planas de simulación y recorridos."""

    def __init__(self, parent: tk.Misc, fonts: Dict[str, Tuple[str, int, str]], callbacks: Dict[str, Callable]) -> None:
        super().__init__(parent, bg=theme.DOCK_BG)
        self._fonts, self._callbacks = fonts, callbacks
        self._label_to_scenario: Dict[str, PrecipitationScenario] = {}
        self._id_to_label: Dict[int, str] = {}
        self._playing = False
        self._wheel_active = False
        self._needs_scroll = False
        self._btn_styles: Dict[tk.Button, Tuple[str, str, str, str]] = {}

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

        self._build_scenario_card()
        self._build_traversal_card()
        self._bind_wheel_recursive(self._inner)

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
        if hasattr(self, "_search_feedback"):
            self._search_feedback.configure(wraplength=wrap)
        if hasattr(self, "_traversal_note"):
            self._traversal_note.configure(wraplength=wrap)
        self.after_idle(self._sync_scroll)

    def _on_wheel(self, event: tk.Event) -> None:
        if not self._wheel_active or not getattr(self, "_needs_scroll", False):
            return
        step = -1 if (event.num == 4 or (event.delta and event.delta > 0)) else 1
        self._canvas.yview_scroll(step, "units")

    def _bind_wheel_recursive(self, widget: tk.Misc) -> None:
        if isinstance(widget, ttk.Combobox):
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

    def _make_card(self, title: str, bottom_pad: int = 0) -> tk.Frame:
        card = tk.Frame(self._inner, bg=theme.PAPER_BG, highlightbackground=theme.PAPER_RULE, highlightthickness=1, bd=0)
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
        btn.bind("<Enter>", lambda _e, b=btn, h=hov: str(b.cget("state")) != "disabled" and b.configure(bg=h))
        btn.bind("<Leave>", lambda _e, b=btn, c=bg: str(b.cget("state")) != "disabled" and b.configure(bg=c))
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

    def _build_scenario_card(self) -> None:
        body = self._make_card("DATOS Y ESCENARIO")
        io_row = tk.Frame(body, bg=theme.PAPER_BG)
        io_row.pack(fill=tk.X, pady=(0, 6))
        for c, (lbl, key) in enumerate((("Excel", "load_excel"), ("CSV", "load_csv"), ("Exportar CSV", "export_csv"))):
            io_row.columnconfigure(c, weight=1)
            self._btn(io_row, lbl, lambda k=key: self._cb(k)).grid(row=0, column=c, sticky="ew", padx=(0 if c == 0 else 3, 0))

        self._lbl(body, "Escenario de precipitación").pack(fill=tk.X)
        self._scenario_var = tk.StringVar()
        self._scenario_combo = ttk.Combobox(body, textvariable=self._scenario_var, state="readonly", font=self._fonts["body"])
        self._scenario_combo.pack(fill=tk.X, pady=(2, 6))

        tgrid = tk.Frame(body, bg=theme.PAPER_BG)
        tgrid.pack(fill=tk.X, pady=(0, 6))
        self._duration_var, self._storm_var, self._dt_var = tk.StringVar(value="90"), tk.StringVar(value="60"), tk.StringVar(value="1.0")
        for c, (lbl, var) in enumerate((("Duración (min)", self._duration_var), ("Lluvia (min)", self._storm_var), ("Δt (min)", self._dt_var))):
            tgrid.columnconfigure(c, weight=1)
            pad = (0 if c == 0 else 4, 0)
            self._lbl(tgrid, lbl).grid(row=0, column=c, sticky="ew", padx=pad)
            self._entry(tgrid, var).grid(row=1, column=c, sticky="ew", padx=pad, pady=(2, 0), ipady=2)

        rgrid = tk.Frame(body, bg=theme.PAPER_BG)
        rgrid.pack(fill=tk.X, pady=(0, 7))
        self._split_var = tk.StringVar(value=theme.SPLIT_RULE_TO_ES["proportional"])
        self._source_var = tk.StringVar(value=theme.SOURCE_DIST_TO_ES["capacity"])
        for c, (lbl, var, vals) in enumerate((
            ("Bifurcación", self._split_var, list(theme.SPLIT_RULE_TO_ES.values())),
            ("Fuentes", self._source_var, list(theme.SOURCE_DIST_TO_ES.values())),
        )):
            rgrid.columnconfigure(c, weight=1)
            pad = (0 if c == 0 else 4, 0)
            self._lbl(rgrid, lbl).grid(row=0, column=c, sticky="ew", padx=pad)
            ttk.Combobox(rgrid, textvariable=var, values=vals, state="readonly", font=self._fonts["small"]).grid(row=1, column=c, sticky="ew", padx=pad, pady=(2, 0))

        self._btn(body, "Ejecutar simulación", lambda: self._cb("run_simulation"), primary=True, pady=6).pack(fill=tk.X)

    def _build_traversal_card(self) -> None:
        body = self._make_card("RECORRIDOS BFS / DFS Y BÚSQUEDA", bottom_pad=6)
        self._lbl(body, "Búsqueda O(1) (ID de nodo o tubería)").pack(fill=tk.X)
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
        self._start_var, self._target_var = tk.StringVar(), tk.StringVar(value=_NONE_TARGET)
        self._start_combo = ttk.Combobox(ngrid, textvariable=self._start_var, state="readonly", font=self._fonts["mono"])
        self._target_combo = ttk.Combobox(ngrid, textvariable=self._target_var, state="readonly", font=self._fonts["mono"])
        for c, (lbl, cb) in enumerate((("Inicio", self._start_combo), ("Destino", self._target_combo))):
            ngrid.columnconfigure(c, weight=1)
            pad = (0 if c == 0 else 4, 0)
            self._lbl(ngrid, lbl).grid(row=0, column=c, sticky="ew", padx=pad)
            cb.grid(row=1, column=c, sticky="ew", padx=pad, pady=(2, 0))

        self._lbl(body, "Aguas abajo y aguas arriba usan el nodo «Inicio».").pack(fill=tk.X, pady=(0, 5))

        agrid = tk.Frame(body, bg=theme.PAPER_BG)
        agrid.pack(fill=tk.X, pady=(0, 4))
        for c in (0, 1):
            agrid.columnconfigure(c, weight=1)
        for idx, (lbl, algo, anim) in enumerate((("BFS", "BFS", False), ("DFS", "DFS", False), ("Animar BFS", "BFS", True), ("Animar DFS", "DFS", True))):
            r, c = divmod(idx, 2)
            self._btn(agrid, lbl, lambda a=algo, an=anim: self._emit_traversal(a, an)).grid(row=r, column=c, sticky="ew", padx=(0 if c == 0 else 3, 0), pady=(0 if r == 0 else 3, 0))

        trow = tk.Frame(body, bg=theme.PAPER_BG)
        trow.pack(fill=tk.X)
        trace_specs = (
            ("▼ Aguas abajo", lambda: self._emit_trace("trace_downstream"), "#E0F2FE", "#BAE6FD", theme.TRAV_DOWNSTREAM_OUTLINE, theme.TRAV_DOWNSTREAM_EDGE),
            ("▲ Aguas arriba", lambda: self._emit_trace("trace_upstream"), "#F3E8FF", "#EDE9FE", theme.TRAV_UPSTREAM_OUTLINE, theme.TRAV_UPSTREAM_EDGE),
            ("Limpiar", lambda: self._cb("clear_traversal"), None, None, None, None),
        )
        for c, (lbl, cmd, bg, hov, fg, bdr) in enumerate(trace_specs):
            trow.columnconfigure(c, weight=1)
            self._btn(trow, lbl, cmd, bg=bg, hov=hov, fg=fg, bdr=bdr).grid(row=0, column=c, sticky="ew", padx=(0 if c == 0 else 3, 0))

        self._traversal_note = tk.Label(
            body, text="", bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY,
            font=self._fonts["small"], justify="left", anchor="w", padx=6, pady=4, wraplength=240,
        )

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
            self.show_search_feedback("Ingresa un ID de nodo (ej. 17) o tubería (ej. P30).", is_error=True)
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
        self._scenario_combo.configure(values=labels)
        if labels:
            self._scenario_var.set(labels[0])

        node_ids, sources, sinks = dataset.graph.node_ids(), dataset.graph.source_ids(), dataset.graph.sink_ids()
        self._start_combo.configure(values=node_ids)
        self._start_var.set("17" if "17" in sources else (sources[0] if sources else (node_ids[0] if node_ids else "")))
        self._target_combo.configure(values=[_NONE_TARGET] + node_ids)
        self._target_var.set("31" if "31" in sinks else (sinks[0] if sinks else _NONE_TARGET))

    def select_scenario_by_id(self, scenario_id: int) -> None:
        """Selecciona un escenario en el desplegable por su identificador."""
        if (label := self._id_to_label.get(scenario_id)) is not None:
            self._scenario_var.set(label)

    def get_simulation_config(self) -> SimulationConfig:
        """Valida los parámetros numéricos y construye SimulationConfig."""
        if (sc := self._label_to_scenario.get(self._scenario_var.get())) is None:
            raise ValueError("Seleccione un escenario de precipitación válido.")
        try:
            duration = float(self._duration_var.get().strip())
            storm = float(self._storm_var.get().strip())
            dt = float(self._dt_var.get().strip())
        except ValueError as exc:
            raise ValueError("Duración, Lluvia y Δt deben ser valores numéricos válidos.") from exc

        if not all(math.isfinite(v) for v in (duration, storm, dt)):
            raise ValueError("Los parámetros temporales deben ser números finitos.")
        if duration <= 0.0 or storm <= 0.0 or dt <= 0.0:
            raise ValueError("Duración, Lluvia y Δt deben ser mayores que 0 min.")
        if dt > duration:
            raise ValueError("El paso temporal Δt no puede superar la duración total.")
        if storm > duration:
            storm = duration
            self._storm_var.set(f"{storm:g}")

        return SimulationConfig(
            scenario_id=sc.scenario_id, scenario_name=sc.condition, intensity_mm_h=sc.intensity_mm_h,
            duration_min=duration, storm_duration_min=storm, dt_min=dt,
            split_rule=theme.SPLIT_RULE_FROM_ES.get(self._split_var.get(), "proportional"),
            source_distribution=theme.SOURCE_DIST_FROM_ES.get(self._source_var.get(), "capacity"),
        )

    def update_traversal_view(
        self, frame: Optional[TraversalFrame] = None, summary_text: str = "", playing: bool = False,
        mode: Optional[str] = None, has_frames: Optional[bool] = None,
    ) -> None:
        """Actualiza la nota compacta de recorrido/traza en el panel."""
        self.set_traversal_playing(playing)
        msg = summary_text or (frame.note if frame else "")
        if msg:
            self._traversal_note.configure(text=msg)
            self._traversal_note.pack(fill=tk.X, pady=(6, 0))
        else:
            self._traversal_note.configure(text="")
            self._traversal_note.pack_forget()

    def set_traversal_playing(self, playing: bool) -> None:
        """Actualiza el estado de reproducción del recorrido."""
        self._playing = bool(playing)
