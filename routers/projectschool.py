from fastapi import APIRouter, Request, Body, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
import base64
import httpx
import os
from utils.helpers import serialize, send_task_completion_email, send_assignment_email
from models import UserStats, DashboardStatsResponse, Assignment, Task

router = APIRouter()

@router.get("/debug/tasks")
async def debug_tasks(request: Request):
    db = request.app.state.db
    cursor = db.tasks.find().sort("updatedAt", -1).limit(10)
    tasks = []
    async for t in cursor:
        tasks.append({
            "id": str(t["_id"]),
            "title": t.get("title"),
            "isGlobal": t.get("isGlobal"),
            "createdBy": t.get("createdBy"),
            "isEnabled": t.get("isEnabled")
        })
    return tasks

import bcrypt

# --- Models ---

class LoginRequest(BaseModel):
    userName: str
    password: str

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
    isGlobal: bool = False
    createdBy: str = "admin"
    createdAt: datetime = Field(default_factory=datetime.now)

class BroadcastTaskRequest(BaseModel):
    taskId: str
    adminId: str
    adminName: Optional[str] = None
    adminEmail: Optional[str] = None
    userIds: List[str]

class SendJobsEmailRequest(BaseModel):
    collegeId: Optional[str] = None
    allColleges: bool = False
    excludeIITG: bool = False
    templateId: Optional[str] = None
    jobShortCodes: str  # CSV string

# --- Endpoints ---

@router.get("/colleges/get", status_code=200)
async def get_colleges(request: Request):
    """
    Fetch all colleges from the main database.
    """
    if not hasattr(request.app.state, 'main_db') or request.app.state.main_db is None:
        raise HTTPException(status_code=503, detail="Main Database not available")
    
    db = request.app.state.main_db
    cursor = db.colleges.find({}, {"name": 1, "collegeName": 1, "_id": 1})
    colleges = []
    async for doc in cursor:
        college = serialize(doc)
        if "collegeName" not in college and "name" in college:
            college["collegeName"] = college["name"]
        colleges.append(college)
    
    return colleges

@router.post("/reports-login", status_code=200)
async def reports_login(request: Request, login_data: LoginRequest = Body(...)):
    """
    Login for Reports Admin (uses Main DB Users)
    """
    raw_name = login_data.userName.strip()
    print(f"🔐 Login Attempt: {raw_name}")

    if not hasattr(request.app.state, 'main_db') or request.app.state.main_db is None:
        print("❌ Main DB not available")
        raise HTTPException(status_code=503, detail="Main Database not available")
        
    db = request.app.state.main_db
    
    import re
    regex_user = re.compile(f"^{re.escape(raw_name)}$", re.IGNORECASE)
    
    user = await db.users.find_one({
        "$or": [
            {"userName": {"$regex": regex_user}},
            {"email": {"$regex": regex_user}},
            {"fullName": {"$regex": regex_user}}
        ]
    })
    
    if not user:
        print(f"❌ User not found: {raw_name}")
        user = await db.users.find_one({
            "$or": [
                {"userName": {"$regex": re.compile(re.escape(raw_name), re.IGNORECASE)}},
                {"fullName": {"$regex": re.compile(re.escape(raw_name), re.IGNORECASE)}}
            ]
        })
        if not user:
             raise HTTPException(status_code=400, detail="User Not Found")
        else:
             print(f"💡 Found partial/alternate match: {user.get('userName')}")
        
    if not user.get("password"):
         print(f"❌ User has no password set: {user.get('userName')}")
         raise HTTPException(status_code=400, detail="Invalid credentials")

    try:
        password_bytes = login_data.password.encode('utf-8')
        hashed_bytes = user["password"].encode('utf-8')
        
        if bcrypt.checkpw(password_bytes, hashed_bytes):
            u_type = user.get("userType", "s")
            if u_type in ["a", "s"]:
                print(f"✅ Login Success: {user.get('userName')} (Type: {u_type})")
                return {
                    "token": "valid-token-placeholder", 
                    "_id": str(user["_id"]),
                    "fullName": user.get("fullName"),
                    "userType": u_type
                }
            else:
                print(f"❌ Unauthorized access (type {u_type}): {user.get('userName')}")
                raise HTTPException(status_code=403, detail="Unauthorized access")
        else:
             print(f"❌ Password mismatch for: {user.get('userName')}")
             raise HTTPException(status_code=400, detail="Invalid userName or password")
    except Exception as e:
        print(f"💥 Login Error: {e}")
        raise HTTPException(status_code=500, detail=f"Login failed: {str(e)}")

