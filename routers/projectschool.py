from fastapi import APIRouter, Request, Body, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from bson import ObjectId
from utils.helpers import serialize
from models import UserStats, DashboardStatsResponse, Assignment, Task

router = APIRouter()

# --- Models ---

class ProjectSchoolSubscription(BaseModel):
    userId: str
    cohortId: str
    status: str = "active"
    type: str = "paid"
    startDate: datetime = Field(default_factory=datetime.now)

class PaymentRecord(BaseModel):
    userId: str
    amount: float
    status: str
    transactionId: str
    date: datetime = Field(default_factory=datetime.now)

class FeedbackItem(BaseModel):
    userId: str
    message: str
    adminId: str
    createdAt: datetime = Field(default_factory=datetime.now)

class AssignmentTemplateTask(BaseModel):
    name: str
    description: Optional[str] = None

class AssignmentTemplate(BaseModel):
    name: str
    description: Optional[str] = None
    tasks: List[AssignmentTemplateTask] = Field(default_factory=list)
    createdBy: str = "admin"
    createdAt: datetime = Field(default_factory=datetime.now)

# --- Endpoints ---

@router.get("/get-cohort-members", status_code=200)
async def get_cohort_members(request: Request):
    db = request.app.state.db
    # Fetch all users with relevant fields
    cursor = db.users.find({}, {"_id": 1, "name": 1, "email": 1, "phone": 1, "subscriptionStatus": 1})
    members = []
    async for doc in cursor:
        member = serialize(doc)
        # Map backend 'name' to frontend 'fullName' and 'id' to 'userId'
        member["userId"] = member.get("id")
        member["fullName"] = member.get("name", "Unknown User")
        
        # Determine subscription status flags
        sub_status = member.get("subscriptionStatus", "trial").lower()
        member["isPaid"] = sub_status == "paid"
        member["isTrial"] = sub_status == "trial"
        
        members.append(member)
    return members

@router.post("/add-assignment", status_code=201)
async def add_assignment(request: Request, assignment: AssignmentTemplate = Body(...)):
    db = request.app.state.db
    assignment_dict = assignment.model_dump()
    result = await db.assignment_templates.insert_one(assignment_dict)
    return {"status": "success", "id": str(result.inserted_id)}

@router.post("/feedback", status_code=201)
async def add_feedback(request: Request, feedback: FeedbackItem = Body(...)):
    db = request.app.state.db
    feedback_dict = feedback.model_dump()
    await db.feedback.insert_one(feedback_dict)
    return {"status": "success", "message": "Feedback recorded"}

@router.get("/get-assignments", status_code=200)
async def get_assignments(request: Request):
    db = request.app.state.db
    cursor = db.assignment_templates.find().sort("createdAt", -1)
    assignments = [serialize(doc) async for doc in cursor]
    return assignments

@router.post("/update-assignment", status_code=200)
async def update_assignment(request: Request, body: Dict[str, Any] = Body(...)):
    db = request.app.state.db
    assignment_id = body.get("id")
    if not assignment_id or not ObjectId.is_valid(assignment_id):
        raise HTTPException(status_code=400, detail="Invalid Assignment ID")
    
    update_data = body.get("update", {})
    await db.assignment_templates.update_one(
        {"_id": ObjectId(assignment_id)},
        {"$set": update_data}
    )
    return {"status": "success"}

@router.post("/assignments/delete", status_code=200)
async def delete_assignment(request: Request, body: Dict[str, Any] = Body(...)):
    db = request.app.state.db
    assignment_id = body.get("id")
    if not assignment_id or not ObjectId.is_valid(assignment_id):
        raise HTTPException(status_code=400, detail="Invalid Assignment ID")
    
    await db.assignment_templates.delete_one({"_id": ObjectId(assignment_id)})
    return {"status": "success"}

@router.post("/get-preferences", status_code=200)
async def get_preferences(request: Request, body: Dict[str, Any] = Body(...)):
    """Proxy to preferences router or direct DB call"""
    db = request.app.state.db
    user_id = body.get("userId")
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
    
    prefs_doc = await db.preferences.find_one({"userId": user_id})
    if not prefs_doc:
        return {"status": "success", "preferences": {"userId": user_id, "preferences": []}}
    
    return {"status": "success", "preferences": serialize(prefs_doc)}

