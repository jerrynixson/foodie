from filterpy.kalman import KalmanFilter
import numpy as np
from foodie.logic.models import LogEntry, User
from typing import Tuple, List
from datetime import date, timedelta
import math

# --- MODEL CONSTANTS (RE-TUNED FOR NEW STABLE MODEL) ---
# Represents our belief in how much TDEE can naturally drift day-to-day.
# A standard deviation of ~50 kcal/day (50*50 = 2500).
BASE_PROCESS_VARIANCE = 2500.0

# Represents our belief in how noisy our daily TDEE *observation* is.
# A standard deviation of ~600 kcal/day (600*600 = 360,000). This is high
# to reflect the massive noise from water weight, inaccurate logging, etc.
BASE_MEASUREMENT_VARIANCE = 360000.0
CALORIES_PER_KG = 7700.0

# --- DATA QUALITY THRESHOLDS ---
MAX_INTERPOLATION_DAYS = 3
MAX_WEIGHT_CHANGE_PER_DAY = 2.0
MAX_CALORIE_DEVIATION = 3.0

def calculate_adaptive_parameters(user: User) -> Tuple[float, float]:
    """Calculates KF parameters based on user's data quality."""
    base_process = BASE_PROCESS_VARIANCE
    base_measurement = BASE_MEASUREMENT_VARIANCE
    
    if len(user.logs) < 7:
        return base_process * 0.5, base_measurement * 1.5
    
    quality = user.data_quality
    consistency_factor = (quality.weight_consistency_score + quality.calorie_consistency_score) / 2
    measurement_adjustment = 2.0 - consistency_factor
    gap_factor = min(2.0, 1.0 + quality.average_gap_days / 5.0)
    process_adjustment = gap_factor
    
    return base_process * process_adjustment, base_measurement * measurement_adjustment

def interpolate_missing_data(log_before: LogEntry, log_after: LogEntry, target_date: date) -> LogEntry:
    """Linear interpolation for missing log entries."""
    days_total = (log_after.log_date - log_before.log_date).days
    days_to_target = (target_date - log_before.log_date).days
    
    if days_total == 0: return log_before
    
    weight_ratio = days_to_target / days_total
    interpolated_weight = log_before.weight_kg + (log_after.weight_kg - log_before.weight_kg) * weight_ratio
    interpolated_calories = int((log_before.calories_in + log_after.calories_in) / 2)
    
    return LogEntry(log_date=target_date, weight_kg=round(interpolated_weight, 2), calories_in=interpolated_calories)

def detect_outliers(logs: List[LogEntry]) -> List[bool]:
    """Detects outlier data points."""
    if len(logs) < 3: return [False] * len(logs)
    outliers = [False] * len(logs)
    
    for i in range(1, len(logs)):
        days_diff = (logs[i].log_date - logs[i-1].log_date).days
        if days_diff > 0:
            if abs(logs[i].weight_kg - logs[i-1].weight_kg) / days_diff > MAX_WEIGHT_CHANGE_PER_DAY:
                outliers[i] = True
    
    if len(logs) >= 7:
        calories = [log.calories_in for log in logs]
        mean_cal = np.mean(calories)
        std_cal = np.std(calories)
        if std_cal > 0:
            for i, log in enumerate(logs):
                if abs(log.calories_in - mean_cal) / std_cal > MAX_CALORIE_DEVIATION:
                    outliers[i] = True
    return outliers

def prepare_continuous_data(logs: List[LogEntry]) -> Tuple[List[LogEntry], List[bool]]:
    """Prepares continuous daily data, handling missing days and outliers."""
    if len(logs) < 2: return logs, [False] * len(logs)
    
    sorted_logs = sorted(logs, key=lambda x: x.log_date)
    outlier_flags = detect_outliers(sorted_logs)
    clean_logs = [log for i, log in enumerate(sorted_logs) if not outlier_flags[i]]
    
    if len(clean_logs) < 2: return logs, [False] * len(logs)
    
    continuous_logs, interpolated_flags = [], []
    current_log_index = 0
    start_date = clean_logs[0].log_date
    end_date = clean_logs[-1].log_date
    
    for i in range((end_date - start_date).days + 1):
        target_date = start_date + timedelta(days=i)
        
        if current_log_index < len(clean_logs) and clean_logs[current_log_index].log_date == target_date:
            continuous_logs.append(clean_logs[current_log_index])
            interpolated_flags.append(False)
            current_log_index += 1
        elif continuous_logs:
            next_real_log_index = current_log_index
            if next_real_log_index < len(clean_logs):
                days_gap = (clean_logs[next_real_log_index].log_date - continuous_logs[-1].log_date).days
                if days_gap <= MAX_INTERPOLATION_DAYS:
                    interpolated_log = interpolate_missing_data(continuous_logs[-1], clean_logs[next_real_log_index], target_date)
                    continuous_logs.append(interpolated_log)
                    interpolated_flags.append(True)
    
    return continuous_logs, interpolated_flags

