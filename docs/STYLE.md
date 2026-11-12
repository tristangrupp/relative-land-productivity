# Site style

What this site takes from the two sites it should match, and what it does differently.
The two references are `C:\Users\grupp\src\agriculture-and-drought\docs` (live at
https://tristangrupp.github.io/agriculture-and-drought/) and `D:\teleshed\rainsheds\app`
(the wri/teleshed Pages site).

## Typography

Both references set a 13px to 14px base with a 1.45 to 1.55 line height. The drought site
uses IBM Plex Mono for structure (breadcrumbs, nav items, card headings, stat values,
legend labels, tick marks) and IBM Plex Sans for prose. Teleshed uses the system sans only
and limits the panel to four type roles: title, label, body, tick. This site follows the
drought site's fonts and teleshed's discipline: mono for structure and numbers, sans for
sentences, uppercase 11px mono with letter spacing for section labels, and no other roles.

## Color system

The drought site reads its tokens off WRI's ai-web-map-exploration build and this site
reuses them unchanged in `style.css`: ground `#faf8f6`, card `#f2efe9`, hairline `#d8d4ce`
at 0.606px, ink `#2c2a28`, secondary ink `#5c5a58`, muted `#8a8681`, WRI amber
`oklch(0.8 0.17 85)` as the one accent, used for the active nav rail and the objective
box rail. Teleshed is a blue ink on white page. It is not reused here because the two WRI
field sites should look like one family.

Data colors follow the dataviz skill. The diverging ramp for productivity change is brown
(below peers) to green (above peers) with a neutral `#e8e3da` midpoint. Adjacent pairs pass
the color vision deficiency (CVD) check at deltaE 13.4. The seven decision classes use the validated categorical
order from the skill's reference palette, with "keep" as the neutral because it means no
change. Crop types use the published MapBiomas legend colors so a reader who knows those
maps reads this one the same way. They are not CVD separated, and the legend and tooltip
name every class.

## Layout

The drought site's three-column shell: 56px header with an uppercase mono breadcrumb, a
248px left nav of grouped view links with an amber active rail, the map in the middle, a
340px right context column of cards. The context column opens with an "objective" box
that names the one question the active view answers, which the drought site added after
feedback that basin and field contexts were hard to tell apart. Below 1100px the context
column moves under the map; below 760px the nav becomes a horizontal strip.

Teleshed keeps its caption on the map itself so a screenshot explains itself. This site
keeps the question in the objective box and a zoom note under it instead.

## Map libraries

MapLibre GL 4.7.1 and pmtiles 3.2.1 from unpkg, pinned. The drought site vendors MapLibre
because its GeoJSON tiling worker failed when loaded cross-origin; this site reads vector
tiles through the pmtiles protocol, which does not hit that path, and the CDN build was
checked in a browser before publishing. No DuckDB-WASM: the drought site's local build
queries GeoParquet with it, but the published build ships plain files, and this site
serves everything as PMTiles, which only needs HTTP range requests. The basemap is the
OpenFreeMap positron style, with the Carto positron style as the fallback when the first
does not load; both are free and need no key. Fields draw from zoom 9; below that an H3
summary layer draws, with its own legend per view.

## Methods and caveats on the page

Both references put the method next to the thing it explains rather than on a separate
page only. The drought site keeps one caveat per view as a muted `.ctxNote` under the
legend, and the full reasoning in the README. Teleshed uses a `.caveat` block in each
layer's key and a `details` fold for the longer explanation. This site does both: every
view has a one-sentence caveat under its legend and a "How this is measured" fold with the
method paragraph, both written in `config.js` beside the view so they travel with it. The
methods page holds the long form.

## Reused directly

`serve.py` (range requests for PMTiles), the CSS tokens and the shell layout from the
drought site, the `.nojekyll` file, the objective box pattern, and the practice of writing
the one caveat that matters into the panel.
