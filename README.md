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
