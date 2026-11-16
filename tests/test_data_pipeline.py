import unittest
from pathlib import Path

from src.data_pipeline import has_telemetry_schema, load_telemetry


DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class DataPipelineTests(unittest.TestCase):
    def test_reference_catalog_is_not_telemetry(self):
        self.assertFalse(has_telemetry_schema(str(DATA_DIR / "osdr_catalog.csv")))
        self.assertTrue(has_telemetry_schema(str(DATA_DIR / "demo_stress_arc.csv")))

    def test_loading_reference_catalog_reports_missing_telemetry_columns(self):
        with self.assertRaisesRegex(ValueError, "faltan columnas:.*timestamp"):
            load_telemetry(str(DATA_DIR / "osdr_catalog.csv"))


if __name__ == "__main__":
    unittest.main()
