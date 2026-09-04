# UMAP/WCL Near-real-time Flood Forecast

This repository builds a static GitHub Pages application from NOAA JPSS VIIRS
daily flood-map composites. A scheduled GitHub Actions workflow downloads the
latest complete observations and publishes three forecast days for two regions:

| Region | History | Forecast | Trained checkpoint |
| --- | ---: | ---: | --- |
| Mississippi River Basin (UMAP) | 7 days | 3 days | `models/umap.pth` |
| Louisiana (WCL) | 9 days | 3 days | `models/wcl.pth` |

The model definitions and checkpoints follow these source notebooks:

- `Test_convlstm_auto/4_Test_convlstm_auto_Mississippi.ipynb`
- `Test_convlstm_auto/4_Test_convlstm_hypersearch_Louisiana.ipynb`

The WCL checkpoint is the notebook-selected HyperSearch epoch 2 model with
`hidden_dim=16`, `kernel_size=3`, and three ConvLSTM layers. The UMAP checkpoint
is the notebook-selected best NoInterp model with `hidden_dim=32` and one layer.

## How daily publication works

At 06:17 UTC every day, `.github/workflows/daily-prediction.yml`:

1. finds the newest strictly consecutive 7-day and 9-day windows for which all
   required NOAA tiles exist;
2. converts `WaterDetection` codes to the water-fraction and cloud-mask channels
   used during training;
3. loads both trained checkpoints with strict state-dict validation;
4. generates three forecast rasters and sampled GeoJSON point layers;
5. publishes the static `site/` directory to GitHub Pages.

If downloading, testing, or either prediction fails, the deployment job does not
run. The previously published Pages version remains available.

This is a **near-real-time research product**. The NOAA input is a completed
one-day composite, so the newest observation is normally the previous UTC day.
Do not use these forecasts as the sole basis for emergency decisions.

## First GitHub deployment

You need a GitHub account and must be signed in for these steps. No NOAA/AWS
credentials are required because the source bucket is public.

1. On GitHub, create a new empty repository, for example
   `convlstm-flood-forecast`. Do not initialize it with a README because this
   directory already contains one.
2. Upload/push the contents of this directory as the repository root. Do not
   push the parent ConvLSTM research directory.
3. Open **Settings → Pages**. Under **Build and deployment**, select
   **GitHub Actions** as the source.
4. Open **Actions → Build and publish daily flood forecast → Run workflow**.
5. When both jobs finish, the website URL is displayed in the `deploy` job and
   under **Settings → Pages**.

With Git installed locally, the initial push is:

```bash
cd github_deploy
git init
git add .
git commit -m "Initial UMAP and WCL flood forecast deployment"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/convlstm-flood-forecast.git
git push -u origin main
```

GitHub will ask you to authenticate. Prefer GitHub's browser/device login via
GitHub CLI or a credential manager; do not place an access token in a file or
commit it to this repository.

## Manual and archive runs

Use **Actions → Run workflow** without an input to publish the latest data. To
test a NOAA archive date, enter `YYYY-MM-DD` as `reference_date`. The pipeline
will find the latest complete input window on or before that date and forecast
the following three days.

The scheduled workflow runs from the default branch. A manual run is also the
quickest way to retry after a temporary NOAA or GitHub outage.

## Local validation

Install CPU PyTorch and the remaining dependencies:

```bash
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Generate current forecasts:

```bash
python scripts/run_daily.py --device cpu
```

Or validate with existing raw, AOI-clipped NetCDF inputs:

```bash
python scripts/run_daily.py \
  --device cpu \
  --output validation_site/data \
  --raw-input umap=/path/to/umap_raw_input.nc \
  --raw-input wcl=/path/to/wcl_raw_input.nc
```

To preview the generated site, serve it over HTTP (browser `file://` access will
not allow the JSON requests):

```bash
python -m http.server 8000 --directory site
```

Then visit `http://localhost:8000`.

## Repository layout

```text
assets/                    AOI shapefiles and training-grid masks
config/regions.json        Source, region, and model parameters
flood_app/                 NOAA download, preprocessing, models, publication
models/                    The two small trained PyTorch state dictionaries
scripts/run_daily.py       Daily/diagnostic command-line entry point
site/                      Static Leaflet application published to Pages
tests/                     Weight compatibility and output tests
.github/workflows/         Scheduled forecast and Pages deployment
```

Downloaded NOAA files are written under `runtime/`; generated forecast assets
under `site/data/` are deployed as workflow artifacts. Both are intentionally
excluded from Git commits.
