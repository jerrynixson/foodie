from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from typing import Dict, Any, List
import uuid
from datetime import date, datetime
import logging

# Use the updated models and logic
from foodie.logic.models import UserProfile, LogEntry, User
import foodie.logic.tdee_logic as tdee_logic
import foodie.logic.kalman_filter_model as kalman_filter_model

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Adaptive Nutrition API",
    description="Enhanced calorie tracking with adaptive goals and robust error handling",
    version="2.1.0-fix"
)

# In-Memory Database
db: Dict[str, User] = {}

# --- EXCEPTION HANDLERS ---
@app.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(status_code=400, content={"error": "Invalid data", "detail": str(exc)})

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    logger.error(f"Unexpected error: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": "Internal server error"})

# --- UTILITY FUNCTIONS ---
def validate_user_exists(user_id: str) -> User:
    if user_id not in db:
        raise HTTPException(status_code=404, detail=f"User {user_id} not found")
    return db[user_id]

def update_user_activity_tracking(user: User):
    user.days_since_last_adaptation += 1
    user.logs.sort(key=lambda x: x.log_date)

# --- API ENDPOINTS ---
@app.get("/")
def read_root():
    return {"message": "Welcome to the Adaptive Nutrition API (Goal Calculation Fix)"}

@app.post("/v1/users", response_model=User, status_code=201)
def create_user(profile: UserProfile, start_weight_kg: float):
    if not (30.0 <= start_weight_kg <= 300.0):
        raise ValueError("Start weight must be between 30-300 kg")
    
    user_id = str(uuid.uuid4())
    initial_tdee = tdee_logic.calculate_initial_tdee(profile, start_weight_kg)
    
    daily_calorie_adjustment = (profile.goal_kg_per_week * kalman_filter_model.CALORIES_PER_KG) / 7
    initial_goal = int(initial_tdee + daily_calorie_adjustment)
    
    new_user = User(
        user_id=user_id,
        profile=profile,
        initial_calorie_goal=initial_goal,
        adapted_calorie_goal=initial_goal,
        kf_tdee_estimate=initial_tdee,
    )
    
    # Use a dummy old goal for the very first record
    new_user.add_adaptation_record(
        old_goal=initial_goal,
        new_goal=initial_goal,
        reason="Initial goal set using standard TDEE calculation.",
        confidence=0.0
    )
    
    db[user_id] = new_user
    logger.info(f"Created user {user_id} with TDEE {initial_tdee:.0f} and goal {initial_goal}")
    return new_user

@app.get("/v1/users/{user_id}", response_model=User)
def get_user(user_id: str):
    return validate_user_exists(user_id)

@app.post("/v1/users/{user_id}/logs", response_model=User)
def add_log(user_id: str, log: LogEntry):
    user = validate_user_exists(user_id)
    if log.log_date > date.today():
        raise ValueError("Log date cannot be in the future")
    
    existing_log = next((l for l in user.logs if l.log_date == log.log_date), None)
    if existing_log:
        # Update existing log instead of raising error
        existing_log.weight_kg = log.weight_kg
        existing_log.calories_in = log.calories_in
    else:
        user.logs.append(log)

    update_user_activity_tracking(user)
    logger.info(f"Added/Updated log for user {user_id} on {log.log_date}")
    return user

@app.post("/v1/users/{user_id}/run-kf-update", response_model=User)
def run_kalman_filter_update(user_id: str):
    user = validate_user_exists(user_id)
    if len(user.logs) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 logs for KF update")
    
    updated_user = kalman_filter_model.run_full_kalman_update(user)
    logger.info(f"KF update for {user_id}. TDEE: {updated_user.kf_tdee_estimate:.0f}, Conf: {updated_user.adaptation_confidence:.2f}")
    return updated_user

@app.post("/v1/users/{user_id}/adapt", response_model=Dict[str, Any])
def adapt_user_goals(user_id: str):
    user = validate_user_exists(user_id)
    old_goal = user.adapted_calorie_goal

    new_goal, explanation = tdee_logic.run_adaptive_update(user)
    
    goal_changed = new_goal != old_goal
    
    if goal_changed:
        user.add_adaptation_record(
            old_goal=old_goal,
            new_goal=new_goal,
            reason=explanation,
            confidence=user.adaptation_confidence
        )
        # Add current TDEE to history record for better explanations later
        user.adaptation_history[-1]['tdee_estimate'] = int(user.kf_tdee_estimate)
        
        user.adapted_calorie_goal = new_goal
        user.days_since_last_adaptation = 0
        logger.info(f"Goal adapted for {user_id}: {old_goal} -> {new_goal}")
    else:
        logger.info(f"No goal change for {user_id}: {explanation}")
    
    return {
        "user": user,
        "goal_changed": goal_changed,
        "old_goal": old_goal,
        "new_goal": new_goal,
        "explanation": explanation,
        "confidence": user.adaptation_confidence,
    }

# Other endpoints like get_status, get_history can remain largely the same
# as they are for fetching data.
