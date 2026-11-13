/**
 * Relative land productivity, Brazil 2020 to 2024: the map page.
 *
 * One MapLibre map with two PMTiles sources, read from S3 with HTTP range requests. Below
 * FIELDS_MIN_ZOOM the summary cells (H3) are drawn; from it upward, the fields. The fields
 * archive stops at zoom 13 and MapLibre overzooms it from there. Each view in the left nav
 * sets one fill expression on both layers and one legend. Clicking a field opens the field
 * card with its attributes and a 2020 against 2024 bar. The Where card loads stats.json for
 * the national and per-state counts and holds the low-confidence control.
 *
 * All attribute names come from config.js (ATTR, SUMMARY_ATTR). Nothing here names a tile
 * property directly.
 */

import {
	CONFIG, ATTR, SUMMARY_ATTR, VIEWS, CROPS, VIGOR, VIGOR_CHANGE, DECISIONS,
	CHANGE_CLASSES, STATES, NODATA_COLOR, CONFIDENCE
} from './config.js';

const $ = (id) => document.getElementById(id);
const NA = 'n/a';
const fmt = (n, d = 2) => (n == null || !isFinite(n) ? NA : Number(n).toFixed(d));
const fmtInt = (n) => (n == null ? NA : Number(n).toLocaleString('en-US'));
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const SRC = CONFIG.USE_PLACEHOLDER ? CONFIG.PLACEHOLDER : CONFIG;
const PLACEHOLDER = CONFIG.USE_PLACEHOLDER || /placeholder/i.test(SRC.FIELDS_PMTILES);

const state = {
	view: VIEWS[0],
	stateCode: '',
	confMode: CONFIDENCE.DEFAULT,
	stats: null,
	picked: null,
	mapReady: false,
	summaryVisible: true
};

const cropByKey = Object.fromEntries(CROPS.map((c) => [c.key, c]));
const decisionByKey = Object.fromEntries(DECISIONS.map((d) => [d.key, d]));
const changeByKey = Object.fromEntries(CHANGE_CLASSES.map((d) => [d.key, d]));

/* ------------------------------------------------------------------ log */

function log(title, meta, cls) {
	const el = document.createElement('div');
	el.className = 'row' + (cls ? ' ' + cls : '');
	el.innerHTML = `<b>${esc(title)}</b>${meta ? `<div class="meta">${esc(meta)}</div>` : ''}`;
	$('log').prepend(el);
	while ($('log').children.length > 3) $('log').lastElementChild.remove();
	setTimeout(() => el.remove(), 9000);
}

/* ------------------------------------------------------------------ fill expressions */

function classFill(attrName, classes) {
	const m = ['match', ['get', attrName]];
	for (const c of classes) m.push(c.key, c.color);
	m.push(NODATA_COLOR);
	return ['case', ['has', attrName], m, NODATA_COLOR];
}

const FIELD_OPACITY = 0.82;

/** Per-class fill opacity: a class with its own `opacity` draws at that value, every other
    feature at FIELD_OPACITY. */
function classOpacity(view) {
	if (view.kind !== 'class' || !view.classes.some((c) => c.opacity != null)) return FIELD_OPACITY;
	const attrName = ATTR[view.attr];
	const m = ['match', ['get', attrName]];
	for (const c of view.classes) if (c.opacity != null) m.push(c.key, c.opacity);
	m.push(FIELD_OPACITY);
	return ['case', ['has', attrName], m, FIELD_OPACITY];
}

/** The class opacity, scaled down for low-confidence fields when the control says fade. */
function fieldOpacity(view) {
	const base = classOpacity(view);
	if (state.confMode !== 'fade') return base;
	const low = ['==', ['get', ATTR.confidence], CONFIDENCE.LOW];
	return ['*', base, ['case', low, CONFIDENCE.FADE_FACTOR, 1]];
}

/** Filter for the fields layers: everything, or only fields that are not low confidence. */
function fieldFilter() {
	if (state.confMode !== 'hide') return null;
	return ['!=', ['get', ATTR.confidence], CONFIDENCE.LOW];
}

function stepFill(attrName, steps) {
	return stepFillExpr(['get', attrName], ['has', attrName], steps);
}

/** A stepped fill over any numeric expression; `hasExpr` says when the value exists. */
function stepFillExpr(valueExpr, hasExpr, steps) {
	const s = ['step', valueExpr, steps.colors[0]];
	steps.breaks.forEach((b, i) => s.push(b, steps.colors[i + 1]));
	return ['case', hasExpr, s, NODATA_COLOR];
}

