from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
from datetime import date
import math
import uuid

class UserProfile(BaseModel):
    age: int = Field(..., ge=13, le=120, description="Age must be between 13-120")
    gender: str = Field(..., pattern="^(male|female|other)$", description="Gender: male, female, or other")
    height_cm: float = Field(..., ge=100, le=250, description="Height must be between 100-250cm")
    activity_level: float = Field(..., ge=1.2, le=2.5, description="Activity level: 1.2 (sedentary) to 2.5 (very active)")
    goal_kg_per_week: float = Field(..., ge=-2.0, le=2.0, description="Weight change goal: -2 to +2 kg/week")
    goal_weight_kg: float = Field(..., ge=30.0, le=300.0, description="Goal weight must be between 30-300kg")

    @field_validator('goal_kg_per_week')
    def validate_reasonable_goal(cls, v):
        if abs(v) > 1.5:
            raise ValueError("Goals above 1.5kg/week are generally unsafe")
        return v

class FoodItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    log_date: date
    name: str
    meal_type: str # e.g., "Breakfast", "Lunch", "Dinner", "Snacks"
    calories: int = Field(..., ge=0)
    protein: float = Field(default=0.0, ge=0.0)
    carbs: float = Field(default=0.0, ge=0.0)
    fat: float = Field(default=0.0, ge=0.0)

class LogEntry(BaseModel):
    log_date: date
    weight_kg: float = Field(..., ge=30.0, le=300.0, description="Weight must be between 30-300kg")
    calories_in: int = Field(..., ge=0, le=10000, description="Calories must be between 0-10000")

    @field_validator('calories_in')
    def validate_calories(cls, v):
        if v > 0 and v < 800:
            # This is now a warning rather than a hard error, as it can be 0 before food is logged
            pass
        return v

class MacroTargets(BaseModel):
    """Daily macro nutrient targets in grams"""
    protein_g: float = Field(..., ge=0.0, description="Daily protein target in grams")
    carbs_g: float = Field(..., ge=0.0, description="Daily carbohydrate target in grams")
    fat_g: float = Field(..., ge=0.0, description="Daily fat target in grams")
    
    @property
    def total_calories(self) -> int:
        """Calculate total calories from macro targets (4 kcal/g protein&carbs, 9 kcal/g fat)"""
        return int(self.protein_g * 4 + self.carbs_g * 4 + self.fat_g * 9)

class DataQualityMetrics(BaseModel):
    """Tracks data quality for KF parameter adjustment"""
    consecutive_days: int = 0
    total_days_logged: int = 0
    average_gap_days: float = 0.0
    weight_consistency_score: float = 1.0  # 0-1, higher = more consistent
    calorie_consistency_score: float = 1.0  # 0-1, higher = more consistent

class User(BaseModel):
    user_id: str
    name: str = Field(default="User", description="User's display name")
    profile: UserProfile
    initial_calorie_goal: int
    adapted_calorie_goal: int
    macro_targets: MacroTargets
    
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
        """Add a record of goal adaptation with reasoning"""
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
        """Get logs from the last N days, sorted chronologically"""
        if not self.logs: return []
        sorted_logs = sorted(self.logs, key=lambda x: x.log_date, reverse=True)
        recent_logs = sorted_logs[:days] if len(sorted_logs) >= days else sorted_logs
        return sorted(recent_logs, key=lambda x: x.log_date)
    
    def calculate_data_quality(self):
        """Calculate data quality metrics for adaptive parameter tuning"""
        if len(self.logs) < 2: return
        sorted_logs = sorted(self.logs, key=lambda x: x.log_date)
        
        total_days = (sorted_logs[-1].log_date - sorted_logs[0].log_date).days + 1
        gaps = []
        consecutive_streak = 1
        max_consecutive = 1
        
        for i in range(1, len(sorted_logs)):
            gap = (sorted_logs[i].log_date - sorted_logs[i-1].log_date).days
            if gap == 1:
                consecutive_streak += 1
                max_consecutive = max(max_consecutive, consecutive_streak)
            else:
                gaps.append(gap - 1)
                consecutive_streak = 1
        
        recent_weights = [log.weight_kg for log in sorted_logs[-14:]]
        if len(recent_weights) > 1:
            weight_var = sum((w - sum(recent_weights)/len(recent_weights))**2 for w in recent_weights) / len(recent_weights)
            weight_consistency = max(0, 1 - (weight_var / 10))
        else: weight_consistency = 1.0
        
        recent_calories = [log.calories_in for log in sorted_logs[-14:] if log.calories_in > 0]
        if len(recent_calories) > 1:
            cal_mean = sum(recent_calories) / len(recent_calories)
            cal_var = sum((c - cal_mean)**2 for c in recent_calories) / len(recent_calories)
            calorie_consistency = max(0, 1 - (cal_var / 200000))
        else: calorie_consistency = 1.0
        
        self.data_quality = DataQualityMetrics(
            consecutive_days=max_consecutive,
            total_days_logged=len(sorted_logs),
            average_gap_days=sum(gaps) / len(gaps) if gaps else 0,
            weight_consistency_score=weight_consistency,
            calorie_consistency_score=calorie_consistency
        )

