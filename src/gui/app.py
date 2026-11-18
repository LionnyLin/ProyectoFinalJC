"""Aplicación principal rediseñada — Lámina Cartográfica de Archivo Hidráulico (#4A4A4A, #CBCBCB, #FFFFE3, #6D8196)."""

import math
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Dict, List, Optional, Set, Tuple

from src.algorithms import (
    OVERLOAD_PERSISTENCE_LEVELS,
    SourceAttributionResult,
    TraversalAnimFrame,
    bfs,
    bfs_anim_frames,
    build_route_to_sink,
    classify_overload_persistence,
    classify_utilization,
    compute_source_attribution,
    dfs,
    dfs_anim_frames,
    find_isolated_from_sinks,
    rank_critical_pipes,
    search_entities,
    trace_downstream,
    trace_upstream,
)
from src.data_structures import PipeEdge
from src.io.data_loader import (
    DataLoadError,
    NetworkDataset,
    export_to_csv_dir,
    load_dataset,
)
from src.simulation import (
    PipeIntervention,
    ScenarioSummary,
    SewerSimulationEngine,
    SimulationConfig,
    SimulationResult,
    TimeStepSnapshot,
    compare_all_scenarios,
    generate_docx_report,
    generate_markdown_report,
    resolve_pipe_hydraulics,
)
from . import theme
from .charts_panel import ComparisonChartsPanel, TemporalChartsPanel
from .icons import build_icon_set
from .network_canvas import NetworkCanvas

_COMMERCIAL_DIAMETERS_IN = [
    "Original",
    '6"',
    '8"',
    '10"',
    '12"',
    '14"',
    '16"',
    '18"',
    '20"',
    '24"',
    '30"',
    '36"',
    '42"',
    '48"',
]


