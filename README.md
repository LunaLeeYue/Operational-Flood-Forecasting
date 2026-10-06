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

## NRT and retrospective modes

NRT Forecast preserves the original live map, forecast-date buttons, input timeline, opacity and basemap controls. Retrospective is a separate map and calendar with a WLC/UMAP region selector; switching back retains the NRT view.

The calendar selects the **first forecast target date D**. Its input is exactly the nine dates D-9 through D-1, and the three targets are D, D+1 and D+2. Curtain shows forecast on the left and same-date observation on the right; drag the divider or use its keyboard controls. Toggle alternates the full layers. Both use the same map extent, opacity and color scale. Missing observations remain pending, and invalid/cloud pixels are transparent.

The WLC 2026-10-01 example uses observations from September 22–30 to predict October 1–3. UMAP uses September 24–30 (its original 7-day model input) for the same forecast dates. For both regions, October 1 and 2 were retrospectively reconstructed because the original operational files were not retained. These entries are explicitly labelled; no claim is made that they are recovered original forecasts.

Each subsequent daily WLC and UMAP run is saved before Pages deployment to the **forecast-history** branch: immutable forecast PNGs, compressed numerical NetCDF, generation time, model SHA-256, workflow run ID and input dates. Later runs attach matching observations only when coordinates agree; predictions are not recomputed or overwritten. Every run is retained; the calendar defaults to the earliest original operational run per target start date, preferring it over retrospective reconstructions. The index starts at 2026-10-01. Archive persistence is separate from the latest NRT output and survives daily deploys.

To precompute additional complete historical dates, run `python scripts/build_validation_example.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD`, then publish the generated files and catalog. It checks consecutive input dates and matching grids. GitHub Pages serves precomputed assets; selecting a date does not launch model inference in the browser.
