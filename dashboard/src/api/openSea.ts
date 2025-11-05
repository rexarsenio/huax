import { appConfig } from "../config";

export type GateFluxWindow = "h24" | "d7";

export interface GateFluxPoint {
  ts: string;
  gate_id: string;
  direction: string | null;
  crossings: number;
}

export interface GateFluxResponse {
  gate_id: string;
  direction: string | null;
  window: GateFluxWindow;
  total_crossings: number;
  series: GateFluxPoint[];
}

export interface SISSeriesPoint {
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

export interface SISResponse {
  corridor: string;
  window_days: number;
  latest: SISSeriesPoint;
  series: SISSeriesPoint[];
}

export async function fetchGateFlux(
  gateId: string,
  window: GateFluxWindow = "h24",
  direction?: "AtoB" | "BtoA",
): Promise<GateFluxResponse> {
  const params = new URLSearchParams({ gate_id: gateId, window });
  if (direction) {
    params.append("direction", direction);
  }
  const url = `${appConfig.apiBaseUrl}/api/open_sea/gate_flux?${params.toString()}`;
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  if (!resp.ok) {
    throw new Error(`gate_flux failed (${resp.status})`);
  }
  return (await resp.json()) as GateFluxResponse;
}

export async function fetchSIS(corridor: string, window = "d7"): Promise<SISResponse> {
  const params = new URLSearchParams({ corridor, window });
  const url = `${appConfig.apiBaseUrl}/api/open_sea/sis?${params.toString()}`;
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  if (!resp.ok) {
    throw new Error(`sis fetch failed (${resp.status})`);
  }
  return (await resp.json()) as SISResponse;
}

export interface TransitSeriesPoint {
  ds: string;
  corridor_id: string;
  from_id: string;
  to_id: string;
  median_h: number;
  mean_h: number;
  p90_h: number;
  n: number;
}

export interface TransitSnapshot {
  ds: string;
  median_h: number;
  mean_h: number;
  p90_h: number;
  n: number;
}

export interface TransitResponse {
  corridor: string;
  from: string;
  to: string;
  from_id: string;
  to_id: string;
  lookback_days: number;
  latest: TransitSnapshot;
  series: TransitSeriesPoint[];
}

export interface TransitParams {
  fromId: string;
  toId: string;
  corridor?: string;
  lookback?: string;
}

export interface CorridorGeometry {
  type: "LineString";
  coordinates: [number, number][];
}

export interface CorridorFeature {
  corridor_id: string;
  geometry: CorridorGeometry;
  flux_h: number;
  flux_z: number;
  delay_ratio: number;
  sis_p90: number;
  as_of: string;
}

export async function fetchCorridorView(window: GateFluxWindow = "h24"): Promise<CorridorFeature[]> {
  const params = new URLSearchParams({ window });
  const url = `${appConfig.apiBaseUrl}/api/open_sea/corridor_view?${params.toString()}`;
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  if (!resp.ok) {
    throw new Error(`corridor_view failed (${resp.status})`);
  }
  return (await resp.json()) as CorridorFeature[];
}

export interface SeaStateRegionSummary {
  id: string;
  label: string;
  samples: number;
  hs_mean?: number | null;
  hs_p90?: number | null;
  we_mean?: number | null;
  we_p90?: number | null;
  head_current_kn_mean?: number | null;
  head_current_kn_p90?: number | null;
  head_wind_ms_mean?: number | null;
  head_wind_ms_p90?: number | null;
  last_sample?: string | null;
  flux_h?: number | null;
}

export interface SeaStateSummaryResponse {
  window: string;
  start: string;
  end: string;
  regions: SeaStateRegionSummary[];
}

export async function fetchSeaStateSummary(
  window: string = "h24",
  scope: "mediterranean" | "global" | "west_africa" = "mediterranean",
): Promise<SeaStateSummaryResponse> {
  const params = new URLSearchParams({ window, scope });
  const url = `${appConfig.apiBaseUrl}/api/open_sea/sea_state_summary?${params.toString()}`;
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  if (!resp.ok) {
    throw new Error(`sea_state_summary failed (${resp.status})`);
  }
  return (await resp.json()) as SeaStateSummaryResponse;
}

export interface CorridorDefinition {
  corridor_id: string;
  entry_gates: string[];
  exit_gates: string[];
  min_hours: number;
  max_hours: number;
}

export async function fetchCorridors(): Promise<CorridorDefinition[]> {
  const url = `${appConfig.apiBaseUrl}/api/open_sea/corridors`;
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  if (!resp.ok) {
    throw new Error(`corridors fetch failed (${resp.status})`);
  }
  return (await resp.json()) as CorridorDefinition[];
}

export async function fetchTransit(params: TransitParams): Promise<TransitResponse> {
  const search = new URLSearchParams({
    from_id: params.fromId,
    to: params.toId,
  });
  if (params.corridor) {
    search.append("corridor", params.corridor);
  }
  if (params.lookback) {
    search.append("lookback", params.lookback);
  }
  const url = `${appConfig.apiBaseUrl}/api/open_sea/transit?${search.toString()}`;
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  if (!resp.ok) {
    throw new Error(`transit fetch failed (${resp.status})`);
  }
  return (await resp.json()) as TransitResponse;
}

// === Gate Weather (Standalone, Independent of Ship Movements) ===

export interface GateWeatherObservation {
  observed_at: string | null;
  waves: {
    height_m: number | null;
    period_s: number | null;
    direction_deg: number | null;
    flag: number;
    severity: "high" | "moderate" | "normal";
  };
  currents: {
    u_knots: number | null;
    v_knots: number | null;
    speed_knots: number | null;
    flag: number;
    severity: "high" | "moderate" | "normal";
  };
}

export interface GateWeatherStatistics {
  samples_count: number;
  waves: {
    mean_height_m: number | null;
    max_height_m: number | null;
    p90_height_m: number | null;
  };
  currents: {
    mean_speed_kn: number | null;
    max_speed_kn: number | null;
    p90_speed_kn: number | null;
  };
}

export interface GateWeatherData {
  gate_id: string;
  gate_name: string;
  basin: string;
  latest_observation: GateWeatherObservation;
  statistics: GateWeatherStatistics;
}

export interface GateWeatherResponse {
  window: string;
  start: string;
  end: string;
  gates: GateWeatherData[];
  message?: string;
}

export async function fetchGateWeather(
  window: string = "h24",
  gateIds?: string[],
): Promise<GateWeatherResponse> {
  const params = new URLSearchParams({ window });
  if (gateIds && gateIds.length > 0) {
    params.append("gate_ids", gateIds.join(","));
  }
  const url = `${appConfig.apiBaseUrl}/api/open_sea/gate_weather?${params.toString()}`;
  const resp = await fetch(url, { headers: { Accept: "application/json" } });
  if (!resp.ok) {
    throw new Error(`gate_weather failed (${resp.status})`);
  }
  return (await resp.json()) as GateWeatherResponse;
}
