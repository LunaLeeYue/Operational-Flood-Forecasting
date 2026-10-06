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

The calendar selects a **target observation date D**. The 1-day, 2-day and 3-day buttons show forecasts for that same date from three different input cutoffs: D-1, D-2 and D-3 respectively. Each uses the original model history length (UMAP 7 days; WLC 9 days). Lead time is measured from the last input date, not the later reconstruction timestamp. Curtain compares forecast (left) and same-day observation (right); Toggle alternates the full layers. Both use the same grid and color scale. Cloud/invalid pixels are transparent.

Both regions include September 1 through October 4, 2026 (34 observed target dates, each with three lead times). These are explicitly labelled retrospective reconstructions from archived NOAA inputs, not recovered original issued forecasts. Providing September 1 at a 3-day lead requires the run beginning August 30 and inputs ending August 29. Only targets with matched observations appear in the calendar; it defaults to the latest available observed target date. Future daily runs extend the calendar as observations arrive.

Daily WLC and UMAP runs are saved before Pages deployment to the **forecast-history** branch: immutable forecast PNGs, compressed numerical NetCDF, generation time, model SHA-256, workflow run ID and input dates. Later runs attach observations only when coordinates agree. Every run is retained; for each region, target date and lead time, the catalog prefers the earliest original operational forecast with an observation, then a reconstruction. Archive persistence is separate from latest NRT output and survives daily deploys.

To reconstruct an observed target interval, run `python scripts/backfill_history.py --start-date 2026-09-01 --end-date 2026-10-04 --region both`. The script caches daily clipped NOAA inputs, checks exact dates and grids, and generates the extra preceding runs needed for all three leads. Forecast inputs strictly precede the target; observations are used only for comparison. GitHub Pages serves precomputed assets; selecting a date does not launch model inference in the browser.

## Verification metrics

Retrospective maps show MAE and RMSE for the selected region, target date and lead. Both are calculated from the saved numerical water fractions on identical latitude/longitude grids, with equal weight per valid paired pixel across the full AOI (including dry pixels). Invalid/cloud and outside-AOI pixels are excluded. MAE = mean(abs(forecast - observation)) and RMSE = sqrt(mean((forecast - observation)^2)); normalized fractions are multiplied by 100 to report **percentage points**, not relative percentage error. The panel also reports the valid paired pixel count; no valid pairs displays unavailable values, not zero error. These metrics do not depend on opacity, map zoom or the curtain divider. Daily archives calculate metrics when matching observations arrive; historical backfills retain shared compressed observation arrays for reproducible verification.
