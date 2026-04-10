# Conventions & Constraints Reconnaissance

## Codebase Location

The frontend codebase lives at `/mnt/e/agentdev/projects/project-zeno-next/` (a separate Next.js project from the Python backend at `/mnt/e/agentdev/projects/project-zeno/`).

---

## Language & Framework

- **TypeScript** (strict mode, `tsconfig.json` has `"strict": true`)
- **Next.js 15** with App Router (`app/` directory), Turbopack build
- **React 19**
- **Chakra UI v3** (`@chakra-ui/react@^3.31.0`) — component library for all UI
- **MapLibre GL / react-map-gl** (`react-map-gl@^8.0.4`, `maplibre-gl@^5.5.0`) — map rendering
- **Zustand** (`zustand@^5.0.5`) — global state management
- **@tanstack/react-query** — server data fetching
- **Phosphor Icons** (`@phosphor-icons/react`) — icon library (no other icon sets)
- **Tailwind CSS v4** — utility classes, but Chakra UI is primary styling method

---

## File Naming Conventions

- **Components**: PascalCase `.tsx` files (e.g., `BasemapSelector.tsx`, `DynamicTileLayers.tsx`, `HighlightedFeaturesLayer.tsx`)
- **Hooks**: camelCase with `use` prefix (e.g., `useErrorHandler.ts`, `useCustomAreasCreate.ts`)
- **Stores**: camelCase with `Store` suffix (e.g., `mapStore.ts`, `contextStore.ts`, `chatStore.ts`)
- **Slices** (Zustand sub-slices): camelCase with `Slice` suffix (e.g., `drawAreaSlice.ts`, `uploadAreaSlice.ts`)
- **Types**: plain camelCase `.ts` (e.g., `map.ts`, `chat.ts`)
- **Config**: camelCase `.ts` (e.g., `api.ts`, `chartColorMappings.ts`)

Subdirectories group related components:
- `app/components/map/` — map-specific components
- `app/components/map/layers/` — MapLibre layer components
- `app/components/ui/` — shared UI primitives (toaster, tooltip, color-mode, etc.)
- `app/store/` — Zustand stores and slices
- `app/hooks/` — custom React hooks
- `app/types/` — TypeScript type definitions
- `app/config/` — configuration constants

---

## Component Patterns

### "use client" Directive
All interactive components start with `"use client";` — required for React hooks and event handlers in Next.js App Router. Example: `BasemapSelector.tsx`, `Map.tsx`.

### Named vs Default Exports
- **Default export** for page-level and main components (e.g., `export default Map;`, `export default DynamicTileLayers;`)
- **Named export** for reusable sub-components exported from a module (e.g., `export function BasemapSelector(...)`)
- Interfaces/types use named exports as well

### Props Interfaces
Props interfaces are declared immediately before the component function, named `[ComponentName]Props`:

```typescript
interface BasemapSelectorProps {
  display: Record<string, string> | string;
  currentBasemap: string;
  onBasemapChange: (tileUrl: string) => void;
}
```

### Internal Interfaces
Module-internal types are declared at the top of the file without export, e.g.:
```typescript
interface GeoJsonFeature { ... }
interface TileLayer { ... }
```

### Wrapper Pattern
Reusable layout wrapper components inside a file are defined as local functions and not exported:
```typescript
function Wrapper({ children, ...props }: { children: React.ReactNode } & BoxProps) { ... }
```

---

## Styling Conventions

- **Chakra UI props** for all layout and style (no CSS modules, minimal Tailwind)
- **Semantic color tokens** from the Chakra theme: `"fg"`, `"fg.muted"`, `"fg.inverted"`, `"bg"`, `"bg.muted"`, `"bg.subtle"`, `"border"`, `"border.inverted"`, `"primary.solid"`, `"secondary.400"`
- **Responsive props** using object syntax: `bottom={{ base: "4.25rem", md: "calc(7rem - 2px)" }}`
- **CSS variable references** for values not in Chakra tokens: `"var(--chakra-colors-fg-muted)"`
- **`zIndex` values** used in map controls: `500` (controls), `510` (basemap selector button), `100` (MapAreaControls wrapper)
- **`pointerEvents`**: overlaid elements set `pointerEvents="none"` on containers and `pointerEvents="all"` on interactive children

