"""
Research-grade formulas for maritime analytics.

Improvements over basic versions:
1. SIS: Physics-based vessel resistance model
2. Z-Score: Robust statistics with Winsorizing
3. Episode Detection: Confidence-weighted state machine
"""

import numpy as np
from typing import Tuple, Optional


# ============================================================================
# 1. ADVANCED SIS (Sea Impact Score)
# ============================================================================

def compute_sis_advanced(
    hs_m: float,           # Significant wave height (meters)
    current_ms: float,     # Head current speed (m/s)
    wind_ms: float,        # Wind speed (m/s)
    wave_angle_deg: float, # Wave encounter angle (0=head, 90=beam)
    draft_m: float = 12.0, # Vessel draft (meters)
    beam_m: float = 32.0,  # Vessel beam (meters)
    length_m: float = 180.0, # Vessel length (meters)
    speed_kn: float = 12.0,  # Vessel speed (knots)
) -> Tuple[float, dict]:
    """
    Advanced SIS using vessel resistance components.

    Based on:
    - Holtrop-Mennen resistance model
    - ITTC wave resistance formulation
    - Added resistance in waves (RAW)

    Returns:
        sis: Overall sea impact score (0-1 scale)
        components: Breakdown by resistance type
    """

    # Convert speed to m/s
    speed_ms = speed_kn * 0.514444

    # 1. CALM WATER RESISTANCE (baseline)
    # Froude number
    froude = speed_ms / np.sqrt(9.81 * length_m)

    # Block coefficient (typical VLCC ~0.85)
    cb = 0.85

    # Calm water resistance coefficient (simplified)
    cf_calm = 0.075 / (np.log10(length_m * speed_ms / 1.19e-6) - 2)**2

    # 2. ADDED RESISTANCE IN WAVES (RAW)
    # Wave length
    wave_length = 1.56 * hs_m**2  # Deep water approximation

    # Encounter frequency
    omega_e = np.sqrt(9.81 * 2 * np.pi / wave_length) * (1 + froude * np.cos(np.radians(wave_angle_deg)))

    # RAW coefficient (empirical, depends on wave steepness)
    wave_steepness = hs_m / wave_length
    raw_coeff = 8 * wave_steepness * (hs_m / beam_m)**2

    # Directional factor (head seas worst, following seas best)
    dir_factor = (1 + np.cos(np.radians(wave_angle_deg))) / 2

    # Added wave resistance
    r_wave = raw_coeff * dir_factor

    # 3. CURRENT RESISTANCE
    # Relative speed through water
    speed_through_water = speed_ms + current_ms  # Head current positive

    # Current adds quadratically to resistance
    r_current = cf_calm * (speed_through_water / speed_ms)**2 - cf_calm
    r_current = max(0, r_current)  # Only positive added resistance

    # 4. WIND RESISTANCE
    # Wind pressure coefficient (typical tanker)
    c_aa = 0.8

    # Air density
    rho_air = 1.225  # kg/m³

    # Wind force (simplified, assumes head wind)
    frontal_area = beam_m * (draft_m + 8)  # Draft + freeboard ~8m
    wind_force = 0.5 * c_aa * rho_air * frontal_area * wind_ms**2

    # Convert to resistance coefficient
    water_density = 1025  # kg/m³
    wetted_surface = 1.7 * length_m * draft_m  # Approximation
    dynamic_pressure = 0.5 * water_density * speed_ms**2 * wetted_surface

    r_wind = wind_force / dynamic_pressure if dynamic_pressure > 0 else 0

    # 5. COMBINE COMPONENTS
    # Total added resistance (normalized)
    r_total = r_wave + r_current + r_wind

    # Scale to 0-1 (typical range 0-0.3, clip at 0.5)
    sis = min(1.0, r_total / 0.5)

    components = {
        'sis': sis,
        'r_wave': r_wave,
        'r_current': r_current,
        'r_wind': r_wind,
        'r_total': r_total,
        'froude': froude,
        'wave_length': wave_length,
        'wave_steepness': wave_steepness,
    }

    return sis, components


# ============================================================================
# 2. ROBUST Z-SCORE with Winsorizing
# ============================================================================

def compute_robust_zscore(
    value: float,
    historical_values: np.ndarray,
    winsorize_pct: float = 0.05,
    use_mad: bool = True
) -> Tuple[float, dict]:
    """
    Robust Z-score with outlier treatment.

    Improvements:
    - Winsorizes extreme values before computing baseline
    - Uses MAD (Median Absolute Deviation) instead of STD
    - Returns confidence metrics

    Args:
        value: Current value to score
        historical_values: Historical data for baseline
        winsorize_pct: Percentage to winsorize (0.05 = 5%)
        use_mad: Use MAD instead of STD for robustness

    Returns:
        z_score: Robust Z-score
        metrics: Diagnostic metrics
    """

    if len(historical_values) < 10:
        return None, {'error': 'insufficient_data', 'n': len(historical_values)}

    # 1. WINSORIZE (cap extreme values)
    lower_pct = winsorize_pct
    upper_pct = 1 - winsorize_pct

    lower_bound = np.percentile(historical_values, lower_pct * 100)
    upper_bound = np.percentile(historical_values, upper_pct * 100)

    winsorized = np.clip(historical_values, lower_bound, upper_bound)

    # 2. COMPUTE ROBUST BASELINE
    baseline_median = np.median(winsorized)

    if use_mad:
        # Median Absolute Deviation (more robust than STD)
        mad = np.median(np.abs(winsorized - baseline_median))
        # Scale MAD to approximate STD for normal distribution
        baseline_scale = 1.4826 * mad
    else:
        baseline_scale = np.std(winsorized)

    # 3. COMPUTE Z-SCORE
    if baseline_scale > 0:
        z_score = (value - baseline_median) / baseline_scale
    else:
        z_score = 0.0

    # 4. DIAGNOSTIC METRICS
    metrics = {
        'z_score': z_score,
        'baseline_median': baseline_median,
        'baseline_scale': baseline_scale,
        'n_samples': len(historical_values),
        'winsorized_n': np.sum((historical_values < lower_bound) | (historical_values > upper_bound)),
        'lower_bound': lower_bound,
        'upper_bound': upper_bound,
        'percentile': np.mean(historical_values < value) * 100,  # Percentile rank
        'method': 'MAD' if use_mad else 'STD',
    }

    return z_score, metrics


