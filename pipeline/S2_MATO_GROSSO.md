# Sentinel-2 in Mato Grosso against the live MODIS result

Written 2026-11-14 by the Sentinel-2 Mato Grosso agent. The analysis chain ran on the Sentinel-2
(s2) monthly tables of Mato Grosso and was compared field by field with the live MODIS release.
Nothing on the site, in the tiles or in the live MODIS tables changed. Every number below was
read from the files listed at the end, written on 14 November 2026 between 04:35 and 04:45.

## Recommendation

Show both, and do not replace MODIS in Mato Grosso yet. Concretely:

1. Keep MODIS as the map's default layer and keep the area calls and the summary cells on MODIS.
   The s2 area tier, calibrated to the MODIS national reference, gives the same area call on
   93.3 percent of Mato Grosso's 3,132 H3 resolution 5 cells (94.7 percent of fields), so
   switching sensors would barely change the area layer.
2. Add the s2 values to the Mato Grosso fields as extra attributes (s2 prod 2024, s2 change
   class, s2 decision, s2 confidence) and show them in the field tooltip and card beside the
   MODIS values. This gives a 30 m value to 682,147 of the state's 684,199 MODIS
   low-confidence fields, 459,957 of them at high s2 confidence.
3. Do not make s2 the default for the change view in Mato Grosso until the source of its
   year-to-year noise is found. s2 calls 27.7 percent of comparable fields declining or
   gaining against 15.2 percent for MODIS. On fields over 100 ha, where MODIS is reliable, the
   s2 peer score of 2020 and of 2024 correlate at 0.25 against 0.40 for MODIS. Swapping now
   would draw Mato Grosso with almost twice the change rate of its MODIS neighbors, a seam
   that comes from the sensor, not from the land.
4. Waiting for the other tier 1 and tier 2 states is not needed for step 2, since the s2
   attributes are per field. A full switch of the change view (step 3) should wait for them
   and for the noise test below, so that neighboring states share one sensor.

The IBGE validation does not separate the two sensors: in Mato Grosso neither tracks municipal
soybean or maize yield (all Spearman values between -0.24 and +0.17 on the same
municipalities). It gives no reason to prefer s2 and no reason against it.

The test that would settle step 3: rerun s2 composites for a sample of Mato Grosso tiles with
every clear day of the month (no thinning to two to four days, `--days 0` or a large
`--days`) for both years, and see whether the 2020 to 2024 persistence of the peer score on
large fields rises toward the MODIS value. If it does, the noise is the scene thinning; if it
does not, s2 sees real year-to-year variation that MODIS smooths.

## Inputs checked

- `extracted\s2\year=2024\state=Mato_Grosso\ndvi_monthly.parquet`: 1,151,506 fields (the same
  fids in the same order as the prepared 2024 fields and the MODIS metrics), 24 months.
  Meta: 1,011 of 1,013 tiles complete, 1,010 with output, share of fields under 8 valid months
  0.0042 for 2020 and 0.0043 for 2024.
- `extracted\s2\year=2020\state=Mato_Grosso\ndvi_monthly.parquet`: 978,055 fields (equal to
  the prepared 2020 fields), 1,011 of 1,013 tiles complete, 995 with output, share under 8
  valid months 0.0044 and 0.0045.
- 4,567 fields of the 2024 layer have no valid month in the 2024 agricultural year (127 in
  2020); they sit in the tiles without output and become no data.

## Step 1: metrics

`s04_metrics.py --source s2 --states Mato_Grosso` for polygons 2024 with agricultural years
2024 and 2020, and for polygons 2020 with 2020. The s2 tables hold only fid and the series, so
`s04_metrics.py` now takes `area_ha` and `mbmode` from the prepared fields when the NDVI table
lacks them (the MODIS path is unchanged). Each month weighs one month, so integrals are in
NDVI-months like MODIS. Median seasonal integral over valid agricultural fields: 3.32 (2024)
and 3.40 (2020) NDVI-months on the 2024 polygons, 3.36 on the 2020 polygons. 125 fields in
2024 and 4,328 in 2020 fail the half-window rule. 11 to 15 s per run.

## Step 2: relative productivity

`s04_relative.py --source s2 --polys 2024 --states Mato_Grosso --no-summary-copy`, then
`--polys 2020`, which applies the saved fit. `--no-summary-copy` keeps the live
`data/summaries/weather_fit.csv` untouched.