@router.get("/projects", status_code=200)
async def get_all_projects_list(request: Request, userId: Optional[str] = None):
    """
    Fetch all projects from Agriculture DB with privacy filtering
    """
    db = request.app.state.db
    
    ADMIN_ID = "6928870c5b168f52cf8bd77a"
    admin_creators = [None, "admin", ADMIN_ID]
    
    if userId:
        query = {
            "$or": [
                {"createdBy": {"$in": admin_creators}},
                {"createdBy": userId}
            ]
        }
    else:
        query = {"createdBy": {"$in": admin_creators}}
        
    print(f"🔍 Fetching project list for dashboard with query: {query}")
    cursor = db.projects.find(query, {"_id": 1, "name": 1, "description": 1, "projectType": 1, "status": 1})
    projects = []
    async for doc in cursor:
        projects.append(serialize(doc))
    print(f"✅ Returning {len(projects)} filtered projects")
    return projects

@router.get("/get-cohort-members", status_code=200)
async def get_cohort_members(request: Request):
    if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
        db = request.app.state.main_db
    else:
        db = request.app.state.db
        
    try:
        ps_user_ids = await db.projectschools.distinct("userId")
        print(f"📋 Found {len(ps_user_ids)} users in projectschools")
    except Exception as e:
        print(f"⚠️ Error fetching from projectschools: {e}")
        ps_user_ids = []

    query = {}
    if ps_user_ids:
        query = {"_id": {"$in": ps_user_ids}}
    else:
        print("⚠️ No projectschool members found, falling back to all users (LIMITED)")
        
    cursor = db.users.find(query, {"_id": 1, "fullName": 1, "name": 1, "userName": 1, "email": 1, "phone": 1, "subscriptionStatus": 1})
    members = []
    async for doc in cursor:
        member = serialize(doc)
        member["userId"] = member.get("id")
        member["fullName"] = member.get("fullName") or member.get("name") or member.get("userName") or "Unknown User"
        
        raw_status = member.get("subscriptionStatus")
        sub_status = str(raw_status if raw_status else "trial").lower()
        member["isPaid"] = sub_status == "paid"
        member["isTrial"] = sub_status == "trial"
        
        members.append(member)
    
    print(f"✅ Returning {len(members)} cohort members")
    return members

@router.post("/tasks", status_code=201)
async def create_project_task(request: Request, task: Task = Body(...)):
    """
    Create a new global task template (used for Project School broadcasting)
    """
    db = request.app.state.db
    task_dict = task.model_dump(exclude={"id"})
    
    if not task_dict.get("updatedAt"):
        task_dict["updatedAt"] = datetime.now()
    
    task_dict["isEnabled"] = True
    task_dict["isGlobal"] = task_dict.get("isGlobal", False)
    
    result = await db.tasks.insert_one(task_dict)
    created_task = await db.tasks.find_one({"_id": result.inserted_id})
    print(f"✅ Created broadcast task template: {task_dict.get('title')}")
    return serialize(created_task)

