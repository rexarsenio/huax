"""
Prometheus metrics for SPVX-Lite observability.
"""

from prometheus_client import Gauge, Counter, Histogram

# Sea-state ingestion metrics
spvx_sea_state_provider = Gauge(
    "spvx_sea_state_provider",
    "Active sea-state data provider (1=active, 0=inactive)",
    ["source"],
)

spvx_sea_state_freshness_seconds = Gauge(
    "spvx_sea_state_freshness_seconds",
    "Time in seconds since last successful sea-state data fetch",
    ["chokepoint"],
)

spvx_sea_state_files_downloaded_total = Counter(
    "spvx_sea_state_files_downloaded_total",
    "Total number of sea-state files downloaded",
    ["provider", "data_type"],
)

spvx_sea_state_records_total = Gauge(
    "spvx_sea_state_records_total",
    "Total number of sea-state records in processed data",
    ["chokepoint"],
)

# Index computation metrics
spvx_index_computation_duration_seconds = Histogram(
    "spvx_index_computation_duration_seconds",
    "Duration of index computation in seconds",
)

spvx_index_value = Gauge(
    "spvx_index_value",
    "Current SPVX-Lite index value",
    ["variant"],
)

spvx_component_value = Gauge(
    "spvx_component_value",
    "Current component feature values",
    ["component"],
)

# Model quality metrics
spvx_model_score = Gauge(
    "spvx_model_score",
    "Model evaluation metrics (e.g. ROC-AUC, PR-AUC, Brier)",
    ["model", "metric"],
)

spvx_model_drift = Gauge(
    "spvx_model_drift",
    "Model drift statistics (e.g. PSI, KS, base_rate_shift, sample_counts)",
    ["model", "metric"],
)
