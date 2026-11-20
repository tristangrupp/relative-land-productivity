/**
 * Every environment-specific value and every attribute name the site reads, in one place.
 *
 * The tiles are PMTiles on S3, read with HTTP range requests. USE_PLACEHOLDER switches the
 * page to the small placeholder set in ./data and shows a banner saying so; it is false for
 * the released product. Nothing else in the app knows where data lives.
 *
 * Attribute names are the contract between the tiles and the page. See DATA_CONTRACT.md.
 */

const TILE_BASE =
	'https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/tiles';

export const CONFIG = {
	USE_PLACEHOLDER: false,

	FIELDS_PMTILES: `${TILE_BASE}/fields.pmtiles`,
	SUMMARY_PMTILES: `${TILE_BASE}/summary.pmtiles`,
	STATS_URL: `${TILE_BASE}/stats.json`,
	/** Ecoregion names and their Scale C change per class (s07_decisions.py lookup), for the
	    ecoregion line of the tooltip and the field card. Served from the site, not S3. */
	ECOREGIONS_URL: './data/ecoregions.json',

	PLACEHOLDER: {
		FIELDS_PMTILES: './data/placeholder_fields.pmtiles',
		SUMMARY_PMTILES: './data/placeholder_summary.pmtiles',
		STATS_URL: './data/placeholder_stats.json',
		/** The Sorriso window the placeholder covers, [[west, south], [east, north]]. */
		BOUNDS: [[-55.87, -12.72], [-55.48, -12.33]]
	},

	/** Layer names inside the PMTiles, as tippecanoe -l wrote them. */
	FIELDS_LAYER: 'fields',
	SUMMARY_LAYER: 'summary',

	/** Below this zoom the map shows the summary cells; from it upward, the fields. Since
	    17 November 2026 the zoom 9 to 11 field tiles keep every polygon (user: no field may be
	    dropped once fields show), so fields start at zoom 9 again. */
	FIELDS_MIN_ZOOM: 9,

	/** The fields archive stops at zoom 13. MapLibre overzooms its zoom 13 tiles up to
	    MAX_ZOOM, so no layer in the style may set a maxzoom at or under 13. */
	FIELDS_MAX_ZOOM: 13,
	MAX_ZOOM: 16,

	/** Free vector basemaps, no key. The fallback is used when the first fails to load. */
	BASEMAP_STYLE: 'https://tiles.openfreemap.org/styles/positron',
	BASEMAP_FALLBACK: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',

	/** Satellite imagery basemap behind the toggle under "Select a state" (user, 17 November
	    2026). Esri World Imagery tiles, no key; when it is on the fields draw at
	    SATELLITE_FIELD_OPACITY so the imagery shows through. */
	SATELLITE_TILES: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
	SATELLITE_ATTRIBUTION: 'Imagery: Esri, Maxar, Earthstar Geographics',
	/* 0.25 at first; 17 November 2026 the user found the fields too faint over the imagery
	   ("make the fields stand out more"), so 0.65 with light outlines. */
	SATELLITE_FIELD_OPACITY: 0.65,
	SATELLITE_LINE: { color: '#ffffff', opacity: 0.85, width: 1 },

	BRAZIL_BOUNDS: [[-74.0, -33.8], [-34.7, 5.3]],

	YEARS: [2020, 2024],
	GITHUB: 'https://github.com/tristangrupp/relative-land-productivity'
};

/** Field attribute names in the fields PMTiles. The key is what app.js uses; the value is
    the property name in the tile. Rename on the right only. vigor_2020 and vigor_2024 are
    in the contract but absent from this release's tiles (pasture vigor is not implemented);
    the page tests presence before it reads them. */
export const ATTR = {
	fid: 'fid',
	area_ha: 'area_ha',
	crop_2020: 'crop_2020',
	crop_2024: 'crop_2024',
	prod_2020: 'prod_2020',
	prod_2024: 'prod_2024',
	change: 'change',
	change_class: 'change_class',
	vigor_2020: 'vigor_2020',
	vigor_2024: 'vigor_2024',
	decision: 'decision',
	decision_computed: 'decision_computed',
	area_decision: 'area_decision',
	area_level: 'area_level',
	source: 'source',
	native_share_1km: 'native_share_1km',
	native_share_250m: 'native_share_250m',
	native_share_1km_large: 'native_share_1km_large',
	largest_patch_ha_1km: 'largest_patch_ha_1km',
	regrowth_share_in: 'regrowth_share_in',
	regrowth_share_1km: 'regrowth_share_1km',
	eco_id: 'eco_id',
	confidence: 'confidence',
	n_obs_2020: 'n_obs_2020',
	n_obs_2024: 'n_obs_2024',
	muni_code: 'muni_code'
};

/** Attribute names in the summary PMTiles (one feature per H3 resolution 6 cell). */
export const SUMMARY_ATTR = {
	h3: 'h3',
	n_fields: 'n_fields',
	area_ha: 'area_ha',
	mean_change: 'mean_change',
	share_decline: 'share_decline',
	share_gain: 'share_gain',
	share_no_data: 'share_no_data',
	mean_prod_2020: 'mean_prod_2020',
	mean_prod_2024: 'mean_prod_2024',
	dominant_crop_2020: 'dominant_crop_2020',
	dominant_crop_2024: 'dominant_crop_2024',
	share_pasture: 'share_pasture',
	mean_vigor_change: 'mean_vigor_change',
	dominant_decision: 'dominant_decision',
	dominant_area_decision: 'dominant_area_decision',
	share_restore: 'share_restore',
	share_improve_yields: 'share_improve_yields',
	share_convert_pasture: 'share_convert_pasture',
	share_converted: 'share_converted',
	share_switch_failed: 'share_switch_failed',
	area_crops_2024: 'area_crops_2024',
	area_pasture_2024: 'area_pasture_2024',
	area_crops_change: 'area_crops_change',
	area_pasture_change: 'area_pasture_change',
	area_mosaic_2024: 'area_mosaic_2024',
	area_mosaic_change: 'area_mosaic_change',
	eco_trend: 'eco_trend',
	eco_crops_2024: 'eco_crops_2024',
	eco_pasture_2024: 'eco_pasture_2024',
	eco_crops_change: 'eco_crops_change',
	eco_pasture_change: 'eco_pasture_change',
	nat_change: 'nat_change',
	nat_pct_change: 'nat_pct_change',
	top_action: 'top_action',
	top_action_share: 'top_action_share',
	top3: 'top3',
	top_area: 'top_area',
	top_area_share: 'top_area_share',
	area_call: 'area_call',
	area_level: 'area_level',
	area_score: 'area_score',
	n_trusted: 'n_trusted',
	share_low_confidence: 'share_low_confidence',
	share_s2: 'share_s2'
};

