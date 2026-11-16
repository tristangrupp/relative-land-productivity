# CAR parcels and the Forest Code legal reserve, per field

Status, 16 November 2026: incomplete. Parcel indicators exist for 16 of 27 states (AC AL AP
BA DF MG MT PA PB PE RJ RO RR RS SE SP). The parcels step for the other 11, the fields step
and the summary have not run, so this report has no coverage or deficit numbers yet. The runs
were stopped because they filled the machine's memory (see WORKLOG.md, 16 Nov).

Stage `pipeline/s10_car_forest_code.py`, written 14 November 2026 by the CAR agent. It adds
Forest Code indicators to every 2024 field. It does not change the decision rules, the tiles
or the site. The orchestrator folds the indicators into the recommendations later, following
the proposal in methods/METHODS.md section 7.7.

## What the user decided, in their words

- 14 November 2026: "I think your recommendation with the car parcel data is a good one.
  Again like please document this really well and the decisions behind doing it, and I don't
  want to have a restoration plan done for the particular field site, just a recommendation
  for the field treatment: what should be done, what options are."
- 14 November 2026: "I don't want the forest code policy and the CAR data to be super
  obviously incorporated onto the map. I think this will overcomplicate what it's trying to
  visualize with a bunch of policy context, but do let it inform how the restoration is
  recommended so it's grounded in Brazilian policy. I think we can put it in the
  methodological documentation on the website and in the GitHub, but please don't make the
  legend or the map visualization super extra complicated. If you really want to do that we
  could make a separate toggle to view a different map and show that nuance, but I really
  don't want to see it on the main map layers for the main land use recommendations."
- 14 November 2026, on the CAR source: the preferred dataset is the source.coop cadastral
  catalog, collection brazil-car-area-imovel, instead of the local GeoPackage on E:.
- 14 November 2026, on publication: "I don't know what project you're referring to about how
  certain states should not be public ... We can just publish this to the github pages map, I
  don't care." CAR-derived indicators for every state may feed the published map. The
  property code `cod_imovel` stays out of every published file.

## Why CAR, and why the legal reserve

The map already finds fields that are below their same-crop neighbors and next to large
native vegetation (restore candidates). Such a field could be restored or farmed better. The
Forest Code (Law 12.651/2012) adds a reason to choose restoration: article 12 requires every
rural property to keep a legal reserve of native vegetation, and a property with less native
vegetation than required has to restore, regenerate or compensate the difference. A restore
candidate inside a property that owes legal reserve is a stronger case, because restoring it
helps the owner meet a legal duty, so it is more likely to happen and to find funding.

The Rural Environmental Registry (Cadastro Ambiental Rural, CAR) is the national register of
rural property outlines, declared by the landholders. It is the only national source that
says which property a field belongs to.

The legal reserve was chosen over the riverside protection areas (APP) because it can be
screened from two national layers that exist locally at 30 m (the property outline and the
MapBiomas 2024 map) plus the biome and Legal Amazon limits. APP was not done; see "Riverside
protection" below.

## Inputs

