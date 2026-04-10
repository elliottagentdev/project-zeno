# Validation Report: Fix Basemap Layer Ordering Plan

## 1. Requirements Coverage Matrix

| # | Requirement (from PROMPT.md) | Addressed in Plan? | Where in Plan | Testable? | Notes |
|---|---|---|---|---|---|
| R1 | Opening basemap selector popover does not mask/cover AOI polygon overlays | YES | "Chosen Approach: Approach B" section; removing `key` prevents remount that causes layer reordering | YES (Manual Test Cases 1-4) | Acceptance criteria is testable but only via manual testing |
| R2 | Opening basemap selector popover does not mask/cover dynamic tile layers (e.g. tree cover loss) | YES | Same section; preserving layer stack order keeps DynamicTileLayers above basemap | YES (Manual Test Cases 1-4) | Same approach addresses both R1 and R2 |
| R3 | Popover still opens, positions correctly, and allows basemap switching | YES | "No Changes Needed to Other Files" section confirms BasemapSelector.tsx is unchanged | YES (Manual Test Cases 1-7) | Implicit -- no changes to popover code means behavior preserved |
| R4 | Both desktop and mobile layouts are unaffected | PARTIALLY | Manual Test Case 7 covers mobile, but only basemap switching. No explicit desktop layout regression test. | WEAK | Test plan says "same correct behavior, popover still usable" but does not specify what to check for desktop layout specifically |
| R5 (Constraint) | Fix must not break popover positioning or usability | YES | Plan modifies only the `<Source>` element, not the popover | YES | Covered by not touching BasemapSelector.tsx |
| R6 (Constraint) | Do not remove the basemap selector feature | YES | Plan preserves all basemap switching functionality | YES | Trivially satisfied |
| R7 (Context) | Fix should ensure basemap Layer is always positioned below all other layers when switching basemaps | YES | Core of the plan -- removing `key` prevents remount/reinsertion at top of stack | YES | The plan's primary mechanism |
| R8 (Context) | Do NOT use `<Portal>` | YES | Plan explicitly does not use Portal | YES | Plan uses Approach B (remove key), not Portal |

**Coverage Summary**: All requirements are addressed. R4 (desktop/mobile) has weak acceptance criteria -- "unaffected" is vague for desktop since the plan does not describe what desktop-specific behaviors to verify beyond basemap switching.

---

## 2. Codebase Fact-Check

### 2.1 File Existence Verification

| Claim in Plan | Actual Status | Verdict |
|---|---|---|
| `/mnt/e/agentdev/projects/project-zeno-next/app/components/Map.tsx` exists | EXISTS | CORRECT |
| `BasemapSelector.tsx` at `app/components/map/BasemapSelector.tsx` | EXISTS | CORRECT |
| `MapAreaControls.tsx` at `app/components/MapAreaControls.tsx` | EXISTS | CORRECT |
| `DynamicTileLayers.tsx` at `app/components/map/layers/DynamicTileLayers.tsx` | EXISTS | CORRECT |
| `HighlightedFeaturesLayer.tsx` at `app/components/map/layers/HighlightedFeaturesLayer.tsx` | EXISTS | CORRECT |
| `mapStore.ts` at `app/store/mapStore.ts` | EXISTS | CORRECT |

### 2.2 Code Structure Claims

| Claim | Actual | Verdict |
|---|---|---|
| `Map.tsx` lines 126-134 contain `<Source key={basemapTiles}>` | Lines 126-134 contain exactly that code with `key={basemapTiles}`, `id="background"`, `type="raster"`, `tiles={[basemapTiles]}`, `tileSize={512}`, and `<Layer id="background-tiles" type="raster" />` | CORRECT |
| `basemapTiles` is local state in Map.tsx (line 39-41) | Lines 39-41: `const [basemapTiles, setBasemapTiles] = useState("https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png")` | CORRECT |
| Plan says `basemapTiles` state is "not in the store" | Confirmed -- `basemapTiles` is `useState` in Map.tsx, not in mapStore.ts | CORRECT |
| Plan says BasemapSelector calls `onBasemapChange(option.tileUrl)` | Line 111 of BasemapSelector.tsx: `onClick={() => onBasemapChange(option.tileUrl)}` | CORRECT |
| Plan says DynamicTileLayers uses layer IDs `tile-layer-{tileLayer.id}` | Line 18: `id={\`tile-layer-${tileLayer.id}\`}` | CORRECT |
| Plan says HighlightedFeaturesLayer uses IDs `geojson-fill-{feature.id}` | Line 137: `const fillLayerId = \`geojson-fill-${feature.id}\`` | CORRECT |
| Plan says MapAreaControls passes `basemapTiles` and `setBasemapTiles` as props | Lines 64-65 of MapAreaControls.tsx confirm props are destructured; lines 170-171 pass them to BasemapSelector | CORRECT |
| Plan lists 3 basemap options: Light, Satellite, Dark | BasemapSelector.tsx lines 19-40 confirm exactly these 3 options with matching URLs | CORRECT |