@router.post("/tasks/broadcast-task", status_code=200)
async def broadcast_task_to_users(request: Request, body: BroadcastTaskRequest = Body(...)):
    """
    Link a task ID to multiple users in one go (active status, selected users)
    """
    db = request.app.state.db
    task_id = body.taskId
    user_ids = body.userIds
    admin_id = body.adminId
    admin_name = body.adminName or "Admin"
    admin_email = body.adminEmail or ""

    print(f"📡 Broadcasting task {task_id} to {len(user_ids)} users from {admin_id}")

    if not admin_email or admin_name == "Admin":
        admin_doc = None
        if admin_id and ObjectId.is_valid(admin_id):
            if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
                admin_doc = await request.app.state.main_db.users.find_one({"_id": ObjectId(admin_id)})
            if not admin_doc:
                admin_doc = await db.users.find_one({"_id": ObjectId(admin_id)})
            
            if admin_doc:
                admin_email = admin_doc.get("email", admin_email)
                admin_name = admin_doc.get("fullName") or admin_doc.get("userName") or admin_name
                print(f"👤 Found admin info: {admin_name} ({admin_email})")

    task_doc = await db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task_doc:
        raise HTTPException(status_code=404, detail="Task template not found")
        
    await db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"isEnabled": True}}
    )
    
    assigned_count = 0
    for u_id in user_ids:
        existing = await db.assignments.find_one({
            "userId": u_id,
            "tasks.taskId": task_id
        })
        
        if not existing:
            new_task_link = {
                "taskId": task_id,
                "assignedBy": "admin",
                "assignerUserId": admin_id,
                "assignerName": admin_name,
                "assignerEmail": admin_email,
                "sequenceId": None,
                "taskStatus": "active",
                "comments": []
            }
            
            await db.assignments.update_one(
                {"userId": u_id},
                {"$push": {"tasks": new_task_link}},
                upsert=True
            )
            
            assignee_doc = None
            if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
                assignee_doc = await request.app.state.main_db.users.find_one({"_id": ObjectId(u_id)})
            if not assignee_doc:
                assignee_doc = await db.users.find_one({"_id": ObjectId(u_id)})
            
            if assignee_doc and assignee_doc.get("email"):
                project_name = "Personal"
                project_id = task_doc.get("project_id")
                if project_id and ObjectId.is_valid(project_id):
                    project_doc = await db.projects.find_one({"_id": ObjectId(project_id)})
                    if project_doc:
                        project_name = project_doc.get("name", "Personal")

                await send_assignment_email(
                    assignee_doc["email"],
                    assignee_doc.get("fullName") or assignee_doc.get("userName", "Student"),
                    admin_name,
                    task_doc.get("title") or task_doc.get("name", "a task"),
                    project_name=project_name,
                    day=task_doc.get("day"),
                    task_type=task_doc.get("taskType"),
                    task_description=task_doc.get("description") or task_doc.get("taskDescription")
                )

            assigned_count += 1
            
    print(f"✅ Completed broadcast: {assigned_count} new assignments created")
    return {"status": "success", "assignedCount": assigned_count}


