from fastapi import APIRouter, Request, Body, HTTPException
from models import UserPreferences
from utils.helpers import serialize
from datetime import datetime
from pydantic import BaseModel
from typing import List

router = APIRouter()

class ManagePreferencesRequest(BaseModel):
    """Request model for managing preferences"""
    userId: str
    preferences: List[str]

class GetPreferencesRequest(BaseModel):
    """Request model for getting preferences"""
    userId: str

@router.post("/manage-preferences", status_code=200)
async def manage_preferences(request: Request, prefs_req: ManagePreferencesRequest = Body(...)):
    """
    Create or update preferences for a user.
    Preferences is stored as a list of strings.
    """
    db = request.app.state.db
    user_id = prefs_req.userId
    preferences = prefs_req.preferences

    print(f"📝 Managing preferences for user: {user_id}")
    print(f"Selected preferences: {preferences}")

    # Validate preferences based on allowed list (optional, but good practice)
    allowed_skills = ["All", "Frontend", "Backend", "AI", "ML", "Devops", "Data Analysis", "Data", "DSA", "Fullstack", "GenAI", "Analytics"]
    # Filter out any invalid skills just in case
    valid_preferences = [p for p in preferences if p in allowed_skills]
    
    # If "All" is selected, we might want to store just "All" or keep it as is. 
    # Storing exactly what user sent is safest.

    # Upsert preferences document
    result = await db.preferences.update_one(
        {"userId": user_id},
        {
            "$set": {
                "preferences": valid_preferences,
                "updated_at": datetime.now()
            },
            "$setOnInsert": {
                "created_at": datetime.now()
            }
        },
        upsert=True
    )

    # Fetch the updated/created preferences
    prefs_doc = await db.preferences.find_one({"userId": user_id})
    
    print(f"✅ Preferences {'updated' if result.modified_count > 0 else 'created'} successfully")
    

    # Insert proactive message from agent
    prefs_list = ", ".join(valid_preferences)
    proactive_msg = f"Looks like preferences has been set for {prefs_list}. From where do you want to start? Please choose from your preferences!"
    
    await db.chats.insert_one({
        "userId": user_id,
        "userType": "agent",
        "message": proactive_msg,
        "timestamp": datetime.now()
    })
    print(f"🤖 [AGENT] Proactive message added for user {user_id}")

    
    return {
        "status": "success",
        "message": f"Preferences {'updated' if result.modified_count > 0 else 'created'} successfully",
        "preferences": serialize(prefs_doc)
    }


@router.post("/get-preferences", status_code=200)
async def get_preferences(request: Request, prefs_req: GetPreferencesRequest = Body(...)):
    """
    Get preferences for a specific user.
    """
    db = request.app.state.db
    user_id = prefs_req.userId

    print(f"🔍 Fetching preferences for user: {user_id}")

    # Find preferences document
    prefs_doc = await db.preferences.find_one({"userId": user_id})
    
    if not prefs_doc:
        # Return empty preferences if not found
        return {
            "status": "success",
            "preferences": {
                "userId": user_id,
                "preferences": [],
                "isDefault": True
            }
        }
    
    print(f"✅ Preferences found")
    
    return {
        "status": "success",
        "preferences": serialize(prefs_doc)
    }
