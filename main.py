"""Punto de entrada principal del Simulador de Alcantarillado de Ciudad Bicentenario."""

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulación y visualización de la red de alcantarillado de Ciudad Bicentenario."
    )
    parser.add_argument(
        "--data",
        help="Ruta opcional a DataSetBicentenario.xlsx o carpeta CSV.",
        default=None,
    )
    parser.add_argument(
        "--report",
        help="Ejecuta los 5 escenarios en modo CLI y exporta un reporte Markdown en la ruta indicada.",
        default=None,
    )
    parser.add_argument(
        "--report-docx",
        help="Genera un reporte Word (.docx) a dos columnas con ecuaciones OMML en la ruta indicada.",
        default=None,
    )
    parser.add_argument(
        "--technical-docx",
        help="Genera el Documento Técnico completo (.docx) a dos columnas con Anexos A-D.",
        default=None,
    )
    args = parser.parse_args()

    if args.report or args.report_docx or args.technical_docx:
        from src.io.data_loader import DataLoadError, load_dataset
        from src.simulation import (
            SimulationConfig,
            compare_all_scenarios,
            generate_docx_report,
            generate_markdown_report,
            generate_technical_document_docx,
        )

        data_path = args.data or os.path.join(
            os.path.dirname(__file__), "data", "DataSetBicentenario.xlsx"
        )
        try:
            dataset = load_dataset(data_path)
            base_cfg = SimulationConfig(
                scenario_id=3,
                scenario_name="Moderate rain",
                intensity_mm_h=30.0,
            )
            summaries = compare_all_scenarios(dataset, base_cfg)
            primary = summaries[2] if len(summaries) > 2 else summaries[0]

            if args.report:
                out = generate_markdown_report(
                    dataset, primary.result, summaries, args.report
                )
                print(f"Reporte Markdown generado en: {out}")
            if args.report_docx:
                out = generate_docx_report(
                    dataset, primary.result, summaries, args.report_docx
                )
                print(f"Reporte Word (.docx) generado en: {out}")
            if args.technical_docx:
                out = generate_technical_document_docx(
                    dataset, summaries, args.technical_docx
                )
                print(f"Documento Técnico (.docx) generado en: {out}")
        except (DataLoadError, OSError, ValueError) as exc:
            print(f"Error en modo CLI: {exc}", file=sys.stderr)
            return 1
        return 0

    from src.gui import launch_gui

    return launch_gui(initial_data_path=args.data)


if __name__ == "__main__":
    sys.exit(main())