# ─── NEW ENDPOINT: Assign task to ALL cohort members as PENDING ───────────────
@router.post("/tasks/assign-all-cohort", status_code=200)
async def assign_task_to_all_cohort(request: Request, body: Dict[str, Any] = Body(...)):
    """
    Assigns an existing task to ALL cohort members with taskStatus='pending' (NOT active).
    isEnabled is set to True on the task so admin can later mark individual users as active.
    Sends assignment email notifications to all cohort members.

    Called when admin creates a task without selecting any specific users.
    Admin must manually mark each user's task as active via the existing
    PUT /tasks/user-tasks/{user_id}/{task_id}/active endpoint.
    """
    db = request.app.state.db
    task_id = body.get("taskId")
    admin_id = body.get("adminId", "admin")

    if not task_id:
        raise HTTPException(status_code=400, detail="taskId is required")

    # 1. Validate task exists
    if not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=400, detail="Invalid taskId format")

    task_doc = await db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task_doc:
        raise HTTPException(status_code=404, detail="Task not found")

    # 2. Ensure task is enabled (but NOT active per user — that's the point)
    await db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"isEnabled": True}}
    )
    print(f"✅ Task {task_id} marked as isEnabled=True")

    # 3. Resolve admin info for email notifications
    admin_name = "Admin"
    admin_email = ""
    if admin_id and ObjectId.is_valid(admin_id):
        admin_doc = None
        if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
            admin_doc = await request.app.state.main_db.users.find_one({"_id": ObjectId(admin_id)})
        if not admin_doc:
            admin_doc = await db.users.find_one({"_id": ObjectId(admin_id)})
        if admin_doc:
            admin_name = admin_doc.get("fullName") or admin_doc.get("userName", "Admin")
            admin_email = admin_doc.get("email", "")
            print(f"👤 Admin resolved: {admin_name} ({admin_email})")

    # 4. Fetch all cohort members — reuses same logic as get-cohort-members endpoint
    user_db = request.app.state.main_db if (
        hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None
    ) else db

    try:
        ps_user_ids = await user_db.projectschools.distinct("userId")
    except Exception as e:
        print(f"⚠️ Error fetching projectschool user IDs: {e}")
        ps_user_ids = []

    if not ps_user_ids:
        raise HTTPException(status_code=404, detail="No cohort members found in projectschools collection")

    cursor = user_db.users.find(
        {"_id": {"$in": ps_user_ids}},
        {"_id": 1, "fullName": 1, "userName": 1, "email": 1}
    )
    cohort_members = [doc async for doc in cursor]
    print(f"📡 Assigning task {task_id} to {len(cohort_members)} cohort members as PENDING")

    # 5. Fetch project name once (reused for all email notifications)
    project_name = "Personal"
    project_id = task_doc.get("project_id")
    if project_id and ObjectId.is_valid(str(project_id)):
        project_doc = await db.projects.find_one({"_id": ObjectId(str(project_id))})
        if project_doc:
            project_name = project_doc.get("name", "Personal")

    # 6. Assign to each cohort member with taskStatus = "pending" (NOT "active")
    assigned_count = 0
    skipped_count = 0

    for member in cohort_members:
        u_id = str(member["_id"])

        # Deduplicate — skip if already assigned
        existing = await db.assignments.find_one({
            "userId": u_id,
            "tasks.taskId": task_id
        })
        if existing:
            skipped_count += 1
            continue

        new_task_link = {
            "taskId": task_id,
            "assignedBy": "admin",
            "assignerUserId": admin_id,
            "assignerName": admin_name,
            "assignerEmail": admin_email,
            "sequenceId": None,
            # ── PENDING: task is created but NOT active yet ──
            # Admin activates individually via PUT /tasks/user-tasks/{userId}/{taskId}/active
            "taskStatus": "pending",
            "comments": []
        }

        await db.assignments.update_one(
            {"userId": u_id},
            {"$push": {"tasks": new_task_link}},
            upsert=True
        )

        # Send email notification to each cohort member immediately
        member_email = member.get("email")
        if member_email:
            member_name = member.get("fullName") or member.get("userName", "Student")
            try:
                await send_assignment_email(
                    member_email,
                    member_name,
                    admin_name,
                    task_doc.get("title") or task_doc.get("name", "a task"),
                    project_name=project_name,
                    day=task_doc.get("day"),
                    task_type=task_doc.get("taskType"),
                    task_description=task_doc.get("description") or task_doc.get("taskDescription")
                )
            except Exception as email_err:
                print(f"⚠️ Failed to send email to {member_email}: {email_err}")

        assigned_count += 1

    print(f"✅ Assigned to {assigned_count} cohort members as pending (skipped {skipped_count} already assigned)")
    return {
        "status": "success",
        "assignedCount": assigned_count,
        "skippedCount": skipped_count,
        "totalCohort": len(cohort_members)
    }
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/feedback/fetch", status_code=200)
async def fetch_user_feedback(request: Request, body: Dict[str, Any] = Body(...)):
    """Fetch feedback for a specific user"""
    db = request.app.state.db
    user_id = body.get("userId")
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
    
    cursor = db.feedback.find({"userId": user_id}).sort("createdAt", -1)
    feedback_list = []
    async for doc in cursor:
        feedback_list.append(serialize(doc))
    return feedback_list