/** The net share of a summary cell: one share attribute minus another, for example the
    share of fields that declined minus the share that gained. */
function netExpr(s) {
	return ['-', ['get', SUMMARY_ATTR[s.minuend]], ['get', SUMMARY_ATTR[s.subtrahend]]];
}
function netHasExpr(s) {
	return ['all', ['has', SUMMARY_ATTR[s.minuend]], ['has', SUMMARY_ATTR[s.subtrahend]]];
}

const SUMMARY_OPACITY = 0.78;

/** Cell opacity. A net view fades the cells where the two shares balance, and the cells with
    too few fields for a share to mean much, so the cells where one side dominates stand out. */
function summaryOpacity(view) {
	const s = view.summary;
	if (s.kind !== 'net') return SUMMARY_OPACITY;
	const st = s.steps;
	const neutralLo = st.breaks[Math.floor(st.breaks.length / 2) - 1];
	const neutralHi = st.breaks[Math.floor(st.breaks.length / 2)];
	const net = netExpr(s);
	const balanced = ['all', ['>=', net, neutralLo], ['<', net, neutralHi]];
	const few = ['<', ['coalesce', ['get', SUMMARY_ATTR.n_fields], 0], st.minFields];
	return ['case', netHasExpr(s), ['case', ['any', balanced, few], st.neutralOpacity, st.fullOpacity], st.neutralOpacity];
}

function vigorFill() {
	const a = ATTR.vigor_2020;
	const b = ATTR.vigor_2024;
	const m = ['match', ['-', ['get', b], ['get', a]]];
	for (const c of VIGOR_CHANGE) m.push(c.key, c.color);
	m.push(NODATA_COLOR);
	return ['case', ['all', ['has', a], ['has', b]], m, NODATA_COLOR];
}

/** Classes with `derivedFrom` are not values of the view's attribute; they are read from
    another attribute and drawn ahead of the attribute's own match. */
function derivedFill(view, base) {
	let expr = base;
	for (const c of view.classes || []) {
		if (!c.derivedFrom) continue;
		expr = ['case', ['==', ['get', ATTR[c.derivedFrom.attr]], c.derivedFrom.value], c.color, expr];
	}
	return expr;
}

function derivedKey(view, p) {
	for (const c of view.classes || []) {
		if (c.derivedFrom && p[ATTR[c.derivedFrom.attr]] === c.derivedFrom.value) return c.key;
	}
	return null;
}

function fieldFill(view) {
	if (view.kind === 'vigor') return vigorFill();
	if (view.kind === 'class') return derivedFill(view, classFill(ATTR[view.attr], view.classes));
	return stepFill(ATTR[view.attr], view.steps);
}

function summaryFill(view) {
	const s = view.summary;
	if (s.kind === 'class') return classFill(SUMMARY_ATTR[s.attr], s.classes);
	if (s.kind === 'net') return stepFillExpr(netExpr(s), netHasExpr(s), s.steps);
	return stepFill(SUMMARY_ATTR[s.attr], s.steps);
}

/* ------------------------------------------------------------------ map */

let map = null;

async function loadStyle() {
	try {
		const r = await fetch(CONFIG.BASEMAP_STYLE);
		if (r.ok) return await r.json();
	} catch (e) { /* fall through */ }
	log('Primary basemap unavailable', 'Using the Carto fallback style', 'err');
	return CONFIG.BASEMAP_FALLBACK;
}

