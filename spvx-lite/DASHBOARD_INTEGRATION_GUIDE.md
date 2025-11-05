# 🎨 Dashboard Integration - Weather Impact Badges

## ✅ Was bereits fertig ist

1. ✅ **Backend:** 28,532 Sea State Samples in Database
2. ✅ **Backend:** API Snapshot aktualisiert
3. ✅ **Frontend:** SISBadge Komponente existiert bereits!
4. ✅ **Frontend:** SeaStateChip Komponente vorhanden

## 📋 Was noch zu tun ist

### 1. API Client erweitern

**File:** `dashboard/src/api/openSea.ts`

```typescript
// Füge hinzu:
export interface SISData {
  ds: string;
  corridor_id: string;
  sis_mean: number;
  sis_p90: number;
  pct_sis_gt_0_7: number;
  hc_p90_kn: number;
  hw_p90_ms: number;
  we_p90_m: number;
  n_samples: number;
}

export async function fetchSIS(corridor: string, window: string = 'd7'): Promise<SISData[]> {
  const response = await fetch(
    `${API_BASE}/api/open_sea/sis?corridor=${encodeURIComponent(corridor)}&window=${window}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch SIS data: ${response.statusText}`);
  }

  const data = await response.json();
  return data.records || [];
}
```

### 2. Hook für SIS-Daten erstellen

**File:** `dashboard/src/hooks/useSISData.ts` (NEU)

```typescript
import { useQuery } from '@tanstack/react-query';
import { fetchSIS, type SISData } from '../api/openSea';

export function useSISData(corridor: string | null, window: string = 'd7') {
  return useQuery({
    queryKey: ['sis', corridor, window],
    queryFn: () => (corridor ? fetchSIS(corridor, window) : Promise.resolve([])),
    enabled: !!corridor,
    refetchInterval: 5 * 60 * 1000, // Refresh every 5 minutes
    staleTime: 2 * 60 * 1000, // Consider stale after 2 minutes
  });
}
```

### 3. MapPage Integration

**File:** `dashboard/src/pages/MapPage.tsx`

Finde die Stelle wo Polygon-Infos angezeigt werden und füge hinzu:

```typescript
import { SISBadge } from '../components/SISBadge';
import { useSISData } from '../hooks/useSISData';

// Im Component:
const { data: sisData } = useSISData(selectedPolygon?.id);
const latestSIS = sisData?.[0]; // Most recent record

// Im JSX (bei Polygon-Info):
{latestSIS && (
  <div className="mt-2">
    <SISBadge
      sis={latestSIS.sis_mean}
      waveHeight={latestSIS.we_p90_m}
      corridor={selectedPolygon.id}
    />
  </div>
)}
```

### 4. OperationsPage Integration

**File:** `dashboard/src/pages/OperationsPage.tsx`

Füge bei jedem Chokepoint/Corridor eine Badge hinzu:

```typescript
import { SISBadge } from '../components/SISBadge';
import { useSISData } from '../hooks/useSISData';

// Für jeden Corridor:
const { data: sisData } = useSISData(corridor.id);
const latestSIS = sisData?.[0];

// Im JSX (Card Header):
<div className="flex items-center justify-between">
  <h3>{corridor.name}</h3>
  {latestSIS && (
    <SISBadge
      sis={latestSIS.sis_mean}
      waveHeight={latestSIS.we_p90_m}
      corridor={corridor.id}
      compact
    />
  )}
</div>
```

### 5. Aktuell verfügbare Corridors

Die SIS-Daten sind verfügbar für:
- `CHOKEPOINT_MALACCA->UNK`
- `CHOKEPOINT_SINGAPORE_STRAIT->UNK`
- `CHOKEPOINT_SUEZ_NORTH->UNK`

## 🎨 Design Specs

### SISBadge Props
```typescript
{
  sis: number,           // 0-1 (e.g. 0.558)
  waveHeight?: number,   // in meters (e.g. 0.16)
  corridor: string,      // corridor ID
  compact?: boolean      // true = small circle, false = full badge
}
```

