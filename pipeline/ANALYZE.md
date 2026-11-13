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

One composite of agricultural year 2024 is missing from the input. Terra composite 2024225
(12 to 27 August 2024) has no item on the Planetary Computer for any of the 18 MODIS tiles,
and `raw\modis\missing.json` lists only that composite. Its raw column is NaN in every 2024
table, and the filled series that the metrics stage reads interpolates across it, so every
2024 table has 22 composites with data of 23 columns. The 2020 tables have all 23. The
assembly fix that produced the 2024 tables is commit f5e9b86, and `pipeline/EXTRACT.md`
has a section on it.

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
twice per state: zoom 12 to 13 with `-pk -pf` (no size limit, no feature limit, nothing
dropped or merged; the files are still named `_z12_14` from an earlier setting, and the
tile-join warning "mismatched maxzooms: 13" confirms the top zoom is 13) and zoom 9 to 11 with `--coalesce-densest-as-needed -pf`, both with
`-ab` (shared borders) and `-P`; `--drop-densest-as-needed` is not used. The per-state
files are joined with `tile-join -pk`. The Trazo4 outlines are 10 m pixel staircases (131
vertices on a median 0.4 ha Tocantins field, 5.3 KB of GeoJSON each, about 75 GB for the
country), so each polygon is simplified with a one-pixel tolerance of 0.0001 degree with
topology preserved (27 vertices, 0.6 KB; the median drawn area is unchanged and 5 percent
of fields lose over 17 percent of drawn area) and coordinates are rounded to 5 decimals.
`area_ha` keeps the original value. The summary layer is one hexagon per H3 resolution 6
cell with the contract's means and counts over the scored 2024 fields, plus
`share_no_data`; `mean_vigor_change` is absent because vigor is null.

## Results of the national run, 12 November 2026