async function initMap() {
	const protocol = new pmtiles.Protocol();
	maplibregl.addProtocol('pmtiles', protocol.tile);
	const style = await loadStyle();
	map = new maplibregl.Map({
		container: 'map',
		style,
		bounds: CONFIG.BRAZIL_BOUNDS,
		fitBoundsOptions: { padding: 20 },
		maxZoom: CONFIG.MAX_ZOOM,
		hash: 'map',
		attributionControl: { compact: true }
	});
	map.addControl(new maplibregl.NavigationControl({ visualizePitch: false }), 'bottom-right');
	map.addControl(new maplibregl.ScaleControl({ maxWidth: 110, unit: 'metric' }), 'bottom-left');

	map.on('load', () => {
		const firstSymbol = (map.getStyle().layers || []).find((l) => l.type === 'symbol');
		const before = firstSymbol ? firstSymbol.id : undefined;

		map.addSource('summary', {
			type: 'vector', url: 'pmtiles://' + absolute(SRC.SUMMARY_PMTILES),
			attribution: 'Trazo4 fields (WRI), MapBiomas Collection 10, MODIS MOD13Q1'
		});
		/* The PMTiles header gives minzoom 9 and maxzoom 13; MapLibre overzooms the zoom 13
		   tiles for every zoom above that, because no layer below sets a maxzoom. */
		map.addSource('fields', { type: 'vector', url: 'pmtiles://' + absolute(SRC.FIELDS_PMTILES) });

		map.addLayer({
			id: 'summary-fill', type: 'fill', source: 'summary', 'source-layer': CONFIG.SUMMARY_LAYER,
			maxzoom: CONFIG.FIELDS_MIN_ZOOM,
			paint: { 'fill-color': summaryFill(state.view), 'fill-opacity': summaryOpacity(state.view) }
		}, before);
		/* The cell outlines appear only when zoomed in enough for a cell to be more than a few
		   pixels wide; at the national zooms the hex grid would hide the color pattern. */
		map.addLayer({
			id: 'summary-line', type: 'line', source: 'summary', 'source-layer': CONFIG.SUMMARY_LAYER,
			maxzoom: CONFIG.FIELDS_MIN_ZOOM,
			paint: {
				'line-color': '#2c2a28',
				'line-opacity': ['interpolate', ['linear'], ['zoom'], 5, 0, 7, 0.1, 9, 0.25],
				'line-width': 0.5
			}
		}, before);
		map.addLayer({
			id: 'fields-fill', type: 'fill', source: 'fields', 'source-layer': CONFIG.FIELDS_LAYER,
			minzoom: CONFIG.FIELDS_MIN_ZOOM,
			paint: { 'fill-color': fieldFill(state.view), 'fill-opacity': fieldOpacity(state.view) }
		}, before);
		map.addLayer({
			id: 'fields-line', type: 'line', source: 'fields', 'source-layer': CONFIG.FIELDS_LAYER,
			minzoom: CONFIG.FIELDS_MIN_ZOOM,
			paint: {
				'line-color': '#2c2a28',
				'line-opacity': ['interpolate', ['linear'], ['zoom'], 9, 0.15, 13, 0.45],
				'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.2, 14, 1, 16, 1.6]
			}
		}, before);
		map.addLayer({
			id: 'fields-pick', type: 'line', source: 'fields', 'source-layer': CONFIG.FIELDS_LAYER,
			minzoom: CONFIG.FIELDS_MIN_ZOOM,
			filter: ['==', ['get', ATTR.fid], -1],
			paint: { 'line-color': '#2c2a28', 'line-width': 2.2 }
		}, before);
		applyConfidence();

		for (const id of ['fields-fill', 'summary-fill']) {
			map.on('mouseenter', id, () => { map.getCanvas().style.cursor = 'pointer'; });
			map.on('mouseleave', id, () => { map.getCanvas().style.cursor = ''; hideTip(); });
			map.on('mousemove', id, (e) => showTip(e, id));
		}
		map.on('click', 'fields-fill', (e) => pickField(e.features[0]));
		map.on('click', 'summary-fill', (e) => pickCell(e.features[0]));
		map.on('zoomend', updateScaleNote);
		map.on('error', (e) => {
			const msg = e && e.error && e.error.message ? e.error.message : '';
			if (/pmtiles|fields|summary|404|403/i.test(msg)) log('Tile source failed', msg, 'err');
		});
		state.mapReady = true;
		updateScaleNote();
		if (PLACEHOLDER && !location.hash.includes('map=')) goToPlaceholder();
	});
}

/** pmtiles wants an absolute URL for a relative path. */
function absolute(u) {
	return /^https?:/i.test(u) ? u : new URL(u, location.href).href;
}

function applyView() {
	if (!state.mapReady) return;
	map.setPaintProperty('fields-fill', 'fill-color', fieldFill(state.view));
	map.setPaintProperty('fields-fill', 'fill-opacity', fieldOpacity(state.view));
	map.setPaintProperty('summary-fill', 'fill-color', summaryFill(state.view));
	map.setPaintProperty('summary-fill', 'fill-opacity', summaryOpacity(state.view));
}

function applyConfidence() {
	if (!state.mapReady) return;
	const f = fieldFilter();
	map.setFilter('fields-fill', f);
	map.setFilter('fields-line', f);
	map.setPaintProperty('fields-fill', 'fill-opacity', fieldOpacity(state.view));
}