### Color Coding
- **Good** (SIS < 0.5): Green 🟢 `border-success/40 bg-success/10 text-success`
- **Moderate** (SIS 0.5-0.7): Yellow 🟡 `border-warning/40 bg-warning/10 text-warning`
- **Difficult** (SIS > 0.7): Red 🔴 `border-danger/40 bg-danger/10 text-danger`

### Current Values
- MALACCA: SIS 0.549 (Moderate, 0.14m waves)
- SINGAPORE: SIS 0.547 (Moderate, 0.14m waves)
- SUEZ: SIS 0.584 (Moderate, 0.59m waves)

## 🧪 Testing

### 1. API Test
```bash
curl 'http://localhost:8000/api/open_sea/sis?corridor=CHOKEPOINT_MALACCA-%3EUNK&window=d7'
```

Expected response:
```json
{
  "as_of": "2025-11-01",
  "window": "d7",
  "corridor": "CHOKEPOINT_MALACCA->UNK",
  "records": [
    {
      "ds": "2025-11-01",
      "corridor_id": "CHOKEPOINT_MALACCA->UNK",
      "sis_mean": 0.549,
      "sis_p90": 0.603,
      "we_p90_m": 0.14,
      "n_samples": 145
    }
  ]
}
```

### 2. Component Test
```tsx
import { SISBadge } from './components/SISBadge';

// Test in Storybook or standalone:
<SISBadge sis={0.549} waveHeight={0.14} corridor="MALACCA" />
```

### 3. Integration Test
1. Open Dashboard: `http://localhost:5173`
2. Navigate to Map
3. Click on MALACCA polygon
4. Should see SIS Badge with yellow color (moderate)

## 📦 Required Packages

Check if installed:
```bash
cd dashboard
npm list @tanstack/react-query
```

If missing:
```bash
npm install @tanstack/react-query
```

## 🚀 Quick Start

### Option A: Full Implementation (2-3 hours)
1. Add API functions (15 min)
2. Create useSISData hook (15 min)
3. Integrate in MapPage (45 min)
4. Integrate in OperationsPage (45 min)
5. Testing & Polish (30 min)

### Option B: MVP (30 minutes)
Just add to MapPage for quick demo:

```typescript
// MapPage.tsx - Quick & Dirty MVP
const [sisData, setSisData] = useState<any>(null);

useEffect(() => {
  if (selectedPolygon) {
    fetch(`http://localhost:8000/api/open_sea/sis?corridor=${selectedPolygon.id}&window=d7`)
      .then(res => res.json())
      .then(data => setSisData(data.records?.[0]))
      .catch(console.error);
  }
}, [selectedPolygon]);

// In JSX:
{sisData && (
  <SISBadge
    sis={sisData.sis_mean}
    waveHeight={sisData.we_p90_m}
    corridor={selectedPolygon.id}
  />
)}
```

## 🎯 Success Criteria

✅ User can see weather conditions at a glance
✅ Color coding matches severity (green/yellow/red)
✅ Wave height displayed in badge
✅ Tooltip shows full SIS details
✅ Auto-refreshes every 5 minutes
✅ Works on Map and Operations pages

## 📸 Expected UI

```
┌─────────────────────────────────────┐
│ MALACCA STRAIT                      │
│                                     │
│ Occupancy: 160 tankers              │
│                                     │
│ ┌───────────────────┐               │
│ │ ~ Moderate        │               │
│ │   0.1m waves      │               │
│ └───────────────────┘               │
└─────────────────────────────────────┘
```

## 💡 Tips

1. **Start with MapPage** - Easier to test
2. **Use compact mode** for tables/lists
3. **Full mode** for detail views
4. **Add loading states** - useSISData returns `isLoading`
5. **Handle errors gracefully** - Some corridors might not have data yet

## 🔗 Related Files

- [SISBadge.tsx](dashboard/src/components/SISBadge.tsx) ✅ Exists
- [SeaStateChip.tsx](dashboard/src/components/SeaStateChip.tsx) ✅ Exists
- [MapPage.tsx](dashboard/src/pages/MapPage.tsx) - Needs update
- [OperationsPage.tsx](dashboard/src/pages/OperationsPage.tsx) - Needs update

---

**Ready to implement! Willst du dass ich die Code-Änderungen direkt mache?** 🚀
