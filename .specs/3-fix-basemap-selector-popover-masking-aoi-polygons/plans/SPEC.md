# SPEC: Fix Basemap Selector Masking AOI Polygons and Dataset Tile Layers

## Issue Summary

When the user switches basemaps via the BasemapSelector popover, the basemap raster tiles render on top of AOI polygons and dataset tile layers, obscuring them. This is a MapLibre GL layer ordering bug caused by React forcing a Source component unmount/remount when the basemap URL changes.

## Root Cause (Confirmed)

In `/mnt/e/agentdev/projects/project-zeno-next/app/components/Map.tsx` (lines 126-134):

```tsx
<Source
  key={basemapTiles}          // Forces unmount/remount on basemap change
  id="background"
  type="raster"
  tiles={[basemapTiles]}
  tileSize={512}
>
  <Layer id="background-tiles" type="raster" />
</Source>
```

The `key={basemapTiles}` prop causes React to destroy and recreate the `<Source>` component whenever the tile URL changes. When MapLibre GL re-adds the `background-tiles` layer, it inserts it at the top of the layer stack, above `DynamicTileLayers` and `HighlightedFeaturesLayer`.

## Fix (Verified Against react-map-gl Source)

Remove the `key={basemapTiles}` prop. The react-map-gl v8 `<Source>` component handles `tiles` prop changes via `source.setTiles()` (confirmed at `node_modules/react-map-gl/src/mapbox-legacy/components/source.ts` line 71-72), which updates the tile URL in-place without removing or re-adding the source or its layers. Layer ordering is preserved.

---

## 1. Requirements Traceability Matrix

| # | Requirement | Spec Section | Status |
|---|-------------|-------------|--------|
| R1 | Opening basemap selector popover does not mask/cover AOI polygon overlays | Section 3, Step 1 | ADDRESSED -- removing `key` prevents layer reordering that causes masking |
| R2 | Opening basemap selector popover does not mask/cover dynamic tile layers (e.g. tree cover loss) | Section 3, Step 1 | ADDRESSED -- same fix preserves DynamicTileLayers ordering |
| R3 | Popover still opens, positions correctly, and allows basemap switching | Section 3 (no changes to BasemapSelector.tsx) | ADDRESSED -- popover code is untouched |
| R4 | Both desktop and mobile layouts are unaffected | Section 4, Test Cases 7-8 | ADDRESSED -- fix is render-layer only, no layout/CSS changes |
| R5 | Fix must not break popover positioning or usability (constraint) | Section 3 (no changes to popover) | ADDRESSED -- only Map.tsx Source element is modified |
| R6 | Do not remove the basemap selector feature (constraint) | Section 3 | ADDRESSED -- all basemap switching functionality preserved |
| R7 | Basemap Layer always positioned below all other layers when switching (context) | Section 3, Step 1 | ADDRESSED -- `setTiles()` updates in-place, layer stays at bottom |
| R8 | Do NOT use Portal (context) | Section 3 | ADDRESSED -- Portal is not used |

**Gaps**: None. All requirements are fully addressed.

---

## 2. Validation Resolution Log