function goToPlaceholder() {
	map.fitBounds(CONFIG.PLACEHOLDER.BOUNDS, { padding: 20, duration: 1200 });
}

function updateScaleNote() {
	const z = map.getZoom();
	const fieldsOn = z >= CONFIG.FIELDS_MIN_ZOOM;
	state.summaryVisible = !fieldsOn;
	$('objScale').textContent = fieldsOn
		? `Zoom ${z.toFixed(1)}: fields`
		: `Zoom ${z.toFixed(1)}: summary cells. Zoom past ${CONFIG.FIELDS_MIN_ZOOM} for fields.`;
	renderLegend();
}

/* ------------------------------------------------------------------ tooltip */

function showTip(e, layerId) {
	const f = e.features && e.features[0];
	if (!f) return hideTip();
	const p = f.properties;
	const v = state.view;
	let title;
	let rows;
	if (layerId === 'fields-fill') {
		title = `Field ${p[ATTR.fid]}`;
		rows = [[v.title, fieldValueText(v, p)]];
		/* The crop of each year is named in every view, from the MapBiomas mode class. */
		const c20 = p[ATTR.crop_2020];
		const c24 = p[ATTR.crop_2024];
		if (v.id !== 'crop_2020') rows.push(['Crop 2020', cropName(c20)]);
		if (v.id !== 'crop_2024') rows.push(['Crop 2024', cropName(c24) + (c20 != null && c24 != null && c20 !== c24 ? ' (switched)' : '')]);
		rows.push(['Area', `${fmt(p[ATTR.area_ha], 1)} ha`]);
		if (p[ATTR.confidence] != null) rows.push(['Confidence', confidenceName(p[ATTR.confidence])]);
	} else {
		title = 'Summary cell';
		rows = [[v.summary.label, summaryValueText(v, p)], ['Fields', fmtInt(p[SUMMARY_ATTR.n_fields])]];
		if (v.id === 'change') {
			rows.push(['Declining / gaining', `${pct(p[SUMMARY_ATTR.share_decline])} / ${pct(p[SUMMARY_ATTR.share_gain])}`]);
			rows.push(['Mean change (ratio scale)', fmt(p[SUMMARY_ATTR.mean_change])]);
		}
		if (v.id !== 'crop_2020') rows.push(['Main crop 2020', cropName(p[SUMMARY_ATTR.dominant_crop_2020])]);
		if (v.id !== 'crop_2024') rows.push(['Main crop 2024', cropName(p[SUMMARY_ATTR.dominant_crop_2024])]);
	}
	const el = $('tip');
	el.innerHTML = `<b>${esc(title)}</b>` + rows.map(([k, val]) => `<div class="r"><span>${esc(k)}</span><span>${esc(val)}</span></div>`).join('');
	el.style.opacity = 1;
	el.style.left = Math.min(e.originalEvent.clientX + 14, window.innerWidth - 300) + 'px';
	el.style.top = (e.originalEvent.clientY + 14) + 'px';
}
function hideTip() { $('tip').style.opacity = 0; }

function cropName(k) { return k == null ? NA : (cropByKey[k] ? cropByKey[k].label : `class ${k}`); }
function decisionName(k) { return k == null ? NA : (decisionByKey[k] ? decisionByKey[k].label : k); }
function changeName(k) { return k == null ? NA : (changeByKey[k] ? changeByKey[k].label : k); }
function vigorName(k) { return k == null ? NA : (VIGOR[k] || k); }
function confidenceName(k) {
	if (k == null) return NA;
	return k === CONFIDENCE.LOW ? 'low' : (k === CONFIDENCE.HIGH ? 'high' : String(k));
}

function fieldValueText(v, p) {
	switch (v.id) {
		case 'change': return changeName(p[ATTR.change_class]) + (p[ATTR.change] != null ? ` (${fmt(p[ATTR.change])})` : '');
		case 'prod_2020': return fmt(p[ATTR.prod_2020]);
		case 'prod_2024': return fmt(p[ATTR.prod_2024]);
		case 'crop_2020': return cropName(p[ATTR.crop_2020]);
		case 'crop_2024': return cropName(p[ATTR.crop_2024]);
		case 'vigor': {
			const a = p[ATTR.vigor_2020];
			const b = p[ATTR.vigor_2024];
			return a == null || b == null ? 'not pasture in both years' : `${vigorName(a)} to ${vigorName(b)}`;
		}
		case 'decision': return decisionName(derivedKey(v, p) || p[ATTR.decision]);
		default: return '';
	}
}

