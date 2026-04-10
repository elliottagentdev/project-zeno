# Architecture Reconnaissance

## Repository Structure

The feature lives in the **project-zeno-next** repository (a separate Next.js frontend), located at:
`/mnt/e/agentdev/projects/project-zeno-next/`

The main backend repository (`project-zeno`) is a Python/FastAPI project and is NOT relevant to this fix.

## project-zeno-next Directory Layout

```
/mnt/e/agentdev/projects/project-zeno-next/
├── app/                         # Next.js App Router root
│   ├── app/                     # Route segments
│   │   ├── (chat)/              # Chat route group
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   └── threads/
│   │   └── classic/
│   ├── components/              # Shared UI components
│   │   ├── Map.tsx              # Main map component (KEY FILE)
│   │   ├── MapAreaControls.tsx  # Map controls container (KEY FILE)
│   │   ├── map/
│   │   │   ├── BasemapSelector.tsx       # Basemap switching UI (KEY FILE)
│   │   │   └── layers/
│   │   │       ├── DynamicTileLayers.tsx        # TCL/dataset tile layers (KEY FILE)
│   │   │       ├── HighlightedFeaturesLayer.tsx # AOI polygon overlays (KEY FILE)
│   │   │       └── select-area-layer/
│   │   │           ├── CustomAreasLayer.tsx
│   │   │           ├── VectorAreasLayer.tsx
│   │   │           ├── mapStyles.ts
│   │   │           └── index.tsx
│   │   ├── legend/
│   │   ├── providers/
│   │   └── ui/
│   ├── hooks/
│   ├── store/
│   │   ├── mapStore.ts          # Zustand store for map state (KEY FILE)
│   │   ├── contextStore.ts
│   │   ├── chatStore.ts
│   │   ├── drawAreaSlice.ts
│   │   └── uploadAreaSlice.ts
│   ├── types/
│   │   ├── map.ts               # LayerId, selectLayerOptions
│   │   └── chat.ts
│   ├── constants/
│   ├── utils/
│   ├── schemas/
│   ├── config/
│   ├── actions/
│   ├── api/
│   ├── auth/
│   └── layout.tsx               # Root layout with Providers
├── components/                  # (top-level, appears to be duplicate/shared)
├── amplify.yml                  # AWS Amplify CI/CD config
├── next.config.ts
├── package.json
├── pnpm-lock.yaml
├── tsconfig.json
└── middleware.ts
```

## Tech Stack

| Category | Technology |
|---|---|
| Framework | Next.js 15 (App Router) with Turbopack |
| Language | TypeScript 5 |
| UI Library | Chakra UI v3 (`@chakra-ui/react@^3.31.0`) |
| Map Library | MapLibre GL (`maplibre-gl@^5.5.0`) via `react-map-gl@^8.0.4` |
| State Management | Zustand v5 (`zustand@^5.0.5`) |
| Icons | `@phosphor-icons/react@^2.1.9` |
| Geospatial | `@turf/*` (area, bbox, center, helpers, union) |
| Drawing | `terra-draw@^1.10.0` + `terra-draw-maplibre-gl-adapter` |
| Animation | Framer Motion / Motion |
| Package Manager | pnpm 10 |
| Deployment | AWS Amplify (`amplify.yml`) |
| Build | `next build --turbopack` |

## Build System

- `pnpm dev` → `next dev` (development)
- `pnpm build` → `next build --turbopack` (production)
- `pnpm lint` → `next lint` (ESLint)
- CI/CD: AWS Amplify (`amplify.yml`) — runs `pnpm install --frozen-lockfile` then `pnpm run build`

## Key Entry Points

### Root Layout
`/mnt/e/agentdev/projects/project-zeno-next/app/layout.tsx`
- Wraps everything in `<Providers>` component
- Loads IBM Plex Sans/Mono fonts

### Map Component Tree (Most Relevant)
```
Map.tsx (MapGl wrapper)
├── <Source key={basemapTiles}> / <Layer id="background-tiles">  ← BUG ROOT
├── <DynamicTileLayers />       ← TCL dataset tile layers
├── <HighlightedFeaturesLayer>  ← AOI polygon overlays
├── <SelectAreaLayer />
└── <MapAreaControls>
    └── <BasemapSelector>       ← Chakra UI Popover for switching basemaps
```

## The Bug: MapLibre Layer Ordering

### Root Cause (from Map.tsx)

In `/mnt/e/agentdev/projects/project-zeno-next/app/components/Map.tsx` lines 126–134:

