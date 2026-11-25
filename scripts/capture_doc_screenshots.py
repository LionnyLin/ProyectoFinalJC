"""Generador reproducible de capturas de pantalla para la documentación técnica (PySide6).

Produce 24 capturas en `docs/screenshots/` combinando:
- Vistas globales de ventana (1280x740)
- Recortes enfocados de paneles/widgets con QWidget.grab() multiplataforma
- Tarjetas terminales compactas de ejecución real (CSV, CLI y pruebas unitarias)
"""

import os
import subprocess
import sys
import tempfile
import time
from typing import Dict, List

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtWidgets import QApplication, QWidget

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

SHOT_DIR = os.path.join(ROOT, "docs", "screenshots")
os.makedirs(SHOT_DIR, exist_ok=True)


def _pump(ms: int = 120) -> None:
    app = QApplication.instance()
    if app is None:
        return
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.015)


def _goto_step(app, target_min: float) -> None:
    app.pause()
    if not app.state.result or not app.state.result.snapshots:
        return
    best_i = min(
        range(len(app.state.result.snapshots)),
        key=lambda idx: abs(app.state.result.snapshots[idx].time_min - target_min),
    )
    app._set_step(best_i)
    _pump(80)


def _set_scenario_and_run(app, scenario_idx_0_based: int, target_min: float = 35.0) -> None:
    from src.gui import theme as gui_theme

    if app.state.dataset and 0 <= scenario_idx_0_based < len(app.state.dataset.scenarios):
        sc = app.state.dataset.scenarios[scenario_idx_0_based]
        app.controls_panel.set_scenario_text(
            gui_theme.format_scenario_display(sc.scenario_id, sc.condition, sc.intensity_mm_h)
        )
    app.run_simulation(auto_play=False)
    _goto_step(app, target_min)


def _grab_widget(widget: QWidget, filename: str, wait_ms: int = 250) -> str:
    _pump(wait_ms)
    path = os.path.join(SHOT_DIR, filename)
    pm = widget.grab()
    pm.save(path, "PNG")
    print(f"Captured {filename} ({pm.width()}x{pm.height()})")
    return path


def _render_terminal_card(title: str, lines: List[str], filename: str) -> str:
    font = ImageFont.load_default()
    title_font = font
    for cand in (
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        r"C:\Windows\Fonts\consola.ttf",
    ):
        if os.path.isfile(cand):
            try:
                font = ImageFont.truetype(cand, 14)
                title_font = ImageFont.truetype(cand, 15)
                break
            except Exception:
                pass

    pad_x, pad_y = 18, 16
    line_h = 20
    w = 880
    h = 44 + len(lines) * line_h + pad_y * 2

    img = Image.new("RGB", (w, h), (22, 27, 34))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), (w, 36)], fill=(33, 38, 45))
    draw.ellipse([(12, 11), (24, 23)], fill=(255, 95, 86))
    draw.ellipse([(32, 11), (44, 23)], fill=(255, 189, 46))
    draw.ellipse([(52, 11), (64, 23)], fill=(39, 201, 63))
    draw.text((78, 9), title, font=title_font, fill=(230, 237, 243))

    y = 44
    for line in lines:
        color = (201, 209, 217)
        if line.endswith("... ok") or "OK" in line or "passed" in line or "Generado" in line or "bytes)" in line:
            color = (126, 231, 135)
        elif line.startswith("$") or line.startswith(">"):
            color = (121, 192, 255)
        draw.text((pad_x, y), line[:98], font=font, fill=color)
        y += line_h

    path = os.path.join(SHOT_DIR, filename)
    img.save(path)
    print(f"Rendered terminal card {filename} ({w}x{h})")
    return path