class BicentenarioSewerApp(tk.Tk):
    """Interfaz gráfica adaptable para simulación y análisis de la red de alcantarillado."""

    def __init__(self, initial_data_path: Optional[str] = None) -> None:
        theme.enable_dpi_awareness()
        super().__init__()
        self._dpi_scale: float = theme.resolve_dpi_scale(self)
        # Limitar DPI embebido (máx. ~115) y bloquear el reescalado dinámico de TkAgg para evitar recortes
        self._mpl_dpi: int = min(116, max(96, int(round(96.0 * min(1.20, self._dpi_scale)))))
        self._param_rerun_after: Optional[str] = None

        self.title("Red de Alcantarillado Ciudad Bicentenario · Simulador Hidráulico")
        self._configure_initial_geometry()
        self.configure(bg=theme.DOCK_BORDER)

        self.ui_font, self.mono_font, self.inter_loaded = theme.resolve_fonts(self)
        self.display_font = theme.resolve_display_font(self)
        self._icons = build_icon_set(
            fg_dark=theme.SHELL_TEXT,
            fg_light=theme.INK_PRIMARY,
            fg_on_accent=theme.ACCENT_INK,
            accent_color=theme.ACCENT_PRIMARY,
            scale=self._dpi_scale,
        )

        self.dataset: Optional[NetworkDataset] = None
        self.engine: Optional[SewerSimulationEngine] = None
        self.result: Optional[SimulationResult] = None
        self._previous_result: Optional[SimulationResult] = None
        self.comparisons: List[ScenarioSummary] = []
        self._comparisons_dirty: bool = True

        self.current_step: int = 0
        self.is_playing: bool = False
        self._after_id: Optional[str] = None
        self._resize_after_id: Optional[str] = None
        self._selected_pipe_id: Optional[str] = None
        self._selected_node_id: Optional[str] = None
        self._updating_slider: bool = False
        self._slider_restore_pending: bool = False
        self._suppress_tree_select: bool = False
        self._inspector_layout_state: Optional[tuple] = None
        self._insp_tab_dirty: bool = False
        self._crit_tab_dirty: bool = False
        self._charts_tab_dirty: bool = False

        # Estado de Cirugía Cartográfica, Cuenca Aportante, Animación BFS/DFS, Mapa de Estrés y Guía
        self._interventions: Dict[str, PipeIntervention] = {}
        self._isolated_nodes: Set[str] = set()
        self._isolated_pipes: Set[str] = set()
        self._basin_isolated: bool = False
        self._active_route_pipes: List[PipeEdge] = []
        self._last_traversal_alg: str = "BFS"
        self._anim_frames: List[TraversalAnimFrame] = []
        self._anim_idx: int = 0
        self._anim_after_id: Optional[str] = None
        self._is_animating_traversal: bool = False
        self._map_mode: str = "instant"
        self._map_mode_buttons: Dict[str, tk.Button] = {}
        self._tour_active: bool = False
        self._tour_step: int = 0
        self._source_attribution: Optional[SourceAttributionResult] = None
        self._last_attr_key: Optional[tuple] = None

        # Estado responsivo y de paneles
        self._show_left: bool = True
        self._show_right: bool = True
        self._rail_tab: str = "sim"
        self._layout_tier: str = ""
        self._topbar_mode: str = ""
        self._player_compact: Optional[bool] = None
        self._dataset_summary_text: str = "Sin conjunto de datos cargado"
        self._scenario_display_map: Dict[str, object] = {}

        # Variables de control
        self.var_scenario = tk.StringVar()
        self.var_duration = tk.DoubleVar(value=90.0)
        self.var_storm_dur = tk.DoubleVar(value=60.0)
        self.var_dt = tk.DoubleVar(value=1.0)
        self.var_ingress_pct = tk.DoubleVar(value=2.5)
        self.var_dry_flow = tk.DoubleVar(value=0.003)
        self.var_split_rule = tk.StringVar(value="proportional")
        self.var_hyetograph = tk.StringVar(value="uniform")
        self.var_split_rule_es = tk.StringVar(value=theme.SPLIT_RULE_TO_ES["proportional"])
        self.var_hyetograph_es = tk.StringVar(value=theme.HYETOGRAPH_TO_ES["uniform"])
        self.var_speed = tk.StringVar(value="2x")
        self.var_search = tk.StringVar()
        self.var_bfs_start = tk.StringVar(value="6")
        self.var_bfs_target = tk.StringVar(value="31")
        self.var_crit_filter = tk.StringVar(value="all")
        self.var_show_pipe_labels = tk.BooleanVar(value=True)
        self.var_show_util_labels = tk.BooleanVar(value=True)
        self.var_obstruction_pct = tk.DoubleVar(value=0.0)
        self.var_diam_override = tk.StringVar(value="Original")

        self.var_split_rule_es.trace_add(
            "write",
            lambda *_a: self.var_split_rule.set(
                theme.ES_TO_SPLIT_RULE.get(self.var_split_rule_es.get(), "proportional")
            ),
        )
        self.var_hyetograph_es.trace_add(
            "write",
            lambda *_a: self.var_hyetograph.set(
                theme.ES_TO_HYETOGRAPH.get(self.var_hyetograph_es.get(), "uniform")
            ),
        )

        for v in (
            self.var_duration,
            self.var_storm_dur,
            self.var_dt,
            self.var_ingress_pct,
            self.var_dry_flow,
            self.var_split_rule,
            self.var_hyetograph,
        ):
            v.trace_add("write", lambda *_a: self._mark_comparisons_dirty())

        self._legend_count_labels: List[tk.Label] = []
        self._legend_text_labels: List[tk.Label] = []
        self._legend_header_label: Optional[tk.Label] = None

        self._configure_styles()
        self._build_layout()
        self._bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        default_path = initial_data_path or self._find_default_dataset()
        if default_path:
            self._load_path(default_path, silent_error=False)
            if self.dataset is not None:
                self.run_simulation()

        self.update_idletasks()
        self._apply_responsive_layout(self.winfo_width(), self.winfo_height())

    def _px(self, base_px: int) -> int:
        return max(1, int(round(base_px * self._dpi_scale)))

    def _configure_initial_geometry(self) -> None:
        sw = max(800, self.winfo_screenwidth())
        sh = max(600, self.winfo_screenheight())
        init_w = max(860, min(int(round(1440 * min(1.15, self._dpi_scale))), int(sw * 0.92)))
        init_h = max(580, min(int(round(880 * min(1.15, self._dpi_scale))), int(sh * 0.88)))
        pos_x = max(0, (sw - init_w) // 2)
        pos_y = max(0, (sh - init_h) // 2)
        self.geometry(f"{init_w}x{init_h}+{pos_x}+{pos_y}")
        self.minsize(780, 540)

    def _find_default_dataset(self) -> Optional[str]:
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        xlsx = os.path.join(base, "data", "DataSetBicentenario.xlsx")
        if os.path.isfile(xlsx):
            return xlsx
        csv_dir = os.path.join(base, "data", "csv")
        if os.path.isdir(csv_dir):
            return csv_dir
        return None

    def _configure_styles(self) -> None:
        self.option_add("*TCombobox*Listbox.background", theme.PAPER_BG)
        self.option_add("*TCombobox*Listbox.foreground", theme.INK_PRIMARY)
        self.option_add("*TCombobox*Listbox.selectBackground", theme.ACCENT_PRIMARY)
        self.option_add("*TCombobox*Listbox.selectForeground", theme.ACCENT_INK)
        self.option_add("*TCombobox*Listbox.font", (self.ui_font, 9))

        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            ".",
            background=theme.PAPER_BG,
            foreground=theme.INK_PRIMARY,
            font=(self.ui_font, 9),
        )
        style.configure("TFrame", background=theme.PAPER_BG)
        style.configure("TLabel", background=theme.PAPER_BG, foreground=theme.INK_PRIMARY)
        style.configure(
            "TNotebook",
            background=theme.DOCK_BG,
            borderwidth=0,
            tabmargins=(6, 6, 6, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=theme.PAPER_SUBTLE,
            foreground=theme.INK_PRIMARY,
            padding=(11, 7),
            font=(self.ui_font, 9, "bold"),
            borderwidth=1,
            bordercolor=theme.DOCK_BORDER,
            lightcolor=theme.PAPER_SUBTLE,
            darkcolor=theme.DOCK_BG,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", theme.ACCENT_PRIMARY), ("active", theme.PAPER_HOVER)],
            foreground=[("selected", theme.ACCENT_INK), ("active", theme.INK_PRIMARY)],
        )
        style.configure(
            "Treeview",
            background=theme.PAPER_BG,
            foreground=theme.INK_PRIMARY,
            fieldbackground=theme.PAPER_BG,
            rowheight=self._px(24),
            borderwidth=0,
            font=(self.mono_font, 8),
        )
        style.configure(
            "Treeview.Heading",
            background=theme.SHELL_BG,
            foreground=theme.SHELL_TEXT,
            relief="flat",
            padding=(4, 5),
            font=(self.ui_font, 8, "bold"),
            bordercolor=theme.ACCENT_PRIMARY,
        )
        style.map(
            "Treeview.Heading",
            background=[("active", theme.SHELL_ELEVATED)],
            foreground=[("active", theme.SHELL_TEXT)],
        )
        style.map(
            "Treeview",
            background=[("selected", theme.ACCENT_SOFT)],
            foreground=[("selected", theme.INK_PRIMARY)],
        )
        style.configure(
            "Dark.TCombobox",
            fieldbackground=theme.SHELL_SURFACE,
            background=theme.SHELL_ELEVATED,
            foreground=theme.SHELL_TEXT,
            bordercolor=theme.ACCENT_PRIMARY,
            arrowcolor=theme.SHELL_TEXT,
            insertcolor=theme.SHELL_TEXT,
            padding=4,
        )
        style.map(
            "Dark.TCombobox",
            fieldbackground=[("readonly", theme.SHELL_SURFACE)],
            selectbackground=[("readonly", theme.ACCENT_PRIMARY)],
            selectforeground=[("readonly", theme.ACCENT_INK)],
        )
        style.configure(
            "Light.TCombobox",
            fieldbackground=theme.PAPER_BG,
            background=theme.DOCK_BG,
            foreground=theme.INK_PRIMARY,
            bordercolor=theme.DOCK_BORDER,
            arrowcolor=theme.INK_PRIMARY,
            padding=3,
        )
        style.map(
            "Light.TCombobox",
            fieldbackground=[("readonly", theme.PAPER_BG)],
            selectbackground=[("readonly", theme.ACCENT_SOFT)],
            selectforeground=[("readonly", theme.INK_PRIMARY)],
        )
        style.configure(
            "Dark.Vertical.TScrollbar",
            background=theme.SHELL_ELEVATED,
            troughcolor=theme.SHELL_BG,
            bordercolor=theme.SHELL_BG,
            arrowcolor=theme.SHELL_TEXT,
            relief="flat",
        )
        style.configure(
            "Dock.Vertical.TScrollbar",
            background=theme.ACCENT_PRIMARY,
            troughcolor=theme.DOCK_BG,
            bordercolor=theme.DOCK_BORDER,
            arrowcolor=theme.INK_PRIMARY,
            relief="flat",
        )
        style.configure(
            "Light.Vertical.TScrollbar",
            background=theme.DOCK_BG,
            troughcolor=theme.PAPER_SUBTLE,
            bordercolor=theme.PAPER_BORDER,
            arrowcolor=theme.INK_PRIMARY,
            relief="flat",
        )

    def _make_btn(
        self,
        parent: tk.Misc,
        text: str,
        command: Callable[[], None],
        *,
        variant: str = "light_secondary",
        padx: int = 10,
        pady: int = 5,
        font_size: int = 9,
        width: Optional[int] = None,
        image: Optional[tk.PhotoImage] = None,
        compound: Optional[str] = None,
    ) -> tk.Button:
        """Crea un botón con paleta consistente y estados hover/focus."""
        palettes: Dict[str, tuple] = {
            "primary": (theme.ACCENT_PRIMARY, theme.ACCENT_INK, theme.ACCENT_HOVER, theme.INK_PRIMARY),
            "dark_primary": (theme.ACCENT_ON_DARK, theme.ACCENT_ON_DARK_INK, theme.ACCENT_ON_DARK_HOVER, theme.ACCENT_ON_DARK),
            "dark_secondary": (theme.SHELL_ELEVATED, theme.SHELL_TEXT, theme.SHELL_HOVER, theme.SHELL_BORDER),
            "dark_ghost": (theme.SHELL_BG, theme.SHELL_TEXT_SECONDARY, theme.SHELL_ELEVATED, theme.SHELL_BORDER),
            "dock_secondary": (theme.DOCK_BG, theme.INK_PRIMARY, theme.DOCK_HOVER, theme.DOCK_BORDER),
            "light_secondary": (theme.PAPER_SUBTLE, theme.INK_PRIMARY, theme.PAPER_HOVER, theme.DOCK_BORDER),
        }
        bg, fg, hover_bg, border = palettes[variant]
        kw = {
            "text": text,
            "command": command,
            "bg": bg,
            "fg": fg,
            "activebackground": hover_bg,
            "activeforeground": fg,
            "relief": "flat",
            "bd": 0,
            "padx": padx,
            "pady": pady,
            "font": (self.ui_font, font_size, "bold" if "primary" in variant else "normal"),
            "cursor": "hand2",
            "highlightthickness": 1,
            "highlightbackground": border,
            "highlightcolor": theme.ACCENT_PRIMARY,
        }
        if width is not None:
            kw["width"] = width
        if image is not None:
            kw["image"] = image
            if compound is not None:
                kw["compound"] = compound
        btn = tk.Button(parent, **kw)
        btn._base_bg = bg  # type: ignore[attr-defined]
        btn._hover_bg = hover_bg  # type: ignore[attr-defined]
        btn.bind("<Enter>", lambda _e, b=btn: b.configure(bg=b._hover_bg))
        btn.bind("<Leave>", lambda _e, b=btn: b.configure(bg=b._base_bg))
        return btn

    def _set_btn_variant(self, btn: tk.Button, variant: str) -> None:
        palettes: Dict[str, tuple] = {
            "primary": (theme.ACCENT_PRIMARY, theme.ACCENT_INK, theme.ACCENT_HOVER, theme.INK_PRIMARY),
            "dark_primary": (theme.ACCENT_ON_DARK, theme.ACCENT_ON_DARK_INK, theme.ACCENT_ON_DARK_HOVER, theme.ACCENT_ON_DARK),
            "dark_secondary": (theme.SHELL_ELEVATED, theme.SHELL_TEXT, theme.SHELL_HOVER, theme.SHELL_BORDER),
            "dock_secondary": (theme.DOCK_BG, theme.INK_PRIMARY, theme.DOCK_HOVER, theme.DOCK_BORDER),
            "light_secondary": (theme.PAPER_SUBTLE, theme.INK_PRIMARY, theme.PAPER_HOVER, theme.DOCK_BORDER),
        }
        bg, fg, hover_bg, border = palettes[variant]
        btn._base_bg = bg  # type: ignore[attr-defined]
        btn._hover_bg = hover_bg  # type: ignore[attr-defined]
        btn.configure(
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            highlightbackground=border,
            font=(self.ui_font, 8, "bold" if "primary" in variant else "normal"),
        )

    def _build_layout(self) -> None:
        # 1. Barra superior grafito (#4A4A4A) con filete azul pizarra (#6D8196)
        self.topbar = tk.Frame(self, bg=theme.SHELL_BG, height=self._px(54))
        self.topbar.pack(side=tk.TOP, fill=tk.X)
        tk.Frame(self, bg=theme.ACCENT_PRIMARY, height=3).pack(side=tk.TOP, fill=tk.X)

        left_bar = tk.Frame(self.topbar, bg=theme.SHELL_BG)
        left_bar.pack(side=tk.LEFT, padx=(10, 8), pady=8)

        brand_badge = tk.Label(
            left_bar,
            image=self._icons["brand_network"],
            bg=theme.SHELL_BG,
        )
        brand_badge.pack(side=tk.LEFT, padx=(0, 8))

        title_wrap = tk.Frame(left_bar, bg=theme.SHELL_BG)
        title_wrap.pack(side=tk.LEFT, padx=(0, 14))
        self.lbl_app_title = tk.Label(
            title_wrap,
            text="Simulador Hidráulico · Ciudad Bicentenario",
            bg=theme.SHELL_BG,
            fg=theme.SHELL_TEXT,
            font=(self.display_font, 11, "bold"),
            anchor="w",
        )
        self.lbl_app_title.pack(anchor="w")
        self.lbl_app_subtitle = tk.Label(
            title_wrap,
            text="Red dirigida de alcantarillado hacia PTAR Punta Canoa (Nodo 31)",
            bg=theme.SHELL_BG,
            fg=theme.SHELL_TEXT_MUTED,
            font=(self.ui_font, 8),
            anchor="w",
        )
        self.lbl_app_subtitle.pack(anchor="w")

        self.btn_toggle_left = self._make_btn(
            left_bar,
            " Controles",
            self.toggle_left_panel,
            variant="dark_secondary",
            padx=9,
            pady=4,
            font_size=8,
            image=self._icons["sliders_light"],
            compound=tk.LEFT,
        )
        self.btn_toggle_left.pack(side=tk.LEFT, padx=(0, 6))

        self.btn_toggle_right = self._make_btn(
            left_bar,
            " Análisis",
            self.toggle_right_panel,
            variant="dark_secondary",
            padx=9,
            pady=4,
            font_size=8,
            image=self._icons["chart_light"],
            compound=tk.LEFT,
        )
        self.btn_toggle_right.pack(side=tk.LEFT)

        # Acciones de la barra superior (se reorganizan según ancho de ventana)
        self.actions_bar = tk.Frame(self.topbar, bg=theme.SHELL_BG)
        self.actions_bar.pack(side=tk.RIGHT, padx=10, pady=8)

        self.btn_report = self._make_btn(
            self.actions_bar,
            "Generar Reporte",
            self._action_generate_report,
            variant="dark_primary",
            padx=11,
            pady=4,
            font_size=8,
        )
        self.btn_assumptions = self._make_btn(
            self.actions_bar, "Supuestos", self._action_show_assumptions, variant="dark_secondary", padx=9, pady=4, font_size=8
        )
        self.btn_export_csv = self._make_btn(
            self.actions_bar, "Exportar CSV", self._action_export_csv, variant="dark_secondary", padx=9, pady=4, font_size=8
        )
        self.btn_load_csv = self._make_btn(
            self.actions_bar, "Cargar CSV", self._action_load_csv, variant="dark_secondary", padx=9, pady=4, font_size=8
        )
        self.btn_load_excel = self._make_btn(
            self.actions_bar, "Cargar Excel", self._action_load_excel, variant="dark_secondary", padx=9, pady=4, font_size=8
        )
        self.btn_guided_tour = self._make_btn(
            self.actions_bar,
            "Recorrido Guiado (4 Hallazgos)",
            self.toggle_guided_tour,
            variant="dark_secondary",
            padx=9,
            pady=4,
            font_size=8,
        )

        # Menú compacto para ventanas medianas/estrechas
        self.menu_btn_file = tk.Menubutton(
            self.actions_bar,
            text="Archivo y Modelo ",
            image=self._icons["chevron_light"],
            compound=tk.RIGHT,
            bg=theme.SHELL_ELEVATED,
            fg=theme.SHELL_TEXT,
            activebackground=theme.SHELL_HOVER,
            activeforeground=theme.SHELL_TEXT,
            relief="flat",
            bd=0,
            padx=10,
            pady=5,
            font=(self.ui_font, 8, "bold"),
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=theme.ACCENT_PRIMARY,
        )
        file_menu = tk.Menu(
            self.menu_btn_file,
            tearoff=0,
            bg=theme.SHELL_BG,
            fg=theme.SHELL_TEXT,
            activebackground=theme.ACCENT_PRIMARY,
            activeforeground=theme.ACCENT_INK,
            font=(self.ui_font, 9),
        )
        file_menu.add_command(label="Cargar Excel (.xlsx)...", command=self._action_load_excel)
        file_menu.add_command(label="Cargar carpeta CSV...", command=self._action_load_csv)
        file_menu.add_command(label="Exportar CSV...", command=self._action_export_csv)
        file_menu.add_separator()
        file_menu.add_command(label="Supuestos del modelo", command=self._action_show_assumptions)
        self.menu_btn_file.configure(menu=file_menu)

        # 2. Barra de estado inferior en grafito (#4A4A4A) con línea azul pizarra
        statusbar = tk.Frame(self, bg=theme.SHELL_BG, height=self._px(27))
        statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(self, bg=theme.ACCENT_PRIMARY, height=2).pack(side=tk.BOTTOM, fill=tk.X)

        self.status_var = tk.StringVar(value="Listo.")
        tk.Label(
            statusbar,
            textvariable=self.status_var,
            bg=theme.SHELL_BG,
            fg=theme.SHELL_TEXT,
            font=(self.ui_font, 8),
            anchor="w",
        ).pack(side=tk.LEFT, padx=12, pady=3)

        self.lbl_shortcuts_hint = tk.Label(
            statusbar,
            text="Espacio: Reproducir/Pausar  ·  ←/→: Paso  ·  Ctrl+F: Buscar  ·  Esc: Limpiar",
            bg=theme.SHELL_BG,
            fg=theme.SHELL_TEXT_MUTED,
            font=(self.ui_font, 8),
        )
        self.lbl_shortcuts_hint.pack(side=tk.RIGHT, padx=12, pady=3)

        # 3. Área principal redimensionable
        self.main_pane = tk.PanedWindow(
            self,
            orient=tk.HORIZONTAL,
            bg=theme.DOCK_BORDER,
            sashwidth=4,
            bd=0,
            opaqueresize=True,
        )
        self.main_pane.pack(fill=tk.BOTH, expand=True)

        # Panel izquierdo: Muelle Plata Mineral (#CBCBCB) con láminas Vitela (#FFFFE3)
        self.left_panel = tk.Frame(self.main_pane, bg=theme.DOCK_BG, width=self._px(288))
        self.left_panel.pack_propagate(False)

        rail_tabs_bar = tk.Frame(self.left_panel, bg=theme.DOCK_BG)
        rail_tabs_bar.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(10, 6))
        self.btn_rail_sim = self._make_btn(
            rail_tabs_bar,
            "Simulación",
            lambda: self._switch_rail_tab("sim"),
            variant="primary",
            padx=8,
            pady=5,
            font_size=8,
        )
        self.btn_rail_sim.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        self.btn_rail_trav = self._make_btn(
            rail_tabs_bar,
            "Recorridos",
            lambda: self._switch_rail_tab("trav"),
            variant="light_secondary",
            padx=8,
            pady=5,
            font_size=8,
        )
        self.btn_rail_trav.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))
        tk.Frame(self.left_panel, bg=theme.DOCK_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

        self.left_canvas = tk.Canvas(
            self.left_panel, bg=theme.DOCK_BG, highlightthickness=0, bd=0
        )
        left_scroll = ttk.Scrollbar(
            self.left_panel,
            orient=tk.VERTICAL,
            command=self.left_canvas.yview,
            style="Dock.Vertical.TScrollbar",
        )
        self.left_frame = tk.Frame(self.left_canvas, bg=theme.DOCK_BG)
        self._left_window_id = self.left_canvas.create_window(
            (0, 0), window=self.left_frame, anchor="nw"
        )
        self.left_frame.bind(
            "<Configure>",
            lambda _e: self.left_canvas.configure(scrollregion=self.left_canvas.bbox("all")),
        )
        self.left_canvas.bind(
            "<Configure>",
            lambda e: self.left_canvas.itemconfigure(self._left_window_id, width=e.width),
        )
        self.left_canvas.configure(yscrollcommand=left_scroll.set)
        self.left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.left_panel.bind("<Enter>", lambda _e: self._bind_left_mousewheel(True))
        self.left_panel.bind("<Leave>", lambda _e: self._bind_left_mousewheel(False))

        self._build_left_controls(self.left_frame)

        # Panel central: Franja de telemetría + Lienzo Vitela + Reproductor
        self.center_panel = tk.Frame(self.main_pane, bg=theme.DOCK_BG)
        self._build_center_panel(self.center_panel)

        # Panel derecho: Muelle analítico en Plata Mineral + Notebook Vitela
        self.right_panel = tk.Frame(self.main_pane, bg=theme.DOCK_BG, width=self._px(382))
        self.right_panel.pack_propagate(False)
        self._right_tabs_compact: Optional[bool] = None
        self.right_panel.bind("<Configure>", self._on_right_configure)
        self._build_right_panel(self.right_panel)

        self._sync_panes()
        self._update_toggle_styles()
        self.bind("<Configure>", self._on_window_configure)

    def _bind_left_mousewheel(self, active: bool) -> None:
        if active:
            self.left_canvas.bind_all("<MouseWheel>", self._on_left_wheel)
            self.left_canvas.bind_all("<Button-4>", lambda _e: self.left_canvas.yview_scroll(-1, "units"))
            self.left_canvas.bind_all("<Button-5>", lambda _e: self.left_canvas.yview_scroll(1, "units"))
        else:
            self.left_canvas.unbind_all("<MouseWheel>")
            self.left_canvas.unbind_all("<Button-4>")
            self.left_canvas.unbind_all("<Button-5>")

    def _on_left_wheel(self, event: tk.Event) -> None:
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is not None and self._is_descendant(widget, self.left_panel):
            self.left_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    @staticmethod
    def _is_descendant(widget: tk.Misc, ancestor: tk.Misc) -> bool:
        cur: Optional[tk.Misc] = widget
        while cur is not None:
            if cur is ancestor:
                return True
            cur = getattr(cur, "master", None)
        return False

    def _bind_shortcuts(self) -> None:
        self.bind("<space>", self._shortcut_play_pause)
        self.bind("<Left>", lambda e: self._shortcut_step(e, -1))
        self.bind("<Right>", lambda e: self._shortcut_step(e, 1))
        self.bind("<Home>", self._shortcut_home)
        self.bind("<Control-f>", self._shortcut_focus_search)
        self.bind("<Escape>", self._shortcut_escape)

    def _is_typing_widget(self) -> bool:
        w = self.focus_get()
        if w is None:
            return False
        return w.winfo_class() in ("Entry", "TEntry", "Spinbox", "TSpinbox", "TCombobox", "Text")

    def _shortcut_play_pause(self, _event: tk.Event) -> Optional[str]:
        if self._is_typing_widget():
            return None
        self.toggle_play_pause()
        return "break"

    def _shortcut_step(self, _event: tk.Event, delta: int) -> Optional[str]:
        if self._is_typing_widget():
            return None
        self._player_step(delta)
        return "break"

    def _shortcut_home(self, _event: tk.Event) -> Optional[str]:
        if self._is_typing_widget():
            return None
        self._player_reset()
        return "break"

    def _shortcut_focus_search(self, _event: tk.Event) -> str:
        if not self._show_left:
            self.toggle_left_panel()
        self._switch_rail_tab("trav")
        self.entry_search.focus_set()
        self.entry_search.select_range(0, tk.END)
        return "break"

    def _shortcut_escape(self, _event: tk.Event) -> None:
        if self._tour_active:
            self._close_guided_tour()
        self._clear_highlights()
        self._selected_pipe_id = None
        self._selected_node_id = None
        self._basin_isolated = False
        self.network_canvas.set_basin_focus(None, None)
        self.network_canvas.select_pipe(None)
        self.network_canvas.select_node(None)
        self._refresh_inspector()

    def _on_window_configure(self, event: tk.Event) -> None:
        if event.widget is not self:
            return
        if self._resize_after_id is not None:
            self.after_cancel(self._resize_after_id)
        self._resize_after_id = self.after(
            70, lambda: self._apply_responsive_layout(self.winfo_width(), self.winfo_height())
        )

    def _apply_responsive_layout(self, width: int, height: int) -> None:
        self._resize_after_id = None
        if width < 200 or height < 200:
            return

        new_tier = (
            "wide"
            if width >= theme.BREAKPOINT_MEDIUM
            else ("medium" if width >= theme.BREAKPOINT_COMPACT else "compact")
        )
        tier_changed = new_tier != self._layout_tier
        self._layout_tier = new_tier

        # 1. Adaptación de la barra superior (garantiza visibilidad de Guía y acciones en todo ancho)
        tb_mode = "wide" if width >= 1220 else ("medium" if width >= 920 else "compact")
        wide_full_bar = width >= 1660
        tour_lbl = "Recorrido Guiado (4 Hallazgos)" if width >= 1340 else "Guía 4"
        topbar_sig = (tb_mode, wide_full_bar, tour_lbl)
        if topbar_sig != getattr(self, "_topbar_layout_sig", None):
            self._topbar_layout_sig = topbar_sig
            self._topbar_mode = tb_mode
            for child in self.actions_bar.pack_slaves():
                child.pack_forget()
            self.btn_guided_tour.configure(text=tour_lbl)

            if tb_mode == "wide":
                if not self.lbl_app_subtitle.winfo_ismapped():
                    self.lbl_app_subtitle.pack(anchor="w")
                self.lbl_app_title.configure(text="Simulador Hidráulico · Ciudad Bicentenario")
                self.btn_report.configure(text="Generar Reporte")
                self.btn_report.pack(side=tk.RIGHT, padx=(4, 0))
                if wide_full_bar:
                    self.btn_assumptions.pack(side=tk.RIGHT, padx=4)
                    self.btn_export_csv.pack(side=tk.RIGHT, padx=4)
                    self.btn_load_csv.pack(side=tk.RIGHT, padx=4)
                    self.btn_load_excel.pack(side=tk.RIGHT, padx=4)
                else:
                    self.menu_btn_file.configure(text="Archivo y Modelo ")
                    self.menu_btn_file.pack(side=tk.RIGHT, padx=4)
                self.btn_guided_tour.pack(side=tk.RIGHT, padx=(0, 6))
            elif tb_mode == "medium":
                self.lbl_app_subtitle.pack_forget()
                self.lbl_app_title.configure(text="Ciudad Bicentenario")
                self.btn_report.configure(text="Generar Reporte")
                self.menu_btn_file.configure(text="Archivo y Modelo ")
                self.btn_report.pack(side=tk.RIGHT, padx=(6, 0))
                self.menu_btn_file.pack(side=tk.RIGHT, padx=4)
                self.btn_guided_tour.pack(side=tk.RIGHT, padx=(0, 4))
            else:
                self.lbl_app_subtitle.pack_forget()
                self.lbl_app_title.configure(text="Ciudad Bicentenario")
                self.btn_report.configure(text="Reporte")
                self.menu_btn_file.configure(text="Archivo ")
                self.btn_report.pack(side=tk.RIGHT, padx=(6, 0))
                self.menu_btn_file.pack(side=tk.RIGHT, padx=4)
                self.btn_guided_tour.pack(side=tk.RIGHT, padx=(0, 4))

        # 2. Atajos de teclado en barra de estado solo si caben
        if width >= 980:
            if not self.lbl_shortcuts_hint.winfo_ismapped():
                self.lbl_shortcuts_hint.pack(side=tk.RIGHT, padx=12, pady=3)
        else:
            self.lbl_shortcuts_hint.pack_forget()

        # 3. Adaptación de paneles laterales según umbral
        if tier_changed:
            if new_tier == "compact" and self._show_left and self._show_right:
                self._show_right = False
            self._sync_panes()
            self._update_toggle_styles()

        # 4. Ajuste de proporciones de sashes cuando la ventana se reduce
        self._clamp_sashes(width)

    def _sync_panes(self) -> None:
        for pane in list(self.main_pane.panes()):
            self.main_pane.forget(pane)

        tier = self._layout_tier or "wide"
        left_min = 272 if tier == "wide" else 264
        center_min = 420 if tier == "wide" else 310
        right_min = 340 if tier == "wide" else 285

        if self._show_left:
            self.main_pane.add(self.left_panel, minsize=left_min, stretch="never")
        self.main_pane.add(self.center_panel, minsize=center_min, stretch="always")
        if self._show_right:
            self.main_pane.add(self.right_panel, minsize=right_min, stretch="never")

    def _clamp_sashes(self, total_w: int) -> None:
        panes = list(self.main_pane.panes())
        if len(panes) <= 1 or total_w < 400:
            return
        try:
            self.update_idletasks()
            if self._show_left and self._show_right and len(panes) == 3:
                if total_w >= theme.BREAKPOINT_MEDIUM:
                    left_target = min(self._px(304), max(272, int(total_w * 0.21)))
                    right_target = min(self._px(440), max(360, int(total_w * 0.30)))
                else:
                    left_target = min(272, max(264, int(total_w * 0.25)))
                    right_target = min(344, max(296, int(total_w * 0.31)))
                self.main_pane.sash_place(0, left_target, 0)
                self.main_pane.sash_place(1, max(left_target + 320, total_w - right_target), 0)
            elif self._show_left and not self._show_right and len(panes) == 2:
                left_target = min(self._px(304), max(264, int(total_w * 0.27)))
                self.main_pane.sash_place(0, left_target, 0)
            elif not self._show_left and self._show_right and len(panes) == 2:
                right_target = min(self._px(420), max(324, int(total_w * 0.39)))
                self.main_pane.sash_place(0, max(320, total_w - right_target), 0)
        except tk.TclError:
            pass

    def _update_toggle_styles(self) -> None:
        self._set_btn_variant(
            self.btn_toggle_left, "dark_primary" if self._show_left else "dark_secondary"
        )
        self.btn_toggle_left.configure(
            image=self._icons["sliders_ink"] if self._show_left else self._icons["sliders_light"]
        )
        self._set_btn_variant(
            self.btn_toggle_right, "dark_primary" if self._show_right else "dark_secondary"
        )
        self.btn_toggle_right.configure(
            image=self._icons["chart_ink"] if self._show_right else self._icons["chart_light"]
        )

    def toggle_left_panel(self) -> None:
        self._show_left = not self._show_left
        if self._show_left and self._layout_tier == "compact":
            self._show_right = False
        self._sync_panes()
        self._update_toggle_styles()
        self.after_idle(lambda: self._clamp_sashes(self.winfo_width()))

    def toggle_right_panel(self) -> None:
        self._show_right = not self._show_right
        if self._show_right and self._layout_tier == "compact":
            self._show_left = False
        self._sync_panes()
        self._update_toggle_styles()
        self.after_idle(lambda: self._clamp_sashes(self.winfo_width()))

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
            self._rail_trav_container.pack(fill=tk.X, expand=True)
            self._set_btn_variant(self.btn_rail_sim, "light_secondary")
            self._set_btn_variant(self.btn_rail_trav, "primary")
        else:
            self._rail_sim_container.pack(fill=tk.X, expand=True)
            self._set_btn_variant(self.btn_rail_sim, "primary")
            self._set_btn_variant(self.btn_rail_trav, "light_secondary")
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
        self.combo_scenario = ttk.Combobox(
            sec_sim,
            textvariable=self.var_scenario,
            state="readonly",
            style="Light.TCombobox",
        )
        self.combo_scenario.pack(fill=tk.X, pady=(0, 8))
        self.combo_scenario.bind("<<ComboboxSelected>>", lambda _e: self._on_simulation_option_changed(mark_comp=False))

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
        grid.columnconfigure(0, weight=1)

        preset_row = tk.Frame(sec_sim, bg=theme.PAPER_BG)
        preset_row.pack(fill=tk.X, pady=(8, 4))
        self._make_btn(
            preset_row,
            "Calibrado (2.5%)",
            lambda: self._apply_preset(2.5, 0.003),
            variant="dock_secondary",
            padx=6,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        self._make_btn(
            preset_row,
            "Racional 100%",
            lambda: self._apply_preset(100.0, 0.0),
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
        self.combo_split_rule = ttk.Combobox(
            row_rules,
            textvariable=self.var_split_rule_es,
            values=list(theme.SPLIT_RULE_TO_ES.values()),
            state="readonly",
            width=14,
            style="Light.TCombobox",
        )
        self.combo_split_rule.pack(side=tk.RIGHT)
        self.combo_split_rule.bind("<<ComboboxSelected>>", lambda _e: self._on_simulation_option_changed(mark_comp=True))

        row_hyeto = tk.Frame(sec_sim, bg=theme.PAPER_BG)
        row_hyeto.pack(fill=tk.X, pady=3)
        tk.Label(
            row_hyeto,
            text="Hietograma",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8),
        ).pack(side=tk.LEFT)
        self.combo_hyetograph = ttk.Combobox(
            row_hyeto,
            textvariable=self.var_hyetograph_es,
            values=list(theme.HYETOGRAPH_TO_ES.values()),
            state="readonly",
            width=14,
            style="Light.TCombobox",
        )
        self.combo_hyetograph.pack(side=tk.RIGHT)
        self.combo_hyetograph.bind("<<ComboboxSelected>>", lambda _e: self._on_simulation_option_changed(mark_comp=True))

        self._make_btn(
            sec_sim,
            " Ejecutar simulación",
            self.run_simulation,
            variant="primary",
            pady=6,
            font_size=9,
            image=self._icons["play_on_accent"],
            compound=tk.LEFT,
        ).pack(fill=tk.X, pady=(8, 0))

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

    def _build_center_panel(self, parent: tk.Frame) -> None:
        # Franja superior de telemetría: bloque de reloj en grafito (#4A4A4A) + 4 tarjetas KPI en vitela (#FFFFE3)
        kpi_header = tk.Frame(
            parent,
            bg=theme.DOCK_BG,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )
        kpi_header.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(8, 0))

        row_top = tk.Frame(kpi_header, bg=theme.PAPER_BG)
        row_top.pack(fill=tk.X)

        view_opts = tk.Frame(row_top, bg=theme.PAPER_BG)
        view_opts.pack(side=tk.RIGHT, padx=8)
        for label, var in [("% Util.", self.var_show_util_labels), ("IDs", self.var_show_pipe_labels)]:
            tk.Checkbutton(
                view_opts,
                text=label,
                variable=var,
                command=self._toggle_labels,
                bg=theme.PAPER_BG,
                fg=theme.INK_PRIMARY,
                selectcolor=theme.PAPER_BG,
                activebackground=theme.PAPER_BG,
                activeforeground=theme.ACCENT_TEXT_ON_LIGHT,
                font=(self.ui_font, 8, "bold"),
                cursor="hand2",
            ).pack(side=tk.RIGHT, padx=(4, 0))

        clock_pill = tk.Frame(row_top, bg=theme.SHELL_BG)
        clock_pill.pack(side=tk.LEFT, padx=8, pady=6)
        self.lbl_clock = tk.Label(
            clock_pill,
            text="t = 0.0 min  ·  Escenario: -",
            bg=theme.SHELL_BG,
            fg=theme.SHELL_TEXT,
            font=(self.mono_font, 9, "bold"),
            anchor="w",
            padx=9,
            pady=3,
        )
        self.lbl_clock.pack(side=tk.LEFT)

        tk.Frame(kpi_header, bg=theme.DOCK_BORDER, height=1).pack(fill=tk.X)

        row_metrics = tk.Frame(kpi_header, bg=theme.DOCK_BG)
        row_metrics.pack(fill=tk.X, padx=0, pady=0)

        self._kpi_cards: Dict[str, tk.Label] = {}
        kpi_defs = [
            ("max_util", "UTILIZACIÓN MÁX.", "-"),
            ("critical", "CRÍTICAS (≥75%)", "-"),
            ("overloaded", "SOBRECARGA (>100%)", "-"),
            ("ptar", "DESCARGA PTAR 31", "-"),
        ]
        for idx, (key, caption, initial) in enumerate(kpi_defs):
            cell = tk.Frame(row_metrics, bg=theme.PAPER_BG)
            cell.grid(
                row=0,
                column=idx,
                sticky="nsew",
                padx=(0 if idx == 0 else 1, 0),
                pady=0,
            )
            row_metrics.columnconfigure(idx, weight=1, uniform="kpi")
            tk.Frame(cell, bg=theme.ACCENT_PRIMARY, height=2).pack(fill=tk.X)
            tk.Label(
                cell,
                text=caption,
                bg=theme.PAPER_BG,
                fg=theme.INK_MUTED,
                font=(self.ui_font, 7, "bold"),
                anchor="w",
                padx=8,
            ).pack(anchor="w", pady=(4, 0))
            val_lbl = tk.Label(
                cell,
                text=initial,
                bg=theme.PAPER_BG,
                fg=theme.INK_PRIMARY,
                font=(self.mono_font, 10, "bold"),
                anchor="w",
                padx=8,
            )
            val_lbl.pack(anchor="w", pady=(0, 5))
            self._kpi_cards[key] = val_lbl

        # Barra de reproducción temporal (empaquetada abajo antes del canvas expandible)
        self.player_frame = tk.Frame(
            parent,
            bg=theme.PAPER_BG,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )
        self.player_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=(0, 8))

        self.player_controls_row = tk.Frame(self.player_frame, bg=theme.PAPER_BG)
        self.player_controls_row.pack(fill=tk.X, padx=10, pady=(7, 3))

        self.btn_reset = self._make_btn(
            self.player_controls_row,
            " Inicio",
            self._player_reset,
            variant="dock_secondary",
            padx=8,
            pady=4,
            font_size=8,
            image=self._icons["reset_light"],
            compound=tk.LEFT,
        )
        self.btn_step_back = self._make_btn(
            self.player_controls_row,
            " -1",
            lambda: self._player_step(-1),
            variant="dock_secondary",
            padx=8,
            pady=4,
            font_size=8,
            image=self._icons["step_back_light"],
            compound=tk.LEFT,
        )
        self.btn_play_pause = self._make_btn(
            self.player_controls_row,
            " Reproducir",
            self.toggle_play_pause,
            variant="primary",
            padx=10,
            pady=4,
            font_size=8,
            width=self._px(102),
            image=self._icons["play_on_accent"],
            compound=tk.LEFT,
        )
        self.btn_step_fwd = self._make_btn(
            self.player_controls_row,
            " +1",
            lambda: self._player_step(1),
            variant="dock_secondary",
            padx=8,
            pady=4,
            font_size=8,
            image=self._icons["step_fwd_light"],
            compound=tk.LEFT,
        )

        self.btn_reset.pack(side=tk.LEFT, padx=(0, 3))
        self.btn_step_back.pack(side=tk.LEFT, padx=2)
        self.btn_play_pause.pack(side=tk.LEFT, padx=4)
        self.btn_step_fwd.pack(side=tk.LEFT, padx=2)

        self.lbl_speed_cap = tk.Label(
            self.player_controls_row,
            text="Velocidad",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8),
        )
        self.lbl_speed_cap.pack(side=tk.LEFT, padx=(10, 4))
        self.combo_speed = ttk.Combobox(
            self.player_controls_row,
            textvariable=self.var_speed,
            values=["1x", "2x", "5x", "10x"],
            state="readonly",
            width=4,
            style="Light.TCombobox",
        )
        self.combo_speed.pack(side=tk.LEFT)
        self.combo_speed.bind("<<ComboboxSelected>>", self._on_speed_change)

        self.lbl_mass_audit = tk.Label(
            self.player_controls_row,
            text="Balance masa: -",
            bg=theme.ACCENT_SOFT,
            fg=theme.STATUS_OK_LIGHT,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
            padx=8,
            pady=2,
            font=(self.mono_font, 8, "bold"),
        )
        self.lbl_mass_audit.pack(side=tk.RIGHT, padx=2)

        slider_row = tk.Frame(self.player_frame, bg=theme.PAPER_BG)
        slider_row.pack(fill=tk.X, padx=10, pady=(0, 7))
        self.lbl_t_start = tk.Label(
            slider_row, text="0m", bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=(self.mono_font, 7, "bold")
        )
        self.lbl_t_start.pack(side=tk.LEFT)
        self.timeline_slider = tk.Scale(
            slider_row,
            from_=0,
            to=0,
            orient=tk.HORIZONTAL,
            showvalue=False,
            command=self._on_slider_move,
            bg=theme.ACCENT_PRIMARY,
            fg=theme.ACCENT_PRIMARY,
            troughcolor=theme.DOCK_BG,
            highlightthickness=0,
            sliderrelief="flat",
            sliderlength=20,
            activebackground=theme.ACCENT_HOVER,
            bd=0,
            width=10,
        )
        self.timeline_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.lbl_t_end = tk.Label(
            slider_row, text="90m", bg=theme.PAPER_BG, fg=theme.INK_PRIMARY, font=(self.mono_font, 7, "bold")
        )
        self.lbl_t_end.pack(side=tk.RIGHT)

        self.center_panel.bind("<Configure>", self._on_center_configure)

        # Cabecera del lienzo: selector segmentado plano para Modo de Estrés / Lectura
        map_mode_bar = tk.Frame(
            parent,
            bg=theme.DOCK_BG,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )
        map_mode_bar.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(6, 0))
        self._lbl_map_mode = tk.Label(
            map_mode_bar,
            text="Lectura cartográfica:",
            bg=theme.DOCK_BG,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8, "bold"),
            padx=8,
            pady=4,
        )
        self._lbl_map_mode.pack(side=tk.LEFT)

        self._seg_wrap = tk.Frame(map_mode_bar, bg=theme.DOCK_BORDER)
        self._seg_wrap.pack(side=tk.LEFT, padx=(4, 8), pady=3)
        self._map_mode_compact: Optional[str] = None
        self._map_mode_buttons.clear()
        for idx, (mode_id, mode_lbl) in enumerate(
            [
                ("instant", "Instantáneo O(t)"),
                ("peak", "Pico Máximo"),
                ("overload_minutes", "Minutos en Sobrecarga"),
            ]
        ):
            is_act = mode_id == self._map_mode
            btn = tk.Button(
                self._seg_wrap,
                text=mode_lbl,
                command=lambda m=mode_id: self._set_map_mode(m),
                bg=theme.ACCENT_PRIMARY if is_act else theme.DOCK_BG,
                fg=theme.ACCENT_INK if is_act else theme.INK_PRIMARY,
                activebackground=theme.ACCENT_HOVER,
                activeforeground=theme.ACCENT_INK,
                relief="flat",
                bd=0,
                padx=9,
                pady=2,
                font=(self.ui_font, 8, "bold" if is_act else "normal"),
                cursor="hand2",
                highlightthickness=0,
            )
            btn.pack(side=tk.LEFT, padx=(1 if idx > 0 else 1, 1), pady=1)
            self._map_mode_buttons[mode_id] = btn

        # Lienzo interactivo del grafo sobre papel vitela (#FFFFE3)
        self.network_canvas = NetworkCanvas(
            parent,
            ui_font=self.ui_font,
            mono_font=self.mono_font,
            dpi_scale=self._dpi_scale,
            on_select_pipe=self._on_pipe_selected,
            on_select_node=self._on_node_selected,
        )
        self.network_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self._build_tour_card()

    def _on_speed_change(self, _event: tk.Event) -> None:
        if self.is_playing:
            self.network_canvas.set_playing(True, self._speed_factor())

    def _speed_factor(self) -> float:
        return {"1x": 1.0, "2x": 1.35, "5x": 1.85, "10x": 2.4}.get(self.var_speed.get(), 1.2)

    def _on_center_configure(self, event: tk.Event) -> None:
        compact = event.width < 600
        if compact != self._player_compact:
            self._player_compact = compact
            if compact:
                self.btn_reset.configure(text="", padx=6, width=self._px(26))
                self.btn_step_back.configure(text="", padx=6, width=self._px(26))
                self.btn_step_fwd.configure(text="", padx=6, width=self._px(26))
                self.lbl_speed_cap.pack_forget()
            else:
                self.btn_reset.configure(text=" Inicio", padx=8, width=0)
                self.btn_step_back.configure(text=" -1", padx=8, width=0)
                self.btn_step_fwd.configure(text=" +1", padx=8, width=0)
                if not self.lbl_speed_cap.winfo_ismapped():
                    self.lbl_speed_cap.pack(
                        side=tk.LEFT, padx=(10, 4), before=self.combo_speed
                    )
            self._update_play_button_label()
            self._update_mass_audit_label()
            self._update_clock_label()

        # Adaptación responsiva del selector segmentado de modo cartográfico
        mm_tier = "full" if event.width >= 660 else ("mid" if event.width >= 480 else "short")
        if mm_tier != getattr(self, "_map_mode_compact", None) and hasattr(self, "_lbl_map_mode"):
            self._map_mode_compact = mm_tier
            if mm_tier == "full":
                if not self._lbl_map_mode.winfo_ismapped():
                    self._lbl_map_mode.pack(side=tk.LEFT, before=self._seg_wrap)
                labels = {
                    "instant": "Instantáneo O(t)",
                    "peak": "Pico Máximo",
                    "overload_minutes": "Minutos en Sobrecarga",
                }
                padx_val = 9
            elif mm_tier == "mid":
                self._lbl_map_mode.pack_forget()
                labels = {
                    "instant": "Instantáneo O(t)",
                    "peak": "Pico Máximo",
                    "overload_minutes": "Min. Sobrecarga",
                }
                padx_val = 8
            else:
                self._lbl_map_mode.pack_forget()
                labels = {
                    "instant": "O(t)",
                    "peak": "Pico",
                    "overload_minutes": "Min >100%",
                }
                padx_val = 6
            for mid, lbl_txt in labels.items():
                if mid in self._map_mode_buttons:
                    self._map_mode_buttons[mid].configure(text=lbl_txt, padx=padx_val)

        if self._tour_active:
            self._fit_tour_card_geometry()

    def _update_play_button_label(self) -> None:
        icon = self._icons["pause_on_accent"] if self.is_playing else self._icons["play_on_accent"]
        if self._player_compact:
            self.btn_play_pause.configure(text="", image=icon, padx=6, width=self._px(32))
        else:
            self.btn_play_pause.configure(
                text=" Pausar" if self.is_playing else " Reproducir",
                image=icon,
                padx=10,
                width=self._px(102),
            )

    def _build_right_panel(self, parent: tk.Frame) -> None:
        sheet_frame = tk.Frame(
            parent,
            bg=theme.PAPER_BG,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )
        sheet_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.notebook = ttk.Notebook(sheet_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Tab 1: Inspector y Resumen + Cirugía Cartográfica (Idea 1)
        tab_info = ttk.Frame(self.notebook)
        self.notebook.add(tab_info, text="Inspector")

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
            lambda: self._trace_from_selected("up"),
            variant="light_secondary",
            padx=7,
            pady=3,
            font_size=8,
        )
        self.btn_insp_downstream = self._make_btn(
            self.inspector_actions,
            "Aguas abajo",
            lambda: self._trace_from_selected("down"),
            variant="light_secondary",
            padx=7,
            pady=3,
            font_size=8,
        )
        self._inspector_actions_sep = tk.Frame(tab_info, bg=theme.DOCK_BORDER, height=1)

        # Tarjeta compacta de intervención en vivo sobre tubería (Idea 1)
        self.pipe_intervention_card = tk.Frame(tab_info, bg=theme.PAPER_SUBTLE)
        self._pipe_intervention_sep = tk.Frame(tab_info, bg=theme.DOCK_BORDER, height=1)

        int_hdr = tk.Frame(self.pipe_intervention_card, bg=theme.PAPER_SUBTLE)
        int_hdr.pack(fill=tk.X, padx=8, pady=(6, 2))
        tk.Label(
            int_hdr,
            text="Intervención en vivo (Idea 1)",
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
            values=_COMMERCIAL_DIAMETERS_IN,
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

        # Sección de Trazabilidad por Fuente Aportante (barra apilada monocromática)
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

        # Tab 2: Tuberías Críticas
        tab_crit = ttk.Frame(self.notebook)
        self.notebook.add(tab_crit, text="Tuberías Críticas")

        filter_bar = tk.Frame(tab_crit, bg=theme.PAPER_SUBTLE)
        filter_bar.pack(fill=tk.X)
        tk.Frame(tab_crit, bg=theme.DOCK_BORDER, height=1).pack(fill=tk.X)
        for text, val in [
            ("Todas", "all"),
            ("Críticas (≥75%)", "critical"),
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

        # Tab 3: Evolución Temporal (Hidrograma Antes vs. Después + Perfil Longitudinal)
        tab_charts = ttk.Frame(self.notebook)
        self.notebook.add(tab_charts, text="Evolución")
        self.temporal_charts = TemporalChartsPanel(
            tab_charts,
            dpi=self._mpl_dpi,
            ui_font=self.ui_font,
            mono_font=self.mono_font,
        )
        self.temporal_charts.pack(fill=tk.BOTH, expand=True)

        # Tab 4: Comparación de Escenarios
        tab_comp = ttk.Frame(self.notebook)
        self.notebook.add(tab_comp, text="Comparación")

        comp_top = tk.Frame(tab_comp, bg=theme.PAPER_SUBTLE)
        comp_top.pack(fill=tk.X)
        tk.Frame(tab_comp, bg=theme.DOCK_BORDER, height=1).pack(fill=tk.X)
        self._make_btn(
            comp_top,
            "Comparar 5 Escenarios",
            self._action_compare_scenarios,
            variant="primary",
            padx=10,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, padx=8, pady=6)
        self.lbl_comp_hint = tk.Label(
            comp_top,
            text="Doble clic para activar escenario",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_MUTED,
            font=(self.ui_font, 8),
        )
        self.lbl_comp_hint.pack(side=tk.RIGHT, padx=8)

        comp_cols = ("esc", "int", "max_u", "crit_p", "n_crit", "n_over", "ptar")
        self._comp_tree_compact: Optional[bool] = None
        self.tree_comp = ttk.Treeview(tab_comp, columns=comp_cols, show="headings", height=5)
        self.tree_comp.tag_configure("odd", background=theme.PAPER_ALT_ROW)
        for cid, htext in [
            ("esc", "Escenario"),
            ("int", "mm/h"),
            ("max_u", "Máx %"),
            ("crit_p", "Crítica"),
            ("n_crit", "≥75%"),
            ("n_over", ">100%"),
            ("ptar", "Pico PTAR"),
        ]:
            self.tree_comp.heading(cid, text=htext)
            self.tree_comp.column(cid, width=54, minwidth=30, anchor="center")
        self.tree_comp.pack(fill=tk.X, padx=6, pady=(4, 4))
        self.tree_comp.bind("<Double-1>", self._on_comparison_row_activate)
        self.tree_comp.bind("<Configure>", self._resize_comp_columns)

        self.comparison_charts = ComparisonChartsPanel(tab_comp, dpi=self._mpl_dpi)
        self.comparison_charts.pack(fill=tk.BOTH, expand=True)

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
                ("rank", 0.07, 22),
                ("pipe", 0.11, 34),
                ("tramo", 0.16, 48),
                ("q_curr", 0.15, 45),
                ("q_max", 0.15, 45),
                ("util", 0.17, 48),
                ("estado", 0.19, 54),
            ]
        else:
            weights = [
                ("rank", 0.07, 26),
                ("pipe", 0.11, 40),
                ("tramo", 0.15, 52),
                ("q_curr", 0.17, 56),
                ("q_max", 0.16, 54),
                ("util", 0.13, 46),
                ("estado", 0.21, 70),
            ]
        for cid, ratio, min_w in weights:
            self.tree_critical.column(cid, width=max(min_w, int(w * ratio)))

    def _resize_comp_columns(self, event: tk.Event) -> None:
        w = max(220, event.width - 4)
        compact = w < 385
        if compact != self._comp_tree_compact:
            self._comp_tree_compact = compact
            if compact:
                self.tree_comp["displaycolumns"] = ("esc", "int", "max_u", "crit_p", "n_over", "ptar")
                for cid, htext in [
                    ("esc", "Esc."),
                    ("int", "mm"),
                    ("max_u", "Máx %"),
                    ("crit_p", "Crít."),
                    ("n_over", ">100"),
                    ("ptar", "PTAR"),
                ]:
                    self.tree_comp.heading(cid, text=htext)
            else:
                self.tree_comp["displaycolumns"] = "#all"
                for cid, htext in [
                    ("esc", "Escenario"),
                    ("int", "mm/h"),
                    ("max_u", "Máx %"),
                    ("crit_p", "Crítica"),
                    ("n_crit", "≥75%"),
                    ("n_over", ">100%"),
                    ("ptar", "Pico PTAR"),
                ]:
                    self.tree_comp.heading(cid, text=htext)
            if self.comparisons:
                self._populate_comp_tree()

        if compact:
            weights = [
                ("esc", 0.22, 60),
                ("int", 0.11, 30),
                ("max_u", 0.19, 52),
                ("crit_p", 0.13, 38),
                ("n_over", 0.15, 42),
                ("ptar", 0.20, 56),
            ]
        else:
            weights = [
                ("esc", 0.27, 82),
                ("int", 0.10, 36),
                ("max_u", 0.14, 46),
                ("crit_p", 0.12, 42),
                ("n_crit", 0.11, 38),
                ("n_over", 0.11, 40),
                ("ptar", 0.15, 52),
            ]
        for cid, ratio, min_w in weights:
            self.tree_comp.column(cid, width=max(min_w, int(w * ratio)))

    def _on_right_configure(self, event: tk.Event) -> None:
        if not hasattr(self, "notebook"):
            return
        compact = event.width < 395
        if compact != self._right_tabs_compact:
            self._right_tabs_compact = compact
            style = ttk.Style(self)
            if compact:
                style.configure("TNotebook.Tab", padding=(5, 6), font=(self.ui_font, 8))
                self.notebook.tab(0, text="Inspector")
                self.notebook.tab(1, text="Críticas")
                self.notebook.tab(2, text="Evolución")
                self.notebook.tab(3, text="Comparar")
            else:
                style.configure("TNotebook.Tab", padding=(10, 7), font=(self.ui_font, 9, "bold"))
                self.notebook.tab(0, text="Inspector")
                self.notebook.tab(1, text="Tuberías Críticas")
                self.notebook.tab(2, text="Evolución")
                self.notebook.tab(3, text="Comparación")

        if hasattr(self, "lbl_comp_hint"):
            if event.width < 365:
                self.lbl_comp_hint.pack_forget()
            else:
                self.lbl_comp_hint.configure(text="Doble clic para activar escenario")
                if not self.lbl_comp_hint.winfo_ismapped():
                    self.lbl_comp_hint.pack(side=tk.RIGHT, padx=4)

    def _on_tab_changed(self, _event: tk.Event) -> None:
        if self.dataset is None:
            return
        try:
            idx = self.notebook.index(self.notebook.select())
        except tk.TclError:
            return
        if idx == 0 and self._insp_tab_dirty:
            self._insp_tab_dirty = False
            self._refresh_inspector()
        elif idx == 1 and self._crit_tab_dirty:
            self._crit_tab_dirty = False
            self._refresh_critical_table()
        elif idx == 2 and self._charts_tab_dirty and self.result is not None:
            self._charts_tab_dirty = False
            snap = self.result.snapshots[self.current_step]
            self.temporal_charts.update_plots(
                self.result,
                self._selected_pipe_id,
                snap.time_min,
                previous_result=self._previous_result,
                route_pipes=self._resolve_active_route(),
                current_step_index=self.current_step,
                diameter_overrides=self._diameter_overrides_map(),
                throttle_draw=False,
            )
        elif idx == 3 and (not self.comparisons or self._comparisons_dirty):
            self._action_compare_scenarios()

    def _mark_comparisons_dirty(self) -> None:
        self._comparisons_dirty = True
        if hasattr(self, "lbl_comp_hint") and self.comparisons:
            self.lbl_comp_hint.configure(
                text="Parámetros modificados · Recalcular", fg=theme.STATUS_WARN_LIGHT
            )

    # --- Lógica de archivos, intervenciones y simulación ---

    def _apply_preset(self, ingress_pct: float, dry_flow: float) -> None:
        self.var_ingress_pct.set(ingress_pct)
        self.var_dry_flow.set(dry_flow)
        self.run_simulation()

    def _toggle_labels(self) -> None:
        self.network_canvas.show_pipe_labels = self.var_show_pipe_labels.get()
        self.network_canvas.show_util_labels = self.var_show_util_labels.get()
        self.network_canvas.redraw()

    def _load_path(self, path: str, silent_error: bool = False) -> None:
        try:
            dataset = load_dataset(path)
        except DataLoadError as exc:
            if not silent_error:
                messagebox.showerror("Error de validación de datos", str(exc))
            self.status_var.set(f"Error al cargar: {exc}")
            return
        except Exception as exc:
            if not silent_error:
                messagebox.showerror("Error inesperado", str(exc))
            self.status_var.set(f"Error inesperado: {exc}")
            return

        self._player_pause()
        self._stop_traversal_anim(clear_canvas=False)
        self._close_guided_tour()
        self.dataset = dataset
        self.engine = SewerSimulationEngine(dataset.graph, dataset.basin)
        self.result = None
        self._previous_result = None
        self.comparisons = []
        self._comparisons_dirty = True
        self._selected_pipe_id = None
        self._selected_node_id = None
        self._interventions.clear()
        self._isolated_nodes.clear()
        self._isolated_pipes.clear()
        self._basin_isolated = False
        self._active_route_pipes = []

        self.network_canvas.set_graph(dataset.graph)

        scen_labels = []
        self._scenario_display_map.clear()
        for s in dataset.scenarios:
            es_lbl = theme.format_scenario_display(s.scenario_id, s.condition, s.intensity_mm_h)
            scen_labels.append(es_lbl)
            self._scenario_display_map[es_lbl] = s
            self._scenario_display_map[s.display_name] = s
        self.combo_scenario["values"] = scen_labels
        if len(scen_labels) >= 3:
            self.var_scenario.set(scen_labels[2])
        elif scen_labels:
            self.var_scenario.set(scen_labels[0])

        nids = dataset.graph.node_ids()
        self.combo_bfs_start["values"] = nids
        self.combo_bfs_target["values"] = nids
        srcs = dataset.graph.source_ids()
        snks = dataset.graph.sink_ids()
        if srcs:
            self.var_bfs_start.set(srcs[0])
        if snks:
            self.var_bfs_target.set(snks[0])

        n_nodes, n_pipes, _n_src, _n_snk, total_len = dataset.graph.summary()
        self._dataset_summary_text = (
            f"{n_nodes} nodos · {n_pipes} tuberías · {total_len:,.1f} m ({os.path.basename(path)})"
        )
        self.status_var.set(f"Red cargada: {self._dataset_summary_text}")
        self._render_structure_strip("Queue", [])
        self._refresh_inspector()

    def _action_load_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar archivo Excel de la red",
            filetypes=[("Archivos Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
        )
        if path:
            self._load_path(path)
            if self.dataset is not None:
                self.run_simulation()

    def _action_load_csv(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta con archivos CSV")
        if path:
            self._load_path(path)
            if self.dataset is not None:
                self.run_simulation()

    def _action_export_csv(self) -> None:
        if self.dataset is None:
            messagebox.showwarning("Sin datos", "Primero cargue un conjunto de datos.")
            return
        out_dir = filedialog.askdirectory(title="Seleccionar carpeta destino para CSV")
        if out_dir:
            export_to_csv_dir(self.dataset, out_dir)
            messagebox.showinfo("Exportación completada", f"Archivos CSV exportados en:\n{out_dir}")

    def _action_generate_report(self) -> None:
        if self.dataset is None or self.result is None:
            messagebox.showwarning("Sin simulación", "Ejecute primero una simulación.")
            return
        out_file = filedialog.asksaveasfilename(
            title="Guardar reporte de simulación",
            defaultextension=".docx",
            initialfile=f"reporte_escenario_{self.result.config.scenario_id}.docx",
            filetypes=[
                ("Documento Word (2 columnas)", "*.docx"),
                ("Markdown + CSV", "*.md"),
            ],
        )
        if not out_file:
            return
        comps = self.comparisons or compare_all_scenarios(self.dataset, self.result.config)
        self.comparisons = comps
        self._comparisons_dirty = False
        if out_file.lower().endswith(".docx"):
            try:
                written = generate_docx_report(self.dataset, self.result, comps, out_file)
                messagebox.showinfo(
                    "Reporte Word generado",
                    f"Documento .docx a dos columnas (OMML 8.5 pt) generado en:\n{written}",
                )
                return
            except Exception as exc:
                fallback = os.path.splitext(out_file)[0] + ".md"
                written = generate_markdown_report(self.dataset, self.result, comps, fallback)
                messagebox.showwarning(
                    "Respaldo Markdown generado",
                    f"No se pudo generar .docx ({exc}).\nSe exportó respaldo Markdown/CSV en:\n{written}",
                )
                return

        written = generate_markdown_report(self.dataset, self.result, comps, out_file)
        messagebox.showinfo("Reporte generado", f"Reporte y tabla CSV generados en:\n{written}")

    def _action_show_assumptions(self) -> None:
        msg = (
            "Supuestos del Modelo Computacional (Ciudad Bicentenario):\n\n"
            "1. Grafo Dirigido Propio: 46 vértices (8 fuentes, 37 pozos, 1 sumidero PTAR 31) y 59 aristas.\n"
            "2. Método Racional: Q = 0.00278 · C · I(t) · A · f_ingreso + Q_sanitario.\n"
            "3. Tiempo de Tránsito: t_i = L_i / V_i, con V_i = Q_max,i / A_i (Manning).\n"
            "4. Distribución en Bifurcaciones: Proporcional a Q_max (o uniforme seleccionable).\n"
            "5. Sobrecarga (>100%): Almacenamiento temporal en el pozo aguas arriba sin pérdida de masa."
        )
        messagebox.showinfo("Supuestos del Modelo", msg)

    def _selected_scenario_obj(self):
        assert self.dataset is not None
        selected = self.var_scenario.get()
        if selected in self._scenario_display_map:
            return self._scenario_display_map[selected]
        for sc in self.dataset.scenarios:
            if sc.display_name == selected:
                return sc
        return self.dataset.scenarios[0]

    def _build_sim_config(self) -> SimulationConfig:
        sc = self._selected_scenario_obj()
        duration = float(self.var_duration.get())
        storm_dur = float(self.var_storm_dur.get())
        dt = float(self.var_dt.get())
        ingress = float(self.var_ingress_pct.get())
        dry_flow = float(self.var_dry_flow.get())
        for val, label in (
            (duration, "Duración simulación"),
            (storm_dur, "Duración lluvia"),
            (dt, "Paso temporal Δt"),
            (ingress, "Ingreso pluvial (%)"),
            (dry_flow, "Caudal sanitario"),
        ):
            if not math.isfinite(val):
                raise ValueError(f"{label} debe ser un número finito.")
        return SimulationConfig(
            scenario_id=sc.scenario_id,
            scenario_name=sc.condition,
            intensity_mm_h=sc.intensity_mm_h,
            duration_min=max(5.0, duration),
            storm_duration_min=max(0.0, storm_dur),
            dt_min=max(0.25, dt),
            ingress_factor=max(0.001, min(1.0, ingress / 100.0)),
            dry_weather_flow_per_source_m3s=max(0.0, dry_flow),
            split_rule=self.var_split_rule.get(),
            hyetograph=self.var_hyetograph.get(),
            interventions=dict(self._interventions),
        )

    def _schedule_param_rerun(self) -> None:
        if self._param_rerun_after is not None:
            try:
                self.after_cancel(self._param_rerun_after)
            except tk.TclError:
                pass
        self._param_rerun_after = self.after(140, self._run_param_rerun)

    def _run_param_rerun(self) -> None:
        self._param_rerun_after = None
        if self.dataset is None or self.engine is None:
            return
        self._on_simulation_option_changed(mark_comp=True)

    def _on_simulation_option_changed(self, mark_comp: bool = True) -> None:
        if mark_comp:
            self._mark_comparisons_dirty()
        self.run_simulation(preserve_previous=False)

    def run_simulation(self, preserve_previous: bool = False) -> None:
        if self.dataset is None or self.engine is None:
            return
        self._player_pause()
        try:
            cfg = self._build_sim_config()
        except Exception as exc:
            messagebox.showerror("Parámetros inválidos", f"Revise los parámetros numéricos: {exc}")
            return

        if preserve_previous and self.result is not None:
            self._previous_result = self.result
        elif not preserve_previous and self.result is not None and self._interventions:
            self._previous_result = self.result
        else:
            self._previous_result = None

        self.result = self.engine.run(cfg)
        self._last_attr_key = None
        n_snaps = len(self.result.snapshots)
        self.network_canvas.set_map_mode(
            self._map_mode,
            peak_util=self.result.peak_pipe_utilization,
            overload_minutes=self.result.pipe_overloaded_minutes,
            total_duration_min=cfg.duration_min,
        )
        self._updating_slider = True
        try:
            self.timeline_slider.configure(command="", to=max(0, n_snaps - 1))
        finally:
            if not self._slider_restore_pending:
                self._slider_restore_pending = True
                self.after_idle(self._restore_slider_command)
        self.lbl_t_end.configure(text=f"{cfg.duration_min:.0f}m")

        # Iniciar siempre en el minuto 0 (comienzo de la simulación)
        self._set_step(0)
        if self._tour_active:
            self._go_tour_stop(self._tour_step, animate_cam=False)
        self.status_var.set(
            f"{self._dataset_summary_text}  ·  Escenario {cfg.scenario_id} ({cfg.intensity_mm_h:.0f} mm/h) "
            f"en {self.result.execution_time_ms:.1f} ms ({n_snaps} instantes)"
        )

    def _resolve_active_route(self) -> List[PipeEdge]:
        if self.dataset is None:
            return []
        g = self.dataset.graph
        if self._active_route_pipes:
            return list(self._active_route_pipes)
        if self._selected_pipe_id and g.has_pipe(self._selected_pipe_id):
            return build_route_to_sink(g, pipe_id=self._selected_pipe_id, sink_id="31")
        if self._selected_node_id and g.has_node(self._selected_node_id):
            return build_route_to_sink(g, node_id=self._selected_node_id, sink_id="31")
        if g.has_pipe("P31"):
            return build_route_to_sink(g, pipe_id="P31", sink_id="31")
        srcs = g.source_ids()
        if srcs:
            return build_route_to_sink(g, node_id=srcs[0], sink_id="31")
        return []

    def _diameter_overrides_map(self) -> Dict[str, float]:
        return {
            pid: inv.diameter_in_override
            for pid, inv in self._interventions.items()
            if inv.diameter_in_override is not None
        }

    def _restore_slider_command(self) -> None:
        self._slider_restore_pending = False
        try:
            if self.timeline_slider.winfo_exists():
                self.timeline_slider.configure(command=self._on_slider_move)
        except tk.TclError:
            pass
        self._updating_slider = False

    def _active_right_tab(self) -> int:
        try:
            return int(self.notebook.index(self.notebook.select()))
        except tk.TclError:
            return 0

    def _set_step(self, step_idx: int) -> None:
        if self.result is None or not self.result.snapshots:
            return
        step_idx = max(0, min(len(self.result.snapshots) - 1, step_idx))
        self.current_step = step_idx
        snap = self.result.snapshots[step_idx]

        self._updating_slider = True
        self.timeline_slider.configure(command="")
        self.timeline_slider.set(step_idx)
        if not self._slider_restore_pending:
            self._slider_restore_pending = True
            self.after_idle(self._restore_slider_command)

        self.network_canvas.set_snapshot(snap)
        self._update_clock_label(snap)

        max_u = max((ps.utilization_pct for ps in snap.pipe_states.values()), default=0.0)
        tier_idx = 0 if max_u <= 25 else (1 if max_u <= 50 else (2 if max_u <= 75 else (3 if max_u <= 100 else 4)))
        self._kpi_cards["max_util"].configure(
            text=f"{max_u:.1f}%", fg=theme.TIER_TEXT_ON_LIGHT[tier_idx]
        )
        self._kpi_cards["critical"].configure(
            text=str(len(snap.critical_pipe_ids)),
            fg=theme.STATUS_ERR_LIGHT if snap.critical_pipe_ids else theme.INK_PRIMARY,
        )
        self._kpi_cards["overloaded"].configure(
            text=str(len(snap.overloaded_pipe_ids)),
            fg=theme.TIER_TEXT_ON_LIGHT[4] if snap.overloaded_pipe_ids else theme.INK_PRIMARY,
        )
        self._kpi_cards["ptar"].configure(
            text=f"{snap.total_sink_discharge_m3s:.4f} m³/s", fg=theme.ACCENT_TEXT_ON_LIGHT
        )

        self._update_mass_audit_label(snap)
        self._update_legend_counts(snap)

        active_tab = self._active_right_tab()
        if active_tab == 1:
            self._crit_tab_dirty = False
            self._refresh_critical_table()
        else:
            self._crit_tab_dirty = True

        if active_tab == 0 or not self.is_playing:
            self._insp_tab_dirty = False
            self._refresh_inspector()
        else:
            self._insp_tab_dirty = True

        if active_tab == 2:
            self._charts_tab_dirty = False
            self.temporal_charts.update_plots(
                self.result,
                self._selected_pipe_id,
                snap.time_min,
                previous_result=self._previous_result,
                route_pipes=self._resolve_active_route(),
                current_step_index=step_idx,
                diameter_overrides=self._diameter_overrides_map(),
                throttle_draw=self.is_playing,
            )
        else:
            self._charts_tab_dirty = True

    def _update_clock_label(self, snap: Optional[TimeStepSnapshot] = None) -> None:
        if self.result is None or not self.result.snapshots:
            return
        if snap is None:
            snap = self.result.snapshots[self.current_step]
        cfg = self.result.config
        scen_es = theme.translate_scenario_name(
            cfg.scenario_name, compact=bool(self._player_compact)
        )
        if self._player_compact:
            self.lbl_clock.configure(
                text=f"t={snap.time_min:.0f}/{cfg.duration_min:.0f}m · {scen_es} ({snap.rain_intensity_mm_h:.0f} mm/h)"
            )
        else:
            self.lbl_clock.configure(
                text=(
                    f"t = {snap.time_min:.1f} / {cfg.duration_min:.0f} min  ·  "
                    f"{scen_es} ({snap.rain_intensity_mm_h:.0f} mm/h)"
                )
            )

    def _update_mass_audit_label(self, snap: Optional[TimeStepSnapshot] = None) -> None:
        if snap is None and self.result and self.result.snapshots:
            snap = self.result.snapshots[self.current_step]
        if snap is None:
            self.lbl_mass_audit.configure(text="Balance masa: -")
            return
        if self._player_compact:
            self.lbl_mass_audit.configure(text=f"Masa OK · {snap.mass_balance_error_m3:.1e}")
        else:
            self.lbl_mass_audit.configure(
                text=f"Balance masa OK · Err {snap.mass_balance_error_m3:.2e} m³"
            )

    def _set_map_mode(self, mode: str) -> None:
        if mode not in ("instant", "peak", "overload_minutes"):
            return
        self._map_mode = mode
        for mid, btn in self._map_mode_buttons.items():
            is_act = mid == mode
            btn.configure(
                bg=theme.ACCENT_PRIMARY if is_act else theme.DOCK_BG,
                fg=theme.ACCENT_INK if is_act else theme.INK_PRIMARY,
                font=(self.ui_font, 8, "bold" if is_act else "normal"),
            )
        if self.result is not None:
            self.network_canvas.set_map_mode(
                mode,
                peak_util=self.result.peak_pipe_utilization,
                overload_minutes=self.result.pipe_overloaded_minutes,
                total_duration_min=self.result.config.duration_min,
            )
            self._update_legend_counts(self.result.snapshots[self.current_step])
        else:
            self.network_canvas.set_map_mode(mode)

    def _update_legend_counts(self, snap: TimeStepSnapshot) -> None:
        counts = [0, 0, 0, 0, 0]
        if self._map_mode == "overload_minutes" and self.result is not None:
            if self._legend_header_label is not None:
                self._legend_header_label.configure(text="Tiempo acumulado en sobrecarga")
            for idx, (rng, _col, desc) in enumerate(OVERLOAD_PERSISTENCE_LEVELS):
                if idx < len(self._legend_text_labels):
                    self._legend_text_labels[idx].configure(text=f"{rng} · {desc}")
            dur = max(1.0, float(self.result.config.duration_min))
            for pid in snap.pipe_states:
                ov_m = self.result.pipe_overloaded_minutes.get(pid, 0.0)
                tier, _, _ = classify_overload_persistence(ov_m, dur)
                counts[tier] += 1
        else:
            if self._legend_header_label is not None:
                title = (
                    "Escala oficial de utilización"
                    if self._map_mode == "instant"
                    else "Escala oficial · Pico máximo"
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
                    u = self.result.peak_pipe_utilization.get(pid, 0.0)
                    counts[classify_utilization(u).tier_index] += 1
            else:
                for ps in snap.pipe_states.values():
                    counts[ps.category.tier_index] += 1
        for lbl, c in zip(self._legend_count_labels, counts):
            lbl.configure(text=str(c))

    def _on_slider_move(self, val: str) -> None:
        step = int(float(val))
        if self._updating_slider or step == self.current_step:
            return
        self._player_pause()
        self._set_step(step)

    def toggle_play_pause(self) -> None:
        if self.is_playing:
            self._player_pause()
        else:
            self._player_play()

    def _player_play(self) -> None:
        if self.result is None:
            return
        self._stop_traversal_anim(clear_canvas=False)
        if self.current_step >= len(self.result.snapshots) - 1:
            self._set_step(0)
        self.is_playing = True
        self._update_play_button_label()
        self.network_canvas.set_playing(True, self._speed_factor())
        self._schedule_next_frame()

    def _player_pause(self) -> None:
        self.is_playing = False
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if hasattr(self, "network_canvas"):
            self.network_canvas.set_playing(False)
        if hasattr(self, "btn_play_pause"):
            self._update_play_button_label()

    def _player_reset(self) -> None:
        self._player_pause()
        self._set_step(0)

    def _player_step(self, delta: int) -> None:
        self._player_pause()
        self._set_step(self.current_step + delta)

    def _schedule_next_frame(self) -> None:
        if not self.is_playing or self.result is None:
            return
        if self.current_step >= len(self.result.snapshots) - 1:
            self._player_pause()
            return
        self._set_step(self.current_step + 1)
        speed_map = {"1x": 420, "2x": 210, "5x": 85, "10x": 40}
        delay = speed_map.get(self.var_speed.get(), 200)
        self._after_id = self.after(delay, self._schedule_next_frame)

    def _on_pipe_selected(self, pipe_id: str) -> None:
        self._selected_pipe_id = pipe_id
        self._selected_node_id = None
        self._sync_intervention_controls()
        if self._basin_isolated:
            self._apply_basin_isolation()
        self._refresh_inspector()
        if self.result is not None:
            snap = self.result.snapshots[self.current_step]
            self.temporal_charts.update_plots(
                self.result,
                pipe_id,
                snap.time_min,
                previous_result=self._previous_result,
                route_pipes=self._resolve_active_route(),
                current_step_index=self.current_step,
                diameter_overrides=self._diameter_overrides_map(),
            )

    def _on_node_selected(self, node_id: str) -> None:
        self._selected_node_id = node_id
        self._selected_pipe_id = None
        self.var_bfs_start.set(node_id)
        if self._basin_isolated:
            self._apply_basin_isolation()
        self._refresh_inspector()
        if self.result is not None:
            snap = self.result.snapshots[self.current_step]
            self.temporal_charts.update_plots(
                self.result,
                None,
                snap.time_min,
                previous_result=self._previous_result,
                route_pipes=self._resolve_active_route(),
                current_step_index=self.current_step,
                diameter_overrides=self._diameter_overrides_map(),
            )

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
        self.combo_diam_override.configure(values=[orig_label] + _COMMERCIAL_DIAMETERS_IN[1:])
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

    def _trace_from_selected(self, direction: str) -> None:
        if self._selected_node_id:
            self.var_bfs_start.set(self._selected_node_id)
            self._run_trace(direction)

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

        self._stop_traversal_anim(clear_canvas=False)
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
        self._stop_traversal_anim(clear_canvas=True)
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
            snap = self.result.snapshots[self.current_step]
            self.temporal_charts.update_plots(
                self.result,
                self._selected_pipe_id,
                snap.time_min,
                previous_result=self._previous_result,
                route_pipes=self._resolve_active_route(),
                current_step_index=self.current_step,
                diameter_overrides=self._diameter_overrides_map(),
            )

    def _action_toggle_traversal_anim(self) -> None:
        if self.dataset is None:
            return
        if self._is_animating_traversal:
            self._stop_traversal_anim(clear_canvas=False)
            return

        self._player_pause()
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

    def _clear_highlights(self) -> None:
        self._stop_traversal_anim(clear_canvas=True)
        self._active_route_pipes = []
        self._basin_isolated = False
        self.network_canvas.set_basin_focus(None, None)
        self.network_canvas.set_highlights(set(), set())
        self._render_structure_strip("Queue", [])
        self._set_traversal_text("")
        self._refresh_inspector()

    def _set_traversal_text(self, text: str) -> None:
        self.txt_traversal.configure(state=tk.NORMAL)
        self.txt_traversal.delete("1.0", tk.END)
        self.txt_traversal.insert("1.0", text)
        self.txt_traversal.configure(state=tk.DISABLED)

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
            qmax_overrides = {
                pid: ps.effective_q_max_m3s
                for pid, ps in snap.pipe_states.items()
                if ps.effective_q_max_m3s is not None
            }

            flt = self.var_crit_filter.get()
            min_u = 75.0 if flt == "critical" else (100.0001 if flt == "overloaded" else 0.0)
            ranked = rank_critical_pipes(
                self.dataset.graph,
                flows,
                utils,
                min_utilization_pct=min_u,
                pipe_qmax_overrides=qmax_overrides,
            )
            self.lbl_crit_count.configure(text=f"{len(ranked)} reg.")

            short_estado = {
                "Baja utilización": "Baja",
                "Utilización moderada": "Moderada",
                "Utilización alta": "Alta",
                "Cercana a la capacidad máxima": "Cercana",
                "Capacidad excedida": "Excedida",
            }
            compact = bool(self._crit_tree_compact)
            desired_ids = [rec.pipe_id for rec in ranked]
            existing_ids = list(self.tree_critical.get_children())

            if existing_ids == desired_ids:
                for idx, rec in enumerate(ranked):
                    estado_txt = (
                        short_estado.get(rec.category.label, rec.category.label)
                        if compact
                        else rec.category.label
                    )
                    self.tree_critical.item(
                        rec.pipe_id,
                        tags=("odd",) if idx % 2 == 1 else (),
                        values=(
                            rec.rank,
                            rec.pipe_id,
                            f"{rec.from_node}→{rec.to_node}",
                            f"{rec.flow_m3s:.4f}",
                            f"{rec.q_max_m3s:.4f}",
                            f"{rec.utilization_pct:.1f}%",
                            estado_txt,
                        ),
                    )
            else:
                for item in existing_ids:
                    self.tree_critical.delete(item)
                for idx, rec in enumerate(ranked):
                    estado_txt = (
                        short_estado.get(rec.category.label, rec.category.label)
                        if compact
                        else rec.category.label
                    )
                    self.tree_critical.insert(
                        "",
                        tk.END,
                        iid=rec.pipe_id,
                        tags=("odd",) if idx % 2 == 1 else (),
                        values=(
                            rec.rank,
                            rec.pipe_id,
                            f"{rec.from_node}→{rec.to_node}",
                            f"{rec.flow_m3s:.4f}",
                            f"{rec.q_max_m3s:.4f}",
                            f"{rec.utilization_pct:.1f}%",
                            estado_txt,
                        ),
                    )

            if not ranked:
                msg = (
                    "Ninguna tubería supera el 100% en este instante."
                    if flt == "overloaded"
                    else "Ninguna tubería alcanza ≥75% en este instante."
                )
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

            if sel_kind == "pipe":
                if n_int > 0:
                    if not self.btn_restore_all.winfo_manager():
                        self.btn_restore_all.pack(side=tk.RIGHT)
                else:
                    if self.btn_restore_all.winfo_manager():
                        self.btn_restore_all.pack_forget()
            elif prev_has_int and self.btn_restore_all.winfo_manager():
                self.btn_restore_all.pack_forget()

        if sel_kind == "pipe":
            self.lbl_active_interventions.configure(
                text=f"{n_int} activa(s)" if n_int else ""
            )

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
                    add_line(f"Caudal Q(t)     : {ps.flow_m3s:.5f} m³/s")
                    add_line(f"Conducción real : {ps.conveyed_flow_m3s:.5f} m³/s")
                    add_line(f"Vol. tránsito   : {ps.volume_in_transit_m3:.2f} m³")
                    add_line(
                        f"Utilización (%) : {ps.utilization_pct:.2f} %",
                        "alert" if ps.utilization_pct > 100.0 else None,
                    )
                    add_line(f"Clasificación   : {ps.category.label}")
                    add_line(f"Exceso sobrec.  : {ps.excess_flow_m3s:.5f} m³/s")
                if self.result:
                    add_line(
                        f"Utilización pico: {self.result.peak_pipe_utilization.get(p.pipe_id, 0.0):.2f} %"
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
                    add_line("")
                    add_line(f"Estado en t = {snap.time_min:.1f} min", "section")
                    add_line(f"Caudal entrada  : {ns.inflow_m3s:.5f} m³/s")
                    add_line(f"Caudal salida   : {ns.outflow_m3s:.5f} m³/s")
                    add_line(
                        f"Vol. almacenado : {ns.stored_volume_m3:.3f} m³",
                        "alert" if ns.stored_volume_m3 > 1e-3 else None,
                    )
            else:
                add_line("Seleccione una tubería o pozo del grafo para inspeccionarlo.", "muted")

            add_line("")
            add_line("RESUMEN DEL ESCENARIO", "section")
            add_line("─" * 40, "muted")
            if self.result and snap:
                cfg = self.result.config
                scen_es = theme.translate_scenario_name(cfg.scenario_name)
                add_line(f"Escenario       : {cfg.scenario_id} — {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)")
                add_line(f"Cuenca          : C={self.dataset.basin.runoff_coefficient_c}, A={self.dataset.basin.area_ha} ha")
                add_line(f"Factor ingreso  : {cfg.ingress_factor*100:.1f}%  |  Q_san={cfg.dry_weather_flow_per_source_m3s:.4f} m³/s")
                add_line(f"Entrada acum.   : {snap.cumulative_inflow_m3:,.2f} m³")
                add_line(f"Descarga PTAR 31: {snap.cumulative_sink_discharge_m3:,.2f} m³ (pico {self.result.peak_sink_discharge_m3s:.4f} m³/s)")
                add_line(f"Pozos / Tránsito: {snap.total_manhole_storage_m3:,.2f} / {snap.total_pipe_transit_m3:,.2f} m³")
                add_line(f"Error balance   : {self.result.max_mass_balance_error_m3:.3e} m³")
                add_line(f"Críticas (≥75%) : {len(self.result.ever_critical_pipes)} tuberías")
                add_line(f"Sobrec. (>100%) : {len(self.result.ever_overloaded_pipes)} tuberías")
                if self._interventions:
                    add_line(
                        f"Intervenciones  : {', '.join(sorted(self._interventions))} ({len(self._isolated_nodes)} aislados)",
                        "alert" if self._isolated_nodes else "section",
                    )

        self.txt_inspector.configure(state=tk.DISABLED)

    def _populate_comp_tree(self) -> None:
        for item in self.tree_comp.get_children():
            self.tree_comp.delete(item)
        compact = bool(self._comp_tree_compact)
        for idx, s in enumerate(self.comparisons):
            cond = theme.translate_scenario_name(s.condition, compact=compact)
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
                    s.num_critical_pipes,
                    s.num_overloaded_pipes,
                    f"{s.peak_sink_discharge_m3s:.4f}",
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

        self.comparisons = compare_all_scenarios(self.dataset, cfg)
        self._comparisons_dirty = False
        self.lbl_comp_hint.configure(
            text="Doble clic para activar escenario", fg=theme.INK_MUTED
        )

        self._populate_comp_tree()
        self.comparison_charts.update_comparison(self.comparisons)
        self.status_var.set("Comparación de los 5 escenarios completada.")

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
        entity_kind = "pipe" if self._selected_pipe_id else "node"
        entity_id = self._selected_pipe_id or self._selected_node_id or ""
        attr_key = (
            id(g),
            id(snap),
            split_rule,
            entity_kind,
            entity_id,
            tuple(sorted(self._interventions.items(), key=lambda kv: kv[0])),
        )
        if attr_key == self._last_attr_key:
            return
        self._last_attr_key = attr_key

        attr = compute_source_attribution(
            g, snapshot=snap, split_rule=split_rule, pipe_qmax_overrides=qmax_over
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

        # Paleta estrictamente monocromática (grafito, azul pizarra y plata mineral)
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

    def _build_tour_card(self) -> None:
        """Crea la ficha técnica flotante de la Guía de Sustentación sobre la esquina inferior izquierda."""
        self._tour_card = tk.Frame(
            self.network_canvas,
            bg=theme.PAPER_BG,
            highlightthickness=1,
            highlightbackground=theme.DOCK_BORDER,
        )

        hdr = tk.Frame(self._tour_card, bg=theme.ACCENT_PRIMARY)
        hdr.pack(fill=tk.X)
        self._lbl_tour_hdr = tk.Label(
            hdr,
            text="HALLAZGO 1 / 4 · MIN 5",
            bg=theme.ACCENT_PRIMARY,
            fg=theme.ACCENT_INK,
            font=(self.mono_font, 8, "bold"),
            padx=9,
            pady=4,
            anchor="w",
        )
        self._lbl_tour_hdr.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btn_x = tk.Button(
            hdr,
            text="×",
            command=self._close_guided_tour,
            bg=theme.ACCENT_PRIMARY,
            fg=theme.ACCENT_INK,
            activebackground=theme.ACCENT_HOVER,
            activeforeground=theme.ACCENT_INK,
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            font=(self.ui_font, 10, "bold"),
            cursor="hand2",
        )
        btn_x.pack(side=tk.RIGHT)

        body = tk.Frame(self._tour_card, bg=theme.PAPER_BG)
        body.pack(fill=tk.BOTH, expand=True, padx=8, pady=5)
        self._lbl_tour_title = tk.Label(
            body,
            text="",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.display_font, 9, "bold"),
            anchor="w",
            justify="left",
            wraplength=260,
        )
        self._lbl_tour_title.pack(fill=tk.X, pady=(0, 2))

        self._lbl_tour_desc = tk.Label(
            body,
            text="",
            bg=theme.PAPER_BG,
            fg=theme.INK_PRIMARY,
            font=(self.ui_font, 8),
            anchor="w",
            justify="left",
            wraplength=260,
        )
        self._lbl_tour_desc.pack(fill=tk.X, pady=(0, 4))

        self._lbl_tour_metrics = tk.Label(
            body,
            text="",
            bg=theme.PAPER_SUBTLE,
            fg=theme.INK_PRIMARY,
            font=(self.mono_font, 8, "bold"),
            anchor="w",
            justify="left",
            padx=6,
            pady=3,
            highlightthickness=1,
            highlightbackground=theme.PAPER_BORDER,
            wraplength=252,
        )
        self._lbl_tour_metrics.pack(fill=tk.X)

        tk.Frame(self._tour_card, bg=theme.PAPER_BORDER, height=1).pack(fill=tk.X)
        ftr = tk.Frame(self._tour_card, bg=theme.PAPER_SUBTLE)
        ftr.pack(fill=tk.X, padx=8, pady=4)
        self._btn_tour_prev = self._make_btn(
            ftr,
            "Anterior",
            lambda: self._go_tour_stop(self._tour_step - 1),
            variant="light_secondary",
            padx=7,
            pady=2,
            font_size=8,
        )
        self._btn_tour_prev.pack(side=tk.LEFT)
        self._btn_tour_next = self._make_btn(
            ftr,
            "Siguiente",
            lambda: self._go_tour_stop(self._tour_step + 1),
            variant="primary",
            padx=8,
            pady=2,
            font_size=8,
        )
        self._btn_tour_next.pack(side=tk.LEFT, padx=(5, 0))
        self._make_btn(
            ftr,
            "Cerrar",
            self._close_guided_tour,
            variant="dock_secondary",
            padx=7,
            pady=2,
            font_size=8,
        ).pack(side=tk.RIGHT)

    def _fit_tour_card_geometry(self) -> int:
        """Ajusta el ancho de la ficha flotante según el lienzo disponible y retorna el ancho efectivo."""
        cw = self.network_canvas.winfo_width()
        if cw <= 1:
            cw = 680
        preferred = max(270, min(self._px(265), int(cw * 0.52)))
        card_w = max(200, min(cw - 20, preferred))
        wrap_w = max(175, card_w - 24)
        self._lbl_tour_title.configure(wraplength=wrap_w)
        self._lbl_tour_desc.configure(wraplength=wrap_w)
        self._lbl_tour_metrics.configure(wraplength=max(168, wrap_w - 10))
        if self._tour_card.winfo_manager():
            self._tour_card.place_configure(width=card_w)
        return card_w

    def _build_tour_stops(self) -> List[Dict[str, object]]:
        if self.dataset is None:
            return []
        g = self.dataset.graph

        def _snap_for_min(target_m: float) -> Tuple[int, Optional[TimeStepSnapshot]]:
            if not self.result or not self.result.snapshots:
                return (0, None)
            best_i = min(
                range(len(self.result.snapshots)),
                key=lambda i: abs(self.result.snapshots[i].time_min - target_m),
            )
            return (best_i, self.result.snapshots[best_i])

        # Parada 1 (Min 5): 8 alcantarillas fuente y sus tuberías de cabecera
        src_ids = g.source_ids()
        src_pipes = [e.pipe_id for s in src_ids for e in g.outgoing_pipes(s)]
        idx1, s1 = _snap_for_min(5.0)
        q_in1 = s1.total_source_inflow_m3s if s1 else 0.0
        t_vals = [e.transit_time_s / 60.0 for e in g.pipes()]
        t_min_r = min(t_vals) if t_vals else 0.81
        t_max_r = max(t_vals) if t_vals else 18.05

        # Parada 2 (Min 25): estrangulamiento inicial en tuberías de 8" (P31, P39, P43)
        p2_pipes = [pid for pid in ("P31", "P39", "P43") if g.has_pipe(pid)]
        p2_nodes: Set[str] = set()
        for pid in p2_pipes:
            e = g.get_pipe(pid)
            if e:
                p2_nodes.update((e.from_node, e.to_node))
        idx2, s2 = _snap_for_min(25.0)
        u2_max = (
            max((s2.pipe_states[p].utilization_pct for p in p2_pipes if p in s2.pipe_states), default=0.0)
            if s2
            else 0.0
        )
        v2_stor = (
            sum((s2.node_states[n].stored_volume_m3 for n in ("17", "19", "20") if n in s2.node_states), 0.0)
            if s2
            else 0.0
        )

        # Parada 3 (Min 40): convergencia crítica en tramo P25 (23 -> J)
        p3_pipes = ["P25"] if g.has_pipe("P25") else []
        p3_nodes: Set[str] = set()
        for pid in p3_pipes:
            e = g.get_pipe(pid)
            if e:
                p3_nodes.update((e.from_node, e.to_node))
        idx3, s3 = _snap_for_min(40.0)
        q25 = s3.pipe_states["P25"].flow_m3s if (s3 and "P25" in s3.pipe_states) else 0.0
        u25 = s3.pipe_states["P25"].utilization_pct if (s3 and "P25" in s3.pipe_states) else 0.0

        # Parada 4 (Min 65): amortiguación y descarga en PTAR Punta Canoa (31, P29, P30)
        p4_pipes = [pid for pid in ("P29", "P30") if g.has_pipe(pid)]
        p4_nodes: Set[str] = {"31"}
        for pid in p4_pipes:
            e = g.get_pipe(pid)
            if e:
                p4_nodes.update((e.from_node, e.to_node))
        idx4, s4 = _snap_for_min(65.0)
        q_ptar = s4.total_sink_discharge_m3s if s4 else 0.0
        u_final = (
            max((s4.pipe_states[p].utilization_pct for p in p4_pipes if p in s4.pipe_states), default=0.0)
            if s4
            else 0.0
        )
        err4 = self.result.max_mass_balance_error_m3 if self.result else 0.0

        return [
            {
                "title": "Inyección en las 8 alcantarillas fuente",
                "target_min": 5.0,
                "step_idx": idx1,
                "nodes": set(src_ids),
                "pipes": set(src_pipes),
                "desc": (
                    "Los 8 nodos fuente (1, 6, 9, 17, 18, 19, 20 y 27) inyectan el caudal del Método "
                    "Racional (C=0.75, A=388 ha) más el caudal sanitario base respetando el tránsito de Manning."
                ),
                "metrics": f"Q_in = {q_in1:.4f} m³/s  ·  Tránsito: {t_min_r:.2f}–{t_max_r:.2f} min",
            },
            {
                "title": "Estrangulamiento inicial en tuberías de 8\"",
                "target_min": 25.0,
                "step_idx": idx2,
                "nodes": p2_nodes,
                "pipes": set(p2_pipes),
                "desc": (
                    "Los tramos iniciales P31, P39 y P43 (8\") saturan su capacidad Qmax y activan "
                    "almacenamiento temporal en los pozos 17, 19 y 20 sin pérdida de masa."
                ),
                "metrics": f"Util. máx: {u2_max:.2f}%  ·  Represado (17,19,20): {v2_stor:.2f} m³",
            },
            {
                "title": "Convergencia crítica en el tramo P25",
                "target_min": 40.0,
                "step_idx": idx3,
                "nodes": p3_nodes,
                "pipes": set(p3_pipes),
                "desc": (
                    "La unión de varias subcuencas sobre el pozo 23 hacia J (P25) dispara el caudal "
                    "muy por encima de la capacidad hidráulica del colector."
                ),
                "metrics": f"P25: Q = {q25:.5f} m³/s  ·  Utilización = {u25:.2f}%",
            },
            {
                "title": "Amortiguación y descarga en PTAR Punta Canoa",
                "target_min": 65.0,
                "step_idx": idx4,
                "nodes": p4_nodes,
                "pipes": set(p4_pipes),
                "desc": (
                    "Los colectores troncales de 20\" (P29 y P30) reciben la onda laminada aguas arriba "
                    "y estabilizan la entrega al Nodo sumidero 31."
                ),
                "metrics": f"PTAR 31 = {q_ptar:.4f} m³/s  ·  P29/P30: {u_final:.2f}%  ·  Err = {err4:.1e} m³",
            },
        ]

    def toggle_guided_tour(self) -> None:
        if self.dataset is None or self.result is None:
            return
        if self._tour_active:
            self._close_guided_tour()
        else:
            if self._basin_isolated:
                self._basin_isolated = False
                self._apply_basin_isolation()
                self._refresh_inspector()
            if self._map_mode != "instant":
                self._set_map_mode("instant")
            self._tour_active = True
            self._set_btn_variant(self.btn_guided_tour, "dark_primary")
            self._go_tour_stop(0, animate_cam=True)

    def _go_tour_stop(self, stop_idx: int, animate_cam: bool = True) -> None:
        stops = self._build_tour_stops()
        if not stops:
            return
        if stop_idx >= len(stops):
            self._close_guided_tour()
            return
        stop_idx = max(0, stop_idx)
        self._tour_step = stop_idx
        stop = stops[stop_idx]

        self._player_pause()
        self._stop_traversal_anim(clear_canvas=False)
        self._set_step(int(stop["step_idx"]))  # type: ignore[arg-type]

        focus_nodes: Set[str] = set(stop["nodes"])  # type: ignore[arg-type]
        focus_pipes: Set[str] = set(stop["pipes"])  # type: ignore[arg-type]
        self.network_canvas.set_tour_focus(focus_nodes, focus_pipes)

        t_real = self.result.snapshots[self.current_step].time_min if self.result else float(stop["target_min"])  # type: ignore[arg-type]
        self._lbl_tour_hdr.configure(text=f"HALLAZGO {stop_idx + 1} / {len(stops)} · MIN {t_real:.0f}")
        self._lbl_tour_title.configure(text=str(stop["title"]))
        self._lbl_tour_desc.configure(text=str(stop["desc"]))
        self._lbl_tour_metrics.configure(text=str(stop["metrics"]))
        self._btn_tour_prev.configure(state=tk.NORMAL if stop_idx > 0 else tk.DISABLED)
        self._btn_tour_next.configure(
            text="Finalizar" if stop_idx == len(stops) - 1 else "Siguiente hallazgo"
        )
        card_w = self._fit_tour_card_geometry()
        self._tour_card.place(relx=0.0, rely=1.0, x=12, y=-12, width=card_w, anchor="sw")
        self._tour_card.lift()

        if animate_cam:
            cw = self.network_canvas.winfo_width()
            self.network_canvas.animate_focus_region(
                focus_nodes,
                focus_pipes,
                left_reserve_px=(card_w + 20) if cw >= 520 else 0,
            )
        self.status_var.set(f"Guía de Sustentación · Parada {stop_idx + 1}/{len(stops)}: {stop['title']}")

    def _close_guided_tour(self) -> None:
        if not self._tour_active:
            return
        self._tour_active = False
        self._tour_card.place_forget()
        self._set_btn_variant(self.btn_guided_tour, "dark_secondary")
        self.network_canvas.set_tour_focus(None, None)
        self.network_canvas.animate_reset_view()
        self.status_var.set("Guía de Sustentación cerrada · Encuadre general restaurado.")

    def _on_close(self) -> None:
        self._player_pause()
        self._stop_traversal_anim(clear_canvas=False)
        if hasattr(self, "network_canvas"):
            self.network_canvas._stop_camera_animation()
        if self._param_rerun_after is not None:
            try:
                self.after_cancel(self._param_rerun_after)
            except tk.TclError:
                pass
            self._param_rerun_after = None
        for obj in (self, self.network_canvas, self.temporal_charts, self.comparison_charts):
            aid = getattr(obj, "_resize_after_id", None) or getattr(obj, "_resize_after", None)
            if aid is not None:
                try:
                    obj.after_cancel(aid)
                except tk.TclError:
                    pass
                if hasattr(obj, "_resize_after_id"):
                    obj._resize_after_id = None
                if hasattr(obj, "_resize_after"):
                    obj._resize_after = None
        try:
            self.update_idletasks()
        except tk.TclError:
            pass
        self.destroy()
