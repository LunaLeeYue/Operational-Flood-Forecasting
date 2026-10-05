# UMAP/WLC Near-real-time Flood Forecast

This repository publishes three-day ConvLSTM water-fraction forecasts from
NOAA JPSS VIIRS daily flood-map composites.

| Region | Observation history | Forecast |
| --- | ---: | ---: |
| Upper Mississippi Alluvial Plain (UMAP) | 7 days | 3 days |
| Western Louisiana Coast (WLC) | 9 days | 3 days |

The public map is available at:

https://lunaleeyue.github.io/Operational-Flood-Forecasting/

## How daily publication works

At 06:17 UTC every day, `.github/workflows/daily-prediction.yml`:

1. finds the newest strictly consecutive 7-day and 9-day observation windows
   for which every required NOAA tile is available;
2. applies the same water-fraction and cloud-mask preprocessing used for
   training;
3. runs the trained UMAP and WLC models to predict the following three days;
4. creates the raster and point-map assets;
5. publishes the updated static application to GitHub Pages.

The workflow runs at **06:17 UTC** because a NOAA daily composite can only be
finished after its UTC observation day has closed, and NOAA then needs time to
publish the files. Waiting until 06:17 gives the previous day's composite time
to arrive. Minute 17 also avoids GitHub Actions' busiest top-of-hour scheduling
window. If the newest day is still incomplete, the pipeline safely uses the
most recent complete consecutive window instead of mixing missing dates.

The workflow can also be started manually from **Actions → Build and publish
daily flood forecast → Run workflow**. An optional `reference_date` can be used
to test an archived NOAA date.

This is a near-real-time research forecast, not a minute-by-minute operational
feed. It must not be used as the sole basis for emergency decisions.

## Map controls

- **Layer Opacity** adjusts the forecast raster, markers, or selected input observation from 0–100%.
- **Basemap** switches between OpenStreetMap and Esri World Imagery. Satellite imagery is background context, not a current flood observation.
- **Model Input Observations** shows the actual preprocessed water-fraction channel used by the model (7 days for UMAP, 9 for WLC). Drag the date slider to show an input raster. Uncheck the option or select a prediction date to return to forecasts. Invalid/cloud pixels and pixels outside the AOI are transparent; no-data is not interpreted as dry land.

Input rasters are published with each forecast under `site/data/<region>/inputs/` and listed in `input_assets` in regional metadata. Older publications without these assets keep the input controls disabled.

## WLC historical comparison example

The History & Validation selector includes the forecast run dated 2026-09-29. Its original Actions log confirms an input cutoff of 2026-09-28 and target dates 2026-09-29, 2026-09-30 and 2026-10-01. The original Pages artifact was no longer available, so this example is explicitly labelled a retrospective reconstruction, not a recovered operational forecast. It uses unchanged WLC model weights and archived NOAA inputs; the upstream archive may have been revised since issuance.

Select a target date and toggle **Show observation instead of forecast** to compare the same date and map extent. Both layers use the same 0–100% water-fraction color scale and opacity. Invalid observation pixels remain transparent. This compares water fraction, including permanent water, rather than isolating new inundation.

The six preview images, provenance metadata, and compressed numerical comparison (`comparison.nc`) are stored in `site/validation/wlc/2026-09-29/`, so daily Pages builds retain this example. Rebuild with `python scripts/build_validation_example.py`; it verifies exact dates and coordinate equality and records the model SHA-256. This first example does not yet implement automatic daily historical archiving.
