export type Basin = "GLOBAL" | "EUR" | "APAC" | "NAM" | "SAM";

export type GlobalIndexPoint = {
  d: string;
  spvx_global: number;
  basins_present?: number | null;
  weather_flag?: number | null;
};

export type BasinIndexPoint = {
  d: string;
  spvx_basin: number;
  comps_present?: number | null;
  weather_flag?: number | null;
};

export type GlobalIndexResponse = {
  series: GlobalIndexPoint[];
  latest?: GlobalIndexPoint;
};

export type BasinIndexResponse = {
  basin: string;
  series: BasinIndexPoint[];
  latest?: BasinIndexPoint;
};

export type ComponentPoint = {
  d: string;
  comp: string;
  z_value: number | null;
  raw_value: number | null;
  n_obs: number | null;
  missing_reason?: string | null;
  weather_flag?: number | null;
};

export type ComponentsResponse = {
  basin: string;
  series: ComponentPoint[];
};

export type OpsHealth = {
  ready: boolean;
  latest_snapshot?: string | null;
  coverage_30d: Record<string, number | null>;
  components_present: Record<string, { present: number; expected: number }>;
  revision_flag: boolean;
  age_days?: number | null;
  weather_flags?: Record<string, number | null>;
};

export type SpreadSignal = {
  prob_up: number;
  top_decile: boolean;
  spread_fwd?: number | null;
};

export type SpreadSnapshot = {
  model_ver?: string | null;
  metrics?: Record<string, number | null> | null;
  drift?: Record<string, number | null> | null;
  degraded: boolean;
  mode?: string | null;
  prob_up?: number | null;
  prob_up_raw?: number | null;
  prob_up_calibrated?: number | null;
  drivers?: Record<string, number | null> | null;
  reasons?: string[];
  top_decile_threshold?: number | null;
  recent_window_days?: number | null;
  calibration_curve?: Array<[number, number]> | null;
};

export type SpreadSignalsResponse = {
  latest: Record<string, unknown>;
  series: Record<string, unknown>[];
};

export type ThroughputNowcastResponse = {
  latest: Record<string, unknown>;
  series: Record<string, unknown>[];
};

export type SignalsSnapshot = {
  asof: string;
  spvx_lite?: number;
  spvx_lite_chg?: number;
  drivers?: Record<string, number>;
  spread?: SpreadSnapshot;
  spread_direction?: {
    "t+1_prob_up": number;
    top_decile: boolean;
  } | null;
  throughput_72h?: {
    mae_units: number | null;
    nowcast: Record<string, number>;
  };
  degraded?: boolean;
  annotations?: string[];
};

export type HealthStatus = {
  status: "ok" | "ready" | "not_ready";
  missing?: string[];
};

export type RunMeta = Record<
  string,
  {
    ts?: string;
    git?: string;
    data_hash?: number;
    versions?: Record<string, string>;
    [key: string]: unknown;
  }
>;

export type DriverMeta = {
  id: string;
  label_key?: string;
  label_default?: string;
  title_key?: string;
  title_default?: string;
  tooltip_key?: string;
  tooltip_default?: string;
};

export type CoverageMeta = {
  id: string;
  label_key?: string;
  label_default?: string;
  description_key?: string;
  description_default?: string;
  cadence_key?: string;
  cadence_default?: string;
  note_key?: string;
  note_default?: string;
};

export type InterpretationBand = {
  label_key?: string;
  label_default?: string;
  range_key?: string;
  range_default?: string;
};

export type BadgeMeta = {
  state: string;
  text_key?: string;
  text_default?: string;
};

export type MethodologyMeta = {
  summary_key?: string;
  summary_default?: string;
  interpretation_key?: string;
  interpretation_default?: string;
  table: {
    component_key?: string;
    component_default?: string;
    geofence_key?: string;
    geofence_default?: string;
    cadence_key?: string;
    cadence_default?: string;
    note_key?: string;
    note_default?: string;
  }[];
  quality_key?: string;
  quality_default?: string;
  transparency_keys?: string[];
  transparency_defaults?: string[];
  disclaimer_key?: string;
  disclaimer_default?: string;
};

export type IndexMeta = {
  index: {
    name: string;
    tagline_key?: string;
    tagline_default?: string;
    description_key?: string;
    description_default?: string;
    fix_time_utc: string;
    version: string;
    rule_of_thumb_key?: string;
    rule_of_thumb_default?: string;
    material_move_points: number;
    bands: InterpretationBand[];
  };
  drivers: DriverMeta[];
  coverage: CoverageMeta[];
  freshness_badges: BadgeMeta[];
  publish_badges: BadgeMeta[];
  methodology: MethodologyMeta;
};