| # | Finding | Resolution | Status |
|---|---------|-----------|--------|
| V1 | `relevant_code.md` recon describes wrong codebase (Python/Folium instead of React/Next.js) | No impact on spec -- all file paths and code references verified against actual Next.js codebase in `project-zeno-next`. The draft plan was not misled. | RESOLVED |
| V2 | Plan's description of react-map-gl Source update behavior contains internal contradiction (claims ordering preserved AND not preserved in remove/re-add scenario) | Resolved by reading react-map-gl source code directly. Lines 71-72 of `source.ts` confirm `source.setTiles()` is called when only `tiles` prop changes -- no remove/re-add occurs. The contradiction is moot. | RESOLVED |
| V3 | Ambiguity: unclear whether fallback `useEffect`+`moveLayer` should be implemented alongside or only if primary fix fails | Resolved: primary fix is confirmed correct via source code inspection. Fallback is NOT needed and should NOT be implemented. See Section 3. | RESOLVED |
| V4 | Ambiguity: test plan lacks setup instructions for creating AOI polygons and dataset tile layers | Resolved: Section 4 includes explicit setup steps. | RESOLVED |
| V5 | Ambiguity: no debugging steps to verify layer ordering | Resolved: Section 4 includes console debugging commands. | RESOLVED |
| V6 | Edge case: DynamicTileLayers also uses `key={tileLayer.id}` on Source components | DEFERRED. Severity: Low. The `key` in DynamicTileLayers is keyed on a stable `tileLayer.id` (not a changing URL), so it only remounts when a tile layer is added/removed from the store, not when properties change. This is correct React behavior for list rendering. Follow-up: monitor for layer ordering issues when adding/removing dataset layers. | DEFERRED |
| V7 | Edge case: HighlightedFeaturesLayer uses `key` on Sources | DEFERRED. Severity: Low. Same reasoning as V6 -- key is based on stable feature ID. Follow-up: monitor for ordering issues when features are added/removed. | DEFERRED |
| V8 | Edge case: invalid/unreachable basemap URL after fix | DEFERRED. Severity: Low. Likelihood: Very Low. The three hardcoded basemap URLs (Carto Light, Carto Dark, ESRI Satellite) are stable CDN endpoints. MapLibre handles failed tile loads gracefully (shows blank tiles). This is pre-existing behavior unrelated to this fix. | DEFERRED |
| V9 | Edge case: basemap switch before map `onLoad` fires | DEFERRED. Severity: Low. Likelihood: Very Low. The BasemapSelector is rendered inside `<MapGl>` and only becomes interactive after the map loads. The user cannot switch basemaps before `onLoad`. | DEFERRED |
| V10 | Fallback `useEffect`+`moveLayer` has timing issues (`sourcedata` event, `once` vs `off`) | Resolved: Fallback is not needed (see V3). Removed from spec entirely. | RESOLVED |
| V11 | R4 (desktop/mobile) has weak acceptance criteria | Resolved: Section 4 includes explicit desktop and mobile test cases with specific checks. | RESOLVED |

---

## 3. Implementation Plan

### Prerequisites

- Access to `/mnt/e/agentdev/projects/project-zeno-next/` repository
- Node.js 22, pnpm 10 installed
- No new dependencies required

### Step 1: Remove `key` prop from basemap Source in Map.tsx

**File**: `/mnt/e/agentdev/projects/project-zeno-next/app/components/Map.tsx`
**Lines**: 126-134

**Before:**
```tsx
<Source
  key={basemapTiles}
  id="background"
  type="raster"
  tiles={[basemapTiles]}
  tileSize={512}
>
  <Layer id="background-tiles" type="raster" />
</Source>
```

**After:**
```tsx
<Source
  id="background"
  type="raster"
  tiles={[basemapTiles]}
  tileSize={512}
>
  <Layer id="background-tiles" type="raster" />
</Source>
```

**What changes**: Remove the line `key={basemapTiles}` from the `<Source>` element. This is the only code change.

**Why it works**: Without the `key` prop, React reconciles the `<Source>` component in-place when `basemapTiles` state changes. The react-map-gl `<Source>` component detects the `tiles` prop change and calls `source.setTiles([newUrl])` on the existing MapLibre GL raster source (confirmed in `react-map-gl/src/mapbox-legacy/components/source.ts` lines 71-72). The `background-tiles` layer remains in its original position at the bottom of the layer stack. All overlay layers (`DynamicTileLayers`, `HighlightedFeaturesLayer`, `SelectAreaLayer`) stay above it.

**Verification**: Run `pnpm lint && pnpm build` from the `project-zeno-next` directory. Both must pass with zero errors.

### Step 2: Build verification

```bash
cd /mnt/e/agentdev/projects/project-zeno-next
pnpm lint
pnpm build
```

