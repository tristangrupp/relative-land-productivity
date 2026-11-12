# Data contract between the tiles and the site

The site reads three files. Their URLs and every attribute name live in `docs/config.js`,
in `CONFIG`, `ATTR` and `SUMMARY_ATTR`. The analysis agent writes tiles that match this
file; if a name has to change, change it in `config.js` and here, nowhere else.

## Files

| config key | default URL | what it is |
|---|---|---|
| `FIELDS_PMTILES` | `https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/tiles/fields.pmtiles` | one polygon per 2024 Trazo4 field, layer name `fields`, zoom 9 to 14 |
| `SUMMARY_PMTILES` | `.../tiles/summary.pmtiles` | one polygon per H3 cell, layer name `summary`, zoom 3 to 9 |
| `STATS_URL` | `.../tiles/stats.json` | class counts for Brazil and per state, read by the legend and the Where card |

The bucket is public read with CORS, so GitHub Pages can range-read the PMTiles. The
tile files are written by tippecanoe (`-l fields -Z9 -z14`, `-l summary -Z3 -z9`).

`CONFIG.USE_PLACEHOLDER` switches the page to the placeholder copies in `docs/data/`.
Set it to `false` once the real tiles are on S3.

## Fields layer attributes

| property | type | meaning | null means |
|---|---|---|---|
| `fid` | int | Trazo4 field id from the 2024 parquet | never null |
| `area_ha` | float | field area in hectares (ESRI:102033 equal area) | never null |
| `crop_2020` | int | modal MapBiomas Collection 10 class inside the 2024 outline, 2020 coverage | no coverage |
| `crop_2024` | int | modal MapBiomas Collection 10 class inside the 2024 outline, 2024 coverage | no coverage |
| `prod_2020` | float | weather-adjusted relative productivity 2020: the field's seasonal greenness divided by the median of its peers (same crop, same region). 1.0 is the peer median | not cropped or not measured in 2020 |
| `prod_2024` | float | the same for 2024 | not cropped or not measured in 2024 |
| `change` | float | `prod_2024` minus `prod_2020`, only when both exist and the crop class is the same | not comparable |
| `change_class` | string | one of `large_decline`, `decline`, `stable`, `gain`, `large_gain`, `crop_switched`, `newly_cropped`, `abandoned` | never null |
| `vigor_2020` | int | MapBiomas pasture vigor class 1 low, 2 medium, 3 high, modal inside the outline | not pasture in 2020 |
| `vigor_2024` | int | the same for 2024 | not pasture in 2024 |
| `decision` | string | one of `restore`, `switch_crop`, `change_pattern`, `abandon`, `intensify`, `improve_yields`, `keep` | never null |
| `n_obs_2020` | int | clear composites inside the 2020 growing season window | not measured |
| `n_obs_2024` | int | the same for 2024 | not measured |
| `muni_code` | int | IBGE 7-digit municipality code of the field centroid | outside coverage |

The change class thresholds the legend states are 0.08 and 0.25 in relative productivity.
If the methods agent sets different thresholds, update `CHANGE_CLASSES` in `config.js`.

MapBiomas classes the site names: 39 soybean, 19 temporary crop, 41 other temporary crop,
20 sugarcane, 40 rice, 62 cotton, 46 coffee, 47 citrus, 48 other perennial, 35 oil palm,
15 pasture, 21 mosaic of uses, 9 forest plantation, 18 agriculture, 3 forest, 4 savanna,
12 grassland, 24 urban, 30 mining, 33 water. Any other value renders as "class N".

Tippecanoe drops a property whose value is null, so the page tests presence with `has`
rather than comparing against null.

## Summary layer attributes

One feature per H3 cell (resolution 7 in the placeholder; the analysis agent chooses the
resolution for the full set and may use municipalities instead, as long as the names hold).

| property | type | meaning |
|---|---|---|
| `h3` | string | H3 cell index (or municipality code if municipalities are used) |
| `n_fields` | int | fields with a centroid in the cell |
| `area_ha` | float | their total area |
| `mean_change` | float | mean `change` over fields that have one |
| `share_decline` | float | share of fields in `decline` or `large_decline`, 0 to 1 |
| `share_gain` | float | share in `gain` or `large_gain`, 0 to 1 |
| `mean_prod_2020` | float | mean `prod_2020` over fields that have one |
| `mean_prod_2024` | float | mean `prod_2024` over fields that have one |
| `dominant_crop_2020` | int | most common `crop_2020` |
| `dominant_crop_2024` | int | most common `crop_2024` |
| `share_pasture` | float | share of fields with `crop_2024` 15 |
| `mean_vigor_change` | float | mean of `vigor_2024` minus `vigor_2020` over fields with both |
| `dominant_decision` | string | most common `decision` |

## stats.json

```json
{
  "placeholder": false,
  "generated": "YYYY-MM-DD",
  "years": [2020, 2024],
  "brazil": { "n_fields": 0, "area_ha": 0.0,
              "change_class": { "stable": 0, "...": 0 },
              "decision": { "keep": 0, "...": 0 },
              "crop_2020": { "39": 0, "...": 0 },
              "crop_2024": { "39": 0, "...": 0 } },
  "states": { "MT": { "same keys as brazil" } }
}
```

State keys are the two-letter codes in `STATES` in `config.js`. Count keys are the class
values as strings. A state that has no tiles yet can be left out; the Where card then
shows the Brazil block.

## The placeholder

`docs/data/placeholder_fields.pmtiles` (1.8 MB) holds 2,576 real Trazo4 2024 outlines
from `E:\trazo4_master_parquet_seamfix\country=Brazil\state=Mato_Grosso\year=2024`, cut
with a `geom_bbox` filter on the window west -55.87, south -12.72, east -55.48, north
-12.33 near Sorriso. The brief asked for a 0.15 degree window; that window held 441
fields because Sorriso fields are large, so the window was widened to 0.39 degrees.
Geometries went through `shapely.make_valid`. `fid` and `area_ha` are real; every other
attribute is drawn at random with seed 20261112. `placeholder_summary.pmtiles` is the H3
resolution 7 aggregation of the same fields, and `placeholder_stats.json` its counts. The
script that made them is kept outside the repository; the recipe is the paragraph above.
