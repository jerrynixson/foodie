from datetime import date, timedelta
from typing import Dict, List, Optional
from foodie.logic.models import User, LogEntry
from .openrouter_client import OpenRouterClient
import json

class NutritionAssistant:
    """Personalized nutrition assistant with access to user data"""
    
    def __init__(self):
        self.client = OpenRouterClient()
        self.conversation_context = []
        
    def _build_system_prompt(self, user: User) -> str:
        """Build a personalized system prompt based on user data"""
        
        # Calculate user stats
        current_weight = user.logs[-1].weight_kg if user.logs else "Unknown"
        goal_weight = user.profile.goal_weight_kg
        goal_rate = user.profile.goal_kg_per_week
        
        # Recent progress
        recent_logs = user.get_recent_logs(7) if user.logs else []
        progress_summary = ""
        if len(recent_logs) >= 2:
            weight_change = recent_logs[-1].weight_kg - recent_logs[0].weight_kg
            progress_summary = f"In the last {len(recent_logs)} days, their weight changed by {weight_change:+.1f} kg."
        
        # Adaptation info
        recent_adaptations = user.adaptation_history[-3:] if user.adaptation_history else []
        adaptation_summary = ""
        if recent_adaptations:
            last_adaptation = recent_adaptations[-1]
            adaptation_summary = f"Most recent goal adaptation: {last_adaptation['reason']} (changed to {last_adaptation['new_goal']} kcal)"
        
        # Data quality insights
        dq = user.data_quality
        consistency_note = ""
        if dq.total_days_logged > 7:
            if dq.weight_consistency_score < 0.7:
                consistency_note = "Note: Their weight logging shows some inconsistency - they might benefit from weighing at the same time daily."
            if dq.calorie_consistency_score < 0.7:
                consistency_note += " Their calorie tracking varies significantly - consider discussing portion control or food measurement."
        
        # Get user's name safely
        user_name = getattr(user, 'name', 'there')
        
        system_prompt = f"""
You are a knowledgeable, friendly, and supportive nutrition assistant for {user_name}. You have access to their complete nutrition and fitness journey data.

**USER PROFILE:**
- Name: {user_name}
- Age: {user.profile.age}, Gender: {user.profile.gender}
- Height: {user.profile.height_cm} cm
- Activity Level: {user.profile.activity_level}
- Current Weight: {current_weight} kg
- Goal Weight: {goal_weight} kg
- Weekly Goal: {goal_rate:+.1f} kg/week
- Current Calorie Target: {user.adapted_calorie_goal} kcal/day
- Estimated TDEE: {user.kf_tdee_estimate:.0f} kcal/day
- Macro Targets: {user.macro_targets.protein_g:.0f}g protein, {user.macro_targets.carbs_g:.0f}g carbs, {user.macro_targets.fat_g:.0f}g fat

**PROGRESS INSIGHTS:**
{progress_summary}
{adaptation_summary}
{consistency_note}

**CONVERSATION GUIDELINES:**
1. Always address them by name ({user_name}) in a warm, personal way
2. Reference their specific goals and progress when relevant
3. Be encouraging and supportive, celebrating small wins
4. Provide practical, actionable advice based on their data
5. Ask follow-up questions to better understand their challenges
6. Suggest specific foods, meal ideas, or strategies that align with their macro targets
7. If they seem struggling, offer alternative approaches or modifications
8. Keep responses conversational and not overly clinical
9. Use emojis sparingly but appropriately to maintain friendliness
10. If weight loss/gain isn't happening as expected, gently explore potential causes

**AREAS YOU CAN HELP WITH:**
- Meal planning and food suggestions
- Understanding their adaptive calorie system
- Troubleshooting plateaus or unexpected results
- Motivation and accountability
- Clarifying nutrition concepts
- Analyzing their progress patterns
- Suggesting fixes for consistency issues
- Celebrating achievements and milestones

Remember: You're their personal nutrition companion who knows their journey intimately. Be supportive, knowledgeable, and help them succeed! 🌟
"""
        return system_prompt
    
    def _get_recent_food_summary(self, user: User) -> str:
        """Get a summary of recent food logging for context"""
        today = date.today()
        recent_items = [
            item for item in user.food_items 
            if item.log_date >= today - timedelta(days=3)
        ]
        
        if not recent_items:
            return "No recent food entries found."
        
        summary = "Recent food entries:\n"
        for day_offset in range(3):
            check_date = today - timedelta(days=day_offset)
            day_items = [item for item in recent_items if item.log_date == check_date]
            
            if day_items:
                day_name = "Today" if day_offset == 0 else f"{day_offset} day(s) ago"
                total_cals = sum(item.calories for item in day_items)
                summary += f"- {day_name}: {len(day_items)} items, {total_cals} kcal total\n"
        
        return summary
    
    def chat(self, user_message: str, user: User, conversation_history: List[Dict] = None) -> str:
        """Generate a response to user message with full context"""
        
        # Build the conversation with system prompt
        messages = []
        
        # Add system prompt with current user data
        system_prompt = self._build_system_prompt(user)
        messages.append({"role": "system", "content": system_prompt})
        
        # Add conversation history if provided (clean any extra fields)
        if conversation_history:
            for msg in conversation_history:
                if isinstance(msg, dict) and "role" in msg and "content" in msg:
                    # Only include role and content, exclude timestamps or other fields
                    clean_msg = {
                        "role": msg["role"], 
                        "content": msg["content"]
                    }
                    messages.append(clean_msg)
        
        # Add current food context if relevant to the conversation
        if any(keyword in user_message.lower() for keyword in ['food', 'eat', 'meal', 'calorie', 'macro', 'protein', 'carb', 'fat']):
            food_summary = self._get_recent_food_summary(user)
            context_message = f"Recent food context for reference: {food_summary}"
            messages.append({"role": "system", "content": context_message})
        
        # Add the user's current message
        messages.append({"role": "user", "content": user_message})
        
        # Get AI response
        try:
            response = self.client.chat_completion(
                messages=messages,
                max_tokens=800,
                temperature=0.7
            )
            
            if "error" in response:
                return f"I'm having some technical difficulties right now. {response.get('choices', [{}])[0].get('message', {}).get('content', 'Please try again later.')}"
            
            ai_response = response["choices"][0]["message"]["content"]
            return ai_response.strip()
            
        except (KeyError, IndexError) as e:
            return "I'm having trouble processing your message right now. Could you try rephrasing it? 🤔"
        except Exception as e:
            return f"An unexpected error occurred: {str(e)}. Please try again later."
    
    def get_greeting(self, user: User) -> str:
        """Generate a personalized greeting based on user's current situation"""
        
        user_name = getattr(user, 'name', 'there')
        recent_logs = user.get_recent_logs(3)
        
        # Check if they logged today
        today_logged = any(log.log_date == date.today() for log in recent_logs)
        
        if today_logged:
            greeting_msg = f"Great job logging your data today, {user_name}! How are you feeling about your progress? 💪"
        elif recent_logs:
            days_since = (date.today() - recent_logs[-1].log_date).days
            if days_since == 1:
                greeting_msg = f"Hi {user_name}! I noticed you haven't logged today yet. How's your day going? 📝"
            else:
                greeting_msg = f"Welcome back, {user_name}! It's been {days_since} days since your last log. Ready to get back on track? 🎯"
        else:
            greeting_msg = f"Hello {user_name}! I'm here to help you on your nutrition journey. What would you like to talk about? 🌟"
        
        return greeting_msg
    
    def suggest_topics(self, user: User) -> List[str]:
        """Suggest conversation topics based on user's current situation"""
        
        suggestions = []
        
        # Recent progress
        recent_logs = user.get_recent_logs(7)
        if len(recent_logs) >= 3:
            suggestions.append("📈 How am I progressing toward my goal?")
        
        # Food suggestions
        suggestions.append("🍽️ Suggest meals for my macro targets")
        
        # Troubleshooting
        if user.adaptation_confidence < 0.5:
            suggestions.append("🔧 Why isn't my goal adapting yet?")
        
        # Motivation
        suggestions.append("💪 I need some motivation")
        
        # Education
        suggestions.append("🤔 Explain how the adaptive system works")
        
        return suggestions[:4]  # Limit to 4 suggestions
