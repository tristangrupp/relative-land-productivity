# AGENTS.md

Standing instructions for any coding agent (Claude Code, Codex or other) working in this
repository. Read this file first, then WORKLOG.md, then BRIEF.md.

## What this project is

A public map of per-field productivity change in Brazil between the 2020 and 2024
agricultural years (1 September to 31 August), by crop type, with a suggested land use
decision per field and per area. Live site: https://tristangrupp.github.io/relative-land-productivity/
(GitHub Pages from `docs/` on main). Productivity is relative greenness: the seasonal NDVI
integral inside the CONAB crop calendar window, weather-adjusted, compared with peers of the
same crop. It is not yield. Validation against IBGE municipal yields is weak, and the site
says so.

## Read order

1. AGENTS.md (this file): rules and duties.
2. WORKLOG.md: current state, open items, resume steps, and the dated log of every decision.
   DECISIONS.md: the register of every decision, one row each, with who made it and its status.
3. BRIEF.md: the agent contract, the folder contract, and the Decisions section.
4. methods/METHODS.md: the method, including the decision table in section 7.
5. pipeline/ANALYZE.md and the other pipeline reports for the stage you touch.
6. docs/DATA_CONTRACT.md before any change to the tiles or the site.

## Documentation duty

The work must survive a context reset of whoever runs it. So, as you work:

- Every decision the user makes goes into WORKLOG.md, dated, in the Log section, with the
  reason and what changed. Do this in the same commit as the change.
- A decision that changes the method also goes into methods/METHODS.md at the place it
  governs (for example the decision table), and into docs/methods.html if the site states
  it.
- A change to tile attributes, zoom bands or file locations goes into docs/DATA_CONTRACT.md
  and README.md.
- Before you end, update the "Current state" and "Open items" sections of WORKLOG.md if you
  changed them, and append one dated entry to the BRIEF.md Decisions section.
- Record answers to the user's questions about the data in WORKLOG.md when they explain a
  feature of the map, so the next session does not rediscover them.
- Never rewrite earlier log or Decisions entries. Correct them with a new entry.

## Hard rules

- No Earth Engine in any form. Never the Google Cloud project tkt-tristan. Satellite data
  comes from Microsoft Planetary Computer COGs read locally.
- No AWS compute. S3 is storage only, through the profile `mfr-datalab` (SSO). If the SSO
  session expires, stop and ask the user to run `aws sso login --profile mfr-datalab --no-browser`.