@router.post("/assignments/user/assignments", status_code=200)
async def fetch_user_assignments(request: Request, body: Dict[str, Any] = Body(...)):
    """Fetch assignments for a specific user (compatibility with old component)"""
    db = request.app.state.db
    user_id = body.get("userId")
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
    
    cursor = db.assignment_templates.find().sort("createdAt", -1)
    templates = [serialize(doc) async for doc in cursor]
    
    user_assignment_doc = await db.assignments.find_one({"userId": user_id})
    assigned_task_ids = {}
    if user_assignment_doc and user_assignment_doc.get("tasks"):
        for t in user_assignment_doc["tasks"]:
            assigned_task_ids[t["taskId"]] = t.get("taskStatus") == "completed"

    result = []
    for temp in templates:
        template_tasks = temp.get("tasks", [])
        formatted_tasks = []
        is_any_task_assigned = False
        
        for t in template_tasks:
            t_id = str(t.get("_id", ""))
            t_name = t.get("name")
            
            is_done = assigned_task_ids.get(t_id, False)
            if t_id in assigned_task_ids:
                is_any_task_assigned = True

            formatted_tasks.append({
                "taskId": t_id or (str(temp["id"]) + "_" + t_name), 
                "name": t_name,
                "description": t.get("description"),
                "isTaskDone": is_done
            })
        
        if is_any_task_assigned or temp.get("isGlobal"):
            result.append({
                "assignmentId": str(temp["id"]),
                "assignmentName": temp.get("name") or temp.get("assignmentName"),
                "assignmentDescription": temp.get("description") or temp.get("assignmentDescription"),
                "tasks": formatted_tasks,
                "createdAt": temp.get("createdAt")
            })
    return result

import logging
logger = logging.getLogger("project-school")

@router.post("/assignments/user/complete-task", status_code=200)
async def complete_user_task_proxy(request: Request, body: Dict[str, Any] = Body(...)):
    """Proxy to mark a task as complete and notify the assigner"""
    db = request.app.state.db
    user_id = body.get("userId")
    task_id = body.get("taskId")
    
    if not user_id or not task_id:
        raise HTTPException(status_code=400, detail="userId and taskId are required")
        
    assignment_doc = await db.assignments.find_one({"userId": user_id, "tasks.taskId": task_id})
    task_assignment = None
    if assignment_doc:
        for t in assignment_doc.get("tasks", []):
            if t.get("taskId") == task_id:
                task_assignment = t
                break

    await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {"$set": {
            "tasks.$.taskStatus": "completed",
            "tasks.$.completionDate": datetime.now().isoformat()
        }}
    )

    if task_assignment and task_assignment.get("assignerEmail"):
        assigner_email = task_assignment["assignerEmail"]
        assigner_name = task_assignment.get("assignerName", "Admin")
        
        task_doc = await db.tasks.find_one({"_id": ObjectId(task_id)}) if ObjectId.is_valid(task_id) else None
        task_title = task_doc.get("title") or task_doc.get("name", "a task") if task_doc else "a task"

        assignee_doc = None
        if ObjectId.is_valid(user_id):
            if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
                assignee_doc = await request.app.state.main_db.users.find_one({"_id": ObjectId(user_id)})
            if not assignee_doc:
                assignee_doc = await db.users.find_one({"_id": ObjectId(user_id)})
        assignee_name = (assignee_doc.get("fullName") or assignee_doc.get("userName", "Student")) if assignee_doc else "Student"

        await send_task_completion_email(assigner_email, assigner_name, assignee_name, task_title)

    return {"status": "success"}