/** The satellite source of each field (attribute `source`). Mato Grosso switched from MODIS to
    Sentinel-2 on 14 November 2026; the other states follow as their extraction completes. */
export const SOURCES = {
	modis: { label: 'MODIS, 250 m', lowAreaHa: 6.25 },
	s2: { label: 'Sentinel-2, 30 m', lowAreaHa: 0.45 }
};

/** The confidence attribute: 'low' when the field is under 6.25 ha (one MODIS pixel; 0.45 ha,
    five Sentinel-2 pixels, where the source is s2) or fewer than 75 percent of its growing-season
    composites were observed in either year. Since 14 November 2026 a low-confidence field's
    decision is "Low confidence: too small to judge yet".
    The control in the Where card draws low-confidence fields as usual, faded, or not at all. */
export const CONFIDENCE = {
	LOW: 'low',
	HIGH: 'high',
	LOW_AREA_HA: 6.25,
	FADE_FACTOR: 0.3,
	MODES: [
		{ key: 'show', label: 'Draw as usual' },
		{ key: 'fade', label: 'Fade low-confidence fields' },
		{ key: 'hide', label: 'Hide low-confidence fields' }
	],
	DEFAULT: 'show'
};

/** Fill for a feature that has no value for the active view. */
export const NODATA_COLOR = '#ffffff';

/** Fill for a class that is a measured absence rather than a result: no data, no suggestion. */
const GRAY_NEUTRAL = '#c9c4bc';

/* Diverging arms: brown for below peers, green for above, a neutral midpoint. Adjacent
   pairs pass the dataviz validator's CVD separation (worst pair deltaE 13.4). */
const BROWN2 = '#7a2e12';
const BROWN1 = '#d4874a';
const NEUTRAL = '#e8e3da';
const GREEN1 = '#7db77a';
const GREEN2 = '#1e6b3a';

/** change_class values the tiles hold, with legend text and color. The five compared
    classes are set on D, the change in peer standard deviations (SD) of the weather-adjusted
    seasonal greenness between the two years (methods, section 6). An `opacity` on a class
    overrides the fields layer's default fill opacity for that class; the three classes that
    are not a comparison of two years draw at half strength so they recede. */
export const CHANGE_CLASSES = [
	{ key: 'large_decline', label: 'Large decline', color: BROWN2, note: 'fell by more than 2 peer SD' },
	{ key: 'decline', label: 'Decline', color: BROWN1, note: 'fell by 1 to 2 peer SD' },
	{ key: 'stable', label: 'Stable', color: NEUTRAL, note: 'moved less than 1 peer SD either way' },
	{ key: 'gain', label: 'Gain', color: GREEN1, note: 'rose by 1 to 2 peer SD' },
	{ key: 'large_gain', label: 'Large gain', color: GREEN2, note: 'rose by more than 2 peer SD' },
	{ key: 'crop_switched', label: 'Crop switched', color: '#6250d6', opacity: 0.5, note: 'a different crop group in 2024 than in 2020, so the two years are not compared' },
	{ key: 'newly_cropped', label: 'Newly cropped', color: '#2a78d6', opacity: 0.5, note: 'not a crop or pasture class in 2020' },
	{ key: 'abandoned', label: 'Abandoned', color: '#898781', opacity: 0.5, note: 'a 2020 field whose 2024 land cover is not a crop or pasture class; drawn on the 2020 outline' },
	{ key: 'no_data', label: 'No data', color: GRAY_NEUTRAL, note: 'too few clear satellite composites in one of the years to compare' }
];

/** Relative productivity: the field's weather-adjusted seasonal greenness divided by the
    median of its peers (same crop, same region). 1.0 means at the peer median. */
export const PROD_CLASSES = {
	breaks: [0.7, 0.85, 0.95, 1.05, 1.15, 1.3],
	colors: [BROWN2, '#b8552a', '#dfa16c', NEUTRAL, '#9ccf98', '#4f9c5a', GREEN2],
	labels: ['below 0.70', '0.70 to 0.85', '0.85 to 0.95', '0.95 to 1.05 (at peers)',
		'1.05 to 1.15', '1.15 to 1.30', 'above 1.30']
};

/** Change in relative productivity for the summary cells, on the ratio scale (2024 ratio
    minus 2020 ratio, where 1.0 is the peer median). These steps are not the field class
    thresholds, which are in peer standard deviations. Shown in the cell tooltip and card. */
export const CHANGE_STEPS = {
	breaks: [-0.25, -0.08, 0.08, 0.25],
	colors: [BROWN2, BROWN1, NEUTRAL, GREEN1, GREEN2],
	labels: ['mean fell by more than 0.25', 'fell by 0.08 to 0.25', 'within 0.08',
		'rose by 0.08 to 0.25', 'rose by more than 0.25']
};

/** The zoomed-out change map colors each cell by the share of its fields that declined minus
    the share that gained (decline and large decline against gain and large gain), in
    percentage points of the cell's fields. The mean change on the ratio scale sits within
    0.08 of zero in 82 percent of cells, so a map of it is flat; the net share shows where
    decline outnumbers gain. Breaks sit near the 10th, 25th, 75th and 90th percentiles of the
    cells (net share quartiles are at -0.04 and 0.06, deciles at -0.13 and 0.14). Cells where
    decline and gain balance draw at low opacity so the frontiers stand out. */
