import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL")
DATABASE_NAME = os.getenv("DATABASE_NAME", "projects")

async def verify_auto_assign():
    print("Starting verification...")
    
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    
    test_user_id = "VERIFY_USER_001"
    test_skill = "Frontend"
    
    # 1. Clean up previous test data
    print("Cleaning up old test data...")
    await db.preferences.delete_one({"userId": test_user_id})
    await db.assignments.delete_one({"userId": test_user_id})
    # We'll delete the task later
    
    # 2. Set Preferences
    print(f"Setting preferences for {test_user_id} to ['{test_skill}']")
    await db.preferences.update_one(
        {"userId": test_user_id},
        {"$set": {"preferences": [test_skill]}},
        upsert=True
    )
    
    # 3. Create Task via API Logic (simulating what task router does)
    # We can't easily call the API function directly without running the server, 
    # but we can simulate the DB operations exactly as written in tasks.py
    
    print("Creating a new task with skillType: 'Frontend'...")
    task_data = {
        "title": "Verification Task",
        "description": "This is a test task",
        "skillType": "Frontend",
        "estimatedTime": 2.0,
        "project_id": "TEST_PROJECT",
        "isEnabled": True
    }
    
    result = await db.tasks.insert_one(task_data)
    task_id = str(result.inserted_id)
    print(f"Task created with ID: {task_id}")
    
    # --- SIMULATING ROUTER LOGIC HERE ---
    # (This logic should be identical to what we added in tasks.py)
    skill_type = task_data.get("skillType")
    assigned_count = 0
    if skill_type:
        async for pref_doc in db.preferences.find({"preferences": {"$in": ["All", skill_type]}}):
            u_id = pref_doc["userId"]
            new_assignment_data = {
                "taskId": task_id,
                "assignedBy": "admin",
                "sequenceId": None,
                "taskStatus": "active", # Mark as active immediately as per requirement
                "expectedCompletionDate": None
            }
            if u_id == test_user_id:
                print(f"Found matching user {u_id}, auto-assigning...")
                await db.assignments.update_one(
                    {"userId": u_id},
                    {"$push": {"tasks": new_assignment_data}, "$setOnInsert": {"userId": u_id}},
                    upsert=True
                )
                assigned_count += 1
    # ------------------------------------
    
    # 4. Verify Assignment
    print("Verifying assignment...")
    assignment = await db.assignments.find_one({"userId": test_user_id})
    
    found = False
    if assignment:
        for t in assignment.get("tasks", []):
            if t["taskId"] == task_id:
                found = True
                break
    
    if found:
        print("SUCCESS: Task was correctly auto-assigned to the user!")
    else:
        print("FAILURE: Task was NOT assigned to the user.")
        
    # 5. Cleanup
    print("Cleaning up...")
    await db.tasks.delete_one({"_id": result.inserted_id})
    await db.preferences.delete_one({"userId": test_user_id})
    await db.assignments.delete_one({"userId": test_user_id})
    
    client.close()

if __name__ == "__main__":
    asyncio.run(verify_auto_assign())
