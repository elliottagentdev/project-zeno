# Rubric Evaluation: Draft Plans 1-4

## Score Table

### Draft Plan 1: Minimal Surgery Fix

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Requirements Coverage | 4 | All acceptance criteria mapped with traceability table. However, the dual-map issue (AC: layer order on single map) is only partially addressed -- the plan fixes layer order within `render_dataset_map` but does not address the fact that `render_aoi_map` and `render_dataset_map` produce two separate maps. |
| Implementability | 5 | Exact file paths, line numbers, before/after code blocks, step-by-step order. A developer could implement this with zero questions. |
| Codebase Consistency | 5 | Reuses `ZenoClient.fetch_geometry()` pattern from `render_aoi_map()`, follows existing error handling patterns (try/except with fallback), uses existing imports. No new files, no new abstractions. |
| Completeness | 3 | Error handling and rollback addressed. Testing strategy is thin -- relies primarily on manual verification with one optional unit test. No frontend test infrastructure proposed. The tile content verification test (checking PNG size > 1000) is brittle. |
| Feasibility | 4 | All changes verified against actual codebase from recon. One concern: the plan assumes zoom level 5 will always show TCL pixels, but does not validate this assumption empirically. |
| Risk Identification | 3 | Identifies zoom-level root cause clearly and distinguishes it from the `render_type` secondary concern. However, does not identify the dual-map rendering risk, the session state persistence issue for AOI data across stream updates, or the performance cost of the extra geometry fetch. |

**Total: 24/30**

### Draft Plan 2: Clean Architecture Lens

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Requirements Coverage | 5 | Every acceptance criterion is mapped. Explicitly addresses the dual-map problem with `render_unified_map()`. Layer order requirement is directly fulfilled by the unified renderer. Subregion rendering is also covered. |
| Implementability | 4 | Good detail with full code blocks for all changes. However, the `TileURLBuilder` strategy pattern introduces complexity that is tangential to the actual bug fix. The plan acknowledges the refactor is not needed for the fix itself but proposes it anyway. Some ambiguity around import management when removing the if/elif chain. |
| Codebase Consistency | 3 | The `TileURLBuilder` strategy pattern introduces a new architectural pattern (abstract base class hierarchy) that does not exist elsewhere in the codebase for similar concerns. The existing `DataSourceHandler` strategy pattern in `data_handlers/` is for data pulling, not URL construction. Creating a new strategy pattern for a ~30-line if/elif chain is over-engineering. The `render_unified_map` function duplicates much of `render_dataset_map`. |
| Completeness | 5 | Comprehensive testing strategy with dedicated test file for TileURLBuilder, regression tests for other datasets, manual test plan, and migration plan with phased rollout. Error handling addressed at every layer. Backward compatibility preserved by keeping old functions. |
| Feasibility | 4 | Code is concrete and verified against recon. The lazy import in `get_url_builder()` correctly handles the circular import risk. The unified map function is feasible but introduces scope creep. |
| Risk Identification | 5 | Excellent risk register with severity, likelihood, and specific mitigations. Identifies circular import risk, latency concern, CORS non-issue, and the `render_type` investigation need. |

**Total: 26/30**

### Draft Plan 3: Robustness-First Lens

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Requirements Coverage | 5 | All acceptance criteria addressed. Identifies and catalogs 6 distinct failure modes, each mapped to specific detection, handling, and test coverage. The dual-map issue is identified explicitly (Failure Mode 6). |
| Implementability | 4 | Good detail with code blocks for all phases. However, the session state persistence approach (Change 2b) introduces complexity around thread-scoped keys that could be error-prone. The edge case about thread switching (Edge Case 4) is valid but the proposed mitigation adds complexity. |
| Codebase Consistency | 4 | Follows existing patterns (try/except, `get_logger`, structlog). The session state approach using `st.session_state` is consistent with Streamlit patterns. Year clamping with explicit constants is a clean improvement. However, proposing new test directories (`tests/frontend/`) breaks from the existing test structure (all frontend tests would be new). |
| Completeness | 5 | The most thorough testing strategy of all drafts: 16 named tests across 5 test suites covering geometry resolution, tile URL construction, regression, integration smoke tests, and render_stream integration. Edge cases cataloged (concurrent sessions, large AOI geometry, thread switching). Rollback plan with per-change revert instructions. |
| Feasibility | 4 | All changes verified against recon. The session state persistence for AOI data is a real need (since AOI and dataset updates arrive in separate stream events), and this plan is the only one to identify this timing issue. The year clamping logic is sound. Minor concern: the plan proposes `tests/frontend/` directory but no existing frontend tests exist, so the test infrastructure may need setup. |
| Risk Identification | 4 | Good identification of failure modes as implicit risks. Edge cases are well-cataloged. However, risks are described as failure modes rather than forward-looking risks with mitigations. The `render_type` investigation (Edge Case 5) is noted but not given a concrete mitigation beyond "check GFW docs." |

**Total: 26/30**

### Draft Plan 4: Developer Experience Lens