| input | source | local copy |
|---|---|---|
| CAR property outlines | source.coop `tristangruppwri/cadastral`, collection `brazil-car-area-imovel`, file `brazil_car_area_imovel.parquet` (GeoParquet 1.1, EPSG:4326, 8,453,552 rows, 212 row groups, 3,258,574,258 bytes, SICAR snapshot of 16 July 2026, collection updated 2 August 2026). The quarantine sidecar `brazil_car_area_imovel_suspect.parquet` (2 rows with corrupt coordinates, EPSG:4674) is not used, as its README says. | `F:\relative-land-productivity-data\raw\car\` |
| native vegetation | MapBiomas Collection 10 coverage 2024, classes 3, 4, 5, 6, 11, 12, 49, 50 | `F:\relative-land-productivity-data\raw\mapbiomas\brazil_coverage_2024.tif` |
| biomes | IBGE biomes 1:250,000 (`lm_bioma_250.shp`, 2019) | `F:\relative-land-productivity-data\raw\biomes\` (already downloaded on 14 Nov by the decisions round 2 agent; reused read only) |
| Legal Amazon | IBGE Legal Amazon limit 2024 (`Limites_Amazonia_Legal_2024.shp`, geoftp.ibge.gov.br) | `F:\relative-land-productivity-data\raw\legal_amazon\` |
| fields | 2024 polygons, `fields\year=2024\state=<State>\fields.parquet` | |

## Method

1. Split. One pass over the national file writes one parquet per state code under
   `analysis\car\raw\`.
2. Parcels, per state code.
   - Duplicates of `cod_imovel` are dropped, keeping the row with the latest update date
     (`dat_atuali`), so each property counts once.
   - Invalid geometries are repaired with `make_valid`, keeping polygon parts only.
   - Area in hectares from the IBGE Albers equal-area projection for Brazil (SIRGAS 2000 /
     GRS80, standard parallels -2 and -22, center -12, -54), not from DuckDB.
   - Biome and Legal Amazon under the property's interior point (`point_on_surface`).
   - Legal reserve requirement (art. 12): inside the Legal Amazon, 0.80 if the point is in the
     Amazon biome, 0.35 in the Cerrado biome, 0.20 in any other biome (mainly the Pantanal,
     standing in for "campos gerais"); outside the Legal Amazon, 0.20.
   - Native share: MapBiomas 2024 is first reduced to a 90 m grid of 3 by 3 blocks of the
     30 m map (`analysis\car\native_2024_90m.tif`, step `nativemask`; band 1 counts native
     pixels, band 2 pixels with data). The share is the coverage-weighted sum of band 1 over
     the sum of band 2 inside the parcel (exactextract), in spatially sorted chunks of 5,000
     parcels. Repeated consecutive vertices are removed first, because exactextract 0.3 hung
     on them. The 30 m per-class extraction ran out of memory on Mato Grosso on 14 Nov; the
     90 m grid took Mato Grosso's 216,804 parcels in 113 s.
   - Deficit: `lr_deficit_share = lr_required_share - native_share_property` and
     `lr_deficit_ha = lr_deficit_share * area_ha`. Positive means the property has less native
     vegetation than required; negative is a surplus.
   - `small_property`: up to 4 fiscal modules (`mod_fiscal`).
3. Fields, per field state. Every parcel whose bounding box meets the state's fields is
   loaded, from any state, so fields near a state line find parcels registered next door.
   Fields and parcels are projected to the Albers projection and joined by intersection.
   The overlap share is the intersection area over the field area. Parcels covering under 20
   percent of a field are ignored. The field takes the active (AT) or pending (PE) parcel
   with the largest overlap. A field with no AT or PE parcel takes the canceled (CA) or
   suspended (SU) parcel with the largest overlap, but only its status and code: CA and SU
   parcels get no Forest Code indicators. `car_overlap_count` is the number of AT or PE
   parcels that each cover at least 20 percent of the field.
4. Summary per state, nationally and for the seven Amazon frontier ecoregions of
   `s07_decisions.py`, in `data/summaries/car_forest_code_by_state.csv`. Property hectares
   of deficit are summed once per property touched by a field, not per field.

Run: `python pipeline\s10_car_forest_code.py all` (or the steps `split`, `parcels --uf MT`,
`fields --state Mato_Grosso`, `summary`).

## Output columns

`F:\relative-land-productivity-data\analysis\car\state=<State>.parquet`, one row per 2024 field:

| column | meaning |
|---|---|
| fid | field id |
| car_overlap_count | AT or PE parcels covering at least 20 percent of the field (data quality flag; 2 or more means overlapping declarations) |
| car_overlap_share | share of the field covered by the chosen parcel |
| car_cod | `cod_imovel` of the chosen parcel. Local only, never published |
| car_status | AT, PE, CA or SU |
| car_type | IRU rural property, AST agrarian reform settlement, PCT traditional territory |
| car_area_ha | parcel area, Albers equal area |
| car_fiscal_modules | `mod_fiscal` |
| car_biome, car_in_legal_amazon | biome and Legal Amazon under the parcel's interior point |
| lr_required_share | 0.80, 0.35 or 0.20 |
| native_share_property | MapBiomas 2024 native share inside the parcel |
| lr_deficit_ha, lr_deficit_share | positive means less native vegetation than required |
| small_property | up to 4 fiscal modules |

The parcel tables `analysis\car\parcels\<UF>.parquet` hold the same per-property values with
the geometry. Both stay local.

## Privacy and publication

`cod_imovel` identifies a landholder. It stays in the local tables under `analysis\car\` and
never goes into tiles, S3, the repo or the summaries. Only the derived indicators may be
published. On 14 November the CAR agent first held the indicators for Mato Grosso, Maranhão,
Tocantins and Goiás local, because of a local-only rule for those states in another project
(the Restoration Explorer). The user answered the same day that this project can publish them
for every state. Nothing is held from publication now except `cod_imovel`.

## Riverside protection (APP)

Not done. The only national stream maps that could be used locally are IBGE's 1:250,000
drainage (the BC250 GeoPackage, an 874 MB download on a link the Sentinel-2 extraction is
using) and ANA's BHO. At 1:250,000 most first and second order streams are missing, and most
APP lies along those small streams: on three Pará properties in an earlier project, channels
draining 1 km² or more gave 23 to 29 percent of the watercourse APP mapped from a 10 m
elevation model. The real APP width also depends on the river's width (30 m for rivers under
10 m wide, up to 500 m) and, on land cleared before July 2008, on the consolidated-area rules
of art. 61-A (5 to 100 m by property size). A 30 m buffer on 1:250,000 lines would understate
the deficit badly and in a way that differs by region. The CAR theme layer for APP exists in
SICAR but is not in the source.coop catalog.

## Limits

The indicator is a screening estimate, not a legal finding.

- CAR outlines are self-declared, mostly not yet analyzed (most rows are "Aguardando
  analise"), and overlap. Two or more parcels cover the same field for the share given in
  the numbers below.
- The law sets the requirement by the vegetation type of the land (forest, cerrado, general
  fields), not by biome. A forest inside the Cerrado biome in the Legal Amazon legally needs
  80 percent; this screen gives it 35. A property that spans two biomes takes the one under
  its interior point.
- Properties up to 4 fiscal modules on 22 July 2008 keep the native vegetation they had on
  that date as their reserve (art. 67) and owe no restoration for deficits from before that
  date. `small_property` flags them; their deficits should not tip a recommendation.
- Land cleared before 22 July 2008 can be consolidated, reserves can be compensated on
  another property in the same biome (art. 66), APP can count toward the reserve (art. 15),
  and state ecological-economic zoning can lower the Amazon forest requirement to 50 percent
  (art. 12, paragraphs 4 and 5). None of this is modeled.
- Agrarian reform settlements (AST) are registered as one perimeter around many family lots,
  so their area and fiscal modules describe the settlement, not the lot.
- MapBiomas 2024 at 30 m is the native vegetation layer; it counts secondary vegetation as
  native and has its own errors, largest in mosaics of pasture and savanna.
- The parcel is joined by largest overlap; the overlap share is recorded so that a weak
  match can be excluded.