### 2.3 react-map-gl Version and Behavior Claims

| Claim | Actual | Verdict |
|---|---|---|
| Plan says `react-map-gl@^8.0.4` | package.json line 42: `"react-map-gl": "^8.0.4"` | CORRECT |
| Plan says react-map-gl `<Source>` handles prop changes via `_updateSource` method | This is an internal implementation detail. The plan acknowledges uncertainty about exact behavior in the "Important nuance" paragraph and Edge Case 1. | UNVERIFIABLE but plan handles the uncertainty appropriately |
| Plan says removing `key` will cause react-map-gl to call `map.getSource("background").setTiles([newUrl])` | This is speculative. The plan itself admits (line 98-101) that react-map-gl may internally remove/re-add the source. The `setTiles` method exists on MapLibre GL raster sources but react-map-gl's Source component may not use it. | UNCERTAIN -- plan correctly flags this as a risk |

### 2.4 Recon Document Contradictions

**CRITICAL FINDING**: The `relevant_code.md` recon document describes a completely different codebase (Python/Streamlit/Folium) than what actually exists. It states: "The PROMPT.md references `app/components/map/BasemapSelector.tsx`, `MapLibre GL`, `HighlightedFeaturesLayer`, and `DynamicTileLayers` -- **none of these exist in the actual codebase**."

This is WRONG. All referenced React/TypeScript files exist in `project-zeno-next`. The `relevant_code.md` was exploring the wrong repository (`project-zeno` -- the Python backend) instead of `project-zeno-next` (the Next.js frontend).

**Impact on draft plan**: The draft plan was NOT misled by `relevant_code.md`. It correctly references the React/Next.js codebase in `project-zeno-next` and all its file paths and code references are accurate. The plan drafter appears to have relied primarily on `architecture.md` and `conventions.md` (which correctly describe the Next.js codebase) and independently verified file contents.

---

## 3. Ambiguity Audit

### 3.1 Section: "Chosen Approach: Approach B"

**Ambiguity 1**: The plan states removing `key` will cause react-map-gl to update tiles "in-place" but then admits (Important nuance, lines 98-101) this may not work. The plan does not specify **how to determine** whether the in-place update worked vs. the fallback is needed. A developer would need to:
- Know to open browser dev tools
- Inspect the MapLibre layer stack order
- Or visually observe the layer ordering

**Missing information**: Specific debugging steps to determine if Edge Case 1 is occurring (e.g., `map.getStyle().layers.map(l => l.id)` in console to inspect layer order).

**Ambiguity 2**: The plan says the fallback `useEffect` with `map.moveLayer()` "should only be used if the primary fix does not work." It is unclear whether the implementer should:
- (a) Try the primary fix, manually test, and only add the fallback if it fails
- (b) Implement both the primary fix AND the fallback as a safety net

The plan implies (a) but does not make it explicit.

### 3.2 Section: "react-map-gl Source Update Behavior"

**Ambiguity 3**: The plan describes two contradictory behaviors of react-map-gl:
1. Line 95-96: "it removes the old source and adds a new one with the updated tiles, BUT it preserves all associated layers and their ordering"
2. Line 101-102: "If react-map-gl does internally remove/re-add the source when tiles change, the layers would still end up on top"

These statements contradict each other. Statement 1 claims ordering is preserved even with remove/re-add. Statement 2 says it would not be. A developer reading both would be confused about the expected behavior.

### 3.3 Section: "Testing Strategy"

**Ambiguity 4**: The test plan requires "at least one AOI polygon visible" and "at least one dataset tile layer visible" as preconditions but does not specify HOW to create these conditions. A developer unfamiliar with the app would need to know:
- How to create an AOI (chat interaction? drawing? upload?)
- How to enable a dataset tile layer (which dataset? how?)

### 3.4 Section: "Implementation Order"

