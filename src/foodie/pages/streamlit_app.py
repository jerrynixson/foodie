import streamlit as st
import pandas as pd
from datetime import date, timedelta
import math
from typing import List
import altair as alt

# Import the backend logic and the updated models
from foodie.logic.models import UserProfile, LogEntry, User, FoodItem
import foodie.logic.tdee_logic as tdee_logic
import foodie.logic.kalman_filter_model as kalman_filter_model  
import foodie.logic.adaptive_service as main # We will "monkey-patch" its in-memory DB
from foodie.pages.add_food import add_food_dialog
from foodie.pages.visualizations import visualizations_page
from foodie.chatbot import render_chat_assistant

# --- HELPER FUNCTIONS ---

def create_macro_progress_ring(name: str, current: float, target: float, unit: str = "g", color: str = "#1f77b4"):
    """Create a circular progress ring showing macro progress towards target"""
    progress = min(current / target, 1.0) if target > 0 else 0
    percentage = progress * 100
    
    # Create SVG for circular progress
    size = 120
    center = size / 2
    radius = 45
    circumference = 2 * math.pi * radius
    stroke_dasharray = circumference
    stroke_dashoffset = circumference * (1 - progress)
    
    svg = f"""
    <div style="display: flex; flex-direction: column; align-items: center; margin: 10px;">
        <div style="position: relative; width: {size}px; height: {size}px;">
            <svg width="{size}" height="{size}" style="transform: rotate(-90deg);">
                <!-- Background circle -->
                <circle
                    cx="{center}" cy="{center}" r="{radius}"
                    stroke="#e6e6e6"
                    stroke-width="8"
                    fill="transparent"
                />
                <!-- Progress circle -->
                <circle
                    cx="{center}" cy="{center}" r="{radius}"
                    stroke="{color}"
                    stroke-width="8"
                    stroke-linecap="round"
                    fill="transparent"
                    stroke-dasharray="{stroke_dasharray}"
                    stroke-dashoffset="{stroke_dashoffset}"
                    style="transition: stroke-dashoffset 0.5s ease-in-out;"
                />
            </svg>
            <!-- Center text -->
            <div style="
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                text-align: center;
                font-family: sans-serif;
            ">
                <div style="font-size: 18px; font-weight: bold; color: {color};">
                    {current:.0f}{unit}
                </div>
                <div style="font-size: 12px; color: #666; margin-top: 2px;">
                    {percentage:.0f}%
                </div>
            </div>
        </div>
        <!-- Label -->
        <div style="margin-top: 8px; text-align: center;">
            <div style="font-size: 14px; font-weight: bold;">{name}</div>
            <div style="font-size: 12px; color: #666;">{target:.0f}{unit} left</div>
        </div>
    </div>
    """
    return svg

def calculate_time_to_goal(user: User):
    """Estimates the time to reach the goal weight."""
    if not user.logs:
        return "Not enough data", "Log your weight to begin."

    current_weight = user.logs[-1].weight_kg
    goal_weight = user.profile.goal_weight_kg
    target_rate = user.profile.goal_kg_per_week

    weight_to_change = current_weight - goal_weight

    if abs(weight_to_change) < 0.1:
        return "Goal Reached!", f"You've successfully reached your goal of {goal_weight} kg."

    if (weight_to_change > 0 and target_rate >= 0) or \
       (weight_to_change < 0 and target_rate <= 0):
        direction = "lose" if weight_to_change > 0 else "gain"
        return "Check Goal Rate", f"Your goal is to {direction} weight, but your weekly target is set to gain/maintain. Please adjust your goal rate."

    estimated_weeks = abs(weight_to_change / target_rate) if target_rate != 0 else float('inf')
    if math.isinf(estimated_weeks):
        return "Goal Unreachable", "Your weekly goal rate is 0. Please set a weight loss or gain target."
        
    estimated_days = int(estimated_weeks * 7)
    
    title = f"{estimated_weeks:.1f} weeks"
    body = f"to reach your goal of {goal_weight} kg. That's approximately {estimated_days} days."
    return title, body

