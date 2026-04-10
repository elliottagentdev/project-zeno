# Draft Plan Evaluation

## Score Table

### Draft 1: Minimal Surgery Fix

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Requirements Coverage | 4 | All acceptance criteria mapped to specific changes. Light basemap, Satellite continuation, no API keys, layer ordering, and AOI-on-top are all addressed. Minor gap: no explicit acceptance test for "running any query renders a visible geographic basemap by default" -- relies on manual verification only. |
| Implementability | 5 | Exact file paths, exact line numbers, before/after code blocks, precise insertion points. A developer can follow this with zero questions. |
| Codebase Consistency | 4 | Uses underscore-prefix private helper (matches convention), UPPER_SNAKE_CASE constants, and stays within the single-file modification pattern. Uses separate constants per provider (CARTO_LIGHT_TILES, CARTO_DARK_TILES, etc.) rather than a unified config structure -- slightly less idiomatic but not inconsistent. |
| Completeness | 3 | Happy path well-covered. Error handling section explicitly states "no changes" and defers to existing try/except blocks. Testing strategy is manual-first with an optional smoke test. No discussion of `tiles=None` compatibility across folium versions. No discussion of `overlay=False` vs default behavior for basemap TileLayers. |
| Feasibility | 5 | Every step verified against actual codebase. File paths, line numbers, and existing code snippets match the recon documents. CartoDB and ESRI tile URLs are well-known free providers. |
| Risk Identification | 2 | Rollback mentioned briefly ("revert the single file change"). No discussion of risks like: tiles=None behavior across folium versions, CartoDB/ESRI availability, overlay=False interaction with LayerControl, or retina display handling. |

**Total: 23/30**

### Draft 2: Clean Architecture Approach

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Requirements Coverage | 5 | Every requirement from the issue maps to a specific section. Layer ordering contract explicitly documented. Acceptance criteria for Light basemap, Satellite, no API keys, AOI-on-top, and layer order all have corresponding code changes and verification steps. |
| Implementability | 5 | Exact file paths, line numbers, before/after code blocks, function signatures with docstrings. Step-by-step order is clear. The `_create_base_map` factory function signature and return type are specified. |
| Codebase Consistency | 5 | Uses list-of-dicts config pattern (simple, Pythonic). Private helper with underscore prefix. Uses `folium.raster_layers.TileLayer` (matches existing code in `render_dataset_map`). UPPER_SNAKE_CASE for the config constant. Docstrings on new functions. Follows Ruff double-quote convention. |
| Completeness | 4 | Error handling addressed (multiple providers as fallback strategy). Testing strategy includes both unit tests and manual checklist. Rollback plan documented. Migration plan documented. Missing: no discussion of `tiles=None` compatibility across folium versions. The `overlay=False` + `show=True/False` interaction is explained but not validated against the actual folium version in use. |
| Feasibility | 5 | All code changes verified against recon. The `overlay=False` and `show` parameters are standard folium TileLayer API. Test imports (`from frontend.utils import ...`) would need PYTHONPATH adjustment but this is a minor detail. |
| Risk Identification | 3 | Section 9 ("Why This Design Over Inline Fixes") identifies maintainability risks of alternative approaches. Rollback section mentions swapping CartoDB URLs. But no systematic risk enumeration -- no discussion of folium version compatibility, tile provider SLA, or LayerControl interaction edge cases. |

**Total: 27/30**

### Draft 3: Robustness-First Implementation

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Requirements Coverage | 4 | All acceptance criteria addressed. However, only includes Light and Satellite basemaps (no Dark option), which partially conflicts with the issue's mention of "Light/Dark/Satellite" in the context. The PROMPT.md acceptance criteria only require Light and Satellite, so this is defensible but less complete than other drafts. |
| Implementability | 4 | File paths and line numbers provided. Before/after code blocks are clear. However, some sections (like 4.1 edge case on tiles=None) present alternatives without committing to a single approach, which could cause implementer hesitation. |
| Codebase Consistency | 5 | Uses `folium.raster_layers.TileLayer` (matches existing code). UPPER_SNAKE_CASE constants. Private helper with underscore prefix. Config dict keys include `overlay` and `control` which map directly to folium kwargs -- clean pattern. Ruff compliance checklist explicitly included. |
| Completeness | 5 | Outstanding edge case coverage: tiles=None across folium versions, both providers down, show=True on multiple basemaps, dataset tiles obscured by basemap, retina/HiDPI displays. Failure mode analysis table (Section 1) is thorough. Testing includes manual protocol table with numbered test cases. Rollback and migration documented. |
| Feasibility | 4 | Generally feasible. The edge case discussion of tiles=None compatibility mentions checking uv.lock but does not actually report what folium version is resolved. The fallback suggestion of `tiles=""` is unverified. |
| Risk Identification | 5 | Comprehensive risk tables for both current failure modes (F1-F5) and proposed fix risks (R1-R7). Each risk has a specific mitigation. This is the strongest risk analysis across all drafts. |