---

## Chakra UI v3 Specifics

Chakra UI v3 uses the Ark UI compound component pattern for complex components:

```typescript
// Popover usage (BasemapSelector.tsx)
<Popover.Root positioning={{ placement: "top-start", strategy: "fixed" }}>
  <Popover.Trigger asChild>...</Popover.Trigger>
  <Popover.Positioner>
    <Popover.Content>
      <Popover.Body>...</Popover.Body>
    </Popover.Content>
  </Popover.Positioner>
</Popover.Root>

// Tag usage (HighlightedFeaturesLayer.tsx)
<Tag.Root colorPalette="primary" variant="solid">
  <Tag.StartElement>...</Tag.StartElement>
  <Tag.Label>...</Tag.Label>
  <Tag.EndElement>
    <Tag.CloseTrigger />
  </Tag.EndElement>
</Tag.Root>

// Menu usage (MapAreaControls.tsx)
<Menu.Root>
  <Menu.Trigger asChild>...</Menu.Trigger>
  <Portal>
    <Menu.Positioner>
      <Menu.Content>
        <Menu.Item>...</Menu.Item>
      </Menu.Content>
    </Menu.Positioner>
  </Portal>
</Menu.Root>
```

Note: `Portal` from Chakra UI is used with `Menu.Positioner` but NOT with `Popover.Positioner` — the Popover uses `strategy: "fixed"` positioning instead.

---

## Error Handling Patterns

All user-facing errors use the centralized error utilities in `/mnt/e/agentdev/projects/project-zeno-next/app/hooks/useErrorHandler.ts`:

```typescript
// Utility functions (not a hook, exported directly)
showError(error: Error | string, options?: ErrorHandlerOptions)
showApiError(error: Error | string, options?: ErrorHandlerOptions)
showServiceUnavailableError(serviceName?: string)

// Hook (if needed inside component)
const { showError } = useErrorHandler();
```

These call `toaster.create(...)` from `@/app/components/ui/toaster`.

**Pattern for async errors in event handlers:**
```typescript
const handleConfirmDrawing = async () => {
  try {
    const result = await confirmDrawing();
    ...
  } catch (error) {
    console.error("Upload failed:", error);
  }
};
```

**Pattern for non-critical errors (map operations):**
```typescript
try {
  const bboxCoords = bbox(feature.data) as [...];
} catch (error) {
  console.warn(`Failed to calculate bbox for feature ${feature.id}:`, error);
}
```

**MapLibre onError pattern** (`Map.tsx`):
```typescript
onError={(e) => {
  const msg = e.error?.message ?? String(e);
  console.error("[MapLibre error]", msg);
  fetch("/api/log-map-error", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ message: msg, source: e.type, timestamp: new Date().toISOString() })
  });
}}
```

---

## State Management (Zustand)

The map store uses the **slice pattern** for composing stores:

```typescript
// mapStore.ts
const useMapStore = create<MapState>()((...a) => ({
  ...createMapSlice(...a),
  ...createDrawAreaSlice(...a),
  ...createUploadAreaSlice(...a),
}));
```

Slices are typed with `StateCreator<MapState, [], [], SliceInterface>`.

State updates use `set(...)` with object spread for immutability:
```typescript
set((state) => ({
  geoJsonFeatures: [...state.geoJsonFeatures.filter(...), feature],
}));
```

Direct `get()` is used to read other state or call other actions within the same store:
```typescript
get().clearSelectionMode();
```

---

## react-map-gl / MapLibre Layer Ordering

Layers in `react-map-gl` are rendered in the order they appear in the JSX tree. In `Map.tsx`, the current render order is:

1. `<Source id="background">` with `<Layer id="background-tiles" type="raster" />` — basemap
2. `<DynamicTileLayers />` — dataset tile layers (TCL etc.)
3. `<HighlightedFeaturesLayer />` — AOI polygon outlines
4. `<SelectAreaLayer />` — selection interface layer

The bug: when `key={basemapTiles}` causes the background Source to remount, MapLibre re-inserts `background-tiles` at the top of the layer stack (above DynamicTileLayers and HighlightedFeaturesLayer).

The `beforeId` prop on `<Layer>` can be used to control insertion position:
```typescript
<Layer id="background-tiles" type="raster" beforeId="first-dynamic-layer-id" />
```