def capture_all_screenshots() -> Dict[str, str]:
    from src.gui import theme as gui_theme
    from src.gui.app import BicentenarioSewerApp, ensure_qapplication
    from src.io.data_loader import export_to_csv_dir, load_dataset

    ensure_qapplication()
    data_path = os.path.join(ROOT, "data", "DataSetBicentenario.xlsx")
    app = BicentenarioSewerApp(initial_data_path=data_path)
    app.resize(1280, 740)
    app.show()
    _pump(350)
    app.pause()

    shots: Dict[str, str] = {}

    # 00. Vista general sistema (Esc. 3, t = 35 min)
    _set_scenario_and_run(app, 2, target_min=35.0)
    shots["00_vista_general"] = _grab_widget(app, "00_vista_general.png")

    # 01_1. Sub-pasos continuos con PriorityQueue (Esc. 3, t = 35 min)
    shots["01_1_subpasos_transit"] = _grab_widget(app.center_panel, "01_1_subpasos_transit.png")

    # 01_2. Almacenamiento finito 4.0 m3 + rebose superficial (Esc. 5, t = 45 min)
    _set_scenario_and_run(app, 4, target_min=45.0)
    snap = app.state.current_snapshot()
    flood_node = max(snap.node_states.items(), key=lambda kv: kv[1].surface_flooding_m3)[0]
    app._on_node_selected(flood_node)
    app.right_tabs.setCurrentIndex(0)
    _goto_step(app, 45.0)
    shots["01_2_almacenamiento_rebose"] = _grab_widget(app.right_panel, "01_2_almacenamiento_rebose.png")

    # 01_3a. Intervención en vivo (P29 al 80 % en t = 40 min)
    _set_scenario_and_run(app, 2, target_min=40.0)
    app._on_pipe_selected("P29")
    app.inspector_panel.set_obstruction_pct(80.0)
    app._action_apply_intervention(80.0, app.inspector_panel.combo_diam_override.currentText())
    _goto_step(app, 40.0)
    app.right_tabs.setCurrentIndex(0)
    shots["01_3a_intervencion_mapa"] = _grab_widget(app.network_canvas, "01_3a_intervencion_mapa.png")

    # 01_3b. Hidrograma comparativo Antes vs Después
    app.right_tabs.setCurrentIndex(2)
    app.temporal_charts.set_subtab("hydro")
    _goto_step(app, 40.0)
    shots["01_3b_antes_despues"] = _grab_widget(app.temporal_charts, "01_3b_antes_despues.png", wait_ms=350)

    app._action_restore_all_interventions()
    app.right_tabs.setCurrentIndex(0)

    # 01_4. Reglas configurables desde la GUI (recorte panel Controles)
    app.controls_panel.combo_split_rule.setCurrentText(gui_theme.SPLIT_RULE_TO_ES["equal"])
    app.controls_panel.combo_source_dist.setCurrentText(gui_theme.SOURCE_DIST_TO_ES["equal"])
    app.controls_panel.apply_preset(2.5, 0.003)
    app.run_simulation(auto_play=False)
    _goto_step(app, 35.0)
    shots["01_4_reglas_gui"] = _grab_widget(app.controls_panel, "01_4_reglas_gui.png")

    app.controls_panel.apply_preset(100.0, 0.0)
    app.controls_panel.combo_split_rule.setCurrentText(gui_theme.SPLIT_RULE_TO_ES["proportional"])
    app.controls_panel.combo_source_dist.setCurrentText(gui_theme.SOURCE_DIST_TO_ES["capacity"])
    app.run_simulation(auto_play=False)
    _goto_step(app, 35.0)

    # 02_1a & 02_1b. Animación BFS (Queue) y DFS (Stack)
    app.controls_panel.switch_rail_tab("trav")
    app._run_traversal("BFS")
    app._action_toggle_traversal_anim()
    for _ in range(7):
        app._step_traversal_anim()
    shots["02_1a_bfs_queue"] = _grab_widget(app, "02_1a_bfs_queue.png")

    app._stop_traversal_anim(clear_canvas=True)
    app._run_traversal("DFS")
    app._action_toggle_traversal_anim()
    for _ in range(9):
        app._step_traversal_anim()
    shots["02_1b_dfs_stack"] = _grab_widget(app, "02_1b_dfs_stack.png")

    app._stop_traversal_anim(clear_canvas=True)
    app.controls_panel.switch_rail_tab("sim")

    # 02_2. Trazado Aguas arriba + Aislar cuenca
    app._on_node_selected("K")
    app._action_toggle_inspector_trace("up")
    app._action_toggle_basin_isolation()
    _goto_step(app, 35.0)
    shots["02_2_aguas_arriba_aislar"] = _grab_widget(app, "02_2_aguas_arriba_aislar.png")
    app._clear_highlights()

    # 02_3. Detección de nodos desconectados (P29 al 100 % en t = 40 min)
    app._on_pipe_selected("P29")
    app._action_apply_intervention(100.0, app.inspector_panel.combo_diam_override.currentText())
    _goto_step(app, 40.0)
    shots["02_3_nodos_desconectados"] = _grab_widget(app, "02_3_nodos_desconectados.png")
    app._action_restore_all_interventions()

    # 02_4. Composición por fuente aportante (Nodo 30 en Inspector)
    _set_scenario_and_run(app, 2, target_min=40.0)
    app._on_node_selected("30")
    app.right_tabs.setCurrentIndex(0)
    _goto_step(app, 40.0)
    shots["02_4_composicion_fuentes"] = _grab_widget(app.right_panel, "02_4_composicion_fuentes.png")

    # 02_5. Persistencia de sobrecarga (Tuberías Críticas en Esc. 5)
    _set_scenario_and_run(app, 4, target_min=45.0)
    app._set_map_mode("overload_minutes")
    app.right_tabs.setCurrentIndex(1)
    shots["02_5_persistencia_sobrecarga"] = _grab_widget(app.right_panel, "02_5_persistencia_sobrecarga.png")
    app.right_tabs.setCurrentIndex(0)

    # 03_1a, b, c. 3 Modos cartográficos en Esc. 5
    app._set_map_mode("instant")
    _goto_step(app, 45.0)
    shots["03_1a_modo_instantaneo"] = _grab_widget(app, "03_1a_modo_instantaneo.png")

    app._set_map_mode("peak")
    shots["03_1b_modo_pico"] = _grab_widget(app, "03_1b_modo_pico.png")

    app._set_map_mode("overload_minutes")
    shots["03_1c_modo_sobrecarga"] = _grab_widget(app, "03_1c_modo_sobrecarga.png")

    # 03_2. NetworkCanvas avanzado (zoom en confluencia 30-D-G-31 con rebose en t = 45 min)
    app._set_map_mode("instant")
    _goto_step(app, 45.0)
    cw = app.network_canvas.width()
    ch = app.network_canvas.height()
    app.network_canvas._zoom_at(cw * 0.38, ch * 0.65, 1.85)
    shots["03_2_canvas_zoom_rebose"] = _grab_widget(app.network_canvas, "03_2_canvas_zoom_rebose.png")
    app.network_canvas.reset_view()

    # 03_3a & 03_3b. Gráficas avanzadas (Hidrograma twinx + Perfil longitudinal)
    _set_scenario_and_run(app, 2, target_min=40.0)
    app.right_tabs.setCurrentIndex(2)
    app.temporal_charts.set_subtab("hydro")
    _goto_step(app, 40.0)
    shots["03_3a_hidrograma_twinx"] = _grab_widget(app.temporal_charts, "03_3a_hidrograma_twinx.png", wait_ms=350)
    app.temporal_charts.set_subtab("profile")
    _goto_step(app, 40.0)
    shots["03_3b_perfil_longitudinal"] = _grab_widget(app.temporal_charts, "03_3b_perfil_longitudinal.png", wait_ms=350)
    app.right_tabs.setCurrentIndex(0)

    # 03_4. Recorrido Guiado (Esc. 5, parada 2)
    _set_scenario_and_run(app, 4, target_min=45.0)
    app.toggle_guided_tour()
    app._go_tour_stop(1, animate_cam=False)
    shots["03_4_recorrido_guiado"] = _grab_widget(app, "03_4_recorrido_guiado.png", wait_ms=350)
    app._close_guided_tour(reset_view=True)

    # 03_5a. Comparación 5 escenarios
    app.right_tabs.setCurrentIndex(3)
    app.wait_for_background_tasks(8000)
    _pump(200)
    shots["03_5a_comparacion_escenarios"] = _grab_widget(app, "03_5a_comparacion_escenarios.png", wait_ms=350)

    # 03_5b. UI responsiva modo compacto
    app.resize(900, 700)
    app.right_tabs.setCurrentIndex(0)
    shots["03_5b_ui_compacta"] = _grab_widget(app, "03_5b_ui_compacta.png", wait_ms=350)

    app.close()

    # 04_1. Carga dual .xlsx + .csv y exportación a CSV
    ds = load_dataset(data_path)
    with tempfile.TemporaryDirectory() as td:
        csv_dir = os.path.join(td, "csv_export")
        export_to_csv_dir(ds, csv_dir)
        csv_lines = [
            "$ python -c \"export_to_csv_dir(load_dataset('DataSetBicentenario.xlsx'), 'csv_export')\"",
            f"Red validada (DAG): {ds.graph.num_nodes} nodos, {ds.graph.num_pipes} tuberias, {len(ds.scenarios)} escenarios",
            "Archivos CSV generados:",
        ] + [
            f"  - {fn:<30} ({os.path.getsize(os.path.join(csv_dir, fn)):>6,} bytes)"
            for fn in sorted(os.listdir(csv_dir))
        ]
    shots["04_1_carga_export_csv"] = _render_terminal_card(
        "4.1 Carga Dual .xlsx + .csv y Exportacion CSV", csv_lines, "04_1_carga_export_csv.png"
    )

    # 04_2. Generación automática por CLI (main.py)
    with tempfile.TemporaryDirectory() as td:
        md_p = os.path.join(td, "REPORTE_ESCENARIOS.md")
        docx_p = os.path.join(td, "REPORTE_ESCENARIOS.docx")
        tech_p = os.path.join(td, "DOCUMENTO_TECNICO.docx")
        proc_cli = subprocess.run(
            [sys.executable, os.path.join(ROOT, "main.py"), "--report", md_p, "--report-docx", docx_p, "--technical-docx", tech_p],
            cwd=ROOT, capture_output=True, text=True, timeout=90,
        )
        cli_lines = [
            "$ python main.py --report REPORTE.md --report-docx REPORTE.docx --technical-docx DOC.docx",
            f"Exit code: {proc_cli.returncode} (Generacion pura Python sin Pandoc)",
        ] + [l for l in (proc_cli.stdout or "").splitlines()[:6]] + [
            "Artefactos generados:"
        ] + [
            f"  - {fn:<35} ({os.path.getsize(os.path.join(td, fn)):>7,} bytes)"
            for fn in sorted(os.listdir(td)) if os.path.isfile(os.path.join(td, fn))
        ]
    shots["04_2_cli_reportes"] = _render_terminal_card(
        "4.2 Generacion Automatica CLI (main.py)", cli_lines, "04_2_cli_reportes.png"
    )

    # 04_3. Suite de pruebas unitarias
    env = dict(os.environ)
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    proc_test = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=150,
    )
    test_lines = (proc_test.stdout + "\n" + proc_test.stderr).strip().splitlines()
    if len(test_lines) > 22:
        shown = test_lines[:12] + ["  ... (pruebas intermedias omitidas) ..."] + test_lines[-8:]
    else:
        shown = test_lines
    shots["04_3_tests_41"] = _render_terminal_card(
        "4.3 Suite de Pruebas Unitarias (unittest)",
        ["$ python -m unittest discover -s tests -v"] + shown,
        "04_3_tests_41.png",
    )

    return shots


if __name__ == "__main__":
    capture_all_screenshots()