- Local compute only. Keep peak memory under about 20 GB; other jobs share the machine.
- Never modify anything under `E:\`. Fields come from `E:\trazo4_master_parquet_seamfix`,
  read only.
- Data lives under `F:\relative-land-productivity-data`. Scripts never go inside a folder of
  downloaded data.
- Do not stop the Sentinel-2 extraction (`s03g_s2_fetch_reduce.py`, detached) unless the
  user asks.
- Do not submit forms, send messages or publish anywhere other than this repo, its Pages site
  and the S3 prefix below without asking the user.

## Working rules from the user (16 November 2026)

- Prioritize work that can be committed, pushed and made live on GitHub Pages soon.
- Do not occupy the machine indefinitely; stop or hand back long jobs that are not needed.
- Launch every long job hidden: no console windows (`pipeline/launch_detached.py`, or WMI
  with ShowWindow 0; subprocesses with `creationflags=CREATE_NO_WINDOW`).
- Commit and save work before context compaction, and record what remains to be done in
  WORKLOG.md (Open items).
- Keep methods/METHODS.md current on GitHub as the work progresses.

## Writing rules

Apply to prose, code comments, commit messages, identifiers and JSON keys.

- No em dashes or en dashes, in any form.
- No form of the verb "carry".
- American spelling.
- Plain prose, one idea per sentence, exact numbers, no self-grading or rhythm fragments.
  Name things; say what the reader sees before what it means.
- Commit messages are plain and end with the co-author line the session supplies.

## Environment

- Python: `E:\Water\water intelligence\wci_tools\.venv\Scripts\python.exe`. Never bare
  `python`; on this machine it is a broken wrapper.
- tippecanoe and tile-join run in WSL Ubuntu-22.04. Write their output on the WSL disk and
  copy to F:, because writing through /mnt/f is about 100 times slower (pipeline/s05_tiles.py
  does this).
- GitHub in Git Bash: `export GH_TOKEN=$(printf 'protocol=https\nhost=github.com\n' | git credential fill | sed -n 's/^password=//p')`.
- Long runs (16 November 2026): start them with `pipeline/launch_detached.py`, itself
  launched through WMI, so they survive the end of the Claude session and console Ctrl-C.
  Processes started from a Claude shell, with Start-Process, or through WMI with a `cmd`
  console all died in November. In PowerShell:
  `Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{ CurrentDirectory = 'C:\Users\grupp\src\relative-land-productivity'; CommandLine = '"<python>" C:\Users\grupp\src\relative-land-productivity\pipeline\launch_detached.py <log> <err> -- "<python>" -u pipeline\<script>.py <args>' }`,
  with `<python>` the interpreter above. Add `ProcessStartupInformation = (New-CimInstance
  -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 })` to the
  arguments so no window opens (the user asked for no console windows). Wait for such a run inside your turn with cheap
  periodic checks of its log; do not hand back while it runs. Run one heavy worker at a
  time unless the orchestrator says otherwise, and keep each under about 8 GB: on 16 Nov two
  CAR workers and a fields test filled memory and killed the tile join twice.
- Several agents may work in the clone at once. Commit only your own files, pull with
  rebase (or `git rebase --autostash origin/main`) before pushing, and leave other agents'
  unstaged files alone.

## Published data

Prefix: `https://wri-datalab-sandbox.s3.amazonaws.com/trazofields/trazo4/relative-land-productivity/`

- `tiles/fields.pmtiles`: 2024 field outlines, zoom 9 to 13 (overzoomed above).
- `tiles/summary.pmtiles`: H3 summary cells, resolution 6 (about 6 km) at zooms 3 to 9
  (13 November 2026; resolution 7 measured 173 MB, over the 150 MB budget).
- `tiles/stats.json`: counts nationally and per state. Its change_class and decision counts
  include the abandoned 2020 outlines; shares divide by n_fields of 2024 outlines.
- `fields/year=2024/state=<State>/fields_scored.parquet` and `fields/abandoned/state=<State>.parquet`.

`pipeline/s05_upload.py --tiles --check` uploads and confirms public read (HTTP 206).

## Site workflow

1. Edit `docs/` (config.js holds classes, colors, views and attribute names; app.js holds
   no attribute names of its own).
2. Test: `python serve.py` from the repo root serves `docs/` on port 8810 with range support.
3. Bump the `?v=` cache busters in docs/index.html.
4. Commit, push, wait for Pages (about a minute), and check the live page in a browser,
   including the console. Stop the local server when done.

## The user's standing preferences for the map

- Default view: productivity change 2020 vs 2024.
- The zoomed-out map must be dense: many small cells. 100 km, 40 km and (13 November) 15 km
  cells were rejected as too coarse; 6 km cells at every zoom now. The change view uses a
  continuous ramp, not a few flat steps ("too coarse and oversimplified").