Weather fit: refitted on s2. The code refits whenever the polygon year is 2024 and no
`--fit-from` is given, and a refit is also the consistent choice, because the fit's intercept
and coefficients are in the sensor's integral units (s2 intercepts are 3 to 32 percent higher
than MODIS for the same class). The design is the same as the live one: the live fit is
per state and class too, from Mato Grosso's groups only. Six of seven classes were fitted
(cotton has one year only, as in MODIS); median R squared 0.054 against 0.074 for the MODIS
Mato Grosso fit; no field hit the cap. The coefficients have the same signs and similar sizes
as MODIS for pasture and temporary crops. Sensitivity: applying the MODIS fit to s2 instead
gives an r_adj 2024 that correlates at 0.99993 with the refit version and the same change
class on 99.65 percent of comparable fields, so the choice does not matter.

Peer groups and the border. MODIS pools peer groups across state borders; s2 has only Mato
Grosso. Measured on the MODIS data (Mato Grosso alone against Mato Grosso plus Rondônia,
Amazonas, Pará, Tocantins, Goiás and Mato Grosso do Sul), so that only the border effect
differs:

| effect on Mato Grosso's 1,151,506 fields | fields |
|---|---|
| lose their peer group (no group of 30 up to H3 resolution 3) | 112 |
| change group, all to a coarser H3 level | 1,145 |
| keep the same group with fewer peers | 26,103 |
| total affected | 27,360 (2.4 percent) |

167 of the state's 3,132 resolution 5 cells also hold fields of a neighboring state; 26,405
fields lie in them. On s2 itself 1,146,103 of 1,146,814 valid 2024 fields have a group
(resolution 5: 1,104,974; 4: 36,025; 3: 5,104).

## Step 3: change classes and decisions

`s08_s2_compare.py` reproduces `s04_change.py` (change classes, version 1 decision for the
abandon rule) and `s07_decisions.py` (area call, field call) in memory, because those two
scripts write `fields_scored.parquet` at a path with no source in it and would overwrite the
live MODIS tables. Output: `analysis\source=s2\year=2024\state=Mato_Grosso\fields_scored.parquet`
(attributes only, no geometry).

s2 confidence is low when the field is under 0.45 ha (five 30 m pixels) or fewer than 75
percent of the window months were observed in either year: 228,320 fields, 220,193 of them
for size.

### Area tier: calibrated to the MODIS national reference

Chosen: calibrate s2 to MODIS, not a within-state reference. The user asked for Brazil as the
reference of the area call; a within-state reference cancels Mato Grosso's own mean, so a
state whose crops sit above Brazil (most of Mato Grosso) would still have its lowest fifth
called below. Measured, the within-state version calls 24 restore areas and 313 area-declining
cells where MODIS calls 0 and 40, and agrees with the live call on 80.9 percent of cells
against 93.3 percent for the calibrated version.

Calibration: per peer class and agricultural year, on fields over 25 ha with high MODIS
confidence, valid on both sensors and in the same peer class, s2 metric_adj is mapped linearly
so that its median and robust SD match MODIS. OLS of MODIS on s2 is reported but not used,
because noise in s2 flattens the OLS slope (soybean 2020: 0.59 OLS against 1.04 matched).
`data/summaries/s2_mt_calibration.csv`:

| peer class | year | fields | Pearson | matched slope | residual SD in national cell SD |
|---|---|---|---|---|---|
| pasture 15 | 2020 / 2024 | 140,358 / 138,493 | 0.90 / 0.90 | 0.89 / 0.84 | 0.53 / 0.51 |
| soybean 39 | 2020 / 2024 | 60,947 / 66,951 | 0.58 / 0.75 | 1.04 / 0.98 | 0.68 / 0.59 |
| temporary crops 19 | 2020 / 2024 | 12,840 / 10,161 | 0.78 / 0.80 | 0.79 / 0.84 | 0.44 / 0.45 |
| mosaic 21 | 2020 / 2024 | 2,149 / 7,869 | 0.84 / 0.86 | 0.76 / 0.72 | 0.60 / 0.58 |
| sugarcane 20 | 2020 / 2024 | 1,731 / 1,636 | 0.91 / 0.94 | 0.75 / 0.73 | 0.69 / 0.70 |
| forest plantation 9 | 2020 / 2024 | 1,491 / 1,512 | 0.94 / 0.96 | 0.69 / 0.71 | 0.46 / 0.46 |
| cotton 62 | 2020 | 149 | 0.54 | 0.89 | 0.77 |

Cotton 2024 has 94 calibration fields, under the 100 required, so cotton cells have no 2024
area value. The residual SD is per field; cell medians of 30 fields average most of it away.
Calibrated s2 cell values then go through `s07_decisions.area_call` unchanged against the
MODIS national medians and cell SD (`analysis\decisions\national_summary.json`, resolution 5).

What is lost: a cell on the border has only its Mato Grosso fields in s2, and the national
medians stay MODIS medians, so the area tier inherits any error in the calibration.

## Step 4: s2 against MODIS, field by field

### Change classes

