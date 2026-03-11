import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import date, timedelta

from foodie.logic.models import UserProfile, LogEntry, User, MacroTargets, DataQualityMetrics
from foodie.logic.tdee_logic import calculate_initial_tdee, calculate_bmr_mifflin_st_jeor
from foodie.logic.kalman_filter_model import (
    run_full_kalman_update,
    CALORIES_PER_KG,
)


# --- SYNTHETIC DATA GENERATION ---

def generate_synthetic_user(
    true_tdee_start: float = 2400.0,
    true_tdee_end: float = 2250.0,
    days: int = 90,
    start_weight: float = 85.0,
    noise_std_weight: float = 0.4,
    noise_std_calories: float = 250.0,
    seed: int = 42,
) -> tuple:
    """
    Generate synthetic daily logs for a user whose *true* TDEE drifts linearly
    from ``true_tdee_start`` to ``true_tdee_end`` over ``days`` days.

    Returns (profile, logs, true_tdee_series).
    """
    rng = np.random.default_rng(seed)

    # Linear TDEE drift
    true_tdee = np.linspace(true_tdee_start, true_tdee_end, days)

    # The user targets a ~500 kcal deficit on average
    target_intake = true_tdee - 500

    # Simulate noisy calorie intake around the target
    calories_in = np.round(target_intake + rng.normal(0, noise_std_calories, days)).astype(int)
    calories_in = np.clip(calories_in, 800, 5000)

    # Simulate weight trajectory from energy balance + measurement noise
    weights = np.zeros(days)
    weights[0] = start_weight
    for i in range(1, days):
        energy_balance = calories_in[i - 1] - true_tdee[i - 1]  # kcal
        true_weight_change = energy_balance / CALORIES_PER_KG     # kg
        weights[i] = weights[i - 1] + true_weight_change + rng.normal(0, noise_std_weight)

    start_date = date.today() - timedelta(days=days)
    logs = [
        LogEntry(
            log_date=start_date + timedelta(days=i),
            weight_kg=round(float(weights[i]), 2),
            calories_in=int(calories_in[i]),
        )
        for i in range(days)
    ]

    profile = UserProfile(
        age=30,
        gender="male",
        height_cm=178.0,
        activity_level=1.55,
        goal_kg_per_week=-0.5,
        goal_weight_kg=75.0,
    )

    return profile, logs, true_tdee


# --- STATIC MODEL ---

def compute_static_tdee_series(profile: UserProfile, logs: list[LogEntry]) -> np.ndarray:
    """Return a per-day TDEE estimate using only the Mifflin-St Jeor formula
    (i.e. recalculated each day from that day's weight, but never learning
    from calorie / weight trends)."""
    return np.array([
        calculate_initial_tdee(profile, log.weight_kg) for log in logs
    ])


# --- KALMAN FILTER MODEL ---

def compute_kalman_tdee_series(
    profile: UserProfile, logs: list[LogEntry]
) -> np.ndarray:
    """Run the full Kalman filter over the logs and return per-day TDEE
    estimates (one per log entry, starting from the second)."""
    initial_tdee = calculate_initial_tdee(profile, logs[0].weight_kg)
    initial_goal = int(initial_tdee - 500)

    user = User(
        user_id="synthetic",
        name="Synthetic User",
        profile=profile,
        initial_calorie_goal=initial_goal,
        adapted_calorie_goal=initial_goal,
        macro_targets=MacroTargets(protein_g=150, carbs_g=200, fat_g=70),
        kf_tdee_estimate=initial_tdee,
        kf_tdee_uncertainty=50000.0,
        logs=list(logs),
    )

    # Walk day-by-day to capture the evolving estimate
    estimates = [initial_tdee]  # day 0
    for end_idx in range(2, len(logs) + 1):
        partial_user = user.model_copy(deep=True)
        partial_user.logs = list(logs[:end_idx])
        partial_user.kf_tdee_estimate = initial_tdee
        partial_user.kf_tdee_uncertainty = 50000.0
        partial_user.total_adaptations = 0
        updated = run_full_kalman_update(partial_user)
        estimates.append(updated.kf_tdee_estimate)

    return np.array(estimates)


# --- STREAMLIT PAGE ---