function summaryValueText(v, p) {
	const s = v.summary;
	if (s.kind === 'net') return netText(s, p);
	const val = p[SUMMARY_ATTR[s.attr]];
	if (s.kind === 'class') {
		const c = s.classes.find((x) => x.key == val);
		return c ? c.label : (val == null ? NA : String(val));
	}
	return fmt(val);
}

/** The net share of a cell as signed percentage points, for example "+12 points declining". */
function netText(s, p) {
	const a = p[SUMMARY_ATTR[s.minuend]];
	const b = p[SUMMARY_ATTR[s.subtrahend]];
	if (a == null || b == null) return NA;
	const pts = Math.round((a - b) * 100);
	if (pts === 0) return 'balanced';
	return pts > 0 ? `${pts} points more declining` : `${-pts} points more gaining`;
}

/* ------------------------------------------------------------------ legend and context */

function scopeStats() {
	if (!state.stats) return null;
	if (state.stateCode && state.stats.states && state.stats.states[state.stateCode]) {
		return state.stats.states[state.stateCode];
	}
	return state.stats.brazil || null;
}

function scopeName() {
	return state.stateCode ? (STATES.find((s) => s.code === state.stateCode) || {}).name : 'Brazil';
}

function renderLegend() {
	const v = state.view;
	const st = scopeStats();
	let counts = v.countKey && st && st[v.countKey] ? st[v.countKey] : null;
	/* A derived class takes its count from the source attribute's counts and leaves the
	   tile value it was split from (decision "none") with the rest. */
	if (counts && v.classes && st) {
		for (const c of v.classes) {
			if (!c.derivedFrom || !st[c.derivedFrom.attr]) continue;
			const n = st[c.derivedFrom.attr][c.derivedFrom.value];
			if (n == null) continue;
			counts = { ...counts, [c.key]: n };
			if (counts.none != null) counts.none = Math.max(0, counts.none - n);
		}
	}
	let items;
	if (state.summaryVisible) {
		const s = v.summary;
		items = s.kind === 'class'
			? s.classes.map((c) => ({ color: c.color, label: c.label }))
			: s.steps.labels.map((l, i) => ({ color: s.steps.colors[i], label: l }));
		$('legendTitle').textContent = s.label;
	} else if (v.kind === 'vigor') {
		items = VIGOR_CHANGE.map((c) => ({ color: c.color, label: c.label }));
		$('legendTitle').textContent = '2024 class minus 2020 class';
	} else if (v.kind === 'class') {
		items = v.classes
			.map((c) => ({
				color: c.color, label: c.label, note: c.note, opacity: c.opacity,
				n: counts ? counts[String(c.key)] : undefined
			}))
			/* Crop classes that never occur in the scope are left off the legend. */
			.filter((it) => v.attr.indexOf('crop') !== 0 || !counts || it.n != null);
		$('legendTitle').textContent = 'Classes';
	} else {
		items = v.steps.labels.map((l, i) => ({ color: v.steps.colors[i], label: l }));
		$('legendTitle').textContent = 'Field value against the peer median';
	}
	items.push({ color: NODATA_COLOR, label: 'No value' });
	if (!state.summaryVisible && state.confMode === 'fade') {
		items.push({ color: '#2c2a28', opacity: CONFIDENCE.FADE_FACTOR, label: 'Low confidence (faded)' });
	}
	$('legend').innerHTML = items.map((it) => `
		<li><span class="sw" style="background:${it.color}${it.opacity != null ? `;opacity:${it.opacity}` : ''}"></span><span>${esc(it.label)}</span>
		<span class="n">${it.n != null ? fmtInt(it.n) : ''}</span>
		${it.note ? `<span class="sub">${esc(it.note)}</span>` : ''}</li>`).join('');
	$('legendCaveat').textContent = v.caveat;
	$('legendMethod').textContent = v.method;
	const hasCounts = items.some((it) => it.n != null);
	$('legendCountNote').hidden = !hasCounts;
	if (hasCounts) {
		let note = `Counts are fields in ${scopeName()}${state.stats && state.stats.placeholder ? ' (placeholder)' : ''}.`;
		const ab = st && st.change_class ? st.change_class.abandoned : null;
		if (v.id === 'change' && ab != null) {
			note += ` The ${fmtInt(ab)} abandoned fields are 2020 outlines and add to the field total above.`;
		}
		if (v.id === 'decision' && ab != null && counts && counts.restore != null) {
			note += ` Restore includes the ${fmtInt(ab)} abandoned 2020 outlines; on 2024 outlines alone it is ${fmtInt(counts.restore - ab)}.`;
		}
		$('legendCountNote').textContent = note;
	}
}

