from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr


def coordinate_bounds(values: np.ndarray) -> tuple[float, float]:
    values = np.asarray(values, dtype=np.float64)
    if values.size == 1:
        return float(values[0] - 0.5), float(values[0] + 0.5)
    spacing = float(np.nanmedian(np.abs(np.diff(values))))
    return float(np.nanmin(values) - spacing / 2), float(np.nanmax(values) + spacing / 2)


def save_forecast_png(values: np.ndarray, output_path: Path) -> None:
    """Write an AOI-masked, transparent raster for Leaflet imageOverlay."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    height, width = values.shape
    dpi = 100
    figure = plt.figure(figsize=(width / dpi, height / dpi), dpi=dpi, frameon=False)
    axes = figure.add_axes((0, 0, 1, 1))
    axes.axis("off")
    color_map = matplotlib.colormaps["jet"].copy()
    color_map.set_bad((0, 0, 0, 0))
    visible = np.ma.masked_where(~np.isfinite(values) | (values <= 0.05), values)
    axes.imshow(
        visible,
        cmap=color_map,
        vmin=0,
        vmax=1,
        origin="upper",
        interpolation="bilinear",
    )
    figure.savefig(output_path, transparent=True, pad_inches=0)
    plt.close(figure)


def write_geojson(
    values: np.ndarray,
    latitudes: np.ndarray,
    longitudes: np.ndarray,
    output_path: Path,
    sample_rate: int = 10,
    minimum_fraction: float = 0.1,
) -> int:
    features = []
    for row in range(0, len(latitudes), sample_rate):
        for column in range(0, len(longitudes), sample_rate):
            value = float(values[row, column])
            if not np.isfinite(value) or value <= minimum_fraction:
                continue
            if value > 0.7:
                level = "high"
            elif value > 0.4:
                level = "medium"
            else:
                level = "low"
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [float(longitudes[column]), float(latitudes[row])],
                    },
                    "properties": {
                        "water_fraction": round(value, 5),
                        "flood_level": level,
                    },
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(
            {"type": "FeatureCollection", "features": features},
            handle,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    return len(features)


def publish_region(
    region_id: str,
    region: dict,
    raw_data: xr.Dataset,
    predictions: np.ndarray,
    aoi_mask: np.ndarray,
    output_root: Path,
) -> dict:
    region_dir = output_root / region_id
    maps_dir = region_dir / "maps"
    points_dir = region_dir / "points"
    maps_dir.mkdir(parents=True, exist_ok=True)
    points_dir.mkdir(parents=True, exist_ok=True)

    latest_observation = np.datetime64(raw_data.time.values[-1], "D")
    observation_date = str(latest_observation)
    prediction_dates = [
        str(latest_observation + np.timedelta64(lead, "D"))
        for lead in range(1, int(region["pred_len"]) + 1)
    ]
    latitudes = raw_data.lat.values
    longitudes = raw_data.lon.values
    south, north = coordinate_bounds(latitudes)
    west, east = coordinate_bounds(longitudes)

    assets = []
    for index, prediction_date in enumerate(prediction_dates):
        masked = predictions[index].astype(np.float32, copy=True)
        masked[~aoi_mask] = np.nan
        png_name = f"day-{index + 1}.png"
        geojson_name = f"day-{index + 1}.geojson"
        save_forecast_png(masked, maps_dir / png_name)
        point_count = write_geojson(
            masked,
            latitudes,
            longitudes,
            points_dir / geojson_name,
        )
        assets.append(
            {
                "lead_day": index + 1,
                "date": prediction_date,
                "raster": f"data/{region_id}/maps/{png_name}",
                "points": f"data/{region_id}/points/{geojson_name}",
                "point_count": point_count,
            }
        )

    input_dates = [str(np.datetime64(value, "D")) for value in raw_data.time.values]
    metadata = {
        "status": "success",
        "region_id": region_id,
        "region_name": region["name"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_observation_date": observation_date,
        "input_dates": input_dates,
        "prediction_dates": prediction_dates,
        "bounds": [[south, west], [north, east]],
        "center": region["center"],
        "zoom": region["zoom"],
        "model": {
            "label": region["model_label"],
            "architecture": region["architecture"],
            "history_days": region["input_len"],
            "forecast_days": region["pred_len"],
        },
        "assets": assets,
        "data_source": "NOAA JPSS VFM 1-day global composite",
        "disclaimer": "Near-real-time research forecast; not for emergency decisions.",
    }
    with (region_dir / "latest.json").open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, indent=2)
    return metadata


def publish_catalog(region_results: dict[str, dict], output_root: Path) -> None:
    catalog = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "regions": {
            region_id: {
                "name": result["region_name"],
                "center": result["center"],
                "zoom": result["zoom"],
                "latest": f"data/{region_id}/latest.json",
            }
            for region_id, result in region_results.items()
        },
    }
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "catalog.json").open("w", encoding="utf-8") as handle:
        json.dump(catalog, handle, ensure_ascii=False, indent=2)
