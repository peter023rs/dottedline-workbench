# Dotted line workbench v2.1

Turn dashed/dotted P&ID strokes into continuous trace geometry **without discarding their visual pattern or engineering meaning**.

## Open

Double-click **Open UI.command** in this folder. It starts a local server and opens http://127.0.0.1:8767. Keep its Terminal window open. No API keys, model downloads, or cloud uploads are used.

The GitHub repository contains code and research notes. Private drawings, uploads, derived images/results and the Python environment are excluded. The original Desktop installation keeps the supplied 12-page 2401 PDF locally at `data/2401.pdf`, opening at page 4. A fresh clone starts ready for you to upload a drawing. Upload a PDF/image to try another drawing. Uploads stay in `data/uploads`; their active identifiers last until the server restarts.

The UI uses the blue-gray/teal tokens and Avenir typography from the existing Desktop `line-tracing-diagex` workbench.

## Recommended workflow

1. Choose a page and **V2 native geometry**. It falls back to raster when no straight native strokes exist. Choose raster explicitly to compare the scan-only path, or V1 for the unchanged original detector.
2. Move the before/after slider. Use Semantic overlay or Trace only, zoom and pan. Click a line or candidate row to inspect it.
3. Check the observed pattern and meaning evidence. Accept/reject geometry; assign a meaning and evidence note when needed. Reviews persist locally in this browser, keyed by document hash, page, method and detector revision. Prior-version reviews remain stored separately so renumbered candidates cannot inherit another line's decision.
4. Export the AI package. Select **Export accepted geometry only** to exclude unreviewed candidates. Otherwise all non-rejected candidates are included, clearly labeled as candidates.

Exports contain `original.png`, `normalized.png`, `trace-mask.png`, `boundary-mask.png`, `lines.json`, and a coordinate/readme note. Mask foreground is white. The trace mask includes signal/unknown candidates; assigned supply/unit boundaries go in a separate mask. The normalized image includes both classes. **Always carry JSON with the images**: a single black-and-white image cannot preserve the original distinctions.

JSON includes source document hash, page, coordinate system, candidate ID, continuous endpoints, original pattern, observed fragments with source IDs, dash/gap lengths, inferred bridge intervals, heuristic geometry score, meaning/evidence and review status. User semantic assignments preserve the prior detected semantics. All crossings remain independent; there is no inferred junction or equipment connectivity.

## Algorithm

`engine.py` extracts native straight path fragments, clusters compatible directions, offsets and widths, merges touching intervals, chains bounded gaps, splits local gap regimes before calculating their statistics, checks gap regularity and classifies repeated length patterns. Native text spans block bridging. The native path handles arbitrary straight orientations; the raster fallback uses directional morphology plus small-dot components for horizontal/vertical runs. Pattern families are dashed, dotted, dash-dot and dash-double-dot. Mixed/irregular evidence is rejected conservatively. Two-stroke runs can be recovered only when they touch an independently detected longer run at an endpoint and match its pattern, spacing, interior dash size and stroke width. This support is recorded in JSON and shown in the inspector; it never asserts a junction.

The bundled 2401 profile excludes the title block at PDF-point box `[1823,1326,2318,1629]`. It is applied only to the exact bundled document hash. Page 4's note explicitly says double-dot-dash encloses the manufacturer's supply scope. Such pattern candidates receive `supply_boundary` with source evidence. Uniform dashes receive an **electrical-signal candidate** label from page 3's legend, not verified meaning or connectivity. The legend's dash scale differs from diagram scale. Other documents retain unknown meaning until reviewed.

This is a research-inspired implementation, not an exact reproduction of Dori's algorithm. See `research.md` for eight original papers and the distinction between published claims and our adaptations. Jonk et al.'s centerline-plus-grammar formulation and CVPR 2022's separate observed/continuous representations motivate the data model.

## Tests

Install `requirements-dev.txt`, then run `.venv/bin/python -m pytest -q`. Four document-specific integration tests are skipped when `data/2401.pdf` is absent; the detector and upload tests run without it. `validate.py` requires the original 2401 document. Historical before-fix comparisons are included only when the local baseline output exists.

## Test results

- **32 automated tests pass**, including four pattern families, arbitrary native angles, parallel lines, crossings, irregular gaps, missing strokes, text interruptions, dots at three DPIs, the four real supply-boundary sides, image upload, invalid inputs and reviewed ZIP export, local pattern transitions, the reported missed runs, supported short corners, distractor rejection and stale-review isolation.
- **36 smoke runs**: all 12 sheets through V2 native, V2 raster and unchanged V1 at 144 DPI.
- **16 selected page-4 reference spans**, with approximate source coordinates recorded in `validate.py`: native V2.1 recovered geometry and style for 16/16; raster V2.1 for 14/16. V1 recovered geometry for 15/16 but has no separate style-family output.
- Page 4 has **31 native candidates: 27 dashed runs and 4 dash-double-dot boundary runs**. Counts are not accuracy scores. The native and raster modalities differ, and only V2 excludes the title block.

The v2.1 fix recovers the upper TI00203 line plus the short PI00201, PI00202 and PI00206 corners on page 4. All 27 previous page-4 candidates retain their geometry and style. The former native detector recovered 12/16 of the expanded reference set.

These checks are not whole-sheet precision/recall and do not establish better downstream AI comprehension. Isolated runs with fewer than three strokes, curved paths, symbol-occluded lines, native outline text, dense hatching and low-resolution scans remain limitations. Genuine corners are retained as separate straight spans; this version does not stitch routes. Explicit PDF dash-array phase across multi-item polylines is approximate. No OCR or symbol detector is included.

## Files and commands

- `engine.py`: detector, metadata and command-line exports.
- `server.py`, `static/`: local review UI.
- `baseline_v1.py`: unchanged copy of your original script; the Desktop original is untouched.
The following outputs are generated locally and are not committed:

- `outputs/page4/`: ready-made original/normalized images, masks and JSON.
- `outputs/native/`, `outputs/raster/`, `outputs/v1/`: per-page JSON for all 12 pages.
- `outputs/validation.json`: exact validation scope and results.

```sh
.venv/bin/python engine.py --page 4 --out outputs/page4
.venv/bin/python engine.py path/to/drawing.pdf --page 1 --mode raster --out outputs/custom
.venv/bin/python -m pytest -q
.venv/bin/python validate.py
```

The Desktop installation has a Python 3.12 runtime in `.venv`. For a fresh clone or new machine:

```sh
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r requirements.txt
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/python server.py --open
```

PyMuPDF currently emits upstream SWIG deprecation warnings during tests; they do not cause failures. Keep the supplied engineering drawing local unless you have permission to distribute it.