@router.post("/tasks/link-user-task", status_code=200)
async def link_task_to_user_proxy(request: Request, body: Dict[str, Any] = Body(...)):
    db = request.app.state.db
    user_id = body.get("userId")
    task_id = body.get("taskId")
    assigned_by = body.get("assignedBy", "admin")
    assigner_user_id = body.get("assignerUserId", "")
    assigner_name = body.get("assignerName", "Admin")
    assigner_email = body.get("assignerEmail", "")

    assigner_doc = None
    if assigner_user_id and ObjectId.is_valid(assigner_user_id):
        if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
            assigner_doc = await request.app.state.main_db.users.find_one({"_id": ObjectId(assigner_user_id)})
            if assigner_doc: logger.info(f"👤 Found assigner in main_db: {assigner_doc.get('email')}")
        if not assigner_doc:
            assigner_doc = await db.users.find_one({"_id": ObjectId(assigner_user_id)})
            if assigner_doc: logger.info(f"👤 Found assigner in project_db: {assigner_doc.get('email')}")
        
        if assigner_doc:
            assigner_email = assigner_doc.get("email", "")
            assigner_name = assigner_doc.get("fullName") or assigner_doc.get("userName", assigner_name)
        else:
            logger.warning(f"⚠️ Assigner ID {assigner_user_id} not found in any database.")
    else:
        logger.warning(f"⚠️ No valid assignerUserId provided: '{assigner_user_id}'")

    if not user_id or not task_id:
        raise HTTPException(status_code=400, detail="userId and taskId are required")

    existing = await db.assignments.find_one({"userId": user_id, "tasks.taskId": task_id})

    if not existing:
        new_link = {
            "taskId": task_id,
            "assignedBy": assigned_by,
            "assignerUserId": assigner_user_id,
            "assignerName": assigner_name,
            "assignerEmail": assigner_email,
            "sequenceId": body.get("sequenceId"),
            "taskStatus": "active" if assigned_by == "admin" else "pending",
            "comments": []
        }
        await db.assignments.update_one(
            {"userId": user_id},
            {"$push": {"tasks": new_link}},
            upsert=True
        )

        task_doc = await db.tasks.find_one({"_id": ObjectId(task_id)}) if ObjectId.is_valid(task_id) else None
        task_title = task_doc.get("title", "a task") if task_doc else "a task"

        assignee_doc = None
        if ObjectId.is_valid(user_id):
            if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
                assignee_doc = await request.app.state.main_db.users.find_one({"_id": ObjectId(user_id)})
            if not assignee_doc:
                assignee_doc = await db.users.find_one({"_id": ObjectId(user_id)})

        if assignee_doc and assignee_doc.get("email"):
            project_name = "Personal"
            project_id = task_doc.get("project_id") if task_doc else None
            if project_id and ObjectId.is_valid(project_id):
                project_doc = await db.projects.find_one({"_id": ObjectId(project_id)})
                if project_doc:
                    project_name = project_doc.get("name", "Personal")

            await send_assignment_email(
                assignee_doc["email"],
                assignee_doc.get("fullName") or assignee_doc.get("userName", "Student"),
                assigner_name,
                task_title,
                project_name=project_name,
                day=task_doc.get("day") if task_doc else None,
                task_type=task_doc.get("taskType") if task_doc else None,
                task_description=(task_doc.get("description") or task_doc.get("taskDescription")) if task_doc else None
            )

    return {"status": "success"}

