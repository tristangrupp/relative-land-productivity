# Measuring relative field productivity from Sentinel-2 greenness, 2020 and 2024

Written 2026-11-12 by the methods agent. This is the specification the extract and analyze
agents implement. Every quantity has a formula, its inputs and the public source of each
input. No Earth Engine is used anywhere.

## 1. Inputs

| input | source | resolution | what is read |
|---|---|---|---|
| Sentinel-2 L2A | Planetary Computer STAC, collection `sentinel-2-l2a`, signed with `planetary_computer.sign` | 10 m, read at 30 m through COG overviews with `odc.stac` | bands `B04` (red), `B08` (near infrared), `SCL` (scene classification) |
| field polygons | `E:\trazo4_master_parquet_seamfix`, years 2020 and 2024 | vector | `geom`, `area_ha`, `mbmode` |
| land cover | MapBiomas Collection 10 coverage GeoTIFF for 2020 and 2024, the copies at `s3://wri-datalab-sandbox/trazofields/mapbiomas/brazil_coverage_<YYYY>.tif` (confirm the collection from the file metadata; the MapBiomas public bucket path in the brief answered 403 on 2026-11-12) | 30 m | class per pixel |
| pasture vigor | MapBiomas Collection 10 pasture vigor, per-year GeoTIFF from the MapBiomas platform download (plataforma.brasil.mapbiomas.org, pasture quality theme); no direct public URL was found | 30 m | class per pixel: 1 low, 2 medium, 3 high, as the Pará pipeline reads them; verify with a histogram before use |
| precipitation | CHIRPS v2.0 monthly GeoTIFFs, `https://data.chc.ucsb.edu/products/CHIRPS-2.0/global_monthly/tifs/chirps-v2.0.<YYYY>.<MM>.tif.gz` (the listing answered 429 on 2026-11-12; confirm the names) | 0.05 degree | mm per month |
| temperature | TerraClimate monthly `tmax` and `tmin`, yearly files `https://climate.northwestknowledge.net/TERRACLIMATE-DATA/TerraClimate_<var>_<YYYY>.nc`. The Planetary Computer `terraclimate` collection ends 2021-12 and `era5-pds` ends 2020-12, so neither holds 2024, and the Idaho host did not answer from this machine on 2026-11-12. Fallback: NASA POWER monthly regional `T2M_MAX` and `T2M_MIN`, 0.5 degree, no account needed | 4 km or 0.5 degree | degrees C per month |
| yields for validation | IBGE (the Brazilian statistics institute) SIDRA table 5457, see section 8 | municipality | kg per ha |

## 2. The agricultural year

Agricultural year Y runs from 1 September of Y-1 to 31 August of Y. "2020" is
2019-09-01 to 2020-08-31 and "2024" is 2023-09-01 to 2024-08-31. The agricultural year of
CONAB, the national supply company that publishes the crop calendars, starts on 22 September. Starting on 1 September keeps the September sowing of soybean
in Mato Grosso, Mato Grosso do Sul, Paraná, Santa Catarina and São Paulo inside the window
(CONAB 2022 calendar), and the window still holds the second-season maize harvest, which ends
in August in the main states and spills into September only in Paraná, Mato Grosso do Sul and
Piauí, where the September part is dry-down with near-baseline NDVI. The year also matches
MapBiomas, which labels a temporary crop by the first cycle whose peak falls around January to
February of Y. Field layers: Trazo4 2020 and 2024 delineations; every metric is computed on
the 2024 polygons for both years and on the 2020 polygons for 2020.

## 3. Composites

NDVI per pixel and scene: `NDVI = (B08 - B04) / (B08 + B04)`, with the bands as reflectance
(digital number times 0.0001; the Planetary Computer L2A items already have the 2022
baseline offset removed, check one scene from each year against SCL vegetation pixels).