```tsx
<Source
  key={basemapTiles}          // ← Forces Source unmount/remount on basemap change
  id="background"
  type="raster"
  tiles={[basemapTiles]}
  tileSize={512}
>
  <Layer id="background-tiles" type="raster" />  // ← No beforeId prop
</Source>
```

When `basemapTiles` state changes (user selects a new basemap), the `key={basemapTiles}` prop causes the `<Source>` to unmount and remount. MapLibre GL re-adds the `background-tiles` layer at the **top** of the layer stack. This causes it to render on top of:
- `DynamicTileLayers` layers (TCL dataset rasters)
- `HighlightedFeaturesLayer` layers (AOI polygon outlines)

### Layer ordering in Map.tsx (JSX render order)
1. `background-tiles` (basemap raster) — remounts to top on basemap change
2. Layers from `<DynamicTileLayers />` → `tile-layer-{id}` (raster)
3. Layers from `<HighlightedFeaturesLayer />` → fill + line layers per feature
4. Layers from `<SelectAreaLayer />`

### Basemap State
`basemapTiles` is local React state in `Map.tsx` (line 39–41):
```tsx
const [basemapTiles, setBasemapTiles] = useState(
  "https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png"
);
```
It is passed down through `MapAreaControls` → `BasemapSelector` as props.

## MapStore (Zustand)

`/mnt/e/agentdev/projects/project-zeno-next/app/store/mapStore.ts`

Key state:
- `tileLayers: TileLayer[]` — list of dynamic tile layers (dataset/TCL tiles)
- `geoJsonFeatures: GeoJsonFeature[]` — AOI features for polygon rendering
- `mapRef: MapRef | null` — reference to MapLibre GL instance

`TileLayer` interface:
```ts
interface TileLayer {
  id: string;
  name: string;
  url: string;
  visible: boolean;
  opacity?: number;
}
```

## DynamicTileLayers Component

`/mnt/e/agentdev/projects/project-zeno-next/app/components/map/layers/DynamicTileLayers.tsx`

Renders raster Sources/Layers for each `TileLayer` in mapStore:
- Source id: `tile-source-{tileLayer.id}`
- Layer id: `tile-layer-{tileLayer.id}` (raster, no `beforeId` prop)

## HighlightedFeaturesLayer Component

`/mnt/e/agentdev/projects/project-zeno-next/app/components/map/layers/HighlightedFeaturesLayer.tsx`

Renders per-feature:
- Source: `geojson-source-{feature.id}`
- Fill layer: `geojson-fill-{feature.id}`
- Line layer: `geojson-line-{feature.id}-solid`
- Bbox source + dashed/solid line layers
- MapLibre `Marker` for label

No `beforeId` prop on any `<Layer>` elements.

## BasemapSelector Component

`/mnt/e/agentdev/projects/project-zeno-next/app/components/map/BasemapSelector.tsx`

- Uses Chakra UI `<Popover.Root>` with `positioning={{ placement: "top-start", strategy: "fixed" }}`
- Trigger: `<IconButton>` positioned absolutely at `bottom/left` with `zIndex={510}`
- Content: list of 3 basemap options (Light, Satellite, Dark) with thumbnails
- Calls `onBasemapChange(option.tileUrl)` on click — this sets `basemapTiles` in Map.tsx

**BasemapOptions:**
| id | tileUrl |
|---|---|
| light | `https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png` |
| satellite | `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}` |
| dark | `https://basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png` |

## MapAreaControls Component

`/mnt/e/agentdev/projects/project-zeno-next/app/components/MapAreaControls.tsx`

- Wraps BasemapSelector and drawing/selection tools
- Renders a `<Wrapper>` Box with `pointerEvents="none"`, `zIndex={100}` (absolute positioning)
- Passes `basemapTiles` and `setBasemapTiles` props from Map.tsx to BasemapSelector
- On mobile: hides tools behind a toggle button; on desktop: always visible

## Testing

No test files (`.test.*` / `.spec.*`) were found in the project-zeno-next repository. The project has no automated test suite currently.

## Images

The `/mnt/e/agentdev/projects/project-zeno/.specs/3-fix-basemap-selector-popover-masking-aoi-polygons/images/` directory exists but is empty — no screenshots or mockups were provided.

## Summary of Files To Modify

For the fix described in PROMPT.md (layer ordering fix):

| File | Change Needed |
|---|---|
| `/mnt/e/agentdev/projects/project-zeno-next/app/components/Map.tsx` | Fix basemap Source/Layer rendering to ensure `background-tiles` layer stays at bottom of MapLibre layer stack |

No other files need modification per the minimal-surgery approach.