function renderScope() {
	const st = scopeStats();
	const box = $('scopeStats');
	if (!st) { box.innerHTML = '<p class="ctxNote">No summary statistics loaded.</p>'; return; }
	const n = st.n_fields || 0;
	const cc = st.change_class || {};
	const noData = cc.no_data;
	const abandoned = cc.abandoned;
	const low = st.confidence_low;
	const share = (x) => (x == null || !n ? NA : `${(100 * x / n).toFixed(1)}%`);
	const src = state.stats.source ? esc(state.stats.source) : '';
	const gen = state.stats.generated ? esc(state.stats.generated) : '';
	box.innerHTML = `
		<div class="stats">
			<div class="stat"><span class="v">${fmtInt(n)}</span><span class="k">fields, 2024 outlines</span></div>
			<div class="stat"><span class="v">${fmtInt(Math.round(st.area_ha || 0))}</span><span class="k">hectares</span></div>
			<div class="stat"><span class="v">${share(low)}</span><span class="k">low confidence</span></div>
			<div class="stat"><span class="v">${share(noData)}</span><span class="k">no data</span></div>
			<div class="stat"><span class="v">${fmtInt(abandoned)}</span><span class="k">abandoned, 2020 outlines</span></div>
		</div>
		<p class="ctxNote">Shares are of the 2024 outlines. Abandoned fields are 2020 outlines, listed on their own and not in the shares; in the legend counts they add to the abandoned class and to the restore suggestion.</p>
		${src ? `<p class="ctxNote">Source: ${src}${gen ? `, built ${gen}` : ''}. Low confidence means the field is under ${CONFIDENCE.LOW_AREA_HA} ha (one MODIS pixel) or fewer than 75 percent of its growing-season composites were observed.</p>` : ''}`;
}

function setView(id, push = true) {
	const v = VIEWS.find((x) => x.id === id) || VIEWS[0];
	state.view = v;
	document.querySelectorAll('.view-link').forEach((b) => b.classList.toggle('active', b.dataset.view === v.id));
	$('crumbMode').textContent = v.title.toUpperCase();
	$('objQ').textContent = v.question;
	$('objMode').textContent = v.group;
	applyView();
	renderLegend();
	if (state.picked) renderPick();
	if (push) writeUrl();
}

function setState(code, fly = true) {
	state.stateCode = code;
	$('stateSel').value = code;
	const s = STATES.find((x) => x.code === code);
	if (fly && state.mapReady) {
		if (s) map.fitBounds([[s.bbox[0], s.bbox[1]], [s.bbox[2], s.bbox[3]]], { padding: 20, duration: 900 });
		else map.fitBounds(CONFIG.BRAZIL_BOUNDS, { padding: 20, duration: 900 });
	}
	renderScope();
	renderLegend();
	writeUrl();
}

function setConfidence(mode) {
	state.confMode = CONFIDENCE.MODES.some((m) => m.key === mode) ? mode : CONFIDENCE.DEFAULT;
	$('confSel').value = state.confMode;
	applyConfidence();
	renderLegend();
	writeUrl();
}

function writeUrl() {
	const u = new URL(location.href);
	u.searchParams.set('view', state.view.id);
	if (state.stateCode) u.searchParams.set('state', state.stateCode); else u.searchParams.delete('state');
	if (state.confMode !== CONFIDENCE.DEFAULT) u.searchParams.set('conf', state.confMode); else u.searchParams.delete('conf');
	history.replaceState(null, '', u);
}

/* ------------------------------------------------------------------ picked field */

function pickField(f) {
	state.picked = { kind: 'field', p: f.properties };
	map.setFilter('fields-pick', ['==', ['get', ATTR.fid], f.properties[ATTR.fid]]);
	renderPick();
}

function pickCell(f) {
	state.picked = { kind: 'cell', p: f.properties };
	renderPick();
}

function clearPick() {
	state.picked = null;
	if (state.mapReady) map.setFilter('fields-pick', ['==', ['get', ATTR.fid], -1]);
	$('pickBox').hidden = true;
}

