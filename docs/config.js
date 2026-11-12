/**
 * Every environment-specific value and every attribute name the site reads, in one place.
 *
 * The tiles are PMTiles on S3. Until the analysis agent uploads them, USE_PLACEHOLDER keeps
 * the page on the small placeholder set in ./data, and the page shows a banner saying so.
 * To go live: set USE_PLACEHOLDER to false. Nothing else in the app knows where data lives.
 *
 * Attribute names are the contract between the tiles and the page. See DATA_CONTRACT.md.
 */

const TILE_BASE =
	'https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/tiles';

export const CONFIG = {
	USE_PLACEHOLDER: true,

	FIELDS_PMTILES: `${TILE_BASE}/fields.pmtiles`,
	SUMMARY_PMTILES: `${TILE_BASE}/summary.pmtiles`,
	STATS_URL: `${TILE_BASE}/stats.json`,

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

	/** Below this zoom the map shows the summary cells; from it upward, the fields. */
	FIELDS_MIN_ZOOM: 9,

	/** Free vector basemaps, no key. The fallback is used when the first fails to load. */
	BASEMAP_STYLE: 'https://tiles.openfreemap.org/styles/positron',
	BASEMAP_FALLBACK: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',

	BRAZIL_BOUNDS: [[-74.0, -33.8], [-34.7, 5.3]],

	YEARS: [2020, 2024],
	GITHUB: 'https://github.com/tristangrupp/relative-land-productivity'
};

/** Field attribute names in the fields PMTiles. The key is what app.js uses; the value is
    the property name in the tile. Rename on the right only. */
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
	n_obs_2020: 'n_obs_2020',
	n_obs_2024: 'n_obs_2024',
	muni_code: 'muni_code'
};

/** Attribute names in the summary PMTiles (one feature per H3 cell). */
export const SUMMARY_ATTR = {
	h3: 'h3',
	n_fields: 'n_fields',
	area_ha: 'area_ha',
	mean_change: 'mean_change',
	share_decline: 'share_decline',
	share_gain: 'share_gain',
	mean_prod_2020: 'mean_prod_2020',
	mean_prod_2024: 'mean_prod_2024',
	dominant_crop_2020: 'dominant_crop_2020',
	dominant_crop_2024: 'dominant_crop_2024',
	share_pasture: 'share_pasture',
	mean_vigor_change: 'mean_vigor_change',
	dominant_decision: 'dominant_decision'
};

/** Fill for a feature that has no value for the active view. */
export const NODATA_COLOR = '#ffffff';

/* Diverging arms: brown for below peers, green for above, a neutral midpoint. Adjacent
   pairs pass the dataviz validator's CVD separation (worst pair deltaE 13.4). */
const BROWN2 = '#7a2e12';
const BROWN1 = '#d4874a';
const NEUTRAL = '#e8e3da';
const GREEN1 = '#7db77a';
const GREEN2 = '#1e6b3a';

/** change_class values the tiles may hold, with legend text and color. An `opacity` on a
   class overrides the fields layer's default fill opacity for that class; the three classes
   that are not a comparison of two years draw at half strength so they recede. */
export const CHANGE_CLASSES = [
	{ key: 'large_decline', label: 'Large decline', color: BROWN2, note: 'relative productivity fell by more than 0.25' },
	{ key: 'decline', label: 'Decline', color: BROWN1, note: 'fell by 0.08 to 0.25' },
	{ key: 'stable', label: 'Stable', color: NEUTRAL, note: 'moved less than 0.08 either way' },
	{ key: 'gain', label: 'Gain', color: GREEN1, note: 'rose by 0.08 to 0.25' },
	{ key: 'large_gain', label: 'Large gain', color: GREEN2, note: 'rose by more than 0.25' },
	{ key: 'crop_switched', label: 'Crop switched', color: '#6250d6', opacity: 0.5, note: 'a different crop class in 2024 than in 2020, so the two years are not compared' },
	{ key: 'newly_cropped', label: 'Newly cropped', color: '#2a78d6', opacity: 0.5, note: 'not a crop or pasture class in 2020' },
	{ key: 'abandoned', label: 'Abandoned', color: '#898781', opacity: 0.5, note: 'a crop or pasture class in 2020, not in 2024' }
];

/** Relative productivity: the field's weather-adjusted seasonal greenness divided by the
    median of its peers (same crop, same region). 1.0 means at the peer median. */
export const PROD_CLASSES = {
	breaks: [0.7, 0.85, 0.95, 1.05, 1.15, 1.3],
	colors: [BROWN2, '#b8552a', '#dfa16c', NEUTRAL, '#9ccf98', '#4f9c5a', GREEN2],
	labels: ['below 0.70', '0.70 to 0.85', '0.85 to 0.95', '0.95 to 1.05 (at peers)',
		'1.05 to 1.15', '1.15 to 1.30', 'above 1.30']
};