def get_daily_food_summary(food_items: List[FoodItem], log_date: date):
    """Calculates total calories and macros for a given day."""
    daily_items = [item for item in food_items if item.log_date == log_date]
    summary = {
        "calories": sum(item.calories for item in daily_items),
        "protein": sum(item.protein for item in daily_items),
        "carbs": sum(item.carbs for item in daily_items),
        "fat": sum(item.fat for item in daily_items),
    }
    return summary

# --- UI DIALOGS ---



# --- UI PAGES ---

def onboarding_page():
    """Page for new user creation."""
    st.header("Welcome! Let's set up your profile.", divider='rainbow')
    st.markdown("Provide your details below to get a personalized, adaptive calorie target.")

    activity_options = {
        "Sedentary (little or no exercise)": 1.2,
        "Lightly Active (light exercise/sports 1-3 days/week)": 1.375,
        "Moderately Active (moderate exercise/sports 3-5 days/week)": 1.55,
        "Very Active (hard exercise/sports 6-7 days a week)": 1.725,
        "Extra Active (very hard exercise/sports & physical job)": 1.9
    }

    st.subheader("Your Details")
    name = st.text_input("Your Name*", placeholder="Enter your name")

    st.subheader("Your Stats")
    col1, col2 = st.columns(2)
    with col1:
        age = st.number_input("Age", min_value=13, max_value=120, value=30, step=1)
        gender = st.selectbox("Gender", options=["male", "female", "other"])
        height_cm = st.number_input("Height (cm)", min_value=100.0, max_value=250.0, value=175.0, step=0.5)
    with col2:
        start_weight_kg = st.number_input("Starting Weight (kg)", min_value=30.0, max_value=300.0, value=80.0, step=0.1)
        activity_description = st.selectbox(
            "Activity Level",
            options=list(activity_options.keys()),
            index=2 
        )
        activity_level = activity_options[activity_description]

    st.subheader("Your Goals")
    col3, col4 = st.columns(2)
    with col3:
        goal_weight_kg = st.number_input("Goal Weight (kg)", min_value=30.0, max_value=300.0, value=75.0, step=0.1)
    with col4:
        goal_kg_per_week = st.slider("Weekly Weight Change Goal (kg/week)", min_value=-1.5, max_value=1.5, value=-0.5, step=0.1)

    weight_to_change = start_weight_kg - goal_weight_kg
    estimated_date_str = "—"
    
    if goal_kg_per_week == 0:
        estimated_date_str = "Set a weekly goal"
    elif (weight_to_change > 0 and goal_kg_per_week >= 0) or \
         (weight_to_change < 0 and goal_kg_per_week <= 0):
        estimated_date_str = "Rate conflicts with goal"
    else:
        try:
            estimated_weeks = abs(weight_to_change / goal_kg_per_week)
            estimated_days = int(estimated_weeks * 7)
            goal_date = date.today() + timedelta(days=estimated_days)
            estimated_date_str = goal_date.strftime("%B %d, %Y")
        except ZeroDivisionError:
            estimated_date_str = "Set a weekly goal"

    st.metric("Estimated Goal Date", estimated_date_str)
    
    submitted = st.button("Create My Plan", type="primary", use_container_width=True)

    if submitted:
        if not name:
            st.error("Please enter your name.")
        else:
            try:
                profile = UserProfile(
                    age=age,
                    gender=gender,
                    height_cm=height_cm,
                    activity_level=activity_level,
                    goal_kg_per_week=goal_kg_per_week,
                    goal_weight_kg=goal_weight_kg
                )
                
                # We need to create the user object slightly differently now
                user_id = main.create_user(profile, start_weight_kg, name)
                
                initial_log = LogEntry(log_date=date.today(), weight_kg=start_weight_kg, calories_in=0)
                st.session_state.db[user_id].logs.append(initial_log)

                st.session_state.user_id = user_id
                st.session_state.page = "dashboard"
                st.rerun()

            except ValueError as e:
                st.error(f"Error creating profile: {e}")