**Total: 27/30**

### Draft 4: Developer Experience Lens

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Requirements Coverage | 4 | All acceptance criteria addressed with specific code changes. Layer ordering verified in a dedicated section. Includes Light, Dark, and Satellite basemaps. Minor gap: no explicit mapping from each acceptance criterion to a verification step. |
| Implementability | 5 | Excellent detail. Exact line numbers, before/after code, insertion points. The `show=(i == 0)` pattern for default selection is concise and well-explained. The "What NOT to Change" section (Section 5) is valuable for preventing scope creep. |
| Codebase Consistency | 5 | Follows all project conventions. The extensive comment block above BASEMAP_CONFIGS explaining "why explicit URLs" is appropriate for this codebase. Uses `folium.TileLayer` (shorthand, but equivalent to `folium.raster_layers.TileLayer`). UPPER_SNAKE_CASE constant. Private helper with underscore prefix. |
| Completeness | 3 | Error handling section is brief -- just notes that Leaflet shows gray placeholders. Testing is manual-first with an optional unit test. No discussion of edge cases like tiles=None compatibility, retina displays, or provider outages. No discussion of what happens if BASEMAP_CONFIGS is empty. |
| Feasibility | 5 | All changes verified against the actual codebase. The design is straightforward and uses well-known folium APIs. The "first entry is default" convention via `show=(i == 0)` is elegant and standard. |
| Risk Identification | 2 | Rollback mentioned (edit BASEMAP_CONFIGS to swap URLs). Dependency considerations note free tier and no API keys. But no systematic risk analysis. No discussion of failure modes, edge cases, or what happens if the fix introduces new problems. |

**Total: 24/30**

---

## Comparative Ranking

| Rank | Draft | Score | Strongest Dimensions |
|------|-------|-------|---------------------|
| 1 (tie) | Draft 2: Clean Architecture | 27/30 | Requirements Coverage (5), Implementability (5), Codebase Consistency (5), Feasibility (5) |
| 1 (tie) | Draft 3: Robustness-First | 27/30 | Completeness (5), Risk Identification (5), Codebase Consistency (5) |
| 3 | Draft 4: Developer Experience | 24/30 | Implementability (5), Codebase Consistency (5), Feasibility (5) |
| 4 | Draft 1: Minimal Surgery | 23/30 | Implementability (5), Feasibility (5) |

Drafts 2 and 3 tie at 27/30 but excel in different areas. Draft 2 is the most well-rounded and implementable plan. Draft 3 has the best risk analysis and edge case coverage. The synthesized plan should combine Draft 2's clean architecture with Draft 3's robustness analysis.

---

## Strengths to Preserve

### From Draft 1 (Minimal Surgery)
- **Separate named constants per tile provider** (CARTO_LIGHT_TILES, CARTO_DARK_TILES, etc.) -- while less extensible than a list-of-dicts, the explicit naming makes grep/search easier. The synthesizer should consider whether to use named constants OR a config list, but not both.

### From Draft 2 (Clean Architecture)
- **`_create_base_map(center, zoom_start)` factory function** that returns a fully-configured `folium.Map`. This is cleaner than the `_add_basemap_layers(m)` helper used by other drafts because it encapsulates the `tiles=None` + basemap setup in one call, reducing the chance of forgetting to call the helper.
- **`overlay=False` and `show=True/False` explanation** -- clearly documents the critical distinction between base layers (radio buttons) and overlay layers (checkboxes) in LayerControl.
- **Comprehensive unit tests** with good coverage: config validation (required keys, exactly one default), factory output validation (correct type, correct tile URLs in HTML), and negative test (no OpenStreetMap tiles).