---

## Testing

**No test framework is currently configured** in the project-zeno-next repository:
- No `jest.config.*` found
- No `vitest.config.*` found
- No `*.test.ts` or `*.spec.ts` application files found (only in node_modules)
- No test script in `package.json` (only `dev`, `build`, `start`, `lint`, `analyze`)

This is a frontend-only project with no automated test suite. Quality gates are:
1. TypeScript type checking (`tsc --noEmit` via `next build`)
2. ESLint linting (`pnpm lint`)
3. Build verification (`pnpm build`)

---

## CI/CD

**File**: `/mnt/e/agentdev/projects/project-zeno-next/.github/workflows/ci.yml`

CI runs on pull requests and pushes to `main` or `develop`. Steps:
1. Checkout
2. Setup Node.js 22
3. Install pnpm 10.14.0
4. `pnpm install --frozen-lockfile`
5. `pnpm lint` (ESLint)
6. `pnpm build` (Next.js build with Turbopack)

**Deployment**: AWS Amplify via `amplify.yml`. Runs `pnpm install --frozen-lockfile` then `pnpm run build`.

---

## Dependency Management

- **Package manager**: `pnpm@10.14.0` (enforced via `packageManager` field in `package.json`)
- **Lock file**: `pnpm-lock.yaml` (must not be manually edited, use `pnpm install`)
- **Adding packages**: `pnpm add <package>` or `pnpm add -D <package>`
- All CI commands use `--frozen-lockfile` to ensure reproducibility

---

## Configuration Constants

Constants are co-located with types or in dedicated config files:

- Map layer options: `/mnt/e/agentdev/projects/project-zeno-next/app/types/map.ts` (uses `Object.freeze` and `as const`)
- API endpoints: `/mnt/e/agentdev/projects/project-zeno-next/app/config/api.ts` (uses `as const`)
- Area validation limits: `/mnt/e/agentdev/projects/project-zeno-next/app/constants/custom-areas.ts`
- Basemap options: currently inline in `BasemapSelector.tsx` as a module-level array

---

## Imports & Aliases

Path alias `@/*` maps to the repo root (configured in `tsconfig.json`):
```typescript
import useMapStore from "@/app/store/mapStore";
import { showError } from "@/app/hooks/useErrorHandler";
```

Relative imports are used for local files within the same component tree:
```typescript
import { BasemapSelector } from "./map/BasemapSelector";
```

react-map-gl imports use the maplibre subpath:
```typescript
import MapGl, { Layer, Source, MapRef } from "react-map-gl/maplibre";
```

---

## Key Utilities to Reuse

- **`showError` / `showApiError`** from `@/app/hooks/useErrorHandler` — for user-visible error toasts
- **`useMapStore`** — for all map state (tileLayers, geoJsonFeatures, mapRef)
- **`bbox` from `@turf/bbox`** — for bounding box calculations
- **Chakra UI `<Portal>`** — available when content needs to escape stacking contexts (used in `Menu.Positioner` but not currently in `Popover.Positioner`)

---

## Relevant Files for This Bug Fix

| File | Role |
|------|------|
| `/mnt/e/agentdev/projects/project-zeno-next/app/components/Map.tsx` | Contains the `<Source>/<Layer>` for basemap, and the layer render order |
| `/mnt/e/agentdev/projects/project-zeno-next/app/components/map/BasemapSelector.tsx` | The Popover UI for selecting basemaps |
| `/mnt/e/agentdev/projects/project-zeno-next/app/components/map/layers/DynamicTileLayers.tsx` | Renders dataset tile layers above basemap |
| `/mnt/e/agentdev/projects/project-zeno-next/app/components/map/layers/HighlightedFeaturesLayer.tsx` | Renders AOI polygon outlines |
| `/mnt/e/agentdev/projects/project-zeno-next/app/components/MapAreaControls.tsx` | Parent that passes `basemapTiles` state to `BasemapSelector` |
| `/mnt/e/agentdev/projects/project-zeno-next/app/store/mapStore.ts` | Zustand store — contains `tileLayers` state |

---

## No CLAUDE.md or AGENTS.md Found

No `CLAUDE.md`, `AGENTS.md`, or `CONTRIBUTING.md` files exist in the project-zeno-next repository.
