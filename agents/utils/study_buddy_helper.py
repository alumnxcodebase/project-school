# agents/utils/study_buddy_helper.py

from datetime import datetime, timedelta
from bson import ObjectId

async def get_user_learning_state(db, user_id: str):
    """
    Fetch user's preferences, assignments, and current buddy status.
    """
    print(f"🔍 [DEBUG] get_user_learning_state for user_id: {user_id}")
    
    # 1. Fetch Preferences
    preferences_doc = await db.preferences.find_one({"userId": user_id})
    preferences = preferences_doc.get("preferences", []) if preferences_doc else []
    print(f"🔍 [DEBUG] Preferences found: {preferences}")
    
    # 2. Fetch Assignments
    assignment = await db.assignments.find_one({"userId": user_id})
    all_tasks = assignment.get("tasks", []) if assignment else []
    print(f"🔍 [DEBUG] Total tasks in assignment: {len(all_tasks)}")
    
    # Filter active and completed tasks
    active_tasks = [t for t in all_tasks if t.get("taskStatus") == "active"]
    # Fixed: Check for taskStatus == "completed"
    completed_tasks = [t for t in all_tasks if t.get("taskStatus") == "completed"]
    print(f"🔍 [DEBUG] Active: {len(active_tasks)}, Completed: {len(completed_tasks)}")
    
    # 3. Fetch Agent/User Meta (for scheduling)
    agent_meta = await db.agents.find_one({"userId": user_id})
    if agent_meta:
        print(f"🔍 [DEBUG] Agent meta found: name={agent_meta.get('agentName')}, status={agent_meta.get('buddy_status')}")
    else:
        print(f"🔍 [DEBUG] Agent meta NOT FOUND for {user_id}")
        
    buddy_status = agent_meta.get("buddy_status", "active") if agent_meta else "active"
    next_contact = agent_meta.get("next_buddy_contact_date") if agent_meta else None
    
    current_time = datetime.now()
    
    # Auto-reset if DND period has passed
    if buddy_status == "postponed" and next_contact and current_time > next_contact:
        print(f"⏰ DND period for {user_id} has expired! Resetting to active.")
        await update_buddy_status(db, user_id, "active")
        buddy_status = "active"
    
    return {
        "preferences": preferences,
        "active_tasks": active_tasks,
        "completed_tasks": completed_tasks,
        "buddy_status": buddy_status,
        "next_contact_date": next_contact,
        "current_time": current_time,
        "has_preferences": len(preferences) > 0,
        "has_active_tasks": len(active_tasks) > 0
    }

