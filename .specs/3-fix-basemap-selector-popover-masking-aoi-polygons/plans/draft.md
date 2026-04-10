# Implementation Plan: Fix Basemap Layer Ordering on Basemap Switch

## Problem Summary

When the user switches basemaps via the BasemapSelector popover, the basemap raster tiles render **on top of** AOI polygons (`HighlightedFeaturesLayer`) and dataset tile layers (`DynamicTileLayers`). This is a MapLibre GL layer ordering bug, not a CSS z-index issue.

## Root Cause

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

The `key={basemapTiles}` prop causes React to unmount and remount the `<Source>` component whenever the basemap URL changes. When MapLibre GL re-adds the `background-tiles` layer, it inserts it at the **top** of the internal layer stack -- above `DynamicTileLayers` and `HighlightedFeaturesLayer` layers.

## Chosen Approach: Approach B -- Update Tiles URL In-Place (No Remount)

### Why Approach B over Approach A (beforeId)

**Approach A** (`beforeId` prop) would require knowing the ID of the first dynamic layer to position the basemap before. This is fragile because:
- `DynamicTileLayers` renders layers with IDs like `tile-layer-{tileLayer.id}` -- these are dynamic and may not exist when the basemap remounts
- `HighlightedFeaturesLayer` renders layers with IDs like `geojson-fill-{feature.id}` -- also dynamic
- If no dynamic layers exist yet, `beforeId` has nothing to reference, and the basemap would still end up on top when dynamic layers are added later

**Approach B** avoids the remount entirely. By removing the `key={basemapTiles}` prop and instead updating the source's tile URL in-place, MapLibre GL keeps the existing `background-tiles` layer in its original position at the bottom of the stack. The layer never gets removed and re-added, so ordering is preserved.

### Why This Is Minimal Surgery

- **1 file modified**: `Map.tsx`
- **0 new files**
- **0 new dependencies**
- The fix removes code complexity (the `key` prop) rather than adding it

## Detailed Implementation

### File: `/mnt/e/agentdev/projects/project-zeno-next/app/components/Map.tsx`

#### Change 1: Remove `key` prop from basemap Source

**Before (lines 126-134):**
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

The only change is removing `key={basemapTiles}`. This is the entire fix.

#### How It Works

1. When `basemapTiles` state changes (user picks a new basemap in `BasemapSelector`), React re-renders `Map`.
2. The `<Source>` component receives a new `tiles` prop value.
3. `react-map-gl`'s `<Source>` component detects the prop change and calls MapLibre GL's `map.getSource("background").setTiles([newUrl])` internally -- updating the tile URL without removing/re-adding the source or its layers.
4. MapLibre GL fetches and renders the new tiles in the existing `background-tiles` layer, which remains at the bottom of the layer stack.
5. All overlay layers (`DynamicTileLayers`, `HighlightedFeaturesLayer`, `SelectAreaLayer`) remain above the basemap.

### No Changes Needed to Other Files

- **`BasemapSelector.tsx`**: No changes. It calls `onBasemapChange(option.tileUrl)` which sets `basemapTiles` state in `Map.tsx` -- this flow is correct.
- **`MapAreaControls.tsx`**: No changes. It passes props through correctly.
- **`DynamicTileLayers.tsx`**: No changes. Layer ordering relative to basemap is preserved.
- **`HighlightedFeaturesLayer.tsx`**: No changes. Layer ordering relative to basemap is preserved.
- **`mapStore.ts`**: No changes. The `basemapTiles` state is local to `Map.tsx`, not in the store.

## react-map-gl Source Update Behavior

The `react-map-gl` `<Source>` component (v8.x) handles prop changes via its internal `_updateSource` method. When the `tiles` array changes on a raster source:

1. It calls `map.getSource(id)` to get the existing MapLibre GL source
2. For raster sources, it detects that the `tiles` prop changed
3. It removes the old source and adds a new one with the updated tiles, BUT it preserves all associated layers and their ordering

Critically, the `id` prop (`"background"`) stays the same across renders, so `react-map-gl` treats it as an update rather than a create. Without the `key` prop forcing an unmount, React reconciles the component in-place, and `react-map-gl` handles the source update internally without disrupting layer ordering.

**Important nuance**: If `react-map-gl` does internally remove/re-add the source when tiles change, the layers would still end up on top. In that case, we need a fallback approach using `useEffect` to call `map.moveLayer()` after basemap changes. This is documented in the Edge Cases section below.

## Edge Cases and Robustness

### Edge Case 1: react-map-gl internally removes/re-adds source on tiles change

**Risk**: Medium. Some versions of `react-map-gl` may remove and re-add the source when `tiles` changes, which would re-add `background-tiles` at the top of the stack -- the same bug we are fixing.

**Detection**: After implementing the fix, test by switching basemaps with both AOI polygons and dataset tile layers visible. If the basemap still renders on top, this edge case is occurring.

**Mitigation (Fallback)**: Add a `useEffect` that monitors `basemapTiles` and calls `map.moveLayer("background-tiles", firstOverlayLayerId)` after the source update settles. This would use the MapLibre GL native API to reposition the layer:

