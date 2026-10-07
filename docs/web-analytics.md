# Private usage reports

Cloudflare Web Analytics is disabled until the owner supplies the public site
token from their Web Analytics JavaScript snippet. Do not use an account API key.
Set the `token` constant in `site/analytics.js` and deploy. The beacon only loads
on `lunaleeyue.github.io`; local previews do not send traffic.

In the Cloudflare dashboard, add `lunaleeyue.github.io` as a Web Analytics site
using manual installation (no DNS migration required). Keep the analytics
dashboard private. Reports start after installation; past visits cannot be
reconstructed. Browser blocking and Cloudflare aggregation can affect counts.

## Reading the reports

- Select this site's host and paths under `/Operational-Flood-Forecasting/`.
- Use Visits and the time range for daily traffic trends. Visits are Cloudflare's
  referrer-based metric, not a count of identifiable people.
- Use Country for geographic distribution.
- Use page views by Path for mode entries:
  - NRT: `/Operational-Flood-Forecasting/`, `/Operational-Flood-Forecasting/index.html`,
    and `/Operational-Flood-Forecasting/nrt.html` combined.
  - Retrospective: `/Operational-Flood-Forecasting/retrospective.html`.

Mode counts mean entries/page views, including refreshes and returning to a
mode, not distinct users or every map interaction. Repeated clicks on the active
mode do not add routes. The quick tour's synthetic mode clicks do not change
URLs. Cloudflare's SPA beacon observes real History API navigations.

`python scripts/prepare_site.py` generates both HTML aliases before deployment
from `site/index.html`, so reloading/bookmarking either route works on GitHub
Pages without maintaining duplicate templates. Run it before local previews too.

After configuring the real token, verify both routes in the Cloudflare dashboard
and confirm receipt before treating the integration as live.

References: [installation](https://developers.cloudflare.com/web-analytics/get-started/),
[SPA tracking](https://developers.cloudflare.com/web-analytics/get-started/web-analytics-spa/),
[dimensions](https://developers.cloudflare.com/web-analytics/data-metrics/dimensions/).
