from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED_REGION_FIELDS = {
    "name",
    "center",
    "zoom",
    "tiles",
    "aoi_path",
    "mask_path",
    "model_path",
    "architecture",
    "input_len",
    "pred_len",
    "input_dim",
    "hidden_dim",
    "output_dim",
    "kernel_size",
    "num_layers",
    "dropout_rate",
}


def load_config(config_path: Path, repo_root: Path) -> dict[str, Any]:
    """Load and validate the deployment configuration.

    Asset paths are resolved relative to the deployment repository so the
    pipeline behaves identically locally and on a GitHub Actions runner.
    """
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)

    if "source" not in config or "regions" not in config:
        raise ValueError("Configuration must contain 'source' and 'regions'")

    for region_id, region in config["regions"].items():
        missing = REQUIRED_REGION_FIELDS.difference(region)
        if missing:
            raise ValueError(f"Region {region_id!r} is missing: {sorted(missing)}")
        if region["architecture"] not in {"single_layer", "stacked"}:
            raise ValueError(f"Unsupported architecture for {region_id}")
        if int(region["input_len"]) < 1 or int(region["pred_len"]) < 1:
            raise ValueError(f"Invalid temporal lengths for {region_id}")

        for key in ("aoi_path", "mask_path", "model_path"):
            path = (repo_root / region[key]).resolve()
            if not path.is_file():
                raise FileNotFoundError(f"Missing {region_id} {key}: {path}")
            region[key] = str(path)

    return config