- The zoomed-out change map is the national frontier map: cells colored by their change
  against Brazil as a whole ("lets do brazil as a whole then to get the true frontiers of
  productivity change").
- Legend rows are short: swatch, label, count. Explanatory notes open from an info marker on
  hover, focus or tap, never as text in the legend.
- Crop names (from the MapBiomas mode codes, legend from the source.coop mapbiomas-brazil
  collection) show on hover in every view, for 2020 and 2024.
- Crop switched, newly cropped and abandoned draw at 50 percent opacity.
- Newly cropped fields get the suggestion "Recently converted land", in a green near but
  distinct from restore.
- Decisions must blend two scales: the immediate area (H3 cell) and a large reference.
  Since 13 November the area call uses Brazil as the reference; the RESOLVE 2017 ecoregion
  scores stay as secondary context in the tooltip and card. See WORKLOG.md and METHODS.md
  section 7 for the two-tier design.
- The zoomed-out decision map must not be one color: it shows the action that stands out in
  each cell, and intensify is a calm color, not orange.
- (14 November 2026) The area call is made per 6 km cell (H3 resolution 6), with the 15 km
  parent where the 6 km cell is too thin; `area_level` says which.
- (14 November 2026) A low-confidence field (MODIS under 6.25 ha or few clear composites;
  Sentinel-2 under 0.45 ha) shows "Low confidence: too small to judge yet" in a cool light
  gray distinct from no data; its computed call stays in `decision_computed` and the card
  shows it as "Computed, not trusted".
- (14 November 2026) States move from MODIS to Sentinel-2 one by one with
  `pipeline/s09_swap_state_to_s2.py --state <State>` (see "Switching a state to Sentinel-2"
  below). Every field has a `source` attribute (modis or s2) shown in the tooltip and card.
- (14 November 2026) Below-neighbors fields split by native vegetation: native vegetation
  returning inside the field gives assisted natural regeneration; large native patches
  (50 ha or more) within 1 km give a restore candidate; otherwise improve yields, which
  spares land elsewhere. Large patches count more than slivers.
- (14 November 2026) Each field shows one recommended treatment plus a short list of other
  options (`options` per class in config.js), never a site plan.
- (14 November 2026) Restore, assisted natural regeneration, restore candidate and recently
  converted land are one green family that stays distinguishable (adjacent pairs deltaE 12
  or more under simulated color vision deficiency): restore #008300, assisted natural
  regeneration #2e9e82, restore candidate #285c23, recently converted below #7cc24e, at or
  above #d7f28c.
- (14 November 2026) Keep the map, legend and tooltip simple: one legend swatch per
  recommendation; native patch size, regrowth shares and CAR or Forest Code indicators go in
  the field card details only, never as map layers, legend classes or tooltip rows.

## Switching a state to Sentinel-2

Run order (user, 14 November 2026): Mato Grosso (done 14 November), Pará, Rondônia, Acre,
Amazonas, Roraima, Amapá, then Mato Grosso do Sul, Goiás, Tocantins, Maranhão. When the
Sentinel-2 extraction has finished a state's tiles
(`F:\relative-land-productivity-data\extracted\s2\progress.log`), run

```
python pipeline\s09_swap_state_to_s2.py --state Para
```

It assembles the state's s2 tables (refusing under 99 percent of tiles complete), runs metrics
and relative on s2, runs `s08_s2_compare.py all` (calibration to the MODIS national reference,
comparison, noise and the change scale k), copies the MODIS tables to
`analysis\source=modis\`, rewrites the live tables from s2 with `s04_change.py --source s2
--change-scale k`, records the state in `analysis\sources.json` (and
`data/summaries/sources.json`), then rebuilds the decisions for all states, the field tiles
(about 45 minutes), the summary and stats, and uploads. `--no-tiles` and `--no-upload` stop
earlier; `--revert` puts the MODIS tables back. Afterwards record the state's numbers
(`data/summaries/s2_<uf>_noise.json`, `decisions_v2.json`) in WORKLOG.md, bump the cache
busters if the site changed, commit and push.

## Caveats every output should state where relevant

- MODIS at 250 m: most fields are low confidence (smaller than one pixel or few clear
  composites) and show "too small to judge yet" until their state switches to Sentinel-2.
- Mato Grosso uses Sentinel-2 since 14 November 2026, with change thresholds scaled by 1.22.
- The restore versus improve yields split rests on two years of greenness and on the
  MapBiomas maps of 2020 and 2024.
- Wet-season cloud removes about a fifth of Pará's fields (no data).
- The weather regression explains little (median R squared 0.15).
- Pasture vigor is not implemented.
- Relative greenness is not yield; prod and change correlate below 0.24 with municipal yields.