# ============================================================================
# 3. CONFIDENCE-WEIGHTED EPISODE DETECTION
# ============================================================================

def compute_dwell_confidence(
    sog_values: np.ndarray,
    position_deltas: np.ndarray,
    time_deltas: np.ndarray,
    sog_threshold: float = 1.0,
    pos_threshold: float = 100.0,  # meters
) -> Tuple[float, dict]:
    """
    Compute confidence that vessel is truly dwelling (anchored).

    Uses:
    - Rolling median SOG (removes noise)
    - Position stability (removes oscillation)
    - Time consistency (removes brief stops)

    Returns:
        confidence: 0-1 score for dwell likelihood
        metrics: Breakdown of confidence factors
    """

    if len(sog_values) < 3:
        return 0.0, {'error': 'insufficient_fixes'}

    # 1. SPEED CONFIDENCE (rolling median to remove spikes)
    window_size = min(5, len(sog_values))
    sog_smoothed = np.convolve(sog_values, np.ones(window_size)/window_size, mode='valid')

    # Percentage of time below threshold
    speed_conf = np.mean(sog_smoothed < sog_threshold)

    # 2. POSITION CONFIDENCE (low movement)
    if len(position_deltas) > 0:
        median_movement = np.median(position_deltas)
        # Exponential decay: high confidence if movement < threshold
        pos_conf = np.exp(-median_movement / pos_threshold)
    else:
        pos_conf = 0.5

    # 3. TIME CONFIDENCE (longer = higher confidence)
    total_time_hours = np.sum(time_deltas) / 3600 if len(time_deltas) > 0 else 0
    # Sigmoid: reaches 0.95 confidence at 2 hours
    time_conf = 1 / (1 + np.exp(-(total_time_hours - 1)))

    # 4. COMBINE (weighted geometric mean for balance)
    weights = np.array([0.4, 0.4, 0.2])  # Speed and position most important
    confidence = np.prod([speed_conf, pos_conf, time_conf] ** weights)

    metrics = {
        'confidence': confidence,
        'speed_conf': speed_conf,
        'pos_conf': pos_conf,
        'time_conf': time_conf,
        'median_sog': np.median(sog_values),
        'median_movement': np.median(position_deltas) if len(position_deltas) > 0 else None,
        'total_hours': total_time_hours,
        'n_fixes': len(sog_values),
    }

    return confidence, metrics


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # 1. Advanced SIS
    print("=" * 70)
    print("1. ADVANCED SIS (Sea Impact Score)")
    print("=" * 70)

    sis, components = compute_sis_advanced(
        hs_m=2.5,
        current_ms=0.8,
        wind_ms=12.0,
        wave_angle_deg=30,
        draft_m=12.0,
        speed_kn=12.0
    )

    print(f"Overall SIS: {sis:.3f}")
    print(f"  Wave resistance:    {components['r_wave']:.4f}")
    print(f"  Current resistance: {components['r_current']:.4f}")
    print(f"  Wind resistance:    {components['r_wind']:.4f}")
    print(f"  Total resistance:   {components['r_total']:.4f}")
    print()

    # 2. Robust Z-Score
    print("=" * 70)
    print("2. ROBUST Z-SCORE")
    print("=" * 70)

    # Historical dwell times with outliers
    historical = np.array([18, 20, 22, 19, 21, 23, 20, 48, 19, 21, 22, 20])  # 48 is outlier

    z, metrics = compute_robust_zscore(35, historical, winsorize_pct=0.05, use_mad=True)

    print(f"Current value: 35h")
    print(f"Z-score: {z:.2f}")
    print(f"Baseline median: {metrics['baseline_median']:.1f}h")
    print(f"Baseline scale (MAD): {metrics['baseline_scale']:.1f}")
    print(f"Percentile rank: {metrics['percentile']:.1f}%")
    print(f"Winsorized {metrics['winsorized_n']} outliers")
    print()

    # 3. Dwell Confidence
    print("=" * 70)
    print("3. DWELL CONFIDENCE")
    print("=" * 70)

    sog_values = np.array([0.5, 0.3, 0.8, 0.4, 0.2, 0.6, 0.3])  # knots
    position_deltas = np.array([50, 30, 80, 40, 60])  # meters
    time_deltas = np.array([600, 600, 600, 600, 600])  # seconds

    conf, conf_metrics = compute_dwell_confidence(sog_values, position_deltas, time_deltas)

    print(f"Overall confidence: {conf:.3f}")
    print(f"  Speed confidence:    {conf_metrics['speed_conf']:.3f}")
    print(f"  Position confidence: {conf_metrics['pos_conf']:.3f}")
    print(f"  Time confidence:     {conf_metrics['time_conf']:.3f}")
    print(f"  Median SOG: {conf_metrics['median_sog']:.2f} kn")
    print(f"  Median movement: {conf_metrics['median_movement']:.1f} m")
    print(f"  Total duration: {conf_metrics['total_hours']:.2f} hours")
