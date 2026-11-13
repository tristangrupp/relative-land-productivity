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

	/** The fields archive stops at zoom 13. MapLibre overzooms its zoom 13 tiles up to
	    MAX_ZOOM, so no layer in the style may set a maxzoom at or under 13. */
	FIELDS_MAX_ZOOM: 13,
	MAX_ZOOM: 16,

	/** Free vector basemaps, no key. The fallback is used when the first fails to load. */
	BASEMAP_STYLE: 'https://tiles.openfreemap.org/styles/positron',
	BASEMAP_FALLBACK: 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json',

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
	dominant_decision: 'dominant_decision'
};

/** The confidence attribute: 'low' when the field is under 6.25 ha (one MODIS pixel) or
    fewer than 75 percent of its growing-season composites were observed in either year.
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
	colors: [GREEN2, GREEN1, NEUTRAL, BROWN1, BROWN2],
	labels: ['gaining fields outnumber declining by 15 points or more', 'gaining outnumber declining by 5 to 15 points',
		'balanced, within 5 points', 'declining outnumber gaining by 5 to 15 points',
		'declining fields outnumber gaining by 15 points or more'],
	neutralOpacity: 0.42,
	fullOpacity: 0.9,
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

/** Suggested decision, from the methods section 7 table as the analyze stage applied it.
    Colors follow the dataviz reference categorical order; "keep" is the neutral because it
    means no change, and "none" is gray because no suggestion is made. */
export const DECISIONS = [
	{ key: 'restore', label: 'Restore', color: '#008300', note: 'below peers in 2024 and declining: the field falls further behind neighbors under the same weather' },
	{ key: 'switch_crop', label: 'Switch crop', color: '#6250d6', note: 'below peers in 2024 and stable: a persistent gap under the same weather is a site or management limit' },
	{ key: 'change_pattern', label: 'Change land use pattern', color: '#2a78d6', note: 'the crop group changed between the years; the 2024 level says whether the switch paid off' },
	{ key: 'abandon', label: 'Abandon', color: '#e34948', note: 'below peers in both years, declining, and 2024 greenness in the lowest fifth of the crop in the state' },
	{ key: 'intensify', label: 'Intensify', color: '#eb6834', note: 'at peers and stable or gaining: an average field with headroom to the best neighbors' },
	{ key: 'improve_yields', label: 'Improve yields', color: '#eda100', note: 'closing a gap from below, or slipping from at or above peers: management on the same crop is the lever' },
	{ key: 'keep', label: 'Keep', color: NEUTRAL, note: 'above peers and stable or gaining' },
	{ key: 'none', label: 'No suggestion', color: GRAY_NEUTRAL, note: 'newly cropped or no data: one year of evidence or none' }
];

/** The views in the left nav. attr names a key of ATTR; summary.attr a key of SUMMARY_ATTR.
    The pasture vigor view is left out of this release because the vigor attributes are null;
    see methods, section 9. */