function renderPick() {
	const box = $('pickBox');
	box.hidden = false;
	const { kind, p } = state.picked;
	const has = (name) => p[name] != null;
	if (kind === 'cell') {
		$('pickTitle').textContent = 'Summary cell';
		const rows = [
			['H3 cell', p[SUMMARY_ATTR.h3]],
			['Fields', fmtInt(p[SUMMARY_ATTR.n_fields])],
			['Area', `${fmtInt(Math.round(p[SUMMARY_ATTR.area_ha] || 0))} ha`],
			['Declining minus gaining', netText(VIEWS[0].summary, p)],
			['Mean change (ratio scale)', fmt(p[SUMMARY_ATTR.mean_change])],
			['Share declining', pct(p[SUMMARY_ATTR.share_decline])],
			['Share gaining', pct(p[SUMMARY_ATTR.share_gain])],
			['Share no data', pct(p[SUMMARY_ATTR.share_no_data])],
			['Mean productivity 2020', fmt(p[SUMMARY_ATTR.mean_prod_2020])],
			['Mean productivity 2024', fmt(p[SUMMARY_ATTR.mean_prod_2024])],
			['Main crop 2020', cropName(p[SUMMARY_ATTR.dominant_crop_2020])],
			['Main crop 2024', cropName(p[SUMMARY_ATTR.dominant_crop_2024])],
			['Share pasture', pct(p[SUMMARY_ATTR.share_pasture])]
		];
		if (has(SUMMARY_ATTR.mean_vigor_change)) rows.push(['Mean vigor change', fmt(p[SUMMARY_ATTR.mean_vigor_change])]);
		rows.push(['Main suggestion', decisionName(p[SUMMARY_ATTR.dominant_decision])]);
		$('pickRows').innerHTML = rows.map(row).join('');
		$('pickChart').innerHTML = '';
		$('pickNote').textContent = '';
		return;
	}
	$('pickTitle').textContent = `Field ${p[ATTR.fid]}`;
	const c20 = p[ATTR.crop_2020];
	const c24 = p[ATTR.crop_2024];
	const rows = [
		['Area', `${fmt(p[ATTR.area_ha], 1)} ha`],
		['Crop 2020', cropName(c20)],
		['Crop 2024', cropName(c24) + (c20 != null && c24 != null && c20 !== c24 ? ' (switched)' : '')],
		['Relative productivity 2020', fmt(p[ATTR.prod_2020])],
		['Relative productivity 2024', fmt(p[ATTR.prod_2024])],
		['Change (ratio scale)', fmt(p[ATTR.change])],
		['Change class', changeName(p[ATTR.change_class])]
	];
	if (has(ATTR.vigor_2020) || has(ATTR.vigor_2024)) {
		rows.push(['Pasture vigor 2020', vigorName(p[ATTR.vigor_2020])]);
		rows.push(['Pasture vigor 2024', vigorName(p[ATTR.vigor_2024])]);
	}
	const decKey = derivedKey(VIEWS.find((x) => x.id === 'decision'), p) || p[ATTR.decision];
	rows.push(['Suggested decision', decisionName(decKey)]);
	rows.push(['Confidence', confidenceName(p[ATTR.confidence])]);
	rows.push(['Clear composites 2020 / 2024', `${fmtInt(p[ATTR.n_obs_2020])} / ${fmtInt(p[ATTR.n_obs_2024])}`]);
	rows.push(['Municipality (IBGE)', p[ATTR.muni_code] == null ? NA : String(p[ATTR.muni_code])]);
	$('pickRows').innerHTML = rows.map(row).join('');
	const d = decisionByKey[decKey];
	let note = d ? `${d.label}: ${d.note}.` : '';
	if (p[ATTR.confidence] === CONFIDENCE.LOW) {
		note += ` Low confidence: the field is under ${CONFIDENCE.LOW_AREA_HA} ha or had few clear composites, so its greenness is shared with neighboring land.`;
	}
	$('pickNote').textContent = note.trim();
	$('pickChart').innerHTML = prodBars(p[ATTR.prod_2020], p[ATTR.prod_2024]);
}

function row([k, v]) { return `<li><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></li>`; }
function pct(v) { return v == null ? NA : `${Math.round(v * 100)}%`; }

