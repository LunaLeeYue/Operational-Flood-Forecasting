from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import numpy as np
import pandas as pd
import rioxarray  # noqa: F401 - registers the .rio accessor
import s3fs
import xarray as xr
from rioxarray.merge import merge_arrays
from shapely.geometry import mapping


INVALID_CODES = (1, 30, 50)
NON_WATER_CODES = (15, 16, 17, 20, 27, 38)


def open_tile(path: Path) -> xr.Dataset:
    errors = []
    for engine in ("h5netcdf", "netcdf4", "scipy"):
        try:
            return xr.open_dataset(path, engine=engine)
        except Exception as exc:  # pragma: no cover - backend-specific detail
            errors.append(f"{engine}: {exc}")
    raise OSError(f"Cannot open {path}; " + "; ".join(errors))


def validate_tile(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        with open_tile(path) as dataset:
            return "WaterDetection" in dataset.variables
    except Exception:
        return False


class NoaaVfmClient:
    """Anonymous client for NOAA's daily VIIRS flood-map composites."""

    def __init__(self, bucket: str, base_path: str, cache_dir: Path):
        self.bucket = bucket
        self.base_path = base_path.strip("/")
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.fs = s3fs.S3FileSystem(anon=True)
        self._list_cache: dict[date, list[str]] = {}

    def day_prefix(self, day: date) -> str:
        return f"{self.bucket}/{self.base_path}/{day:%Y/%m/%d}"

    def list_day(self, day: date) -> list[str]:
        if day not in self._list_cache:
            try:
                self._list_cache[day] = sorted(self.fs.ls(self.day_prefix(day), detail=False))
            except (FileNotFoundError, OSError):
                self._list_cache[day] = []
        return self._list_cache[day]

    def files_for_tiles(self, day: date, tile_ids: Iterable[str]) -> dict[str, str]:
        files = self.list_day(day)
        selected: dict[str, str] = {}
        for tile_id in tile_ids:
            matches = [path for path in files if f"GLB{tile_id}_" in Path(path).name]
            if matches:
                # If NOAA republishes a tile/version, prefer the lexically latest name.
                selected[tile_id] = matches[-1]
        return selected

    def find_latest_complete_window(
        self,
        tile_ids: list[str],
        input_len: int,
        lookback_days: int,
        reference_date: date | None = None,
    ) -> list[date]:
        """Find the newest strictly consecutive input window with every tile."""
        anchor = reference_date or datetime.now(timezone.utc).date()
        complete: dict[date, bool] = {}
        for offset in range(lookback_days + input_len):
            day = anchor - timedelta(days=offset)
            complete[day] = len(self.files_for_tiles(day, tile_ids)) == len(tile_ids)

        for candidate_offset in range(lookback_days):
            latest = anchor - timedelta(days=candidate_offset)
            window = [latest - timedelta(days=offset) for offset in reversed(range(input_len))]
            if all(complete.get(day, False) for day in window):
                return window

        raise RuntimeError(
            f"No complete {input_len}-day window for tiles {tile_ids} "
            f"within {lookback_days} days of {anchor}"
        )

    def download(self, remote_path: str) -> Path:
        local_path = self.cache_dir / Path(remote_path).name
        if validate_tile(local_path):
            return local_path

        local_path.unlink(missing_ok=True)
        partial = local_path.with_suffix(local_path.suffix + ".part")
        partial.unlink(missing_ok=True)
        with self.fs.open(remote_path, "rb") as remote, partial.open("wb") as local:
            while chunk := remote.read(8 * 1024 * 1024):
                local.write(chunk)
        partial.replace(local_path)

        if not validate_tile(local_path):
            local_path.unlink(missing_ok=True)
            raise OSError(f"Downloaded NOAA tile is invalid: {remote_path}")
        return local_path

    def merge_day(self, tile_paths: dict[str, Path], aoi_path: Path) -> xr.DataArray:
        arrays = []
        for tile_id in sorted(tile_paths):
            with open_tile(tile_paths[tile_id]) as dataset:
                array = dataset["WaterDetection"].squeeze(drop=True).load()
            rename = {}
            if "lat" in array.dims:
                rename["lat"] = "y"
            if "lon" in array.dims:
                rename["lon"] = "x"
            array = array.rename(rename)
            array = array.rio.write_crs("EPSG:4326").rio.set_spatial_dims("x", "y")
            arrays.append(array)

        merged = merge_arrays(arrays)
        aoi = gpd.read_file(aoi_path)
        if aoi.crs is None:
            raise ValueError(f"AOI has no CRS: {aoi_path}")
        aoi = aoi.to_crs("EPSG:4326")
        clipped = merged.rio.clip(
            [mapping(geometry) for geometry in aoi.geometry],
            aoi.crs,
            drop=True,
        )
        return clipped.transpose("y", "x").load()

    def fetch_region(
        self,
        region: dict,
        lookback_days: int,
        reference_date: date | None = None,
    ) -> xr.Dataset:
        input_dates = self.find_latest_complete_window(
            tile_ids=region["tiles"],
            input_len=int(region["input_len"]),
            lookback_days=lookback_days,
            reference_date=reference_date,
        )

        daily_arrays = []
        for day in input_dates:
            remote_files = self.files_for_tiles(day, region["tiles"])
            if len(remote_files) != len(region["tiles"]):
                raise RuntimeError(f"Required tiles disappeared for {day}")
            local_files = {tile: self.download(path) for tile, path in remote_files.items()}
            daily_arrays.append(self.merge_day(local_files, Path(region["aoi_path"])))

        # NOAA daily grids should be identical. join='exact' prevents a silent
        # resample if a future product changes coordinates.
        combined = xr.concat(daily_arrays, dim="time", join="exact")
        return xr.Dataset(
            {
                "water_fraction": (
                    ("time", "lat", "lon"),
                    combined.values.astype(np.float32, copy=False),
                )
            },
            coords={
                "time": pd.DatetimeIndex(input_dates),
                "lat": combined["y"].values,
                "lon": combined["x"].values,
            },
            attrs={
                "source": f"s3://{self.bucket}/{self.base_path}",
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        )


def preprocess(raw_data: xr.Dataset) -> xr.DataArray:
    """Reproduce the water-fraction/cloud-mask preprocessing used in training."""
    encoded = raw_data["water_fraction"].values.astype(np.float32, copy=False)
    water_fraction = np.full(encoded.shape, np.nan, dtype=np.float32)
    cloud_mask = np.zeros(encoded.shape, dtype=np.float32)

    for time_index, frame in enumerate(encoded):
        if np.isnan(frame).all():
            invalid = np.ones(frame.shape, dtype=bool)
        else:
            # Keep this identical to the training/deployment notebooks: partial
            # NaNs become water_fraction=-1 but are not a coded cloud pixel.
            invalid = np.zeros(frame.shape, dtype=bool)
            for code in INVALID_CODES:
                invalid |= frame == code
        cloud_mask[time_index] = invalid.astype(np.float32)

        decoded = np.full(frame.shape, np.nan, dtype=np.float32)
        decoded[frame == 99] = 1.0
        fractional = (frame >= 100) & (frame <= 200)
        decoded[fractional] = (frame[fractional] - 100.0) / 100.0
        for code in NON_WATER_CODES:
            decoded[frame == code] = 0.0
        decoded[invalid] = np.nan
        water_fraction[time_index] = np.nan_to_num(decoded, nan=-1.0)

    values = np.stack([water_fraction, cloud_mask], axis=-1)
    return xr.DataArray(
        values,
        coords={
            "time": raw_data.time.values,
            "lat": raw_data.lat.values,
            "lon": raw_data.lon.values,
            "features": ["water_fraction", "cloud_mask"],
        },
        dims=("time", "lat", "lon", "features"),
        name="convlstm_input",
    )


def align_mask(mask_path: Path, template: xr.DataArray) -> np.ndarray:
    """Align the training AOI mask to a newly clipped NOAA grid by coordinates."""
    errors = []
    mask = None
    for engine in ("h5netcdf", "netcdf4", "scipy"):
        try:
            with xr.open_dataarray(mask_path, engine=engine) as source:
                mask = source.astype(np.float32).sortby("lat").sortby("lon").load()
            break
        except Exception as exc:  # pragma: no cover - backend-specific detail
            errors.append(f"{engine}: {exc}")
    if mask is None:
        raise OSError(f"Cannot open AOI mask {mask_path}; " + "; ".join(errors))
    target_lat = xr.DataArray(template.lat.values, dims="lat")
    target_lon = xr.DataArray(template.lon.values, dims="lon")
    aligned = mask.interp(lat=target_lat, lon=target_lon, method="nearest").fillna(0)
    return aligned.values >= 0.5
