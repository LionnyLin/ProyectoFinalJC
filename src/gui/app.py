"""Ventana principal del Simulador de Alcantarillado — Ciudad Bicentenario."""

from __future__ import annotations

import os, time
from dataclasses import replace
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional, Tuple

from src.algorithms import (
    OVERLOAD_PERSISTENCE_LEVELS, TraversalFrame, TraversalResult, bfs, classify_overload_persistence, classify_utilization,
    compute_source_attribution, dfs, find_isolated_from_sinks, search_entities, search_entity, trace_downstream,
    trace_upstream, trace_upstream_result,
)
from src.data_structures import PipeEdge
from src.io.data_loader import DataLoadError, NetworkDataset, export_to_csv_dir, load_dataset
from src.simulation import (
    MODEL_ASSUMPTIONS_TEXT, PipeIntervention, ScenarioSummary, SewerSimulationEngine, SimulationConfig,
    SimulationResult, TimeStepSnapshot, compare_all_scenarios, generate_docx_report, generate_markdown_report,
)
from . import theme
from .charts_panel import ChartsPanel
from .comparison_panel import ComparisonPanel
from .controls_panel import ControlsPanel
from .guided_tour import GuidedTourController
from .icons import build_icon_set
from .inspector_panel import CriticalPipesTab, InspectorTab
from .network_canvas import NetworkCanvas

_SPEED_MS: Dict[str, int] = theme.PLAY_SPEED_MS
_ANIM_MS_BY_ALGO: Dict[str, int] = {"BFS": 560, "DFS": 340}
_TRAVERSAL_ANIM_MS = 560
_BASE_SPEED_MS = _SPEED_MS["1x"]  # referencia del factor de velocidad de los pulsos de flujo
_MAP_MODE_IDS = tuple(m for m, _ in theme.MAP_MODES)
_ATTR_THROTTLE_S = 0.25  # composición por fuente durante la reproducción: ≥ 250 ms entre cálculos
_TYPING_CLASSES = ("Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox", "Text")
_BUTTON_CLASSES = ("Button", "TButton", "Menubutton", "Checkbutton", "TCheckbutton")
_ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_BTN_PAL = {
    "primary": (theme.ACCENT_PRIMARY, theme.ACCENT_HOVER, theme.ACCENT_INK, theme.ACCENT_HOVER, "label"),
    "dark": (theme.SHELL_ELEVATED, theme.SHELL_HOVER, theme.SHELL_TEXT, theme.SHELL_BORDER, "small"),
    "light": (theme.PAPER_SUBTLE, theme.PAPER_HOVER, theme.INK_PRIMARY, theme.PAPER_BORDER, "small"),
    "dark_primary": (theme.ACCENT_ON_DARK, theme.ACCENT_ON_DARK_HOVER, theme.ACCENT_ON_DARK_INK, theme.ACCENT_ON_DARK, "small"),
}


def _base_key(c: SimulationConfig) -> tuple:
    return (c.duration_min, c.storm_duration_min, c.dt_min, c.split_rule, c.source_distribution,
            c.max_manhole_storage_m3, c.ingress_factor, c.dry_weather_flow_per_source_m3s,
            tuple(sorted(c.interventions.items())))


