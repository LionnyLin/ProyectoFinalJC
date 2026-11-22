"""Aplicación principal rediseñada — Lámina Cartográfica de Archivo Hidráulico (#4A4A4A, #CBCBCB, #FFFFE3, #6D8196)."""

from dataclasses import replace
import math
import os
import time
import tkinter as tk
from tkinter import filedialog, font as tkfont, messagebox, ttk
from typing import Callable, Dict, List, Optional, Sequence, Set, Tuple

from src.algorithms import (
    build_route_to_sink,
    classify_overload_persistence,
    classify_utilization,
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
)
from . import theme
from .charts_panel import TemporalChartsPanel
from .comparison_panel import ComparisonPanelMixin
from .controls_panel import ControlsPanelMixin
from .guided_tour import GuidedTourMixin
from .icons import build_icon_set
from .inspector_panel import InspectorPanelMixin
from .network_canvas import NetworkCanvas
from .widgets import _ScenarioMenuButton


class BicentenarioSewerApp(
    ControlsPanelMixin,
    InspectorPanelMixin,
    ComparisonPanelMixin,
    GuidedTourMixin,
    tk.Tk,
):
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
        self._baseline_result: Optional[SimulationResult] = None
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
        self._inspector_trace_state: Optional[Tuple[str, str]] = None
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
        self.var_ingress_pct = tk.DoubleVar(value=100.0)
        self.var_dry_flow = tk.DoubleVar(value=0.0)
        self.var_split_rule = tk.StringVar(value="proportional")
        self.var_source_dist = tk.StringVar(value="capacity")
        self.var_split_rule_es = tk.StringVar(value=theme.SPLIT_RULE_TO_ES["proportional"])
        self.var_source_dist_es = tk.StringVar(value=theme.SOURCE_DIST_TO_ES["capacity"])
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
        self.var_source_dist_es.trace_add(
            "write",
            lambda *_a: self.var_source_dist.set(
                theme.ES_TO_SOURCE_DIST.get(self.var_source_dist_es.get(), "capacity")
            ),
        )

        for v in (
            self.var_duration,
            self.var_storm_dur,
            self.var_dt,
            self.var_ingress_pct,
            self.var_dry_flow,
            self.var_split_rule,
            self.var_source_dist,
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
            if self._load_path(default_path, silent_error=False):
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
        style.configure(
            "Light.Horizontal.TScrollbar",
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
        self.left_frame.bind("<Configure>", self._update_left_scrollregion)
        self.left_canvas.bind("<Configure>", self._update_left_scrollregion)
        self.left_canvas.configure(yscrollcommand=left_scroll.set)
        self.left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.left_panel.bind("<Enter>", lambda _e: self._bind_left_mousewheel(True))
        self.left_panel.bind("<Leave>", self._on_left_panel_leave)

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
        self._crit_tab_dirty = True
        self._charts_tab_dirty = True
        self._suppress_tree_select = True
        try:
            sel = self.tree_critical.selection()
            if sel:
                self.tree_critical.selection_remove(*sel)
        except tk.TclError:
            pass
        finally:
            self._suppress_tree_select = False
        if self._active_right_tab() == 2 and self.result is not None and self.result.snapshots:
            self._charts_tab_dirty = False
            self._push_temporal_charts(throttle_draw=False)
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
        tour_lbl = self._guided_tour_button_label(width)
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
        self._kpi_captions: Dict[str, tk.Label] = {}
        kpi_defs = [
            ("max_util", "UTILIZACIÓN MÁX.", "-"),
            ("critical", "CRÍTICAS (>75–100%)", "-"),
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
            cap_lbl = tk.Label(
                cell,
                text=caption,
                bg=theme.PAPER_BG,
                fg=theme.INK_MUTED,
                font=(self.ui_font, 7, "bold"),
                anchor="w",
                padx=8,
            )
            cap_lbl.pack(anchor="w", pady=(4, 0))
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
            self._kpi_captions[key] = cap_lbl
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

        self._build_inspector_tab(self.notebook)
        self._build_critical_tab(self.notebook)

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

        self._build_comparison_tab(self.notebook)

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
                if not self.comparisons and self._comparisons_dirty:
                    self.lbl_comp_hint.configure(text="Doble clic para activar escenario")
                if not self.lbl_comp_hint.winfo_ismapped():
                    self.lbl_comp_hint.pack(side=tk.RIGHT, padx=8)

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
            self._push_temporal_charts(throttle_draw=False)
        elif idx == 3 and (not self.comparisons or self._comparisons_dirty):
            self._action_compare_scenarios()

    def _toggle_labels(self) -> None:
        self.network_canvas.show_pipe_labels = self.var_show_pipe_labels.get()
        self.network_canvas.show_util_labels = self.var_show_util_labels.get()
        self.network_canvas.redraw()

    def _load_path(self, path: str, silent_error: bool = False) -> bool:
        try:
            dataset = load_dataset(path)
        except DataLoadError as exc:
            if not silent_error:
                messagebox.showerror("Error de validación de datos", str(exc))
            self.status_var.set(f"Error al cargar: {exc}")
            return False
        except Exception as exc:
            if not silent_error:
                messagebox.showerror("Error inesperado", str(exc))
            self.status_var.set(f"Error inesperado: {exc}")
            return False

        self._player_pause()
        self._stop_traversal_anim(clear_canvas=False)
        self._close_guided_tour()
        self.dataset = dataset
        self.engine = SewerSimulationEngine(dataset.graph, dataset.basin)
        self.result = None
        self._baseline_result = None
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
        self._last_attr_key = None
        self._source_attribution = None
        for item in self.tree_comp.get_children():
            self.tree_comp.delete(item)
        self.comparison_charts.update_comparison([])
        if hasattr(self, "lbl_comp_hint"):
            self.lbl_comp_hint.configure(
                text="Doble clic para activar escenario", fg=theme.INK_MUTED
            )

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
        self._update_guided_tour_button_label()

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
        return True

    def _action_load_excel(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar archivo Excel de la red",
            filetypes=[("Archivos Excel", "*.xlsx"), ("Todos los archivos", "*.*")],
        )
        if path and self._load_path(path):
            self.run_simulation()

    def _action_load_csv(self) -> None:
        path = filedialog.askdirectory(title="Seleccionar carpeta con archivos CSV")
        if path and self._load_path(path):
            self.run_simulation()

    def _action_export_csv(self) -> None:
        if self.dataset is None:
            messagebox.showwarning("Sin datos", "Primero cargue un conjunto de datos.")
            return
        out_dir = filedialog.askdirectory(title="Seleccionar carpeta destino para CSV")
        if out_dir:
            try:
                export_to_csv_dir(self.dataset, out_dir)
                messagebox.showinfo("Exportación completada", f"Archivos CSV exportados en:\n{out_dir}")
            except Exception as exc:
                messagebox.showerror("Error al exportar CSV", f"No se pudieron exportar los archivos CSV:\n{exc}")

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
        need_recomp = not self.comparisons or self._comparisons_dirty
        comps = (
            compare_all_scenarios(self.dataset, self.result.config)
            if need_recomp
            else self.comparisons
        )
        self.comparisons = comps
        self._comparisons_dirty = False
        if need_recomp:
            if hasattr(self, "lbl_comp_hint"):
                self.lbl_comp_hint.configure(
                    text="Doble clic para activar escenario", fg=theme.INK_MUTED
                )
            self._populate_comp_tree()
            self.comparison_charts.update_comparison(comps)
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
                try:
                    written = generate_markdown_report(self.dataset, self.result, comps, fallback)
                    messagebox.showwarning(
                        "Respaldo Markdown generado",
                        f"No se pudo generar .docx ({exc}).\nSe exportó respaldo Markdown/CSV en:\n{written}",
                    )
                except Exception as md_exc:
                    messagebox.showerror(
                        "Error al exportar reporte",
                        f"Falló la generación de .docx ({exc}) y el respaldo Markdown ({md_exc}).",
                    )
                return

        try:
            written = generate_markdown_report(self.dataset, self.result, comps, out_file)
            messagebox.showinfo("Reporte generado", f"Reporte y tabla CSV generados en:\n{written}")
        except Exception as exc:
            messagebox.showerror("Error al exportar reporte", f"No se pudo generar el reporte:\n{exc}")

    def _action_show_assumptions(self) -> None:
        msg = (
            "Supuestos del Modelo Computacional (Ciudad Bicentenario):\n\n"
            "1. Grafo Dirigido Propio: 46 vértices (8 fuentes, 37 pozos, 1 sumidero PTAR 31) y 59 aristas.\n"
            "2. Método Racional: Q = 0.00278 · C · I(t) · A (por defecto al 100% y Q_san=0 según guía; opcionalmente calibrable en parámetros).\n"
            "3. Tiempo de Tránsito Continuo: t_i = L_i / V_i con sub-paso hidráulico interno (≤10 s) y cola de prioridad de eventos.\n"
            "4. Porcentaje Oficial de Utilización: O_i(t) = (Q_dem,i(t) / Q_max,i) × 100 sin techo artificial, mientras el caudal conducido se limita físicamente a Q_max,i.\n"
            "5. Pozos Finitos y Rebose: Cada pozo retiene hasta 4.0 m³ antes de derivar el excedente a rebose superficial en vía con conservación exacta de masa."
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

    @staticmethod
    def _read_float_var(var: tk.DoubleVar, label: str) -> float:
        try:
            val = float(var.get())
        except (tk.TclError, ValueError) as exc:
            raise ValueError(f"{label} debe ser un número válido.") from exc
        if not math.isfinite(val):
            raise ValueError(f"{label} debe ser un número finito.")
        return val

    def _build_sim_config(self) -> SimulationConfig:
        sc = self._selected_scenario_obj()
        duration = self._read_float_var(self.var_duration, "Duración simulación")
        storm_dur = self._read_float_var(self.var_storm_dur, "Duración lluvia")
        dt = self._read_float_var(self.var_dt, "Paso temporal Δt")
        ingress = self._read_float_var(self.var_ingress_pct, "Ingreso pluvial (%)")
        dry_flow = self._read_float_var(self.var_dry_flow, "Caudal sanitario")

        if duration <= 0.0 or duration > 1440.0:
            raise ValueError("Duración simulación debe estar entre > 0 y 1440 min.")
        if storm_dur < 0.0 or storm_dur > 1440.0:
            raise ValueError("Duración lluvia debe estar entre 0 y 1440 min.")
        if dt <= 0.0 or dt > 60.0:
            raise ValueError("Paso temporal Δt debe estar entre > 0 y 60 min.")
        if ingress <= 0.0 or ingress > 100.0:
            raise ValueError("Ingreso pluvial (%) debe estar entre > 0 y 100 %.")
        if dry_flow < 0.0 or dry_flow > 10.0:
            raise ValueError("Caudal sanitario debe estar entre 0 y 10 m³/s.")

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
            source_distribution=self.var_source_dist.get(),
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
        try:
            self._build_sim_config()
        except ValueError:
            return
        self._on_simulation_option_changed(mark_comp=True)

    def _on_simulation_option_changed(self, mark_comp: bool = True) -> None:
        if mark_comp:
            self._mark_comparisons_dirty()
        self.run_simulation(preserve_previous=False)

    def _action_execute_simulation(self) -> None:
        self.run_simulation(preserve_previous=False, auto_play=True)

    def run_simulation(self, preserve_previous: bool = False, auto_play: bool = False) -> None:
        if self.dataset is None or self.engine is None:
            return
        if self._param_rerun_after is not None:
            try:
                self.after_cancel(self._param_rerun_after)
            except tk.TclError:
                pass
            self._param_rerun_after = None
        self._player_pause()
        try:
            cfg = self._build_sim_config()
        except Exception as exc:
            messagebox.showerror("Parámetros inválidos", f"Revise los parámetros numéricos: {exc}")
            return

        prev_scenario_id = self.result.config.scenario_id if self.result is not None else None
        base_cfg = replace(cfg, interventions={})

        if self._interventions:
            if (
                self._baseline_result is not None
                and replace(self._baseline_result.config, interventions={}) == base_cfg
            ):
                pass
            elif (
                self.result is not None
                and not self.result.config.interventions
                and replace(self.result.config, interventions={}) == base_cfg
            ):
                self._baseline_result = self.result
            else:
                self._baseline_result = self.engine.run(base_cfg)
            self._previous_result = self._baseline_result
        else:
            self._previous_result = None

        self.result = self.engine.run(cfg)
        if not self._interventions:
            self._baseline_result = self.result
        self._last_attr_key = None
        n_snaps = len(self.result.snapshots)
        if auto_play and self._map_mode != "instant":
            self._map_mode = "instant"
            self._apply_map_mode_button_styles("instant")
        peak_all, ov_all, dur_total = self._global_stress_maps()
        self.network_canvas.set_map_mode(
            self._map_mode,
            peak_util=peak_all,
            overload_minutes=ov_all,
            total_duration_min=dur_total,
        )
        self._updating_slider = True
        try:
            self.timeline_slider.configure(command="", to=max(0, n_snaps - 1))
        finally:
            if not self._slider_restore_pending:
                self._slider_restore_pending = True
                self.after_idle(self._restore_slider_command)
        end_min = self.result.snapshots[-1].time_min if self.result.snapshots else cfg.duration_min
        self.lbl_t_end.configure(text=f"{end_min:.0f}m")
        self._update_guided_tour_button_label()

        # Iniciar siempre en el minuto 0 (comienzo de la simulación)
        self._set_step(0)
        if auto_play:
            if self._tour_active:
                self._close_guided_tour(reset_view=True)
            if n_snaps > 1:
                self._player_play()
        elif self._tour_active:
            scenario_changed = prev_scenario_id is not None and prev_scenario_id != cfg.scenario_id
            self._go_tour_stop(0 if scenario_changed else self._tour_step, animate_cam=scenario_changed)
        self.status_var.set(
            f"{self._dataset_summary_text}  ·  Escenario {cfg.scenario_id} ({cfg.intensity_mm_h:.0f} mm/h) "
            f"en {self.result.execution_time_ms:.1f} ms ({n_snaps} instantes)"
        )

    def _global_stress_maps(self) -> Tuple[Dict[str, float], Dict[str, float], float]:
        """Retorna (peak_util_global, overload_min_global, duracion_total_min) de la simulación."""
        if self.result is None or not self.result.snapshots:
            return ({}, {}, 90.0)
        dur_total = max(
            1.0,
            float(self.result.snapshots[-1].time_min),
            float(self.result.config.duration_min),
        )
        return (
            self.result.peak_pipe_utilization,
            self.result.pipe_overloaded_minutes,
            dur_total,
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

    def _push_temporal_charts(self, throttle_draw: bool = False) -> None:
        if self.result is None or not self.result.snapshots or not hasattr(self, "temporal_charts"):
            return
        step_idx = max(0, min(len(self.result.snapshots) - 1, self.current_step))
        snap = self.result.snapshots[step_idx]
        self.temporal_charts.update_plots(
            self.result,
            self._selected_pipe_id,
            snap.time_min,
            previous_result=self._previous_result,
            route_pipes=self._resolve_active_route(),
            current_step_index=step_idx,
            diameter_overrides=self._diameter_overrides_map(),
            interventions=dict(self._interventions),
            throttle_draw=throttle_draw,
        )

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

        peak_all, ov_all, dur_total = self._global_stress_maps()
        self.network_canvas.set_stress_maps(
            peak_util=peak_all,
            overload_minutes=ov_all,
            total_duration_min=dur_total,
        )
        canvas_snap = snap if self._map_mode == "instant" else self.result.snapshots[-1]
        self.network_canvas.set_snapshot(canvas_snap)
        self._update_clock_label(snap)
        self._update_kpi_cards(snap)
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
            self._push_temporal_charts(throttle_draw=self.is_playing)
        else:
            self._charts_tab_dirty = True

    def _update_kpi_cards(self, snap: Optional[TimeStepSnapshot] = None) -> None:
        if self.result is None or not self.result.snapshots:
            return
        if snap is None:
            snap = self.result.snapshots[self.current_step]
        peak_all, ov_all, dur_total = self._global_stress_maps()
        if self._map_mode == "peak":
            captions = {
                "max_util": "PICO MÁX. UTIL.",
                "critical": "CRÍTICAS PICO (>75–100%)",
                "overloaded": "SOBRECARGA PICO (>100%)",
                "ptar": "PICO DESCARGA PTAR 31",
            }
            for k, txt in captions.items():
                if k in self._kpi_captions:
                    self._kpi_captions[k].configure(text=txt)
            max_u = max((peak_all.get(pid, 0.0) for pid in snap.pipe_states), default=0.0)
            tier_idx = classify_utilization(max_u).tier_index
            crit_cnt = sum(
                1 for pid in snap.pipe_states if classify_utilization(peak_all.get(pid, 0.0)).tier_index == 3
            )
            over_cnt = sum(
                1 for pid in snap.pipe_states if classify_utilization(peak_all.get(pid, 0.0)).tier_index == 4
            )
            self._kpi_cards["max_util"].configure(
                text=f"{max_u:.1f}%", fg=theme.TIER_TEXT_ON_LIGHT[tier_idx]
            )
            self._kpi_cards["critical"].configure(
                text=str(crit_cnt),
                fg=theme.STATUS_ERR_LIGHT if crit_cnt else theme.INK_PRIMARY,
            )
            self._kpi_cards["overloaded"].configure(
                text=str(over_cnt),
                fg=theme.TIER_TEXT_ON_LIGHT[4] if over_cnt else theme.INK_PRIMARY,
            )
            self._kpi_cards["ptar"].configure(
                text=f"{self.result.peak_sink_discharge_m3s:.4f} m³/s",
                fg=theme.ACCENT_TEXT_ON_LIGHT,
            )
        elif self._map_mode == "overload_minutes":
            captions = {
                "max_util": "MÁX. SOBREC. ACUM.",
                "critical": "TUBERÍAS >0 min >100%",
                "overloaded": "COLAPSO CRÓNICO (>75%)",
                "ptar": "VOLUMEN PTAR 31",
            }
            for k, txt in captions.items():
                if k in self._kpi_captions:
                    self._kpi_captions[k].configure(text=txt)
            max_ov = max((ov_all.get(pid, 0.0) for pid in snap.pipe_states), default=0.0)
            tier_ov, _, _ = classify_overload_persistence(max_ov, dur_total)
            any_ov_cnt = sum(1 for pid in snap.pipe_states if ov_all.get(pid, 0.0) >= 0.5)
            chronic_cnt = sum(
                1
                for pid in snap.pipe_states
                if classify_overload_persistence(ov_all.get(pid, 0.0), dur_total)[0] == 4
            )
            self._kpi_cards["max_util"].configure(
                text=f"{max_ov:.0f} / {dur_total:.0f}m",
                fg=theme.TIER_TEXT_ON_LIGHT[tier_ov],
            )
            self._kpi_cards["critical"].configure(
                text=str(any_ov_cnt),
                fg=theme.STATUS_ERR_LIGHT if any_ov_cnt else theme.INK_PRIMARY,
            )
            self._kpi_cards["overloaded"].configure(
                text=str(chronic_cnt),
                fg=theme.TIER_TEXT_ON_LIGHT[4] if chronic_cnt else theme.INK_PRIMARY,
            )
            self._kpi_cards["ptar"].configure(
                text=f"{self.result.total_sink_discharge_m3:.1f} m³",
                fg=theme.ACCENT_TEXT_ON_LIGHT,
            )
        else:
            captions = {
                "max_util": "UTILIZACIÓN MÁX.",
                "critical": "CRÍTICAS (>75–100%)",
                "overloaded": "SOBRECARGA (>100%)",
                "ptar": "DESCARGA PTAR 31",
            }
            for k, txt in captions.items():
                if k in self._kpi_captions:
                    self._kpi_captions[k].configure(text=txt)
            max_u = max((ps.utilization_pct for ps in snap.pipe_states.values()), default=0.0)
            tier_idx = 0 if max_u <= 25 else (1 if max_u <= 50 else (2 if max_u <= 75 else (3 if max_u <= 100 else 4)))
            self._kpi_cards["max_util"].configure(
                text=f"{max_u:.1f}%", fg=theme.TIER_TEXT_ON_LIGHT[tier_idx]
            )
            self._kpi_cards["critical"].configure(
                text=str(len(snap.near_capacity_pipe_ids)),
                fg=theme.STATUS_ERR_LIGHT if snap.near_capacity_pipe_ids else theme.INK_PRIMARY,
            )
            self._kpi_cards["overloaded"].configure(
                text=str(len(snap.overloaded_pipe_ids)),
                fg=theme.TIER_TEXT_ON_LIGHT[4] if snap.overloaded_pipe_ids else theme.INK_PRIMARY,
            )
            self._kpi_cards["ptar"].configure(
                text=f"{snap.total_sink_discharge_m3s:.4f} m³/s", fg=theme.ACCENT_TEXT_ON_LIGHT
            )

    def _update_clock_label(self, snap: Optional[TimeStepSnapshot] = None) -> None:
        if self.result is None or not self.result.snapshots:
            return
        if snap is None:
            snap = self.result.snapshots[self.current_step]
        cfg = self.result.config
        scen_es = theme.translate_scenario_name(
            cfg.scenario_name, compact=bool(self._player_compact)
        )
        _, _, dur_total = self._global_stress_maps()
        if self._map_mode == "peak":
            if self._player_compact:
                self.lbl_clock.configure(
                    text=f"Pico 0–{dur_total:.0f}m · {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
                )
            else:
                self.lbl_clock.configure(
                    text=f"Pico máximo · 0–{dur_total:.0f} min  ·  {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
                )
        elif self._map_mode == "overload_minutes":
            if self._player_compact:
                self.lbl_clock.configure(
                    text=f"Sobrecarga 0–{dur_total:.0f}m · {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
                )
            else:
                self.lbl_clock.configure(
                    text=f"Sobrecarga acumulada · 0–{dur_total:.0f} min  ·  {scen_es} ({cfg.intensity_mm_h:.0f} mm/h)"
                )
        elif self._player_compact:
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

    def _apply_map_mode_button_styles(self, mode: str) -> None:
        for mid, btn in self._map_mode_buttons.items():
            is_act = mid == mode
            btn.configure(
                bg=theme.ACCENT_PRIMARY if is_act else theme.DOCK_BG,
                fg=theme.ACCENT_INK if is_act else theme.INK_PRIMARY,
                font=(self.ui_font, 8, "bold" if is_act else "normal"),
            )

    def _set_map_mode(self, mode: str) -> None:
        if mode not in ("instant", "peak", "overload_minutes"):
            return
        if mode in ("peak", "overload_minutes"):
            self._player_pause()
        self._map_mode = mode
        self._apply_map_mode_button_styles(mode)
        if self.result is not None and self.result.snapshots:
            peak_all, ov_all, dur_total = self._global_stress_maps()
            snap_cur = self.result.snapshots[self.current_step]
            canvas_snap = snap_cur if mode == "instant" else self.result.snapshots[-1]
            self.network_canvas.snapshot = canvas_snap
            self.network_canvas.set_map_mode(
                mode,
                peak_util=peak_all,
                overload_minutes=ov_all,
                total_duration_min=dur_total,
            )
            self._update_clock_label(snap_cur)
            self._update_kpi_cards(snap_cur)
            self._update_legend_counts(snap_cur)
        else:
            self.network_canvas.set_map_mode(mode)

    def _on_slider_move(self, val: str) -> None:
        step = int(float(val))
        if self._updating_slider or step == self.current_step:
            return
        self._player_pause()
        if self._map_mode != "instant":
            self._map_mode = "instant"
            self._apply_map_mode_button_styles("instant")
            self.network_canvas._map_mode = "instant"
            self.network_canvas._fast_cache_valid = False
        self._set_step(step)

    def toggle_play_pause(self) -> None:
        if self.is_playing:
            self._player_pause()
        else:
            self._player_play()

    def _player_play(self) -> None:
        if self.result is None or len(self.result.snapshots) <= 1:
            return
        if self._after_id is not None:
            try:
                self.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None
        if self._tour_active:
            self._close_guided_tour(reset_view=True)
        if self._map_mode != "instant":
            self._set_map_mode("instant")
        self._stop_traversal_anim(clear_canvas=False)
        if self.current_step >= len(self.result.snapshots) - 1:
            self._set_step(0)
        self.is_playing = True
        self._update_play_button_label()
        self.network_canvas.set_playing(True, self._speed_factor())
        self._schedule_next_frame()

    def _player_pause(self) -> None:
        was_playing = self.is_playing
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
        if was_playing and self.result is not None and self.result.snapshots:
            active_tab = self._active_right_tab()
            if active_tab == 2 and hasattr(self, "temporal_charts"):
                self._push_temporal_charts(throttle_draw=False)
            elif active_tab == 0 and self._insp_tab_dirty:
                self._insp_tab_dirty = False
                self._refresh_inspector()

    def _player_reset(self) -> None:
        self._player_pause()
        if self._map_mode != "instant":
            self._map_mode = "instant"
            self._apply_map_mode_button_styles("instant")
            self.network_canvas._map_mode = "instant"
            self.network_canvas._fast_cache_valid = False
        self._set_step(0)

    def _player_step(self, delta: int) -> None:
        self._player_pause()
        if self._map_mode != "instant":
            self._map_mode = "instant"
            self._apply_map_mode_button_styles("instant")
            self.network_canvas._map_mode = "instant"
            self.network_canvas._fast_cache_valid = False
        self._set_step(self.current_step + delta)

    def _schedule_next_frame(self) -> None:
        self._after_id = None
        if not self.is_playing or self.result is None:
            return
        try:
            if not self.winfo_exists():
                return
        except tk.TclError:
            return
        if self.current_step >= len(self.result.snapshots) - 1:
            self._player_pause()
            return
        self._set_step(self.current_step + 1)
        if not self.is_playing:
            return
        speed_map = {"1x": 420, "2x": 210, "5x": 85, "10x": 40}
        delay = speed_map.get(self.var_speed.get(), 200)
        try:
            self._after_id = self.after(delay, self._schedule_next_frame)
        except tk.TclError:
            self._after_id = None

    def _on_close(self) -> None:
        self._player_pause()
        self._stop_traversal_anim(clear_canvas=False)
        self._bind_left_mousewheel(False)
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
