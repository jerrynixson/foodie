from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import date
import uuid
import pandas as pd

class UserProfile(BaseModel):
    age: int = Field(..., ge=13, le=120)
    gender: str = Field(..., pattern="^(male|female|other)$")
    height_cm: float = Field(..., ge=100, le=250)
    activity_level: float = Field(..., ge=1.2, le=2.5)
    goal_kg_per_week: float = Field(..., ge=-2.0, le=2.0)
    goal_weight_kg: float = Field(..., ge=30.0, le=300.0)

class FoodItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    log_date: date
    name: str
    meal_type: str # e.g., "Breakfast", "Lunch"
    calories: int
    protein: float = 0.0
    carbs: float = 0.0
    fat: float = 0.0

class LogEntry(BaseModel):
    log_date: date
    weight_kg: float = Field(..., ge=30.0, le=300.0)
    calories_in: int = Field(..., ge=0, le=10000)

class DataQualityMetrics(BaseModel):
    consecutive_days: int = 0
    total_days_logged: int = 0
    average_gap_days: float = 0.0
    weight_consistency_score: float = 1.0
    calorie_consistency_score: float = 1.0

class User(BaseModel):
    user_id: str
    name: str  # Added user's name
    profile: UserProfile
    initial_calorie_goal: int
    adapted_calorie_goal: int
    
    kf_tdee_estimate: float
    kf_tdee_uncertainty: float = 50000.0
    
    adaptation_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    days_since_last_adaptation: int = Field(default=0)
    total_adaptations: int = Field(default=0)
    
    data_quality: DataQualityMetrics = Field(default_factory=DataQualityMetrics)
    adaptation_history: List[dict] = Field(default_factory=list)
    
    logs: List[LogEntry] = Field(default_factory=list)
    food_items: List[FoodItem] = Field(default_factory=list)
    
    def add_adaptation_record(self, old_goal: int, new_goal: int, reason: str, confidence: float):
        self.adaptation_history.append({
            "date": date.today().isoformat(),
            "old_goal": old_goal,
            "new_goal": new_goal,
            "change": new_goal - old_goal,
            "reason": reason,
            "confidence": confidence,
            "adaptation_number": self.total_adaptations + 1
        })
        self.total_adaptations += 1
    
    def get_recent_logs(self, days: int = 14) -> List[LogEntry]:
        if not self.logs:
            return []
        sorted_logs = sorted(self.logs, key=lambda x: x.log_date, reverse=True)
        recent_logs = sorted_logs[:days]
        return sorted(recent_logs, key=lambda x: x.log_date)
    
    def calculate_data_quality(self):
        if len(self.logs) < 2:
            return
        
        sorted_logs = sorted(self.logs, key=lambda x: x.log_date)
        gaps = []
        consecutive_streak = 1
        max_consecutive = 1
        
        for i in range(1, len(sorted_logs)):
            gap = (sorted_logs[i].log_date - sorted_logs[i-1].log_date).days
            if gap == 1:
                consecutive_streak += 1
            else:
                if gap > 1:
                    gaps.append(gap - 1)
                consecutive_streak = 1
            max_consecutive = max(max_consecutive, consecutive_streak)
        
        recent_weights = [log.weight_kg for log in sorted_logs[-14:]]
        if len(recent_weights) > 1:
            weight_var = pd.Series(recent_weights).var()
            weight_consistency = max(0, 1 - (weight_var / 2.0))
        else:
            weight_consistency = 1.0
        
        recent_calories = [log.calories_in for log in sorted_logs[-14:] if log.calories_in > 0]
        if len(recent_calories) > 1:
            cal_var = pd.Series(recent_calories).var()
            calorie_consistency = max(0, 1 - (cal_var / 100000))
        else:
            calorie_consistency = 1.0
        
        self.data_quality = DataQualityMetrics(
            consecutive_days=max_consecutive,
            total_days_logged=len(sorted_logs),
            average_gap_days=sum(gaps) / len(gaps) if gaps else 0,
            weight_consistency_score=weight_consistency,
            calorie_consistency_score=calorie_consistency
        )

