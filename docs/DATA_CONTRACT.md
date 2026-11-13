# Data contract between the tiles and the site

The site reads three files. Their URLs and every attribute name live in `docs/config.js`,
in `CONFIG`, `ATTR` and `SUMMARY_ATTR`. The analysis stage writes tiles that match this
file; if a name has to change, change it in `config.js` and here, nowhere else. This version
describes the tiles released on 13 November 2026, read back from the PMTiles metadata, with
the version 2 decision attributes added the same day (`decision` on new values,
`area_decision`, `eco_id`; summary `dominant_area_decision`, the decision shares and the area
terms). The site also reads `docs/data/ecoregions.json` from Pages (`CONFIG.ECOREGIONS_URL`).

## Files

| config key | URL | what it is |
|---|---|---|
| `FIELDS_PMTILES` | `https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/tiles/fields.pmtiles` | one polygon per 2024 Trazo4 field plus the abandoned 2020 fields, layer name `fields`, zoom 9 to 13, 6.36 GB |
| `SUMMARY_PMTILES` | `.../tiles/summary.pmtiles` | one polygon per H3 resolution 6 cell (144,909 cells, about 6 km across) at every zoom, layer name `summary`, zoom 3 to 9, 92.2 MB |
| `STATS_URL` | `.../tiles/stats.json` | class counts for Brazil and per state, read by the legend and the Where card |
| `ECOREGIONS_URL` | `./data/ecoregions.json` (on Pages) | RESOLVE 2017 ecoregion names by `eco_id`, with the class-weighted (`c`, `p`) and per peer class (`k`: class to `[Scale C change, plain change percent]`) context written by `s07_decisions.py lookup` |

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
| `decision` | string | version 2 field call (methods section 7.2): one of `restore`, `converted_below`, `converted_ok`, `convert_pasture`, `switch_paid_off`, `switch_failed`, `improve_yields`, `intensify`, `keep`, `abandon`, `abandoned_outline` (the abandoned 2020 outlines), `none` (no data) | never absent |
| `area_decision` | string | area call of the field's H3 resolution 5 cell (methods section 7.1): `restore_area`, `good_land_underused`, `system_misfit`, `area_declining`, `area_fine`, `none` (no area call); abandoned 2020 outlines take the call of the cell of their centroid | never absent |
| `eco_id` | int | RESOLVE 2017 `ECO_ID` of the field centroid; the key into `ecoregions.json` | 0 for the 3 unassigned fields |
| `confidence` | string | `low` when the field is under 6.25 ha (one MODIS pixel) or fewer than 75 percent of its window composites were observed in either year, else `high` | never absent |
| `n_obs_2020` | int | observed (not interpolated) 16-day composites inside the 2020 growing season window, 0 to 23 | not measured |
| `n_obs_2024` | int | the same for 2024, 0 to 22 (composite 2024225 is missing from the source and always interpolated) | not measured |
| `muni_code` | int | IBGE 7-digit municipality code of the field centroid | outside coverage |
| `vigor_2020`, `vigor_2024` | int | in the original contract (MapBiomas pasture vigor 1 low, 2 medium, 3 high); not written in this release because the product was not available | always absent |

`r_adj_2020` and `r_adj_2024` (the relative metric in peer standard deviations),
`decision_v1` (the version 1 suggestion: `restore`, `switch_crop`, `change_pattern`, `abandon`,
`intensify`, `improve_yields`, `keep`, `none`) and `eco_trend` (`declining`, `steady`,
`gaining`, `unknown`: the ecoregion-class Scale C change at plus or minus 0.1) are in the
analysis GeoParquet but not in the tiles.

The five compared change classes are thresholds on `D = r_adj_2024 - r_adj_2020` in peer
standard deviations: large decline below -2, decline -2 to -1, stable -1 to 1, gain 1 to 2,
large gain above 2. The 0.08 and 0.25 steps in `CHANGE_STEPS` describe the summary cells'
mean `change` on the ratio scale (tooltip and card) and are not class boundaries. Since 13 November 2026 the
zoomed-out change map colors each cell by `nat_change` on the continuous `FRONTIER_RAMP`
(-1.0 to +1.0 national SD, gray at zero; cells with fewer than 10 fields at opacity 0.55). The
net share `share_decline - share_gain` that colored it before is in the tooltip and the cell
card, next to `nat_pct_change`.