| Dimension | Score | Justification |
|-----------|-------|---------------|
| Requirements Coverage | 4 | All primary acceptance criteria addressed. However, the plan explicitly chooses NOT to address the dual-map issue, arguing it is "intentional UX." This partially contradicts the acceptance criterion requiring "basemap -> dataset tiles -> AOI outline" on a single map. The plan instead ensures the dataset map has the AOI overlay, which is a pragmatic but incomplete interpretation. |
| Implementability | 5 | Exceptionally clear. Every change has "current code" and "new code" blocks with line numbers. The self-correction about wrapping `aoi_geometry` in `{"geometry": aoi_geometry}` shows the author actually traced through the code. Implementation order is explicit and each step is independently verifiable. |
| Codebase Consistency | 5 | The strongest on this dimension. Zero new files, zero new abstractions. Reuses exact existing patterns. The `{"geometry": aoi_geometry}` wrapper preserves the existing `render_dataset_map` interface unchanged. Explicitly explains why it does NOT refactor the if/elif chain or add new abstractions. |
| Completeness | 3 | Testing strategy leans heavily on manual verification. The one proposed unit test is trivial (testing dict.get behavior, not actual rendering). No new test infrastructure. Error handling follows existing patterns but does not add logging for the new geometry fetch path. Does not address the session state issue for AOI data persistence across stream updates. |
| Feasibility | 5 | Every change is minimal, concrete, and verified against the actual codebase. The plan explicitly lists what it does NOT do and why, showing deep understanding of scope. The geometry fetch approach is identical to the existing `render_aoi_map` pattern. |
| Risk Identification | 3 | Identifies three risks with likelihood and impact. However, the "two separate maps" risk is acknowledged as "by design" rather than treated as a concern to address. Does not identify the session state timing issue (AOI and dataset arriving in separate updates). |

**Total: 25/30**

---

## Comparative Ranking

| Rank | Draft | Total | Strongest Dimensions |
|------|-------|-------|---------------------|
| 1 (tie) | Draft 2 (Clean Architecture) | 26/30 | Requirements Coverage, Completeness, Risk Identification |
| 1 (tie) | Draft 3 (Robustness-First) | 26/30 | Requirements Coverage, Completeness, Feasibility |
| 3 | Draft 4 (Developer Experience) | 25/30 | Implementability, Codebase Consistency, Feasibility |
| 4 | Draft 1 (Minimal Surgery) | 24/30 | Implementability, Codebase Consistency |

**Draft 2 and Draft 3 tie at 26/30** but for different reasons. Draft 2 excels at risk identification and provides a comprehensive architectural vision. Draft 3 excels at failure mode cataloging and testing strategy depth. Both lose points on codebase consistency (Draft 2 for over-engineering, Draft 3 for proposing new test directories without precedent).

**Draft 4 at 25/30** is the most pragmatic and developer-friendly. Its weakness is testing strategy and incomplete treatment of the dual-map requirement.

**Draft 1 at 24/30** is the simplest and most codebase-consistent but falls short on testing and risk identification.

---

## Strengths to Preserve

### From Draft 1 (Minimal Surgery):
- **The geometry fetch pattern in `render_dataset_map()`** -- the cleanest implementation of the core fix. The code mirrors `render_aoi_map()` exactly and avoids changing function signatures.
- **Single-file scope** -- the fix correctly identifies that only `frontend/utils.py` needs changes. No backend changes required.
- **Acceptance criteria traceability table** -- clear mapping from each criterion to how it is addressed.

### From Draft 2 (Clean Architecture):
- **`render_unified_map()` concept** -- the only plan that fully addresses the dual-map issue by creating a single map with correct layer ordering. The synthesizer should adopt this for the case when both AOI and dataset are available.
- **Risk register format** -- severity, likelihood, and specific mitigation for each risk. Best risk documentation of all drafts.
- **Phased migration plan** -- each phase independently deployable and verifiable.
- **Comprehensive TileURLBuilder tests** -- the test structure (even if the strategy pattern itself is over-engineering) provides a template for thorough URL construction testing.

### From Draft 3 (Robustness-First):
- **Failure mode catalog** -- the 6 failure modes are the most thorough analysis of what can go wrong. The synthesizer should preserve this as documentation.
- **Session state persistence for AOI data** (Change 2b) -- this is the ONLY plan that identifies and solves the timing issue where AOI and dataset arrive in separate stream updates. Critical insight.
- **Year range clamping with constants** -- `TCL_TILE_MIN_YEAR`, `TCL_TILE_MAX_YEAR`, `TCL_TILE_MAX_START_YEAR` constants with double-clamp logic and inverted range check. More robust than the current implementation.
- **16 named test cases across 5 suites** -- the most comprehensive testing strategy.
- **Thread-scoped session state key** -- identifies the edge case of thread switching causing stale AOI data.

