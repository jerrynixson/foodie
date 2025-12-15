from foodie.logic.models import User, UserProfile
from typing import Tuple, Optional
import math

# --- CONTROL PARAMETERS ---
MIN_ADAPTATION_INTERVAL = 7
CONFIDENCE_THRESHOLD = 0.3
CALORIES_PER_KG = 7700.0

# --- TDEE CALCULATION FORMULAS ---
def calculate_bmr_mifflin_st_jeor(profile: UserProfile, weight_kg: float) -> float:
    """Calculate BMR using Mifflin-St Jeor equation."""
    if profile.gender.lower() == 'male':
        bmr = 10 * weight_kg + 6.25 * profile.height_cm - 5 * profile.age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * profile.height_cm - 5 * profile.age - 161
    return bmr

def calculate_initial_tdee(profile: UserProfile, weight_kg: float) -> float:
    """Calculate initial TDEE estimate using standard formulas."""
    bmr = calculate_bmr_mifflin_st_jeor(profile, weight_kg)
    tdee = bmr * profile.activity_level
    return tdee

def generate_adaptation_explanation(old_tdee: int, new_tdee: int, confidence: float, old_goal: int, new_goal: int) -> str:
    """Generate human-readable explanation for goal changes based on TDEE updates."""
    tdee_change = new_tdee - old_tdee
    
    if abs(tdee_change) < 25:
        return f"Your metabolism appears stable. Your goal remains at {new_goal} kcal based on the latest data."

    direction = "increased" if tdee_change > 0 else "decreased"
    confidence_desc = "high" if confidence > 0.7 else "moderate" if confidence > 0.4 else "low"
    
    explanation = (f"Based on your recent progress, your estimated maintenance (TDEE) has {direction} "
                   f"from {old_tdee} to {new_tdee} kcal. This adjustment was made with {confidence_desc} confidence. "
                   f"As a result, your calorie goal has been updated from {old_goal} to {new_goal} kcal to keep you on track.")
    return explanation

def run_adaptive_update(user: User) -> Tuple[int, str]:
    """
    FIXED: Adaptive update with a direct and clear goal calculation.
    The primary purpose of this function is to calculate a new calorie goal
    based on the latest TDEE estimate from the Kalman Filter.
    """
    # Check minimum data requirements
    if len(user.logs) < 7:
        return user.adapted_calorie_goal, "Insufficient data - need at least 7 days of logs to adapt."
    
    # Check adaptation interval
    if user.days_since_last_adaptation < MIN_ADAPTATION_INTERVAL:
        days_left = MIN_ADAPTATION_INTERVAL - user.days_since_last_adaptation
        return user.adapted_calorie_goal, f"Next adaptation available in {days_left} days."
    
    # Check confidence threshold
    if user.adaptation_confidence < CONFIDENCE_THRESHOLD:
        return user.adapted_calorie_goal, f"Confidence too low ({user.adaptation_confidence:.2f}) - need more consistent data to adapt."

    # --- CORE GOAL CALCULATION (THE FIX) ---
    # The Kalman Filter has already updated the TDEE estimate.
    # The new goal is simply the new TDEE +/- the deficit/surplus for the user's goal.
    
    old_tdee = int(user.adaptation_history[-1].get('tdee_estimate', user.kf_tdee_estimate)) if user.adaptation_history else int(user.kf_tdee_estimate)
    latest_tdee = int(user.kf_tdee_estimate)
    
    target_daily_surplus = (user.profile.goal_kg_per_week * CALORIES_PER_KG) / 7
    
    # The new goal is a direct calculation from the latest TDEE estimate.
    new_goal = int(latest_tdee + target_daily_surplus)
    
    # Validate the goal is within safe bounds
    validated_goal, warning = validate_calorie_goal(new_goal, user)
    
    # Generate explanation based on the change in TDEE
    explanation = generate_adaptation_explanation(
        old_tdee=old_tdee,
        new_tdee=latest_tdee,
        confidence=user.adaptation_confidence,
        old_goal=user.adapted_calorie_goal,
        new_goal=validated_goal
    )
    
    if warning:
        explanation += f" ({warning})"

    return validated_goal, explanation

def validate_calorie_goal(goal: int, user: User) -> Tuple[int, str]:
    """Validate that calorie goal is within safe/reasonable bounds."""
    current_weight = user.logs[-1].weight_kg if user.logs else 70
    bmr = calculate_bmr_mifflin_st_jeor(user.profile, current_weight)
    min_safe_calories = int(bmr) # BMR is a safe floor
    
    # Maximum reasonable calories (TDEE + 1000)
    max_reasonable_calories = int(user.kf_tdee_estimate + 1000)
    
    warning = ""
    if goal < min_safe_calories:
        goal = min_safe_calories
        warning = f"Goal adjusted to minimum safe level"
    
    if goal > max_reasonable_calories:
        goal = max_reasonable_calories
        warning = f"Goal capped at reasonable maximum"
    
    return goal, warning