On all 1,151,506 fields the change class is the same on 73.0 percent. Crop switched and newly
cropped come from MapBiomas and agree by construction (55,020 and 69,165). On the 1,021,906
fields comparable on both sensors, 70.0 percent have the same class, 73.6 percent the same
direction (decline, stable, gain), and 0.46 percent opposite directions.
`data/summaries/s2_mt_change_confusion.csv`, rows MODIS, columns s2:

| MODIS \ s2 | large decline | decline | stable | gain | large gain | no data |
|---|---|---|---|---|---|---|
| large decline | 11,702 | 3,599 | 3,075 | 253 | 98 | 143 |
| decline | 19,237 | 29,505 | 28,279 | 1,705 | 408 | 407 |
| stable | 20,855 | 82,402 | 643,183 | 88,034 | 13,749 | 3,637 |
| gain | 433 | 1,486 | 26,828 | 26,143 | 10,487 | 229 |
| large gain | 102 | 194 | 2,383 | 2,628 | 5,138 | 80 |
| no data | 27 | 71 | 290 | 82 | 31 | 418 |

s2 moves many MODIS-stable fields into decline or gain. Declining fields: 169,613 on s2
against 98,411 on MODIS (14.7 against 8.5 percent of all fields); gaining 148,756 against
76,131 (12.9 against 6.6 percent). The reason is the spread of D, the 2024 minus 2020 peer
score: its robust SD is 0.97 on s2 and 0.68 on MODIS. By size band:

| size band | robust SD of D, s2 / MODIS | correlation of 2020 and 2024 peer scores, s2 / MODIS |
|---|---|---|
| under 6.25 ha | 1.00 / 0.64 | 0.52 / 0.73 |
| 6.25 to 25 ha | 0.92 / 0.66 | 0.36 / 0.63 |
| 25 to 100 ha | 0.93 / 0.75 | 0.31 / 0.47 |
| over 100 ha | 1.02 / 0.92 | 0.25 / 0.40 |

On small fields MODIS reads mostly the same shared 250 m pixels in both years, so its peer
score is persistent by construction and its change is damped; s2 removes that. On fields over
100 ha both sensors resolve the field, and s2 is still less persistent (0.25 against 0.40).
Part of the extra s2 change is therefore noise of the s2 composites or real variation that the
16-day MODIS series smooths; this analysis cannot tell which.

### Correlations by field size

Pearson correlation between the sensors, same peer class in both
(`data/summaries/s2_mt_corr_by_size.csv`, which also has Spearman):

| quantity | under 6.25 ha | 6.25 to 25 ha | 25 to 100 ha | over 100 ha | all |
|---|---|---|---|---|---|
| seasonal integral 2020 | 0.66 | 0.79 | 0.82 | 0.75 | 0.73 |
| seasonal integral 2024 | 0.67 | 0.82 | 0.87 | 0.82 | 0.75 |
| peer score r_adj 2020 | 0.56 | 0.73 | 0.76 | 0.68 | 0.64 |
| peer score r_adj 2024 | 0.53 | 0.72 | 0.78 | 0.75 | 0.62 |
| change D | 0.51 | 0.72 | 0.75 | 0.65 | 0.62 |
| same change class (share, comparable fields) | 0.67 | 0.74 | 0.75 | 0.65 | 0.70 |
| same decision (share, all fields) | 0.54 | 0.62 | 0.66 | 0.63 | 0.59 |

Agreement rises from the smallest band to 25 to 100 ha and dips over 100 ha. 50.4 percent of
Mato Grosso's fields are under 6.25 ha (median 6.09 ha).

### Decisions

The field decision is the same on 58.7 percent of fields
(`data/summaries/s2_mt_decision_confusion.csv`). Most disagreement is between neighbors on the
level scale: of 362,146 MODIS intensify fields, s2 calls 176,596 intensify, 91,344 improve
yields and 86,754 keep. Switch paid off and switch failed agree on 29,376 and 10,754 fields
and swap on 13,673. Abandon rises from 8,027 to 12,877 and improve or convert pasture from
15,719 to 24,273. Neither sensor calls restore in Mato Grosso.

| decision | MODIS | s2 |
|---|---|---|
| improve yields | 339,085 | 353,793 |
| intensify | 362,146 | 340,720 |
| keep | 301,786 | 291,305 |
| recently converted, at or above | 57,159 | 50,003 |
| switch paid off | 36,520 | 36,351 |
| improve or convert pasture | 15,719 | 24,273 |
| recently converted, below | 12,006 | 19,162 |
| switch failed | 17,803 | 17,581 |
| abandon | 8,027 | 12,877 |
| no data | 1,255 | 5,441 |

### Area calls

