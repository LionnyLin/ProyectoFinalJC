"""Pruebas unitarias para carga y validación desde Excel y CSV."""

import os
import tempfile
import unittest

from src.io.data_loader import DataLoadError, load_dataset


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_XLSX = os.path.join(BASE_DIR, "data", "DataSetBicentenario.xlsx")
DATA_CSV = os.path.join(BASE_DIR, "data", "csv")


class TestLoader(unittest.TestCase):
    def test_excel_and_csv_parity(self) -> None:
        ds_xlsx = load_dataset(DATA_XLSX)
        ds_csv = load_dataset(DATA_CSV)

        self.assertEqual(ds_xlsx.graph.summary()[:4], (46, 59, 8, 1))
        self.assertAlmostEqual(ds_xlsx.graph.total_network_length_m(), 19163.57, places=2)
        self.assertEqual(ds_xlsx.graph.summary()[:4], ds_csv.graph.summary()[:4])
        self.assertAlmostEqual(
            ds_xlsx.graph.total_network_length_m(),
            ds_csv.graph.total_network_length_m(),
            places=2,
        )
        self.assertEqual(len(ds_xlsx.scenarios), 5)
        self.assertEqual(len(ds_csv.scenarios), 5)
        self.assertAlmostEqual(ds_xlsx.basin.runoff_coefficient_c, 0.75)
        self.assertAlmostEqual(ds_xlsx.basin.area_ha, 388.0)

    def test_missing_or_invalid_path_raises(self) -> None:
        with self.assertRaises(DataLoadError):
            load_dataset("no_existe.xlsx")

        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(DataLoadError):
                load_dataset(tmpdir)


if __name__ == "__main__":
    unittest.main()