export const NET_STEPS = {
	breaks: [-0.15, -0.05, 0.05, 0.15],
	/* The balanced color is darker than the fields' NEUTRAL because the summary cells sit on
	   the basemap with no outline at the national zooms, and NEUTRAL matches the land color. */
	colors: [GREEN2, GREEN1, '#bdb7a9', BROWN1, BROWN2],
	labels: ['gaining fields outnumber declining by 15 points or more', 'gaining outnumber declining by 5 to 15 points',
		'balanced, within 5 points', 'declining outnumber gaining by 5 to 15 points',
		'declining fields outnumber gaining by 15 points or more'],
	neutralOpacity: 0.85,
	fullOpacity: 1.0,
	/* a cell with fewer fields than this draws at the neutral opacity, since its share is noisy */
	minFields: 10
};

/** MapBiomas Collection 10 classes, code to name, with the MapBiomas legend colors. Names
    and colors follow the classification:classes list of the MapBiomas Brazil collection on
    source.coop (https://source.coop/tristangruppwri/mapbiomas/, mapbiomas-brazil/collection.json),
    which is the legend the crop_2020 and crop_2024 codes were read from. The legend colors are
    the published MapBiomas ones and are kept as is, so a reader who knows MapBiomas maps reads
    these the same way. They are not CVD-separated. The non-agricultural classes occur in
    crop_2020 (newly cropped fields) and in crop_2024 of abandoned fields. */
export const CROPS = [
	{ key: 39, label: 'Soybean', color: '#f5b3c8' },
	{ key: 19, label: 'Temporary crop', color: '#c27ba0' },
	{ key: 41, label: 'Other temporary crops', color: '#f54ca9' },
	{ key: 20, label: 'Sugar cane', color: '#db7093' },
	{ key: 40, label: 'Rice', color: '#c71585' },
	{ key: 62, label: 'Cotton (beta)', color: '#ff69b4' },
	{ key: 46, label: 'Coffee', color: '#d68fe2' },
	{ key: 47, label: 'Citrus', color: '#9932cc' },
	{ key: 48, label: 'Other perennial crops', color: '#e6ccff' },
	{ key: 36, label: 'Perennial crop', color: '#d082de' },
	{ key: 35, label: 'Palm oil', color: '#9065d0' },
	{ key: 15, label: 'Pasture', color: '#edde8e' },
	{ key: 21, label: 'Mosaic of uses', color: '#ffefc3' },
	{ key: 14, label: 'Farming', color: '#ffefc3' },
	{ key: 9, label: 'Forest plantation', color: '#7a5900' },
	{ key: 18, label: 'Agriculture', color: '#e974ed' },
	{ key: 1, label: 'Forest', color: '#1f8d49' },
	{ key: 3, label: 'Forest formation', color: '#1f8d49' },
	{ key: 4, label: 'Savanna formation', color: '#7dc975' },
	{ key: 5, label: 'Mangrove', color: '#04381d' },
	{ key: 6, label: 'Floodable forest', color: '#007785' },
	{ key: 49, label: 'Wooded sandbank vegetation', color: '#02d659' },
	{ key: 10, label: 'Herbaceous and shrubby vegetation', color: '#d6bc74' },
	{ key: 11, label: 'Wetland', color: '#519799' },
	{ key: 12, label: 'Grassland', color: '#d6bc74' },
	{ key: 32, label: 'Hypersaline tidal flat', color: '#fc8114' },
	{ key: 29, label: 'Rocky outcrop', color: '#ffaa5f' },
	{ key: 50, label: 'Herbaceous sandbank vegetation', color: '#ad5100' },
	{ key: 23, label: 'Beach, dune and sand spot', color: '#ffa07a' },
	{ key: 22, label: 'Non vegetated area', color: '#d4271e' },
	{ key: 24, label: 'Urban area', color: '#d4271e' },
	{ key: 30, label: 'Mining', color: '#9c0027' },
	{ key: 75, label: 'Photovoltaic power plant (beta)', color: '#c12100' },
	{ key: 25, label: 'Other non vegetated areas', color: '#db4d4f' },
	{ key: 26, label: 'Water', color: '#2532e4' },
	{ key: 33, label: 'River, lake and ocean', color: '#2532e4' },
	{ key: 31, label: 'Aquaculture', color: '#091077' },
	{ key: 27, label: 'Not observed', color: '#ffffff' },
	{ key: 0, label: 'Not observed', color: '#ffffff' }
];

/** MapBiomas pasture vigor classes. Not in this release; kept for the next one. */
export const VIGOR = { 1: 'Low', 2: 'Medium', 3: 'High' };

/** vigor_2024 minus vigor_2020, pasture fields only. Not in this release. */
export const VIGOR_CHANGE = [
	{ key: -2, label: 'Fell two classes (high to low)', color: BROWN2 },
	{ key: -1, label: 'Fell one class', color: BROWN1 },
	{ key: 0, label: 'Same class', color: NEUTRAL },
	{ key: 1, label: 'Rose one class', color: GREEN1 },
	{ key: 2, label: 'Rose two classes (low to high)', color: GREEN2 }
];

/** Field decision (methods, section 7): the area call of the field's H3 cell (about 6 km, or 15 km
    where the 6 km cell is too thin) first, the field's own record second. Each class is the
    recommended treatment; `options` lists the other treatments that fit it, shown in the field card
    under the recommendation. The page gives a treatment and options, never a plan for a site.
    A class with `opacity` draws at that value: crop-switched, recently converted and abandoned
    fields draw at half strength. Restore, assisted natural regeneration, restore candidate and
    recently converted land are one green family; adjacent pairs separate by at least deltaE 12
    under simulated protan, deutan and tritan vision (14 November 2026). Possible mis-detection
    (20 November 2026) is a recently converted field whose outline may be a segmentation failure:
    a dark green-gray at full opacity, deltaE 13.8 or more from every other class under the same
    simulations. A class with `showComputed` shows decision_computed in the field card as
    "Computed, not trusted". */