**Expected**: Both commands pass. The change is a prop removal -- no type errors, no lint issues.

**Dependencies**: Step 1 must be complete.

### Step 3: Manual testing

Execute the test plan in Section 4 below.

**Dependencies**: Steps 1 and 2 must be complete. A running dev server (`pnpm dev`) is required.

### Files Modified

| File | Change | Lines Affected |
|------|--------|---------------|
| `/mnt/e/agentdev/projects/project-zeno-next/app/components/Map.tsx` | Remove `key={basemapTiles}` from `<Source>` element | Line 127 (delete) |

### Files NOT Modified (and why)

| File | Reason |
|------|--------|
| `app/components/map/BasemapSelector.tsx` | Popover UI unchanged -- calls `onBasemapChange(option.tileUrl)` which correctly triggers state update |
| `app/components/MapAreaControls.tsx` | Props passthrough unchanged |
| `app/components/map/layers/DynamicTileLayers.tsx` | Layer ordering preserved by fix -- no changes needed |
| `app/components/map/layers/HighlightedFeaturesLayer.tsx` | Layer ordering preserved by fix -- no changes needed |
| `app/store/mapStore.ts` | `basemapTiles` is local state in Map.tsx, not in store |

### Data Models and Schema Changes

None. This fix modifies only JSX rendering props. No state shape, store, type, or API changes.

### Implementation Order and Dependencies

```
Step 1 (Remove key prop) --> Step 2 (Build verification) --> Step 3 (Manual testing)
```

All three steps are sequential. There is no parallelism. The entire implementation is a single line deletion.

---

## 4. Testing Strategy

### Test Framework

The `project-zeno-next` repository has **no automated test framework** (no Jest, Vitest, or similar). Quality gates are:
1. `pnpm lint` -- ESLint
2. `pnpm build` -- Next.js build with TypeScript type checking

All functional testing is manual.

### Automated Checks

```bash
cd /mnt/e/agentdev/projects/project-zeno-next
pnpm lint    # Must pass with zero errors
pnpm build   # Must pass with zero errors
```

### Manual Test Plan

#### Setup

1. Start the dev server: `cd /mnt/e/agentdev/projects/project-zeno-next && pnpm dev`
2. Open the app in a browser
3. Create an AOI: Use the chat interface to ask about a specific geographic area (e.g., "What is the tree cover loss in Costa Rica?"). This triggers the backend to return AOI polygon data, which renders via `HighlightedFeaturesLayer`.
4. Ensure a dataset tile layer is visible: After the chat response, tree cover loss (TCL) tiles should appear via `DynamicTileLayers`. If not, ask a question that triggers dataset rendering (e.g., "Show me tree cover loss data for this area").
5. Confirm both AOI polygon outlines and dataset tiles are visible on the map before proceeding.

#### Test Case 1: Switch from Light to Satellite (primary regression test)

1. With AOI and dataset tiles visible, click the basemap selector button (bottom-left, globe icon)
2. Click "Satellite"
3. **PASS if**: Satellite basemap renders below both AOI polygon outlines and dataset tile layers. All overlays remain fully visible.
4. **FAIL if**: Satellite basemap covers/obscures AOI polygons or dataset tiles.

#### Test Case 2: Switch from Satellite to Dark

1. With Satellite active, open basemap selector
2. Click "Dark"
3. **PASS if**: Dark basemap renders below all overlays.

#### Test Case 3: Switch from Dark back to Light

1. With Dark active, open basemap selector
2. Click "Light"
3. **PASS if**: Light basemap renders below all overlays.

#### Test Case 4: Rapid switching

1. Quickly click through Light -> Satellite -> Dark -> Light in rapid succession
2. **PASS if**: No visual glitches, final basemap renders correctly below overlays, no console errors.

#### Test Case 5: Switch with no overlays

1. Start fresh (no AOIs or datasets loaded)
2. Switch between all three basemaps
3. **PASS if**: Basemap renders correctly each time, no console errors.

