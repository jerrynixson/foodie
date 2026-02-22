import streamlit as st
import pandas as pd
from datetime import date, timedelta
import math
from typing import List
import altair as alt

# Backend imports
from foodie.logic.models import UserProfile, LogEntry, User, FoodItem
import foodie.logic.tdee_logic as tdee_logic
import foodie.logic.kalman_filter_model as kalman_filter_model
import foodie.logic.adaptive_service as main
from foodie.pages.add_food import add_food_dialog

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------

def calculate_time_to_goal(user: User):
    if not user.logs:
        return "Not enough data", "Log your weight to begin."

    current_weight = user.logs[-1].weight_kg
    goal_weight = user.profile.goal_weight_kg
    target_rate = user.profile.goal_kg_per_week
    weight_to_change = current_weight - goal_weight

    if abs(weight_to_change) < 0.1:
        return "Goal Reached!", "You've reached your goal."

    estimated_weeks = abs(weight_to_change / target_rate) if target_rate != 0 else float('inf')
    estimated_days = int(estimated_weeks * 7)
    return f"{estimated_weeks:.1f} weeks", f"~{estimated_days} days remaining"


def get_daily_food_summary(food_items: List[FoodItem], log_date: date):
    daily_items = [i for i in food_items if i.log_date == log_date]
    return {
        "calories": sum(i.calories for i in daily_items),
        "protein": sum(i.protein for i in daily_items),
        "carbs": sum(i.carbs for i in daily_items),
        "fat": sum(i.fat for i in daily_items),
    }

# -----------------------------
# DASHBOARD PAGE
# -----------------------------