/** Two bars, 2020 and 2024, against a dashed line at 1.0 (the peer median). */
function prodBars(a, b) {
	const W = 300;
	const H = 110;
	const padL = 30;
	const padB = 18;
	const padT = 10;
	const vals = [a, b].filter((v) => v != null && isFinite(v));
	if (!vals.length) return '<p class="ctxNote">No productivity value in either year.</p>';
	const hi = Math.max(1.6, ...vals) * 1.05;
	const yf = (v) => padT + (1 - v / hi) * (H - padT - padB);
	const bw = 70;
	const xs = [padL + 50, padL + 170];
	const bar = (v, x, cls, yr) => {
		if (v == null || !isFinite(v)) {
			return `<text class="tick" x="${x + bw / 2}" y="${yf(0) - 4}" text-anchor="middle">no value</text>
				<text class="tick" x="${x + bw / 2}" y="${H - 4}" text-anchor="middle">${yr}</text>`;
		}
		const y = yf(v);
		return `<rect class="bar ${cls}" x="${x}" y="${y}" width="${bw}" height="${(yf(0) - y).toFixed(1)}" rx="2"/>
			<text class="val" x="${x + bw / 2}" y="${y - 4}" text-anchor="middle">${fmt(v)}</text>
			<text class="tick" x="${x + bw / 2}" y="${H - 4}" text-anchor="middle">${yr}</text>`;
	};
	return `<svg class="chart" viewBox="0 0 ${W} ${H}" width="100%" role="img"
		aria-label="Relative productivity 2020 ${fmt(a)} and 2024 ${fmt(b)} against a peer median of 1.0">
		<line class="axis" x1="${padL}" x2="${W - 4}" y1="${yf(0)}" y2="${yf(0)}"/>
		<line class="ref" x1="${padL}" x2="${W - 4}" y1="${yf(1)}" y2="${yf(1)}"/>
		<text class="tick" x="${padL - 4}" y="${yf(1) + 3}" text-anchor="end">1.0</text>
		<text class="tick" x="${padL - 4}" y="${yf(0) + 3}" text-anchor="end">0</text>
		${bar(a, xs[0], 'y20', '2020')}${bar(b, xs[1], 'y24', '2024')}
	</svg>
	<p class="ctxNote">Dashed line: the peer median (same crop, same region) in that year.</p>`;
}

/* ------------------------------------------------------------------ boot */

function buildNav() {
	const nav = $('sidebar');
	let group = null;
	let html = '';
	for (const v of VIEWS) {
		if (v.group !== group) { group = v.group; html += `<p class="group">${esc(group)}</p>`; }
		html += `<button class="view-link" type="button" data-view="${v.id}"><span class="vt">${esc(v.title)}</span></button>`;
	}
	html += '<p class="group">More</p>';
	html += '<a class="view-link" href="./methods.html"><span class="vt">Methods</span></a>';
	html += '<a class="view-link" href="./about.html"><span class="vt">About</span></a>';
	nav.innerHTML = html;
	nav.querySelectorAll('button.view-link').forEach((b) => b.addEventListener('click', () => setView(b.dataset.view)));
}

function buildStateSelect() {
	const sel = $('stateSel');
	sel.innerHTML = '<option value="">All of Brazil</option>' +
		STATES.map((s) => `<option value="${s.code}">${esc(s.name)}</option>`).join('');
	sel.addEventListener('change', () => setState(sel.value));
}

function buildConfidenceSelect() {
	const sel = $('confSel');
	sel.innerHTML = CONFIDENCE.MODES.map((m) => `<option value="${m.key}">${esc(m.label)}</option>`).join('');
	sel.value = state.confMode;
	sel.addEventListener('change', () => setConfidence(sel.value));
}

async function loadStats() {
	try {
		const r = await fetch(SRC.STATS_URL);
		if (!r.ok) throw new Error(`${r.status} ${SRC.STATS_URL}`);
		state.stats = await r.json();
	} catch (e) {
		log('Summary statistics not loaded', String(e.message || e), 'err');
		state.stats = null;
	}
	renderScope();
	renderLegend();
}

function setupBanner() {
	if (!PLACEHOLDER) return;
	document.body.classList.add('has-banner');
	$('banner').hidden = false;
	$('bannerGo').addEventListener('click', () => { if (state.mapReady) goToPlaceholder(); });
}

function boot() {
	buildNav();
	buildStateSelect();
	buildConfidenceSelect();
	setupBanner();
	$('pickClose').addEventListener('click', clearPick);
	const u = new URL(location.href);
	if (u.searchParams.get('conf')) setConfidence(u.searchParams.get('conf'));
	setView(u.searchParams.get('view') || VIEWS[0].id, false);
	if (u.searchParams.get('state')) setState(u.searchParams.get('state'), false);
	loadStats();
	initMap();
}

boot();

/** Debug handle, so a console or a test can drive the page. */
window.__rlp = { get map() { return map; }, state, setView, setState, setConfidence, pickField, goToPlaceholder, CONFIG };
