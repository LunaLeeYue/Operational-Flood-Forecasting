#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from datetime import date
from pathlib import Path

import torch
import xarray as xr


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from flood_app.config import load_config  # noqa: E402
from flood_app.data import NoaaVfmClient, align_mask, preprocess  # noqa: E402
from flood_app.models import load_model, predict  # noqa: E402
from flood_app.publish import publish_catalog, publish_region  # noqa: E402


def parse_raw_inputs(values: list[str]) -> dict[str, Path]:
    parsed = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--raw-input must use REGION=PATH")
        region_id, path = value.split("=", 1)
        parsed[region_id] = Path(path).expanduser().resolve()
    return parsed


def open_raw_input(path: Path, input_len: int) -> xr.Dataset:
    if not path.is_file():
        raise FileNotFoundError(path)
    dataset = xr.open_dataset(path).load()
    if "water_fraction" not in dataset:
        dataset.close()
        raise ValueError(f"{path} does not contain water_fraction")
    if dataset.sizes.get("time") != input_len:
        dataset.close()
        raise ValueError(
            f"{path} has {dataset.sizes.get('time')} days; expected {input_len}"
        )
    return dataset


def choose_device(requested: str) -> torch.device:
    if requested == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is unavailable")
    return torch.device(requested)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate the daily static flood forecast site data")
    parser.add_argument("--config", type=Path, default=REPO_ROOT / "config/regions.json")
    parser.add_argument("--output", type=Path, default=REPO_ROOT / "site/data")
    parser.add_argument("--cache", type=Path, default=REPO_ROOT / "runtime/noaa-cache")
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--region", action="append", default=[], help="Only run this region; repeatable")
    parser.add_argument(
        "--raw-input",
        action="append",
        default=[],
        metavar="REGION=PATH",
        help="Use an existing raw NetCDF instead of NOAA (for validation)",
    )
    parser.add_argument("--reference-date", type=date.fromisoformat)
    args = parser.parse_args()

    config = load_config(args.config.resolve(), REPO_ROOT)
    selected_regions = args.region or list(config["regions"])
    unknown = set(selected_regions).difference(config["regions"])
    if unknown:
        raise ValueError(f"Unknown regions: {sorted(unknown)}")

    raw_inputs = parse_raw_inputs(args.raw_input)
    device = choose_device(args.device)
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    print(f"Inference device: {device}; torch threads: {torch.get_num_threads()}")

    source = config["source"]
    client = None
    results = {}
    for region_id in selected_regions:
        region = config["regions"][region_id]
        print(f"\n=== {region['name']} ({region_id}) ===")
        if region_id in raw_inputs:
            raw_data = open_raw_input(raw_inputs[region_id], int(region["input_len"]))
            print(f"Using validation input: {raw_inputs[region_id]}")
        else:
            if client is None:
                client = NoaaVfmClient(
                    bucket=source["bucket"],
                    base_path=source["base_path"],
                    cache_dir=args.cache.resolve(),
                )
            raw_data = client.fetch_region(
                region,
                lookback_days=int(source["lookback_days"]),
                reference_date=args.reference_date,
            )

        try:
            processed = preprocess(raw_data)
            model = load_model(region, device)
            predictions = predict(
                model=model,
                processed_values=processed.values,
                input_len=int(region["input_len"]),
                pred_len=int(region["pred_len"]),
                device=device,
            )
            mask = align_mask(Path(region["mask_path"]), processed)
            if mask.shape != predictions.shape[1:]:
                raise ValueError(
                    f"Aligned mask {mask.shape} does not match prediction {predictions.shape[1:]}"
                )
            results[region_id] = publish_region(
                region_id,
                region,
                raw_data,
                predictions,
                mask,
                args.output.resolve(),
            )
            print(
                f"Published {region_id}: observation "
                f"{results[region_id]['latest_observation_date']} -> "
                f"{results[region_id]['prediction_dates']}"
            )
        finally:
            raw_data.close()

    publish_catalog(results, args.output.resolve())
    print(f"\nStatic forecast data written to {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