def dashboard_page():
    user = st.session_state.db.get(st.session_state.user_id)
    if not user:
        st.error("User not found"); return

    st.sidebar.header(f"Hey {user.name} 👋")
    if st.sidebar.button("Logout"):
        st.session_state.page = "login"
        st.rerun()

    st.title("Your Adaptive Nutrition Dashboard")

    if "diary_date" not in st.session_state:
        st.session_state.diary_date = date.today()

    c1, c2, c3 = st.columns([1,2,1])
    if c1.button("◀ Previous"): st.session_state.diary_date -= timedelta(days=1)
    st.session_state.diary_date = c2.date_input("Date", st.session_state.diary_date, label_visibility="collapsed")
    if c3.button("Next ▶"): st.session_state.diary_date += timedelta(days=1)

    # -----------------------------
    # DAILY SUMMARY
    # -----------------------------
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Daily Summary")
        summary = get_daily_food_summary(user.food_items, st.session_state.diary_date)

        goal = user.adapted_calorie_goal
        maintenance = int(user.kf_tdee_estimate)
        st.metric("Calorie Goal", f"{goal} kcal", f"{goal-maintenance:+} vs maintenance")

        st.progress(min(summary["calories"]/goal if goal else 0, 1.0))
        m1, m2, m3 = st.columns(3)
        m1.metric("Protein", f"{summary['protein']:.1f} g")
        m2.metric("Carbs", f"{summary['carbs']:.1f} g")
        m3.metric("Fat", f"{summary['fat']:.1f} g")

    with col2:
        st.subheader("Log Weight")
        today_log = next((l for l in user.logs if l.log_date == st.session_state.diary_date), None)

        if today_log:
            st.success(f"Logged: {today_log.weight_kg} kg")
        else:
            with st.form("weight_form"):
                w = st.number_input("Weight (kg)", value=user.logs[-1].weight_kg if user.logs else 70.0, step=0.1)
                if st.form_submit_button("Log"):
                    user.logs.append(LogEntry(
                        log_date=st.session_state.diary_date,
                        weight_kg=w,
                        calories_in=summary["calories"]
                    ))
                    user.logs.sort(key=lambda x: x.log_date)
                    kalman_filter_model.run_full_kalman_update(user)
                    main.adapt_user_goals(user.user_id)
                    st.rerun()

    st.divider()

    # -----------------------------
    # FOOD DIARY
    # -----------------------------
    st.header("Food Diary")
    meals = ["Breakfast", "Lunch", "Dinner", "Snacks"]
    cols = st.columns(4)

    for col, meal in zip(cols, meals):
        with col:
            st.subheader(meal)
            items = [i for i in user.food_items if i.log_date == st.session_state.diary_date and i.meal_type == meal]
            for item in items:
                st.write(f"• {item.name} ({item.calories} kcal)")
            if st.button(f"+ Add {meal}", key=meal):
                add_food_dialog(user, meal, st.session_state.diary_date)

    st.divider()

    # -----------------------------
    # TABS
    # -----------------------------
    tab1, tab2, tab3 = st.tabs(["📊 Progress Dashboard", "🧠 Adaptation", "📜 History"])

    # =============================
    # PROGRESS DASHBOARD
    # =============================
    with tab1:
        if len(user.logs) < 2:
            st.info("Log more days to unlock insights.")
        else:
            df = pd.DataFrame([l.model_dump() for l in user.logs])
            df["log_date"] = pd.to_datetime(df["log_date"])
            df = df.sort_values("log_date")

            df["calories_out"] = user.kf_tdee_estimate
            df["net_calories"] = df["calories_in"] - df["calories_out"]

            # KPI ROW
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Latest Weight", f"{df.weight_kg.iloc[-1]:.1f} kg")
            k2.metric("Avg Intake", f"{df.calories_in.mean():.0f} kcal")
            k3.metric("Est Burn", f"{df.calories_out.mean():.0f} kcal")
            k4.metric("Net Calories", f"{df.net_calories.mean():+.0f} kcal")

            st.divider()

            # Weight Trend
            st.subheader("📉 Weight Trend")
            st.altair_chart(
                alt.Chart(df).mark_line(point=True).encode(
                    x="log_date:T",
                    y="weight_kg:Q",
                    tooltip=["log_date", "weight_kg"]
                ),
                use_container_width=True
            )

            # Intake vs Burn
            st.subheader("🔥 Intake vs Burn")
            st.altair_chart(
                alt.Chart(df).transform_fold(
                    ["calories_in", "calories_out"],
                    as_=["Type", "Calories"]
                ).mark_line(point=True).encode(
                    x="log_date:T",
                    y="Calories:Q",
                    color="Type:N"
                ),
                use_container_width=True
            )

            # Net Calories
            st.subheader("⚖ Net Calories")
            st.altair_chart(
                alt.Chart(df).mark_bar().encode(
                    x="log_date:T",
                    y="net_calories:Q",
                    color=alt.condition(
                        alt.datum.net_calories > 0,
                        alt.value("red"),
                        alt.value("green")
                    )
                ),
                use_container_width=True
            )

            # Weekly Weight Change
            df["week"] = df["log_date"].dt.to_period("W").astype(str)
            weekly = df.groupby("week").agg(
                change=("weight_kg", lambda x: x.iloc[-1] - x.iloc[0])
            ).reset_index()

            st.subheader("📆 Weekly Weight Change")
            st.altair_chart(
                alt.Chart(weekly).mark_bar().encode(
                    x="week:N",
                    y="change:Q",
                    color=alt.condition(
                        alt.datum.change < 0,
                        alt.value("green"),
                        alt.value("red")
                    )
                ),
                use_container_width=True
            )

            st.success("Consistency beats perfection. Keep logging!")

    # =============================
    # ADAPTATION DETAILS
    # =============================
    with tab2:
        st.progress(user.adaptation_confidence)
        dq = user.data_quality
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Logs", dq.total_days_logged)
        c2.metric("Weight Consistency", f"{dq.weight_consistency_score:.2f}")
        c3.metric("Calorie Consistency", f"{dq.calorie_consistency_score:.2f}")

    # =============================
    # HISTORY
    # =============================
    with tab3:
        for r in reversed(user.adaptation_history):
            st.write(f"{r['date']} → {r['new_goal']} kcal")

# -----------------------------
# LOGIN + ROUTER
# -----------------------------

def login_page():
    st.title("Adaptive Nutrition Tracker")
    if not st.session_state.db:
        if st.button("Create Profile"):
            st.session_state.page = "onboarding"
    else:
        user = list(st.session_state.db.values())[0]
        if st.button("Login"):
            st.session_state.user_id = user.user_id
            st.session_state.page = "dashboard"


def run_app():
    st.set_page_config("Adaptive Nutrition", layout="wide")
    if "page" not in st.session_state: st.session_state.page = "login"
    if "db" not in st.session_state: st.session_state.db = {}
    if "user_id" not in st.session_state: st.session_state.user_id = None
    main.db = st.session_state.db

    if st.session_state.page == "login": login_page()
    if st.session_state.page == "dashboard": dashboard_page()


if __name__ == "__main__":
    run_app()