export const DECISIONS = [
	{ key: 'restore', label: 'Restore', color: '#008300',
		note: 'The field lies in an area where crops and pasture are both less green than the same uses across Brazil and both fell further behind since 2020, or it declined in a pasture area that is falling behind Brazil. Restoring the land is the recommended treatment.',
		options: ['Assisted natural regeneration where native vegetation is returning', 'Improve yields if the land stays in production'] },
	{ key: 'assisted_regen', label: 'Assisted natural regeneration', color: '#2e9e82',
		note: 'Below nearby fields of the same crop and declining (or in a restore area), and native vegetation is already returning inside the field: at least 10 percent of its pixels were crop or pasture in 2020 and native vegetation in 2024. Protect and help the regrowth rather than plant.',
		options: ['Active restoration if the regrowth stalls', 'Improve yields on the rest of the field if it stays in production'] },
	{ key: 'restore_candidate', label: 'Restore candidate: next to native vegetation', color: '#285c23',
		note: 'Below nearby fields of the same crop and not gaining, and next to large native vegetation: at least 30 percent of the land within 1 km is native vegetation in patches of 50 ha or more. Restoring would join a larger block of nature.',
		options: ['Improve yields if the land stays in production', 'Assisted natural regeneration if native vegetation starts to return'] },
	{ key: 'converted_below', label: 'Recently converted, below peers', color: '#7cc24e', opacity: 0.5,
		note: 'Native vegetation in 2020, crop or pasture in 2024, and already less green than the same use elsewhere in the ecoregion. The clearing is not paying off, which makes this a strong case for restoring.',
		options: ['Restore or let native vegetation return', 'Improve the new use if it stays'] },
	{ key: 'converted_ok', label: 'Recently converted, at or above peers', color: '#d7f28c', opacity: 0.5,
		note: 'Native vegetation in 2020, crop or pasture in 2024, and at least as green as the same use elsewhere in the ecoregion. The new use produces; the open question is the clearing itself.',
		options: ['Keep the new use and stop further clearing', 'Restore if the clearing broke the law or a commitment'] },
	{ key: 'converted_misdetect', label: 'Possible mis-detection', color: '#364036', showComputed: true,
		note: 'Counted as recently converted, but the outline is 50 ha or more and among the largest 1 percent of fields of its land use in the state, and a quarter or more of the land inside it is still native vegetation in 2024 (MapBiomas). The field model may have drawn one outline around native vegetation, roads and several fields. The computed call is in the field card.',
		options: ['Check the outline against satellite imagery before acting', 'Treat as recently converted land if the clearing is confirmed'] },
	{ key: 'convert_cropland', label: 'Productive pasture on good cropland: conversion to crops possible', color: '#164e63',
		note: 'Inside the Amazon biome, a pasture at least as green as nearby pasture, in an area where crops do as well as across Brazil but pasture lags. Conversion here means crops on this already cleared pasture, not new clearing.',
		options: ['Convert this pasture to crops', 'Intensify the pasture (rotation, reform)', 'Keep as it is'] },
	{ key: 'improve_pasture', label: 'Improve pasture', color: '#67b7d1',
		note: 'Inside the Amazon biome, a pasture less green than nearby pasture, in an area where crops do as well as across Brazil but pasture lags. Recover the pasture before any change of use.',
		options: ['Reform or fertilize the pasture', 'Rotate grazing', 'Restore if the pasture keeps falling behind'] },
	{ key: 'convert_pasture', label: 'Improve or convert pasture', color: '#0e7490',
		note: 'Outside the Amazon biome, a pasture in an area where crops do as well as across Brazil but pasture lags behind. Recover the pasture (reform, fertilize, rotate grazing) or move the land into crops.',
		options: ['Reform or fertilize the pasture', 'Convert to crops', 'Integrated crop and livestock'] },
	{ key: 'switch_paid_off', label: 'Switch paid off', color: '#2a78d6', opacity: 0.5,
		note: 'The crop changed since 2020, and in 2024 the field is at least as green as nearby fields of the new crop. Keep the new crop.',
		options: ['Keep the new crop', 'Intensify the new crop'] },
	{ key: 'switch_failed', label: 'Switch failed', color: '#6250d6', opacity: 0.5,
		note: 'The crop changed since 2020, and in 2024 the field is less green than nearby fields of the new crop. Reconsider the switch or how the new crop is managed.',
		options: ['Return to the former crop', 'Improve how the new crop is managed'] },
	{ key: 'improve_spare', label: 'Improve yields: spares land elsewhere', color: '#eda100',
		note: 'Same crop in both years, below nearby fields of the same crop and not gaining, and little large native vegetation within 1 km. Raising yields here can spare land elsewhere.',
		options: ['Improve management (inputs, sowing date, variety, soil)', 'Switch crop if the area\u2019s crop lags Brazil (see the area call)'] },
	{ key: 'improve_yields', label: 'Improve yields', color: '#f7d58a',
		note: 'Same crop in both years: fell behind nearby fields while at or above them, or below them but gaining. Look first at management: inputs, sowing date, variety, field condition.',
		options: ['Improve management', 'Keep watching the trend'] },
	{ key: 'intensify', label: 'Intensify', color: '#c4b38f',
		note: 'Same crop, about as green as nearby fields of the same crop and not falling behind. The best neighbors show room to produce more.',
		options: ['Intensify toward the best neighbors', 'Keep as it is'] },
	{ key: 'keep', label: 'Keep', color: NEUTRAL,
		note: 'Same crop, greener than nearby fields of the same crop and not falling behind. Nothing to change on this evidence.',
		options: ['Keep as it is'] },
	{ key: 'abandon', label: 'Abandon or change use', color: '#e34948',
		note: 'Below nearby fields in both years, falling further, and close to bare soil in 2024. The land may suit another use or restoration better than the present one.',
		options: ['Restore', 'Another use suited to the land'] },
	{ key: 'abandoned_outline', label: 'Abandoned since 2020', color: '#898781', opacity: 0.5,
		note: 'Cropped or grazed in 2020 and not in 2024; drawn on the 2020 outline. Check whether native vegetation is coming back; if it is not, restore it.',
		options: ['Assisted natural regeneration if native vegetation is coming back', 'Active restoration if it is not'] },
	{ key: 'low_confidence', label: 'Low confidence: too small to judge yet', color: '#cfd8e3', showComputed: true,
		note: 'The field is smaller than the satellite pixel (under 6.25 ha for MODIS, under 0.45 ha for Sentinel-2) or had too few clear images, so its greenness mixes with its neighbors. The computed call is shown in the field card but not trusted. Sentinel-2 at 30 m replaces MODIS state by state.',
		options: ['Wait for the Sentinel-2 update of the state'] },
	{ key: 'none', label: 'No data', color: GRAY_NEUTRAL,
		note: 'Too few clear satellite images in one of the years to compare, or a recently converted field with no 2024 measurement.',
		options: [] }
];

