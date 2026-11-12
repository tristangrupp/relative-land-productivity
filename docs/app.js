/**
 * Relative land productivity, Brazil 2020 to 2024: the map page.
 *
 * One MapLibre map with two PMTiles sources. Below FIELDS_MIN_ZOOM the summary cells (H3)
 * are drawn; from it upward, the fields. Each view in the left nav sets one fill expression
 * on both layers and one legend. Clicking a field opens the field card with its attributes
 * and a 2020 against 2024 bar.
 *
 * All attribute names come from config.js (ATTR, SUMMARY_ATTR). Nothing here names a tile
 * property directly.
 */

import {
	CONFIG, ATTR, SUMMARY_ATTR, VIEWS, CROPS, VIGOR, VIGOR_CHANGE, DECISIONS,
	CHANGE_CLASSES, STATES, NODATA_COLOR
} from './config.js';

const $ = (id) => document.getElementById(id);
const fmt = (n, d = 2) => (n == null || !isFinite(n) ? '–' : Number(n).toFixed(d));
const fmtInt = (n) => (n == null ? '–' : Number(n).toLocaleString('en-US'));
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

const SRC = CONFIG.USE_PLACEHOLDER ? CONFIG.PLACEHOLDER : CONFIG;
const PLACEHOLDER = CONFIG.USE_PLACEHOLDER || /placeholder/i.test(SRC.FIELDS_PMTILES);

const state = {
	view: VIEWS[0],
	stateCode: '',
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
function fieldOpacity(view) {
	if (view.kind !== 'class' || !view.classes.some((c) => c.opacity != null)) return FIELD_OPACITY;
	const attrName = ATTR[view.attr];
	const m = ['match', ['get', attrName]];
	for (const c of view.classes) if (c.opacity != null) m.push(c.key, c.opacity);
	m.push(FIELD_OPACITY);
	return ['case', ['has', attrName], m, FIELD_OPACITY];
}

function stepFill(attrName, steps) {
	const s = ['step', ['get', attrName], steps.colors[0]];
	steps.breaks.forEach((b, i) => s.push(b, steps.colors[i + 1]));
	return ['case', ['has', attrName], s, NODATA_COLOR];
}

function vigorFill() {
	const a = ATTR.vigor_2020;
	const b = ATTR.vigor_2024;
	const m = ['match', ['-', ['get', b], ['get', a]]];
	for (const c of VIGOR_CHANGE) m.push(c.key, c.color);
	m.push(NODATA_COLOR);
	return ['case', ['all', ['has', a], ['has', b]], m, NODATA_COLOR];
}

function fieldFill(view) {
	if (view.kind === 'vigor') return vigorFill();
	if (view.kind === 'class') return classFill(ATTR[view.attr], view.classes);
	return stepFill(ATTR[view.attr], view.steps);
}

function summaryFill(view) {
	const s = view.summary;
	if (s.kind === 'class') return classFill(SUMMARY_ATTR[s.attr], s.classes);
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
		maxZoom: 16,
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
			attribution: 'Trazo4 fields (WRI), MapBiomas Collection 10'
		});
		map.addSource('fields', { type: 'vector', url: 'pmtiles://' + absolute(SRC.FIELDS_PMTILES) });

		map.addLayer({
			id: 'summary-fill', type: 'fill', source: 'summary', 'source-layer': CONFIG.SUMMARY_LAYER,
			maxzoom: CONFIG.FIELDS_MIN_ZOOM,
			paint: { 'fill-color': summaryFill(state.view), 'fill-opacity': 0.78 }
		}, before);
		map.addLayer({
			id: 'summary-line', type: 'line', source: 'summary', 'source-layer': CONFIG.SUMMARY_LAYER,
			maxzoom: CONFIG.FIELDS_MIN_ZOOM,
			paint: { 'line-color': '#2c2a28', 'line-opacity': 0.25, 'line-width': 0.5 }
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
				'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.2, 14, 1]
			}
		}, before);
		map.addLayer({
			id: 'fields-pick', type: 'line', source: 'fields', 'source-layer': CONFIG.FIELDS_LAYER,
			minzoom: CONFIG.FIELDS_MIN_ZOOM,
			filter: ['==', ['get', ATTR.fid], -1],
			paint: { 'line-color': '#2c2a28', 'line-width': 2.2 }
		}, before);

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
		rows = [[v.title, fieldValueText(v, p)], ['Area', `${fmt(p[ATTR.area_ha], 1)} ha`]];
	} else {
		title = 'Summary cell';
		rows = [[v.summary.label, summaryValueText(v, p)], ['Fields', fmtInt(p[SUMMARY_ATTR.n_fields])]];
	}
	const el = $('tip');
	el.innerHTML = `<b>${esc(title)}</b>` + rows.map(([k, val]) => `<div class="r"><span>${esc(k)}</span><span>${esc(val)}</span></div>`).join('');
	el.style.opacity = 1;
	el.style.left = Math.min(e.originalEvent.clientX + 14, window.innerWidth - 300) + 'px';
	el.style.top = (e.originalEvent.clientY + 14) + 'px';
}
function hideTip() { $('tip').style.opacity = 0; }

