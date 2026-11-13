# Metrics, relative productivity, change classes, tiles

Written 2026-11-12 by the analyze agent. The stages are `s04_xyear_reduce.py`,
`s04_metrics.py`, `s04_relative.py`, `s04_change.py`, `s04_validate.py`, `s05_tiles.py` and
`s05_upload.py`, with shared paths and class tables in `s04_common.py`. Every stage runs in
the wci_tools venv (`E:\Water\water intelligence\wci_tools\.venv\Scripts\python.exe`), per
state, and skips outputs that exist unless `--force` is passed. Everything is written under
`F:\relative-land-productivity-data\analysis\` and `tiles\`; nothing under `extracted\` is
touched. No Earth Engine, no AWS compute.

## The 2020 year on the 2024 polygons

The extract tables couple polygon year and composite year: `extracted\modis\year=2024` holds
the 23 composites of agricultural year 2024 (day 241 of 2023 to day 225 of 2024) on the 2024
polygons, and `year=2020` the 2020 composites on the 2020 polygons. METHODS.md section 2 asks
for both years on the 2024 polygons. `s04_xyear_reduce.py` runs the extract stage's own
reduce and assemble functions (imported from `s03e_modis_reduce.py`, with the module's
partial and output roots pointed at `analysis\modis_xyear\`) over the 2020 composites with the
`weights\modis\year=2024` matrices. The output tables have the extract schema, so the metrics
stage reads them the same way. Checked on 2026-11-12: reducing composite 2024017 of tile
h12v08 through this path reproduces the extract agent's partial exactly (maximum absolute
difference 0 in `num` and `den`). The script runs as `watch` beside the extract watcher and
reduces each 2020 composite as its raw files land.

## Metrics (s04_metrics.py)

One table per source, polygon year, agricultural year and state under `analysis\metrics\`.
The source flag selects the series: `modis` reads the 23 interpolated 16-day columns, dates
each composite at its mid point (start plus 8 days) and weighs it 16 / 30.4375 months in the
integrals; `s2` reads the 12 monthly columns of the Sentinel-2 tables with a weight of one
month. Both give integrals in NDVI-months. The class of the year is `mbmode` for the polygon's
own year and `mb_2020` from `extracted\mapbiomas` for the 2020 year on 2024 polygons. The
calendar window comes from `data/calendars/class_window_lookup.csv`; classes 9 and 18 are not
in the table and take the full year. A window is a run of months in the September to August
order, so October to April is one run that wraps the calendar year.

Decisions taken here:

- Peer class: MapBiomas classes 19 and 41 pool into one peer class. The calendar gives them
  the same window, MapBiomas puts the same crops in both, and the task's crop-switch rule
  treats them as one crop group, so a field that moves from 19 to 41 keeps its peers.
- Perennial baseline: the 5th percentile of the interpolated values of the class in the state
  and year, for classes 20, 46, 47, 48, 35, 15 and 9 (forest plantation added to the six the
  methods list; it has no bare month either). Annual classes use the field's own minimum.
- Weather baseline: the rasters start in January 2015, so agricultural year 2015 lacks its
  September to December 2014 months. The baseline is the nine complete years 2016 to 2024,
  not the ten METHODS.md names. The anomaly of the target year is against the mean and
  sample standard deviation of those nine years, which include the target year.
- Weather is read at the field centroid, converted once per raster grid to row and column.
  Temperature is (tmax + tmin) / 2 from the TerraClimate files on disk.

Check on Mato Grosso 2024 (partial table, 21 of 23 composites): soybean (116,914 fields)
peaks a median 4.8 months after 1 September, late January, with median peak 0.884 and
window integral 2.45 NDVI-months over the October to April window; pasture (948,056 fields)
has a full-year integral of 2.88 above its 5th percentile floor of 0.402. The 2024
precipitation anomaly over the windows is a median -1.6 SD and the temperature anomaly +1.6
SD, the 2023 to 2024 El Niño drought.

## Relative productivity (s04_relative.py)

Layer 1 and layer 2 of METHODS.md section 5, on all states of a polygon year at once so peer
cells that straddle a state border pool both sides. A field enters a peer group when its
class is agricultural and at least half of its window composites have a raw value. The
peer group is (H3 cell, peer class, year): the resolution 5 cell when it holds at least 30
such fields of the class, else resolution 4, else 3, else none. R1 is the field integral
minus the group median over 1.4826 times the group MAD.

Layer 2 regresses the group medians of both years on the group mean precipitation and
temperature anomalies with quadratic terms, per peer class and state, by numpy least
squares, and removes the fitted term at field level from the field's own anomalies. Three
guards were added after a one-year development run gave an intercept of -68 NDVI-months for
Mato Grosso sugarcane (55 groups, one year): a class x state is fitted only with at least 30
groups spanning both years; the field anomalies are clipped to the range of group anomalies
the fit saw, so the quadratic is never evaluated outside its support; and the term is
capped at half the intercept in absolute value. The fit, R squared and anomaly ranges per
class x state are in `data/summaries/weather_fit.csv`. Layer 1 is recomputed on the adjusted
metric, giving `r_adj` in peer standard deviations, and the site's scale is
`prod = metric_adj / median_g(metric_adj)`, 1.0 at the peer median, clipped to 0 to 5.

The 2020 polygons (for the abandoned layer) take the coefficients fitted on the 2024 polygons.

## Change classes and decisions (s04_change.py)

On the 2024 polygons. `D = r_adj_2024 - r_adj_2020` in peer standard deviations gives
large_decline (D < -2), decline, stable (-1 to 1), gain, large_gain (D > 2), the METHODS.md
thresholds. Before that: `newly_cropped` when the MapBiomas 2020 class inside the outline is
not agricultural, `crop_switched` when the 2020 and 2024 crop groups differ, `no_data` when
either year has no relative value. The abandoned layer holds the 2020 polygons whose
MapBiomas 2024 class is not agricultural, with `change_class` abandoned and `decision`
restore. The overlay rules of METHODS.md (a 2020 field with no 2024 field over half of it,
and the reverse) are not applied, only the class rules; an overlay of 21.6 million by
24.6 million polygons was not affordable tonight and the class rule catches the same
fields when MapBiomas and Trazo4 agree.

The decision follows the METHODS.md section 7 table with the site's seven keys: below
peers and declining is `restore`; below and stable is `switch_crop`; below and gaining, at
peers and declining, above and declining are `improve_yields`; at peers and stable or
gaining is `intensify`; above and stable or gaining is `keep`; `abandon` when below in both
years, declining, and the 2024 integral is under the 20th percentile of the class in the
state; `change_pattern` for crop_switched. Fields that are newly_cropped or no_data get the
value `none`, which is not in the contract list; METHODS.md gives no suggestion for them and
a `keep` would be wrong. The site has to tolerate `none` and `no_data` (an unknown key
renders as the class name).

Two scale notes for the integrate agent. `change` is `prod_2024 - prod_2020` on the ratio
scale the contract asks for, but `change_class` follows the METHODS.md thresholds in peer
standard deviations, so the legend notes in `docs/config.js` (0.08 and 0.25) describe the
summary-cell steps, not the class boundaries. `crop_2024` is Trazo4's `mbmode`, the class
the 2024 peers were formed on, not the MapBiomas 2024 mode inside the outline; the two
agree on 96.7 to 98.2 percent of fields (EXTRACT.md).

`confidence` is low when the field is under 6.25 ha (one MODIS pixel) or fewer than 75
percent of the window composites were observed in either year. The columns `r_adj_2020`
and `r_adj_2024` are kept in the GeoParquet but not in the tiles.

## Tiles (s05_tiles.py)

Newline-delimited GeoJSON per state, streamed by 100,000-row groups, then tippecanoe in WSL
twice per state: zoom 12 to 14 with `-pk -pf` (no size limit, no feature limit, nothing
dropped or merged) and zoom 9 to 11 with `--coalesce-densest-as-needed -pf`, both with
`-ab` (shared borders) and `-P`; `--drop-densest-as-needed` is not used. The per-state
files are joined with `tile-join -pk`. The Trazo4 outlines are 10 m pixel staircases (131
vertices on a median 0.4 ha Tocantins field, 5.3 KB of GeoJSON each, about 75 GB for the
country), so each polygon is simplified with a one-pixel tolerance of 0.0001 degree with
topology preserved (27 vertices, 0.6 KB; the median drawn area is unchanged and 5 percent
of fields lose over 17 percent of drawn area) and coordinates are rounded to 5 decimals.
`area_ha` keeps the original value. The summary layer is one hexagon per H3 resolution 6
cell with the contract's means and counts over the scored 2024 fields, plus
`share_no_data`; `mean_vigor_change` is absent because vigor is null.