@router.put("/tasks/user-tasks/{user_id}/{task_id}/active", status_code=200)
async def mark_task_active_proxy(request: Request, user_id: str, task_id: str):
    """
    Proxy to make a task active.
    Used by admin to activate a pending task for a specific user.
    """
    db = request.app.state.db
    result = await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {"$set": {"tasks.$.taskStatus": "active"}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task assignment not found")
    return {"status": "success"}

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
    return {"success": True, "assignments": assignments}

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
    
    user_stats = await db.user_stats.find_one({"userId": userId})
    if not user_stats:
        new_stats = UserStats(userId=userId)
        await db.user_stats.insert_one(new_stats.model_dump(exclude={"id"}))
        user_stats = new_stats.model_dump()
    else:
        user_stats = serialize(user_stats)

    assignments_doc = await db.user_task_assignments.find_one({"userId": userId})
    
    user_tasks = []
    if assignments_doc:
        task_list = assignments_doc.get("tasks", [])
        task_ids = [ObjectId(t["taskId"]) for t in task_list if ObjectId.is_valid(t["taskId"])]
        
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

    total_active = sum(1 for t in user_tasks if t["status"] == "active")
    total_completed = sum(1 for t in user_tasks if t["status"] == "completed")
    
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
        new_stats = UserStats(userId=user_id, totalXP=xp_earned, currentStreak=1, lastActivityDate=today)
        await db.user_stats.insert_one(new_stats.model_dump(exclude={"id"}))
        return {"status": "success", "message": "Stats created"}

    await db.user_stats.update_one(
        {"userId": user_id},
        update_ops,
        upsert=True
    )
    
    return {"status": "success", "earned": xp_earned}

@router.post("/send-jobs-email", status_code=200)
async def send_jobs_email(request: Request, body: SendJobsEmailRequest = Body(...)):
    """
    Sends job digest email to users of specific college or all colleges.
    Fetches job details by shortcodes.
    """
    if not hasattr(request.app.state, 'main_db') or request.app.state.main_db is None:
        raise HTTPException(status_code=503, detail="Main Database not available")
    
    db = request.app.state.main_db
    zepto_token = os.getenv("ZEPTO_MAIL_TOKEN")
    
    if not zepto_token:
        raise HTTPException(status_code=500, detail="ZEPTO_MAIL_TOKEN not configured")

    short_codes = [sc.replace('"', '').replace("'", "").strip() for sc in body.jobShortCodes.split(",") if sc.strip()]
    if not short_codes:
        raise HTTPException(status_code=400, detail="No job shortcodes provided")

    cursor = db.jobposts.find({"shortCode": {"$in": short_codes}})
    all_jobs_list = []
    async for doc in cursor:
        all_jobs_list.append(doc)
    
    if not all_jobs_list:
        raise HTTPException(status_code=404, detail="No jobs found for the provided shortcodes")

    user_query = {"email": {"$exists": True, "$ne": ""}}
    
    if body.allColleges and body.excludeIITG:
        import re
        iitg_college = await db.colleges.find_one({"collegeName": {"$regex": re.compile("Indian Institute of Technology.*Guwahati|IIT.*Guwahati|IITG", re.IGNORECASE)}})
        if iitg_college:
            user_query["collegeId"] = {"$ne": iitg_college["_id"]}

    elif not body.allColleges and body.collegeId:
        if ObjectId.is_valid(body.collegeId):
            user_query["collegeId"] = ObjectId(body.collegeId)
        else:
            user_query["collegeId"] = body.collegeId

    unsubscribed_emails = await db.email_unsubscribes.distinct("email")
    if unsubscribed_emails:
        user_query["email"]["$nin"] = unsubscribed_emails

    user_cursor = db.users.find(user_query, {"email": 1, "fullName": 1, "userName": 1, "collegeId": 1})
    target_users = []
    async for u in user_cursor:
        target_users.append(u)

    if not target_users:
        return {"status": "success", "message": "No users found for the selected criteria", "sentCount": 0}

    colleges_cursor = db.colleges.find({}, {"collegeName": 1, "_id": 1})
    college_map = {}
    async for c in colleges_cursor:
        college_map[str(c["_id"])] = c.get("collegeName") or "your college"

    template_key = body.templateId or "2518b.6d1e43aa616e32a8.k1.f80371c0-025f-11f1-9250-ae9c7e0b6a9f.19c2c97aadc"
    current_date = datetime.now().strftime("%d %b %Y")
    
    success_count = 0
    failed_count = 0
    
    async with httpx.AsyncClient() as client:
        for user in target_users:
            user_email = user.get("email")
            user_name = user.get("fullName") or user.get("userName") or "Alumnus"
            user_college_id = str(user.get("collegeId")) if user.get("collegeId") else None
            user_college_name = college_map.get(user_college_id, "your college")

            unsubscribe_token = base64.b64encode(user_email.encode()).decode()
            unsubscribe_url = f"https://projectschool.alumnx.com/api/projectschool/unsubscribe?token={unsubscribe_token}"

            job_details_html = f"<p style='margin-bottom: 20px; font-size: 16px;'>As you are a registered user of Alumnx, we are sending you a curated list of jobs from your Alumni Updated and From Alumnx Jobs.</p>"

            job_details_html += """
            <div style="background-color: #25586b; color: #ffffff; padding: 12px 18px; border-radius: 8px; font-weight: bold; margin-bottom: 15px; font-size: 16px;">
                Your college alumni jobs
            </div>
            """

            alumni_jobs = [j for j in all_jobs_list if str(j.get("postedByCollegeId")) == user_college_id]
            if alumni_jobs:
                job_details_html += "<ul style='margin-bottom: 30px; padding-left: 20px; line-height: 1.6;'>"
                for job in alumni_jobs:
                    title = job.get("jobTitle") or job.get("title") or "Untitled Job"
                    short_code = job.get("shortCode")
                    job_link = f"https://alumnx.com/jobs?job={short_code}"
                    job_details_html += f"<li style='margin-bottom: 12px;'><strong style='color: #0f172a;'>{title}</strong>: <a href='{job_link}' style='color: #2563eb; text-decoration: none; font-weight: 600;'>Apply in Portal</a></li>"
                job_details_html += "</ul>"
            else:
                job_details_html += f"<p style='margin-bottom: 30px; color: #64748b; font-style: italic; padding: 0 10px;'>You don't have alumni jobs from {user_college_name} yet.</p>"

            job_details_html += """
            <div style="background-color: #25586b; color: #ffffff; padding: 12px 18px; border-radius: 8px; font-weight: bold; margin-bottom: 15px; font-size: 16px;">
                Alumnx Curated Jobs in AI/ML/DS
            </div>
            """

            job_details_html += "<ul style='margin-bottom: 35px; padding-left: 20px; line-height: 1.6;'>"
            for job in all_jobs_list:
                title = job.get("jobTitle") or job.get("title") or "Untitled Job"
                short_code = job.get("shortCode")
                job_link = f"https://alumnx.com/jobs?job={short_code}"
                job_details_html += f"<li style='margin-bottom: 12px;'><strong style='color: #0f172a;'>{title}</strong>: <a href='{job_link}' style='color: #2563eb; text-decoration: none; font-weight: 600;'>Apply in Portal</a></li>"
            job_details_html += "</ul>"

            job_details_html += f"""
            <div style="border-top: 1px solid #e2e8f0; padding-top: 25px; margin-top: 20px; font-size: 14px; color: #64748b;">
                <p>If you do not want to get this email every week, you can <a href='{unsubscribe_url}' style='color: #64748b; text-decoration: underline;'>click here to unsubscribe</a> Alumni Jobs.</p>
                <p style="margin-top: 20px; font-weight: bold; color: #0f172a;">Thank you,<br>Support@Alumnx.com</p>
            </div>
            """
            
            zepto_payload = {
                "from": {"address": "support@alumnx.com", "name": "Alumnx AI Labs"},
                "to": [{"email_address": {"address": user_email, "name": user_name}}],
                "template_key": template_key,
                "merge_info": {
                    "date": current_date,
                    "name": user_name,
                    "agent_message": job_details_html,
                    "unsubscribe_link": unsubscribe_url
                }
            }
            
            try:
                response = await client.post(
                    "https://api.zeptomail.in/v1.1/email/template",
                    json=zepto_payload,
                    headers={
                        "accept": "application/json",
                        "content-type": "application/json",
                        "authorization": zepto_token
                    },
                    timeout=10.0
                )
                if 200 <= response.status_code < 300:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as e:
                failed_count += 1

    return {
        "status": "success",
        "totalUsers": len(target_users),
        "successCount": success_count,
        "failedCount": failed_count,
        "jobsProcessed": len(all_jobs_list)
    }

@router.get("/unsubscribe")
async def unsubscribe(request: Request, token: str):
    """
    Unsubscribe a user from job emails using a base64 encoded email token.
    """
    if not hasattr(request.app.state, 'main_db') or request.app.state.main_db is None:
        raise HTTPException(status_code=503, detail="Main Database not available")
    
    db = request.app.state.main_db
    try:
        email = base64.b64decode(token).decode()
        await db.email_unsubscribes.update_one(
            {"email": email},
            {"$set": {"email": email, "unsubscribedAt": datetime.now()}},
            upsert=True
        )
        from fastapi.responses import HTMLResponse
        return HTMLResponse(content="""
            <html>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
                    <h2 style="color: #25586B;">Successfully Unsubscribed</h2>
                    <p>You will no longer receive job digest emails from Alumnx AI Labs.</p>
                </body>
            </html>
        """)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid unsubscribe token")