@router.get("/dashboard-stats/{userId}", response_model=DashboardStatsResponse)
async def get_dashboard_stats(request: Request, userId: str):
    db = request.app.state.db
    
    # 1. Fetch User Stats (Lazy Init)
    user_stats = await db.user_stats.find_one({"userId": userId})
    if not user_stats:
        new_stats = UserStats(userId=userId)
        await db.user_stats.insert_one(new_stats.model_dump(exclude={"id"}))
        user_stats = new_stats.model_dump()
    else:
        user_stats = serialize(user_stats)

    # 2. Fetch User Tasks & Assignments
    # We need to join Assignments with Tasks to get skillType and status
    assignments_doc = await db.user_task_assignments.find_one({"userId": userId})
    
    user_tasks = []
    if assignments_doc:
        task_list = assignments_doc.get("tasks", [])
        task_ids = [ObjectId(t["taskId"]) for t in task_list if ObjectId.is_valid(t["taskId"])]
        
        # Fetch task details
        tasks_cursor = db.tasks.find({"_id": {"$in": task_ids}})
        all_tasks = {str(doc["_id"]): doc async for doc in tasks_cursor}
        
        for t in task_list:
            t_id = t["taskId"]
            if t_id in all_tasks:
                task_details = all_tasks[t_id]
                user_tasks.append({
                    "taskId": t_id,
                    "status": t.get("taskStatus", "pending"),
                    "skillType": task_details.get("skillType", "General"),
                    "title": task_details.get("title", ""),
                    "estimatedTime": task_details.get("estimatedTime", 0)
                })

    # 3. Calculate Stats
    total_active = sum(1 for t in user_tasks if t["status"] == "active")
    total_completed = sum(1 for t in user_tasks if t["status"] == "completed")
    
    # 4. Calculate Skills Progress
    skills_map = {}
    for t in user_tasks:
        skill = t["skillType"]
        if skill not in skills_map:
            skills_map[skill] = {"total": 0, "completed": 0}
        skills_map[skill]["total"] += 1
        if t["status"] == "completed":
            skills_map[skill]["completed"] += 1
            
    skills_list = []
    for skill, counts in skills_map.items():
        percentage = int((counts["completed"] / counts["total"]) * 100) if counts["total"] > 0 else 0
        skills_list.append({
            "name": skill,
            "percentage": percentage,
            "total": counts["total"],
            "completed": counts["completed"]
        })

    return {
        "stats": {
            "active": total_active,
            "completed": total_completed
        },
        "gamification": user_stats,
        "skills": skills_list
    }

@router.post("/log-activity", status_code=200)
async def log_activity(request: Request, body: Dict[str, Any] = Body(...)):
    """Update XP and Streak when a task is completed"""
    db = request.app.state.db
    user_id = body.get("userId")
    xp_earned = body.get("xp", 0)
    
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
        
    user_stats = await db.user_stats.find_one({"userId": user_id})
    today = datetime.now()
    
    update_ops = {
        "$inc": {"totalXP": xp_earned},
        "$set": {"lastActivityDate": today}
    }
    
    # Simple Streak Logic (Reset if last activity was before yesterday)
    # Real implementation would require precise date comparison
    if user_stats:
        last_date = user_stats.get("lastActivityDate")
        if last_date:
            delta = today - last_date
            if delta.days == 1:
                update_ops["$inc"]["currentStreak"] = 1
            elif delta.days > 1:
                update_ops["$set"]["currentStreak"] = 1
        else:
             update_ops["$set"]["currentStreak"] = 1
    else:
        # Create if not exists (handled by update with upsert=True mostly, but let's be safe)
        new_stats = UserStats(userId=user_id, totalXP=xp_earned, currentStreak=1, lastActivityDate=today)
        await db.user_stats.insert_one(new_stats.model_dump(exclude={"id"}))
        return {"status": "success", "message": "Stats created"}

    await db.user_stats.update_one(
        {"userId": user_id},
        update_ops,
        upsert=True
    )
    
    return {"status": "success", "earned": xp_earned}
