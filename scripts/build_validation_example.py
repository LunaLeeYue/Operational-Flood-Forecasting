"""Build the explicitly labelled WLC retrospective example from NOAA archives."""
from pathlib import Path
import sys,json,hashlib
from datetime import date,datetime,timezone
import numpy as np
import xarray as xr
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flood_app.config import load_config
from flood_app.data import NoaaVfmClient,preprocess,align_mask
from flood_app.models import load_model,predict
from flood_app.publish import save_forecast_png,coordinate_bounds

def main():
    config=load_config(ROOT/'config/regions.json',ROOT); region=config['regions']['wlc']; source=config['source']
    client=NoaaVfmClient(source['bucket'],source['base_path'],ROOT/'runtime/validation-cache')
    output=ROOT/'site/validation/wlc/2026-09-29'; output.mkdir(parents=True,exist_ok=True)
    raw_path=ROOT/'runtime/validation-input.nc'; obs_path=ROOT/'runtime/validation-observations.nc'
    if raw_path.exists():raw=xr.load_dataset(raw_path)
    else:
        raw=client.fetch_region(region,lookback_days=1,reference_date=date(2026,9,28));raw.to_netcdf(raw_path)
    assert str(np.datetime64(raw.time.values[-1],'D'))=='2026-09-28'
    print('Input dates:',raw.time.values,flush=True)
    if obs_path.exists():obs=xr.load_dataset(obs_path)
    else:
        obs=client.fetch_region({**region,'input_len':3},lookback_days=1,reference_date=date(2026,10,1));obs.to_netcdf(obs_path)
    np.testing.assert_array_equal(raw.lat.values,obs.lat.values);np.testing.assert_array_equal(raw.lon.values,obs.lon.values)
    proc=preprocess(raw); observed=preprocess(obs).sel(features='water_fraction').values.copy()
    torch.set_num_threads(4)
    forecast=predict(load_model(region,torch.device('cpu')),proc.values,9,3,torch.device('cpu'))
    mask=align_mask(Path(region['mask_path']),proc)
    forecast[:,~mask]=np.nan; observed[(observed<0)|~mask[None,:,:]]=np.nan
    dates=[str(np.datetime64(v,'D')) for v in obs.time.values]
    assert dates==['2026-09-29','2026-09-30','2026-10-01']
    assets=[]
    for i,d in enumerate(dates):
        f=f'forecast-{d}.png';o=f'observation-{d}.png'
        save_forecast_png(forecast[i],output/f);save_forecast_png(observed[i],output/o)
        assets.append({'date':d,'lead_day':i+1,'raster':f'validation/wlc/2026-09-29/{f}','observation':f'validation/wlc/2026-09-29/{o}'})
    south,north=coordinate_bounds(raw.lat.values);west,east=coordinate_bounds(raw.lon.values)
    metadata={'region_id':'wlc','region_name':region['name'],'issue_date':'2026-09-29','provenance':'retrospective_reconstruction','generated_at':datetime.now(timezone.utc).isoformat(),'latest_observation_date':'2026-09-28','input_dates':[str(np.datetime64(v,'D')) for v in raw.time.values],'bounds':[[south,west],[north,east]],'assets':assets,'input_assets':[],'model':{'history_days':9,'forecast_days':3},'model_sha256':hashlib.sha256(Path(region['model_path']).read_bytes()).hexdigest(),'original_run_url':'https://github.com/LunaLeeYue/Operational-Flood-Forecasting/actions/runs/36570605428','note':'Recomputed using archived NOAA inputs and unchanged model weights. Original issued rasters were not retained; this is not a recovered operational forecast. NOAA archives may have been revised.'}
    xr.Dataset({'forecast':(('time','lat','lon'),forecast),'observation':(('time','lat','lon'),observed)},coords={'time':obs.time.values,'lat':raw.lat.values,'lon':raw.lon.values},attrs={'provenance':metadata['note'],'model_sha256':metadata['model_sha256']}).to_netcdf(output/'comparison.nc',engine='netcdf4',encoding={k:{'zlib':True,'complevel':4} for k in ['forecast','observation']})
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print('Comparison written to',output,flush=True)
if __name__=='__main__':main()