/** Classes that the legend shows as one row (17 November 2026, user: combine the two improve
    yields classes "into just 'improve yields' with a + button that adds the sparing
    distinction to the map when clicked on"). Collapsed, every member draws in `color` and the
    row counts all members; the + button expands the row into its members with their own
    colors, on the map and in the legend. Intensify joined the group the same day (user: "i
    dont understand the difference between intensify and improve yields. fold that in"). */
export const CLASS_GROUPS = [
	{ key: 'improve_yields_all', members: ['improve_spare', 'improve_yields', 'intensify'], label: 'Improve yields', color: '#eda100',
		note: 'Same crop in both years, and the best nearby fields of the same crop produce more: the field is behind them, falling behind, or about level with room to reach the best. Look first at management: inputs, sowing date, variety, field condition. Press + to split it: where higher yields would also spare land elsewhere (little large native vegetation within 1 km), other fields behind or falling behind, and fields about level with their neighbors (intensify).' }
];

/** Area decision per H3 resolution 6 cell (about 6 km across; the 15 km resolution 5 parent where
    the 6 km cell has fewer than 30 fields of any crop or of pasture), from the cell's crops and
    pasture against the same uses across Brazil (methods, section 7). Below means more than
    0.75 national SD of cell medians under the national median; declining means the gap grew
    by more than 0.4 SD between 2020 and 2024. */
export const AREA_DECISIONS = [
	{ key: 'restore_area', label: 'Restore the area', color: '#008300',
		note: 'Crops and pasture here are both less green than the same uses across Brazil, and both fell further behind since 2020. Restore the land across the area rather than fix single fields.' },
	{ key: 'good_land_underused', label: 'Good land underused', color: '#0f8b8d',
		note: 'Crops here do as well as or better than crops across Brazil, but the pasture is weaker than pasture across Brazil. The land can give more: improve the pasture or convert it to crops.' },
	{ key: 'system_misfit', label: 'System misfit', color: '#6250d6',
		note: 'Pasture here does as well as pasture across Brazil, but the crops are weaker than crops across Brazil. The crops may not suit this land; pasture or another use may fit better.' },
	{ key: 'area_declining', label: 'Area declining', color: BROWN1,
		note: 'The uses present are less green than the same uses across Brazil, and at least one fell further behind since 2020. Look for a cause shared across the area. Where pasture is the only use, the declining fields are recommended for restoration.' },
	{ key: 'area_fine', label: 'Area fine', color: '#d6d1c7',
		note: 'No area-wide problem: crops and pasture stand at or above the same uses across Brazil, or below them without falling further. The field call decides.' },
	{ key: 'none', label: 'No area call', color: GRAY_NEUTRAL,
		note: 'Fewer than 30 fields of any crop or of pasture in the area, so it cannot be compared with Brazil.' }
];

/** The ecoregion line of the tooltip: the ecoregion median of the field's crop against the
    national median, change between 2020 and 2024 in national cell SD (Scale C), read as
    losing or gaining ground beyond this threshold. */
export const ECO_TREND = {
	threshold: 0.1,
	labels: { declining: 'losing ground against Brazil', steady: 'steady against Brazil', gaining: 'gaining ground against Brazil' }
};

/** The zoomed-out change map: the national frontier. Each cell is colored on a continuous
    ramp by the class-weighted change of its crops against Brazil (cell_vs_nation 2024 minus
    2020, in national cell SD of each class). The stops sit near the 5th, 25th, 75th and 95th
    percentiles of the resolution 6 cells (-1.03, -0.36, 0.30, 0.92); balanced cells are the
    gray at zero, darker than the basemap so they stay visible. */
export const FRONTIER_RAMP = {
	attr: 'nat_change',
	stops: [[-1.0, BROWN2], [-0.4, BROWN1], [0, '#bdb7a9'], [0.4, GREEN1], [1.0, GREEN2]],
	ticks: ['-1.0', '-0.4', '0', '+0.4', '+1.0'],
	ends: ['lost ground against Brazil', 'gained'],
	fullOpacity: 1.0,
	/* a cell with fewer fields than this draws at this opacity, since its value is noisy */
	fewOpacity: 0.55,
	minFields: 10
};

/** The zoomed-out decision map: a cell takes the color of its top action, the actionable
    decision (any except keep, intensify and no data) most over-represented against its
    national share, among those that cover at least 15 percent of the cell's fields and at
    least 1.5 times their national share (s05_tiles.py writes it as top_action). Other cells
    are the gray of "no action stands out". 15 percent is about twice the national share of
    every actionable decision except improve yields; the 1.5 lift keeps improve yields, 27
    percent of all fields, from painting the map one color (it is the most common action in
    100,538 of 144,909 cells, but stands out in 17,508). */