Written 2026-11-13 by the reporting agent from `F:\relative-land-productivity-data\analysis\`
(`run_all.log`, `year=2024\state=<State>\counts.json`, `relative\source=modis\`), from
`tiles\stats.json` and `tiles\tiles_log.jsonl`, and from the two CSV files in
`data/summaries/`. Every number below was read from those files with a script; none is
copied from another agent's report.

### Stage times

`s04_run_all.py` waited from 19:25:59 for the last MODIS NDVI tables, found them all at
22:35:00 and ran the stages in order. Times are from `run_all.log`.

| stage | command | wall seconds |
|---|---|---|
| metrics, 2024 polygons, agricultural year 2024 | `s04_metrics.py --polys 2024 --ay 2024 --workers 3` | 74 |
| metrics, 2024 polygons, agricultural year 2020 | `s04_metrics.py --polys 2024 --ay 2020 --workers 3` | 75 |
| metrics, 2020 polygons, agricultural year 2020 | `s04_metrics.py --polys 2020 --ay 2020 --workers 3` | 67 |
| relative, 2024 polygons, both years | `s04_relative.py --polys 2024` | 79 |
| relative, 2020 polygons | `s04_relative.py --polys 2020` | 33 |
| change classes and decisions | `s04_change.py --workers 3` | 122 |
| validation | `s04_validate.py` | 27 |
| tiles | `s05_tiles.py all --workers 4 --parallel 3` | 2,494 |
| upload | `s05_upload.py` | 2,104, exit code 1 |

The metrics, relative, change and validate stages together took 477 seconds (22:35:00 to
22:42:57). The tiles stage ended at 23:24:31 and the first upload at 23:59:35, so the whole
run took 84 minutes 35 seconds. Every state reported `status ok` in every stage. The only
warnings in the log are numpy `All-NaN slice` and `Mean of empty slice` messages from fields
with no valid composite in a window.

### Fields that entered the peer groups

From `relative_summary_polys=2024.json` and `relative_summary_polys=2020.json`. A field is
valid when its class is agricultural and at least half of its window composites have a raw
value. Grouped means it found a peer cell at H3 resolution 5, 4 or 3.

| table | fields | valid | grouped | grouped at resolution 5 |
|---|---|---|---|---|
| 2024 polygons, year 2024 | 24,554,482 | 24,338,019 (99.1%) | 24,333,109 | 24,089,417 (99.0% of grouped) |
| 2024 polygons, year 2020 | 24,554,482 | 22,625,394 (92.1%) | 22,620,827 | 22,361,379 (98.9%) |
| 2020 polygons, year 2020 | 21,632,817 | 21,446,785 (99.1%) | 21,442,130 | 21,182,055 (98.8%) |

The 1,929,088 fields of the 2024 polygons that fail the 2020 gate are mostly the 1,645,646
whose MapBiomas 2020 class is not agricultural. Most of the rest are in Pará, where the
metrics log counts 217,910 fields with fewer than half of the 2020 window composites observed
(Pará: 868,062 of 1,238,196 fields valid in 2020, 1,109,143 in 2024). Amapá is the other
weak state: 1,687 of 8,420 fields valid in 2020 and 2,621 in 2024.

### Weather fit

`data/summaries/weather_fit.csv` has 176 peer class by state pairs, one row each. 134 were
fitted. The 42 not fitted all had fewer than 30 peer groups, and 7 of those also had groups
in only one year. The fitted pairs hold 114,385 of the 114,837 peer groups. Across the 134
fitted pairs the median R squared is 0.150. One pair is above 0.5 (Alagoas pasture, class
15, 245 groups, R squared 0.574), 18 are above 0.3 and 47 are below 0.1. The next four are
Minas Gerais other perennial (class 48) 0.461, Acre pasture 0.452, Espírito Santo sugarcane
0.438 and Distrito Federal mosaic (class 21) 0.438. The weather term hit its cap of half the
intercept on 126,853 fields for agricultural year 2020 and 216,033 fields for 2024 on the
2024 polygons, and on 122,448 fields on the 2020 polygons (`run_all.log` lines
`term_capped_fields`). The median 2024 group anomaly over the fitted pairs is a precipitation
deficit of 0.39 SD and a temperature excess of 1.36 SD.

The weather layer explains a small part of the between-cell variation in group medians, so
`r_adj` stays close to the unadjusted R1 for most fields. The product does not separate the
2023 to 2024 drought from management with any confidence.

### National change classes and decisions

From `tiles\stats.json` (`brazil`), which matches the sum of the 27 `counts.json` files
exactly. The 24,554,482 scored fields are the 2024 polygons. Shares are of that total.

| change_class | fields | share |
|---|---|---|
| stable | 15,672,741 | 63.8% |
| crop_switched | 2,424,420 | 9.9% |
| decline | 1,777,196 | 7.2% |
| gain | 1,661,737 | 6.8% |
| newly_cropped | 1,645,646 | 6.7% |
| large_decline | 510,660 | 2.1% |
| large_gain | 487,082 | 2.0% |
| no_data | 375,000 | 1.5% |

The abandoned layer holds 748,022 polygons, the 2020 fields whose MapBiomas 2024 class is not
agricultural, 3.5 percent of the 21,632,817 prepared 2020 fields. `stats.json` adds them to
`change_class.abandoned` and to `decision.restore` but not to `n_fields`, so its
`change_class` and `decision` counts sum to 25,302,504, not 24,554,482, and
`brazil.decision.restore` is 2,010,594, of which 1,262,572 are 2024 polygons.

| decision | fields | share of 2024 polygons |
|---|---|---|
| intensify | 7,061,028 | 28.8% |
| keep | 5,902,506 | 24.0% |
| switch_crop | 4,675,213 | 19.0% |
| change_pattern | 2,424,420 | 9.9% |
| none | 2,020,646 | 8.2% |
| restore | 1,262,572 (plus 748,022 abandoned) | 5.1% |
| improve_yields | 1,074,137 | 4.4% |
| abandon | 133,960 | 0.5% |

`none` is exactly `newly_cropped` plus `no_data`. `confidence_low` is set on 20,344,905
fields, 82.9 percent, because 78 percent of fields are under one MODIS pixel (6.25 ha) and
the rest of the flag comes from the 75 percent observation rule.

### Per state

Shares are of the state's 2024 polygons. Gain is `gain` plus `large_gain`, decline is
`decline` plus `large_decline`, switched is `crop_switched`, new is `newly_cropped`, low
conf. is `confidence_low`. Abandoned is a count of 2020 polygons and is outside the shares.

| state | fields | stable | gain | decline | switched | new | no_data | low conf. | abandoned |
|---|---|---|---|---|---|---|---|---|---|
| Acre | 172,628 | 69.7% | 4.5% | 7.6% | 0.1% | 17.9% | 0.1% | 91.3% | 3,344 |
| Alagoas | 299,345 | 68.2% | 9.8% | 9.9% | 7.5% | 3.6% | 1.1% | 93.2% | 8,763 |
| Amapá | 8,420 | 4.0% | 1.2% | 1.3% | 0.9% | 33.0% | 59.6% | 100.0% | 351 |
| Amazonas | 152,019 | 53.1% | 5.9% | 8.3% | 0.0% | 27.6% | 5.1% | 97.1% | 6,613 |
| Bahia | 2,342,495 | 65.2% | 9.0% | 9.1% | 8.1% | 7.3% | 1.4% | 88.6% | 111,694 |
| Ceará | 686,875 | 54.1% | 8.0% | 8.0% | 7.7% | 21.8% | 0.5% | 94.9% | 38,820 |
| Distrito Federal | 33,485 | 65.7% | 5.3% | 6.4% | 13.9% | 8.7% | 0.0% | 87.5% | 2,268 |
| Espírito Santo | 609,809 | 60.4% | 9.9% | 9.7% | 17.8% | 2.1% | 0.0% | 90.6% | 10,791 |
| Goiás | 1,253,488 | 70.4% | 5.5% | 6.6% | 13.1% | 4.5% | 0.0% | 62.3% | 34,807 |
| Maranhão | 567,125 | 60.6% | 6.9% | 8.1% | 3.5% | 17.1% | 3.8% | 90.6% | 26,885 |
| Mato Grosso | 1,151,506 | 74.0% | 6.6% | 8.6% | 4.8% | 6.0% | 0.1% | 59.4% | 23,140 |
| Mato Grosso do Sul | 590,173 | 65.9% | 8.8% | 9.5% | 13.5% | 2.3% | 0.0% | 43.7% | 6,524 |
| Minas Gerais | 4,078,771 | 71.7% | 6.6% | 7.0% | 11.0% | 3.6% | 0.0% | 82.1% | 89,763 |
| Pará | 1,238,196 | 51.3% | 6.8% | 8.1% | 0.8% | 12.3% | 20.7% | 95.1% | 22,945 |
| Paraíba | 511,631 | 62.2% | 7.1% | 7.7% | 11.7% | 9.0% | 2.3% | 96.0% | 24,546 |
| Paraná | 1,869,028 | 60.7% | 11.8% | 11.9% | 13.1% | 2.5% | 0.0% | 82.9% | 42,768 |
| Pernambuco | 853,306 | 63.6% | 7.6% | 8.8% | 10.1% | 7.9% | 2.0% | 94.7% | 43,425 |
| Piauí | 521,325 | 61.2% | 5.7% | 5.5% | 11.0% | 16.6% | 0.0% | 91.1% | 40,254 |
| Rio Grande do Norte | 315,440 | 61.2% | 8.4% | 10.0% | 12.7% | 5.3% | 2.4% | 94.8% | 12,874 |
| Rio Grande do Sul | 2,345,289 | 54.8% | 12.2% | 12.1% | 10.7% | 10.2% | 0.0% | 86.7% | 90,696 |
| Rio de Janeiro | 269,184 | 72.8% | 7.2% | 7.8% | 10.7% | 1.4% | 0.1% | 83.3% | 4,632 |
| Rondônia | 617,670 | 77.4% | 6.8% | 9.1% | 0.4% | 5.8% | 0.5% | 85.4% | 4,023 |
| Roraima | 66,184 | 62.3% | 5.6% | 8.3% | 2.1% | 19.8% | 1.9% | 88.8% | 1,899 |
| Santa Catarina | 1,385,998 | 59.1% | 12.2% | 11.9% | 13.1% | 3.7% | 0.0% | 94.4% | 40,366 |
| São Paulo | 1,913,933 | 59.2% | 12.4% | 13.2% | 14.4% | 0.8% | 0.0% | 71.8% | 26,158 |
| Sergipe | 220,252 | 61.8% | 11.4% | 11.8% | 8.7% | 5.7% | 0.6% | 95.8% | 6,007 |
| Tocantins | 480,907 | 73.9% | 5.1% | 5.9% | 4.1% | 10.9% | 0.1% | 66.5% | 23,666 |

Pará has 256,202 `no_data` fields, 20.7 percent of its fields and 68 percent of the national
375,000. The cause is the wet-season cloud cover that EXTRACT.md describes. Amapá has 5,019
`no_data` of 8,420 and every field low confidence. Low confidence is lowest where fields are
largest: Mato Grosso do Sul 43.7 percent, Mato Grosso 59.4, Goiás 62.3, Tocantins 66.5. The
highest `newly_cropped` shares are Amazonas 27.6 percent, Ceará 21.8, Roraima 19.8, Acre 17.9
and Maranhão 17.1, where the MapBiomas 2020 class inside a 2024 field is forest, savanna or
grassland. Minas Gerais took the longest in every per-state stage (51.1 seconds in change,
640.2 seconds for its GeoJSON).

### Validation against SIDRA municipal yields

`s04_validate.py` compares municipal area-weighted means of three field metrics with IBGE PAM
yields (SIDRA table 5457, variable 112, kg per ha) for soybean (class 39), sugarcane (class
20) and maize (classes 19 and 41 in the states where maize is the dominant temporary crop by
PAM 2023 area), in municipalities with at least 20 valid fields. `data/summaries/validation.csv`
has 351 rows: 27 for Brazil and 324 for states with at least 20 municipalities. The Brazil
rows:

| crop | year | metric | municipalities | Spearman | Pearson |
|---|---|---|---|---|---|
| soybean | 2020 | integral | 1,951 | 0.459 | 0.529 |
| soybean | 2020 | prod | 1,951 | 0.015 | 0.024 |
| soybean | 2020 | r_adj | 1,951 | 0.058 | 0.037 |
| soybean | 2024 | integral | 2,089 | 0.093 | 0.123 |
| soybean | 2024 | prod | 2,089 | 0.113 | 0.090 |
| soybean | 2024 | r_adj | 2,089 | 0.178 | 0.148 |
| maize | 2020 | integral | 2,289 | -0.043 | -0.091 |
| maize | 2020 | prod | 2,289 | 0.116 | 0.109 |
| maize | 2020 | r_adj | 2,289 | 0.103 | 0.093 |
| maize | 2024 | integral | 2,175 | -0.030 | -0.065 |
| maize | 2024 | prod | 2,175 | 0.117 | 0.083 |
| maize | 2024 | r_adj | 2,175 | 0.093 | 0.077 |
| sugarcane | 2020 | integral | 985 | 0.230 | 0.214 |
| sugarcane | 2020 | prod | 985 | -0.057 | -0.005 |
| sugarcane | 2020 | r_adj | 985 | -0.083 | -0.017 |
| sugarcane | 2024 | integral | 950 | 0.480 | 0.407 |
| sugarcane | 2024 | prod | 950 | -0.022 | 0.034 |
| sugarcane | 2024 | r_adj | 950 | -0.042 | 0.020 |
| soybean | change | integral | 1,946 | 0.234 | 0.254 |
| soybean | change | prod | 1,946 | -0.021 | 0.020 |
| soybean | change | r_adj | 1,946 | -0.016 | -0.007 |
| maize | change | integral | 2,088 | -0.021 | 0.022 |
| maize | change | prod | 2,088 | 0.026 | 0.019 |
| maize | change | r_adj | 2,088 | 0.033 | 0.030 |
| sugarcane | change | integral | 939 | -0.013 | -0.071 |
| sugarcane | change | prod | 939 | 0.063 | 0.027 |
| sugarcane | change | r_adj | 939 | 0.078 | 0.053 |

The raw seasonal integral has a moderate correlation with yield for soybean in 2020
(Spearman 0.46) and sugarcane in 2024 (0.48), a weak one for sugarcane 2020 (0.23) and
soybean 2024 (0.09), and none for maize (-0.04 and -0.03). `prod` and `r_adj` are within
0.18 of zero for every crop and year. Part of that is by construction: both are relative to
the median of the peer cell, so the municipal mean of `prod` is close to 1 everywhere, and the
between-municipality yield differences that SIDRA reports are what the peer normalization
removes. The change correlations (municipal 2024 minus 2020 metric against the yield
difference) are 0.23 for the soybean integral and under 0.08 for every other row. Of the 324
state rows, 8 have a Spearman at or above 0.5, all for the raw integral: maize in Ceará 2020
(0.60, 72 municipalities), Mato Grosso do Sul 2020 (0.54) and 2024 (0.59); soybean in
Tocantins 2024 (0.52) and Piauí 2024 (0.51, 23 municipalities); sugarcane in Paraná 2020
(0.61) and 2024 (0.60) and Mato Grosso do Sul 2024 (0.71, 34 municipalities). The median
state-level Spearman for `prod` and `r_adj` is between -0.04 and 0.17 in every crop and year.

The validation is weak. The raw integral tracks soybean and sugarcane yields in some years
and maize in none. The relative measures and the change are not correlated with yields or
yield change at the municipal level, so `prod` and `change` must not be read as yield
estimates. The maize result is also a definition problem: classes 19 and 41 pool every
temporary crop, and MapBiomas does not separate maize from them.

### Tiles

From the production entries in `tiles_log.jsonl` (time 22:42:57 onward; the earlier entries
are development runs on Mato Grosso and Tocantins). The GeoJSON step wrote 27 state files
with 25,302,504 features (the 24,554,482 scored 2024 polygons plus the 748,022 abandoned 2020
polygons), 17,770,294,310 bytes, 4,648.7 seconds of worker time, the longest Minas Gerais at
640.2 seconds for 4,168,534 features. tippecanoe ran 54 times, 2,732.4 seconds of worker
time: the 27 zoom 12 to 13 files total 3,873,813,589 bytes (largest Minas Gerais,
606,711,939 bytes in 180.1 seconds) and the 27 zoom 9 to 11 files 2,499,490,343 bytes.
tile-join of the 54 files gave `fields.pmtiles`, 6,362,425,967 bytes in 323.9 seconds. The
summary layer has 144,909 H3 resolution 6 cells, 53,262,339 bytes, 89.7 seconds. `stats.json`
is 28,863 bytes with 27 states. The tiles stage took 2,494 seconds of wall time with 4
GeoJSON workers and 3 tippecanoe runs in parallel.

### Upload and public URLs

The first `s05_upload.py` run (23:24:31 to 23:59:35) put the three tile objects on S3:
`stats.json` (28,863 bytes, 2.1 s), `summary.pmtiles` (53,262,339 bytes, 15.2 s) and
`fields.pmtiles` (6,362,425,967 bytes, 1,402.4 s, 4.54 MB/s). It then uploaded the GeoParquet
of eight states in alphabetical order (Acre, Alagoas, Amapá, Amazonas, Bahia, Ceará, Distrito
Federal, Espírito Santo, both the scored fields and the abandoned file) and the Goiás scored
fields (605,690,130 bytes), and failed with exit code 1 on the Goiás abandoned file when the
connection dropped. Commit 8462fb3 made the script skip an object S3 already holds at the same
size and retry a dropped connection. The orchestrator restarted it as `s05_upload.py --fields`,
logging to `analysis\upload_fields_resume.log`.

Public URLs, verified by the orchestrator with HTTP 206 range responses at 00:05 on 13
November 2026:

- https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/tiles/fields.pmtiles
- https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/tiles/summary.pmtiles
- https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/tiles/stats.json

GeoParquet, one file per state, under
`https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/fields/year=2024/state=<State>/fields_scored.parquet`
(the scored 2024 polygons with `r_adj_2020` and `r_adj_2024`) and
`.../fields/abandoned/state=<State>.parquet` (the abandoned 2020 polygons). State names use
the folder spelling, for example `Mato_Grosso` and `Rio_Grande_do_Sul`.

Upload state as read from `upload_fields_resume.log` on 2026-11-13: the resumed run skipped
the 17 objects already on S3 at the same size, uploaded the Goiás abandoned file on its third
attempt (8,332,870 bytes, 114.6 s, after two "Connection was closed" errors), then Maranhão
(scored fields 298,397,671 bytes in 72.4 s, abandoned 7,780,801 bytes), Mato Grosso (scored
fields 1,283,571,038 bytes in 290.4 s, abandoned 12,951,897 bytes) and Mato Grosso do Sul
(scored fields 410,369,771 bytes in 97.1 s, abandoned 1,882,247 bytes). The log had 26 lines
and no "UPLOAD EXIT" line when this section was written, so the run was still going, with
Minas Gerais next and the states from Minas Gerais to Tocantins pending. Check the tail of
that log for "UPLOAD EXIT 0" before treating the GeoParquet set as complete.

### Open items

- The METHODS.md overlay rules for abandoned and newly cropped fields were not applied, only
  the MapBiomas class rules.
- Pasture vigor is null in every table and tile; `mean_vigor_change` is absent from the
  summary layer.
- The weather correction is weak (median R squared 0.15) and the validation of the relative
  measures against yields is near zero, as reported above.
- The `_z12_14` file names under `tiles\states\` hold zoom 12 and 13.
- The development folder `analysis\dev` (319,865,570 bytes, two partial `ndvi_16day.parquet`
  tables for Mato Grosso and Tocantins) was deleted on 2026-11-13 after the national run.