class BicentenarioSewerApp(tk.Tk):
    """Orquestador principal de la GUI: dueño único del estado y coordinación de paneles."""

    def __init__(self, initial_data_path: Optional[str] = None) -> None:
        super().__init__()
        self.title("Simulador de Alcantarillado — Ciudad Bicentenario")
        self.geometry("1320x780"); self.minsize(780, 540); self.configure(bg=theme.DOCK_BG)
        self.fonts = theme.resolve_fonts(self)
        self.style = theme.apply_ttk_theme(self, self.fonts)
        self._dpi_scale = theme.resolve_dpi_scale(self)
        self._icons = build_icon_set(
            fg_dark=theme.SHELL_TEXT, fg_light=theme.INK_PRIMARY, fg_on_accent=theme.ACCENT_INK,
            accent_color=theme.ACCENT_PRIMARY, scale=self._dpi_scale,
        )  # referencias vivas: evitan que el GC libere las PhotoImage

        # Estado UI (dueño único)
        self.dataset: Optional[NetworkDataset] = None
        self.result: Optional[SimulationResult] = None
        self.current_step, self.is_playing, self.play_speed_ms = 0, False, _SPEED_MS["2x"]
        self.selected_kind: Optional[str] = None; self.selected_id: Optional[str] = None
        self.traversal_frames: List[TraversalFrame] = []
        self.anim_idx, self.anim_playing = 0, False
        self.cached_comparisons: Optional[List[ScenarioSummary]] = None
        self._play_after_id: Optional[str] = None; self._anim_after_id: Optional[str] = None
        self._traversal_result: Optional[TraversalResult] = None
        self._base_compare_key: Optional[tuple] = None
        self._last_chart_pipe: Optional[str] = None; self._updating_slider = False
        self._btn_styles: Dict[tk.Button, Tuple[str, str, str]] = {}
        self._slider_dragging = False
        self._slider_restore_pending = False
        self._slider_after_id: Optional[str] = None
        self._pending_slider_step: Optional[int] = None
        self._traversal_mode: Optional[str] = None
        self._traversal_origin: Optional[str] = None
        self._traversal_banner: str = ""
        self._traversal_log: str = ""
        self._last_traversal_algo = "BFS"
        # Estado responsivo y de paneles
        self._show_left, self._show_right = True, True
        self._layout_tier = ""
        self._topbar_sig: Optional[tuple] = None
        self._resize_after_id: Optional[str] = None
        self._closing = False
        self._player_compact: Optional[bool] = None
        # Intervenciones en vivo, línea base (Antes/Después), cuenca aislada y composición por fuente
        self.interventions: Dict[str, PipeIntervention] = {}
        self.previous_result: Optional[SimulationResult] = None   # línea base original para Antes/Después
        self._baseline_result: Optional[SimulationResult] = None
        self.isolated_nodes: set = set(); self.isolated_pipes: set = set()
        self._canvas_int_sig: Optional[tuple] = None
        self.basin_focus_active = False
        self._inspector_trace: Optional[Tuple[str, str]] = None   # (nodo, "up"|"down")
        self._attr_key: Optional[tuple] = None; self._attr_time = 0.0
        # Modo de lectura cartográfica, ruta activa del recorrido y caché de textos de cabecera
        self._map_mode = "instant"
        self._map_mode_buttons: Dict[str, tk.Button] = {}
        self._map_mode_tier: Optional[str] = None
        self._active_route: List[PipeEdge] = []
        self._last_chart_node: Optional[str] = None
        self._txt_cache: Dict[tk.Widget, tuple] = {}
        self.tour = GuidedTourController(self)  # recorrido guiado (G12): ficha, paradas y foco

        self._build_ui()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        xlsx = os.path.join(_ROOT_DIR, "data", "DataSetBicentenario.xlsx")
        start_path = initial_data_path or (xlsx if os.path.exists(xlsx) else os.path.join(_ROOT_DIR, "data", "csv"))
        if start_path and os.path.exists(start_path): self.load_data(start_path)
        self.update_idletasks()
        self._apply_responsive_layout(self.winfo_width(), self.winfo_height())

    def _btn(self, parent: tk.Misc, text: str, cmd: Callable[[], None], style: str = "light", padx: int = 8, pady: int = 3,
             icon: Optional[str] = None) -> tk.Button:
        bg, hov, fg, bdr, fk = _BTN_PAL[style]
        kw = {"image": self._icons[icon], "compound": tk.LEFT} if icon else {}
        b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg, activebackground=hov, activeforeground=fg,
                      relief="flat", bd=0, padx=padx, pady=pady, font=self.fonts[fk], cursor="hand2", highlightthickness=1, highlightbackground=bdr, **kw)
        self._btn_styles[b] = (bg, hov, fg)
        b.bind("<Enter>", lambda _e, w=b: w.configure(bg=self._btn_styles[w][1]) if str(w.cget("state")) != "disabled" else None)
        b.bind("<Leave>", lambda _e, w=b: w.configure(bg=self._btn_styles[w][0]) if str(w.cget("state")) != "disabled" else None)
        return b

    def _restyle_btn(self, btn: tk.Button, style: str) -> None:
        bg, hov, fg, bdr, _fk = _BTN_PAL[style]
        self._btn_styles[btn] = (bg, hov, fg)
        btn.configure(bg=bg, fg=fg, activebackground=hov, activeforeground=fg, highlightbackground=bdr)

    def _set_btn_enabled(self, btn: tk.Button, enabled: bool) -> None:
        bg, _hov, fg = self._btn_styles.get(btn, (theme.PAPER_SUBTLE, theme.PAPER_HOVER, theme.INK_PRIMARY))
        if enabled:
            btn.configure(state="normal", cursor="hand2", bg=bg, fg=fg)
        else:
            btn.configure(
                state="disabled",
                cursor="arrow",
                bg=theme.DISABLED_BG,
                fg=theme.DISABLED_FG,
                disabledforeground=theme.DISABLED_FG,
            )

    def _build_ui(self) -> None:
        self._build_topbar()
        tk.Frame(self, bg=theme.ACCENT_PRIMARY, height=3).pack(side=tk.TOP, fill=tk.X)
        self._build_legend_bar()
        tk.Frame(self, bg=theme.DOCK_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

        # Barra de estado inferior (se empaqueta antes del área expandible)
        statusbar = tk.Frame(self, bg=theme.SHELL_BG)
        statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(self, bg=theme.ACCENT_PRIMARY, height=2).pack(side=tk.BOTTOM, fill=tk.X)
        self._status_lbl = tk.Label(statusbar, text="Listo", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, font=self.fonts["small"], anchor="w")
        self._status_lbl.pack(side=tk.LEFT, padx=12, pady=3)
        self.lbl_shortcuts_hint = tk.Label(
            statusbar, text="Espacio: Reproducir/Pausar  ·  ←/→: Paso  ·  Inicio: t=0  ·  Ctrl+F: Buscar  ·  Esc: Limpiar",
            bg=theme.SHELL_BG, fg=theme.SHELL_TEXT_MUTED, font=self.fonts["small"],
        )
        self.lbl_shortcuts_hint.pack(side=tk.RIGHT, padx=12, pady=3)

        self.paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg=theme.DOCK_BORDER, sashwidth=4, bd=0, relief="flat", opaqueresize=True)
        self.paned.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.controls = ControlsPanel(self.paned, self.fonts, {
            "run_simulation": lambda: self.run_simulation(auto_play=True),
            "param_changed": lambda: self.run_simulation(),
            "pause_playback": lambda: self._stop_playback(True),
            "search": self._action_search, "run_traversal": self._action_traversal,
            "trace_downstream": lambda s: self._action_trace(s, False), "trace_upstream": lambda s: self._action_trace(s, True),
            "clear_traversal": self.clear_traversal, "toggle_anim": self._action_toggle_anim,
        })

        self._center = center = tk.Frame(self.paned, bg=theme.DOCK_BG)
        self._build_kpi_header(center)
        self._build_map_mode_bar(center)
        self.network_canvas = NetworkCanvas(center, fonts=self.fonts, on_select=self.select_entity)
        self.network_canvas.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        self.tour.build_card(self.network_canvas)
        self._build_player(center)

        self.notebook = ttk.Notebook(self.paned)
        self.inspector_tab = InspectorTab(self.notebook, self.fonts, {
            "focus": self._action_focus_selected, "basin": self._action_toggle_basin,
            "trace": self._action_toggle_inspector_trace, "apply": self._action_apply_intervention,
            "restore_pipe": self._action_restore_pipe, "restore_all": self._action_restore_all,
        })
        self.critical_tab = CriticalPipesTab(self.notebook, self.fonts, on_select_pipe=lambda pid: self.select_entity("pipe", pid),
                                             on_focus_pipe=lambda pid: self.network_canvas.focus_pipe(pid))
        self.charts_panel = ChartsPanel(self.notebook, self.fonts)
        self.comparison_panel = ComparisonPanel(self.notebook, self.fonts, self.run_comparison, lambda sid: (self.controls.select_scenario_by_id(sid), self.run_simulation()))
        for w, title in ((self.inspector_tab, "Inspector"), (self.critical_tab, "Tuberías Críticas"), (self.charts_panel, "Evolución"), (self.comparison_panel, "Comparación")):
            self.notebook.add(w, text=title)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._sync_panes()
        self._update_toggle_styles()
        self.bind("<Configure>", self._on_window_configure)

    def _build_topbar(self) -> None:
        self.topbar = tk.Frame(self, bg=theme.SHELL_BG)
        self.topbar.pack(side=tk.TOP, fill=tk.X)
        left = tk.Frame(self.topbar, bg=theme.SHELL_BG)
        left.pack(side=tk.LEFT, padx=(10, 8), pady=6)
        tk.Label(left, image=self._icons["brand_network"], bg=theme.SHELL_BG).pack(side=tk.LEFT, padx=(0, 8))
        wrap = tk.Frame(left, bg=theme.SHELL_BG)
        wrap.pack(side=tk.LEFT, padx=(0, 14))
        self.lbl_app_title = tk.Label(wrap, text="Simulador de Alcantarillado — Ciudad Bicentenario", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, font=self.fonts["headline"], anchor="w")
        self.lbl_app_title.pack(anchor="w")
        self.lbl_app_subtitle = tk.Label(wrap, text="Red dirigida de alcantarillado hacia PTAR Punta Canoa (Nodo 31)", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT_MUTED, font=self.fonts["small"], anchor="w")
        self.lbl_app_subtitle.pack(anchor="w")
        self.btn_toggle_left = self._btn(left, " Controles", self.toggle_left_panel, "dark", padx=9, pady=4, icon="sliders_light")
        self.btn_toggle_left.pack(side=tk.LEFT, padx=(0, 6))
        self.btn_toggle_right = self._btn(left, " Análisis", self.toggle_right_panel, "dark", padx=9, pady=4, icon="chart_light")
        self.btn_toggle_right.pack(side=tk.LEFT)

        self.actions_bar = tk.Frame(self.topbar, bg=theme.SHELL_BG)
        self.actions_bar.pack(side=tk.RIGHT, padx=10, pady=6)
        mk = lambda text, cmd: self._btn(self.actions_bar, text, cmd, "dark", padx=9, pady=4)
        self.btn_load_excel, self.btn_load_csv = mk("Cargar Excel", lambda: self._pick_and_load(False)), mk("Cargar CSV", lambda: self._pick_and_load(True))
        self.btn_export_csv, self.btn_assumptions = mk("Exportar CSV", self._action_export_csv), mk("Supuestos", self._show_assumptions)
        self.btn_export_md, self.btn_export_docx = mk("Exportar MD/CSV", lambda: self._action_export("md")), mk("Exportar Word", lambda: self._action_export("docx"))
        self.menu_btn_file = tk.Menubutton(
            self.actions_bar, text="Archivo y Modelo ", image=self._icons["chevron_light"], compound=tk.RIGHT,
            bg=theme.SHELL_ELEVATED, fg=theme.SHELL_TEXT, activebackground=theme.SHELL_HOVER, activeforeground=theme.SHELL_TEXT,
            relief="flat", bd=0, padx=10, pady=5, font=self.fonts["small"], cursor="hand2",
            highlightthickness=1, highlightbackground=theme.ACCENT_PRIMARY,
        )
        menu = tk.Menu(self.menu_btn_file, tearoff=0, bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, activebackground=theme.ACCENT_PRIMARY, activeforeground=theme.ACCENT_INK, font=self.fonts["body"])
        for item in (("Cargar Excel (.xlsx)...", lambda: self._pick_and_load(False)), ("Cargar carpeta CSV...", lambda: self._pick_and_load(True)),
                           ("Exportar CSV...", self._action_export_csv), None, ("Supuestos del modelo", self._show_assumptions), None,
                           ("Exportar reporte Word...", lambda: self._action_export("docx")), ("Exportar reporte MD/CSV...", lambda: self._action_export("md"))):
            menu.add_separator() if item is None else menu.add_command(label=item[0], command=item[1])
        self.menu_btn_file.configure(menu=menu)
        self.btn_guided_tour = self._btn(self.actions_bar, "Recorrido guiado", self.tour.toggle, "dark", padx=9, pady=4)

    def _build_legend_bar(self) -> None:
        """Leyenda superior dinámica: cabecera del modo + 5 bandas con conteo (cambia con el modo de mapa)."""
        lbar = tk.Frame(self, bg=theme.PAPER_SUBTLE, pady=4, padx=10); lbar.pack(side=tk.TOP, fill=tk.X)
        self._legend_header = tk.Label(lbar, text="Escala oficial", bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY, font=self.fonts["mono_bold"])
        self._legend_header.pack(side=tk.LEFT, padx=(0, 12))
        self._legend_labels: List[Tuple[str, tk.Label]] = []
        self._legend_swatches: List[tk.Frame] = []
        for rng, hex_c, _ in theme.COLOR_SCALE_LEGEND:
            sw = tk.Frame(lbar, bg=hex_c, width=11, height=11, highlightbackground=theme.INK_PRIMARY, highlightthickness=1)
            sw.pack(side=tk.LEFT, padx=(0, 4)); self._legend_swatches.append(sw)
            lbl = tk.Label(lbar, text=f"{rng}: 0", bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY, font=self.fonts["mono"])
            lbl.pack(side=tk.LEFT, padx=(0, 12)); self._legend_labels.append((rng, lbl))
        self._btn(lbar, "Centrar vista", lambda: self.network_canvas.reset_view(), padx=7, pady=2).pack(side=tk.RIGHT)

    def _build_kpi_header(self, parent: tk.Frame) -> None:
        """Cabecera KPI: píldora de contexto (reloj/modo), entrada, checkboxes de etiquetas y 4 tarjetas por modo."""
        head = tk.Frame(parent, bg=theme.DOCK_BG, highlightthickness=1, highlightbackground=theme.DOCK_BORDER)
        head.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 0))
        top = tk.Frame(head, bg=theme.PAPER_BG); top.pack(fill=tk.X)
        self._show_util_var, self._show_ids_var = tk.BooleanVar(value=True), tk.BooleanVar(value=True)
        opts = tk.Frame(top, bg=theme.PAPER_BG); opts.pack(side=tk.RIGHT, padx=8)
        for text, var in (("% Util.", self._show_util_var), ("IDs", self._show_ids_var)):
            tk.Checkbutton(opts, text=text, variable=var, command=lambda: self.network_canvas.set_label_options(self._show_ids_var.get(), self._show_util_var.get()),
                           bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, activebackground=theme.PAPER_BG, activeforeground=theme.ACCENT_TEXT_ON_LIGHT,
                           selectcolor=theme.PAPER_BG, font=(self.fonts["small"][0], 8, "bold"), cursor="hand2").pack(side=tk.RIGHT, padx=(4, 0))
        pill = tk.Frame(top, bg=theme.SHELL_BG); pill.pack(side=tk.LEFT, padx=8, pady=6)
        self._lbl_clock = tk.Label(pill, text="t = 0.0 min  ·  Escenario: -", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, font=self.fonts["mono_bold"], anchor="w", padx=9, pady=3)
        self._lbl_clock.pack(side=tk.LEFT)
        self._lbl_inflow = tk.Label(top, text="Entrada: -", bg=theme.PAPER_BG, fg=theme.INK_MUTED, font=self.fonts["mono"], anchor="w")
        self._lbl_inflow.pack(side=tk.LEFT, padx=(2, 8))
        tk.Frame(head, bg=theme.DOCK_BORDER, height=1).pack(fill=tk.X)
        row = tk.Frame(head, bg=theme.DOCK_BG); row.pack(fill=tk.X)
        self._kpi_keys = ("max_util", "critical", "overloaded", "ptar")
        self._kpi_cards: Dict[str, tk.Label] = {}; self._kpi_captions: Dict[str, tk.Label] = {}
        for idx, (key, cap) in enumerate(zip(self._kpi_keys, theme.MAP_MODE_KPI_CAPTIONS["instant"])):
            cell = tk.Frame(row, bg=theme.PAPER_BG); cell.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 1, 0))
            row.columnconfigure(idx, weight=1, uniform="kpi")
            tk.Frame(cell, bg=theme.ACCENT_PRIMARY, height=2).pack(fill=tk.X)
            cap_lbl = tk.Label(cell, text=cap, bg=theme.PAPER_BG, fg=theme.INK_MUTED, font=(self.fonts["small"][0], 7, "bold"), anchor="w", padx=8)
            cap_lbl.pack(anchor="w", pady=(4, 0))
            val = tk.Label(cell, text="-", bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=(self.fonts["mono"][0], 10, "bold"), anchor="w", padx=8)
            val.pack(anchor="w", pady=(0, 5))
            self._kpi_captions[key], self._kpi_cards[key] = cap_lbl, val

    def _build_map_mode_bar(self, parent: tk.Frame) -> None:
        """Selector segmentado de lectura cartográfica (Instantáneo O(t) / Pico Máximo / Minutos en Sobrecarga)."""
        bar = tk.Frame(parent, bg=theme.DOCK_BG, highlightthickness=1, highlightbackground=theme.DOCK_BORDER)
        bar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(6, 0))
        self._lbl_map_mode = tk.Label(bar, text="Lectura cartográfica:", bg=theme.DOCK_BG, fg=theme.INK_PRIMARY, font=(self.fonts["small"][0], 8, "bold"), padx=8, pady=4)
        self._lbl_map_mode.pack(side=tk.LEFT)
        self._seg_wrap = tk.Frame(bar, bg=theme.DOCK_BORDER); self._seg_wrap.pack(side=tk.LEFT, padx=(4, 8), pady=3)
        for mode_id, (full, _mid, _short) in theme.MAP_MODES:
            btn = tk.Button(self._seg_wrap, text=full, command=lambda m=mode_id: self._set_map_mode(m), relief="flat", bd=0, padx=9, pady=2,
                            activebackground=theme.ACCENT_HOVER, activeforeground=theme.ACCENT_INK, cursor="hand2", highlightthickness=0,
                            font=(self.fonts["small"][0], 8, "normal"))
            btn.pack(side=tk.LEFT, padx=1, pady=1); self._map_mode_buttons[mode_id] = btn
        self._apply_map_mode_button_styles()
        bar.bind("<Configure>", self._on_map_bar_configure)

    def _on_map_bar_configure(self, event: tk.Event) -> None:
        """Textos del segmentado según el ancho disponible (completo / medio / corto)."""
        tier = "full" if event.width >= 660 else ("mid" if event.width >= 480 else "short")
        if event.width <= 1 or tier == self._map_mode_tier:
            return
        self._map_mode_tier = tier
        if tier == "full":
            if not self._lbl_map_mode.winfo_ismapped(): self._lbl_map_mode.pack(side=tk.LEFT, before=self._seg_wrap)
        else:
            self._lbl_map_mode.pack_forget()
        idx, padx = {"full": (0, 9), "mid": (1, 8), "short": (2, 6)}[tier]
        for mid, labels in theme.MAP_MODES:
            self._map_mode_buttons[mid].configure(text=labels[idx], padx=padx)

    def _apply_map_mode_button_styles(self) -> None:
        for mid, btn in self._map_mode_buttons.items():
            on = mid == self._map_mode
            btn.configure(bg=theme.ACCENT_PRIMARY if on else theme.DOCK_BG, fg=theme.ACCENT_INK if on else theme.INK_PRIMARY,
                          font=(self.fonts["small"][0], 8, "bold" if on else "normal"))

    def _build_player(self, parent: tk.Frame) -> None:
        pbar = tk.Frame(parent, bg=theme.PAPER_SUBTLE, padx=8, pady=5); pbar.pack(side=tk.TOP, fill=tk.X)
        row1 = tk.Frame(pbar, bg=theme.PAPER_SUBTLE); row1.pack(fill=tk.X)
        self._btn_reset = self._btn(row1, " Inicio", self._reset_playback, padx=7, icon="reset_light")
        self._btn_step_back = self._btn(row1, " -1", self.step_backward, padx=7, icon="step_back_light")
        self._btn_play = self._btn(row1, " Reproducir", self.toggle_play, "primary", padx=9, icon="play_on_accent")
        self._btn_step_fwd = self._btn(row1, " +1", self.step_forward, padx=7, icon="step_fwd_light")
        for b, padx in ((self._btn_reset, (0, 3)), (self._btn_step_back, 2), (self._btn_play, 4), (self._btn_step_fwd, 2)):
            b.pack(side=tk.LEFT, padx=padx)
        for b in (self._btn_step_back, self._btn_step_fwd, self._btn_reset):
            self._set_btn_enabled(b, False)
        self._speed_var = tk.StringVar(value="2x")
        self._lbl_speed = tk.Label(row1, text="Velocidad", bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY, font=self.fonts["small"])
        self._lbl_speed.pack(side=tk.LEFT, padx=(10, 4))
        self._speed_combo = ttk.Combobox(row1, textvariable=self._speed_var, values=tuple(_SPEED_MS), state="readonly", width=4, font=self.fonts["mono"])
        self._speed_combo.pack(side=tk.LEFT)
        self._speed_combo.bind("<<ComboboxSelected>>", lambda _e: self._on_speed_change())
        self._mass_lbl = tk.Label(row1, text="Balance masa: -", bg=theme.ACCENT_SOFT, fg=theme.OK_TEXT, highlightthickness=1,
                                  highlightbackground=theme.DOCK_BORDER, padx=8, pady=2, font=self.fonts["mono_bold"])
        self._mass_lbl.pack(side=tk.RIGHT, padx=2)
        row2 = tk.Frame(pbar, bg=theme.PAPER_SUBTLE); row2.pack(fill=tk.X, pady=(4, 0))
        self._time_lbl = tk.Label(row2, text="t = 0.0 / 90.0 min", bg=theme.PAPER_SUBTLE, fg=theme.INK_PRIMARY, font=self.fonts["mono_bold"])
        self._time_lbl.pack(side=tk.RIGHT, padx=(8, 0))
        self._scale_min_lbl = tk.Label(row2, text="0m", bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED, font=self.fonts["mono"])
        self._scale_min_lbl.pack(side=tk.LEFT, padx=(0, 4))
        self._scale = tk.Scale(
            row2, from_=0, to=0, resolution=1, orient=tk.HORIZONTAL, showvalue=False,
            sliderrelief="flat", sliderlength=18, troughcolor=theme.DOCK_BG,
            bg=theme.PAPER_SUBTLE, activebackground=theme.ACCENT_HOVER,
            highlightthickness=0, bd=0, state="disabled", command=self._on_slider_move,
        )
        self._scale.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._scale.bind("<ButtonPress-1>", self._on_slider_press)
        self._scale.bind("<ButtonRelease-1>", self._on_slider_release)
        self._scale_max_lbl = tk.Label(row2, text="90m", bg=theme.PAPER_SUBTLE, fg=theme.INK_MUTED, font=self.fonts["mono"])
        self._scale_max_lbl.pack(side=tk.LEFT, padx=(4, 0))
        self._play_btn_sig: Optional[tuple] = None
        pbar.bind("<Configure>", self._on_player_configure)

    def _on_speed_change(self) -> None:
        self.play_speed_ms = _SPEED_MS.get(self._speed_var.get(), _SPEED_MS["2x"])
        if self.is_playing: self.network_canvas.set_playing(True, self._pulse_factor())

    def _pulse_factor(self) -> float:
        """Factor de velocidad de los pulsos de flujo según la velocidad del reproductor (1x = 1.0)."""
        return _BASE_SPEED_MS / max(1, self.play_speed_ms)

    def _on_player_configure(self, event: tk.Event) -> None:
        compact = event.width < 600
        if event.width <= 1 or compact == self._player_compact:
            return
        self._player_compact = compact
        for b, txt in ((self._btn_reset, " Inicio"), (self._btn_step_back, " -1"), (self._btn_step_fwd, " +1")):
            b.configure(text="" if compact else txt)
        if compact:
            self._lbl_speed.pack_forget()
        elif not self._lbl_speed.winfo_ismapped():
            self._lbl_speed.pack(side=tk.LEFT, padx=(10, 4), before=self._speed_combo)
        self._play_btn_sig = None
        self._update_play_button()
        self._update_mass_label()
        self._update_clock_label()

    def _update_play_button(self) -> None:
        """Rotula el botón principal (Reproducir / Pausar / Reanudar) y su icono; solo reconfigura si cambió."""
        last = bool(self.result and self.result.snapshots) and self.current_step >= len(self.result.snapshots) - 1
        word = "Pausar" if self.is_playing else ("Reanudar" if 0 < self.current_step and not last else "Reproducir")
        sig = (self.is_playing, word, bool(self._player_compact))
        if sig == self._play_btn_sig:
            return
        self._play_btn_sig = sig
        self._btn_play.configure(text="" if self._player_compact else f" {word}",
                                 image=self._icons["pause_on_accent" if self.is_playing else "play_on_accent"])

    def _update_mass_label(self, snap: Optional[TimeStepSnapshot] = None) -> None:
        snap = snap or self._current_snapshot()
        if snap is None:
            self._mass_lbl.configure(text="Balance masa: -", fg=theme.INK_MUTED)
            return
        err = snap.mass_balance_error_m3
        ok = abs(err) < theme.MASS_BALANCE_OK_M3
        if self._player_compact:
            text = f"Masa {'OK' if ok else 'ERROR'} · {err:.1e}"
        else:
            text = f"Balance masa {'OK' if ok else 'ERROR'} · Err {err:.2e} m³"
        self._mass_lbl.configure(text=text, fg=theme.OK_TEXT if ok else theme.ERROR_TEXT)

    # ── Atajos de teclado ────────────────────────────────────────────────────

    def _bind_shortcuts(self) -> None:
        self.bind("<space>", self._shortcut_play_pause)
        self.bind("<Left>", lambda e: self._shortcut_step(e, -1))
        self.bind("<Right>", lambda e: self._shortcut_step(e, 1))
        self.bind("<Home>", self._shortcut_home)
        self.bind("<Control-f>", self._shortcut_focus_search)
        self.bind("<Control-F>", self._shortcut_focus_search)
        self.bind("<Escape>", self._shortcut_escape)

    def _focus_class(self) -> str:
        try:
            w = self.focus_get()
        except (KeyError, tk.TclError):
            return ""
        return w.winfo_class() if w is not None else ""

    def _is_typing_widget(self) -> bool:
        """True si el foco está en un campo de texto/numérico (los atajos no deben dispararse)."""
        return self._focus_class() in _TYPING_CLASSES

    def _shortcut_play_pause(self, _event: object = None) -> Optional[str]:
        if self._is_typing_widget() or self._focus_class() in _BUTTON_CLASSES:
            return None
        self.toggle_play()
        return "break"

    def _shortcut_step(self, _event: object, delta: int) -> Optional[str]:
        if self._is_typing_widget():
            return None
        (self.step_forward if delta > 0 else self.step_backward)()
        return "break"

    def _shortcut_home(self, _event: object = None) -> Optional[str]:
        if self._is_typing_widget():
            return None
        self._reset_playback()
        return "break"

    def _shortcut_focus_search(self, _event: object = None) -> str:
        if not self._show_left:
            self.toggle_left_panel()
        self.controls.focus_search()
        return "break"

    def _shortcut_escape(self, _event: object = None) -> Optional[str]:
        if self.tour.active:  # Esc cierra primero el recorrido guiado
            self.tour.close()
            return "break"
        self.clear_traversal()
        self._clear_basin()
        self.select_entity(None, None)

    # ── Layout responsivo ────────────────────────────────────────────────────

    def _on_window_configure(self, event: tk.Event) -> None:
        if event.widget is not self or self._closing:
            return
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(70, lambda: self._apply_responsive_layout(self.winfo_width(), self.winfo_height()))

    def _apply_responsive_layout(self, width: int, height: int) -> None:
        """Adapta topbar, paneles laterales y pista de atajos al ancho de ventana."""
        self._resize_after_id = None
        if width < 200 or height < 200:
            return
        tier = "wide" if width >= theme.BREAKPOINT_MEDIUM else ("medium" if width >= theme.BREAKPOINT_COMPACT else "compact")
        tier_changed, self._layout_tier = tier != self._layout_tier, tier
        sig = (tier, width >= theme.BREAKPOINT_FULL_ACTIONS)
        if sig != self._topbar_sig:
            self._topbar_sig = sig
            self._layout_topbar(*sig)
        if width >= theme.BREAKPOINT_HINT:
            if not self.lbl_shortcuts_hint.winfo_manager():
                self.lbl_shortcuts_hint.pack(side=tk.RIGHT, padx=12, pady=3)
        else:
            self.lbl_shortcuts_hint.pack_forget()
        if tier_changed:
            if tier == "compact" and self._show_left and self._show_right:
                self._show_right = False
            self._sync_panes()
            self._update_toggle_styles()

    def _layout_topbar(self, tier: str, full_actions: bool) -> None:
        for child in self.actions_bar.pack_slaves():
            child.pack_forget()
        wide = tier == "wide"
        self.btn_guided_tour.configure(text=self.tour.button_label(tier))
        self.btn_guided_tour.pack(side=tk.RIGHT, padx=(4, 0))
        if wide:
            if not self.lbl_app_subtitle.winfo_manager():
                self.lbl_app_subtitle.pack(anchor="w")
            self.lbl_app_title.configure(text="Simulador de Alcantarillado — Ciudad Bicentenario")
        else:
            self.lbl_app_subtitle.pack_forget()
            self.lbl_app_title.configure(text="Ciudad Bicentenario")
        if wide:
            self.btn_export_docx.pack(side=tk.RIGHT, padx=(4, 0))
            self.btn_export_md.pack(side=tk.RIGHT, padx=4)
        if full_actions:
            for b in (self.btn_assumptions, self.btn_export_csv, self.btn_load_csv, self.btn_load_excel):
                b.pack(side=tk.RIGHT, padx=4)
        else:
            self.menu_btn_file.configure(text="Archivo y Modelo " if wide or tier == "medium" else "Archivo ")
            self.menu_btn_file.pack(side=tk.RIGHT, padx=4)

    def _sync_panes(self) -> None:
        for pane in list(self.paned.panes()):
            self.paned.forget(pane)
        wide = (self._layout_tier or "wide") == "wide"
        if self._show_left:
            self.paned.add(self.controls, width=290 if wide else 264, minsize=272 if wide else 264, stretch="never")
        self.paned.add(self._center, minsize=420 if wide else 310, stretch="always")
        if self._show_right:
            self.paned.add(self.notebook, width=430 if wide else 330, minsize=340 if wide else 285, stretch="never")

    def _update_toggle_styles(self) -> None:
        for btn, shown, name in ((self.btn_toggle_left, self._show_left, "sliders"), (self.btn_toggle_right, self._show_right, "chart")):
            self._restyle_btn(btn, "dark_primary" if shown else "dark")
            btn.configure(image=self._icons[f"{name}_ink" if shown else f"{name}_light"])

    def toggle_left_panel(self) -> None:
        self._show_left = not self._show_left
        if self._show_left and self._layout_tier == "compact":
            self._show_right = False
        self._sync_panes()
        self._update_toggle_styles()

    def toggle_right_panel(self) -> None:
        self._show_right = not self._show_right
        if self._show_right and self._layout_tier == "compact":
            self._show_left = False
        self._sync_panes()
        self._update_toggle_styles()

    # ── Carga, simulación y reproducción (RF01–RF09) ─────────────────────────

    def _active_tab(self) -> int:
        try: return int(self.notebook.index(self.notebook.select()))
        except tk.TclError: return 0
    def _current_snapshot(self) -> Optional[TimeStepSnapshot]:
        return self.result.snapshots[min(max(self.current_step, 0), len(self.result.snapshots) - 1)] if (self.result and self.result.snapshots) else None
    def _cancel_timer(self, attr: str) -> None:
        if (aid := getattr(self, attr, None)) is not None:
            try: self.after_cancel(aid)
            except tk.TclError: pass
            setattr(self, attr, None)

    def load_data(self, path: str, run_initial: bool = True) -> bool:
        try: ds = load_dataset(path)
        except (DataLoadError, OSError, ValueError) as exc:
            messagebox.showerror("Error al cargar datos", str(exc), parent=self)
            self._status_lbl.configure(text="Error de carga — se conserva dataset previo"); return False
        self._stop_playback(); self.clear_traversal(); self.tour.close(reset_view=False)
        self.dataset, self.cached_comparisons, self._base_compare_key = ds, None, None
        self.interventions.clear(); self.previous_result = self._baseline_result = None
        self.isolated_nodes, self.isolated_pipes, self._canvas_int_sig = set(), set(), None
        self.basin_focus_active, self._inspector_trace, self._attr_key = False, None, None
        self.selected_kind = self.selected_id = self._last_chart_pipe = self._last_chart_node = None
        self.comparison_panel.set_comparisons(None, is_visible=self._active_tab() == 3)
        self.controls.populate_dataset(ds)
        if any(s.scenario_id == 3 for s in ds.scenarios): self.controls.select_scenario_by_id(3)
        self.network_canvas.set_graph(ds.graph)  # también limpia intervenciones y foco de cuenca del lienzo
        self._sync_inspector_context()
        self._status_lbl.configure(text=f"Dataset cargado: {os.path.basename(ds.source_path)}")
        if run_initial: self.run_simulation()
        return True

    def _build_config(self) -> SimulationConfig:
        """Configuración del panel de controles más las intervenciones vigentes (ValueError si es inválida)."""
        cfg = self.controls.get_simulation_config()
        cfg.interventions = dict(self.interventions)
        return cfg

    def _invalidate_comparisons(self) -> None:
        self.cached_comparisons = None; self.comparison_panel.invalidate()

    def run_simulation(self, auto_play: bool = False, preserve_previous: bool = False) -> Optional[SimulationResult]:
        """Simula con la configuración vigente. La línea base (sin intervenciones) se conserva entre
        intervenciones sucesivas y se descarta al restaurar la red (`preserve_previous` es solo una pista)."""
        if self.dataset is None: return None
        self._stop_playback()
        prev_sid = self.result.config.scenario_id if self.result is not None else None
        try: cfg = self._build_config()
        except ValueError as exc: messagebox.showerror("Parámetros inválidos", str(exc), parent=self); return None
        key = _base_key(cfg)
        if self._base_compare_key is not None and key != self._base_compare_key:
            self._invalidate_comparisons()
        self._base_compare_key = key
        engine = SewerSimulationEngine(self.dataset.graph, self.dataset.basin)
        base_cfg = replace(cfg, interventions={})
        if self.interventions:
            if self._baseline_result is not None and replace(self._baseline_result.config, interventions={}) == base_cfg:
                pass
            elif self.result is not None and not self.result.config.interventions and replace(self.result.config, interventions={}) == base_cfg:
                self._baseline_result = self.result
            else:
                self._baseline_result = engine.run(base_cfg)
            self.previous_result = self._baseline_result
        else:
            self.previous_result = None
        res = engine.run(cfg)
        if not self.interventions: self._baseline_result = res
        self.result, self.current_step, self._attr_key = res, 0, None
        if auto_play and self._map_mode != "instant":
            self._map_mode = "instant"; self._apply_map_mode_button_styles()
        peak, ov, dur = self._global_stress_maps()
        self.network_canvas.set_stress_maps(peak, ov, dur)
        self._sync_isolation()
        snaps = res.snapshots
        self._scale.configure(state=("normal" if len(snaps) > 1 else "disabled"), from_=0, to=max(0, len(snaps) - 1))
        self._scale_min_lbl.configure(text="0m")
        self._scale_max_lbl.configure(text=f"{snaps[-1].time_min:g}m" if snaps else "0m")
        self._sync_slider_programmatic(0)
        self._play_btn_sig = None
        self._push_chart_result()
        if self.network_canvas.map_mode != self._map_mode: self.network_canvas.set_map_mode(self._map_mode)
        self.go_to_step(0)
        self._sync_inspector_context()
        self._status_lbl.configure(text=f"Esc. {cfg.scenario_id} ({theme.translate_scenario_name(cfg.scenario_name)}) en {res.execution_time_ms:.1f} ms")
        self.tour.update_button()
        self.tour.on_result(auto_play, prev_sid)
        if auto_play and len(res.snapshots) > 1:
            self.toggle_play()
        return res

    def _push_chart_result(self) -> None:
        """Entrega a Evolución resultado, línea base (Antes/Después), grafo, foco por selección y ruta activa."""
        self._last_chart_pipe = self.selected_id if self.selected_kind == "pipe" else None
        self._last_chart_node = self.selected_id if self.selected_kind == "node" else None
        self.charts_panel.set_route(self._active_route or None)
        self.charts_panel.set_result(self.result, self._last_chart_pipe, is_visible=self._active_tab() == 2,
                                     previous_result=self.previous_result, graph=self.dataset.graph if self.dataset else None,
                                     focus_node_id=self._last_chart_node)

    def go_to_step(self, idx: int, from_slider: bool = False) -> None:
        if not self.result or not self.result.snapshots or self.dataset is None: return
        snaps = self.result.snapshots
        self.current_step = max(0, min(int(idx), len(snaps) - 1))
        snap = snaps[self.current_step]
        if not from_slider and not self._slider_dragging:
            self._sync_slider_programmatic(self.current_step)
        self._set_btn_enabled(self._btn_step_back, self.current_step > 0)
        self._set_btn_enabled(self._btn_step_fwd, self.current_step < len(snaps) - 1)
        self._set_btn_enabled(self._btn_reset, self.current_step > 0 or self.is_playing)
        self._time_lbl.configure(text=f"t = {snap.time_min:.1f} / {snaps[-1].time_min:.1f} min")
        self._update_mass_label(snap)
        self._update_play_button()
        self.network_canvas.set_snapshot(snap if self._map_mode == "instant" else snaps[-1])
        tab = self._active_tab()
        self._update_inspector_view(snap)
        self._refresh_source_composition()
        self.critical_tab.update_view(self.dataset.graph, snap, is_visible=tab == 1)
        if tab == 1 and self.selected_kind == "pipe": self.critical_tab.select_pipe(self.selected_id)
        self.charts_panel.update_cursor(snap.time_min, is_visible=tab == 2, step_index=self.current_step)
        self._update_header(snap)

    # ── Modos de mapa (G11), cabecera KPI (G10) y leyenda dinámica (G7) ─────────

    def _global_stress_maps(self) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """(pico de utilización, minutos en sobrecarga, duración total) globales de la simulación vigente."""
        if self.result is None or not self.result.snapshots: return {}, {}, 90.0
        dur = max(1.0, float(self.result.snapshots[-1].time_min), float(self.result.config.duration_min))
        return self.result.peak_pipe_utilization, self.result.pipe_overloaded_minutes, dur

    def _set_text(self, w: tk.Label, text: str, fg: Optional[str] = None) -> None:
        """`configure` solo si cambió el texto/color (actualización por paso barata)."""
        key = (text, fg)
        if self._txt_cache.get(w) != key:
            self._txt_cache[w] = key
            w.configure(text=text) if fg is None else w.configure(text=text, fg=fg)

    def _set_map_mode(self, mode: str) -> None:
        """Cambia la lectura del mapa. Pico/Sobrecarga son vistas globales congeladas: pausan y conservan `current_step`."""
        if mode not in _MAP_MODE_IDS: return
        if mode != "instant": self._stop_playback(True); self.tour.close(reset_view=False)
        self._map_mode = mode
        self._apply_map_mode_button_styles()
        snap = self._current_snapshot()
        if snap is None:
            self.network_canvas.set_map_mode(mode); return
        peak, ov, dur = self._global_stress_maps()
        self.network_canvas.set_snapshot(snap if mode == "instant" else self.result.snapshots[-1])
        self.network_canvas.set_map_mode(mode, peak_util=peak, overload_minutes=ov, total_duration_min=dur)
        self._update_header(snap)

    def _ensure_instant(self) -> None:
        """Vuelve al modo Instantáneo (restaura el paso conservado) antes de navegar en el tiempo."""
        if self._map_mode != "instant": self._set_map_mode("instant")

    def _update_clock_label(self, snap: Optional[TimeStepSnapshot] = None) -> None:
        snap = snap or self._current_snapshot()
        if snap is None or self.result is None: return
        cfg, compact = self.result.config, bool(self._player_compact)
        scen = theme.translate_scenario_name(cfg.scenario_name, short=compact)
        dur = self._global_stress_maps()[2]
        if self._map_mode == "peak":
            txt = f"Pico 0–{dur:.0f}m · {scen}" if compact else f"Pico máximo · 0–{dur:.0f} min  ·  {scen} ({cfg.intensity_mm_h:.0f} mm/h)"
        elif self._map_mode == "overload_minutes":
            txt = f"Sobrecarga 0–{dur:.0f}m · {scen}" if compact else f"Sobrecarga acumulada · 0–{dur:.0f} min  ·  {scen} ({cfg.intensity_mm_h:.0f} mm/h)"
        elif compact:
            txt = f"t={snap.time_min:.0f}/{cfg.duration_min:.0f}m · {scen} ({snap.rain_intensity_mm_h:.0f} mm/h)"
        else:
            txt = f"t = {snap.time_min:.1f} / {cfg.duration_min:.0f} min  ·  {scen} ({snap.rain_intensity_mm_h:.0f} mm/h)"
        self._set_text(self._lbl_clock, txt)

    def _update_header(self, snap: Optional[TimeStepSnapshot] = None) -> None:
        """Píldora de contexto, entrada, 4 tarjetas KPI y leyenda según el modo de mapa (solo `configure` de labels)."""
        snap = snap or self._current_snapshot()
        if snap is None or self.result is None: return
        res, mode = self.result, self._map_mode
        peak, ov, dur = self._global_stress_maps()
        pids = snap.pipe_states
        ink, err, tier_txt = theme.INK_PRIMARY, theme.STATUS_ERR_LIGHT, theme.TIER_TEXT_ON_LIGHT
        counts = [0] * 5
        if mode == "overload_minutes":
            levels = OVERLOAD_PERSISTENCE_LEVELS
            for pid in pids: counts[classify_overload_persistence(ov.get(pid, 0.0), dur)[0]] += 1
            max_ov = max((ov.get(pid, 0.0) for pid in pids), default=0.0)
            any_ov = sum(1 for pid in pids if ov.get(pid, 0.0) >= 0.5)
            vals = [(f"{max_ov:.0f} / {dur:.0f}m", tier_txt[levels[classify_overload_persistence(max_ov, dur)[0]][1]]),
                    (str(any_ov), err if any_ov else ink), (str(counts[4]), tier_txt["#991b1b"] if counts[4] else ink),
                    (f"{res.total_sink_discharge_m3:.1f} m³", theme.ACCENT_TEXT_ON_LIGHT)]
            header, inflow = f"Sobrecarga acumulada · 0–{dur:.0f} min", f"Entrada total: {res.total_inflow_m3:.1f} m³"
        elif mode == "peak":
            levels = [(r, c, d) for r, c, d in theme.COLOR_SCALE_LEGEND]
            for pid in pids: counts[classify_utilization(peak.get(pid, 0.0)).tier_index] += 1
            max_u = max((peak.get(pid, 0.0) for pid in pids), default=0.0)
            vals = [(f"{max_u:.1f}%", tier_txt[classify_utilization(max_u).color_hex]), (str(counts[3]), err if counts[3] else ink),
                    (str(counts[4]), tier_txt["#991b1b"] if counts[4] else ink), (f"{res.peak_sink_discharge_m3s:.4f} m³/s", theme.ACCENT_TEXT_ON_LIGHT)]
            header = f"Pico máximo · 0–{dur:.0f} min"
            inflow = f"Entrada pico: {max(s.total_source_inflow_m3s for s in res.snapshots):.4f} m³/s"
        else:
            levels = theme.COLOR_SCALE_LEGEND
            max_u = 0.0
            for ps in pids.values():
                counts[ps.category.tier_index] += 1
                if ps.utilization_pct > max_u: max_u = ps.utilization_pct
            n_near, n_over = len(snap.near_capacity_pipe_ids), len(snap.overloaded_pipe_ids)
            vals = [(f"{max_u:.1f}%", tier_txt[classify_utilization(max_u).color_hex]), (str(n_near), err if n_near else ink),
                    (str(n_over), tier_txt["#991b1b"] if n_over else ink), (f"{snap.total_sink_discharge_m3s:.4f} m³/s", theme.ACCENT_TEXT_ON_LIGHT)]
            header, inflow = f"Escala oficial · t = {snap.time_min:.0f} min", f"Entrada: {snap.total_source_inflow_m3s:.4f} m³/s"
        for key, cap, (txt, fg) in zip(self._kpi_keys, theme.MAP_MODE_KPI_CAPTIONS[mode], vals):
            self._set_text(self._kpi_captions[key], cap); self._set_text(self._kpi_cards[key], txt, fg)
        self._set_text(self._lbl_inflow, inflow)
        self._set_text(self._legend_header, header)
        for (_old, lbl), sw, (rng, col, _d), cnt in zip(self._legend_labels, self._legend_swatches, levels, counts):
            self._set_text(lbl, f"{rng}: {cnt}")
            if self._txt_cache.get(sw) != col: self._txt_cache[sw] = col; sw.configure(bg=col)
        self._update_clock_label(snap)

    def _sync_slider_programmatic(self, step: int) -> None:
        self._updating_slider = True
        self._scale.configure(command="")
        self._scale.set(step)
        if not self._slider_restore_pending:
            self._slider_restore_pending = True
            self.after_idle(self._restore_slider_command)

    def _restore_slider_command(self) -> None:
        self._slider_restore_pending = False
        self._updating_slider = False
        try:
            self._scale.configure(command=self._on_slider_move)
        except tk.TclError:
            pass

    def _on_slider_press(self, e: tk.Event) -> Optional[str]:
        if str(self._scale.cget("state")) == "disabled" or not self.result or not self.result.snapshots:
            return None
        self._slider_dragging = True
        self._stop_playback(True); self._ensure_instant()
        if self._scale.identify(e.x, e.y) in ("trough1", "trough2"):
            w = max(1, self._scale.winfo_width())
            snaps = self.result.snapshots
            target = max(0, min(int(round((e.x / w) * (len(snaps) - 1))), len(snaps) - 1))
            self._sync_slider_programmatic(target)
            self.go_to_step(target, from_slider=True)
            return "break"
        return None

    def _on_slider_release(self, _e: tk.Event) -> None:
        self._slider_dragging = False
        self._cancel_timer("_slider_after_id")
        self._pending_slider_step = None
        if not self.result or not self.result.snapshots:
            return
        idx = int(round(float(self._scale.get())))
        if idx != self.current_step:
            self.go_to_step(idx, from_slider=True)

    def _on_slider_move(self, value: str) -> None:
        if self._updating_slider or not self.result or not self.result.snapshots:
            return
        idx = int(round(float(value)))
        if idx == self.current_step and self._map_mode == "instant":
            return
        self._stop_playback(True); self._ensure_instant()
        if self._slider_dragging:
            self._pending_slider_step = idx
            if self._slider_after_id is None:
                self._slider_after_id = self.after(16, self._flush_slider_step)
        else:
            self.go_to_step(idx, from_slider=True)

    def _flush_slider_step(self) -> None:
        self._slider_after_id = None
        if self._pending_slider_step is not None:
            step = self._pending_slider_step
            self._pending_slider_step = None
            self.go_to_step(step, from_slider=True)
    def step_forward(self) -> None: self._stop_playback(True); self._ensure_instant(); self.go_to_step(self.current_step + 1)
    def step_backward(self) -> None: self._stop_playback(True); self._ensure_instant(); self.go_to_step(self.current_step - 1)
    def _reset_playback(self) -> None: self._stop_playback(False); self._ensure_instant(); self.go_to_step(0)
    def _stop_playback(self, resume: bool = False) -> None:
        self.is_playing = False; self._cancel_timer("_play_after_id")
        if hasattr(self, "network_canvas"): self.network_canvas.set_playing(False)
        if hasattr(self, "_btn_play"): self._update_play_button()
        if hasattr(self, "inspector_tab") and not self._closing: self._refresh_source_composition()
    def toggle_play(self) -> None:
        if not self.result or not self.result.snapshots: return
        if self.is_playing: self._stop_playback(True); return
        self.tour.close()  # reproducir cierra el recorrido guiado
        self._ensure_instant()
        if self.current_step >= len(self.result.snapshots) - 1: self.go_to_step(0)
        self.is_playing = True; self._update_play_button()
        self.network_canvas.set_playing(True, self._pulse_factor())
        self._play_after_id = self.after(self.play_speed_ms, self._play_tick)
    def _play_tick(self) -> None:
        self._play_after_id = None
        if not self.is_playing or not self.result: return
        if self.current_step + 1 < len(self.result.snapshots):
            self.go_to_step(self.current_step + 1); self._play_after_id = self.after(self.play_speed_ms, self._play_tick)
        else: self._stop_playback(False)

    # ── Selección, búsqueda O(1), recorridos BFS/DFS y animación ─────────────

    def select_entity(self, kind: Optional[str], entity_id: Optional[str]) -> None:
        new_sel = (kind, entity_id) if kind in ("pipe", "node") and entity_id else (None, None)
        if new_sel == (self.selected_kind, self.selected_id):
            return
        if self._inspector_trace is not None and self._inspector_trace[0] != new_sel[1]:
            self._inspector_trace = None
        self.selected_kind, self.selected_id = new_sel
        self.network_canvas.set_selected(self.selected_kind, self.selected_id)
        if self.basin_focus_active: self._apply_basin()
        self._sync_inspector_context()
        self._update_inspector_view()
        self._refresh_source_composition(force=True)
        pipe_id = self.selected_id if self.selected_kind == "pipe" else None
        self.critical_tab.select_pipe(pipe_id)
        node_id = self.selected_id if self.selected_kind == "node" else None
        if pipe_id != self._last_chart_pipe or node_id != self._last_chart_node: self._push_chart_result()

    def _action_search(self, query: str) -> None:
        """Búsqueda: ID exacto O(1) y, si no coincide, respaldo por subcadena; centra la cámara en el resultado."""
        if self.dataset is None: return
        g = self.dataset.graph
        kind, eid = search_entity(g, query)
        n_hits = 1
        if not kind or not eid:
            nodes, pipes = search_entities(g, query)
            if nodes: kind, eid = "node", nodes[0].node_id
            elif pipes: kind, eid = "pipe", pipes[0].pipe_id
            n_hits = len(nodes) + len(pipes)
        if not kind or not eid:
            sample_n = ", ".join(sorted(g.node_ids())[:2]) or "—"
            sample_p = ", ".join(sorted(g.pipe_ids())[:2]) or "—"
            self.controls.show_search_feedback(f"No existe «{query}» en la red. Ej: nodos {sample_n} o tuberías {sample_p}.", is_error=True)
            self._status_lbl.configure(text=f"No encontrado: «{query}»", fg="#FCA5A5")
            messagebox.showwarning(
                "Elemento no encontrado",
                f"No se encontró ningún nodo ni tubería con el identificador «{query}».\n\nEjemplos válidos: nodos ({sample_n}) o tuberías ({sample_p}).",
                parent=self,
            )
            return
        what = f"{'Tubería' if kind == 'pipe' else 'Nodo'} {eid}"
        if n_hits > 1:
            self.controls.show_search_feedback(f"{n_hits} coincidencias para «{query}». Seleccionado: {what}.", is_error=False)
            self._status_lbl.configure(text=f"Búsqueda «{query}»: {n_hits} coincidencias · {what}", fg=theme.SHELL_TEXT_MUTED)
        else:
            self.controls.show_search_feedback(f"Encontrado: {what}", is_error=False)
            self._status_lbl.configure(text=f"Encontrado O(1): {what}", fg=theme.SHELL_TEXT_MUTED)
        self.select_entity(kind, eid); self.notebook.select(0)
        (self.network_canvas.focus_pipe if kind == "pipe" else self.network_canvas.focus_node)(eid)

    # ── Inspector: acciones, cuenca aislada, intervenciones y composición por fuente ──

    def _selected_edge(self):
        return self.dataset.graph.get_pipe(self.selected_id) if (self.dataset and self.selected_kind == "pipe") else None

    def _update_inspector_view(self, snap: Optional[TimeStepSnapshot] = None) -> None:
        self.inspector_tab.update_view(
            self.dataset.graph if self.dataset else None, snap or self._current_snapshot(), self.result, self.selected_kind,
            self.selected_id, self.interventions, self.isolated_nodes, self.isolated_pipes, self.dataset.basin if self.dataset else None,
        )

    def _sync_inspector_context(self) -> None:
        edge = self._selected_edge()
        self.inspector_tab.set_context(
            self.selected_kind, edge, self.interventions.get(edge.pipe_id) if edge else None, len(self.interventions),
            self.basin_focus_active, self._inspector_trace[1] if self._inspector_trace else None,
        )

    def _action_focus_selected(self) -> None:
        if self.selected_kind == "pipe" and self.selected_id: self.network_canvas.focus_pipe(self.selected_id)
        elif self.selected_kind == "node" and self.selected_id: self.network_canvas.focus_node(self.selected_id)

    def _basin_sets(self) -> Optional[Tuple[set, set]]:
        """Nodos y tuberías de la cuenca de la selección: unión de aguas arriba y aguas abajo."""
        if self.dataset is None or not self.selected_id: return None
        g = self.dataset.graph
        if self.selected_kind == "pipe" and (e := g.get_pipe(self.selected_id)) is not None:
            starts, extra = (e.from_node, e.to_node), {e.pipe_id}
        elif self.selected_kind == "node" and g.has_node(self.selected_id):
            starts, extra = (self.selected_id, self.selected_id), set()
        else:
            return None
        up_n, up_p = trace_upstream(g, starts[0])
        dn = trace_downstream(g, starts[1])
        return set(up_n) | set(dn.visited_order), {p.pipe_id for p in up_p} | {p.pipe_id for p in dn.traversed_edges} | extra

    def _apply_basin(self) -> None:
        sets = self._basin_sets() if self.basin_focus_active else None
        if sets is None:
            self.basin_focus_active = False
            self.network_canvas.set_basin_focus(None, None)
            return
        self.network_canvas.set_basin_focus(*sets)
        self._status_lbl.configure(text=f"Cuenca aislada: {len(sets[0])} nodo(s) y {len(sets[1])} tramo(s) hacia/desde la selección.", fg=theme.SHELL_TEXT_MUTED)

    def _clear_basin(self) -> None:
        self.basin_focus_active = False
        self.network_canvas.set_basin_focus(None, None)
        self._sync_inspector_context()

    def _action_toggle_basin(self) -> None:
        if self.dataset is None or not self.selected_id: return
        self.basin_focus_active = not self.basin_focus_active
        self._apply_basin()
        self._sync_inspector_context()

    def _action_toggle_inspector_trace(self, direction: str) -> None:
        if self.dataset is None or self.selected_kind != "node" or not self.selected_id: return
        nid = self.selected_id
        if self._inspector_trace == (nid, direction):
            self.clear_traversal()
            self._status_lbl.configure(text="Vista de red restaurada.", fg=theme.SHELL_TEXT_MUTED)
        else:
            self.controls.set_start_node(nid)
            self._action_trace(nid, direction == "up")
            self._inspector_trace = (nid, direction)
        self._sync_inspector_context()

    def _sync_isolation(self) -> None:
        """Recalcula nodos/tramos incomunicados de la PTAR por cierres totales y actualiza el lienzo si cambió algo."""
        if self.dataset is None: return
        blocked = {pid for pid, inv in self.interventions.items() if inv.is_closed}
        self.isolated_nodes, self.isolated_pipes = find_isolated_from_sinks(self.dataset.graph, blocked)
        sig = (tuple(sorted(self.interventions.items())), frozenset(self.isolated_nodes), frozenset(self.isolated_pipes))
        if sig != self._canvas_int_sig:
            self._canvas_int_sig = sig
            self.network_canvas.set_interventions(self.interventions, self.isolated_nodes, self.isolated_pipes)
            if self.basin_focus_active: self._apply_basin()

    def _after_intervention_change(self, status: str = "") -> None:
        self._invalidate_comparisons()
        self.run_simulation(preserve_previous=True)
        self._sync_inspector_context()
        if status: self._status_lbl.configure(text=status, fg=theme.SHELL_TEXT_MUTED)
        elif self.isolated_nodes and self.interventions:
            self._status_lbl.configure(text=f"Intervención: {len(self.isolated_nodes)} nodo(s) aislados de la PTAR 31.", fg=theme.SHELL_TEXT_MUTED)

    def _action_apply_intervention(self, obstruction_pct: float, diameter_in: Optional[float]) -> None:
        edge = self._selected_edge()
        if edge is None: return
        try:
            inv = PipeIntervention(edge.pipe_id, float(obstruction_pct), diameter_in)
        except ValueError as exc:
            self.inspector_tab.show_intervention_error(str(exc)); return
        if not inv.has_obstruction and inv.diameter_in_override is None: self.interventions.pop(edge.pipe_id, None)
        else: self.interventions[edge.pipe_id] = inv
        self._after_intervention_change()

    def _action_restore_pipe(self) -> None:
        if self.selected_id in self.interventions and self.selected_kind == "pipe":
            del self.interventions[self.selected_id]
            self._after_intervention_change(f"Tramo {self.selected_id} restaurado.")

    def _action_restore_all(self) -> None:
        if self.interventions:
            self.interventions.clear()
            self._after_intervention_change("Red restaurada: sin intervenciones.")

    def _refresh_source_composition(self, force: bool = False) -> None:
        """Composición por fuente de la entidad seleccionada en el paso actual (con throttle durante la reproducción)."""
        if self.dataset is None or not self.result or not self.selected_id or self.selected_kind not in ("pipe", "node"): return
        snap = self._current_snapshot()
        if snap is None: return
        now = time.perf_counter()
        if not force and self.is_playing and now - self._attr_time < _ATTR_THROTTLE_S: return
        cfg = self.result.config
        key = (id(snap), self.selected_kind, self.selected_id, tuple(sorted(self.interventions.items())), cfg.split_rule, cfg.source_distribution)
        if key == self._attr_key: return
        self._attr_key, self._attr_time = key, now
        qmax = {pid: ps.effective_q_max_m3s for pid, ps in snap.pipe_states.items() if ps.effective_q_max_m3s is not None}
        attr = compute_source_attribution(self.dataset.graph, snap, cfg.split_rule, qmax, cfg.source_distribution)
        if self.selected_kind == "pipe":
            shares, label = attr.pipe_shares.get(self.selected_id, []), f"Tramo {self.selected_id}"
        else:
            shares, label = attr.node_shares.get(self.selected_id, []), (f"PTAR {self.selected_id}" if self.selected_id in self.dataset.graph.sink_ids() else f"Pozo {self.selected_id}")
        self.inspector_tab.set_source_composition(label, shares, cfg.split_rule)

    def _on_tab_changed(self, _event: tk.Event) -> None:
        tab = self._active_tab()
        if tab == 1 and self.dataset is not None:
            self.critical_tab.mark_visible(self.dataset.graph, self._current_snapshot())
            if self.selected_kind == "pipe": self.critical_tab.select_pipe(self.selected_id)
        elif tab == 2: self.charts_panel.mark_visible()
        elif tab == 3: self.comparison_panel.mark_visible()

    def _stop_traversal(self) -> None:
        self.anim_playing = False; self._cancel_timer("_anim_after_id")
        if hasattr(self, "controls"): self.controls.set_traversal_playing(False)

    def _anim_delay(self) -> int:
        """Retardo por paso de la animación del recorrido: 560 ms en BFS y 340 ms en DFS."""
        f = self.traversal_frames[min(self.anim_idx, len(self.traversal_frames) - 1)] if self.traversal_frames else None
        return _ANIM_MS_BY_ALGO.get(f.algorithm if f else self._last_traversal_algo, _TRAVERSAL_ANIM_MS)

    @staticmethod
    def _log_traversal(res: TraversalResult, start_id: str, target_id: Optional[str]) -> str:
        """Texto de la bitácora de un recorrido BFS/DFS terminado (visita, ruta y resumen)."""
        order = res.visited_order
        lines = [f"[{res.algorithm}] {start_id} → {target_id or 'toda la red'}",
                 f"Visitados ({len(order)}): {' → '.join(order[:14])}" + (" ..." if len(order) > 14 else "")]
        if target_id:
            if res.target_reached:
                lines += [f"Ruta ({len(res.path_pipes)} tramos): {' → '.join(res.path_nodes)}",
                          f"Tuberías: {', '.join(p.pipe_id for p in res.path_pipes)}",
                          f"Tránsito acumulado: {sum(p.transit_time_min for p in res.path_pipes):.1f} min"]
            else:
                lines.append(f"Sin camino dirigido desde {start_id} hasta {target_id}.")
        return "\n".join(lines)

    def _action_traversal(self, algo: str, start_id: str, target_id: Optional[str], animate: bool) -> None:
        if self.dataset is None: return
        if not start_id or not self.dataset.graph.has_node(start_id):
            msg = f"Nodo de inicio «{start_id or '—'}» no encontrado en la red."
            self.controls.update_traversal_view(None, summary_text=msg, playing=False, has_frames=False)
            self._status_lbl.configure(text=msg, fg="#FCA5A5")
            messagebox.showwarning("Nodo no encontrado", msg, parent=self)
            return
        self._stop_traversal(); self._inspector_trace = None
        algo = algo.upper()
        res = (bfs if algo == "BFS" else dfs)(self.dataset.graph, start_id, target_id, record_frames=True)
        self._last_traversal_algo = algo
        self._traversal_mode = algo.lower()
        self._traversal_origin = start_id
        label = "BFS (Cola FIFO)" if algo == "BFS" else "DFS (Pila LIFO)"
        self._traversal_banner = f"{label} · Inicio {start_id} → Destino {target_id}" if target_id else f"{label} · Desde {start_id}"
        self._traversal_result, self.traversal_frames = res, res.frames
        self._set_active_route(list(res.path_pipes) if (target_id and res.target_reached) else [])
        self._traversal_log = self._log_traversal(res, start_id, target_id)
        msg = f"{res.algorithm}: {len(res.visited_order)} nodos" + (f" · Ruta ({len(res.path_pipes)}): {' → '.join(res.path_nodes)}" if (target_id and res.target_reached) else (f" · Sin ruta a {target_id}" if target_id else ""))
        if animate:
            if not self.traversal_frames: return
            self.anim_idx = 0
            self.anim_playing = True
            self._render_traversal_frame()
            if len(self.traversal_frames) > 1: self._anim_after_id = self.after(self._anim_delay(), self._anim_tick)
            else: self._stop_traversal(); self._render_traversal_frame()
            return
        self.anim_idx = max(0, len(self.traversal_frames) - 1)
        self.anim_playing = False
        sample = self.traversal_frames[min(1, len(self.traversal_frames) - 1)] if self.traversal_frames else None
        self._render_traversal_frame(summary_override=self._traversal_log, strip_frame=sample, step_text=f"muestra {res.algorithm}")
        self._status_lbl.configure(text=msg, fg=theme.SHELL_TEXT_MUTED)

    def _set_active_route(self, edges: List[PipeEdge]) -> None:
        """Ruta activa del último recorrido con destino: tiene prioridad en el perfil longitudinal."""
        self._active_route = edges
        if hasattr(self, "charts_panel"): self.charts_panel.set_route(edges or None)

    def start_traversal_animation(self, algo: str, start_id: str, target_id: Optional[str] = None) -> None:
        self._action_traversal(algo, start_id, target_id, animate=True)

    def _action_toggle_anim(self) -> None:
        """Botón «Animar recorrido»: alterna la animación; sin recorrido previo usa el último algoritmo."""
        if self.dataset is None: return
        if self.traversal_frames:
            self.toggle_traversal_animation()
        else:
            start_id, target_id = self.controls.get_traversal_endpoints()
            self._action_traversal(self._last_traversal_algo, start_id, target_id, True)

    def _render_traversal_frame(self, summary_override: str = "", strip_frame: Optional[TraversalFrame] = None,
                                step_text: Optional[str] = None) -> None:
        if not self.traversal_frames:
            self.network_canvas.set_traversal_highlight(
                mode=self._traversal_mode, origin_node=self._traversal_origin, banner_text=self._traversal_banner
            )
            self.controls.update_traversal_view(
                None, summary_text=summary_override, playing=self.anim_playing,
                mode=self._traversal_mode, has_frames=False,
            )
            return
        last = self.anim_idx == len(self.traversal_frames) - 1
        f = self.traversal_frames[self.anim_idx]
        lr = self._traversal_result if last else None
        self.network_canvas.set_traversal_highlight(
            f.visited_nodes, f.visited_edges,
            lr.path_nodes if lr else None, lr.path_pipes if lr else None,
            f.current_node, f.active_edge,
            mode=self._traversal_mode, origin_node=self._traversal_origin, banner_text=self._traversal_banner,
            active_nodes=f.active_nodes, active_edges=f.active_edges,
            backtracked_nodes=f.backtracked_nodes, backtracked_edges=f.backtracked_edges,
        )
        if last and not summary_override and not self.anim_playing:
            summary_override = self._traversal_log  # animación terminada: muestra el registro completo
        self.controls.update_traversal_view(
            strip_frame or f, summary_text=summary_override, playing=self.anim_playing,
            mode=self._traversal_mode, has_frames=True, step_text=step_text,
        )

    def _anim_tick(self) -> None:
        self._anim_after_id = None
        if not self.anim_playing or not self.traversal_frames: return
        if self.anim_idx + 1 < len(self.traversal_frames):
            self.anim_idx += 1
            if self.anim_idx == len(self.traversal_frames) - 1: self._stop_traversal()
            self._render_traversal_frame()
            if self.anim_playing: self._anim_after_id = self.after(self._anim_delay(), self._anim_tick)
        else: self._stop_traversal()

    def step_traversal_animation(self, delta: int) -> None:
        if not self.traversal_frames: return
        self._stop_traversal(); self.anim_idx = max(0, min(self.anim_idx + int(delta), len(self.traversal_frames) - 1)); self._render_traversal_frame()

    def toggle_traversal_animation(self) -> None:
        if not self.traversal_frames: return
        if self.anim_playing: self._stop_traversal(); self._render_traversal_frame(); return
        if self.anim_idx >= len(self.traversal_frames) - 1: self.anim_idx = 0
        self.anim_playing = True; self._render_traversal_frame(); self._anim_after_id = self.after(self._anim_delay(), self._anim_tick)

    def _action_trace(self, start_id: str, upstream: bool) -> None:
        if self.dataset is None: return
        g = self.dataset.graph
        if not start_id or not g.has_node(start_id):
            msg = f"Nodo «{start_id or '—'}» no encontrado en la red."
            self.controls.update_traversal_view(None, summary_text=msg, playing=False, has_frames=False)
            self._status_lbl.configure(text=msg, fg="#FCA5A5")
            messagebox.showwarning("Nodo no encontrado", msg, parent=self)
            return
        self._stop_traversal(); self._inspector_trace = None
        res = trace_upstream_result(g, start_id, record_frames=True) if upstream else trace_downstream(g, start_id, record_frames=True)
        self._traversal_mode = "upstream" if upstream else "downstream"
        self._set_active_route([])
        self._traversal_origin = start_id
        self._traversal_result = res
        self.traversal_frames = res.frames
        self.anim_idx = max(0, len(res.frames) - 1)
        self.anim_playing = False
        n_cnt, p_cnt = len(res.visited_order), len(res.traversed_edges)
        if upstream:
            self._traversal_banner = f"Aguas arriba · Aportes hacia {start_id} ({n_cnt} nodos, {p_cnt} tuberías)"
            if p_cnt == 0:
                msg = f"Aguas arriba de {start_id}: nodo fuente inicial sin aportes aguas arriba (0 tuberías entrantes). Pruebe con un pozo o PTAR 31."
            else:
                msg = f"Aguas arriba de {start_id}: {n_cnt} nodos, {p_cnt} tuberías"
        else:
            self._traversal_banner = f"Aguas abajo · Descarga desde {start_id} ({n_cnt} nodos, {p_cnt} tuberías)"
            if p_cnt == 0:
                msg = f"Aguas abajo desde {start_id}: sumidero / PTAR final sin tuberías salientes (0 tuberías)."
            else:
                msg = f"Aguas abajo desde {start_id}: {n_cnt} nodos, {p_cnt} tuberías"
        self._traversal_log = (f"[{'Aguas arriba' if upstream else 'Aguas abajo'} desde {start_id}]\n{msg}\n"
                               f"Nodos ({n_cnt}): {', '.join(res.visited_order[:14])}{' ...' if n_cnt > 14 else ''}\n"
                               f"Tuberías ({p_cnt}): {', '.join(p.pipe_id for p in res.traversed_edges[:14])}{' ...' if p_cnt > 14 else ''}")
        sample = res.frames[min(1, len(res.frames) - 1)] if res.frames else None
        self._render_traversal_frame(summary_override=self._traversal_log, strip_frame=sample, step_text="muestra")
        self._status_lbl.configure(text=msg, fg=theme.SHELL_TEXT_MUTED)

    def clear_traversal(self) -> None:
        self._stop_traversal(); self._inspector_trace = None
        if hasattr(self, "inspector_tab"): self._sync_inspector_context()
        self._traversal_result, self.traversal_frames, self.anim_idx = None, [], 0
        self._traversal_mode = None
        self._traversal_origin = None
        self._traversal_banner = self._traversal_log = ""
        self._set_active_route([])
        self.network_canvas.clear_traversal_highlight()
        self.controls.update_traversal_view(None, has_frames=False)
        self._status_lbl.configure(text="Recorrido limpiado", fg=theme.SHELL_TEXT_MUTED)

    # ── Comparación, I/O, reportes y cierre ──────────────────────────────────

    def run_comparison(self) -> Optional[List[ScenarioSummary]]:
        if self.dataset is None: return None
        try: cfg = self._build_config()
        except ValueError as exc: messagebox.showerror("Parámetros inválidos", str(exc), parent=self); return None
        t0 = time.perf_counter(); summaries = compare_all_scenarios(self.dataset, cfg); elapsed = (time.perf_counter() - t0) * 1000.0
        self.cached_comparisons, self._base_compare_key = summaries, _base_key(cfg)
        self.comparison_panel.set_comparisons(summaries, elapsed_ms=elapsed, is_visible=self._active_tab() == 3)
        self._status_lbl.configure(text=f"Comparación de {len(summaries)} escenarios ({elapsed:.0f} ms)")
        return summaries

    def _pick_and_load(self, is_dir: bool) -> None:
        p = filedialog.askdirectory(parent=self, title="Seleccionar carpeta CSV") if is_dir else filedialog.askopenfilename(parent=self, title="Cargar dataset Excel", filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")])
        if p: self.load_data(p)
    def _action_export_csv(self) -> None:
        if self.dataset and (out_dir := filedialog.askdirectory(parent=self, title="Exportar dataset a carpeta CSV")):
            try: export_to_csv_dir(self.dataset, out_dir); self._status_lbl.configure(text=f"CSV exportado: {out_dir}")
            except OSError as exc: messagebox.showerror("Error al exportar CSV", str(exc), parent=self)

    def _action_export(self, fmt: str) -> None:
        if self.dataset is None or self.result is None:
            messagebox.showwarning("Sin simulación", "Ejecute una simulación antes de exportar.", parent=self); return
        if self.cached_comparisons is None: self.run_comparison()
        is_docx = fmt == "docx"
        p = filedialog.asksaveasfilename(parent=self, title="Exportar reporte Word (.docx)" if is_docx else "Exportar reporte Markdown / CSV",
                                         defaultextension=".docx" if is_docx else ".md", filetypes=[("Word", "*.docx")] if is_docx else [("Markdown", "*.md")])
        if not p: return
        out = (generate_docx_report if is_docx else generate_markdown_report)(self.dataset, self.result, self.cached_comparisons, p)
        self._status_lbl.configure(text=f"Reporte guardado: {os.path.basename(out)}")
        messagebox.showinfo("Reporte exportado", f"Archivo generado en:\n{out}", parent=self)

    def _show_assumptions(self) -> None:
        win = tk.Toplevel(self)
        win.title("Supuestos del Modelo Computacional"); win.configure(bg=theme.PAPER_BG); win.resizable(False, False); win.transient(self)
        tk.Label(win, text="SUPUESTOS DEL MODELO HIDRÁULICO", bg=theme.SHELL_BG, fg=theme.SHELL_TEXT, font=self.fonts["title"], anchor="w", padx=12, pady=8).pack(fill=tk.X)
        tk.Label(win, text=MODEL_ASSUMPTIONS_TEXT, bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=self.fonts["body"], justify="left", anchor="w", wraplength=520, padx=14, pady=12).pack(fill=tk.BOTH, expand=True)
        self._btn(win, "Cerrar", win.destroy, "primary", padx=14, pady=4).pack(pady=(0, 12))

    def _on_close(self) -> None:
        self._closing = True
        self.tour.cancel_timers(); self._stop_playback(); self._stop_traversal(); self._cancel_timer("_slider_after_id"); self._cancel_timer("_resize_after_id")
        self.controls.cancel_pending()
        self.network_canvas.stop_pulse_animation(); self.network_canvas.cancel_pending(); self.charts_panel._cancel_cursor_timer()
        try: self.destroy()
        except tk.TclError: pass