Mask: drop a pixel when `SCL` is in {0 no data, 1 saturated, 3 cloud shadow, 8 cloud medium
probability, 9 cloud high probability, 10 cirrus, 11 snow}. Keep 2 (dark), 4, 5, 6 and 7
(unclassified), the same set the drought pipeline used. Drop a pixel with `NDVI < -0.2` or
`B08 < 0.01` as residual cloud or shadow. SCL misses thin cirrus and cloud edges; the monthly
maximum below absorbs most of that because contamination lowers NDVI.

Cadence: monthly, 12 composites per agricultural year, each the per-pixel maximum of the
masked NDVI scenes in that calendar month, plus a count band `n_obs` of clear scenes. Monthly
rather than 16-day because Sentinel-2 yields about three valid observations per month over
the Amazon (2020 Brazilian study cited below) and often none in a 16-day wet-season window,
so a 16-day cadence would leave the January to March peak unobserved for a large share of
tier 1 fields. The monthly maximum is the standard way to suppress residual cloud, and the
cadence halves the read volume the probe measured.

Per field f and month m: `NDVI_fm = sum_p w_fp NDVI_pm / sum_p w_fp`, where w_fp is the
exactextract coverage fraction of pixel p in field f, taken over pixels with a valid
composite, and `n_fm = sum_p w_fp n_obs_pm / sum_p w_fp`. A field-month with less than 50
percent of its area valid is missing. Missing months are filled by linear interpolation in
time between the nearest valid months; a missing first or last month takes the nearest valid
value. Quality flag per field and year: `q_fy` = number of valid field-months out of 12 in
the field's calendar window, kept in the output and shown on the map; fields with `q_fy <
50 percent of the window` get no class.

## 4. Per-field metrics

Window: `[s, e]` is the state x class window from `data/calendars/class_window_lookup.csv`,
sowing start to harvest end of the field's crop. The crop is `mbmode` for the 2024 polygon in
2024 and the modal MapBiomas 2020 class inside the 2024 polygon for 2020.

Baseline: `b_f = min(NDVI_fm over the 12 months)`, the bare-soil or dry-season floor of the
field itself. For perennial classes (sugarcane, coffee, citrus, oil palm, other perennial,
pasture) use instead the 5th percentile of NDVI over all fields of that class in the state
and year, because a perennial field has no bare month.

1. Seasonal integral: `iNDVI_fy = sum_{m=s..e} max(NDVI_fm - b_f, 0)`, in NDVI-months.
   This is the headline metric.
2. Peak: `peak_fy = max_{m in [s,e]} NDVI_fm`.
3. Peak timing: `tpeak_fy = argmax month - s`, months after sowing start.
4. Annual integral: `aNDVI_fy = sum over 12 months of max(NDVI_fm - b_f, 0)`, which also
   counts a second crop; the difference `aNDVI - iNDVI` is a double-cropping indicator.
5. Pasture: `iNDVI` over the full year, `peak`, and the modal vigor class.

Why the integral is the headline: it sums green canopy over the season, the quantity that
light-use-efficiency and crop models relate to biomass and yield. Becker-Reshef and
colleagues (2010) forecast winter wheat in Kansas and Ukraine within 7 to 10 percent from
MODIS NDVI near peak. Azzari, Jain and Lobell (2017) found that a peak-only index tracks
year-to-year yield worse than methods that use the whole season and weather. In Brazil, Rizzi
and Rudorff (2007) estimated soybean yield in 322 municipalities of Rio Grande do Sul from
MODIS NDVI, Gusso and colleagues (2013, 2017) reached R² 0.87 to 0.95 for soybean from MODIS
EVI in the same state, an Embrapa model (2026) reached R² 0.72 for municipal soybean yield in
the Midwest from Sentinel-2 indices, Amaro and Luciano (2022) raised sugarcane yield R² from
0.64 to 0.83 by adding Sentinel-2 NDVI, and Picoli and colleagues (2009) forecast São Paulo
sugarcane from MODIS NDVI. For pasture, Ferreira and colleagues (2013) found NDVI tracks green
cover at r = 0.95 in the Cerrado, and MapBiomas builds its vigor classes from normalized NDVI
(ATBD section 8). Peak NDVI saturates on dense canopies (Huete and colleagues 2002; Franch
and colleagues 2017 for yields above 4 t/ha), so the integral, which also counts duration,
ranks fields better; peak and timing are diagnostics.

## 5. Weather correction

Weather moves NDVI without moving the field's standing relative to its neighbors, and it
moves yield too. Two layers remove the part that is common to a neighborhood and the part
that varies within it.

Peer region: H3 resolution 5 cells (average 252.9 km², about 17 km across, computed from the
field centroid with the `h3` package). Cells are nested, near equal area and small enough
that CHIRPS (5 km) and the temperature grid vary little inside one. A peer group is (cell,
class, year) with at least 30 fields; a smaller group falls back to the parent resolution 4
cell (1,770 km²), then resolution 3. Municipalities are not used as peers because their area
ranges from under 100 km² to 159,000 km² (Altamira); they are used only for validation.

Layer 1, peer-relative metric:
`R_fy = (M_fy - median_g(M)) / s_g`, where g is the peer group of f in year y, M is iNDVI (or
peak) and `s_g = 1.4826 * MAD_g(M)`, the robust standard deviation of the group. R is in
peer standard deviations.

Layer 2, regression on weather anomalies. Per class k and state, pool the peer groups of
both years and fit on the group medians:
`median_g(M) = a_ks + b1 P'_gy + b2 T'_gy + b3 P'_gy² + b4 T'_gy² + e_gy`,
where `P'_gy` is the standardized precipitation anomaly of the window,
`P' = (P_gy - mean_2015..2024(P_g)) / sd_2015..2024(P_g)`, with `P_gy` the CHIRPS sum over
the window months at the cell centroid, and `T'_gy` the same for the window mean of
`(tmax + tmin) / 2`. The baseline is 2015 to 2024, ten agricultural years. The field-level
adjusted metric removes the fitted weather term using the field's own grid values:
`M*_fy = M_fy - (b1 P'_fy + b2 T'_fy + b3 P'_fy² + b4 T'_fy²)`, and R is then recomputed
from M*. Layer 1 already cancels weather that is common to a cell, so layer 2 matters for
three things: the regional (cell-level) change map, fields whose peer group is small and
therefore noisy, and within-cell weather gradients. Coefficients and R² per class x state are
written to `data/summaries/weather_fit.csv`.

