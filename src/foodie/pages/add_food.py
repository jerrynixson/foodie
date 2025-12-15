import streamlit as st
import time
from foodie.logic.models import User, FoodItem
from foodie.logic.food_db import search_foods
from datetime import date

@st.dialog("Add Food Item")
def add_food_dialog(user: User, meal_type: str, log_date: date):
    """A dialog to add a new food item with search functionality."""
    st.subheader(f"Add to {meal_type}")
    
    # Initialize session state for search if not present
    if "search_query" not in st.session_state:
        st.session_state.search_query = ""
    if "search_results" not in st.session_state:
        st.session_state.search_results = []
    if "last_selected_food" not in st.session_state:
        st.session_state.last_selected_food = "Select..."

    # Search Input
    # We use a key to track the input value in session state
    query = st.text_input("Search for a food", placeholder="e.g., 'Chicken'", key="food_search_input")
    
    # Check if query changed to trigger search
    # Note: st.text_input updates session_state['food_search_input'] on enter/blur
    if query != st.session_state.search_query:
        st.session_state.search_query = query
        if query:
            with st.spinner("Searching..."):
                time.sleep(2) # Debounce simulation
                try:
                    # Call the API function
                    results = search_foods(q=query, limit=10, offset=0)
                    st.session_state.search_results = results
                except Exception as e:
                    st.error(f"Search failed: {e}")
                    st.session_state.search_results = []
        else:
            st.session_state.search_results = []

    # Process Results for Dropdown
    options = {}
    if st.session_state.search_results:
        for food in st.session_state.search_results:
            food_name = food.get("food_name", "Unknown")
            variants = food.get("variants", [])
            for variant in variants:
                label = variant.get("variant_label", "Standard")
                # Format: "food_name variant_label"
                display_name = f"{food_name} {label}"
                options[display_name] = {
                    "name": display_name,
                    "nutrients": variant.get("nutrients", {})
                }
    
    # Dropdown Selection
    # We use a key to track selection
    selected_item_name = st.selectbox("Select Item", options=["Select..."] + list(options.keys()), key="food_search_select")
    
    # Auto-populate logic
    if selected_item_name != st.session_state.last_selected_food:
        st.session_state.last_selected_food = selected_item_name
        if selected_item_name != "Select..." and selected_item_name in options:
            item_data = options[selected_item_name]
            st.session_state.form_name = item_data["name"]
            nutrients = item_data["nutrients"] or {}
            st.session_state.form_cals = int(nutrients.get("calories", 0) or 0)
            st.session_state.form_prot = float(nutrients.get("protein", 0) or 0)
            st.session_state.form_carbs = float(nutrients.get("carbs", 0) or 0)
            st.session_state.form_fat = float(nutrients.get("fat", 0) or 0)

    # Initialize form fields if not present (e.g. first load)
    if "form_name" not in st.session_state: st.session_state.form_name = ""
    if "form_cals" not in st.session_state: st.session_state.form_cals = 0
    if "form_prot" not in st.session_state: st.session_state.form_prot = 0.0
    if "form_carbs" not in st.session_state: st.session_state.form_carbs = 0.0
    if "form_fat" not in st.session_state: st.session_state.form_fat = 0.0

    st.info("Please verify or enter nutritional information manually below.")

    with st.form("add_food_form"):
        name_val = st.text_input("Food Name*", value=st.session_state.form_name, placeholder="e.g., 'Chicken Breast'")
        calories_val = st.number_input("Calories*", min_value=0, step=10, value=st.session_state.form_cals)
        protein_val = st.number_input("Protein (g)", min_value=0.0, step=0.1, format="%.1f", value=st.session_state.form_prot)
        carbs_val = st.number_input("Carbs (g)", min_value=0.0, step=0.1, format="%.1f", value=st.session_state.form_carbs)
        fat_val = st.number_input("Fat (g)", min_value=0.0, step=0.1, format="%.1f", value=st.session_state.form_fat)

        submitted = st.form_submit_button("Add Item", use_container_width=True)
        
    if st.session_state.get("add_food_error"):
        st.error(st.session_state.add_food_error)
        
    # Process form submission after form is rendered
    if submitted:
        if not name_val or calories_val is None:
            st.session_state.add_food_error = "Food Name and Calories are required."
            st.rerun()
        else:
            new_food = FoodItem(
                log_date=log_date,
                name=name_val,
                meal_type=meal_type,
                calories=calories_val,
                protein=protein_val,
                carbs=carbs_val,
                fat=fat_val,
            )
            user.food_items.append(new_food)
            
            # Delete keys from session state to avoid widget key conflicts
            for key in ["form_name", "form_cals", "form_prot", "form_carbs", "form_fat",
                       "food_search_input", "search_query", "search_results", 
                       "last_selected_food", "food_search_select", "add_food_error"]:
                if key in st.session_state:
                    del st.session_state[key]
            
            # Rerun to close dialog and update UI
            st.rerun()
