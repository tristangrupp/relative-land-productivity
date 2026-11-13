# Decisions, version 2: the area call first, the field call second

Written 2026-11-13 by the decision revamp agent. Scripts: `pipeline/s07_weather_refit.py`
(the weather test) and `pipeline/s07_decisions.py` (the decisions). The rules are in
methods/METHODS.md section 7. Every number below was read from the files these scripts wrote
under `F:\relative-land-productivity-data\analysis\weather_refit\`,
`F:\relative-land-productivity-data\analysis\decisions\` and `data/summaries/` on 13 November 2026.

## What the user asked for

"if productivity fell + crop type switch, thats a different story than just productivity
fell. if pasture is low productivity but its soy neighbors are high productivity, thats also a
very different story with different recommendation. if soy and pasture are all low in an area
and declining, restore the whole area." Then: "we keep the ecoregion reference scores, those
are good. we want to see larger scale land use tradeoffs ... but its important to also
consider the immediate area ... there needs to be a blend of the two."

Version 1 judged each field alone against the fields of the same class in its H3 resolution 5
cell. Version 2 adds an area call per cell, made from the cell's crops and pasture against the
same uses in the RESOLVE 2017 ecoregion, and makes the field call inside that area.

## Step 1: the weather refit was tested and not adopted

The ecoregion exploration (pipeline/EXPLORE_ECOREGIONS.md) found that the 2024 change of the
area term forms blocks of 50 to 200 km and recommended a refit of the weather term before the
area term is used. `s07_weather_refit.py compare` fitted layer 2 per ecoregion and peer class,
on the same group medians of both years and with the same guards as `s04_relative.py` (at
least 30 groups, both years, inputs clipped to the fitted range, the term capped at half the
intercept), with and without the field location's mean annual CHIRPS precipitation over the
agricultural years 2016 to 2024 as an extra regressor. Results
(`data/summaries/weather_refit_compare.json`):

| fit | pairs fitted | median R² | pooled R² | pairs with R² above 0.5 |
|---|---|---|---|---|
| state by class, anomalies (current) | 134 | 0.150 | 0.154 | 1 |
| ecoregion by class, anomalies | 146 | 0.126 | 0.123 | 7 |
| ecoregion by class, anomalies and mean precipitation | 146 | 0.188 | 0.184 | 14 |

The 2024 minus 2020 change of the area term, class weighted per cell over 19,856 cells:

| fit | Moran's I, ring 1 | neighbor correlation ring 1 / 2 / 4 / 8 | correlation with the change in precipitation anomaly | SD of the change |
|---|---|---|---|---|
| state by class (current) | 0.616 | 0.79 / 0.69 / 0.54 / 0.23 | 0.13 | 0.42 |
| ecoregion, anomalies | 0.626 | 0.79 / 0.70 / 0.57 / 0.37 | 0.09 | 0.43 |
| ecoregion, anomalies and mean precipitation | 0.626 | 0.79 / 0.70 / 0.56 / 0.35 | 0.04 | 0.44 |

Ring k is the H3 ring at k cells, about 15 km per step, so ring 8 is about 120 km. R squared
improves with the mean precipitation regressor, but the blocks do not shrink: the neighbor
correlation at 60 and 120 km rises, not falls. The change becomes less tied to the
precipitation anomaly (0.13 to 0.04), so the blocks are not the precipitation anomaly that the
fit sees; they may be temperature, timing of the rains within the window, or real regional
change, and this test cannot tell which. The 2024 level of the area term became somewhat less
blocky (ring 4 correlation 0.61 to 0.52). Since the purpose of the refit was the change blocks
and they did not improve, the state-class fit stays, and `apply` was not run. The relative
tables, `fields_scored.parquet` change classes and the ecoregion tables are those of the
13 November release. The fitted coefficients are kept in `data/summaries/weather_fit_eco.csv`.

## Step 2: the area call

Thresholds were set from the distribution of the pooled cell values (`s07_decisions.py dist`):

| group | cells with a 2024 value | level quartiles | share below -0.5 | change quartiles | share with change under -0.3 |
|---|---|---|---|---|---|
| crops | 8,506 | -0.34, +0.45 | 16.8% | -0.24, +0.26 | 20.7% |
| pasture | 18,653 | -0.47, +0.49 | 23.5% | -0.25, +0.28 | 21.6% |
| mosaic of uses (reported only) | 12,026 | -0.29, +0.57 | 15.6% | -0.44, +0.23 | 34.5% |

Below is a level under -0.5 ecoregion SD and declining is a change under -0.3 SD. A cell
median of 30 fields has a sampling error of about 0.23 SD and one of 210 fields (the median
row) about 0.09 SD, so both thresholds sit at two or more standard errors for most cells.

20,433 cells have a value for crops, pasture or mosaic. Area calls per cell and the 2024
fields inside those cells (`data/summaries/area_cells.csv.gz`, `area_decisions_by_state.csv`):

| area call | cells | fields |
|---|---|---|
| restore the area | 68 | 111,673 |
| good land underused | 1,432 | 2,970,980 |
| system misfit | 735 | 1,369,466 |
| area declining | 1,032 | 1,112,908 |
| area fine | 16,933 | 18,801,214 |
| no area call | 233 | 188,241 |

Only 6,959 cells have both a crop and a pasture value; 11,694 have pasture alone and 1,547
crops alone; 233 have only mosaic. A restore-the-area call needs both groups below and both
declining, which happens in 68 cells. The largest restore areas by field count are in
Pernambuco (42,303 fields), São Paulo (24,132), Bahia (12,375), Minas Gerais (8,654) and
Ceará (8,182). Good land underused is concentrated in Santa Catarina (870,793 fields), Rio
Grande do Sul (756,399) and Minas Gerais (483,082), where pasture sits next to strong crops;
system misfit in Paraná (362,464) and São Paulo (231,739).

## Step 3: the field call

National counts on the 24,554,482 2024 outlines, plus the 748,022 abandoned 2020 outlines
(`data/summaries/decisions_v2.json`, `decisions_v2_by_state.csv`):

| field call | fields |
|---|---|
| restore | 104,769 |
| recently converted, below peers | 418,860 |
| recently converted, at or above peers | 1,226,786 |
| improve or convert pasture | 645,098 |
| switch paid off | 1,668,338 |
| switch failed | 670,859 |
| improve yields | 6,705,702 |
| intensify | 6,712,927 |
| keep | 5,875,414 |
| abandon or change use | 133,960 |
| no data | 391,769 |
| abandoned since 2020 (2020 outlines) | 748,022 |

Of the 1,645,646 recently converted fields, 29,875 have no 2024 ecoregion value and are in
the at-or-above class; the site's note says "or not measured in 2024". No data is the 375,000
fields of change class no data plus 16,769 crop-switched fields with no 2024 value.

How the area call and the field call combine (`area_vs_field_decision.csv`): in the 68 restore
areas, 104,769 fields are restore, 4,907 recently converted, 638 abandon and 1,359 no data. In
good-land-underused cells, 645,098 pasture fields are improve or convert pasture, and the
pasture fields above their cell peers stay keep. 5,336,622 of the 6,705,702 improve-yields
fields lie in cells where the area is fine.

## Old against new

`data/summaries/decisions_v1_vs_v2.csv`, 2024 outlines. 14,150,021 fields (57.6 percent) keep
the same key; the rest move as follows.

| version 1 | fields | version 2 |
|---|---|---|
| restore | 1,262,572 | improve yields 1,225,939; improve or convert pasture 29,887; restore 6,746 |
| switch crop | 4,675,213 | improve yields 4,433,789; improve or convert pasture 221,596; restore 19,828 |
| change land use pattern | 2,424,420 | switch paid off 1,668,338; switch failed 670,859; improve or convert pasture 54,685; restore 13,769; no data 16,769 |
| intensify | 7,061,028 | intensify 6,712,927; improve or convert pasture 316,289; restore 31,812 |
| improve yields | 1,074,137 | improve yields 1,045,974; restore 5,522; improve or convert pasture 22,641 |
| keep | 5,902,506 | keep 5,875,414; restore 27,092 |
| abandon | 133,960 | abandon 133,960 |
| no suggestion | 2,020,646 | recently converted 1,645,646 (418,860 below peers); no data 375,000 |

The largest change is that restore is now an area call. Version 1 called 1,262,572 single
fields restore because each was below its cell peers and declining; version 2 calls 97.1
percent of those improve yields, because their areas are not weak and declining for both crops
and pasture. Restore on 2024 outlines falls from 1,262,572 to 104,769.

## The Amazon frontier

The seven Amazon frontier ecoregions of the exploration (Madeira-Tapajós, Xingu-Tocantins-
Araguaia, Mato Grosso tropical dry forests, Tocantins/Pindare, Tapajós-Xingu, Purus-Madeira,
Southwest Amazon moist forests) hold 2,814,635 fields (`decisions_v2_frontier.csv`):

| field call | fields | | area call | fields |
|---|---|---|---|---|
| restore | 285 | | restore the area | 301 |
| recently converted, below peers | 51,422 | | good land underused | 61,837 |
| recently converted, at or above | 225,411 | | system misfit | 53,879 |
| improve or convert pasture | 25,233 | | area declining | 272,172 |
| switch paid off | 18,230 | | area fine | 2,410,298 |
| switch failed | 9,592 | | no area call | 16,148 |
| improve yields | 766,797 | | | |
| intensify | 784,444 | | | |
| keep | 639,603 | | | |
| abandon | 16,190 | | | |
| no data | 277,428 | | | |

The frontier gets almost no restore call. Its cells are mostly pasture alone, and a cell with
one group present can be area declining but never restore the area, by the rule the user set.
272,172 frontier fields (9.7 percent) lie in area-declining cells, against 4.5 percent of all
fields nationally. All 285 frontier restore fields and all 301 fields in frontier restore areas
are in the Mato Grosso tropical dry forests. Recently converted land below its ecoregion
peers, the strongest restore case at field level, is 51,422 fields on the frontier and
418,860 nationally.

## Open questions for the user

1. Restore is now rare (104,769 fields in 68 cells). Should area declining with pasture
   alone (the frontier case) also lead to restore for the declining fields inside it, or stay
   an area flag?
2. A field below its cell peers on the same crop and stable was "switch crop" in version 1 and
   is "improve yields" now; whether the crop suits the land is answered only by the system
   misfit area call. Confirm.
3. Should pasture to crop conversion ever be suggested inside the Amazon biome (asked earlier,
   still open)? Version 2 suggests "improve or convert pasture" on 25,233 frontier pasture
   fields.

## Caveats

- The weather adjustment explains little (median R squared 0.15), and the refit did not remove
  the 50 to 200 km blocks in the change of the area term; part of every area-declining call may
  be weather, especially in the 2024 drought.
- MODIS at 250 m: 82.9 percent of fields are low confidence. Area calls rest on cell medians of
  at least 30 fields and are steadier than single fields.
- Wet-season cloud removes about a fifth of Pará's fields (no data); the frontier no-data count
  is 277,428.
- Pasture vigor is not implemented.
- Relative greenness is not yield; prod and change correlate below 0.24 with municipal yields.

## Run times and verification

`s07_weather_refit.py pclim` 16 s, `compare` 160 s; `s07_decisions.py area` 1 s, `fields`
3 minutes 20 seconds for the 27 states (Minas Gerais 24 s), `report` 20 s. Verified: the field
call counts sum to 24,554,482; the cross table rows match the version 1 national counts of
methods.html (restore 2,010,594 there includes the 748,022 abandoned outlines, and 1,262,572
plus 748,022 is 2,010,594); fid order of fields_scored, the metrics tables and the ecoregion
tables is asserted equal per state. Not verified: no field visit or independent reference
checks any of the calls.