What the method cannot separate: irrigation (a pivot in a drought year scores a gain that is
water, not management), a shift in sowing date (moves the peak within the window; the
integral is less sensitive than the peak), cultivar or crop-management change, and a crop
switch inside the same MapBiomas class. The map says this in the legend and in the field
popup: "relative greenness, weather-corrected; irrigation, planting date and cultivar are not
separated".

## 6. Change measure and classes

`D_f = R*_f,2024 - R*_f,2020` on the 2024 polygon, in peer standard deviations, where the
2020 class is the MapBiomas 2020 mode inside the 2024 polygon. Classes:

| class | rule |
|---|---|
| large decline | D < -2 |
| decline | -2 ≤ D < -1 |
| stable | -1 ≤ D ≤ 1 |
| gain | 1 < D ≤ 2 |
| large gain | D > 2 |
| crop switched | 2020 class ≠ 2024 class, both agricultural; D is reported but shown with its own color because the peers differ |
| newly cropped | no 2020 field covers more than 50 percent of the 2024 polygon, or the 2020 class is not agricultural |
| abandoned | a 2020 field with no 2024 field covering more than 50 percent of it, or a 2024 class that is not agricultural; shown on the 2020 polygon |
| pasture | vigor class 2024 minus vigor class 2020 (modal class in the polygon): -2, -1, 0, +1, +2, shown with the NDVI class as a second attribute |
| no data | `q_fy` below half the window in either year |

