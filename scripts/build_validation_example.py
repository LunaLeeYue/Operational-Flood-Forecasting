"""Build the explicitly labelled regional retrospective example from NOAA archives."""
from pathlib import Path
import sys,json,hashlib,argparse
from datetime import date,datetime,timezone,timedelta
import numpy as np
import xarray as xr
import torch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from flood_app.config import load_config
from flood_app.data import NoaaVfmClient,preprocess,align_mask
from flood_app.models import load_model,predict
from flood_app.publish import save_forecast_png,coordinate_bounds

def build(start, region_id):
    config=load_config(ROOT/'config/regions.json',ROOT); region=config['regions'][region_id]; source=config['source']
    client=NoaaVfmClient(source['bucket'],source['base_path'],ROOT/'runtime/validation-cache')
    output=ROOT/'site/validation'/region_id/start.isoformat(); output.mkdir(parents=True,exist_ok=True)
    raw_path=ROOT/f'runtime/validation-input-{region_id}-{start}.nc'; obs_path=ROOT/f'runtime/validation-observations-{region_id}-{start}.nc'
    if raw_path.exists():raw=xr.load_dataset(raw_path)
    else:
        raw=client.fetch_region(region,lookback_days=1,reference_date=start-timedelta(days=1));raw.to_netcdf(raw_path)
    assert [str(np.datetime64(v,'D')) for v in raw.time.values]==[(start-timedelta(days=n)).isoformat() for n in range(region['input_len'],0,-1)]
    print('Input dates:',raw.time.values,flush=True)
    if obs_path.exists():obs=xr.load_dataset(obs_path)
    else:
        obs=client.fetch_region({**region,'input_len':3},lookback_days=1,reference_date=start+timedelta(days=2));obs.to_netcdf(obs_path)
    np.testing.assert_array_equal(raw.lat.values,obs.lat.values);np.testing.assert_array_equal(raw.lon.values,obs.lon.values)
    proc=preprocess(raw); observed=preprocess(obs).sel(features='water_fraction').values.copy()
    torch.set_num_threads(4)
    forecast=predict(load_model(region,torch.device('cpu')),proc.values,region['input_len'],3,torch.device('cpu'))
    mask=align_mask(Path(region['mask_path']),proc)
    forecast[:,~mask]=np.nan; observed[(observed<0)|~mask[None,:,:]]=np.nan
    dates=[str(np.datetime64(v,'D')) for v in obs.time.values]
    assert dates==[(start+timedelta(days=i)).isoformat() for i in range(3)]
    assets=[]
    for i,d in enumerate(dates):
        f=f'forecast-{d}.png';o=f'observation-{d}.png'
        save_forecast_png(forecast[i],output/f);save_forecast_png(observed[i],output/o)
        assets.append({'date':d,'lead_day':i+1,'raster':f'validation/{region_id}/{start}/{f}','observation':f'validation/{region_id}/{start}/{o}'})
    south,north=coordinate_bounds(raw.lat.values);west,east=coordinate_bounds(raw.lon.values)
    metadata={'region_id':region_id,'region_name':region['name'],'issue_date':start.isoformat(),'provenance':'retrospective_reconstruction','generated_at':datetime.now(timezone.utc).isoformat(),'latest_observation_date':(start-timedelta(days=1)).isoformat(),'input_dates':[str(np.datetime64(v,'D')) for v in raw.time.values],'bounds':[[south,west],[north,east]],'assets':assets,'input_assets':[],'model':{'history_days':region['input_len'],'forecast_days':3},'model_sha256':hashlib.sha256(Path(region['model_path']).read_bytes()).hexdigest(),'note':'Recomputed using archived NOAA inputs and unchanged model weights. Original issued rasters were not retained; this is not a recovered operational forecast. NOAA archives may have been revised.'}
    xr.Dataset({'forecast':(('time','lat','lon'),forecast),'observation':(('time','lat','lon'),observed)},coords={'time':obs.time.values,'lat':raw.lat.values,'lon':raw.lon.values},attrs={'provenance':metadata['note'],'model_sha256':metadata['model_sha256']}).to_netcdf(output/'comparison.nc',engine='netcdf4',encoding={k:{'zlib':True,'complevel':4} for k in ['forecast','observation']})
    (output/'metadata.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    print('Comparison written to',output,flush=True)
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start-date',type=date.fromisoformat,default=date(2026,9,29))
    parser.add_argument('--end-date',type=date.fromisoformat)
    parser.add_argument('--region',choices=['umap','wlc'],default='wlc')
    args=parser.parse_args(); end=args.end_date or args.start_date
    if end<args.start_date: parser.error('end date must not precede start date')
    current=args.start_date
    while current<=end:
        if not (ROOT/'site/validation'/args.region/str(current)/'metadata.json').exists(): build(current,args.region)
        current+=timedelta(days=1)
    from flood_app.archive import update_catalog
    update_catalog(ROOT/'site/validation')
if __name__=='__main__':main()

