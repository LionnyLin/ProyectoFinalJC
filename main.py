"""Punto de entrada principal del Simulador de Alcantarillado de Ciudad Bicentenario."""

import argparse
import os
import sys

DEFAULT_DATA_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "DataSetBicentenario.xlsx"
)


def _run_cli_reports(data_path: str, report_md: str | None, report_docx: str | None) -> int:
    """Ejecuta los 5 escenarios en modo CLI y exporta los reportes solicitados."""
    from src.io.data_loader import DataLoadError, load_dataset
    from src.simulation import (
        SimulationConfig, compare_all_scenarios, generate_docx_report, generate_markdown_report,
    )

    try:
        dataset = load_dataset(data_path)
        base_cfg = SimulationConfig(scenario_id=3, scenario_name="Moderate rain", intensity_mm_h=30.0)
        summaries = compare_all_scenarios(dataset, base_cfg)
        primary = summaries[2] if len(summaries) > 2 else summaries[0]

        if report_md:
            out = generate_markdown_report(dataset, primary.result, summaries, report_md)
            print(f"Reporte Markdown generado en: {out}")
        if report_docx:
            out = generate_docx_report(dataset, primary.result, summaries, report_docx)
            print(f"Reporte Word (.docx) generado en: {out}")
    except (DataLoadError, OSError, ValueError) as exc:
        print(f"Error en modo CLI: {exc}", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulación y visualización de la red de alcantarillado de Ciudad Bicentenario."
    )
    parser.add_argument(
        "--data", default=DEFAULT_DATA_PATH,
        help="Ruta a DataSetBicentenario.xlsx o carpeta CSV (por defecto data/DataSetBicentenario.xlsx).",
    )
    parser.add_argument(
        "--report", default=None,
        help="Ejecuta comparación de 5 escenarios y genera reporte Markdown + CSV hermano.",
    )
    parser.add_argument(
        "--report-docx", default=None,
        help="Ejecuta comparación de 5 escenarios y genera un reporte Word (.docx).",
    )
    args = parser.parse_args()

    if args.report or args.report_docx:
        return _run_cli_reports(args.data, args.report, args.report_docx)

    from src.gui.theme import enable_dpi_awareness
    from src.gui import BicentenarioSewerApp

    enable_dpi_awareness()
    app = BicentenarioSewerApp(initial_data_path=args.data)
    app.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