#### Test Case 6: Add overlays after basemap switch

1. Switch to Satellite basemap first
2. Then create an AOI and trigger a dataset tile layer via chat
3. **PASS if**: New AOI polygons and dataset tiles render above the Satellite basemap.

#### Test Case 7: Mobile layout

1. Open browser dev tools, switch to mobile viewport (e.g., iPhone 14 Pro, 393x852)
2. Open basemap selector (may be behind mobile tools toggle)
3. Switch basemaps
4. **PASS if**: Basemap switches correctly, popover opens/closes properly, overlays visible above basemap.

#### Test Case 8: Desktop layout

1. Use desktop viewport (1440x900 or larger)
2. Open basemap selector
3. Switch basemaps
4. **PASS if**: Basemap switches correctly, popover positions at top-start of trigger button, overlays visible above basemap, navigation controls and scale bar unaffected.

#### Debugging: Verify Layer Order via Console

If any test case fails, open browser console and run:

```javascript
// Get the MapLibre GL map instance
const map = document.querySelector('.maplibregl-canvas').closest('.maplibregl-map').__maplibre;
// Print layer order (bottom to top)
map.getStyle().layers.map(l => l.id);
```

`"background-tiles"` should be the first (bottommost) entry. All `tile-layer-*` and `geojson-*` layers should appear after it.

---

## 5. Risk Register

| # | Risk | Severity | Likelihood | Mitigation |
|---|------|----------|------------|------------|
| R1 | `react-map-gl` updates `tiles` prop by removing/re-adding the source instead of calling `setTiles()` | High | Very Low | **Mitigated**: Source code inspection of `react-map-gl/src/mapbox-legacy/components/source.ts` lines 71-72 confirms `setTiles()` is called when only `tiles` changes. This is not speculative -- it is verified against the installed package source. |
| R2 | Removing `key` causes stale/cached tiles from previous basemap to display | Medium | Very Low | MapLibre GL's tile cache is keyed by URL. When `setTiles()` is called with a new URL, old tiles are evicted and new tiles are fetched. If stale tiles do appear, the mitigation is to add a cache-busting query parameter to tile URLs (e.g., `?t=${Date.now()}`). |
| R3 | Future react-map-gl version changes `Source` update behavior | Medium | Low | Pin `react-map-gl` to current version range (`^8.0.4`) in `package.json`. Add a comment in `Map.tsx` explaining why `key` is intentionally omitted from the basemap `<Source>`. |
| R4 | Multiple props change simultaneously on Source (e.g., `tiles` + `tileSize`), triggering the `console.warn` fallback path in react-map-gl | Low | Very Low | Only `tiles` changes when switching basemaps. `tileSize` is hardcoded to `512`. The `id` and `type` props never change. Only a single prop (`tiles`) changes per basemap switch, so the `setTiles()` path is always taken. |
| R5 | Similar layer ordering bug in DynamicTileLayers or HighlightedFeaturesLayer (V6/V7 from validation) | Low | Low | These components use `key` based on stable IDs (not changing URLs), so remounts only occur on add/remove, which is correct behavior. Monitor during testing. If observed, apply the same fix (remove unnecessary `key` props). |

---

## Appendix: react-map-gl Source Update Path (Evidence)

File: `node_modules/react-map-gl/src/mapbox-legacy/components/source.ts`

The `updateSource()` function (lines 40-77) handles prop changes on existing sources:

1. It iterates over changed props, counting how many changed and tracking the last changed key.
2. For raster/vector sources where only `tiles` changed, it calls `source.setTiles(props.tiles)` (line 72).
3. This is a MapLibre GL native method that updates the tile URL without removing the source or its associated layers.

This means:
- The `background-tiles` layer is NEVER removed from the MapLibre layer stack on basemap switch.
- The layer retains its position at the bottom of the stack.
- All overlay layers remain above it.

No fallback mechanism is needed.
