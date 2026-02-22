import streamlit as st
import pandas as pd
import altair as alt
from datetime import date
from typing import List
from foodie.logic.models import User, LogEntry

def visualizations_page():
    """Comprehensive visualizations and analytics page."""
    user = st.session_state.db.get(st.session_state.user_id)
    if not user:
        st.error("User not found.")
        st.session_state.page = "login"
        st.rerun()

    user_name = getattr(user, 'name', 'User')
    st.title(f"📊 {user_name}'s Progress Analytics")
    st.markdown("Track your journey with detailed charts and insights.")

    if len(user.logs) < 2:
        st.info("📈 Log at least 2 days of data to unlock comprehensive analytics!")
        st.markdown("""
        ### What you'll see here once you have more data:
        - **KPI Dashboard**: Key metrics at a glance
        - **Weight Trends**: Track your progress over time  
        - **Calorie Balance**: See intake vs expenditure patterns
        - **Weekly Analysis**: Understand your weekly patterns
        - **Net Calorie Impact**: Visualize surplus/deficit trends
        """)
        return

    # Prepare data for visualizations
    df = pd.DataFrame([log.model_dump() for log in user.logs])
    df["log_date"] = pd.to_datetime(df["log_date"])
    df = df.sort_values("log_date")
    
    df["calories_out"] = user.kf_tdee_estimate
    df["net_calories"] = df["calories_in"] - df["calories_out"]

    # === KPI DASHBOARD ===
    st.header("🎯 Key Performance Indicators")
    st.markdown("Your essential metrics at a glance")
    
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    
    latest_weight = df.weight_kg.iloc[-1]
    avg_intake = df.calories_in.mean()
    est_burn = df.calories_out.mean()
    net_calories = df.net_calories.mean()
    
    # Calculate trends for delta indicators
    if len(df) >= 7:
        recent_weight_trend = df.weight_kg.iloc[-7:].mean() - df.weight_kg.iloc[-14:-7].mean() if len(df) >= 14 else 0
        recent_intake_trend = df.calories_in.iloc[-7:].mean() - df.calories_in.iloc[-14:-7].mean() if len(df) >= 14 else 0
    else:
        recent_weight_trend = 0
        recent_intake_trend = 0
    
    with kpi1:
        st.metric(
            "📏 Latest Weight", 
            f"{latest_weight:.1f} kg",
            delta=f"{recent_weight_trend:+.1f} kg (7d avg)" if recent_weight_trend != 0 else None
        )
    
    with kpi2:
        st.metric(
            "🍽️ Avg Daily Intake", 
            f"{avg_intake:.0f} kcal",
            delta=f"{recent_intake_trend:+.0f} kcal (7d)" if recent_intake_trend != 0 else None
        )
    
    with kpi3:
        st.metric(
            "🔥 Est. Daily Burn", 
            f"{est_burn:.0f} kcal"
        )
    
    with kpi4:
        net_color = "normal" if abs(net_calories) < 200 else ("inverse" if net_calories > 0 else "normal")
        st.metric(
            "⚖️ Net Balance", 
            f"{net_calories:+.0f} kcal",
            help="Positive = surplus, Negative = deficit"
        )

    st.divider()

    # === WEIGHT TREND ANALYSIS ===
    st.header("📈 Weight Trend Analysis")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.markdown("**Your weight journey over time**")
        
        # Enhanced weight chart with trend line
        min_weight = df['weight_kg'].min()
        max_weight = df['weight_kg'].max()
        weight_buffer = max((max_weight - min_weight) * 0.1, 1)
        weight_domain = [min_weight - weight_buffer, max_weight + weight_buffer]

        base_chart = alt.Chart(df).add_selection(
            alt.selection_interval(bind='scales')
        )
        
        weight_line = base_chart.mark_line(
            color='#1f77b4',
            strokeWidth=3,
            point=alt.OverlayMarkDef(filled=True, size=100, color='#1f77b4')
        ).encode(
            x=alt.X('log_date:T', title='Date'),
            y=alt.Y('weight_kg:Q', title='Weight (kg)', scale=alt.Scale(domain=weight_domain)),
            tooltip=['log_date:T', 'weight_kg:Q']
        )
        
        # Add trend line if enough data points
        if len(df) >= 5:
            trend_line = base_chart.mark_line(
                color='red',
                strokeDash=[5, 5],
                strokeWidth=2
            ).transform_regression(
                'log_date', 'weight_kg'
            ).encode(
                x='log_date:T',
                y='weight_kg:Q'
            )
            weight_chart = weight_line + trend_line
        else:
            weight_chart = weight_line
            
        st.altair_chart(weight_chart, use_container_width=True)
    
    with col2:
        st.markdown("**Key Insights**")
        
        # Calculate weight change statistics
        total_change = latest_weight - df.weight_kg.iloc[0]
        days_tracked = len(df)
        avg_weekly_change = (total_change / days_tracked) * 7 if days_tracked > 0 else 0
        
        goal_weight = user.profile.goal_weight_kg
        weight_to_goal = latest_weight - goal_weight
        
        st.metric("📊 Total Change", f"{total_change:+.1f} kg")
        st.metric("📅 Days Tracked", f"{days_tracked}")
        st.metric("⏱️ Avg Weekly Rate", f"{avg_weekly_change:+.1f} kg/week")
        st.metric("🎯 To Goal", f"{weight_to_goal:+.1f} kg")
        
        if abs(weight_to_goal) < 0.5:
            st.success("🎉 Very close to goal!")
        elif weight_to_goal * user.profile.goal_kg_per_week < 0:
            st.info("📈 On track to goal!")

    st.divider()

    # === CALORIE BALANCE ANALYSIS ===
    st.header("🔥 Calorie Balance Analysis")
    
    tab1, tab2 = st.tabs(["📊 Intake vs Burn", "⚖️ Daily Net Balance"])
    
    with tab1:
        st.markdown("**Daily calorie intake vs estimated expenditure**")
        
        # Intake vs Burn Chart
        intake_burn_chart = alt.Chart(df).transform_fold(
            ["calories_in", "calories_out"],
            as_=["Type", "Calories"]
        ).mark_line(
            point=True,
            strokeWidth=3
        ).encode(
            x=alt.X('log_date:T', title='Date'),
            y=alt.Y('Calories:Q', title='Calories'),
            color=alt.Color(
                'Type:N', 
                title='Type',
                scale=alt.Scale(
                    domain=['calories_in', 'calories_out'],
                    range=['#ff6b6b', '#4ecdc4']
                ),
                legend=alt.Legend(
                    symbolType='circle',
                    symbolSize=100,
                    labelFontSize=12
                )
            ),
            tooltip=['log_date:T', 'Type:N', 'Calories:Q']
        ).interactive()
        
        st.altair_chart(intake_burn_chart, use_container_width=True)
        
        # Balance insights
        avg_deficit = df[df['net_calories'] < 0]['net_calories'].mean()
        avg_surplus = df[df['net_calories'] > 0]['net_calories'].mean()
        
        insight_col1, insight_col2, insight_col3 = st.columns(3)
        
        with insight_col1:
            deficit_days = len(df[df['net_calories'] < 0])
            st.metric("📉 Deficit Days", f"{deficit_days}/{len(df)}")
            
        with insight_col2:
            surplus_days = len(df[df['net_calories'] > 0])  
            st.metric("📈 Surplus Days", f"{surplus_days}/{len(df)}")
            
        with insight_col3:
            balanced_days = len(df[abs(df['net_calories']) < 100])
            st.metric("⚖️ Balanced Days", f"{balanced_days}/{len(df)}")

    with tab2:
        st.markdown("**Daily calorie surplus/deficit patterns**")
        
        # Net Calories Bar Chart  
        net_chart = alt.Chart(df).mark_bar().encode(
            x=alt.X('log_date:T', title='Date'),
            y=alt.Y('net_calories:Q', title='Net Calories (Intake - Burn)'),
            color=alt.condition(
                alt.datum.net_calories > 0,
                alt.value('#ff6b6b'),  # Red for surplus
                alt.value('#4ecdc4')   # Green for deficit  
            ),
            tooltip=['log_date:T', 'net_calories:Q', 'calories_in:Q', 'calories_out:Q']
        ).interactive()
        
        # Add zero line
        zero_line = alt.Chart(pd.DataFrame({'y': [0]})).mark_rule(
            strokeDash=[3, 3], 
            color='gray'
        ).encode(y='y:Q')
        
        combined_chart = net_chart + zero_line
        st.altair_chart(combined_chart, use_container_width=True)
        
        # Net calorie insights
        if not pd.isna(avg_deficit):
            st.info(f"📉 **Average deficit**: {avg_deficit:.0f} kcal on deficit days")
        if not pd.isna(avg_surplus):
            st.warning(f"📈 **Average surplus**: {avg_surplus:.0f} kcal on surplus days")

    st.divider()

    # === MACRO NUTRIENT TRACKING ===
    st.header("🧬 Macro Nutrient Analysis")
    
    if len(user.food_items) == 0:
        st.info("🥗 Start logging food to see your macro nutrient patterns!")
    else:
        # Prepare macro data
        macro_data = []
        for item in user.food_items:
            # Filter for recent days (last 30 days for macro analysis)
            if (date.today() - item.log_date).days <= 30:
                macro_data.append({
                    'date': item.log_date,
                    'protein': item.protein,
                    'carbs': item.carbs,
                    'fat': item.fat
                })
        
        if macro_data:
            macro_df = pd.DataFrame(macro_data)
            macro_df['date'] = pd.to_datetime(macro_df['date'])
            
            # Aggregate by day
            daily_macros = macro_df.groupby('date').agg({
                'protein': 'sum',
                'carbs': 'sum', 
                'fat': 'sum'
            }).reset_index()
            
            # Add targets for comparison
            daily_macros['protein_target'] = user.macro_targets.protein_g
            daily_macros['carbs_target'] = user.macro_targets.carbs_g
            daily_macros['fat_target'] = user.macro_targets.fat_g
            
            macro_col1, macro_col2 = st.columns([2, 1])
            
            with macro_col1:
                st.markdown("**Daily macro intake vs targets**")
                
                # Create macro tracking chart
                macro_chart_data = daily_macros.melt(
                    id_vars=['date'],
                    value_vars=['protein', 'carbs', 'fat', 'protein_target', 'carbs_target', 'fat_target'],
                    var_name='macro_type',
                    value_name='grams'
                )
                
                # Separate actual vs target data
                macro_chart_data['category'] = macro_chart_data['macro_type'].apply(
                    lambda x: 'Target' if 'target' in x else 'Actual'
                )
                macro_chart_data['macro'] = macro_chart_data['macro_type'].apply(
                    lambda x: x.replace('_target', '').title()
                )
                
                base_chart = alt.Chart(macro_chart_data).add_selection(
                    alt.selection_interval(bind='scales')
                )
                
                # Actual values as bars
                actual_bars = base_chart.transform_filter(
                    alt.datum.category == 'Actual'
                ).mark_bar(opacity=0.7).encode(
                    x=alt.X('date:T', title='Date'),
                    y=alt.Y('grams:Q', title='Grams'),
                    color=alt.Color('macro:N', 
                        scale=alt.Scale(
                            domain=['Protein', 'Carbs', 'Fat'],
                            range=['#4CAF50', '#FF9800', '#2196F3']
                        )
                    ),
                    tooltip=['date:T', 'macro:N', 'grams:Q']
                )
                
                # Target lines
                target_lines = base_chart.transform_filter(
                    alt.datum.category == 'Target'
                ).mark_line(strokeDash=[5, 5], strokeWidth=2).encode(
                    x='date:T',
                    y='grams:Q',
                    color=alt.Color('macro:N', 
                        scale=alt.Scale(
                            domain=['Protein', 'Carbs', 'Fat'],
                            range=['#388E3C', '#F57C00', '#1976D2']
                        )
                    ),
                    tooltip=['date:T', 'macro:N', 'grams:Q']
                )
                
                combined_macro_chart = actual_bars + target_lines
                st.altair_chart(combined_macro_chart, use_container_width=True)
            
            with macro_col2:
                st.markdown("**Macro Performance**")
                
                # Calculate average achievement rates
                recent_days = daily_macros.tail(7) if len(daily_macros) >= 7 else daily_macros
                
                protein_achievement = (recent_days['protein'] / recent_days['protein_target']).mean()
                carbs_achievement = (recent_days['carbs'] / recent_days['carbs_target']).mean()
                fat_achievement = (recent_days['fat'] / recent_days['fat_target']).mean()
                
                st.metric("🥩 Protein Achievement", f"{protein_achievement:.1%}")
                st.metric("🍞 Carbs Achievement", f"{carbs_achievement:.1%}")  
                st.metric("🥑 Fat Achievement", f"{fat_achievement:.1%}")
                
                # Overall macro balance
                overall_score = (protein_achievement + carbs_achievement + fat_achievement) / 3
                if overall_score >= 0.9:
                    st.success("🎯 Great macro balance!")
                elif overall_score >= 0.7:
                    st.info("👍 Good macro tracking")
                else:
                    st.warning("📊 Focus on hitting targets")
        else:
            st.info("📅 Log food for more than one day to see macro trends!")

    st.divider()

    # === WEEKLY PATTERN ANALYSIS ===
    st.header("📅 Weekly Pattern Analysis")
    
    if len(df) >= 7:
        st.markdown("**Weekly weight change patterns**")
        
        # Weekly Weight Change
        df_copy = df.copy()
        df_copy["week"] = df_copy["log_date"].dt.to_period("W").astype(str)
        weekly = df_copy.groupby("week").agg(
            weight_start=("weight_kg", "first"),
            weight_end=("weight_kg", "last"),
            avg_intake=("calories_in", "mean"),
            avg_net=("net_calories", "mean")
        ).reset_index()
        
        weekly["change"] = weekly["weight_end"] - weekly["weight_start"]
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            weekly_chart = alt.Chart(weekly).mark_bar().encode(
                x=alt.X('week:N', title='Week'),
                y=alt.Y('change:Q', title='Weight Change (kg)'),
                color=alt.condition(
                    alt.datum.change < 0,
                    alt.value('#4ecdc4'),  # Green for weight loss
                    alt.value('#ff6b6b')   # Red for weight gain
                ),
                tooltip=['week:N', 'change:Q', 'avg_intake:Q', 'avg_net:Q']
            ).interactive()
            
            st.altair_chart(weekly_chart, use_container_width=True)
        
        with col2:
            st.markdown("**Weekly Insights**")
            avg_weekly_change = weekly["change"].mean()
            best_week = weekly.loc[weekly["change"].idxmin()] if user.profile.goal_kg_per_week < 0 else weekly.loc[weekly["change"].idxmax()]
            
            st.metric("📊 Avg Weekly Change", f"{avg_weekly_change:+.2f} kg")
            st.metric("🏆 Best Week", f"{best_week['change']:+.2f} kg")
            st.metric("📝 Best Week Intake", f"{best_week['avg_intake']:.0f} kcal")
            
            # Goal comparison
            goal_weekly = user.profile.goal_kg_per_week
            if abs(avg_weekly_change - goal_weekly) <= 0.1:
                st.success("🎯 On target!")
            elif (goal_weekly < 0 and avg_weekly_change > goal_weekly) or (goal_weekly > 0 and avg_weekly_change < goal_weekly):
                st.warning("📈 Adjust intake")
            else:
                st.info("📊 Good progress")
    else:
        st.info("📅 Track for at least a week to see weekly patterns!")

    st.divider()

    # === SUCCESS METRICS ===
    st.header("🏆 Success Metrics")
    
    success_col1, success_col2, success_col3 = st.columns(3)
    
    with success_col1:
        st.markdown("**🎯 Goal Alignment**")
        goal_rate = user.profile.goal_kg_per_week
        actual_rate = avg_weekly_change if len(df) >= 7 else 0
        alignment_score = max(0, 100 - abs(actual_rate - goal_rate) * 100) if len(df) >= 7 else 0
        
        st.metric("Goal Alignment", f"{alignment_score:.0f}%")
        st.progress(alignment_score / 100)
        
    with success_col2:
        st.markdown("**📊 Consistency Score**")
        consistency = user.data_quality.weight_consistency_score * 100
        st.metric("Logging Consistency", f"{consistency:.0f}%")
        st.progress(consistency / 100)
        
    with success_col3:
        st.markdown("**🧠 Model Confidence**")
        confidence = user.adaptation_confidence * 100
        st.metric("AI Confidence", f"{confidence:.0f}%")
        st.progress(confidence / 100)

    # Motivational message
    st.success("🌟 **Keep it up!** Consistency beats perfection. Every log entry helps improve your personalized recommendations!")