The thresholds are provisional; under no change, D has about one peer standard deviation of
noise, so ±1 marks one-sigma change. The analyze agent reports the share of fields per class
and checks the thresholds against the validation in section 8.

## 7. Decision framing

Level in 2024: below peers (R* < -0.5), at peers, above peers (R* > 0.5). Trend: the class
above. These are screening suggestions from satellite greenness, not agronomic advice; every
suggestion needs a field visit before any decision.

| 2024 level | trend | suggestion | reasoning |
|---|---|---|---|
| below | decline | restore | the field is falling further behind neighbors under the same weather, which points to soil or pasture degradation |
| below | stable | switch crop or improve yields | a persistent gap under the same weather is a site or management limit; try another crop or fix management |
| below | gain | improve yields | the gap is closing; keep the recent change going |
| at | decline | improve yields | the field was average and is slipping; find the cause before it falls behind |
| at | stable | intensify | an average field with headroom to the best neighbors |
| at | gain | intensify | management is working; room remains up to the best neighbors |
| above | decline | improve yields | a top field losing ground; protect what made it good |
| above | stable | maintain | nothing to change on this evidence |
| above | gain | maintain | nothing to change on this evidence |
| below in both years, decline, and 2024 iNDVI under the 20th percentile of the class in the state | abandon or change land use pattern | greenness close to bare soil for two seasons; the land may suit another use |
| crop switched | any | change land use pattern already made; judge the new crop by its 2024 level | the switch is the decision; the 2024 level says whether it paid off |
| newly cropped | none | no suggestion | one year of evidence only |
| abandoned | none | restore or confirm abandonment | a field left cropping; check whether it is regenerating or degrading |
| pasture low vigor in both years | any | restore or change land use pattern | MapBiomas low vigor means low forage and exposed soil through the year |
| pasture vigor down | any | restore | vigor fell by at least one class |
| pasture vigor up | any | maintain or intensify | vigor rose by at least one class |

## 8. Validation

1. Municipal yields. Aggregate the 2020 and 2024 field metrics (iNDVI, M*, and the
   non-relative weather-adjusted metric) to municipality means weighted by `area_ha` for
   soybean (39), maize (classes 19 and 41 in states where maize dominates, see the calendar
   README) and sugarcane (20). Compare with IBGE PAM yields (`Rendimento médio da produção`,
   variable 112, kg/ha) for 2020 and 2024 from
   `https://apisidra.ibge.gov.br/values/t/5457/n6/all/v/112/p/2020,2024/c782/40124,40122,40106?formato=json`
   (40124 soybean, 40122 maize, 40106 sugarcane; `n6/all` returns every municipality;
   verified for one municipality on 2026-11-12). Report Spearman and Pearson correlation of
   the municipal metric with yield per state and year, and of the 2024 minus 2020 differences.
   The expectation from the literature above is r between 0.5 and 0.8 for levels and lower
   for differences.
2. Pasture. Cross-tabulate the field modal vigor class (2020, 2024) against field iNDVI
   terciles within state; the iNDVI should rise monotonically with vigor class. Report the
   agreement and the share of fields where NDVI class and vigor class disagree by two
   classes.
3. Weather fit. Report R² of the layer 2 regressions; a class x state with R² above 0.5
   means weather dominated that season and the field-level residuals are the useful part.

## 9. Limits

- 30 m pixels on a 2 ha median field: about 23 pixels, of which the edge ring is mixed with
  roads, hedges and neighbors. Coverage-fraction weighting reduces but does not remove it;
  fields under 1 ha are flagged `small`.
- Cloud gaps: in the Amazon wet season a month can have zero clear scenes; interpolation
  across two or more missing months inside the window is flagged and the field is shown
  with its `q_fy`.
- Calendar mismatch: irrigated and double-cropped fields grow outside the state window;
  the annual integral is kept so the analyze agent can see them, but the class is computed
  on the calendar window.