def dashboard_page():
    """Main dashboard for logged-in users."""
    user = st.session_state.db.get(st.session_state.user_id)
    if not user:
        st.error("User not found."); st.session_state.page = "login"; st.rerun()

    # Use getattr to safely access the name attribute, providing a default value
    user_name = getattr(user, 'name', 'User') 
    st.sidebar.header(f"Hey there, {user_name}!")
    
    # Sidebar Navigation
    st.sidebar.markdown("---")
    st.sidebar.subheader("📱 Navigation")
    
    # Navigation buttons
    if st.sidebar.button("🏠 Dashboard", use_container_width=True, type="primary" if st.session_state.get('current_view', 'dashboard') == 'dashboard' else "secondary"):
        st.session_state.current_view = "dashboard"
        st.rerun()
        
    if st.sidebar.button("📊 Analytics", use_container_width=True, type="primary" if st.session_state.get('current_view', 'dashboard') == 'analytics' else "secondary"):
        st.session_state.current_view = "analytics"
        st.rerun()
    
    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.user_id = None
        st.session_state.page = "login"
        st.session_state.current_view = "dashboard"
        st.rerun()

    # Add the AI Chat Assistant to sidebar
    try:
        render_chat_assistant(user)
    except Exception as e:
        st.sidebar.error(f"Chat assistant unavailable: {str(e)}")
        st.sidebar.info("💡 Make sure to set up your OPENROUTER_API_KEY in the .env file")

    # Check which view to show
    current_view = st.session_state.get('current_view', 'dashboard')
    
    if current_view == 'analytics':
        visualizations_page()
        return
    
    # Default dashboard view
    st.title("Your Adaptive Nutrition Dashboard")

    if 'diary_date' not in st.session_state:
        st.session_state.diary_date = date.today()

    c1, c2, c3 = st.columns([1,2,1])
    if c1.button("◀️ Previous Day"):
        st.session_state.diary_date -= timedelta(days=1)
    st.session_state.diary_date = c2.date_input("Diary Date", st.session_state.diary_date, label_visibility="collapsed")
    if c3.button("Next Day ▶️"):
        st.session_state.diary_date += timedelta(days=1)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Daily Summary")
        summary = get_daily_food_summary(user.food_items, st.session_state.diary_date)
        
        goal_calories = user.adapted_calorie_goal
        maintenance_calories = int(user.kf_tdee_estimate)
        deficit_surplus = goal_calories - maintenance_calories
        
        st.metric("Your Calorie Goal", f"{goal_calories} kcal/day", f"{deficit_surplus:+} kcal vs maintenance")

        progress_value = (summary["calories"] / goal_calories) if goal_calories > 0 else 0
        progress = min(1.0, progress_value)
        st.progress(progress, text=f"Logged: {summary['calories']} kcal")

        st.markdown(f"<p style='text-align: center; font-size: small; opacity: 0.7;'>Est. Maintenance: {maintenance_calories} kcal</p>", unsafe_allow_html=True)

        # Display macro progress rings
        st.subheader("🧬 Macros")
        
        # Create macro progress rings
        protein_ring = create_macro_progress_ring(
            "Protein", 
            summary['protein'], 
            user.macro_targets.protein_g, 
            "g", 
            "#4CAF50"
        )
        
        carbs_ring = create_macro_progress_ring(
            "Carbs", 
            summary['carbs'], 
            user.macro_targets.carbs_g, 
            "g", 
            "#FF9800"
        )
        
        fat_ring = create_macro_progress_ring(
            "Fat", 
            summary['fat'], 
            user.macro_targets.fat_g, 
            "g", 
            "#2196F3"
        )
        
        # Display rings in columns
        ring_col1, ring_col2, ring_col3 = st.columns(3)
        with ring_col1:
            st.markdown(protein_ring, unsafe_allow_html=True)
        with ring_col2:
            st.markdown(carbs_ring, unsafe_allow_html=True)
        with ring_col3:
            st.markdown(fat_ring, unsafe_allow_html=True)

    with col2:
        st.subheader("Log Your Weight")
        
        # Check if weight has already been logged for the selected date
        todays_log = next((log for log in user.logs if log.log_date == st.session_state.diary_date and log.weight_kg > 0), None)

        if todays_log:
            st.success(f"Weight logged for this day: {todays_log.weight_kg} kg")
        else:
            current_weight = user.logs[-1].weight_kg if user.logs else user.profile.goal_weight_kg - 5.0
            with st.form("weight_log_form"):
                weight_kg = st.number_input("Current Weight (kg)", value=current_weight, step=0.1, format="%.1f")
                
                submitted = st.form_submit_button("Log Weight", type="primary", use_container_width=True)
                if submitted:
                    summary = get_daily_food_summary(user.food_items, st.session_state.diary_date)
                    total_calories = summary['calories']

                    log_entry = next((log for log in user.logs if log.log_date == st.session_state.diary_date), None)
                    if log_entry:
                        log_entry.weight_kg = weight_kg
                        log_entry.calories_in = total_calories
                    else:
                        user.logs.append(LogEntry(log_date=st.session_state.diary_date, weight_kg=weight_kg, calories_in=total_calories))
                    
                    user.logs.sort(key=lambda x: x.log_date)
                    user.days_since_last_adaptation += 1
                    
                    updated_user = kalman_filter_model.run_full_kalman_update(user)
                    st.session_state.db[user.user_id] = updated_user
                    adapt_response = main.adapt_user_goals(user.user_id)
                    
                    if adapt_response['goal_changed']:
                        st.success(f"Log saved and goal adapted! {adapt_response['explanation']}")
                    else:
                        st.info(f"Log saved. No goal change needed. Reason: {adapt_response['explanation']}")
                    st.rerun()
                
    st.divider()

    st.header("Food Diary")
    meal_cols = st.columns(4)
    meal_types = ["Breakfast", "Lunch", "Dinner", "Snacks"]

    for col, meal in zip(meal_cols, meal_types):
        with col:
            st.subheader(meal)
            meal_items = [item for item in user.food_items if item.log_date == st.session_state.diary_date and item.meal_type == meal]
            
            if meal_items:
                for item in meal_items:
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([3, 1, 1])
                        c1.markdown(f"**{item.name}**")
                        c2.markdown(f"_{item.calories} kcal_")
                        if c3.button("🗑️", key=f"del_{item.id}", help="Delete item"):
                            user.food_items = [i for i in user.food_items if i.id != item.id]
                            st.rerun()

            if st.button(f"＋ Add to {meal}", key=f"add_{meal}", use_container_width=True):
                add_food_dialog(user, meal, st.session_state.diary_date)
                
    st.divider()
    tab2, tab3, tab4 = st.tabs(["📈 Quick Charts", "🧠 Adaptation Details", "📜 Full History"])
    with tab2:
        st.subheader("Quick Progress Overview")
        if len(user.logs) >= 2:
            df = pd.DataFrame([log.model_dump() for log in user.logs])
            df['log_date'] = pd.to_datetime(df['log_date'])

            col_chart, col_info = st.columns([2, 1])
            
            with col_chart:
                st.markdown("**Recent Weight Trend**")
                min_weight = df['weight_kg'].min()
                max_weight = df['weight_kg'].max()
                weight_buffer = (max_weight - min_weight) * 0.1 + 1 
                weight_domain = [min_weight - weight_buffer, max_weight + weight_buffer]

                weight_chart = alt.Chart(df).mark_line(
                    color='#1f77b4',
                    point=True
                ).encode(
                    x=alt.X('log_date:T', title='Date'),
                    y=alt.Y('weight_kg:Q', title='Weight (kg)', scale=alt.Scale(domain=weight_domain, clamp=True)),
                    tooltip=['log_date', 'weight_kg']
                ).interactive()
                st.altair_chart(weight_chart, use_container_width=True)
            
            with col_info:
                st.markdown("**📊 Quick Stats**")
                latest_weight = df['weight_kg'].iloc[-1]
                initial_weight = df['weight_kg'].iloc[0]
                total_change = latest_weight - initial_weight
                days_tracked = len(df)
                
                st.metric("Current Weight", f"{latest_weight:.1f} kg")
                st.metric("Total Change", f"{total_change:+.1f} kg")
                st.metric("Days Tracked", f"{days_tracked}")
                
                st.info("💡 **Want detailed analytics?** Check out the Analytics page in the sidebar for comprehensive charts and insights!")
        else:
            st.info("Log at least two weight entries to see progress charts.")
            st.markdown("### 🔮 Coming Soon:")
            st.markdown("""
            - Weight trend visualization
            - Quick progress metrics  
            - Growth indicators
            
            **💡 Tip:** Visit the Analytics page (sidebar) for comprehensive visualizations once you have more data!
            """)

    with tab3:
        st.subheader("Model Confidence & Data Quality")
        confidence = user.adaptation_confidence
        st.progress(confidence, text=f"Model Confidence: {confidence:.2%}")
        st.markdown(f"Improve confidence by logging your weight and calories consistently.")
        dq = user.data_quality
        col_dq1, col_dq2, col_dq3 = st.columns(3)
        col_dq1.metric("Total Logs", dq.total_days_logged)
        col_dq2.metric("Weight Consistency", f"{dq.weight_consistency_score:.2f}/1.0")
        col_dq3.metric("Calorie Consistency", f"{dq.calorie_consistency_score:.2f}/1.0")

    with tab4:
        st.subheader("Adaptation History")
        if not user.adaptation_history:
            st.info("No adaptations have been made yet.")
        else:
            for i, record in enumerate(reversed(user.adaptation_history)):
                with st.expander(f"**{record['date']}**: Goal changed to {record['new_goal']} kcal", expanded=(i==0)):
                    st.markdown(f"**Change**: {record['change']:+d} kcal")
                    st.markdown(f"**Reason**: {record['reason']}")
                    st.markdown(f"**Confidence**: {record['confidence']:.2%}")