def performance_page():
    """Model performance comparison: Static formula vs Kalman Filter."""
    st.title("⚡ Model Performance")
    st.markdown(
        "Compare the adaptive **Kalman Filter** TDEE estimator against a "
        "simple **formula-based (static)** model on synthetic data with a "
        "known ground-truth TDEE."
    )

    # --- Sidebar-style controls ---
    st.subheader("Simulation Parameters")
    col1, col2, col3 = st.columns(3)
    with col1:
        days = st.slider("Simulation days", 30, 180, 90)
        seed = st.number_input("Random seed", value=42, step=1)
    with col2:
        tdee_start = st.number_input("True TDEE start (kcal)", value=2400, step=50)
        tdee_end = st.number_input("True TDEE end (kcal)", value=2250, step=50)
    with col3:
        weight_noise = st.slider("Weight noise σ (kg)", 0.0, 1.5, 0.4, 0.1)
        cal_noise = st.slider("Calorie noise σ (kcal)", 50, 500, 250, 50)

    if st.button("Run Simulation", type="primary", use_container_width=True):
        with st.spinner("Generating synthetic data & running models …"):
            profile, logs, true_tdee = generate_synthetic_user(
                true_tdee_start=float(tdee_start),
                true_tdee_end=float(tdee_end),
                days=int(days),
                noise_std_weight=float(weight_noise),
                noise_std_calories=float(cal_noise),
                seed=int(seed),
            )

            static_tdee = compute_static_tdee_series(profile, logs)
            kalman_tdee = compute_kalman_tdee_series(profile, logs)

        dates = [log.log_date for log in logs]

        # --- Build comparison DataFrame ---
        df = pd.DataFrame({
            "Date": dates,
            "True TDEE": true_tdee,
            "Static Model": static_tdee,
            "Kalman Filter": kalman_tdee,
        })

        df_long = df.melt(
            id_vars="Date",
            value_vars=["True TDEE", "Static Model", "Kalman Filter"],
            var_name="Model",
            value_name="TDEE (kcal)",
        )

        # --- Chart ---
        st.subheader("TDEE Estimates Over Time")
        color_scale = alt.Scale(
            domain=["True TDEE", "Static Model", "Kalman Filter"],
            range=["#2ca02c", "#ff7f0e", "#1f77b4"],
        )

        line_chart = (
            alt.Chart(df_long)
            .mark_line(strokeWidth=2.5)
            .encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y(
                    "TDEE (kcal):Q",
                    title="TDEE (kcal)",
                    scale=alt.Scale(zero=False),
                ),
                color=alt.Color("Model:N", scale=color_scale, legend=alt.Legend(title="Model")),
                strokeDash=alt.condition(
                    alt.datum.Model == "True TDEE",
                    alt.value([5, 5]),
                    alt.value([0]),
                ),
                tooltip=["Date:T", "Model:N", alt.Tooltip("TDEE (kcal):Q", format=".0f")],
            )
            .interactive()
            .properties(height=420)
        )
        st.altair_chart(line_chart, use_container_width=True)

        # --- Error metrics ---
        st.subheader("Error Metrics")
        static_err = static_tdee - true_tdee
        kalman_err = kalman_tdee - true_tdee

        metric_df = pd.DataFrame({
            "Metric": ["MAE (kcal)", "RMSE (kcal)", "Max |Error| (kcal)", "Mean Bias (kcal)"],
            "Static Model": [
                f"{np.mean(np.abs(static_err)):.1f}",
                f"{np.sqrt(np.mean(static_err**2)):.1f}",
                f"{np.max(np.abs(static_err)):.1f}",
                f"{np.mean(static_err):+.1f}",
            ],
            "Kalman Filter": [
                f"{np.mean(np.abs(kalman_err)):.1f}",
                f"{np.sqrt(np.mean(kalman_err**2)):.1f}",
                f"{np.max(np.abs(kalman_err)):.1f}",
                f"{np.mean(kalman_err):+.1f}",
            ],
        })

        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.markdown("##### Static Model")
            st.metric("MAE", f"{np.mean(np.abs(static_err)):.1f} kcal")
            st.metric("RMSE", f"{np.sqrt(np.mean(static_err**2)):.1f} kcal")
        with col_m2:
            st.markdown("##### Kalman Filter")
            st.metric("MAE", f"{np.mean(np.abs(kalman_err)):.1f} kcal")
            st.metric("RMSE", f"{np.sqrt(np.mean(kalman_err**2)):.1f} kcal")

        st.dataframe(metric_df, use_container_width=True, hide_index=True)

        # --- Error over time chart ---
        st.subheader("Absolute Error Over Time")
        err_df = pd.DataFrame({
            "Date": dates,
            "Static Model": np.abs(static_err),
            "Kalman Filter": np.abs(kalman_err),
        })
        err_long = err_df.melt(
            id_vars="Date",
            value_vars=["Static Model", "Kalman Filter"],
            var_name="Model",
            value_name="|Error| (kcal)",
        )
        err_chart = (
            alt.Chart(err_long)
            .mark_area(opacity=0.35, line=True)
            .encode(
                x=alt.X("Date:T", title="Date"),
                y=alt.Y("|Error| (kcal):Q", title="Absolute Error (kcal)"),
                color=alt.Color(
                    "Model:N",
                    scale=alt.Scale(
                        domain=["Static Model", "Kalman Filter"],
                        range=["#ff7f0e", "#1f77b4"],
                    ),
                ),
                tooltip=["Date:T", "Model:N", alt.Tooltip("|Error| (kcal):Q", format=".0f")],
            )
            .interactive()
            .properties(height=300)
        )
        st.altair_chart(err_chart, use_container_width=True)

        # --- Synthetic data preview ---
        with st.expander("📋 Synthetic data preview"):
            preview_df = pd.DataFrame({
                "Date": dates,
                "Weight (kg)": [log.weight_kg for log in logs],
                "Calories In": [log.calories_in for log in logs],
                "True TDEE": np.round(true_tdee, 1),
                "Static TDEE": np.round(static_tdee, 1),
                "Kalman TDEE": np.round(kalman_tdee, 1),
            })
            st.dataframe(preview_df, use_container_width=True, hide_index=True)
