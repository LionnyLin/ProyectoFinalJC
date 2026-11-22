"""Pruebas unitarias para el exportador Word (.docx) y figuras 3.5 x 2.8 in."""

import os
import tempfile
import unittest
import zipfile

from lxml import etree
from PIL import Image

from src.io.data_loader import load_dataset
from src.simulation import (
    SimulationConfig,
    compare_all_scenarios,
    generate_docx_report,
    generate_technical_document_docx,
)
from src.simulation.charts_export import generate_single_column_figures
from src.simulation.models import compute_symlog_ticks

DATA_XLSX = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "data", "DataSetBicentenario.xlsx")
)
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


class TestDocxExporter(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.dataset = load_dataset(DATA_XLSX)
        cls.summaries = compare_all_scenarios(
            cls.dataset,
            SimulationConfig(scenario_id=3, scenario_name="Moderate rain", intensity_mm_h=30.0),
        )

    def _assert_docx_rules(self, docx_path: str, expected_min_omml: int) -> None:
        with zipfile.ZipFile(docx_path, "r") as z:
            doc_xml = z.read("word/document.xml")
            media_files = [n for n in z.namelist() if n.startswith("word/media/")]

        root = etree.fromstring(doc_xml)

        # 1. Diseño continuo a dos columnas en todas las secciones
        sect_prs = root.findall(f".//{{{W_NS}}}sectPr")
        self.assertGreaterEqual(len(sect_prs), 1)
        for sp in sect_prs:
            cols = sp.find(f"{{{W_NS}}}cols")
            self.assertIsNotNone(cols)
            self.assertEqual(cols.get(f"{{{W_NS}}}num"), "2")

        # 2. Ecuaciones OMML centradas y escaladas a 8.5 pt (w:sz = 17)
        omath_paras = root.findall(f".//{{{M_NS}}}oMathPara")
        self.assertGreaterEqual(len(omath_paras), expected_min_omml)
        for omp in omath_paras:
            jc = omp.find(f"{{{M_NS}}}oMathParaPr/{{{M_NS}}}jc")
            self.assertIsNotNone(jc)
            self.assertEqual(jc.get(f"{{{M_NS}}}val"), "center")
            for mr in omp.findall(f".//{{{M_NS}}}r"):
                sz = mr.find(f"{{{W_NS}}}rPr/{{{W_NS}}}sz")
                self.assertIsNotNone(sz)
                self.assertEqual(sz.get(f"{{{W_NS}}}val"), "17")

        # 3. Tablas exclusivamente en texto plano (cero OMML y cero '$')
        tables = root.findall(f".//{{{W_NS}}}tbl")
        self.assertGreater(len(tables), 0)
        for tbl in tables:
            self.assertEqual(len(tbl.findall(f".//{{{M_NS}}}oMath")), 0)
            texts = "".join(t.text or "" for t in tbl.findall(f".//{{{W_NS}}}t"))
            self.assertNotIn("$", texts)

        # 4. Figuras embebidas
        self.assertGreaterEqual(len(media_files), 2)

    def test_single_column_figures_exact_dimensions(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            paths = generate_single_column_figures(
                self.summaries[2].result, self.summaries, td
            )
            self.assertEqual(len(paths), 3)
            for p in paths:
                with Image.open(p) as im:
                    self.assertEqual(im.size, (1050, 840))  # 3.5 x 2.8 in @ 300 DPI

    def test_generate_docx_report_and_technical_document(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            rep_path = os.path.join(td, "reporte.docx")
            tech_path = os.path.join(td, "DOCUMENTO_TECNICO.docx")

            out1 = generate_docx_report(
                self.dataset, self.summaries[2].result, self.summaries, rep_path
            )
            out2 = generate_technical_document_docx(
                self.dataset, self.summaries, tech_path
            )
            self.assertTrue(os.path.isfile(out1))
            self.assertTrue(os.path.isfile(out2))

            self._assert_docx_rules(out1, expected_min_omml=6)
            self._assert_docx_rules(out2, expected_min_omml=7)

    def test_symlog_ticks_coverage(self) -> None:
        for peak, min_top in ((420.0, 250.0), (5126.0, 2500.0), (16560.0, 10000.0)):
            ticks = compute_symlog_ticks(peak)
            self.assertIn(0.0, ticks)
            self.assertIn(100.0, ticks)
            self.assertGreaterEqual(max(ticks), min_top)
            self.assertGreaterEqual(len(ticks), 4)


if __name__ == "__main__":
    unittest.main()