async def get_first_task_for_skill(db, skill_name: str, user_id: str):
    """
    Find the first task in the database for a specific skill that isn't already assigned to the user.
    Prioritizes tasks from assigned projects in their sequence order.
    """
    print(f"🔍 [DEBUG] get_first_task_for_skill: {skill_name} for user {user_id}")
    
    # Get user's current tasks to avoid duplicates
    assignment = await db.assignments.find_one({"userId": user_id})
    assigned_task_ids = []
    assigned_titles = []
    if assignment and assignment.get("tasks"):
        assigned_task_ids = [
            ObjectId(t["taskId"]) 
            for t in assignment["tasks"] 
            if t.get("taskId") and ObjectId.is_valid(t["taskId"])
        ]
        
        # Get titles to avoid duplicates (sometimes same task exists in different projects)
        if assigned_task_ids:
            existing_tasks = await db.tasks.find({"_id": {"$in": assigned_task_ids}}).to_list(100)
            assigned_titles = [t.get("title") for t in existing_tasks if t.get("title")]
    
    # 1. CHECK ASSIGNED PROJECTS IN SEQUENCE
    assigned_proj_docs = await db.assignedprojects.find({"userId": user_id}).sort("sequenceId", 1).to_list(100)
    
    for proj_doc in assigned_proj_docs:
        project_id = proj_doc["projectId"]
        print(f"🔍 [DEBUG] Checking assigned project: {project_id}")
        
        # Search for tasks in THIS project that match the skill
        task_query = {
            "$and": [
                {"project_id": project_id},
                {"_id": {"$nin": assigned_task_ids}},
                {"title": {"$nin": assigned_titles}},
                {
                    "$or": [
                        {"skillType": {"$regex": f"^{skill_name}$", "$options": "i"}},
                        {"category": {"$regex": f"^{skill_name}$", "$options": "i"}},
                        {"title": {"$regex": skill_name, "$options": "i"}}
                    ]
                }
            ]
        }
        
        candidate_tasks = await db.tasks.find(task_query).to_list(100)
        if candidate_tasks:
            import re
            def natural_sort_key(s):
                s = " ".join(s.split()).strip()
                return [int(text) if text.isdigit() else text.lower()
                        for text in re.split('([0-9]+)', s)]
            
            candidate_tasks.sort(key=lambda t: natural_sort_key(t.get("title", "")))
            task = candidate_tasks[0]
            print(f"✅ Found task in assigned project {project_id}: {task.get('title')}")
            return task

    # 2. IF NOT FOUND IN ASSIGNED PROJECTS, SEARCH ALL PROJECTS MATCHING SKILL KEYWORD
    project_query = {
        "$or": [
            {"name": {"$regex": skill_name, "$options": "i"}},
            {"description": {"$regex": skill_name, "$options": "i"}}
        ]
    }
    matching_projects = await db.projects.find(project_query).to_list(20)
    
    for proj in matching_projects:
        proj_id = str(proj["_id"])
        print(f"🔍 [DEBUG] Checking matching project: {proj_id} ({proj.get('name')})")
        
        task_query = {
            "$and": [
                {"project_id": proj_id},
                {"_id": {"$nin": assigned_task_ids}},
                {"title": {"$nin": assigned_titles}}
            ]
        }
        
        candidate_tasks = await db.tasks.find(task_query).to_list(100)
        if candidate_tasks:
            import re
            def natural_sort_key(s):
                s = " ".join(s.split()).strip()
                return [int(text) if text.isdigit() else text.lower()
                        for text in re.split('([0-9]+)', s)]
            
            candidate_tasks.sort(key=lambda t: natural_sort_key(t.get("title", "")))
            task = candidate_tasks[0]
            print(f"✅ Found task in matching project {proj_id}: {task.get('title')}")
            return task

    # 3. FINAL FALLBACK: Broad search across ALL tasks
    task_query = {
        "$and": [
            {
                "$or": [
                    {"skillType": {"$regex": f"^{skill_name}$", "$options": "i"}},
                    {"category": {"$regex": f"^{skill_name}$", "$options": "i"}},
                    {"title": {"$regex": skill_name, "$options": "i"}}
                ]
            },
            {"_id": {"$nin": assigned_task_ids}},
            {"title": {"$nin": assigned_titles}}
        ]
    }
    
    print(f"🔍 [DEBUG] Falling back to broad task search for {skill_name}")
    candidate_tasks = await db.tasks.find(task_query).to_list(100)
    
    if candidate_tasks:
        import re
        def natural_sort_key(s):
            s = " ".join(s.split()).strip()
            return [int(text) if text.isdigit() else text.lower()
                    for text in re.split('([0-9]+)', s)]
        
        candidate_tasks.sort(key=lambda t: natural_sort_key(t.get("title", "")))
        task = candidate_tasks[0]
        print(f"✅ Found task (broad search): {task.get('title')}")
        return task
    
    print(f"⚠️ No unassigned tasks found for skill: {skill_name}")
    return None

async def assign_task_to_user(db, user_id: str, task_id: ObjectId):
    """
    Assign a task to a user's assignments collection.
    """
    print(f"🔗 Assigning task {task_id} to user {user_id}...")
    
    # Check if assignment document exists
    assignment = await db.assignments.find_one({"userId": user_id})
    
    task_entry = {
        "taskId": str(task_id),
        "assignedBy": "admin",  # Changed from "agent" to "admin" to match Pydantic model
        "sequenceId": 1,
        "taskStatus": "active", # Start as active as requested
        "expectedCompletionDate": (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"),
        "completionDate": None,
        "comments": [
            {
                "comment": "Assigned by Study Buddy", 
                "commentBy": "admin", 
                "createdAt": datetime.now()
            }
        ]
    }
    
    if not assignment:
        # Create new assignment doc
        print("📝 Creating new assignment document...")
        await db.assignments.insert_one({
            "userId": user_id,
            "tasks": [task_entry],
            "created_at": datetime.now(),
            "updated_at": datetime.now()
        })
    else:
        # Append to existing tasks
        print("📝 Updating existing assignment document...")
        await db.assignments.update_one(
            {"userId": user_id},
            {
                "$push": {"tasks": task_entry},
                "$set": {"updated_at": datetime.now()}
            }
        )
    
    print(f"✅ Task {task_id} assigned successfully.")
    return True

async def update_buddy_status(db, user_id: str, status: str, next_contact: datetime = None):
    """
    Update the buddy status and next contact date in the agents collection.
    """
    update_doc = {
        "buddy_status": status,
        "updated_at": datetime.now()
    }
    if next_contact:
        update_doc["next_buddy_contact_date"] = next_contact
        
    await db.agents.update_one(
        {"userId": user_id},
        {"$set": update_doc},
        upsert=True
    )