### From Draft 4 (Developer Experience):
- **`{"geometry": aoi_geometry}` wrapper approach** -- the insight that geometry should be fetched in `render_stream()` and wrapped to match `render_dataset_map`'s expected interface without changing the function signature. Minimizes blast radius.
- **"What This Plan Does NOT Do" section** -- explicitly scoping out non-goals with reasoning. The synthesizer should include this.
- **Implementation order** -- each change independently verifiable before moving to the next. Good engineering practice.
- **Self-correcting analysis** -- the plan shows the author traced through the code and caught the interface mismatch, demonstrating deep code understanding.

---

## Weaknesses to Avoid

### From Draft 1:
- **Thin testing strategy** -- relies primarily on manual verification. The proposed tile content size test (`len(response.content) > 1000`) is brittle and environment-dependent. The synthesizer must include more robust automated tests.
- **Ignores the dual-map issue** -- does not address that `render_aoi_map` and `render_dataset_map` produce two separate HTML maps. The acceptance criterion explicitly requires single-map layer ordering.
- **No session state awareness** -- does not consider that AOI and dataset updates may arrive in separate stream events.

### From Draft 2:
- **Over-engineering the TileURLBuilder** -- creating an abstract base class hierarchy with 4 concrete implementations plus a registry function for a 30-line if/elif chain is not justified by the bug being fixed. This adds 2 new files and significant complexity. The synthesizer must NOT adopt this refactor.
- **`render_unified_map()` is too large** -- the proposed function is ~80 lines and duplicates much of `render_dataset_map`. The synthesizer should modify the existing function rather than creating a parallel one.
- **Circular import concern** -- introducing `tile_url.py` that imports from `analytics_handler.py` which imports from `datasets_config.py` creates a new dependency chain. The lazy import workaround is a code smell.

### From Draft 3:
- **Scope creep on year validation** -- while the year clamping improvement is sound, it is a P1 change mixed with the P0 bug fix. The synthesizer should separate these into distinct commits or clearly mark them as secondary.
- **New test directory (`tests/frontend/`)** -- no existing frontend tests exist. Creating this infrastructure is good but should be acknowledged as new ground, not assumed.
- **Verbose failure mode analysis** -- while thorough, some failure modes (FM3, FM4, FM5) are secondary issues that dilute focus on the primary root cause. The synthesizer should prioritize clearly.

### From Draft 4:
- **Does not address dual-map requirement** -- explicitly chooses not to merge the two maps, arguing it is "intentional UX." This contradicts the acceptance criterion. The synthesizer must address this.
- **Trivial unit test** -- the proposed test (`test_render_dataset_map_uses_dataset_name`) tests Python dict.get behavior, not actual rendering logic. The synthesizer needs meaningful tests.
- **No AOI persistence across updates** -- does not solve the timing issue where `aoi_data` is `None` when the dataset update arrives because it was in a previous stream event.
- **Extra geometry fetch without caching** -- acknowledges the duplicate `fetch_geometry()` call adds latency but defers caching as an optimization. The synthesizer should at least use session state.

---

## Gap Analysis: Requirements Not Adequately Addressed by ANY Draft

### 1. Verification that `render_type=true_color` Produces Visible Pixels
All four drafts acknowledge this as a secondary concern but none provide a concrete verification step. The recon documents note that DIST-ALERT uses the same `render_type` and works, but no draft actually fetches a TCL tile at zoom 5+ and verifies pixel visibility. The synthesizer should include a concrete investigation step (e.g., curl a tile at z=6 and inspect the image) as part of the implementation, not just as an afterthought.

### 2. Dual-Map Rendering: Complete Solution
- Draft 1 ignores it
- Draft 2 proposes `render_unified_map()` but creates scope creep
- Draft 3 identifies it (FM6) but the fix (Change 2a: skip AOI map when dataset present) has a timing issue -- AOI and dataset usually arrive in SEPARATE updates, not the same one
- Draft 4 explicitly opts out

No draft fully solves the dual-map problem for the typical case where AOI arrives first in one update and dataset arrives later in a separate update. The synthesizer must address this: either accept two maps as the UX pattern (AOI preview, then dataset+AOI map) or implement a mechanism to replace the AOI map when the dataset map renders.

### 3. Performance Impact of Duplicate Geometry Fetch
`fetch_geometry()` will be called twice -- once in `render_aoi_map()` and again in `render_dataset_map()`. Only Draft 3 partially addresses this via session state caching. The synthesizer should cache the geometry in `st.session_state` after the first fetch.

### 4. Automated Regression Testing for All Dataset Types
No draft provides a comprehensive automated regression test that verifies ALL dataset types (DIST-ALERT, Grasslands, Land Cover Change, TCL, Tree Cover Loss by Driver) continue to render correctly after the fix. The existing `test_tile_url_contains_date` covers URL construction but not frontend rendering. The synthesizer should at minimum propose parametrized tests that verify the geometry-fetch + map-centering behavior for each dataset type.

### 5. Root Cause Documentation for PR
The acceptance criteria require "Root cause is documented in the PR so other GFW-sourced datasets can be checked against the same failure mode." No draft provides a template or outline for this PR documentation. The synthesizer should include a PR description template that explains the root cause (missing AOI geometry -> global zoom -> invisible fine-resolution tiles) in a way that applies to any future GFW-sourced dataset.
