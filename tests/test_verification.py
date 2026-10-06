import unittest
import numpy as np
import xarray as xr
from flood_app.verification import error_metrics, grid_metrics

class VerificationTests(unittest.TestCase):
    def test_known_errors_exclude_invalid_pairs_but_include_dry_pixels(self):
        result=error_metrics([0,.5,1,np.nan,.2,-1,np.inf],[.1,.3,.5,.2,-1,.2,.5])
        self.assertEqual(result['valid_pixels'],3)
        self.assertAlmostEqual(result['mae'],80/3)
        self.assertAlmostEqual(result['rmse'],np.sqrt(1000))
        self.assertEqual(result['unit'],'percentage_points')
    def test_no_valid_pairs_is_missing_not_zero(self):
        result=error_metrics([np.nan,-1],[.2,.5])
        self.assertIsNone(result['mae']); self.assertIsNone(result['rmse'])
        self.assertEqual(result['valid_pixels'],0)
    def test_shape_and_coordinate_mismatch_are_rejected(self):
        with self.assertRaises(ValueError): error_metrics(np.zeros((2,2)),np.zeros((2,)))
        a=xr.DataArray(np.zeros((2,2)),dims=['lat','lon'],coords={'lat':[1,0],'lon':[0,1]})
        with self.assertRaisesRegex(ValueError,'grids differ'): grid_metrics(a,a.assign_coords(lat=[0,1]))
        self.assertEqual(grid_metrics(a,a)['mae'],0)
