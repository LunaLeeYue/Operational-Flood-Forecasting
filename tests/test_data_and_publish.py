from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import xarray as xr


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flood_app.data import preprocess
from flood_app.publish import publish_region


class DataAndPublishTests(unittest.TestCase):
    def test_preprocess_matches_training_codebook(self):
        encoded = np.array(
            [[
                [99, 150, 15, 30],
                [1, 50, 200, 38],
            ]],
            dtype=np.float32,
        )
        raw = xr.Dataset(
            {"water_fraction": (("time", "lat", "lon"), encoded)},
            coords={"time": [np.datetime64("2026-01-01")], "lat": [1.0, 0.0], "lon": range(4)},
        )
        result = preprocess(raw).values
        np.testing.assert_allclose(result[0, 0, :, 0], [1.0, 0.5, 0.0, -1.0])
        np.testing.assert_allclose(result[0, 1, :, 0], [-1.0, -1.0, 1.0, 0.0])
        np.testing.assert_allclose(result[0, :, :, 1], [[0, 0, 0, 1], [1, 1, 0, 0]])

    def test_static_assets_and_metadata_are_written(self):
        raw = xr.Dataset(
            {
                "water_fraction": (
                    ("time", "lat", "lon"),
                    np.zeros((2, 4, 5), dtype=np.float32),
                )
            },
            coords={
                "time": [np.datetime64("2026-01-01"), np.datetime64("2026-01-02")],
                "lat": np.linspace(2, 1, 4),
                "lon": np.linspace(3, 4, 5),
            },
        )
        region = {
            "name": "Test",
            "pred_len": 3,
            "center": [1.5, 3.5],
            "zoom": 8,
            "model_label": "test model",
            "architecture": "single_layer",
            "input_len": 2,
        }
        predictions = np.full((3, 4, 5), 0.8, dtype=np.float32)
        mask = np.ones((4, 5), dtype=bool)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            metadata = publish_region("test", region, raw, predictions, mask, output)
            self.assertEqual(metadata["prediction_dates"], ["2026-01-03", "2026-01-04", "2026-01-05"])
            self.assertTrue((output / "test/latest.json").is_file())
            self.assertTrue((output / "test/maps/day-1.png").is_file())
            self.assertTrue((output / "test/points/day-1.geojson").is_file())
            with (output / "test/points/day-1.geojson").open(encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["type"], "FeatureCollection")


if __name__ == "__main__":
    unittest.main()