export const VIEWS = [
	{
		id: 'change', group: 'Productivity', title: 'Productivity change 2020 vs 2024',
		question: 'Where did a field gain or lose ground against its peers?',
		kind: 'class', attr: 'change_class', classes: CHANGE_CLASSES, countKey: 'change_class',
		summary: {
			kind: 'net', minuend: 'share_decline', subtrahend: 'share_gain', steps: NET_STEPS,
			label: 'Fields that declined minus fields that gained, share of each cell'
		},
		method: 'Relative productivity is the field\u2019s seasonal greenness (MODIS NDVI integrated over the CONAB growing season, corrected for rainfall and temperature) divided by the median of fields with the same crop in the same region. The class is set on the change in peer standard deviations between the 2024 and the 2020 agricultural year, both measured on the 2024 field outline; the number in the tooltip is the change on the ratio scale, where 1.0 is the peer median. Fields whose crop group differs between the years are shown as switched, newly cropped or abandoned rather than compared.',
		caveat: 'A change in greenness relative to peers is not a measured yield change. 83 percent of fields are smaller than one MODIS pixel and are marked low confidence.'
	},
	{
		id: 'prod_2020', group: 'Productivity', title: 'Relative productivity 2020',
		question: 'In 2020, which fields were above or below their peers?',
		kind: 'step', attr: 'prod_2020', steps: PROD_CLASSES,
		summary: { kind: 'step', attr: 'mean_prod_2020', steps: PROD_CLASSES, label: 'Mean per cell' },
		method: 'The field\u2019s weather-adjusted seasonal greenness divided by the median of the same crop in the same region for the 2020 agricultural year (1 September 2019 to 31 August 2020). 1.0 is the peer median. The value is computed on the 2024 outlines from the 2020 satellite record, with the crop taken from the MapBiomas 2020 map.',
		caveat: 'The weather adjustment removes the part of greenness that rainfall and temperature explain across the peer groups of the crop in the state. It explains little (median R squared 0.15) and cannot remove field-level weather such as hail or local flooding.'
	},
	{
		id: 'prod_2024', group: 'Productivity', title: 'Relative productivity 2024',
		question: 'In 2024, which fields were above or below their peers?',
		kind: 'step', attr: 'prod_2024', steps: PROD_CLASSES,
		summary: { kind: 'step', attr: 'mean_prod_2024', steps: PROD_CLASSES, label: 'Mean per cell' },
		method: 'As for 2020, for the 2024 agricultural year (1 September 2023 to 31 August 2024), on the 2024 outlines with the Trazo4 crop class.',
		caveat: 'The 2024 agricultural year was the El Ni\u00f1o drought year in the center and north of Brazil. The peer-relative measure cancels weather that is common to a region, but a field with irrigation scores a gain that is water, not management.'
	},
	{
		id: 'crop_2020', group: 'Land use', title: 'Crop type 2020',
		question: 'What grew on each field in 2020?',
		kind: 'class', attr: 'crop_2020', classes: CROPS, countKey: 'crop_2020',
		summary: { kind: 'class', attr: 'dominant_crop_2020', classes: CROPS, label: 'Most common class per cell' },
		method: 'The modal MapBiomas Collection 10 class inside the 2024 field outline on the 2020 coverage map, so a crop switch is visible per field. Forest, savanna and other non-agricultural classes appear here: those fields were newly cropped by 2024.',
		caveat: 'MapBiomas separates soybean, sugarcane, rice, cotton, coffee, citrus, oil palm and a few perennials. Maize, beans and most other annuals fall in the temporary crop classes.'
	},
	{
		id: 'crop_2024', group: 'Land use', title: 'Crop type 2024',
		question: 'What grew on each field in 2024?',
		kind: 'class', attr: 'crop_2024', classes: CROPS, countKey: 'crop_2024',
		summary: { kind: 'class', attr: 'dominant_crop_2024', classes: CROPS, label: 'Most common class per cell' },
		method: 'The Trazo4 modal MapBiomas Collection 10 class of the 2024 field, the class its peer group was formed on. It agrees with the MapBiomas 2024 mode inside the outline on 96.7 to 98.2 percent of fields. On abandoned 2020 outlines this is the 2024 land cover, which is not a crop or pasture class.',
		caveat: 'MapBiomas separates soybean, sugarcane, rice, cotton, coffee, citrus, oil palm and a few perennials. Maize, beans and most other annuals fall in the temporary crop classes.'
	},
	{
		id: 'decision', group: 'Decision', title: 'Suggested decision',
		question: 'Which land use decision does the evidence point to on each field?',
		kind: 'class', attr: 'decision', classes: DECISIONS, countKey: 'decision',
		summary: { kind: 'class', attr: 'dominant_decision', classes: DECISIONS, label: 'Most common suggestion per cell' },
		method: 'A rule set over the change class and the 2024 level against peers (below, at, above), written in methods, section 7. Newly cropped fields and fields without data get no suggestion.',
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