Per resolution 5 cell (`data/summaries/s2_mt_area_confusion_cells.csv`), over the 3,132 cells
that hold Mato Grosso fields, the call is the same in 93.3 percent. MODIS: area fine 2,571,
good land underused 137, area declining 40, system misfit 4, no call 380. s2: 2,448, 207, 58,
2 and 417. Of MODIS's 137 good-land-underused cells s2 keeps 111; of its 40 area-declining
cells, 21. s2 adds 96 good-land-underused and 36 area-declining cells that MODIS calls fine.
Per field the area call agrees on 94.7 percent. The cell values themselves correlate at 0.83
(crop level), 0.58 (crop change), 0.87 (pasture level) and 0.81 (pasture change).

### MODIS low-confidence fields

Of the 684,199 Mato Grosso fields that MODIS marks low confidence, 681,986 get an s2 r_adj for
2024, 682,147 get an s2 change class other than no data, and 459,957 of those are high s2
confidence (at least 0.45 ha and 75 percent of the window months in both years). No data
rises from 919 fields on MODIS to 4,914 on s2, mostly the 4,567 fields in tiles without
output.

### Validation against IBGE municipal yields

Same municipalities on both sensors (at least 20 valid fields of the crop on each), PAM table
5457 already on disk (`analysis\validation\raw`). Spearman correlation of the area-weighted
municipal mean with yield (`data/summaries/s2_mt_validation.csv` has Pearson too):

| crop | year | municipalities | integral MODIS / s2 | prod MODIS / s2 | r_adj MODIS / s2 |
|---|---|---|---|---|---|
| soybean | 2020 | 112 | 0.18 / 0.14 | 0.04 / -0.04 | 0.08 / 0.03 |
| soybean | 2024 | 117 | 0.09 / 0.17 | 0.07 / -0.11 | 0.05 / -0.03 |
| soybean | change | 112 | -0.04 / 0.02 | 0.05 / -0.16 | 0.02 / -0.08 |
| maize | 2020 | 112 | 0.03 / -0.24 | -0.21 / -0.14 | -0.21 / -0.16 |
| maize | 2024 | 108 | 0.03 / 0.00 | 0.01 / 0.09 | 0.01 / 0.08 |
| maize | change | 105 | 0.12 / 0.08 | 0.07 / 0.11 | 0.06 / 0.09 |
| sugarcane | 2020 | 15 | 0.50 / 0.61 | 0.33 / 0.39 | 0.32 / 0.49 |
| sugarcane | 2024 | 15 | -0.25 / -0.19 | -0.01 / -0.16 | -0.03 / -0.21 |

The MODIS numbers on this common set match the live Mato Grosso rows of
`data/summaries/validation.csv` to within 0.03. Soybean yields vary little between Mato
Grosso municipalities, and maize here is the second-season crop under a union window, so
neither sensor's greenness ranks municipalities by yield. Sugarcane has 15 municipalities,
too few to read.

## Not done

- No tiles, no site change, no upload. The s2 `fields_scored.parquet` has no geometry; a tile
  build would join it to the prepared fields by fid.
- The abandoned layer was not rebuilt on s2. The s2 metrics and relative tables for the 2020
  polygons exist (978,055 fields, 973,990 valid) if it is wanted.
- The noise test above (unthinned composites on sample tiles) was not run; it needs the
  network link, which the running extraction is using.
- Ecoregion trend (`eco_trend`) and the ecoregion context columns were not recomputed for s2;
  they are context only and do not enter any call.

## Files

Scripts: `pipeline/s04_metrics.py` (s2 table fix), `pipeline/s08_s2_compare.py` (border,
change, calibrate, area, fields, compare, validate). Commands, in order:

```
python pipeline\s04_metrics.py --source s2 --polys 2024 --ay 2024 --states Mato_Grosso --workers 1
python pipeline\s04_metrics.py --source s2 --polys 2024 --ay 2020 --states Mato_Grosso --workers 1
python pipeline\s04_metrics.py --source s2 --polys 2020 --ay 2020 --states Mato_Grosso --workers 1
python pipeline\s04_relative.py --source s2 --polys 2024 --states Mato_Grosso --no-summary-copy
python pipeline\s04_relative.py --source s2 --polys 2020 --states Mato_Grosso --no-summary-copy
python pipeline\s08_s2_compare.py all
```

Data, under `F:\relative-land-productivity-data\analysis\`:
`metrics\source=s2\polys=<2020|2024>\ay=<2020|2024>\Mato_Grosso.parquet`,
`relative\source=s2\...` and `relative\source=s2\weather_fit.json`,
`source=s2\year=2024\state=Mato_Grosso\fields_scored.parquet`,
`source=s2\decisions\` (calibration, cell table, area cells, within-state area cells),
`source=s2\compare\` (border and comparison JSON), `source=s2\validation\`, `source=s2\logs\`.
Summaries: `data/summaries/s2_mt_*.csv` (seven files). Peak memory of every step was under
3 GB; the whole chain runs in under two minutes.
