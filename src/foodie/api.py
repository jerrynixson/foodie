from fastapi import FastAPI
from foodie.logic.adaptive_service import app as adaptive_app
from foodie.logic.food_db import app as food_db_app

# Create the unified application
app = FastAPI(
    title="Foodie Unified API",
    description="Combined API for Adaptive Nutrition and Crowdsourced Food Database",
    version="1.0.0"
)

# Include routers from the sub-applications
# Note: We are including the routers from the existing FastAPI apps.
# This merges their endpoints into the main app.
app.include_router(adaptive_app.router)
app.include_router(food_db_app.router)

@app.get("/")
def root():
    return {
        "message": "Welcome to the Foodie Unified API",
        "endpoints": {
            "adaptive_nutrition": "/v1/users",
            "food_database": "/foods/query"
        }
    }