/** Change in relative productivity, for the summary cells. */
export const CHANGE_STEPS = {
	breaks: [-0.25, -0.08, 0.08, 0.25],
	colors: [BROWN2, BROWN1, NEUTRAL, GREEN1, GREEN2],
	labels: ['mean fell by more than 0.25', 'fell by 0.08 to 0.25', 'within 0.08',
		'rose by 0.08 to 0.25', 'rose by more than 0.25']
};

/** MapBiomas Collection 10 classes the site names, with the MapBiomas legend colors. The
    legend colors are the published MapBiomas ones and are kept as is, so a reader who knows
    MapBiomas maps reads these the same way. They are not CVD-separated. */
export const CROPS = [
	{ key: 39, label: 'Soybean', color: '#f5b3c8' },
	{ key: 19, label: 'Temporary crop', color: '#c27ba0' },
	{ key: 41, label: 'Other temporary crop', color: '#f54ca9' },
	{ key: 20, label: 'Sugarcane', color: '#db7093' },
	{ key: 40, label: 'Rice', color: '#c71585' },
	{ key: 62, label: 'Cotton', color: '#ff69b4' },
	{ key: 46, label: 'Coffee', color: '#d68fe2' },
	{ key: 47, label: 'Citrus', color: '#9932cc' },
	{ key: 48, label: 'Other perennial', color: '#e6ccff' },
	{ key: 35, label: 'Oil palm', color: '#9065d0' },
	{ key: 15, label: 'Pasture', color: '#edde8e' },
	{ key: 21, label: 'Mosaic of uses', color: '#ffefc3' },
	{ key: 9, label: 'Forest plantation', color: '#7a5900' },
	{ key: 18, label: 'Agriculture (unspecified)', color: '#e974ed' },
	{ key: 3, label: 'Forest', color: '#1f8d49' },
	{ key: 4, label: 'Savanna', color: '#7dc975' },
	{ key: 12, label: 'Grassland', color: '#d6bc74' },
	{ key: 24, label: 'Urban', color: '#d4271e' },
	{ key: 30, label: 'Mining', color: '#9c0027' },
	{ key: 33, label: 'Water', color: '#2532e4' }
];

/** MapBiomas pasture vigor classes. */
export const VIGOR = { 1: 'Low', 2: 'Medium', 3: 'High' };

/** vigor_2024 minus vigor_2020, pasture fields only. */
export const VIGOR_CHANGE = [
	{ key: -2, label: 'Fell two classes (high to low)', color: BROWN2 },
	{ key: -1, label: 'Fell one class', color: BROWN1 },
	{ key: 0, label: 'Same class', color: NEUTRAL },
	{ key: 1, label: 'Rose one class', color: GREEN1 },
	{ key: 2, label: 'Rose two classes (low to high)', color: GREEN2 }
];

/** Suggested decision. Colors follow the dataviz reference categorical order; "keep" is
    the neutral because it means no change. */
export const DECISIONS = [
	{ key: 'restore', label: 'Restore', color: '#008300', note: 'productivity fell hard and the land shows degradation; restoring cover is the candidate' },
	{ key: 'switch_crop', label: 'Switch crop', color: '#6250d6', note: 'the field trails peers of its crop but the region does well in another crop' },
	{ key: 'change_pattern', label: 'Change land use pattern', color: '#2a78d6', note: 'a decline that fits a rotation or double-cropping change rather than the crop itself' },
	{ key: 'abandon', label: 'Abandon', color: '#e34948', note: 'persistently far below peers in both years' },
	{ key: 'intensify', label: 'Intensify', color: '#eb6834', note: 'stable and below the peer median with room to intensify' },
	{ key: 'improve_yields', label: 'Improve yields', color: '#eda100', note: 'a decline on the same crop, so management rather than land use is the lever' },
	{ key: 'keep', label: 'Keep', color: NEUTRAL, note: 'at or above peers and stable or gaining' }
];