MapBiomas classes the site names are listed in `CROPS` in `config.js` (the agricultural
classes 39, 19, 41, 20, 40, 62, 46, 47, 48, 35, 15, 21, 9, 18 and the natural and other
classes 3, 4, 5, 6, 49, 11, 12, 32, 29, 50, 23, 24, 30, 25, 33, 31, 0). Any other value
renders as "class N".

Tippecanoe drops a property whose value is null, so the page tests presence with `has`
rather than comparing against null.

## Summary layer attributes

One feature per H3 resolution 6 cell (about 6 km, 36 km²), over the scored 2024 fields, at
every zoom from 3 to 9 (13 November 2026, at the user's request for a finer map). Coarser
levels (15 km at zooms 3 to 4, 40 km, 100 km) were used before and rejected as too coarse.
Resolution 7 (about 2.5 km) at zooms 7 to 9 was built and measured 173.0 MB on its own, over
the 150 MB budget, so it is not used. Every level aggregates the
fields directly, so a share is the share of the fields in that cell. The `res` property
names the level.

| property | type | meaning |
|---|---|---|
| `h3` | string | H3 cell index |
| `res` | integer | H3 resolution of the cell: 5 or 6 |
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
| `dominant_decision` | string | most common `decision` (version 2), including `none` |
| `dominant_area_decision` | string | the area call of the parent resolution 5 cell |
| `share_restore`, `share_improve_yields`, `share_convert_pasture`, `share_switch_failed` | float | share of the cell's fields with that `decision`, 0 to 1 |
| `share_converted` | float | share with `converted_below` or `converted_ok` |
| `area_crops_2024`, `area_pasture_2024`, `area_mosaic_2024` | float | pooled `cell_vs_nation` of the parent resolution 5 cell in 2024, national SD of cell medians; the terms of the area call; absent with under 30 fields of every class of the group |
| `area_crops_change`, `area_pasture_change`, `area_mosaic_change` | float | the same, 2024 minus 2020 |
| `nat_change` | float | the national frontier value: class-weighted change, 2024 minus 2020, of the cell's class medians against the national class medians, in national SD of cell medians per class (`cell_vs_nation`); the cell's own value where a class has 30 fields, else its resolution 5 parent's; the change view colors the cell on a continuous ramp from -1.0 to +1.0 |
| `nat_pct_change` | float | class-weighted plain change in weather-adjusted greenness, percent of 2020, over fields valid in both years with the same class |
| `top_action` | string | the actionable decision (not keep, intensify or none) most over-represented against its national share, among those covering at least 15 percent of the cell's fields and 1.5 times their national share; absent when none qualifies (drawn as "no action stands out") |
| `top_action_share` | float | the share of the cell's fields with `top_action` |
| `top_area` | string | the most common `area_decision` other than `area_fine` and `none` among the cell's fields (inherited from the parent resolution 5 cell); absent when there is none; the Area decision view draws it when `top_area_share` is at least 0.15 |
| `top_area_share` | float | the share of the cell's fields with `top_area` |
| `top3` | string | the cell's three most common decisions with shares, `key:share|key:share|key:share` |
| `eco_crops_2024`, `eco_pasture_2024`, `eco_crops_change`, `eco_pasture_change` | float | the same pooled terms as `area_*` against the RESOLVE 2017 ecoregion instead of Brazil (secondary context) |
| `eco_trend` | string | `declining`, `steady` or `gaining`: class-weighted Scale C change of the ecoregion holding most of the resolution 5 cell's fields, at plus or minus 0.1 national cell SD |
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
              "decision": { "intensify": 6712927, "abandoned_outline": 748022, "...": 0 },
              "decision_v1": { "intensify": 7061028, "...": 0 },
              "area_decision": { "area_fine": 18801214, "...": 0 },
              "crop_2020": { "15": 13704598, "...": 0 },
              "crop_2024": { "15": 13920904, "...": 0 },
              "confidence_low": 20344905 },
  "states": { "MT": { "same keys as brazil" } }
}
```

State keys are the two-letter codes in `STATES` in `config.js`; all 27 are present. Count
keys are the class values as strings. `n_fields` and `area_ha` count the 2024 outlines; the
`change_class` and `decision` counts also include the abandoned 2020 outlines, so they sum to
748,022 more than `n_fields` nationally. The abandoned outlines count as `decision.abandoned_outline`,
`decision_v1.restore` and under the `area_decision` of their cell, so `area_decision` sums to
the same total. `confidence_low` is the number of fields with
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
