"""Pixel-wise verification of water fraction on identical grids (percentage points)."""
from pathlib import Path
import json
import numpy as np
import xarray as xr


def error_metrics(forecast, observation):
    forecast, observation = np.asarray(forecast), np.asarray(observation)
    if forecast.shape != observation.shape:
        raise ValueError('Forecast and observation shapes differ')
    valid = np.isfinite(forecast) & np.isfinite(observation) & (forecast >= 0) & (forecast <= 1) & (observation >= 0) & (observation <= 1)
    count = int(valid.sum())
    if not count:
        return {'mae': None, 'rmse': None, 'valid_pixels': 0, 'unit': 'percentage_points'}
    errors = (forecast[valid].astype(np.float64) - observation[valid].astype(np.float64)) * 100
    return {'mae': float(np.abs(errors).mean()), 'rmse': float(np.sqrt(np.square(errors).mean())), 'valid_pixels': count, 'unit': 'percentage_points'}


def grid_metrics(forecast, observation):
    for coord in ['lat', 'lon']:
        if not np.array_equal(forecast[coord].values, observation[coord].values):
            raise ValueError('Forecast and observation grids differ')
    return error_metrics(forecast.transpose('lat', 'lon').values, observation.transpose('lat', 'lon').values)


def refresh_region_metrics(validation_root: Path, region_id: str):
    for path in (validation_root / region_id).rglob('metadata.json'):
        record = json.loads(path.read_text(encoding='utf-8'))
        numerical = path.parent / 'forecast.nc'
        if not numerical.exists(): numerical = path.parent / 'comparison.nc'
        with xr.open_dataset(numerical) as predictions:
            for asset in record['assets']:
                if not asset.get('observation'): continue
                forecast = predictions.forecast.sel(time=asset['date'])
                if 'observation' in predictions:
                    observed = predictions.observation.sel(time=asset['date'])
                    asset['metrics'] = grid_metrics(forecast, observed)
                else:
                    # Operational observations live alongside their PNG. Backfills have a shared numerical archive.
                    observed_path = validation_root.parent / Path(asset['observation']).with_suffix('.nc')
                    if not observed_path.exists():
                        observed_path = validation_root / region_id / 'verification-observations' / f"{asset['date']}.nc"
                    if not observed_path.exists():
                        asset.pop('metrics', None)
                        continue
                    with xr.open_dataset(observed_path) as observed:
                        frame = observed.observation
                        if 'time' in frame.dims: frame = frame.sel(time=asset['date'])
                        asset['metrics'] = grid_metrics(forecast, frame)
        path.write_text(json.dumps(record, indent=2), encoding='utf-8')