export const ACTION_SUMMARY = {
	attr: 'top_action', shareAttr: 'top_action_share', minShare: 0.15,
	background: ['keep', 'intensify', 'none', 'abandoned_outline', 'low_confidence'],
	otherLabel: 'No action stands out', otherColor: '#d6d1c7',
	otherNote: 'Mostly keep or intensify, the national mix, or too few fields with a trusted call: no action other than keep or intensify reaches 15 percent of the cell’s trusted fields and 1.5 times its share across Brazil. Low-confidence fields are left out of this count; a cell needs 10 trusted fields.'
};

/** The zoomed-out area map, drawn by the same rule as the decision map: a cell takes the color
    of its most common area call other than area fine and no call when that call covers at
    least 15 percent of the cell's fields, else the background gray. Since 14 November 2026 the
    area call is made per 6 km cell, so each summary cell shows its own call (or its 15 km parent's
    where the 6 km cell is too thin). */
export const AREA_SUMMARY = {
	attr: 'top_area', shareAttr: 'top_area_share', minShare: 0.15,
	background: ['area_fine', 'none'],
	otherLabel: 'Area fine or no call', otherColor: '#d6d1c7',
	otherNote: 'No area problem was found, or the area has too few fields of a crop or of pasture to compare with Brazil.'
};

/** The views in the left nav. attr names a key of ATTR; summary.attr a key of SUMMARY_ATTR.
    The pasture vigor view is left out of this release because the vigor attributes are null;
    see methods, section 9. */
export const VIEWS = [
	{
		bold: true,
		id: 'decision', group: 'Decisions', title: 'Suggested land use pathway',
		question: 'What would be a better land use decision for sustainable food?',
		kind: 'class', attr: 'decision', classes: DECISIONS, countKey: 'decision',
		summary: { kind: 'action', action: ACTION_SUMMARY, classes: DECISIONS, label: 'Possible sustainable land use future' },
		method: 'Each field gets one suggested action. The field card lists other options. The method starts with the area: it suggests restoration where crops and pasture are both below national levels and falling further behind, or for declining fields in a pasture-only area. Where crops do well and pasture lags, it suggests improving pasture or converting existing pasture to crops. In the Amazon biome, conversion is an option only for pasture at least as green as nearby pasture. The method then looks at the field itself. A field below its peers and stable or declining may be a candidate for assisted natural regeneration where native vegetation is returning, or restoration near large native patches. For other fields below their peers and stable or declining, the method suggests raising yields to spare land elsewhere. The map flags small fields as too small to judge. See section 7 of Methods.',
		caveat: ''
	},
	{
		/* hidden from the page for now (user, 17 November 2026: "turn off area decision from the page for now") */
		hidden: true,
		id: 'area_decision', group: 'Decisions', title: 'Area decision',
		question: 'Which land use tradeoff does each area of about 6 km face?',
		kind: 'class', attr: 'area_decision', classes: AREA_DECISIONS, countKey: 'area_decision',
		summary: { kind: 'action', action: AREA_SUMMARY, classes: AREA_DECISIONS, label: 'Area call, 6 km areas' },
		method: 'Each H3 cell of about 6 km (resolution 6) is compared with Brazil as a whole, separately for crops (soybean, other temporary crops, sugarcane, rice, cotton, perennials) and for pasture: the median weather-adjusted greenness of each crop in the cell against its national median, in national SD of cell medians, pooled by field count. Below means more than 0.75 SD under; declining means the gap grew by more than 0.4 SD from 2020 to 2024. A crop needs 30 fields in the cell to count; a 6 km cell where no crop and no pasture reaches 30 fields takes the call of its 15 km parent (the field card says which). The cell card also shows the same terms against the RESOLVE 2017 ecoregion, and the tooltip how the ecoregion moved against Brazil. Mosaic of uses is shown but does not enter the call. Legend counts are the fields in cells with each call.',
		caveat: 'The change of the area term forms blocks of 50 to 200 km, partly weather that the adjustment left in (median R squared 0.15). A refit per ecoregion with mean rainfall did not remove the blocks. Read an area call next to the 2024 drought.'
	},
	{
		id: 'change', group: 'Productivity', title: 'Productivity change 2020 vs 2024',
		question: 'Where did a field gain or lose ground against its peers?',
		kind: 'class', attr: 'change_class', classes: CHANGE_CLASSES, countKey: 'change_class',
		summary: {
			kind: 'ramp', ramp: FRONTIER_RAMP,
			label: 'Change against Brazil, 2020 to 2024 (national SD, all crops)'
		},
		method: 'Zoomed out, each 6 km cell compares changes in its crops with the same crops across Brazil. For each crop, we compare the median adjusted greenness with the national median in standard deviations (SD) of cell medians. We take the difference from 2020 to 2024 and weight crops by field count. The tooltip shows the change in greenness and the difference between the shares of fields that declined and gained. Zoomed in, each field is compared with nearby fields of the same crop. Crop switches, newly cropped fields and abandoned fields have their own classes.',
		caveat: 'A change in greenness is not a measured yield change. The national comparison keeps regional weather the adjustment missed, including the 2024 drought, so part of a frontier may be weather. A crop needs 30 fields in a cell to count; a 6 km cell without one takes the value of its 15 km parent. Mato Grosso uses Sentinel-2 at 30 m, with the field change thresholds scaled by 1.22, the ratio of the two sensors’ year-to-year spread on fields over 25 ha, so the share of changing fields on large fields matches MODIS (22.5 against 22.8 percent). On small fields Sentinel-2 still sees more change than MODIS, which mixes them with their neighbors. Elsewhere 83 percent of fields are smaller than one MODIS pixel.'
	},
	{
		id: 'prod_2020', group: 'Productivity', title: 'Relative productivity 2020',
		question: 'In 2020, which fields were above or below their peers?',
		kind: 'step', attr: 'prod_2020', steps: PROD_CLASSES,
		summary: { kind: 'step', attr: 'mean_prod_2020', steps: PROD_CLASSES, label: 'Mean per cell' },
		method: 'We divide each field’s adjusted greenness by the median for nearby fields of the same crop. A score of 1.0 is the median. The 2020 agricultural year runs from 1 September 2019 to 31 August 2020. We use the 2024 field outlines with the 2020 satellite observations and MapBiomas crop classes.',
		caveat: 'The adjustment accounts for how rainfall and temperature affect each crop across peer groups in the state. It explains little (median R squared 0.15) and misses local events such as hail or flooding.'
	},
	{
		id: 'prod_2024', group: 'Productivity', title: 'Relative productivity 2024',
		question: 'In 2024, which fields were above or below their peers?',
		kind: 'step', attr: 'prod_2024', steps: PROD_CLASSES,
		summary: { kind: 'step', attr: 'mean_prod_2024', steps: PROD_CLASSES, label: 'Mean per cell' },
		method: 'We divide each field’s adjusted greenness by the median for nearby fields of the same crop. The 2024 agricultural year runs from 1 September 2023 to 31 August 2024. We use the 2024 field outlines and Trazo4 crop classes.',
		caveat: 'An El Niño drought affected central and northern Brazil in 2024. Comparing nearby fields reduces the effect of shared weather. An irrigated field can gain relative to neighboring fields because it had more water.'
	},
	{
		id: 'crop_2020', group: 'Land use', title: 'Crop type 2020',
		question: 'What grew on each field in 2020?',
		kind: 'class', attr: 'crop_2020', classes: CROPS, countKey: 'crop_2020',
		summary: { kind: 'class', attr: 'dominant_crop_2020', classes: CROPS, label: 'Most common class per cell' },
		method: 'We use the most common MapBiomas Collection 10 class in each 2024 field outline to show what was there in 2020. Forest, savanna and other nonagricultural classes show where land was newly cropped by 2024.',
		caveat: 'MapBiomas separates soybean, sugarcane, rice, cotton, coffee, citrus, oil palm and a few perennials. Maize, beans and most other annuals fall in the temporary crop classes.'
	},
	{
		id: 'crop_2024', group: 'Land use', title: 'Crop type 2024',
		question: 'What grew on each field in 2024?',
		kind: 'class', attr: 'crop_2024', classes: CROPS, countKey: 'crop_2024',
		summary: { kind: 'class', attr: 'dominant_crop_2024', classes: CROPS, label: 'Most common class per cell' },
		method: 'We use the Trazo4 crop class to group fields for comparison. It matches the most common MapBiomas Collection 10 class inside the 2024 outline for 96.7 to 98.2 percent of fields. On abandoned 2020 outlines, this view shows the 2024 land cover, which is neither crop nor pasture.',
		caveat: 'MapBiomas separates soybean, sugarcane, rice, cotton, coffee, citrus, oil palm and a few perennials. Maize, beans and most other annuals fall in the temporary crop classes.'
	}
];