def login_page():
    """Page for user selection or starting onboarding."""
    st.title("Welcome to the Adaptive Nutrition Tracker")
    if not st.session_state.db:
        st.info("No users found. Let's get you started!")
        if st.button("Create a New Profile", type="primary", use_container_width=True):
            st.session_state.page = "onboarding"
            st.rerun()
    else:
        st.subheader("Select a User Profile")
        
        # Create a mapping from a display string to the user_id, safely accessing name
        user_options = {
            f"{getattr(user, 'name', 'User')} (...{uid[-6:]})": uid 
            for uid, user in st.session_state.db.items()
        }
        
        selected_display = st.selectbox("Choose a user to continue:", list(user_options.keys()))
        
        if st.button("Login", use_container_width=True):
            selected_user_id = user_options[selected_display]
            st.session_state.user_id = selected_user_id
            st.session_state.page = "dashboard"
            st.rerun()
            
        st.divider()
        if st.button("Create a New Profile", use_container_width=True):
            st.session_state.page = "onboarding"
            st.rerun()

def run_app():
    """Main function to run the Streamlit app."""
    st.set_page_config(page_title="Adaptive Nutrition", layout="wide")

    if "page" not in st.session_state: st.session_state.page = "login"
    if "db" not in st.session_state: st.session_state.db = {}
    if "user_id" not in st.session_state: st.session_state.user_id = None
    
    # Ensure main.db always points to session state db
    # This handles cases where the module might be reloaded but session state persists
    main.db = st.session_state.db
    
    # We also need to slightly adjust how the backend db is patched
    # to make sure the name change is compatible.
    if "main_initialized" not in st.session_state:
        # We need to monkey-patch the create_user function in main
        original_create_user = main.create_user
        def patched_create_user(profile: UserProfile, start_weight_kg: float, name: str):
            import uuid
            user_id = str(uuid.uuid4())
            initial_tdee = tdee_logic.calculate_initial_tdee(profile, start_weight_kg)
            daily_adj = (profile.goal_kg_per_week * kalman_filter_model.CALORIES_PER_KG) / 7
            initial_goal = int(initial_tdee + daily_adj)
            
            # Calculate initial macro targets
            initial_macro_targets = tdee_logic.calculate_macro_targets(
                initial_goal, profile, start_weight_kg
            )

            new_user = User(
                user_id=user_id,
                name=name,
                profile=profile,
                initial_calorie_goal=initial_goal,
                adapted_calorie_goal=initial_goal,
                macro_targets=initial_macro_targets,
                kf_tdee_estimate=initial_tdee,
            )
            # Use the global main.db which we ensured points to st.session_state.db
            main.db[user_id] = new_user
            return user_id

        main.create_user = patched_create_user
        st.session_state.main_initialized = True


    if st.session_state.page == "login": login_page()
    elif st.session_state.page == "onboarding": onboarding_page()
    elif st.session_state.page == "dashboard" and st.session_state.user_id: dashboard_page()
    else:
        st.session_state.page = "login"
        st.rerun()

if __name__ == "__main__":
    run_app()


