"""Aplicación principal rediseñada (Plum #3B153A + Xanthous #F0C987 + arquitectura Impeccable)."""

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional

from src.algorithms import (
    bfs,
    dfs,
    rank_critical_pipes,
    search_entities,
    trace_downstream,
    trace_upstream,
)
from src.io.data_loader import (
    DataLoadError,
    NetworkDataset,
    export_to_csv_dir,
    load_dataset,
)
from src.simulation import (
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
from .charts_panel import ComparisonChartsPanel, TemporalChartsPanel
from .network_canvas import NetworkCanvas


class BicentenarioSewerApp(tk.Tk):
    """Interfaz gráfica moderna para simulación y análisis de la red de alcantarillado."""

    def __init__(self, initial_data_path: Optional[str] = None) -> None:
        super().__init__()
        self.title("Ciudad Bicentenario · Simulador Hidráulico de Alcantarillado")
        self.geometry("1480x900")
        self.minsize(1220, 740)
        self.configure(bg=theme.PLUM_DEEP)

        self.ui_font, self.mono_font, self.inter_loaded = theme.resolve_fonts(self)

        self.dataset: Optional[NetworkDataset] = None
        self.engine: Optional[SewerSimulationEngine] = None
        self.result: Optional[SimulationResult] = None
        self.comparisons: List[ScenarioSummary] = []

        self.current_step: int = 0
        self.is_playing: bool = False
        self._after_id: Optional[str] = None
        self._selected_pipe_id: Optional[str] = None
        self._selected_node_id: Optional[str] = None
        self._updating_slider: bool = False

        # Variables de control
        self.var_scenario = tk.StringVar()
        self.var_duration = tk.DoubleVar(value=90.0)
        self.var_storm_dur = tk.DoubleVar(value=60.0)
        self.var_dt = tk.DoubleVar(value=1.0)
        self.var_ingress_pct = tk.DoubleVar(value=2.5)
        self.var_dry_flow = tk.DoubleVar(value=0.003)
        self.var_split_rule = tk.StringVar(value="proportional")
        self.var_hyetograph = tk.StringVar(value="uniform")
        self.var_speed = tk.StringVar(value="2x")
        self.var_search = tk.StringVar()
        self.var_bfs_start = tk.StringVar(value="6")
        self.var_bfs_target = tk.StringVar(value="31")
        self.var_crit_filter = tk.StringVar(value="all")
        self.var_show_pipe_labels = tk.BooleanVar(value=True)
        self.var_show_util_labels = tk.BooleanVar(value=True)

        self._legend_count_labels: List[tk.Label] = []

        self._configure_styles()
        self._build_layout()

        default_path = initial_data_path or self._find_default_dataset()
        if default_path:
            self._load_path(default_path, silent_error=False)
            if self.dataset is not None:
                self.run_simulation()

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
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            ".",
            background=theme.PLUM_BASE,
            foreground=theme.TEXT_PRIMARY,
            font=(self.ui_font, 9),
        )
        style.configure("TFrame", background=theme.PLUM_BASE)
        style.configure("TLabel", background=theme.PLUM_BASE, foreground=theme.TEXT_PRIMARY)
        style.configure(
            "TNotebook",
            background=theme.PLUM_BASE,
            borderwidth=0,
            tabmargins=(4, 4, 4, 0),
        )
        style.configure(
            "TNotebook.Tab",
            background=theme.PLUM_BASE,
            foreground=theme.TEXT_SECONDARY,
            padding=(12, 7),
            borderwidth=0,
            font=(self.ui_font, 9, "bold"),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", theme.XANTHOUS), ("active", theme.PLUM_ELEVATED)],
            foreground=[("selected", theme.XANTHOUS_INK), ("active", theme.TEXT_PRIMARY)],
        )
        style.configure(
            "Treeview",
            background=theme.PLUM_DEEP,
            foreground=theme.TEXT_PRIMARY,
            fieldbackground=theme.PLUM_DEEP,
            rowheight=25,
            borderwidth=0,
            font=(self.ui_font, 9),
        )
        style.configure(
            "Treeview.Heading",
            background=theme.PLUM_ELEVATED,
            foreground=theme.XANTHOUS,
            borderwidth=0,
            font=(self.ui_font, 8, "bold"),
        )
        style.map(
            "Treeview",
            background=[("selected", theme.PLUM_ELEVATED)],
            foreground=[("selected", theme.XANTHOUS)],
        )
        style.configure(
            "TCombobox",
            fieldbackground=theme.PLUM_DEEP,
            background=theme.PLUM_ELEVATED,
            foreground=theme.TEXT_PRIMARY,
            bordercolor=theme.PLUM_BORDER,
            arrowcolor=theme.XANTHOUS,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", theme.PLUM_DEEP)],
            selectbackground=[("readonly", theme.PLUM_ELEVATED)],
            selectforeground=[("readonly", theme.XANTHOUS)],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=theme.PLUM_ELEVATED,
            troughcolor=theme.PLUM_BASE,
            bordercolor=theme.PLUM_BASE,
            arrowcolor=theme.TEXT_SECONDARY,
        )

    def _make_btn(
        self,
        parent: tk.Misc,
        text: str,
        cmd,
        primary: bool = False,
        padx: int = 10,
        pady: int = 5,
        font_size: int = 9,
    ) -> tk.Button:
        """Crea un botón plano con jerarquía clara (Xanthous para acción primaria, Plum elevado para secundarias)."""
        bg = theme.XANTHOUS if primary else theme.PLUM_ELEVATED
        fg = theme.XANTHOUS_INK if primary else theme.TEXT_PRIMARY
        hover_bg = theme.XANTHOUS_HOVER if primary else theme.PLUM_BORDER
        btn = tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=bg,
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=theme.XANTHOUS if primary else theme.PLUM_BORDER,
            padx=padx,
            pady=pady,
            font=(self.ui_font, font_size, "bold"),
            cursor="hand2",
        )
        btn.bind("<Enter>", lambda _e: btn.configure(bg=hover_bg))
        btn.bind("<Leave>", lambda _e: btn.configure(bg=bg))
        return btn

    def _build_layout(self) -> None:
        # Barra superior minimalista con línea de acento Xanthous
        tk.Frame(self, bg=theme.XANTHOUS, height=2).pack(side=tk.TOP, fill=tk.X)
        topbar = tk.Frame(self, bg=theme.PLUM_BASE, height=52)
        topbar.pack(side=tk.TOP, fill=tk.X)
        tk.Frame(self, bg=theme.PLUM_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

        title_block = tk.Frame(topbar, bg=theme.PLUM_BASE)
        title_block.pack(side=tk.LEFT, padx=16, pady=8)
        tk.Label(
            title_block,
            text="CIUDAD BICENTENARIO",
            bg=theme.PLUM_BASE,
            fg=theme.XANTHOUS,
            font=(self.ui_font, 8, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_block,
            text="Simulador Hidráulico · Red de Alcantarillado hacia PTAR Punta Canoa",
            bg=theme.PLUM_BASE,
            fg=theme.TEXT_PRIMARY,
            font=(self.ui_font, 11, "bold"),
        ).pack(anchor="w")

        actions = tk.Frame(topbar, bg=theme.PLUM_BASE)
        actions.pack(side=tk.RIGHT, padx=14, pady=10)
        self._make_btn(actions, "Supuestos", self._action_show_assumptions, padx=10, pady=4, font_size=8).pack(side=tk.RIGHT, padx=4)
        self._make_btn(actions, "Generar Reporte", self._action_generate_report, primary=True, padx=12, pady=4, font_size=8).pack(side=tk.RIGHT, padx=4)
        self._make_btn(actions, "Exportar CSV", self._action_export_csv, padx=10, pady=4, font_size=8).pack(side=tk.RIGHT, padx=4)
        self._make_btn(actions, "Cargar CSV", self._action_load_csv, padx=10, pady=4, font_size=8).pack(side=tk.RIGHT, padx=4)
        self._make_btn(actions, "Cargar Excel", self._action_load_excel, padx=10, pady=4, font_size=8).pack(side=tk.RIGHT, padx=4)

        # Paneles principales con divisores 1px (sin cards anidadas)
        main_pane = tk.PanedWindow(
            self,
            orient=tk.HORIZONTAL,
            bg=theme.PLUM_BORDER,
            sashwidth=2,
            bd=0,
        )
        main_pane.pack(fill=tk.BOTH, expand=True)

        # Rail izquierdo limpio sobre Plum base
        left_container = tk.Frame(main_pane, bg=theme.PLUM_BASE, width=326)
        left_canvas = tk.Canvas(left_container, bg=theme.PLUM_BASE, highlightthickness=0, width=314)
        left_scroll = ttk.Scrollbar(left_container, orient=tk.VERTICAL, command=left_canvas.yview)
        self.left_frame = tk.Frame(left_canvas, bg=theme.PLUM_BASE)
        self.left_frame.bind(
            "<Configure>",
            lambda _e: left_canvas.configure(scrollregion=left_canvas.bbox("all")),
        )
        left_canvas.create_window((0, 0), window=self.left_frame, anchor="nw", width=312)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        main_pane.add(left_container, minsize=296)

        self._build_left_controls(self.left_frame)

        # Área central: KPI strip + Canvas + Reproductor temporal
        center_frame = tk.Frame(main_pane, bg=theme.PLUM_DEEP)
        main_pane.add(center_frame, minsize=540)
        self._build_center_panel(center_frame)

        # Panel derecho: Notebook editorial
        right_frame = tk.Frame(main_pane, bg=theme.PLUM_BASE, width=440)
        main_pane.add(right_frame, minsize=390)
        self._build_right_panel(right_frame)

        # Barra de estado inferior
        tk.Frame(self, bg=theme.PLUM_BORDER, height=1).pack(side=tk.BOTTOM, fill=tk.X)
        statusbar = tk.Frame(self, bg=theme.PLUM_BASE, height=26)
        statusbar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var = tk.StringVar(value="Listo.")
        tk.Label(
            statusbar,
            textvariable=self.status_var,
            bg=theme.PLUM_BASE,
            fg=theme.TEXT_SECONDARY,
            font=(self.ui_font, 8),
            anchor="w",
        ).pack(side=tk.LEFT, padx=12, pady=3)

        font_tag = "Tipografía: Inter 500" if self.inter_loaded else f"Tipografía: {self.ui_font} (fallback de Inter)"
        tk.Label(
            statusbar,
            text=f"{font_tag}  ·  Plum #3B153A / Xanthous #F0C987",
            bg=theme.PLUM_BASE,
            fg=theme.TEXT_MUTED,
            font=(self.ui_font, 8),
        ).pack(side=tk.RIGHT, padx=12, pady=3)

    def _make_rail_section(self, parent: tk.Misc, eyebrow: str, add_divider: bool = True) -> tk.Frame:
        """Sección limpia en el rail lateral separada por línea fina y aire tipográfico (cero cards-in-cards)."""
        if add_divider:
            tk.Frame(parent, bg=theme.PLUM_BORDER, height=1).pack(fill=tk.X, padx=14, pady=(8, 2))
        sec = tk.Frame(parent, bg=theme.PLUM_BASE)
        sec.pack(fill=tk.X, padx=14, pady=8)
        tk.Label(
            sec,
            text=eyebrow.upper(),
            bg=theme.PLUM_BASE,
            fg=theme.XANTHOUS,
            font=(self.ui_font, 8, "bold"),
            anchor="w",
        ).pack(fill=tk.X, pady=(0, 6))
        return sec

    def _build_left_controls(self, parent: tk.Frame) -> None:
        # 1. Escenario y parámetros hidráulicos
        sec_sim = self._make_rail_section(parent, "01 · Escenario y Parámetros", add_divider=False)

        tk.Label(
            sec_sim,
            text="Escenario de precipitación",
            bg=theme.PLUM_BASE,
            fg=theme.TEXT_SECONDARY,
            font=(self.ui_font, 8),
        ).pack(anchor="w", pady=(0, 2))
        self.combo_scenario = ttk.Combobox(sec_sim, textvariable=self.var_scenario, state="readonly")
        self.combo_scenario.pack(fill=tk.X, pady=(0, 8))

        grid = tk.Frame(sec_sim, bg=theme.PLUM_BASE)
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
                bg=theme.PLUM_BASE,
                fg=theme.TEXT_SECONDARY,
                font=(self.ui_font, 8),
            ).grid(row=row_i, column=0, sticky="w", pady=3)
            tk.Spinbox(
                grid,
                textvariable=var,
                from_=frm,
                to=to,
                increment=inc,
                width=9,
                bg=theme.PLUM_DEEP,
                fg=theme.TEXT_PRIMARY,
                buttonbackground=theme.PLUM_ELEVATED,
                insertbackground=theme.XANTHOUS,
                highlightthickness=1,
                highlightbackground=theme.PLUM_BORDER,
                relief="flat",
                font=(self.mono_font, 9),
            ).grid(row=row_i, column=1, sticky="e", pady=3)
        grid.columnconfigure(0, weight=1)

        preset_row = tk.Frame(sec_sim, bg=theme.PLUM_BASE)
        preset_row.pack(fill=tk.X, pady=(6, 6))
        self._make_btn(
            preset_row,
            "Calibrado (2.5%)",
            lambda: self._apply_preset(2.5, 0.003),
            padx=6,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 3))
        self._make_btn(
            preset_row,
            "Racional 100%",
            lambda: self._apply_preset(100.0, 0.0),
            padx=6,
            pady=4,
            font_size=8,
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(3, 0))

        row_rules = tk.Frame(sec_sim, bg=theme.PLUM_BASE)
        row_rules.pack(fill=tk.X, pady=3)
        tk.Label(row_rules, text="Bifurcación", bg=theme.PLUM_BASE, fg=theme.TEXT_SECONDARY, font=(self.ui_font, 8)).pack(side=tk.LEFT)
        ttk.Combobox(
            row_rules,
            textvariable=self.var_split_rule,
            values=["proportional", "equal"],
            state="readonly",
            width=12,
        ).pack(side=tk.RIGHT)

        row_hyeto = tk.Frame(sec_sim, bg=theme.PLUM_BASE)
        row_hyeto.pack(fill=tk.X, pady=3)
        tk.Label(row_hyeto, text="Hietograma", bg=theme.PLUM_BASE, fg=theme.TEXT_SECONDARY, font=(self.ui_font, 8)).pack(side=tk.LEFT)
        ttk.Combobox(
            row_hyeto,
            textvariable=self.var_hyetograph,
            values=["uniform", "triangular"],
            state="readonly",
            width=12,
        ).pack(side=tk.RIGHT)

        self._make_btn(
            sec_sim,
            "▶  Ejecutar Simulación",
            self.run_simulation,
            primary=True,
            pady=8,
            font_size=9,
        ).pack(fill=tk.X, pady=(10, 0))

        # 2. Leyenda de colores (Sección 7)
        sec_leg = self._make_rail_section(parent, "02 · Escala de Utilización")
        self._legend_count_labels.clear()
        for rng, color_hex, desc in theme.COLOR_SCALE_LEGEND:
            row = tk.Frame(sec_leg, bg=theme.PLUM_BASE)
            row.pack(fill=tk.X, pady=2)
            swatch = tk.Canvas(
                row,
                width=12,
                height=12,
                bg=color_hex,
                highlightthickness=1,
                highlightbackground=theme.PLUM_DEEP,
            )
            swatch.pack(side=tk.LEFT, padx=(0, 8))
            tk.Label(
                row,
                text=f"{rng} · {desc}",
                bg=theme.PLUM_BASE,
                fg=theme.TEXT_SECONDARY,
                font=(self.ui_font, 8),
            ).pack(side=tk.LEFT)
            cnt_lbl = tk.Label(
                row,
                text="0",
                bg=theme.PLUM_BASE,
                fg=theme.XANTHOUS,
                font=(self.mono_font, 8, "bold"),
            )
            cnt_lbl.pack(side=tk.RIGHT)
            self._legend_count_labels.append(cnt_lbl)

        # 3. Consultas y recorridos BFS / DFS
        sec_alg = self._make_rail_section(parent, "03 · Consultas y Recorridos (BFS / DFS)")

        search_row = tk.Frame(sec_alg, bg=theme.PLUM_BASE)
        search_row.pack(fill=tk.X, pady=(0, 6))
        ent = tk.Entry(
            search_row,
            textvariable=self.var_search,
            bg=theme.PLUM_DEEP,
            fg=theme.TEXT_PRIMARY,
            insertbackground=theme.XANTHOUS,
            highlightthickness=1,
            highlightbackground=theme.PLUM_BORDER,
            relief="flat",
            font=(self.ui_font, 9),
        )
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        ent.bind("<Return>", lambda _e: self._action_search())
        self._make_btn(search_row, "Buscar", self._action_search, primary=True, padx=10, pady=4, font_size=8).pack(
            side=tk.RIGHT, padx=(6, 0)
        )

        trav_grid = tk.Frame(sec_alg, bg=theme.PLUM_BASE)
        trav_grid.pack(fill=tk.X, pady=2)
        tk.Label(trav_grid, text="Nodo origen", bg=theme.PLUM_BASE, fg=theme.TEXT_SECONDARY, font=(self.ui_font, 8)).grid(row=0, column=0, sticky="w", pady=2)
        self.combo_bfs_start = ttk.Combobox(trav_grid, textvariable=self.var_bfs_start, width=10)
        self.combo_bfs_start.grid(row=0, column=1, sticky="e", pady=2)
        tk.Label(trav_grid, text="Nodo destino", bg=theme.PLUM_BASE, fg=theme.TEXT_SECONDARY, font=(self.ui_font, 8)).grid(row=1, column=0, sticky="w", pady=2)
        self.combo_bfs_target = ttk.Combobox(trav_grid, textvariable=self.var_bfs_target, width=10)
        self.combo_bfs_target.grid(row=1, column=1, sticky="e", pady=2)
        trav_grid.columnconfigure(0, weight=1)

        btn_trav = tk.Frame(sec_alg, bg=theme.PLUM_BASE)
        btn_trav.pack(fill=tk.X, pady=6)
        for text, cmd in [
            ("BFS", lambda: self._run_traversal("BFS")),
            ("DFS", lambda: self._run_traversal("DFS")),
            ("Aguas Abajo", lambda: self._run_trace("down")),
            ("Limpiar", self._clear_highlights),
        ]:
            self._make_btn(btn_trav, text, cmd, padx=6, pady=4, font_size=8).pack(
                side=tk.LEFT, fill=tk.X, expand=True, padx=2
            )

        self.txt_traversal = tk.Text(
            sec_alg,
            height=5,
            bg=theme.PLUM_DEEP,
            fg=theme.TEXT_SECONDARY,
            highlightthickness=1,
            highlightbackground=theme.PLUM_BORDER,
            relief="flat",
            font=(self.mono_font, 8),
            wrap=tk.WORD,
            padx=6,
            pady=5,
        )
        self.txt_traversal.pack(fill=tk.X, pady=(2, 4))
        self.txt_traversal.configure(state=tk.DISABLED)

    def _build_center_panel(self, parent: tk.Frame) -> None:
        # Franja superior de métricas KPI (sin bordes pesados, solo separación fina)
        kpi_strip = tk.Frame(parent, bg=theme.PLUM_BASE)
        kpi_strip.pack(side=tk.TOP, fill=tk.X)
        tk.Frame(parent, bg=theme.PLUM_BORDER, height=1).pack(side=tk.TOP, fill=tk.X)

        self.lbl_clock = tk.Label(
            kpi_strip,
            text="t = 0.0 min  ·  Escenario: -",
            bg=theme.PLUM_BASE,
            fg=theme.XANTHOUS,
            font=(self.ui_font, 10, "bold"),
        )
        self.lbl_clock.pack(side=tk.LEFT, padx=14, pady=8)

        self.lbl_kpi_summary = tk.Label(
            kpi_strip,
            text="Máx Util: -   |   Críticas: -   |   PTAR 31: -",
            bg=theme.PLUM_BASE,
            fg=theme.TEXT_SECONDARY,
            font=(self.mono_font, 9),
        )
        self.lbl_kpi_summary.pack(side=tk.LEFT, padx=10, pady=8)

        view_opts = tk.Frame(kpi_strip, bg=theme.PLUM_BASE)
        view_opts.pack(side=tk.RIGHT, padx=10, pady=6)
        self._make_btn(view_opts, "Ajustar Vista", lambda: self.network_canvas.reset_view(), padx=8, pady=3, font_size=8).pack(side=tk.RIGHT, padx=4)

        for label, var in [("% Util.", self.var_show_util_labels), ("IDs", self.var_show_pipe_labels)]:
            tk.Checkbutton(
                view_opts,
                text=label,
                variable=var,
                command=self._toggle_labels,
                bg=theme.PLUM_BASE,
                fg=theme.TEXT_SECONDARY,
                selectcolor=theme.PLUM_DEEP,
                activebackground=theme.PLUM_BASE,
                activeforeground=theme.XANTHOUS,
                font=(self.ui_font, 8),
            ).pack(side=tk.RIGHT, padx=4)

        # Lienzo interactivo del grafo
        self.network_canvas = NetworkCanvas(
            parent,
            ui_font=self.ui_font,
            on_select_pipe=self._on_pipe_selected,
            on_select_node=self._on_node_selected,
        )
        self.network_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Barra de reproducción temporal (RF09)
        tk.Frame(parent, bg=theme.PLUM_BORDER, height=1).pack(side=tk.BOTTOM, fill=tk.X)
        player = tk.Frame(parent, bg=theme.PLUM_BASE)
        player.pack(side=tk.BOTTOM, fill=tk.X)

        controls_row = tk.Frame(player, bg=theme.PLUM_BASE)
        controls_row.pack(fill=tk.X, padx=12, pady=(8, 4))

        self._make_btn(controls_row, "⏮ Inicio", self._player_reset, padx=8, pady=4, font_size=8).pack(side=tk.LEFT, padx=2)
        self._make_btn(controls_row, "◀ -1", lambda: self._player_step(-1), padx=8, pady=4, font_size=8).pack(side=tk.LEFT, padx=2)
        self._make_btn(controls_row, "▶ Reproducir", self._player_play, primary=True, padx=12, pady=4, font_size=8).pack(side=tk.LEFT, padx=4)
        self._make_btn(controls_row, "⏸ Pausar", self._player_pause, padx=8, pady=4, font_size=8).pack(side=tk.LEFT, padx=2)
        self._make_btn(controls_row, "+1 ▶", lambda: self._player_step(1), padx=8, pady=4, font_size=8).pack(side=tk.LEFT, padx=2)

        tk.Label(controls_row, text="Velocidad", bg=theme.PLUM_BASE, fg=theme.TEXT_MUTED, font=(self.ui_font, 8)).pack(side=tk.LEFT, padx=(12, 4))
        ttk.Combobox(
            controls_row,
            textvariable=self.var_speed,
            values=["1x", "2x", "5x", "10x"],
            state="readonly",
            width=4,
        ).pack(side=tk.LEFT)

        self.lbl_mass_audit = tk.Label(
            controls_row,
            text="Conservación de masa: -",
            bg=theme.PLUM_BASE,
            fg="#34D399",
            font=(self.mono_font, 8, "bold"),
        )
        self.lbl_mass_audit.pack(side=tk.RIGHT, padx=4)

        self.timeline_slider = tk.Scale(
            player,
            from_=0,
            to=0,
            orient=tk.HORIZONTAL,
            showvalue=False,
            command=self._on_slider_move,
            bg=theme.PLUM_BASE,
            fg=theme.XANTHOUS,
            troughcolor=theme.PLUM_DEEP,
            highlightthickness=0,
            sliderrelief="flat",
            activebackground=theme.XANTHOUS,
        )
        self.timeline_slider.pack(fill=tk.X, padx=12, pady=(0, 8))

    def _build_right_panel(self, parent: tk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        # Tab 1: Inspector y Resumen
        tab_info = ttk.Frame(self.notebook)
        self.notebook.add(tab_info, text="Inspector")
        self.txt_inspector = tk.Text(
            tab_info,
            bg=theme.PLUM_DEEP,
            fg=theme.TEXT_PRIMARY,
            relief="flat",
            font=(self.mono_font, 9),
            wrap=tk.WORD,
            padx=12,
            pady=10,
        )
        self.txt_inspector.pack(fill=tk.BOTH, expand=True)
        self.txt_inspector.configure(state=tk.DISABLED)

        # Tab 2: Tuberías Críticas
        tab_crit = ttk.Frame(self.notebook)
        self.notebook.add(tab_crit, text="Tuberías Críticas")

        filter_bar = tk.Frame(tab_crit, bg=theme.PLUM_BASE)
        filter_bar.pack(fill=tk.X, padx=8, pady=6)
        for text, val in [
            ("Todas (59)", "all"),
            ("Críticas (≥75%)", "critical"),
            ("Sobrecargadas (>100%)", "overloaded"),
        ]:
            tk.Radiobutton(
                filter_bar,
                text=text,
                variable=self.var_crit_filter,
                value=val,
                command=self._refresh_critical_table,
                bg=theme.PLUM_BASE,
                fg=theme.TEXT_SECONDARY,
                selectcolor=theme.PLUM_DEEP,
                activebackground=theme.PLUM_BASE,
                activeforeground=theme.XANTHOUS,
                font=(self.ui_font, 8),
            ).pack(side=tk.LEFT, padx=4)

        cols = ("rank", "pipe", "tramo", "q_curr", "q_max", "util", "estado")
        self.tree_critical = ttk.Treeview(tab_crit, columns=cols, show="headings", selectmode="browse")
        for cid, htext, w in [
            ("rank", "#", 34),
            ("pipe", "Tub.", 48),
            ("tramo", "Tramo", 70),
            ("q_curr", "Q (m³/s)", 76),
            ("q_max", "Qmax", 76),
            ("util", "% Util", 66),
            ("estado", "Estado", 132),
        ]:
            self.tree_critical.heading(cid, text=htext)
            self.tree_critical.column(cid, width=w, anchor="center" if cid in ("rank", "pipe", "tramo") else "e")

        crit_scroll = ttk.Scrollbar(tab_crit, orient=tk.VERTICAL, command=self.tree_critical.yview)
        self.tree_critical.configure(yscrollcommand=crit_scroll.set)
        self.tree_critical.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        crit_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_critical.bind("<<TreeviewSelect>>", self._on_critical_row_select)

        # Tab 3: Evolución Temporal
        tab_charts = ttk.Frame(self.notebook)
        self.notebook.add(tab_charts, text="Evolución")
        self.temporal_charts = TemporalChartsPanel(tab_charts)
        self.temporal_charts.pack(fill=tk.BOTH, expand=True)

        # Tab 4: Comparación de Escenarios
        tab_comp = ttk.Frame(self.notebook)
        self.notebook.add(tab_comp, text="Comparación")

        comp_top = tk.Frame(tab_comp, bg=theme.PLUM_BASE)
        comp_top.pack(fill=tk.X, padx=8, pady=8)
        self._make_btn(
            comp_top,
            "Comparar los 5 Escenarios",
            self._action_compare_scenarios,
            primary=True,
            padx=12,
            pady=5,
            font_size=8,
        ).pack(side=tk.LEFT)

        comp_cols = ("esc", "int", "max_u", "crit_p", "n_crit", "n_over", "ptar")
        self.tree_comp = ttk.Treeview(tab_comp, columns=comp_cols, show="headings", height=6)
        for cid, htext, w in [
            ("esc", "Escenario", 118),
            ("int", "mm/h", 48),
            ("max_u", "Máx %", 64),
            ("crit_p", "Crítica", 54),
            ("n_crit", "≥75%", 50),
            ("n_over", ">100%", 52),
            ("ptar", "Pico PTAR", 76),
        ]:
            self.tree_comp.heading(cid, text=htext)
            self.tree_comp.column(cid, width=w, anchor="center")
        self.tree_comp.pack(fill=tk.X, padx=6, pady=(0, 6))

        self.comparison_charts = ComparisonChartsPanel(tab_comp)
        self.comparison_charts.pack(fill=tk.BOTH, expand=True)

    # --- Lógica de archivos y simulación ---

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
        self.dataset = dataset
        self.engine = SewerSimulationEngine(dataset.graph, dataset.basin)
        self.result = None
        self.comparisons = []

        self.network_canvas.set_graph(dataset.graph)

        scen_labels = [s.display_name for s in dataset.scenarios]
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
        self.status_var.set(
            f"Red cargada: {n_nodes} nodos · {n_pipes} tuberías · {total_len:,.1f} m ({os.path.basename(path)})"
        )
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
        for sc in self.dataset.scenarios:
            if sc.display_name == selected:
                return sc
        return self.dataset.scenarios[0]

    def _build_sim_config(self) -> SimulationConfig:
        sc = self._selected_scenario_obj()
        return SimulationConfig(
            scenario_id=sc.scenario_id,
            scenario_name=sc.condition,
            intensity_mm_h=sc.intensity_mm_h,
            duration_min=max(5.0, float(self.var_duration.get())),
            storm_duration_min=max(0.0, float(self.var_storm_dur.get())),
            dt_min=max(0.25, float(self.var_dt.get())),
            ingress_factor=max(0.001, min(1.0, float(self.var_ingress_pct.get()) / 100.0)),
            dry_weather_flow_per_source_m3s=max(0.0, float(self.var_dry_flow.get())),
            split_rule=self.var_split_rule.get(),
            hyetograph=self.var_hyetograph.get(),
        )

    def run_simulation(self) -> None:
        if self.dataset is None or self.engine is None:
            return
        self._player_pause()
        try:
            cfg = self._build_sim_config()
        except Exception as exc:
            messagebox.showerror("Parámetros inválidos", f"Revise los parámetros numéricos: {exc}")
            return

        self.result = self.engine.run(cfg)
        n_snaps = len(self.result.snapshots)
        self._updating_slider = True
        self.timeline_slider.configure(to=max(0, n_snaps - 1))
        self._updating_slider = False

        target_idx = min(n_snaps - 1, max(1, int(cfg.storm_duration_min / cfg.dt_min)))
        self._set_step(target_idx)
        self.status_var.set(
            f"Escenario {cfg.scenario_id} ({cfg.intensity_mm_h:.0f} mm/h) simulado en "
            f"{self.result.execution_time_ms:.1f} ms · {n_snaps} instantes en LinkedList"
        )

    def _set_step(self, step_idx: int) -> None:
        if self.result is None or not self.result.snapshots:
            return
        step_idx = max(0, min(len(self.result.snapshots) - 1, step_idx))
        self.current_step = step_idx
        snap = self.result.snapshots[step_idx]

        self._updating_slider = True
        self.timeline_slider.set(step_idx)
        self._updating_slider = False

        self.network_canvas.set_snapshot(snap)
        cfg = self.result.config
        self.lbl_clock.configure(
            text=f"t = {snap.time_min:.1f} / {cfg.duration_min:.0f} min  ·  {cfg.scenario_name} ({snap.rain_intensity_mm_h:.0f} mm/h)"
        )
        max_u = max((ps.utilization_pct for ps in snap.pipe_states.values()), default=0.0)
        self.lbl_kpi_summary.configure(
            text=(
                f"Máx Util: {max_u:.1f}%  |  "
                f"Críticas: {len(snap.critical_pipe_ids)}  |  "
                f"Sobrecarg.: {len(snap.overloaded_pipe_ids)}  |  "
                f"PTAR 31: {snap.total_sink_discharge_m3s:.4f} m³/s"
            )
        )
        self.lbl_mass_audit.configure(
            text=f"Balance masa OK · Err {snap.mass_balance_error_m3:.2e} m³"
        )
        self._update_legend_counts(snap)
        self._refresh_critical_table()
        self._refresh_inspector()
        self.temporal_charts.update_plots(self.result, self._selected_pipe_id, snap.time_min)

    def _update_legend_counts(self, snap: TimeStepSnapshot) -> None:
        counts = [0, 0, 0, 0, 0]
        for ps in snap.pipe_states.values():
            counts[ps.category.tier_index] += 1
        for lbl, c in zip(self._legend_count_labels, counts):
            lbl.configure(text=str(c))

    def _on_slider_move(self, val: str) -> None:
        if self._updating_slider:
            return
        self._player_pause()
        self._set_step(int(float(val)))

    def _player_play(self) -> None:
        if self.result is None:
            return
        if self.current_step >= len(self.result.snapshots) - 1:
            self._set_step(0)
        self.is_playing = True
        self._schedule_next_frame()

    def _player_pause(self) -> None:
        self.is_playing = False
        if self._after_id is not None:
            self.after_cancel(self._after_id)
            self._after_id = None

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
            self.is_playing = False
            self._after_id = None
            return
        self._set_step(self.current_step + 1)
        speed_map = {"1x": 420, "2x": 210, "5x": 85, "10x": 40}
        delay = speed_map.get(self.var_speed.get(), 200)
        self._after_id = self.after(delay, self._schedule_next_frame)

    def _on_pipe_selected(self, pipe_id: str) -> None:
        self._selected_pipe_id = pipe_id
        self._selected_node_id = None
        self._refresh_inspector()
        if self.result is not None:
            snap = self.result.snapshots[self.current_step]
            self.temporal_charts.update_plots(self.result, pipe_id, snap.time_min)

    def _on_node_selected(self, node_id: str) -> None:
        self._selected_node_id = node_id
        self._selected_pipe_id = None
        self.var_bfs_start.set(node_id)
        self._refresh_inspector()

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

        exact_pipe = self.dataset.graph.get_pipe(q.upper()) or self.dataset.graph.get_pipe(q)
        exact_node = self.dataset.graph.get_node(q.upper()) or self.dataset.graph.get_node(q)
        if exact_pipe is not None:
            self.network_canvas.select_pipe(exact_pipe.pipe_id)
            self._on_pipe_selected(exact_pipe.pipe_id)
        elif exact_node is not None:
            self.network_canvas.select_node(exact_node.node_id)
            self._on_node_selected(exact_node.node_id)
        elif pipes:
            self.network_canvas.select_pipe(pipes[0].pipe_id)
            self._on_pipe_selected(pipes[0].pipe_id)
        elif nodes:
            self.network_canvas.select_node(nodes[0].node_id)
            self._on_node_selected(nodes[0].node_id)

        self.network_canvas.set_highlights(
            pipe_ids={p.pipe_id for p in pipes},
            node_ids={n.node_id for n in nodes},
        )
        self.status_var.set(f"Búsqueda '{q}': {len(nodes)} nodo(s), {len(pipes)} tubería(s).")

    def _run_traversal(self, alg: str) -> None:
        if self.dataset is None:
            return
        start = self.var_bfs_start.get().strip()
        target = self.var_bfs_target.get().strip() or None
        try:
            res = bfs(self.dataset.graph, start, target) if alg == "BFS" else dfs(self.dataset.graph, start, target)
        except KeyError as exc:
            messagebox.showwarning("Nodo inválido", str(exc))
            return

        if res.path_pipes:
            hl_pipes = {p.pipe_id for p in res.path_pipes}
            hl_nodes = set(res.path_nodes)
        else:
            hl_pipes = {p.pipe_id for p in res.traversed_edges}
            hl_nodes = set(res.visited_order)

        self.network_canvas.set_highlights(hl_pipes, hl_nodes)

        lines = [
            f"[{res.algorithm}] {start} → {target or 'todo'}",
            f"Visitados ({len(res.visited_order)}): {' -> '.join(res.visited_order[:16])}"
            + (" ..." if len(res.visited_order) > 16 else ""),
        ]
        if target:
            if res.target_reached:
                lines.append(f"Camino ({len(res.path_pipes)} tramos): {' -> '.join(res.path_nodes)}")
                lines.append(f"Tuberías: {', '.join(p.pipe_id for p in res.path_pipes)}")
                total_t = sum(p.transit_time_min for p in res.path_pipes)
                lines.append(f"Tránsito acumulado: {total_t:.1f} min")
            else:
                lines.append(f"No hay camino dirigido desde {start} hasta {target}.")

        self._set_traversal_text("\n".join(lines))

    def _run_trace(self, direction: str) -> None:
        if self.dataset is None:
            return
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
        self._set_traversal_text(
            f"[Aguas abajo desde {nid}]\n"
            f"Nodos ({len(nodes)}): {', '.join(nodes)}\n"
            f"Tuberías ({len(pipes)}): {', '.join(p.pipe_id for p in pipes)}"
        )

    def _clear_highlights(self) -> None:
        self.network_canvas.set_highlights(set(), set())
        self._set_traversal_text("")

    def _set_traversal_text(self, text: str) -> None:
        self.txt_traversal.configure(state=tk.NORMAL)
        self.txt_traversal.delete("1.0", tk.END)
        self.txt_traversal.insert("1.0", text)
        self.txt_traversal.configure(state=tk.DISABLED)

    def _refresh_critical_table(self) -> None:
        for item in self.tree_critical.get_children():
            self.tree_critical.delete(item)
        if self.dataset is None or self.result is None:
            return

        snap = self.result.snapshots[self.current_step]
        flows = {pid: ps.flow_m3s for pid, ps in snap.pipe_states.items()}
        utils = {pid: ps.utilization_pct for pid, ps in snap.pipe_states.items()}

        flt = self.var_crit_filter.get()
        min_u = 75.0 if flt == "critical" else (100.0001 if flt == "overloaded" else 0.0)
        ranked = rank_critical_pipes(self.dataset.graph, flows, utils, min_utilization_pct=min_u)

        for rec in ranked:
            self.tree_critical.insert(
                "",
                tk.END,
                iid=rec.pipe_id,
                values=(
                    rec.rank,
                    rec.pipe_id,
                    f"{rec.from_node}→{rec.to_node}",
                    f"{rec.flow_m3s:.4f}",
                    f"{rec.q_max_m3s:.4f}",
                    f"{rec.utilization_pct:.1f}%",
                    rec.category.label,
                ),
            )

    def _on_critical_row_select(self, _event: tk.Event) -> None:
        sel = self.tree_critical.selection()
        if sel:
            pid = sel[0]
            self.network_canvas.select_pipe(pid)
            self._on_pipe_selected(pid)

    def _refresh_inspector(self) -> None:
        lines: List[str] = []
        if self.dataset is None:
            lines.append("Cargue un archivo Excel o carpeta CSV para comenzar.")
        else:
            g = self.dataset.graph
            snap = self.result.snapshots[self.current_step] if self.result else None

            if self._selected_pipe_id and g.has_pipe(self._selected_pipe_id):
                p = g.get_pipe(self._selected_pipe_id)
                assert p is not None
                lines.extend([
                    f"TUBERÍA {p.pipe_id} ({p.from_node} → {p.to_node})",
                    "─" * 42,
                    f"Diámetro        : {p.diameter_in:.0f}\" ({p.diameter_m:.4f} m)",
                    f"Longitud        : {p.length_m:.2f} m",
                    f"Pendiente (S)   : {p.slope:.4f} m/m  |  n: {p.manning_n:.3f}",
                    f"Capacidad Qmax  : {p.q_max_m3s:.5f} m³/s",
                    f"Velocidad ref.  : {p.reference_velocity_ms:.3f} m/s",
                    f"Tiempo tránsito : {p.transit_time_min:.2f} min ({p.transit_time_s:.1f} s)",
                ])
                if p.note:
                    lines.append(f"Marca dataset   : {p.note}")
                if snap and p.pipe_id in snap.pipe_states:
                    ps = snap.pipe_states[p.pipe_id]
                    lines.extend([
                        "",
                        f"Estado en t = {snap.time_min:.1f} min",
                        f"Caudal Q(t)     : {ps.flow_m3s:.5f} m³/s",
                        f"Conducción real : {ps.conveyed_flow_m3s:.5f} m³/s",
                        f"Vol. tránsito   : {ps.volume_in_transit_m3:.2f} m³",
                        f"Utilización O(t): {ps.utilization_pct:.2f} %",
                        f"Clasificación   : {ps.category.label}",
                        f"Exceso sobrec.  : {ps.excess_flow_m3s:.5f} m³/s",
                    ])
                if self.result:
                    lines.append(
                        f"Utilización pico: {self.result.peak_pipe_utilization.get(p.pipe_id, 0.0):.2f} %"
                    )
            elif self._selected_node_id and g.has_node(self._selected_node_id):
                n = g.get_node(self._selected_node_id)
                assert n is not None
                out_p = [e.pipe_id for e in g.outgoing_pipes(n.node_id)]
                in_p = [e.pipe_id for e in g.incoming_pipes(n.node_id)]
                lines.extend([
                    f"NODO {n.node_id} ({n.node_type.upper()})",
                    "─" * 42,
                    f"Tuberías entrantes : {', '.join(in_p) or 'Ninguna (Fuente)'}",
                    f"Tuberías salientes : {', '.join(out_p) or 'Ninguna (PTAR 31)'}",
                ])
                if snap and n.node_id in snap.node_states:
                    ns = snap.node_states[n.node_id]
                    lines.extend([
                        "",
                        f"Estado en t = {snap.time_min:.1f} min",
                        f"Caudal entrada  : {ns.inflow_m3s:.5f} m³/s",
                        f"Caudal salida   : {ns.outflow_m3s:.5f} m³/s",
                        f"Vol. almacenado : {ns.stored_volume_m3:.3f} m³",
                    ])
            else:
                lines.append("Seleccione una tubería o pozo del grafo para inspeccionarlo.")

            lines.extend(["", "RESUMEN DEL ESCENARIO", "─" * 42])
            if self.result and snap:
                cfg = self.result.config
                lines.extend([
                    f"Escenario       : {cfg.scenario_id} — {cfg.scenario_name} ({cfg.intensity_mm_h:.0f} mm/h)",
                    f"Cuenca          : C={self.dataset.basin.runoff_coefficient_c}, A={self.dataset.basin.area_ha} ha",
                    f"Factor ingreso  : {cfg.ingress_factor*100:.1f}%  |  Q_san={cfg.dry_weather_flow_per_source_m3s:.4f} m³/s",
                    f"Entrada acum.   : {snap.cumulative_inflow_m3:,.2f} m³",
                    f"Descarga PTAR 31: {snap.cumulative_sink_discharge_m3:,.2f} m³ (pico {self.result.peak_sink_discharge_m3s:.4f} m³/s)",
                    f"Pozos / Tránsito: {snap.total_manhole_storage_m3:,.2f} / {snap.total_pipe_transit_m3:,.2f} m³",
                    f"Error balance   : {self.result.max_mass_balance_error_m3:.3e} m³",
                    f"Críticas (≥75%) : {len(self.result.ever_critical_pipes)} tuberías",
                    f"Sobrec. (>100%) : {len(self.result.ever_overloaded_pipes)} tuberías",
                ])

        self.txt_inspector.configure(state=tk.NORMAL)
        self.txt_inspector.delete("1.0", tk.END)
        self.txt_inspector.insert("1.0", "\n".join(lines))
        self.txt_inspector.configure(state=tk.DISABLED)

    def _action_compare_scenarios(self) -> None:
        if self.dataset is None:
            return
        cfg = self._build_sim_config()
        self.comparisons = compare_all_scenarios(self.dataset, cfg)

        for item in self.tree_comp.get_children():
            self.tree_comp.delete(item)
        for s in self.comparisons:
            self.tree_comp.insert(
                "",
                tk.END,
                values=(
                    f"E{s.scenario_id} {s.condition}",
                    f"{s.intensity_mm_h:.0f}",
                    f"{s.max_utilization_pct:.1f}%",
                    s.most_critical_pipe,
                    s.num_critical_pipes,
                    s.num_overloaded_pipes,
                    f"{s.peak_sink_discharge_m3s:.4f}",
                ),
            )
        self.comparison_charts.update_comparison(self.comparisons)
        self.status_var.set("Comparación de los 5 escenarios completada.")