**Ambiguity 5**: Step 4 says "If Edge Case 1 manifests... implement the useEffect + moveLayer fallback." It is unclear what happens to the primary fix in that case:
- Is the `key` prop added back?
- Is the `useEffect` added in ADDITION to removing `key`?
- Or does the `useEffect` REPLACE the key removal?

---

## 4. Edge Cases & Risks

### 4.1 Edge Cases NOT Handled

**EC1: DynamicTileLayers also use `key={tileLayer.id}` on their Source components**
`DynamicTileLayers.tsx` line 11: `<Source key={tileLayer.id} ...>`. If a tile layer is removed and re-added (e.g., toggling visibility or dataset changes), the same layer-ordering issue could occur for dynamic tile layers relative to each other and relative to HighlightedFeaturesLayer. The plan only addresses the basemap layer ordering but does not consider whether the same `key` pattern in DynamicTileLayers causes similar issues.

**EC2: HighlightedFeaturesLayer also uses `key` on Sources**
`HighlightedFeaturesLayer.tsx` line 185: `<Source key={sourceId} ...>`. Same pattern as the basemap -- when features change, the Source remounts and layer ordering could be disrupted relative to other feature layers. Not addressed in the plan, but this is a pre-existing issue not introduced by this fix.

**EC3: What happens when `basemapTiles` is set to an invalid/unreachable URL?**
If a basemap tile provider goes down or the URL is malformed, the `<Source>` without a `key` prop will show stale/broken tiles. With the `key` prop, the Source would unmount/remount which might clear stale tiles. The plan does not address error handling for failed tile loads after the fix.

**EC4: Browser cache behavior when switching basemaps rapidly without `key`**
Without the `key` prop forcing a full remount, the browser may serve cached tiles from the previous basemap URL during the transition. The plan claims "MapLibre GL's tile cache is keyed by URL" (Risk Register row 2) but does not verify this experimentally.

### 4.2 Error Paths NOT Covered

**EP1: Map.tsx `onError` handler**
The plan does not discuss how the existing `onError` handler (Map.tsx line 123) interacts with Source/Layer errors that might occur when tiles change without a remount. If `setTiles` internally fails, what error propagation path exists?

**EP2: Source update during map initialization**
If `basemapTiles` state changes before the map has fully loaded (before `onLoad` fires), the Source update behavior could differ. The plan does not address this timing.

### 4.3 Internal Contradictions

**IC1**: The plan's "react-map-gl Source Update Behavior" section (lines 94-101) contradicts itself as noted in Ambiguity 3 above. The plan simultaneously claims that react-map-gl preserves layer ordering when removing/re-adding a source AND that removing/re-adding would put layers on top. Both cannot be true.

**IC2**: The plan says "This is the entire fix" (line 74) and "one-line code change" (Migration Plan), but then provides a multi-paragraph fallback implementation that may be needed. If the fallback IS needed, the fix is significantly more complex than "one line."

### 4.4 Security Concerns

None identified. This change is purely cosmetic/rendering and does not involve user input, authentication, or data exposure.

### 4.5 Risk Assessment for the Primary Fix

**Key risk**: The entire plan hinges on the assumption that `react-map-gl` v8's `<Source>` component will handle a `tiles` prop change on a raster source by updating the existing MapLibre source in-place without removing and re-adding associated layers. This behavior is not documented in react-map-gl's public API docs and is an implementation detail that could change between versions.

The plan appropriately identifies this risk (Edge Case 1, Risk Register row 1) and provides a fallback, but the fallback itself has issues:
1. The `sourcedata` event may fire multiple times or at unexpected times
2. `map.once("sourcedata", handler)` may not fire if the source update happens synchronously before the listener is attached
3. The cleanup `return () => map.off("sourcedata", handler)` uses `off` for a listener registered with `once` -- if the event already fired, `off` is a no-op (harmless but unclear intent)

---

## Summary of Critical Findings

1. **The `relevant_code.md` recon document describes the WRONG codebase** (Python/Folium instead of React/Next.js). The plan was NOT misled by this error, but it means the plan was written without the benefit of the relevant code recon.

2. **The plan's core mechanism (removing `key`) is sound in principle** but relies on unverified assumptions about `react-map-gl` internal behavior. The fallback mechanism has its own timing/reliability concerns.

3. **The plan contains internal contradictions** in its description of react-map-gl's Source update behavior.

4. **All file paths and code references in the plan are factually correct** against the actual codebase.

5. **Test plan lacks setup instructions** -- a developer unfamiliar with the app cannot execute the manual tests without knowing how to create AOI polygons and enable dataset tile layers.
