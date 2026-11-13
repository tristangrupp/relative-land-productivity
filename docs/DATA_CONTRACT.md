# Data contract between the tiles and the site

The site reads three files. Their URLs and every attribute name live in `docs/config.js`,
in `CONFIG`, `ATTR` and `SUMMARY_ATTR`. The analysis stage writes tiles that match this
file; if a name has to change, change it in `config.js` and here, nowhere else. This version
describes the tiles released on 13 November 2026, read back from the PMTiles metadata.

## Files

| config key | URL | what it is |
|---|---|---|
| `FIELDS_PMTILES` | `https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/tiles/fields.pmtiles` | one polygon per 2024 Trazo4 field plus the abandoned 2020 fields, layer name `fields`, zoom 9 to 13, 6.36 GB |
| `SUMMARY_PMTILES` | `.../tiles/summary.pmtiles` | one polygon per H3 cell at three resolutions by zoom band (4, 5, 6; 4,041, 23,878 and 144,909 cells), layer name `summary`, zoom 3 to 9, 26 MB |
| `STATS_URL` | `.../tiles/stats.json` | class counts for Brazil and per state, read by the legend and the Where card |

The bucket is public read with CORS (`Access-Control-Allow-Origin: *`, GET and HEAD), so
GitHub Pages range-reads the PMTiles. The fields archive stops at zoom 13; MapLibre
overzooms the zoom 13 tiles for every zoom above that, so no layer in the style may set a
maxzoom at or under 13. From zoom 9 to 11 tippecanoe merged the smallest fields into their
neighbors (`--coalesce-smallest-as-needed --drop-smallest-as-needed`); at 12 and 13 nothing
is dropped or merged. Outlines are simplified with a 0.0001 degree tolerance and rounded to
5 decimals; `area_ha` keeps the original value.

`CONFIG.USE_PLACEHOLDER` switches the page to the placeholder copies in `docs/data/`. It is
`false` in the released site.

## Fields layer attributes

| property | type | meaning | absent means |
|---|---|---|---|
| `fid` | int | Trazo4 field id from the 2024 parquet (2020 parquet for abandoned fields) | never absent |
| `area_ha` | float | field area in hectares (ESRI:102033 equal area) | never absent |
| `crop_2020` | int | modal MapBiomas Collection 10 class inside the 2024 outline, 2020 coverage; any MapBiomas class can occur | no coverage |
| `crop_2024` | int | the Trazo4 `mbmode` class of the 2024 field, the class its peers were formed on (agrees with the MapBiomas 2024 mode inside the outline on 96.7 to 98.2 percent of fields); on abandoned 2020 fields the MapBiomas 2024 class, which is not agricultural | no coverage |
| `prod_2020` | float | weather-adjusted relative productivity 2020: the field's adjusted seasonal greenness divided by the median of its peers (same crop group, same region). 1.0 is the peer median; clipped to 0 to 5 | not cropped or not measured in 2020 |
| `prod_2024` | float | the same for 2024 | not cropped or not measured in 2024 |
| `change` | float | `prod_2024` minus `prod_2020`, on the ratio scale, only when both exist and the crop group is the same | not comparable |
| `change_class` | string | one of `large_decline`, `decline`, `stable`, `gain`, `large_gain` (set on the change in peer standard deviations, thresholds 1 and 2), `crop_switched`, `newly_cropped`, `abandoned`, `no_data` | never absent |
| `decision` | string | one of `restore`, `switch_crop`, `change_pattern`, `abandon`, `intensify`, `improve_yields`, `keep`, `none` (newly cropped and no-data fields) | never absent |
| `confidence` | string | `low` when the field is under 6.25 ha (one MODIS pixel) or fewer than 75 percent of its window composites were observed in either year, else `high` | never absent |
| `n_obs_2020` | int | observed (not interpolated) 16-day composites inside the 2020 growing season window, 0 to 23 | not measured |
| `n_obs_2024` | int | the same for 2024, 0 to 22 (composite 2024225 is missing from the source and always interpolated) | not measured |
| `muni_code` | int | IBGE 7-digit municipality code of the field centroid | outside coverage |
| `vigor_2020`, `vigor_2024` | int | in the original contract (MapBiomas pasture vigor 1 low, 2 medium, 3 high); not written in this release because the product was not available | always absent |

`r_adj_2020` and `r_adj_2024` (the relative metric in peer standard deviations) are in the
analysis GeoParquet but not in the tiles.