def update_tdee_with_kalman_filter(user: User, log_yesterday: LogEntry, log_today: LogEntry, is_interpolated: bool = False) -> Tuple[float, float, float]:
    """
    FIXED: Enhanced Kalman Filter with a numerically stable measurement model.
    """
    process_var, measurement_var = calculate_adaptive_parameters(user)
    if is_interpolated:
        measurement_var *= 2.0
    
    kf = KalmanFilter(dim_x=1, dim_z=1)
    
    # State transition: TDEE_today = TDEE_yesterday (with some drift)
    kf.F = np.array([[1.0]])
    
    # --- BUG FIX: STABLE MEASUREMENT MODEL ---
    # The measurement is now a direct observation of TDEE.
    # So, H=1, meaning measurement = 1 * TDEE_estimate.
    kf.H = np.array([[1.0]])
    
    # Current state and uncertainty
    kf.x = np.array([user.kf_tdee_estimate])
    kf.P = np.array([[user.kf_tdee_uncertainty]])
    
    # Noise parameters
    kf.Q = np.array([[process_var]])
    kf.R = np.array([[measurement_var]])
    
    # --- Predict Step ---
    kf.predict()
    
    # --- Update Step ---
    days_diff = max(1, (log_today.log_date - log_yesterday.log_date).days)
    daily_weight_change = (log_today.weight_kg - log_yesterday.weight_kg) / days_diff
    daily_calories = log_today.calories_in
    
    # --- BUG FIX: STABLE MEASUREMENT CALCULATION ---
    # Our measurement 'z' is the TDEE we observe from this day's data.
    # z = calories_in - (weight_change * calories_per_kg)
    z = daily_calories - (daily_weight_change * CALORIES_PER_KG)
    
    kf.update(z)
    
    # Confidence Score Calculation
    base_confidence = 1.0 / (1.0 + kf.P[0, 0] / 10000.0)
    quality_factor = (user.data_quality.weight_consistency_score + user.data_quality.calorie_consistency_score) / 2
    final_confidence = (base_confidence * 0.7 + quality_factor * 0.3)
    
    return float(kf.x[0]), float(kf.P[0, 0]), min(1.0, final_confidence)

def run_full_kalman_update(user: User) -> User:
    """
    FIXED: Processes all user logs with a stateful and numerically stable Kalman filter.
    """
    if len(user.logs) < 2:
        return user
    
    user.calculate_data_quality()
    processed_logs, interpolated_flags = prepare_continuous_data(user.logs)
    
    if len(processed_logs) < 2:
        return user

    current_tdee = user.kf_tdee_estimate
    current_uncertainty = user.kf_tdee_uncertainty
    confidence_scores = []
    
    # Reset to initial state only if it's the very first run for this user.
    if user.total_adaptations == 0:
        from foodie.logic.tdee_logic import calculate_initial_tdee
        current_tdee = calculate_initial_tdee(user.profile, processed_logs[0].weight_kg)
        current_uncertainty = 50000.0 # High initial uncertainty

    for i in range(len(processed_logs) - 1):
        log_yesterday = processed_logs[i]
        log_today = processed_logs[i + 1]
        is_interpolated = interpolated_flags[i + 1]
        
        # Pass the current state to the update function via the user object
        user.kf_tdee_estimate = current_tdee
        user.kf_tdee_uncertainty = current_uncertainty
        
        current_tdee, current_uncertainty, confidence = update_tdee_with_kalman_filter(
            user, log_yesterday, log_today, is_interpolated
        )
        confidence_scores.append(confidence)
    
    # Persist the final learned state back to the user object
    user.kf_tdee_estimate = current_tdee
    user.kf_tdee_uncertainty = current_uncertainty
    user.adaptation_confidence = np.mean(confidence_scores) if confidence_scores else 0.0
    
    return user

