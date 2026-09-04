from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import torch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flood_app.config import load_config
from flood_app.models import load_model, predict


class ConfigAndModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(ROOT / "config/regions.json", ROOT)

    def test_expected_regions_and_notebook_parameters(self):
        umap = self.config["regions"]["umap"]
        wlc = self.config["regions"]["wlc"]
        self.assertEqual((umap["input_len"], umap["pred_len"]), (7, 3))
        self.assertEqual((umap["hidden_dim"], umap["num_layers"]), (32, 1))
        self.assertEqual((wlc["input_len"], wlc["pred_len"]), (9, 3))
        self.assertEqual((wlc["hidden_dim"], wlc["num_layers"]), (16, 3))

    def test_both_trained_state_dicts_load_strictly_and_infer(self):
        device = torch.device("cpu")
        for region_id in ("umap", "wlc"):
            with self.subTest(region=region_id):
                region = self.config["regions"][region_id]
                model = load_model(region, device)
                values = torch.zeros(
                    int(region["input_len"]), 8, 9, int(region["input_dim"])
                ).numpy()
                output = predict(
                    model,
                    values,
                    int(region["input_len"]),
                    int(region["pred_len"]),
                    device,
                )
                self.assertEqual(output.shape, (3, 8, 9))
                self.assertTrue(((output >= 0) & (output <= 1)).all())


if __name__ == "__main__":
    unittest.main()