```tsx
useEffect(() => {
  if (!mapRef.current) return;
  const map = mapRef.current.getMap();
  // Wait for the source update to complete
  const handler = () => {
    const layers = map.getStyle()?.layers;
    if (!layers) return;
    // Find the first non-background layer
    const firstOverlay = layers.find(l => l.id !== "background-tiles");
    if (firstOverlay) {
      map.moveLayer("background-tiles", firstOverlay.id);
    }
  };
  map.once("sourcedata", handler);
  return () => map.off("sourcedata", handler);
}, [basemapTiles]);
```

This fallback should only be used if the primary fix (removing `key`) does not work. It is more complex and introduces a timing dependency on the `sourcedata` event.

### Edge Case 2: Initial load with no overlay layers

**Risk**: Low. On initial load, `basemapTiles` is set to the Light basemap URL and the `<Source>` mounts once. Since no basemap switch occurs, the layer ordering is correct. `DynamicTileLayers` and `HighlightedFeaturesLayer` are added after the basemap, so they naturally appear above it.

**No mitigation needed.**

### Edge Case 3: Rapid basemap switching

**Risk**: Low. If the user rapidly switches between basemaps, React will batch state updates and only the final `basemapTiles` value will trigger a re-render. Since we are no longer forcing unmount/remount via `key`, there are no race conditions with source creation/destruction.

**No mitigation needed.**

### Edge Case 4: Basemap switch while map is still loading tiles

**Risk**: Low. MapLibre GL handles tile loading asynchronously. Changing the tiles URL on a source cancels pending tile requests for the old URL and starts fetching tiles for the new URL. The layer remains in place throughout.

**No mitigation needed.**

## Testing Strategy

### Manual Testing (Primary -- No Automated Test Framework)

The `project-zeno-next` repository has no automated test suite (no Jest, Vitest, or similar). Testing is manual.

**Test Plan:**

1. **Precondition**: Navigate to the map view with at least one AOI polygon visible (triggers `HighlightedFeaturesLayer`) and at least one dataset tile layer visible (triggers `DynamicTileLayers`, e.g., tree cover loss).

2. **Test Case 1: Switch from Light to Satellite**
   - Open BasemapSelector popover (bottom-left button)
   - Click "Satellite"
   - **Expected**: Satellite basemap renders below both AOI polygon outlines and dataset tile layers. AOI polygons and dataset tiles remain fully visible.

3. **Test Case 2: Switch from Satellite to Dark**
   - With Satellite active, open BasemapSelector
   - Click "Dark"
   - **Expected**: Dark basemap renders below all overlays.

4. **Test Case 3: Switch from Dark back to Light**
   - With Dark active, open BasemapSelector
   - Click "Light"
   - **Expected**: Light basemap renders below all overlays.

5. **Test Case 4: Rapid switching**
   - Quickly click through Light -> Satellite -> Dark -> Light
   - **Expected**: No visual glitches, final basemap renders correctly below overlays.

6. **Test Case 5: Switch with no overlays**
   - Remove all AOIs and dataset layers
   - Switch basemaps
   - **Expected**: Basemap renders correctly, no errors in console.

7. **Test Case 6: Add overlays after basemap switch**
   - Switch to Satellite basemap
   - Then add an AOI and a dataset tile layer
   - **Expected**: New overlays render above the Satellite basemap.

8. **Test Case 7: Mobile layout**
   - Test on mobile viewport (or responsive dev tools)
   - Switch basemaps
   - **Expected**: Same correct behavior, popover still usable.

### Build Verification

```bash
cd /mnt/e/agentdev/projects/project-zeno-next
pnpm lint    # ESLint passes
pnpm build   # Next.js build succeeds (includes TypeScript type checking)
```

## Risk Register

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| `react-map-gl` internally removes/re-adds source on `tiles` change, causing same layer ordering issue | High | Medium | Use fallback `useEffect` with `map.moveLayer()` as documented in Edge Case 1 |
| Removing `key` causes stale tile cache (old basemap tiles shown after switch) | Medium | Low | MapLibre GL's tile cache is keyed by URL, so new tiles will be fetched. If stale tiles persist, add `key` back and use Approach A or the `moveLayer` fallback instead |
| Some basemap tile providers return different tile sizes or formats that cause rendering issues with in-place source update | Low | Very Low | The three current basemap providers (Carto Light, Carto Dark, ESRI Satellite) all use standard 256/512px PNG tiles. No action needed |

## Migration Plan

No migration is needed. This is a one-line code change (removing the `key` prop) with no data model, API, or configuration changes. The fix is backward-compatible and requires no deployment coordination.

## Implementation Order

1. Remove `key={basemapTiles}` from the `<Source>` component in `Map.tsx`
2. Run `pnpm lint` and `pnpm build` to verify no regressions
3. Manual test using the test plan above
4. If Edge Case 1 manifests (layer still on top after switch), implement the `useEffect` + `moveLayer` fallback
5. Commit and push
