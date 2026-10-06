import unittest
import tempfile
import json
from pathlib import Path
import numpy as np
import xarray as xr
from flood_app.publish import publish_region
from flood_app.archive import archive_run

class ArchiveTests(unittest.TestCase):
    def test_original_predictions_survive_and_later_observations_attach(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); data=root/'data'; model=root/'model.pth';model.write_bytes(b'test model')
            for region_id,history in [('wlc',9),('umap',7)]:
                region={'name':region_id,'input_len':history,'pred_len':3,'center':[0,0],'zoom':8}
                mask=np.ones((2,2),dtype=bool)
                for step,cutoff in enumerate(['2026-09-30','2026-10-01']):
                    dates=np.arange(np.datetime64(cutoff)-(history-1),np.datetime64(cutoff)+1).astype('datetime64[ns]')
                    raw=xr.Dataset({'water_fraction':(('time','lat','lon'),np.full((history,2,2),150))},coords={'time':dates,'lat':[1.,0.],'lon':[0.,1.]})
                    proc=xr.DataArray(np.full((history,2,2,2),.5),dims=['time','lat','lon','features'],coords={**raw.coords,'features':['water_fraction','cloud_mask']})
                    pred=np.full((3,2,2),.25+step*.1,dtype=np.float32)
                    meta=publish_region(region_id,region,raw,pred,mask,data,processed=proc)
                    archive_run(meta,pred,proc,mask,model,data)
                    if step==0:
                        original=next((root/'validation'/region_id/'runs').glob('*/forecast.nc'))
                        saved=original.read_bytes()
                self.assertEqual(saved,original.read_bytes())
                meta=json.loads((original.parent/'metadata.json').read_text())
                self.assertIn('observation',meta['assets'][0])
                self.assertNotIn('observation',meta['assets'][2])
                with xr.open_dataset(original) as ds:self.assertAlmostEqual(float(ds.forecast.mean()),.25)
                self.assertTrue(meta['assets'][0]['observation'].startswith(f'validation/{region_id}/'))
            catalog=json.loads((root/'validation/catalog.json').read_text())
            self.assertEqual(len(catalog['runs']),4)
            self.assertEqual(catalog['runs'][0]['provenance'],'operational_archive')
            self.assertEqual({run['region_id'] for run in catalog['runs']},{'wlc','umap'})