- NDVI saturates above leaf area index of about 3, so two good fields of a dense crop can
  look alike at peak; the integral counts duration, which softens this.
- The temporary crop classes 19 and 41 mix crops; a field that changed from maize to beans
  inside class 41 looks like a productivity change.
- Sugarcane harvest date moves the integral: a field cut in April has more regrowth months
  inside the year than one cut in November; peers in the same cell share mill calendars
  only in part.
- Fields are different delineations in 2020 and 2024; the 2020 metric on the 2024 polygon
  can average two 2020 fields.

## 10. References

- Becker-Reshef et al. (2010), winter wheat from MODIS, Remote Sensing of Environment 114.
  https://lcluc.umd.edu/documents/becker-reshef-i-vermote-e-lindeman-m-justice-c-2010-generalized-regression-based-model
- Azzari, Jain, Lobell (2017), fine resolution crop yield maps, Remote Sensing of
  Environment 202. https://fsi.stanford.edu/node/28155
- Lobell (2013), satellite data for yield gap analysis, Field Crops Research 143.
  https://fsi.stanford.edu/node/26982
- Lobell, Azzari (2017), maize yield heterogeneity, Environmental Research Letters 12.
  https://iopscience.iop.org/article/10.1088/1748-9326/aa5371
- Rizzi, Rudorff (2007), soybean yield from MODIS in Rio Grande do Sul, Pesquisa
  Agropecuária Brasileira. https://apct.sede.embrapa.br/pab/article/download/7537/4456/23886
- Gusso et al. (2013), soybean yield from MODIS EVI. https://lume.ufrgs.br/handle/10183/89727
- Gusso et al. (2017), soybean production forecast, Pesquisa Agropecuária Brasileira.
  https://apct.sede.embrapa.br/pab/article/view/22912
- Embrapa (2026), Sentinel-2 and XGBoost municipal soybean yield, Brazilian Midwest.
  https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1184082/1/AP-Integrating-NDVI-2026.pdf
- Amaro, Luciano (2022), sugarcane yield with Sentinel-2 NDVI, Catanduva.
  https://ebrevistas.eb.mil.br/CT/article/download/9497/102265
- Picoli et al. (2009), MODIS NDVI for sugarcane in São Paulo, Bragantia.
  https://www.redalyc.org/pdf/908/90811757028.pdf
- Ferreira et al. (2013), cultivated pastures in the Cerrado, Remote Sensing 5, 307.
  https://www.mdpi.com/2072-4292/5/1/307
- MapBiomas (2026), Pasture Appendix, ATBD Collection 10 v2.
  https://brasil.mapbiomas.org/wp-content/uploads/sites/4/2026/01/Pasture-Appendix-ATBD-Collection-10-V2.pdf
- MapBiomas (2026), Agriculture Appendix, Collection 11 (growing season is peak month ± 3).
  https://brasil.mapbiomas.org/wp-content/uploads/sites/3/2026/08/Agriculture-and-Forest-Plantation-Appendix_C11-REVISADO.pdf
- Huete et al. (2002), MODIS vegetation indices, Remote Sensing of Environment 83.
  https://experts.arizona.edu/en/publications/overview-of-the-radiometric-and-biophysical-performance-of-the-mo/
- Franch et al. (2017), NDVI saturation above 4 t/ha, AGU abstract.
  https://ui.adsabs.harvard.edu/abs/2017AGUFM.B51C1809F
- Sentinel-2 valid observations per month over the Amazon (about three), 2020 Brazilian
  study. https://core.ac.uk/download/490645805.pdf
- CHIRPS and ERA5-Land against Brazilian stations: Pernambuco,
  https://periodicos.ufpe.br/revistas/rbgfe/article/view/264599; SEALBA,
  https://www.mdpi.com/2073-4441/14/9/1473
- H3 cell statistics: https://h3geo.org/docs/core-library/restable/
- CONAB calendars: `data/calendars/README.md`.
