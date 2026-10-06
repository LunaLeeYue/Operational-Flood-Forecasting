import unittest
import tempfile
import json
from pathlib import Path
import numpy as np
import xarray as xr
from flood_app.publish import publish_region
from flood_app.archive import archive_run, update_catalog

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
                self.assertAlmostEqual(meta['assets'][0]['metrics']['mae'],25.0)
                self.assertAlmostEqual(meta['assets'][0]['metrics']['rmse'],25.0)
                self.assertEqual(meta['assets'][0]['metrics']['valid_pixels'],4)
                self.assertNotIn('observation',meta['assets'][2])
                with xr.open_dataset(original) as ds:self.assertAlmostEqual(float(ds.forecast.mean()),.25)
                self.assertTrue(meta['assets'][0]['observation'].startswith(f'validation/{region_id}/'))
            catalog=json.loads((root/'validation/catalog.json').read_text())
            self.assertEqual(len(catalog['runs']),4)
            self.assertEqual(catalog['runs'][0]['provenance'],'operational_archive')
            self.assertEqual({run['region_id'] for run in catalog['runs']},{'wlc','umap'})

    def test_target_calendar_matches_leads_and_prefers_original_runs(self):
        from datetime import date, timedelta
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for region in ['umap','wlc']:
                for lead in [1,2,3]:
                    for version, provenance in [('reconstructed','retrospective_reconstruction'),('original','operational_archive')]:
                        path=root/region/f'{version}-{lead}'/'metadata.json'
                        path.parent.mkdir(parents=True)
                        target=date(2026,9,1)
                        cutoff=target-timedelta(days=lead)
                        meta={'region_id':region,'latest_observation_date':str(cutoff),'provenance':provenance,'generated_at':'2026-10-05T00:00:00Z',
                              'assets':[{'date':str(cutoff+timedelta(days=i)), 'lead_day':i, **({'observation':'matched.png'} if i==lead else {})} for i in [1,2,3]]}
                        path.write_text(json.dumps(meta))
            update_catalog(root)
            catalog=json.loads((root/'catalog.json').read_text())
            self.assertEqual(len(catalog['targets']),2)
            for target in catalog['targets']:
                self.assertEqual(target['date'],'2026-09-01')
                self.assertEqual(set(target['leads']),{'1','2','3'})
                for lead, entry in target['leads'].items():
                    self.assertEqual(entry['provenance'],'operational_archive')
                    self.assertIn(f"/{target['region_id']}/original-{lead}/",entry['metadata'])
            path=root/'umap/original-3/metadata.json'
            meta=json.loads(path.read_text()); meta['latest_observation_date']='2026-08-31'
            path.write_text(json.dumps(meta))
            with self.assertRaisesRegex(ValueError,'Invalid lead alignment'): update_catalog(root)
