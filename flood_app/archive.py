"""Persist issued regional forecasts and attach observations without rewriting predictions."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import numpy as np
import xarray as xr
from flood_app.publish import save_forecast_png

START_DATE = '2026-10-01'


def update_catalog(validation_root: Path) -> None:
    entries = []
    for path in sorted(validation_root.rglob('metadata.json')):
        meta = json.loads(path.read_text(encoding='utf-8'))
        start = meta['assets'][0]['date']
        if start < START_DATE:
            continue
        entries.append({'region_id': meta['region_id'], 'date': start, 'metadata': 'validation/' + path.relative_to(validation_root).as_posix(),
                        'provenance': meta['provenance'], 'generated_at': meta['generated_at']})
    # Calendar defaults to the earliest genuinely issued run; retain all runs in the index.
    entries.sort(key=lambda e: (e['date'], e['provenance'] != 'operational_archive', e['generated_at']))
    validation_root.mkdir(parents=True, exist_ok=True)
    (validation_root / 'catalog.json').write_text(json.dumps({'regions': ['umap', 'wlc'], 'runs': entries}, indent=2), encoding='utf-8')


def archive_run(metadata, predictions, processed, mask, model_path, data_root: Path) -> None:
    validation_root = data_root.parent / 'validation'
    region_id = metadata['region_id']
    run_id = metadata['generated_at'].replace(':', '').replace('-', '').replace('.', '').replace('+', '_')
    run_dir = validation_root / region_id / 'runs' / run_id
    if run_dir.exists():
        raise FileExistsError(f'Archive run already exists: {run_dir}')
    run_dir.mkdir(parents=True)
    prediction_values = predictions.astype(np.float32, copy=True)
    prediction_values[:, ~mask] = np.nan
    xr.Dataset({'forecast': (('time', 'lat', 'lon'), prediction_values)},
               coords={'time': np.asarray(metadata['prediction_dates'], dtype='datetime64[ns]'),
                       'lat': processed.lat.values, 'lon': processed.lon.values},
               attrs={'generated_at': metadata['generated_at'], 'provenance': 'operational_archive'}).to_netcdf(
                   run_dir / 'forecast.nc', engine='netcdf4', encoding={'forecast': {'zlib': True, 'complevel': 4}})
    record = dict(metadata)
    record.update(provenance='operational_archive', issue_date=metadata['prediction_dates'][0],
                  model_sha256=hashlib.sha256(Path(model_path).read_bytes()).hexdigest(),
                  workflow_run_id=os.environ.get('GITHUB_RUN_ID'), input_assets=[])
    record['assets'] = []
    for original in metadata['assets']:
        name = f"forecast-{original['date']}.png"
        shutil.copyfile(data_root / original['raster'].removeprefix('data/'), run_dir / name)
        record['assets'].append({'date': original['date'], 'lead_day': original['lead_day'],
                                'raster': 'validation/' + (run_dir / name).relative_to(validation_root).as_posix()})
    (run_dir / 'metadata.json').write_text(json.dumps(record, indent=2), encoding='utf-8')

    # Retain first available observation and its grid; missing pixels stay missing.
    obs_dir = validation_root / region_id / 'observations'
    obs_dir.mkdir(parents=True, exist_ok=True)
    for index, day in enumerate(metadata['input_dates']):
        if day < START_DATE or (obs_dir / f'{day}.nc').exists():
            continue
        frame = processed.sel(features='water_fraction').isel(time=index).copy(deep=True)
        frame.values[(frame.values < 0) | ~mask] = np.nan
        frame.to_dataset(name='observation').to_netcdf(obs_dir / f'{day}.nc', engine='netcdf4',
            encoding={'observation': {'zlib': True, 'complevel': 4}})
        save_forecast_png(frame.values, obs_dir / f'{day}.png')

    for path in (validation_root / region_id / 'runs').glob('*/metadata.json'):
        record = json.loads(path.read_text(encoding='utf-8'))
        with xr.open_dataset(path.parent / 'forecast.nc') as prediction:
            for asset in record['assets']:
                observed_path = obs_dir / f"{asset['date']}.nc"
                if not observed_path.exists():
                    continue
                with xr.open_dataset(observed_path) as observed:
                    # Do not silently shift or resample an observation onto another grid.
                    if not (np.array_equal(prediction.lat, observed.lat) and np.array_equal(prediction.lon, observed.lon)):
                        continue
                asset['observation'] = f"validation/{region_id}/observations/{asset['date']}.png"
        path.write_text(json.dumps(record, indent=2), encoding='utf-8')
    update_catalog(validation_root)