function cropName(k) { return k == null ? '–' : (cropByKey[k] ? cropByKey[k].label : `class ${k}`); }
function decisionName(k) { return k == null ? '–' : (decisionByKey[k] ? decisionByKey[k].label : k); }
function changeName(k) { return k == null ? '–' : (changeByKey[k] ? changeByKey[k].label : k); }
function vigorName(k) { return k == null ? '–' : (VIGOR[k] || k); }

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
		case 'decision': return decisionName(p[ATTR.decision]);
		default: return '';
	}
}

function summaryValueText(v, p) {
	const s = v.summary;
	const val = p[SUMMARY_ATTR[s.attr]];
	if (s.kind === 'class') {
		const c = s.classes.find((x) => x.key == val);
		return c ? c.label : (val == null ? '–' : String(val));
	}
	return fmt(val);
}

/* ------------------------------------------------------------------ legend and context */

function scopeStats() {
	if (!state.stats) return null;
	if (state.stateCode && state.stats.states && state.stats.states[state.stateCode]) {
		return state.stats.states[state.stateCode];
	}
	return state.stats.brazil || null;
}

function renderLegend() {
	const v = state.view;
	const st = scopeStats();
	const counts = v.countKey && st && st[v.countKey] ? st[v.countKey] : null;
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
		items = v.classes.map((c) => ({
			color: c.color, label: c.label, note: c.note, opacity: c.opacity,
			n: counts ? counts[String(c.key)] : undefined
		}));
		$('legendTitle').textContent = 'Classes';
	} else {
		items = v.steps.labels.map((l, i) => ({ color: v.steps.colors[i], label: l }));
		$('legendTitle').textContent = 'Field value against the peer median';
	}
	items.push({ color: NODATA_COLOR, label: 'No value' });
	$('legend').innerHTML = items.map((it) => `
		<li><span class="sw" style="background:${it.color}${it.opacity != null ? `;opacity:${it.opacity}` : ''}"></span><span>${esc(it.label)}</span>
		<span class="n">${it.n != null ? fmtInt(it.n) : ''}</span>
		${it.note ? `<span class="sub">${esc(it.note)}</span>` : ''}</li>`).join('');
	$('legendCaveat').textContent = v.caveat;
	$('legendMethod').textContent = v.method;
	const hasCounts = items.some((it) => it.n != null);
	$('legendCountNote').hidden = !hasCounts;
	if (hasCounts) {
		const name = state.stateCode ? (STATES.find((s) => s.code === state.stateCode) || {}).name : 'Brazil';
		$('legendCountNote').textContent = `Counts are fields in ${name}${state.stats && state.stats.placeholder ? ' (placeholder)' : ''}.`;
	}
}