### From Draft 3 (Robustness-First)
- **Failure mode analysis table** (Section 1.1 and 1.2) -- enumerates current failures (F1-F5) and proposed fix risks (R1-R7) with mitigations. This should be included in the final spec as a reference.
- **Edge case analysis** (Section 4) -- tiles=None compatibility, both providers down, show=True on multiple basemaps, dataset tiles z-order, retina/HiDPI. The synthesizer should incorporate these validations.
- **Ruff compliance checklist** -- explicit reminder to verify linting compliance.

### From Draft 4 (Developer Experience)
- **Extensive inline comment block** above BASEMAP_CONFIGS explaining the "why" (folium built-in shortcuts are unreliable). This is valuable documentation for future developers.
- **"What NOT to Change" section** -- explicitly scopes the work and prevents scope creep. The synthesizer should include this.
- **`show=(i == 0)` pattern** for default basemap selection -- more elegant than a `default: True` flag in config dicts because it automatically makes the first entry the default without needing an extra key.

---

## Weaknesses to Avoid

### From Draft 1
- **No risk analysis.** The plan mentions rollback in one sentence but does not enumerate failure modes or edge cases. The synthesizer must not ship a plan without risk identification.
- **Separate constants per provider** (6 constants for 3 providers) creates more surface area for errors than a single config list. The synthesizer should use the list-of-dicts pattern from Drafts 2-4.

### From Draft 2
- **`default` key in config dicts** is redundant with the list ordering convention (first = default). This adds a key that must be kept in sync with the list order. The synthesizer should use either position-based default (Draft 4's `show=(i == 0)`) or the explicit flag, but not leave ambiguity.

### From Draft 3
- **Only two basemaps (Light and Satellite)** -- omits Dark. While the acceptance criteria technically only require Light and Satellite, the issue context mentions "Light/Dark/Satellite" and all other drafts include Dark. The synthesizer should include all three basemaps.
- **Hedging on tiles=None** -- presents three alternatives (tiles=None, tiles="", tiles="OpenStreetMap" with duplicate) without committing. The synthesizer must pick one approach and commit to it.

### From Draft 4
- **Weak error handling and risk sections.** For a "Developer Experience" lens, the plan underinvests in documenting failure modes. A good DX includes understanding what can go wrong.
- **No new test files created** in the summary table (Section 9 says "No files created or deleted") even though Section 7.3 proposes an optional test file. The synthesizer should commit to including tests, not make them optional.

---

## Gap Analysis

Requirements or concerns not adequately addressed by ANY draft:

1. **Folium version verification.** All drafts note that folium is a transitive dependency and `tiles=None` behavior may vary, but none actually check what folium version is resolved in `uv.lock`. The synthesizer should verify this or add a note to check during implementation.

2. **ESRI World Imagery usage terms.** Draft 4 mentions "free for non-commercial use" but the project may be used commercially (it is a WRI production tool). None of the drafts verify whether ESRI World Imagery terms permit this use case. The synthesizer should note this as a risk and suggest OpenStreetMap-based satellite alternatives if needed.

3. **`frontend/index.html` consistency.** All drafts correctly note that `frontend/index.html` is out of scope, but none discuss whether the standalone Leaflet client should also be updated for consistency. The synthesizer should explicitly scope this out with a rationale.

4. **Performance impact of loading three tile providers.** None of the drafts discuss whether adding three TileLayer objects (even with `show=False` on two) causes Leaflet to prefetch tiles from all providers or only the visible one. Draft 3 briefly mentions "only the default basemap tiles are loaded on init" but does not verify this claim against Leaflet's actual behavior.

5. **Tests are optional or minimal in all drafts.** While the project has no frontend tests, all four drafts treat automated testing as optional. Given that this is a bug fix (regression risk is real), the synthesizer should make the unit tests for basemap configuration and helper function a required part of the deliverable, not optional.

6. **`folium.TileLayer` vs `folium.raster_layers.TileLayer`.** Drafts use both forms interchangeably. These are the same class (`folium.TileLayer` is an alias), but the existing code in `render_dataset_map` uses `folium.raster_layers.TileLayer`. The synthesizer should use the same form as the existing code for consistency.