/** The views in the left nav. attr names a key of ATTR; summary.attr a key of SUMMARY_ATTR. */
export const VIEWS = [
	{
		id: 'change', group: 'Productivity', title: 'Productivity change 2020 to 2024',
		question: 'Where did a field gain or lose ground against its peers?',
		kind: 'class', attr: 'change_class', classes: CHANGE_CLASSES, countKey: 'change_class',
		summary: { kind: 'step', attr: 'mean_change', steps: CHANGE_STEPS, label: 'Mean change per cell' },
		method: 'Relative productivity is the field\u2019s seasonal greenness (NDVI integrated over the CONAB growing season, corrected for rainfall and temperature) divided by the median of fields with the same crop in the same region. The change is the 2024 value minus the 2020 value, both measured on the 2024 field outline. Fields whose MapBiomas crop class differs between the years are shown as switched, newly cropped or abandoned rather than compared.',
		caveat: 'A change in greenness relative to peers is not a measured yield change. Fields with few clear satellite looks in either year are the least certain.'
	},
	{
		id: 'prod_2020', group: 'Productivity', title: 'Relative productivity 2020',
		question: 'In 2020, which fields were above or below their peers?',
		kind: 'step', attr: 'prod_2020', steps: PROD_CLASSES,
		summary: { kind: 'step', attr: 'mean_prod_2020', steps: PROD_CLASSES, label: 'Mean per cell' },
		method: 'The field\u2019s weather-adjusted seasonal greenness divided by the median of the same crop in the same region for the 2020 agricultural year. 1.0 is the peer median. Values are computed on both the 2020 and the 2024 outlines; this map draws the 2024 outlines.',
		caveat: 'The weather adjustment removes the part of greenness that rainfall and temperature explain across all fields of the crop. It cannot remove field-level weather such as hail or local flooding.'
	},
	{
		id: 'prod_2024', group: 'Productivity', title: 'Relative productivity 2024',
		question: 'In 2024, which fields were above or below their peers?',
		kind: 'step', attr: 'prod_2024', steps: PROD_CLASSES,
		summary: { kind: 'step', attr: 'mean_prod_2024', steps: PROD_CLASSES, label: 'Mean per cell' },
		method: 'As for 2020, for the 2024 agricultural year, on the 2024 outlines.',
		caveat: 'The weather adjustment removes the part of greenness that rainfall and temperature explain across all fields of the crop. It cannot remove field-level weather such as hail or local flooding.'
	},
	{
		id: 'crop_2020', group: 'Land use', title: 'Crop type 2020',
		question: 'What grew on each field in 2020?',
		kind: 'class', attr: 'crop_2020', classes: CROPS, countKey: 'crop_2020',
		summary: { kind: 'class', attr: 'dominant_crop_2020', classes: CROPS, label: 'Most common class per cell' },
		method: 'The modal MapBiomas Collection 10 class inside the field outline for 2020. For the 2024 outlines this comes from the 2020 coverage raster, so a crop switch is visible per field.',
		caveat: 'MapBiomas separates soybean, sugarcane, rice, cotton, coffee, citrus, oil palm and a few perennials. Maize, beans and most other annuals fall in the temporary crop classes.'
	},
	{
		id: 'crop_2024', group: 'Land use', title: 'Crop type 2024',
		question: 'What grew on each field in 2024?',
		kind: 'class', attr: 'crop_2024', classes: CROPS, countKey: 'crop_2024',
		summary: { kind: 'class', attr: 'dominant_crop_2024', classes: CROPS, label: 'Most common class per cell' },
		method: 'The modal MapBiomas Collection 10 class inside the 2024 field outline for 2024.',
		caveat: 'MapBiomas separates soybean, sugarcane, rice, cotton, coffee, citrus, oil palm and a few perennials. Maize, beans and most other annuals fall in the temporary crop classes.'
	},
	{
		id: 'vigor', group: 'Land use', title: 'Pasture vigor change',
		question: 'On pasture, did vigor rise or fall between 2020 and 2024?',
		kind: 'vigor',
		summary: { kind: 'step', attr: 'mean_vigor_change', steps: {
			breaks: [-1, -0.25, 0.25, 1], colors: CHANGE_STEPS.colors,
			labels: ['mean fell by more than one class', 'fell', 'about the same', 'rose', 'rose by more than one class']
		}, label: 'Mean class change per cell, pasture fields' },
		method: 'MapBiomas Collection 10 pasture vigor classifies each pasture pixel as low, medium or high vigor, already normalized by biome. The field value is the modal class inside the outline. This view shows the 2024 class minus the 2020 class.',
		caveat: 'Only fields whose class is pasture in both years get a value. The vigor product is itself a greenness-based classification, so it shares the weather sensitivity of the productivity measure.'
	},
	{
		id: 'decision', group: 'Decision', title: 'Suggested decision',
		question: 'Which land use decision does the evidence point to on each field?',
		kind: 'class', attr: 'decision', classes: DECISIONS, countKey: 'decision',
		summary: { kind: 'class', attr: 'dominant_decision', classes: DECISIONS, label: 'Most common suggestion per cell' },
		method: 'A rule set over the change class, the 2020 and 2024 relative productivity, the crop types and the pasture vigor change. The rules are written in methods/METHODS.md and the thresholds are stated there.',
		caveat: 'These are screening results from satellite greenness. They are not agronomic advice, they do not know prices, soils, tenure or the farmer\u2019s plans, and a field flagged here deserves a visit before any decision.'
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
