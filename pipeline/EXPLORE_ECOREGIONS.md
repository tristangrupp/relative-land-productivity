# Relative productivity against ecoregion peers: can the map judge a whole region?

Written 2026-11-13 by the ecoregion exploration agent. Script: `pipeline/s06_ecoregion_peers.py`.
Every number below was read from the files the script wrote under
`F:\relative-land-productivity-data\analysis\ecoregions\` and `data/summaries/` on 13 November 2026.

## The question

The user's words: "my issue with the relative productivity differences being in the cell is
that we cant make calls on whether or not we should restore the frontier, influence much larger
areas or scales, etc. would relative productivity work within climate zones or ecoregions, much
larger areas, than cells? explore that with 2017 resolve ecoregions for the relative difference
comparison."

The published map scores each field against the fields of the same MapBiomas class in the same
H3 resolution 5 cell, about 17 km across. The cell median is the zero point, so a decline that
every field in a cell shares disappears from the map. The map can say which field in a cell
fell behind its neighbors. It cannot say that the Tapajós frontier as a whole fell behind the
rest of Brazil, because the frontier is the reference it measures against.

## Three scales and what each cancels

Any relative score subtracts the center of its reference group, so it cannot see a change that
the whole group shares. The only way to judge a region is to measure it against a larger
reference. This exploration builds three nested scales on one metric, the weather-adjusted
seasonal NDVI integral of `s04_relative.py` (`metric_adj`, in NDVI-months).

Scale A is the existing product: the field against the median of its class in its H3
resolution 5 cell, in units of 1.4826 times the median absolute deviation (MAD) of that group,
the robust standard deviation (SD). It cancels everything the cell shares: the regional trend,
the regional weather, the regional soil. It keeps the field's standing against its neighbors.

Scale B is new: the field against the median of its class in its RESOLVE 2017 ecoregion, in
robust SD units of the ecoregion-class distribution. It cancels what the ecoregion shares and
keeps everything inside it, which is the field's management plus the climate and soil gradient
inside the ecoregion. From Scale B comes the cell-within-ecoregion term: the cell median of the
class against the ecoregion-class median, in the same SD units. That term says whether an area
of about 250 km² stands below or above its ecoregion, and its change between the two years says
whether the area lost or gained ground against its ecoregion. It is the "frontier inside the
ecoregion" signal.

Scale C is new: the ecoregion-class median against the national class median, in robust SD
units of the national distribution of cell medians of that class. It cancels only what the whole
country shares, so it can say that an ecoregion stands below the nation and whether that gap
widened. Next to it sits the plain weather-adjusted change: the median over the ecoregion's
fields of (metric_adj 2024 minus metric_adj 2020), divided by the 2020 ecoregion-class median,
as a percent. The plain change cancels nothing. It is the number that can say "the frontier as
a whole lost ground", at the price of keeping any weather the adjustment missed.

## Data and method

Fields: the 24,554,482 agricultural 2024 polygons, with both agricultural years computed on the
2024 outlines (`analysis\metrics\source=modis\polys=2024\ay=<2020|2024>\<State>.parquet`). The
validity gate is the one of `s04_relative.load_year`: agricultural class, finite integral, and
at least half of the window composites observed. The weather adjustment is
`s04_relative.apply_weather` with the fit saved at `analysis\relative\source=modis\weather_fit.json`,
so `metric_adj` is the same quantity the relative tables hold. This was checked by joining the
recomputed values to the relative table of Acre for both years: the maximum absolute difference
is 0.0 for 2020 and 2.4e-7 for 2024, no field differs in validity, and the fid order is the same.
The fit was built for the cell design: per peer class and state, on the cell medians of both
years, median R squared 0.15 across the 134 fitted pairs (ANALYZE.md). It removes part of the
climate gradient inside an ecoregion and leaves the rest, which matters most in the large Amazon
ecoregions, as the caveats say.

Ecoregions: RESOLVE Ecoregions 2017 (Dinerstein et al. 2017), the official distribution
`https://storage.googleapis.com/teow2016/Ecoregions2017.zip`, downloaded on 13 November 2026 to
`F:\relative-land-productivity-data\raw\ecoregions\` (shapefile, 243 MB unpacked, 846 polygons
worldwide; the DBF is latin-1 and is read with `SHAPE_ENCODING=ISO-8859-1`, so names such as
Madeira-Tapajós keep their accents). The local `D:\WRI\Field Boundaries\WWF ecoregions\official\`
copy is the 2001 WWF edition and was not used. The 76 ecoregions that touch Brazil's bounding
box (longitude -74.1 to -34.7, latitude -33.9 to 5.4) were rasterized to ECO_ID at 0.005
degrees, a 7,860 by 7,880 int32 grid, in 4 seconds. Each field takes the ecoregion of the grid
cell under its centroid (`lon`, `lat` of the metrics tables). 24,553,822 fields fell on an
ecoregion directly; 657 fell on no ecoregion (coast and river pixels) and took the nearest
ecoregion within 0.05 degrees by a Euclidean distance transform; 3 remained unassigned (one in
Santa Catarina, two in São Paulo) and get no value. The assignment is cached as
`analysis\ecoregions\field_eco\<State>.parquet` (fid, eco_id, eco_filled). 46 ecoregions hold at
least one class group of 30 fields; the largest by fields valid in both years are the Cerrado
(4,160,101), Caatinga (3,290,887), Alto Paraná Atlantic forests (3,052,060) and Araucaria
moist forests (2,172,901).

Groups and thresholds: a Scale B group is (ECO_ID, peer class, year) with at least 30 valid
fields, the same minimum as the cell design; a cell-within-ecoregion value needs 30 valid fields
of the class in the cell and inside the ecoregion, in that year; the national SD of Scale C is
the robust SD of the cell medians of the class over cells with at least 30 valid fields. The
Scale B change `d_eco` is `r_eco_2024 - r_eco_2020` for fields whose peer class is the same in
both years, classed at the METHODS.md section 6 thresholds (large decline below -2, decline -2
to -1, stable -1 to 1, gain 1 to 2, large gain above 2); fields whose class changed are
`crop_switched`, fields missing either year are `no_data`. Peer classes pool MapBiomas 19 and
41, as in `s04_relative.py`. The class-weighted row of an ecoregion weights each class by its
number of fields valid in both years.

Outputs: `analysis\ecoregions\fields\<State>.parquet` with fid, eco_id, peer_cls_2020,
peer_cls_2024, r_eco_2020, r_eco_2024, d_eco, cell_vs_eco_2020, cell_vs_eco_2024,
eco_change_class (the Scale B class) and change_class_a (the Scale A class from
`fields_scored.parquet`, for the comparison); `data/summaries/ecoregions.csv` (291 rows: one
per ecoregion and peer class plus a class-weighted `all` row per ecoregion, 73 KB);
`data/summaries/ecoregions_by_biome.csv` (57 rows, the same for the RESOLVE biomes);
`data/summaries/cell_vs_ecoregion.csv` (55,225 rows of H3 resolution 5 cell by ecoregion by
class with the term in both years and its change, 2.75 MB); `analysis\ecoregions\national_class.csv`
(the national medians, the Scale C unit and the national plain change per class);
`analysis\ecoregions\agreement_matrix.csv`.

## Results

### How many fields and ecoregions Scale B scores

Scale B scores 22,625,104 fields for agricultural year 2020 and 24,337,715 for 2024, out of
22,625,394 and 24,338,019 valid fields: 290 and 304 valid fields fall in ecoregion-class groups
under 30 fields and get nothing. The cell design scored 22,620,827 and 24,333,109 at some
resolution, so the ecoregion reference loses fewer fields than the cells do. Both years and the
same class give a Scale B change for 20,113,253 fields, against 20,109,416 fields in the five
Scale A change classes. The 46 ecoregions with a group split into 196 ecoregion-class groups in
2020 and 203 in 2024; 37 ecoregions have at least 1,000 fields valid in both years.

Scale B change classes over the 24,554,482 polygons: stable 16,354,572, decline 1,594,326, large
decline 348,686, gain 1,473,903, large gain 341,766, crop switched 2,400,437, no data 2,040,792
(the no data count holds the 1,645,646 newly cropped fields that have no 2020 class, which Scale
A reports under its own label). Scale A, for the same polygons: stable 15,672,741, decline
1,777,196, large decline 510,660, gain 1,661,737, large gain 487,082. The ecoregion groups are
wider than the cell groups, so the same difference in NDVI-months is fewer SDs, and every tail
class shrinks: large decline by 32 percent, large gain by 30 percent.

### Agreement of Scale A and Scale B at field level

Over the 20,109,313 fields that have one of the five change classes under both scales, the
classes agree exactly for 16,135,689 fields, 80.2 percent, and agree in direction (decline,
stable or gain) for 16,713,968, 83.1 percent. 13,102 fields, 0.07 percent, have opposite
signs. Scale A calls a decline that Scale B does not for 1,019,013 fields; Scale B calls a
decline that Scale A does not for 673,614. Figure 5 has the matrix: 91.4 percent of the fields
Scale A calls stable stay stable, 53.8 percent of the Scale A declines become stable under
Scale B, and 45.6 percent of the Scale A large declines stay large declines while 43.1 percent
soften to decline.

Changing the peers from the cell to the ecoregion therefore changes little about any single
field, and what it changes is mostly the threshold crossing of a wider distribution. The field
is still being judged against the center of a group it belongs to, and that center is still
subtracted.

### Scale C and the plain change per ecoregion

Figure 1 maps the class-weighted Scale C change and figure 2 the class-weighted plain change.
Nationally, the moist broadleaf forest biome (11,046,674 fields valid in both years) moved -0.07
national cell SD against the nation and its fields lost a median 1.2 percent of their
weather-adjusted integral; the dry broadleaf forests biome, which is the Caatinga and its
neighbors (3,983,465 fields), +0.01 SD and -1.8 percent; the grasslands and savannas biome,
which is mostly the Cerrado (5,013,373), +0.02 SD and -0.6 percent; the flooded grasslands
biome, which is the Pantanal (40,057), -0.15 SD and -4.7 percent (`ecoregions_by_biome.csv`).

The national reference per class (`national_class.csv`): pasture, 13,461,858 valid fields in
2020 and 13,754,447 in 2024, has a national median of 2.908 and 2.848 NDVI-months and a plain
change of -2.3 percent over the 12,066,093 fields valid in both years; the Scale C unit for
pasture, the robust SD of the 18,267 and 18,737 cell medians, is 0.643 and 0.607 NDVI-months.
Soybean (1,649,016 fields in both years) changed +0.3 percent, mosaic of uses (3,147,247) -0.2
percent, temporary crop (911,638) +0.6 percent, sugarcane (789,393) +1.1 percent, coffee
(375,953) +2.5 percent and forest plantation (932,048) +2.8 percent. The national picture is
therefore flat for crops and a 2.3 percent loss for pasture, and the frontier ecoregions below
are read against that.

The frontier ecoregions, class weighted, from `ecoregions.csv` (n is fields valid in both years
with the same class; Scale C in national cell SD units; declining is decline plus large decline
as a share of the fields with a change value):

| ecoregion | n | Scale C 2020 | Scale C 2024 | change | plain change | declining A | declining B |
|---|---|---|---|---|---|---|---|
| Madeira-Tapajós moist forests | 840,221 | -0.25 | -0.21 | +0.04 | -2.0% | 9.9% | 8.3% |
| Xingu-Tocantins-Araguaia moist forests | 282,619 | -0.24 | -0.39 | -0.15 | -4.6% | 11.2% | 11.8% |
| Mato Grosso tropical dry forests | 436,447 | +0.07 | +0.14 | +0.07 | +0.0% | 10.3% | 10.6% |
| Tocantins/Pindare moist forests | 407,821 | +0.24 | +0.17 | -0.07 | -2.5% | 12.8% | 9.7% |
| Tapajós-Xingu moist forests | 112,793 | +0.00 | -0.35 | -0.35 | -9.6% | 13.4% | 12.0% |
| Purus-Madeira moist forests | 42,278 | -1.31 | -1.59 | -0.27 | -6.9% | 12.0% | 11.9% |
| Southwest Amazon moist forests | 110,896 | -0.81 | -0.88 | -0.07 | -5.9% | 9.3% | 10.2% |
| Cerrado | 4,160,101 | +0.02 | +0.05 | +0.04 | -0.5% | 9.8% | 8.6% |
| Caatinga | 3,290,887 | +0.46 | +0.47 | +0.02 | -1.5% | 10.8% | 11.5% |
| Alto Paraná Atlantic forests | 3,052,060 | -0.19 | -0.25 | -0.07 | -0.4% | 13.1% | 9.8% |
| Uruguayan savanna | 612,606 | -0.37 | -0.45 | -0.08 | +0.3% | 16.4% | 13.3% |
| Pantanal | 40,030 | -0.31 | -0.46 | -0.15 | -4.7% | 8.7% | 6.4% |

Pasture is the class that defines the Amazon frontier ecoregions, and its rows read the same
way. Tapajós-Xingu pasture (111,998 fields) fell from a median 2.907 to 2.633 NDVI-months,
-9.7 percent, and from 0.00 to -0.35 national cell SD. Purus-Madeira pasture (42,135) sits at
-1.32 SD in 2020 and -1.60 in 2024, -6.9 percent. Southwest Amazon pasture (110,860) sits at
-0.81 and -0.88, -5.9 percent. Xingu-Tocantins-Araguaia pasture (280,213) moved from -0.26 to
-0.41, -4.7 percent. Madeira-Tapajós pasture (827,975) moved from -0.27 to -0.23, -2.1 percent.
Mato Grosso tropical dry forest pasture (383,642), the cleared arc of northern Mato Grosso, is at
the national pasture median in both years (-0.09 and -0.01) and did not move (-0.1 percent).
Cerrado pasture (2,735,712) is -0.26 and -0.19, -1.0 percent; Caatinga pasture (2,613,819) is
+0.43 in both years, -2.4 percent. Soybean inside the frontier ecoregions stands well above the
national soybean median of cells: +1.21 to +1.22 SD in Madeira-Tapajós, +1.35 to +1.31 in Mato
Grosso tropical dry forests, +1.52 to +1.23 in Xingu-Tocantins-Araguaia (1,439 fields), with
plain changes of +3.3, +0.6 and -3.1 percent.

Notable rows outside the frontier: Brazilian Atlantic dry forests -0.24 SD and -5.4 percent, Bahia
interior forests -0.19 SD and -4.2 percent, Campos Rupestres montane savanna -0.27 SD and -3.1
percent, Serra do Mar coastal forests -0.22 SD and -0.2 percent, Chiquitano dry forests +0.19 SD
and +2.5 percent (143,091 fields, the only large ecoregion with a clear gain), Guianan savanna
-0.23 SD and -7.6 percent (19,201 fields, Roraima).

### The cell-within-ecoregion term

`cell_vs_ecoregion.csv` has 55,225 rows of cell by ecoregion by class; 50,843 have a 2020 value,
54,057 a 2024 value and 49,675 both, over 20,508 distinct cells. Figure 3 maps the 19,856 cells
whose change could be class weighted. The change in the term has a median of -0.01 SD and an
interquartile range of -0.30 to +0.27; 23.6 percent of the rows moved more than 0.5 SD against
their ecoregion and 4.7 percent more than 1 SD. The map shows coherent blocks of 50 to 200 km of
one sign across the Caatinga and the Bahia interior, and thinner bands along the Amazon road
network in Pará, Rondônia and Acre. Blocks that size are larger than any management unit and
coincide with the 2024 rainfall pattern, so a good part of the term is weather the regression
left in (the pasture fit has R squared 0.15 in Pará, 0.09 in Mato Grosso and 0.05 in Rondônia,
and Pará pasture cells saw a 2024 precipitation anomaly of -1.06 SD and a temperature anomaly of
+1.35 SD). The term is the right shape for an "area" attribute, but on this fit its change
should be read next to the weather anomaly of the cell, not alone.

### Figures

All under `docs/figures/ecoregions/`, 1,600 pixels wide, under 1 MB each.

1. `fig1_scale_c_change.png`: Brazil's ecoregions colored by the class-weighted change in the
   Scale C score between 2020 and 2024, red below zero and blue above; the Amazon frontier
   ecoregions east of the Tapajós are the largest red areas, and the Purus-Madeira interfluve,
   Pantanal and Serra do Mar are the others.
2. `fig2_plain_change_pct.png`: the same ecoregions colored by the class-weighted median change
   in the weather-adjusted integral as a percent of 2020; the Amazon ecoregions west and south
   of the Madeira lost 4 to 7 percent and Tapajós-Xingu 9.6 percent, while the Cerrado, the
   Atlantic forests and the Uruguayan savanna stayed within 1 percent.
3. `fig3_cell_vs_eco_change.png`: the 19,856 H3 resolution 5 cells with a class-weighted change
   in the cell-within-ecoregion term, with ecoregion outlines; the signal forms regional blocks
   in the northeast and road-shaped bands in the Amazon.
4. `fig4_share_declining_a_vs_b.png`: one point per ecoregion with at least 1,000 fields, the
   share of fields declining under Scale A against the share under Scale B; most points sit
   below the diagonal because the ecoregion distribution is wider, and the largest drops are the
   Atlantic forests and the Uruguayan savanna, where fields are small and the cell groups tight.
5. `fig5_agreement_matrix.png`: the five-by-five matrix of Scale A against Scale B change classes
   over 20,109,313 fields, row shares and counts; 80.2 percent on the diagonal.

## The answer

Does relative productivity work at ecoregion scale? As a field score, yes mechanically and no in
substance. The ecoregion reference scores 99.999 percent of the valid fields, agrees with the
cell reference on 80.2 percent of the change classes and reverses the sign on 0.07 percent. What
it changes is the width of the reference distribution, which shrinks the tails, and what it adds
to each field's score is the climate and soil gradient inside its ecoregion, which is not
management. A pasture in the dry southeast corner of the Cerrado scores low against the Cerrado
whatever its owner does. Scale A is the fairer field score, and Scale B does not make the
regional call either, because the ecoregion median is subtracted from every field in it.

What the ecoregion peers do give is the two terms that the cell design cannot: the cell against
its ecoregion (Scale B's cell term) and the ecoregion against the nation (Scale C). Those are the
terms a "restore the frontier" call needs, and they say this for 2020 to 2024: the pasture of the
eastern and southern Amazon frontier stood at or below the national pasture median in 2020 and
fell further by 2024. Tapajós-Xingu lost 9.7 percent of its weather-adjusted integral and 0.35
national cell SD; Purus-Madeira, Southwest Amazon and Xingu-Tocantins-Araguaia lost 4.7 to 6.9
percent, against a national pasture change of -2.3 percent. The Mato Grosso arc
(Mato Grosso tropical dry forests) and Madeira-Tapajós (Rondônia and southern Amazonas) did not
move. That is a statement about regions, and it is the first one this project can make. Its
weakness is the weather fit: the 2024 drought was strongest exactly where the plain change is
most negative, and the regression removed a small part of it, so the plain change of the eastern
Amazon is an upper bound on the management loss.

Which scale supports a "restore the frontier" call? Only Scale C and the plain change, and only
for a class, since the pasture and the soybean of the same ecoregion move in opposite directions
(Madeira-Tapajós pasture -2.1 percent, soybean +3.3 percent). A call to restore an area smaller
than an ecoregion needs the cell-within-ecoregion term, and on the present fit that term needs
the cell's weather anomaly next to it before anyone acts on it.

Recommended design: keep Scale A as the field term (the field against its neighbors, which is
the management signal and the one the field popup already shows). Add two attributes to every
field from this stage, `cell_vs_eco_2024` and its change, as the area term, and add a region
layer of Scale C and the plain change per ecoregion and class (the rows of `ecoregions.csv`) as
a second summary layer and a second sentence in the popup ("this field's cell stands 0.6 SD
below its ecoregion for pasture; the ecoregion's pasture lost 9.7 percent against the nation").
Do not replace Scale A by Scale B. The two-tier decision rules sketched in WORKLOG.md (area call
first, field call second) map onto exactly these terms.

Ecoregion or climate zone as the reference? The ecoregion is the better unit for the call,
because it names the land system people argue about (the frontier is a set of moist forest
ecoregions, not a Köppen class) and because its boundaries follow soil and vegetation as well as
climate. It is the worse unit for the comparison, because the large ecoregions hold a wide
climate range: the Cerrado spans about 800 to 2,000 mm of annual rainfall and the Caatinga
block shows weather blocks in figure 3. Climate belongs in the weather adjustment, not in the
peer definition. The practical fix is to refit the weather term for this design, per ecoregion
and class instead of per state and class, on the cell medians of both years, and to add the
cell's long-run mean precipitation as a regressor so that the within-ecoregion gradient is
removed as well as the anomaly. A climate zone crossed with the ecoregion (for example three
precipitation bands inside the Cerrado) is a cheaper second choice and would make Scale B fairer,
but it would not change the logic: the regional call still comes from the larger reference.

## Caveats

- MODIS pixel size: 78 percent of fields are under one 250 m pixel (6.25 ha), and 82.9 percent
  of the scored fields are low confidence. The ecoregion-class medians rest on millions of
  fields and are stable; the per-field Scale B values share every weakness of the Scale A
  values.
- Residual climate gradients inside ecoregions: the weather fit was built per state and class
  for the cell design and has a median R squared of 0.15; it removes anomalies, not the mean
  gradient. Inside the Amazon ecoregions, which span several states and a rainfall gradient,
  part of a field's Scale B score and part of the cell term is where the field sits, not how it
  is run.
- Class composition: the class-weighted rows mix classes in each ecoregion's own proportions, so
  an ecoregion of pasture and one of soybean are compared on different classes. The per-class
  rows of `ecoregions.csv` are the ones to compare across ecoregions.
- The 2024 El Niño drought: the 2024 precipitation anomaly over the pasture cells was -1.50 SD in
  Mato Grosso, -1.45 in Acre, -1.22 in Amazonas, -1.06 in Pará and the temperature anomaly +1.3
  to +2.1 SD across the Amazon states; the fit removed a small part of it. The plain change of
  the Amazon frontier is partly the drought.
- Validation: `prod` and `r_adj` correlate below 0.24 with municipal yields in every crop and
  year, and the raw integral tracks soybean and sugarcane only in some years. Nothing here is a
  yield.
- Ecoregion polygons extend past the border; all statistics use Brazilian fields only, and the
  maps clip the polygons to the IBGE biome outline.
- The cell term requires 30 valid fields of a class in a cell inside an ecoregion, so the Amazon
  interior, where cells hold few fields, has no cell term outside the road corridors (figure 3).

## Run times

Measured on 13 November 2026 on the host described in BRIEF.md, with the Sentinel-2 extraction
(pid 36992) running at the same time. Download of the 149 MB zip and unpacking: about 1 minute.
`assign`: 18 seconds for the 27 states (4 seconds to rasterize, 10 to compute the distance
transform, 4 to assign 24.5 million fields). `score`: 124 seconds for both years on the first complete run and 148 on a rerun beside the figure step, including the
two 24.5 million row loads, the weather term, the Scale B and Scale C groupings, the per-state
tables and the three CSVs; peak memory was not measured, the two slim year frames and the merged
frame are about 1.5 GB of float32 and int64 columns. `figures`: about 30 seconds.

## What was verified and what was not

Verified: `metric_adj` reproduces the `s04_relative.py` tables on Acre for both years (maximum
absolute difference 2.4e-7, no validity mismatch); the fid order is identical across the metrics
tables of both years, the relative tables, `fields_scored.parquet` and the new tables, by
assertion in the script; the assignment counts (24,553,822 direct, 657 filled, 3 unassigned) sum
to 24,554,482; the agreement matrix sums to 20,109,313; the five figures were opened and read
after rendering. Not verified: no independent check of the ecoregion assignment against the
polygons themselves (the 0.005 degree raster puts a field within about 550 m of the right side
of a boundary); no check that the IBGE biome outline matches Brazil's legal border; no test of
how the results change with a weather fit refitted per ecoregion, which is the recommended next
step and was not run.