/** Brazilian states with the bounding box of their 2024 Trazo4 fields, read from the parquet
    row-group statistics of E:\trazo4_master_parquet_seamfix on 2026-11-12. */
export const STATES = [
	{ code: 'AC', name: 'Acre', tier: 1, bbox: [-73.772, -11.147, -66.626, -7.338] },
	{ code: 'AL', name: 'Alagoas', tier: 3, bbox: [-38.226, -10.476, -35.156, -8.813] },
	{ code: 'AP', name: 'Amap\u00e1', tier: 1, bbox: [-53.417, -1.227, -49.893, 4.477] },
	{ code: 'AM', name: 'Amazonas', tier: 1, bbox: [-73.44, -9.821, -56.108, 2.008] },
	{ code: 'BA', name: 'Bahia', tier: 3, bbox: [-46.577, -18.341, -37.374, -8.533] },
	{ code: 'CE', name: 'Cear\u00e1', tier: 3, bbox: [-41.425, -7.86, -37.258, -2.801] },
	{ code: 'DF', name: 'Distrito Federal', tier: 3, bbox: [-48.285, -16.072, -47.313, -15.488] },
	{ code: 'ES', name: 'Esp\u00edrito Santo', tier: 3, bbox: [-41.889, -21.299, -39.666, -17.871] },
	{ code: 'GO', name: 'Goi\u00e1s', tier: 2, bbox: [-53.24, -19.458, -45.908, -12.406] },
	{ code: 'MA', name: 'Maranh\u00e3o', tier: 2, bbox: [-48.752, -10.275, -41.8, -1.161] },
	{ code: 'MT', name: 'Mato Grosso', tier: 1, bbox: [-61.588, -18.081, -50.217, -7.356] },
	{ code: 'MS', name: 'Mato Grosso do Sul', tier: 2, bbox: [-58.134, -24.039, -50.937, -17.176] },
	{ code: 'MG', name: 'Minas Gerais', tier: 3, bbox: [-51.041, -22.926, -39.839, -14.233] },
	{ code: 'PA', name: 'Par\u00e1', tier: 1, bbox: [-58.897, -9.879, -46.091, 1.795] },
	{ code: 'PB', name: 'Para\u00edba', tier: 3, bbox: [-38.767, -8.304, -34.795, -6.061] },
	{ code: 'PR', name: 'Paran\u00e1', tier: 3, bbox: [-54.616, -26.72, -48.026, -22.522] },
	{ code: 'PE', name: 'Pernambuco', tier: 3, bbox: [-41.358, -9.481, -32.382, -3.809] },
	{ code: 'PI', name: 'Piau\u00ed', tier: 3, bbox: [-46.04, -10.927, -40.37, -2.771] },
	{ code: 'RN', name: 'Rio Grande do Norte', tier: 3, bbox: [-38.582, -6.983, -34.969, -4.827] },
	{ code: 'RS', name: 'Rio Grande do Sul', tier: 3, bbox: [-57.596, -33.743, -49.724, -27.084] },
	{ code: 'RJ', name: 'Rio de Janeiro', tier: 3, bbox: [-44.888, -23.344, -40.962, -20.763] },
	{ code: 'RO', name: 'Rond\u00f4nia', tier: 1, bbox: [-66.814, -13.682, -59.781, -7.923] },
	{ code: 'RR', name: 'Roraima', tier: 1, bbox: [-64.645, -1.343, -58.895, 5.167] },
	{ code: 'SC', name: 'Santa Catarina', tier: 3, bbox: [-53.835, -29.325, -48.368, -25.975] },
	{ code: 'SP', name: 'S\u00e3o Paulo', tier: 3, bbox: [-53.09, -25.293, -44.145, -19.793] },
	{ code: 'SE', name: 'Sergipe', tier: 3, bbox: [-38.246, -11.568, -36.413, -9.522] },
	{ code: 'TO', name: 'Tocantins', tier: 2, bbox: [-50.738, -13.438, -45.699, -5.174] }
];

