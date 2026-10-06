"""Reconstruct forecasts for a target-date interval from strictly earlier NOAA inputs."""
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
import argparse, hashlib, json, sys
import numpy as np
import torch
import xarray as xr
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from flood_app.config import load_config
from flood_app.data import NoaaVfmClient, preprocess, align_mask
from flood_app.models import load_model, predict
from flood_app.publish import save_forecast_png, coordinate_bounds
from flood_app.archive import update_catalog
from flood_app.verification import refresh_region_metrics


def build(region_id, first, last):
    config = load_config(ROOT / 'config/regions.json', ROOT)
    region = config['regions'][region_id]
    source = config['source']
    client = NoaaVfmClient(source['bucket'], source['base_path'], ROOT / 'runtime/validation-cache')
    daily_dir = ROOT / 'runtime/backfill-daily' / region_id
    daily_dir.mkdir(parents=True, exist_ok=True)
    first_run = first - timedelta(days=2)
    day = first_run - timedelta(days=region['input_len'])
    frames = []
    while day <= last:
        path = daily_dir / f'{day}.nc'
        if not path.exists():
            raw = client.fetch_region({**region, 'input_len': 1}, lookback_days=1, reference_date=day)
            assert str(np.datetime64(raw.time.values[0], 'D')) == str(day)
            raw.to_netcdf(path, engine='netcdf4', encoding={'water_fraction': {'zlib': True, 'complevel': 4}})
            raw.close()
        with xr.open_dataset(path) as raw:
            frames.append(raw.load())
        print(f'{region_id} input ready {day}', flush=True)
        day += timedelta(days=1)
    raw = xr.concat(frames, dim='time', join='exact')
    proc = preprocess(raw)
    mask = align_mask(Path(region['mask_path']), proc)
    obs_dir = ROOT / 'site/validation' / region_id / 'verification-observations'
    obs_dir.mkdir(parents=True, exist_ok=True)
    for target in proc.time.values:
        day = str(np.datetime64(target, 'D'))
        frame = proc.sel(time=target, features='water_fraction').copy(deep=True)
        frame.values[(frame.values < 0) | ~mask] = np.nan
        path = obs_dir / f'{day}.nc'
        if not path.exists():
            frame.to_dataset(name='observation').to_netcdf(path, engine='netcdf4', encoding={'observation': {'zlib':True, 'complevel':4}})
    device = torch.device('cpu')
    torch.set_num_threads(4)
    model = load_model(region, device)
    model_hash = hashlib.sha256(Path(region['model_path']).read_bytes()).hexdigest()
    south, north = coordinate_bounds(raw.lat.values)
    west, east = coordinate_bounds(raw.lon.values)
    start = first_run
    while start <= last:
        output = ROOT / 'site/validation' / region_id / str(start)
        if (output / 'metadata.json').exists():
            start += timedelta(days=1)
            continue
        inputs = proc.sel(time=slice(str(start-timedelta(days=region['input_len'])), str(start-timedelta(days=1))))
        assert len(inputs.time) == region['input_len']
        forecast = predict(model, inputs.values, region['input_len'], 3, device)
        forecast[:, ~mask] = np.nan
        output.mkdir(parents=True, exist_ok=True)
        assets = []
        dates = [start + timedelta(days=i) for i in range(3)]
        for i, target in enumerate(dates):
            filename = f'forecast-{target}.png'
            save_forecast_png(forecast[i], output / filename)
            asset = {'date': str(target), 'lead_day': i+1, 'raster': f'validation/{region_id}/{start}/{filename}'}
            if target <= last:
                observed = proc.sel(time=str(target), features='water_fraction').values.copy()
                observed[(observed < 0) | ~mask] = np.nan
                filename = f'observation-{target}.png'
                save_forecast_png(observed, output / filename)
                asset['observation'] = f'validation/{region_id}/{start}/{filename}'
            assets.append(asset)
        xr.Dataset({'forecast': (('time','lat','lon'), forecast)}, coords={'time': np.asarray(dates, dtype='datetime64[ns]'), 'lat': raw.lat.values, 'lon': raw.lon.values}).to_netcdf(output/'forecast.nc', engine='netcdf4', encoding={'forecast': {'zlib': True, 'complevel': 4}})
        metadata = {'region_id': region_id, 'region_name': region['name'], 'issue_date': str(start), 'provenance': 'retrospective_reconstruction', 'generated_at': datetime.now(timezone.utc).isoformat(), 'latest_observation_date': str(start-timedelta(days=1)), 'input_dates': [str(np.datetime64(v,'D')) for v in inputs.time.values], 'bounds': [[south,west],[north,east]], 'assets': assets, 'input_assets': [], 'model': {'history_days': region['input_len'], 'forecast_days': 3}, 'model_sha256': model_hash, 'note': 'Reconstructed using archived NOAA inputs strictly before the forecast start date, not an original issued forecast. Upstream archives may have been revised.'}
        (output/'metadata.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
        print(f'{region_id} forecast ready {start}', flush=True)
        start += timedelta(days=1)
    refresh_region_metrics(ROOT/'site/validation', region_id)
    update_catalog(ROOT/'site/validation')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-date', type=date.fromisoformat, required=True)
    parser.add_argument('--end-date', type=date.fromisoformat, required=True)
    parser.add_argument('--region', choices=['umap','wlc','both'], default='both')
    args = parser.parse_args()
    if args.start_date > args.end_date: parser.error('start date must precede end date')
    for region in (['umap','wlc'] if args.region == 'both' else [args.region]):
        build(region, args.start_date, args.end_date)