The five compared change classes are thresholds on `D = r_adj_2024 - r_adj_2020` in peer
standard deviations: large decline below -2, decline -2 to -1, stable -1 to 1, gain 1 to 2,
large gain above 2. The 0.08 and 0.25 steps in `CHANGE_STEPS` describe the summary cells'
mean `change` on the ratio scale (tooltip and card) and are not class boundaries. The
zoomed-out change map colors each cell by `share_decline - share_gain`, the share of its
fields that declined minus the share that gained, with the `NET_STEPS` breaks at 5 and 15
percentage points; cells within 5 points, or with fewer than 10 fields, draw at low opacity.

MapBiomas classes the site names are listed in `CROPS` in `config.js` (the agricultural
classes 39, 19, 41, 20, 40, 62, 46, 47, 48, 35, 15, 21, 9, 18 and the natural and other
classes 3, 4, 5, 6, 49, 11, 12, 32, 29, 50, 23, 24, 30, 25, 33, 31, 0). Any other value
renders as "class N".

Tippecanoe drops a property whose value is null, so the page tests presence with `has`
rather than comparing against null.

## Summary layer attributes

One feature per H3 cell, over the scored 2024 fields. The layer holds three resolutions in
zoom bands that do not overlap, so the zoomed-out map shows regions rather than sub-pixel
cells: resolution 4 (about 40 km across) at zooms 3 to 5, resolution 5 (about 15 km) at
zooms 6 to 7, resolution 6 (about 6 km, 36 km²) at zooms 8 to 9. Every level aggregates the
fields directly, so a share is the share of the fields in that cell. The `res` property
names the level.

| property | type | meaning |
|---|---|---|
| `h3` | string | H3 cell index |
| `res` | integer | H3 resolution of the cell: 4, 5 or 6 |
| `n_fields` | int | fields with a centroid in the cell |
| `area_ha` | float | their total area |
| `mean_change` | float | mean `change` (ratio scale) over fields that have one |
| `share_decline` | float | share of fields in `decline` or `large_decline`, 0 to 1 |
| `share_gain` | float | share in `gain` or `large_gain`, 0 to 1 |
| `share_no_data` | float | share in `no_data`, 0 to 1 |
| `mean_prod_2020` | float | mean `prod_2020` over fields that have one |
| `mean_prod_2024` | float | mean `prod_2024` over fields that have one |
| `dominant_crop_2020` | int | most common `crop_2020` |
| `dominant_crop_2024` | int | most common `crop_2024` |
| `share_pasture` | float | share of fields with `crop_2024` 15 |
| `dominant_decision` | string | most common `decision`, including `none` |
| `mean_vigor_change` | float | in the original contract; absent in this release |

## stats.json

```json
{
  "placeholder": false,
  "generated": "2026-11-12",
  "years": [2020, 2024],
  "source": "MODIS MOD13Q1 16-day NDVI, 250 m",
  "brazil": { "n_fields": 24554482, "area_ha": 190716947.2,
              "change_class": { "stable": 15672741, "...": 0 },
              "decision": { "intensify": 7061028, "...": 0 },
              "crop_2020": { "15": 13704598, "...": 0 },
              "crop_2024": { "15": 13920904, "...": 0 },
              "confidence_low": 20344905 },
  "states": { "MT": { "same keys as brazil" } }
}
```

State keys are the two-letter codes in `STATES` in `config.js`; all 27 are present. Count
keys are the class values as strings. `n_fields` and `area_ha` count the 2024 outlines; the
`change_class` and `decision` counts also include the abandoned 2020 outlines, so they sum to
748,022 more than `n_fields` nationally. `confidence_low` is the number of fields with
`confidence` `low`. The page shows `confidence_low / n_fields` and
`change_class.no_data / n_fields` as shares.

## The placeholder

`docs/data/placeholder_fields.pmtiles` (1.8 MB) holds 2,576 real Trazo4 2024 outlines
from `E:\trazo4_master_parquet_seamfix\country=Brazil\state=Mato_Grosso\year=2024`, cut
with a `geom_bbox` filter on the window west -55.87, south -12.72, east -55.48, north
-12.33 near Sorriso. Geometries went through `shapely.make_valid`. `fid` and `area_ha` are
real; every other attribute is drawn at random with seed 20261112, and the placeholder has
no `confidence`, `no_data` or `none` values. `placeholder_summary.pmtiles` is the H3
resolution 7 aggregation of the same fields, and `placeholder_stats.json` its counts. The
script that made them is kept outside the repository; the recipe is the paragraph above.