/** The guided walkthrough ("Take the tour" in the left nav; user, 17 November 2026). Each step
    sets a view, a camera and the satellite imagery toggle, and shows a short caption over the
    map. The camera follows the stories of the WRI organizational scorecard: few camera
    chapters, zoom moving one way inside a chapter, a flight time scaled by the distance and the
    zoom change, a held camera ('hold') that does not move, and the view changing while the
    flight lands. `camera` is { center: [lng, lat], zoom }, { bounds: 'brazil' } or 'hold'.
    `state` selects a state in the "Select a state" card without moving the map. Numbers in the
    captions come from methods/METHODS.md, WORKLOG.md and the live stats.json of 17 November 2026. */
export const WALKTHROUGH = {
	/* flight time in ms: FLY_MIN plus 250 per zoom level plus 20 per square root km, capped */
	FLY_MIN: 1600,
	FLY_MAX: 4500,
	/* share of the flight after which the step's view and imagery switch */
	SWITCH_AT: 0.55,
	STEPS: [
		{
			title: 'Land use for more sustainable food production',
			text: 'Compare 24,554,482 crop and pasture fields across Brazil in 2020 and 2024. The map uses greenness relative to nearby fields of the same crop or land use to suggest what to do with each field. Zoom out to see summaries in cells about 6 km across.',
			view: 'decision', camera: { bounds: 'brazil' }, satellite: false, state: ''
		},
		{
			title: 'Fields',
			text: 'The 24,554,482 Trazo4 field outlines cover 190.7 million hectares. Here they sit over satellite imagery near Sorriso, Mato Grosso. Summary cells give way to fields at zoom 9.',
			view: 'crop_2024', camera: { center: [-55.6, -12.62], zoom: 13 }, satellite: true, state: ''
		},
		{
			title: 'Two years and their crops',
			text: 'The 2020 agricultural year ran from 1 September 2019 to 31 August 2020, and 2024 ran from 1 September 2023 to 31 August 2024. For each year, we use the most common MapBiomas Collection 10 class inside each 2024 outline. Use Crop type 2024 to see the later year. Fields that changed crops are marked as crop switched because their peer groups changed.',
			view: 'crop_2020', camera: 'hold', satellite: false, state: ''
		},
		{
			title: 'Productivity relative to neighbors',
			text: 'We add up satellite greenness (NDVI) over the growing season, adjust for rainfall and temperature, then divide by the median for nearby fields of the same crop. A score of 1.0 is the median. Brown marks fields below it and green marks fields above it. A peer group starts with a 17 km H3 cell and needs at least 30 fields of the same crop class.',
			view: 'prod_2024', camera: 'hold', satellite: false, state: ''
		},
		{
			title: 'Productivity change from 2020 to 2024',
			text: 'Zoomed out, brown cells lost ground to the same crops across Brazil and green cells gained. Zoomed in, a change within 1 peer standard deviation is stable. Beyond 1 is a gain or decline, and beyond 2 is a large gain or decline. Some of the differences may reflect weather the model missed, including the 2024 drought.',
			view: 'change', camera: { center: [-52.5, -13.5], zoom: 4 }, satellite: false, state: ''
		},
		{
			title: 'Two satellites',
			text: 'Most states use MODIS at 250 m. Mato Grosso, Pará, Rondônia and Acre use Sentinel-2 at 30 m. Here the Araguaia River separates Pará (left, Sentinel-2) from Tocantins (right, MODIS). Light gray marks fields too small to judge, under 6.25 ha for MODIS or 0.45 ha for Sentinel-2.',
			view: 'decision', camera: { center: [-49.1, -7.3], zoom: 9.4 }, satellite: false, state: ''
		},
		{
			title: 'Native vegetation around and inside fields',
			text: 'Satellite imagery shows native vegetation between fields along the Cuiabá River in Mato Grosso. A field below its peers and stable or declining is a restore candidate if native patches of at least 50 ha cover at least 30 percent of the land within 1 km. If the field is declining and at least 10 percent changed from crop or pasture to native vegetation, the map suggests assisted natural regeneration. These changes come from MapBiomas maps from 2020 and 2024.',
			view: 'decision', camera: { center: [-56.32, -15.3], zoom: 12 }, satellite: true, state: ''
		},
		{
			title: 'The area around each field',
			text: 'In each 6 km cell, we compare crops and pasture with the same uses across Brazil in 2024 and measure how that gap changed since 2020. The green cells near Porto Velho, Rondônia, show where the map suggests restoration because crops and pasture were below national levels and fell further behind. Where crops do well but pasture lags, the map suggests improving the pasture or converting it to crops.',
			view: 'decision', camera: { center: [-64.0, -9.2], zoom: 8 }, satellite: false, state: ''
		},
		{
			title: 'Suggested land use pathways',
			text: 'Each field has one suggested action and other options in its field card. Greens mark restoration and recently converted land. Amber marks Improve yields, which you can expand with + in the legend. Teal and blue mark pasture options, and the bars below Select a state show how common each action is in the selected state, here Mato Grosso.',
			view: 'decision', camera: { bounds: 'brazil' }, satellite: false, state: 'MT'
		}
	]
};
