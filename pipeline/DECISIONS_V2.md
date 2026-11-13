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
same uses across Brazil (first against the RESOLVE 2017 ecoregion, changed the same day at the
user's request), and makes the field call inside that area. Later the same day the user also
asked for a finer and less uniform zoomed-out map and shorter legends; those changes are
reported below and in WORKLOG.md.

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

## Step 2: the area call, on the national reference

The first build of the area call (13 November 2026, morning) compared each cell's crops and
pasture with the same uses in its RESOLVE 2017 ecoregion. After reading the ecoregion
results the user asked for Brazil as the reference: "lets do brazil as a whole then to get
the true frontiers of productivity change". The area call now uses `cell_vs_nation`
(methods/METHODS.md section 7.1): the cell median of a class against the national median of
the class, in national SD of cell medians. The ecoregion terms stay as secondary context in
the cell card and the tooltip.

`s07_decisions.py national` computed 48,865 (cell, class) rows at resolution 5 (44,078 with a
change, 42,301 with a plain percent change) and 174,114 at resolution 6 (150,196 and 143,050),
in 19 s. The pooled distributions over resolution 5 cells (`s07_decisions.py dist`):

| group | cells | level quartiles | 20th percentile of level | change quartiles | 20th percentile of change |
|---|---|---|---|---|---|
| crops | 8,601 | -0.35, +0.96 | -0.52 | -0.29, +0.23 | -0.36 |
| pasture | 18,737 | -0.80, +0.56 | -0.96 | -0.34, +0.36 | -0.43 |
| mosaic (reported only) | 12,146 | -0.18, +1.19 | -0.36 | -0.54, +0.25 | -0.64 |

Below is a level under -0.75 national SD and declining a change under -0.4. The level
threshold puts 24.4 percent of pasture cells and 5.6 percent of crop cells below; the change
threshold puts 19.0 percent of pasture cells and 7.2 percent of crop cells in decline. Crop
cells sit mostly above the national crop medians (median pooled level +0.38), so few crop
areas are below Brazil.

Area calls per resolution 5 cell and the 2024 fields inside those cells
(`data/summaries/area_cells.csv.gz`, `area_decisions_by_state.csv`):

| area call | cells | fields | first build, ecoregion reference: cells / fields |
|---|---|---|---|
| restore the area | 52 | 93,244 | 68 / 111,673 |
| good land underused | 1,675 | 3,096,673 | 1,432 / 2,970,980 |
| system misfit | 356 | 883,479 | 735 / 1,369,466 |
| area declining | 1,189 | 1,224,818 | 1,032 / 1,112,908 |
| area fine | 16,993 | 19,072,057 | 16,933 / 18,801,214 |
| no area call | 272 | 184,211 | 233 / 188,241 |

7,073 cells have both a crop and a pasture value, 11,664 pasture alone and 1,528 crops alone.
The largest restore areas by field count are in São Paulo (38,976 fields), Espírito Santo
(22,319), Santa Catarina (12,193), Minas Gerais (10,449) and Rio de Janeiro (3,885). Good
land underused is concentrated in Rio Grande do Sul (799,773 fields), Santa Catarina
(722,562), Minas Gerais (480,567) and Paraná (335,697); system misfit in Paraná (376,608), São
Paulo (200,871) and Pernambuco (156,832); area declining in Rio Grande do Sul (212,544) and
Pará (211,516).

## The national frontier map

The zoomed-out change view now shows the class-weighted `cell_vs_nation` change per summary
cell on a continuous ramp. Over resolution 5 cells its quartiles are -0.32 and +0.26, its 5th
and 95th percentiles -0.90 and +0.80; over resolution 6 cells -0.36 and +0.30, and -1.03 and
+0.92. The ramp runs from -1.0 to +1.0 with stops at -0.4 and +0.4 and the balanced gray at
zero. The plain percent change was the alternative: its resolution 5 quartiles are -7.2 and
+6.0 percent. The national SD change was chosen because it removes each class's nationwide
shift (pasture -2.3 percent nationally, much of it the 2024 drought) and puts classes with
different integral scales on one unit; the plain percent change is shown in the tooltip, next
to the old net share of fields declining minus gaining.

## Step 3: the field call

National counts on the 24,554,482 2024 outlines, plus the 748,022 abandoned 2020 outlines
(`data/summaries/decisions_v2.json`, `decisions_v2_by_state.csv`):

| field call | fields |
|---|---|
| restore | 91,076 |
| recently converted, below peers | 418,860 |
| recently converted, at or above peers | 1,226,786 |
| improve or convert pasture | 633,043 |
| switch paid off | 1,669,629 |
| switch failed | 671,801 |
| improve yields | 6,715,891 |
| intensify | 6,722,391 |
| keep | 5,879,276 |
| abandon or change use | 133,960 |
| no data | 391,769 |
| abandoned since 2020 (2020 outlines) | 748,022 |

Of the 1,645,646 recently converted fields, 29,875 have no 2024 ecoregion value and are in the
at-or-above class; the site's note says "or not measured in 2024". No data is the 375,000
fields of change class no data plus 16,769 crop-switched fields with no 2024 value.

How the area call and the field call combine (`area_vs_field_decision.csv`): in the 52 restore
areas, 91,076 fields are restore, 1,647 recently converted, 500 abandon and 21 no data. In
good-land-underused cells 633,043 pasture fields are improve or convert pasture, and pasture
above its cell peers stays keep. 5,417,955 of the 6,715,891 improve-yields fields lie in cells
where the area is fine.

## Old against new

`data/summaries/decisions_v1_vs_v2.csv`, 2024 outlines. 14,164,524 fields (57.7 percent) keep
the same key; the rest move as follows.

| version 1 | fields | version 2 |
|---|---|---|
| restore | 1,262,572 | improve yields 1,226,690; improve or convert pasture 29,193; restore 6,689 |
| switch crop | 4,675,213 | improve yields 4,441,993; improve or convert pasture 217,182; restore 16,038 |
| change land use pattern | 2,424,420 | switch paid off 1,669,629; switch failed 671,801; improve or convert pasture 52,804; restore 13,417; no data 16,769 |
| intensify | 7,061,028 | intensify 6,722,391; improve or convert pasture 311,653; restore 26,984 |
| improve yields | 1,074,137 | improve yields 1,047,208; improve or convert pasture 22,211; restore 4,718 |
| keep | 5,902,506 | keep 5,879,276; restore 23,230 |
| abandon | 133,960 | abandon 133,960 |
| no suggestion | 2,020,646 | recently converted 1,645,646 (418,860 below peers); no data 375,000 |

Restore is now an area call. Version 1 called 1,262,572 single fields restore because each was
below its cell peers and declining; version 2 calls 97.2 percent of those improve yields,
because their areas are not weak and declining for both crops and pasture. Restore on 2024
outlines falls from 1,262,572 to 91,076.

## The Amazon frontier

The seven Amazon frontier ecoregions of the exploration (Madeira-Tapajós, Xingu-Tocantins-
Araguaia, Mato Grosso tropical dry forests, Tocantins/Pindare, Tapajós-Xingu, Purus-Madeira,
Southwest Amazon moist forests) hold 2,814,635 fields (`decisions_v2_frontier.csv`):

| field call | fields | | area call | fields |
|---|---|---|---|---|
| restore | 0 | | restore the area | 0 |
| recently converted, below peers | 51,422 | | good land underused | 72,416 |
| recently converted, at or above | 225,411 | | system misfit | 22,869 |
| improve or convert pasture | 31,777 | | area declining | 338,554 |
| switch paid off | 18,211 | | area fine | 2,365,490 |
| switch failed | 9,552 | | no area call | 15,306 |
| improve yields | 763,788 | | | |
| intensify | 781,180 | | | |
| keep | 639,676 | | | |
| abandon | 16,190 | | | |
| no data | 277,428 | | | |

The frontier gets no restore call. Its cells are mostly pasture alone, and a cell with one
group present can be area declining but never restore the area, by the rule the user set.
338,554 frontier fields (12.0 percent) lie in area-declining cells, against 5.0 percent of all
fields nationally; on the ecoregion reference it was 272,172 (9.7 percent). By ecoregion, area
declining holds 85,714 fields in Xingu-Tocantins-Araguaia, 80,852 in Madeira-Tapajós, 50,885
in Tapajós-Xingu, 48,306 in the Mato Grosso tropical dry forests, 32,652 in Southwest Amazon,
22,297 in Tocantins/Pindare and 17,848 in Purus-Madeira. Recently converted land below its
ecoregion peers, the strongest restore case at field level, is 51,422 fields on the frontier
and 418,860 nationally.

## The zoomed-out decision map

The summary cell of the decision view showed the modal decision, which was intensify in most
cells (the user: "on the recommendations zoom out, the whole thing is orange!"). The summary
now shows the cell's top action: the actionable decision (any except keep, intensify and no
data) most over-represented against its national share, among those covering at least 15
percent of the cell's fields and at least 1.5 times their national share; other cells are a
gray "no action stands out". The most common actionable decision alone was tried first: over
the 144,909 resolution 6 cells it is improve yields in 100,538, because improve yields is
27.35 percent of all fields, and with a 15 percent floor it still colored 93,359 cells the
same amber. With the 1.5 lift rule 68,556 cells take a color: recently converted at or above
25,003, improve yields 17,508, switch paid off 9,471, recently converted below 7,449, improve
or convert pasture 6,359, switch failed 1,941, abandon 468, restore 357. 15 percent is about
twice the national share of every actionable decision except improve yields (restore 0.37,
recently converted 6.7, improve or convert pasture 2.6, switch paid off 6.8, switch failed
2.7, abandon 0.55 percent). The tooltip lists the cell's top three decisions with shares.
Intensify now draws in a muted khaki (#c4b38f) instead of orange (#eb6834).

## Open questions for the user

1. Restore is now rare (91,076 fields in 52 cells) and absent from the Amazon frontier.
   Should area declining with pasture alone (the frontier case) also lead to restore for the
   declining fields inside it, or stay an area flag?
2. A field below its cell peers on the same crop and stable was "switch crop" in version 1 and
   is "improve yields" now; whether the crop suits the land is answered only by the system
   misfit area call. Confirm.
3. Should pasture to crop conversion ever be suggested inside the Amazon biome (asked earlier,
   still open)? Version 2 suggests "improve or convert pasture" on 31,777 frontier pasture
   fields.
4. The top-action rule of the zoomed-out decision map adds a 1.5 lift to the coordinator's
   15 percent share; confirm or choose another rule.

## Caveats

- The weather adjustment explains little (median R squared 0.15), and the refit did not remove
  the 50 to 200 km blocks in the change of the area term; part of every area-declining call and
  of the national frontier map may be weather, especially the 2024 drought, which the national
  reference does not cancel.
- MODIS at 250 m: 82.9 percent of fields are low confidence. Area calls rest on cell medians of
  at least 30 fields and are steadier than single fields.
- Wet-season cloud removes about a fifth of Pará's fields (no data); the frontier no-data count
  is 277,428.
- Pasture vigor is not implemented.
- Relative greenness is not yield; prod and change correlate below 0.24 with municipal yields.

## Run times and verification

`s07_weather_refit.py pclim` 16 s, `compare` 160 s; `s07_decisions.py national` 19 s, `area`
1 s, `fields` about 3 minutes 20 seconds for the 27 states, `report` 21 s. Verified: the
field call counts sum to 24,554,482; the cross table rows match the version 1 national counts
of methods.html (restore 2,010,594 there includes the 748,022 abandoned outlines, and
1,262,572 plus 748,022 is 2,010,594); the area-by-field table sums to the restore-area field
count; fid order of fields_scored, the metrics, relative and ecoregion tables is asserted
equal per state. Not verified: no field visit or independent reference checks any call.