function renderScope() {
	const st = scopeStats();
	const box = $('scopeStats');
	if (!st) { box.innerHTML = '<p class="ctxNote">No summary statistics loaded.</p>'; return; }
	box.innerHTML = `
		<div class="stats">
			<div class="stat"><span class="v">${fmtInt(st.n_fields)}</span><span class="k">fields</span></div>
			<div class="stat"><span class="v">${fmtInt(Math.round(st.area_ha || 0))}</span><span class="k">hectares</span></div>
		</div>`;
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
	if (push) {
		const u = new URL(location.href);
		u.searchParams.set('view', v.id);
		if (state.stateCode) u.searchParams.set('state', state.stateCode); else u.searchParams.delete('state');
		history.replaceState(null, '', u);
	}
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
	const u = new URL(location.href);
	if (code) u.searchParams.set('state', code); else u.searchParams.delete('state');
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
	if (kind === 'cell') {
		$('pickTitle').textContent = 'Summary cell';
		$('pickRows').innerHTML = [
			['H3 cell', p[SUMMARY_ATTR.h3]],
			['Fields', fmtInt(p[SUMMARY_ATTR.n_fields])],
			['Area', `${fmtInt(Math.round(p[SUMMARY_ATTR.area_ha] || 0))} ha`],
			['Mean change', fmt(p[SUMMARY_ATTR.mean_change])],
			['Share declining', pct(p[SUMMARY_ATTR.share_decline])],
			['Share gaining', pct(p[SUMMARY_ATTR.share_gain])],
			['Mean productivity 2020', fmt(p[SUMMARY_ATTR.mean_prod_2020])],
			['Mean productivity 2024', fmt(p[SUMMARY_ATTR.mean_prod_2024])],
			['Main crop 2020', cropName(p[SUMMARY_ATTR.dominant_crop_2020])],
			['Main crop 2024', cropName(p[SUMMARY_ATTR.dominant_crop_2024])],
			['Share pasture', pct(p[SUMMARY_ATTR.share_pasture])],
			['Mean vigor change', fmt(p[SUMMARY_ATTR.mean_vigor_change])],
			['Main suggestion', decisionName(p[SUMMARY_ATTR.dominant_decision])]
		].map(row).join('');
		$('pickChart').innerHTML = '';
		return;
	}
	$('pickTitle').textContent = `Field ${p[ATTR.fid]}`;
	const c20 = p[ATTR.crop_2020];
	const c24 = p[ATTR.crop_2024];
	$('pickRows').innerHTML = [
		['Area', `${fmt(p[ATTR.area_ha], 1)} ha`],
		['Crop 2020', cropName(c20)],
		['Crop 2024', cropName(c24) + (c20 != null && c24 != null && c20 !== c24 ? ' (switched)' : '')],
		['Relative productivity 2020', fmt(p[ATTR.prod_2020])],
		['Relative productivity 2024', fmt(p[ATTR.prod_2024])],
		['Change', fmt(p[ATTR.change])],
		['Change class', changeName(p[ATTR.change_class])],
		['Pasture vigor 2020', vigorName(p[ATTR.vigor_2020])],
		['Pasture vigor 2024', vigorName(p[ATTR.vigor_2024])],
		['Suggested decision', decisionName(p[ATTR.decision])],
		['Clear observations 2020 / 2024', `${fmtInt(p[ATTR.n_obs_2020])} / ${fmtInt(p[ATTR.n_obs_2024])}`],
		['Municipality (IBGE)', p[ATTR.muni_code] == null ? '–' : String(p[ATTR.muni_code])]
	].map(row).join('');
	const d = decisionByKey[p[ATTR.decision]];
	$('pickNote').textContent = d ? `${d.label}: ${d.note}.` : '';
	$('pickChart').innerHTML = prodBars(p[ATTR.prod_2020], p[ATTR.prod_2024]);
}

function row([k, v]) { return `<li><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></li>`; }
function pct(v) { return v == null ? '–' : `${Math.round(v * 100)}%`; }

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
	setupBanner();
	$('pickClose').addEventListener('click', clearPick);
	const u = new URL(location.href);
	setView(u.searchParams.get('view') || VIEWS[0].id, false);
	if (u.searchParams.get('state')) setState(u.searchParams.get('state'), false);
	loadStats();
	initMap();
}

boot();

/** Debug handle, so a console or a test can drive the page. */
window.__rlp = { get map() { return map; }, state, setView, setState, pickField, goToPlaceholder, CONFIG };
