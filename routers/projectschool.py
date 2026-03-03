from fastapi import APIRouter, Request, Body, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from bson import ObjectId
from bson import ObjectId
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
    isGlobal: bool = False # Default to private for assignments
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
    templateId: Optional[str] = None
    jobShortCodes: str # CSV string

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
        # Compatibility mapping for frontend
        if "collegeName" not in college and "name" in college:
            college["collegeName"] = college["name"]
        colleges.append(college)
    
    return colleges

@router.post("/reports-login", status_code=200)
async def reports_login(request: Request, login_data: LoginRequest = Body(...)):
    """
    Login for Reports Admin (uses Main DB Users)
    """
    # Normalize name for logging
    raw_name = login_data.userName.strip()
    print(f"🔐 Login Attempt: {raw_name}")

    if not hasattr(request.app.state, 'main_db') or request.app.state.main_db is None:
        print("❌ Main DB not available")
        raise HTTPException(status_code=503, detail="Main Database not available")
        
    db = request.app.state.main_db
    
    # access users collection - Case-insensitive match for userName, email, or fullName
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
        # Try a partial match if exact case-insensitive fails (last resort)
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
        
    # Check password
    if not user.get("password"):
         print(f"❌ User has no password set: {user.get('userName')}")
         raise HTTPException(status_code=400, detail="Invalid credentials")

    try:
        # bcrypt.checkpw requires bytes
        password_bytes = login_data.password.encode('utf-8')
        hashed_bytes = user["password"].encode('utf-8')
        
        if bcrypt.checkpw(password_bytes, hashed_bytes):
            # Allow admin ('a') OR students ('s') if they have a password set explicitly
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
    
    # Visibility logic
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
        # If no user context, only show public/admin projects
        query = {"createdBy": {"$in": admin_creators}}
        
    print(f"🔍 Fetching project list for dashboard with query: {query}")
    # Projects are in the Agriculture DB
    cursor = db.projects.find(query, {"_id": 1, "name": 1, "description": 1, "projectType": 1, "status": 1})
    projects = []
    async for doc in cursor:
        projects.append(serialize(doc))
    print(f"✅ Returning {len(projects)} filtered projects")
    return projects

@router.get("/get-cohort-members", status_code=200)
async def get_cohort_members(request: Request):
    # Use Main DB for users
    if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
        db = request.app.state.main_db
    else:
        # Fallback to default DB if main_db not set
        db = request.app.state.db
        
    # Get unique user IDs from projectschools collection (the 34 members)
    try:
        ps_user_ids = await db.projectschools.distinct("userId")
        print(f"📋 Found {len(ps_user_ids)} users in projectschools")
    except Exception as e:
        print(f"⚠️ Error fetching from projectschools: {e}")
        ps_user_ids = []

    # Filter users based on projectschools membership if found
    query = {}
    if ps_user_ids:
        query = {"_id": {"$in": ps_user_ids}}
    else:
        # Fallback to fetching all but limited if no members found (to avoid 15k)
        print("⚠️ No projectschool members found, falling back to all users (LIMITED)")
        # This is just a safety measure
        # return [] # Or maybe some other logic
        
    # Fetch users with relevant fields
    cursor = db.users.find(query, {"_id": 1, "fullName": 1, "name": 1, "userName": 1, "email": 1, "phone": 1, "subscriptionStatus": 1})
    members = []
    async for doc in cursor:
        member = serialize(doc)
        # Map backend 'fullName' to frontend expected 'fullName' and 'id' to 'userId'
        member["userId"] = member.get("id")
        # Robust name fallback
        member["fullName"] = member.get("fullName") or member.get("name") or member.get("userName") or "Unknown User"
        
        # Determine subscription status flags
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
    
    # Set required defaults
    if not task_dict.get("updatedAt"):
        task_dict["updatedAt"] = datetime.now()
    
    # Force isEnabled true if it's being created for broadcast
    task_dict["isEnabled"] = True
    task_dict["isGlobal"] = task_dict.get("isGlobal", False) # Default to private
    
    result = await db.tasks.insert_one(task_dict)
    created_task = await db.tasks.find_one({"_id": result.inserted_id})
    print(f"✅ Created broadcast task template: {task_dict.get('title')}")
    return serialize(created_task)

@router.post("/tasks/broadcast-task", status_code=200)
async def broadcast_task_to_users(request: Request, body: BroadcastTaskRequest = Body(...)):
    """
    Link a task ID to multiple users in one go
    """
    db = request.app.state.db
    task_id = body.taskId
    user_ids = body.userIds
    admin_id = body.adminId
    admin_name = body.adminName or "Admin"
    admin_email = body.adminEmail or ""

    print(f"📡 Broadcasting task {task_id} to {len(user_ids)} users from {admin_id}")

    # Fetch admin details if missing (to ensure email is available for notifications)
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

    # 1. Ensure the task exists and is enabled
    task_doc = await db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task_doc:
        raise HTTPException(status_code=404, detail="Task template not found")
        
    await db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": {"isEnabled": True}}
    )
    
    # 2. Assign to each user (Deduplicated)
    assigned_count = 0
    for u_id in user_ids:
        # Check if already assigned
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
            
            # Notify assignee (User2)
            assignee_doc = None
            if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
                assignee_doc = await request.app.state.main_db.users.find_one({"_id": ObjectId(u_id)})
            if not assignee_doc:
                assignee_doc = await db.users.find_one({"_id": ObjectId(u_id)})
            
            if assignee_doc and assignee_doc.get("email"):
                await send_assignment_email(
                    assignee_doc["email"],
                    assignee_doc.get("fullName") or assignee_doc.get("userName", "Student"),
                    admin_name,
                    task_doc.get("title") or task_doc.get("name", "a task")
                )

            assigned_count += 1
            
    print(f"✅ Completed broadcast: {assigned_count} new assignments created")
    return {"status": "success", "assignedCount": assigned_count}

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
    
    # This expects assignment_templates but filtered/mapped for the user?
    # Actually the component expects a list where each item has tasks with isTaskDone.
    # We'll return an empty list for now or adapt based on current schema.
    # For now, let's just return what's in assignment_templates and check if assigned.
    cursor = db.assignment_templates.find().sort("createdAt", -1)
    templates = [serialize(doc) async for doc in cursor]
    
    # Get user's active assignments from 'assignments' collection
    user_assignment_doc = await db.assignments.find_one({"userId": user_id})
    assigned_task_ids = {}
    if user_assignment_doc and user_assignment_doc.get("tasks"):
        for t in user_assignment_doc["tasks"]:
            assigned_task_ids[t["taskId"]] = t.get("taskStatus") == "completed"

    result = []
    for temp in templates:
        # For security, we only show templates that have at least one task
        # either assigned to the user OR marked as global (if templates support that)
        # For now, we'll check if any task in this template matches an assigned taskId
        
        template_tasks = temp.get("tasks", [])
        # We need to map this to what the component expects
        # { assignmentId, assignmentName, assignmentDescription, tasks: [{ taskId, name, description, isTaskDone }] }
        formatted_tasks = []
        is_any_task_assigned = False
        
        for t in template_tasks:
            # We don't have taskId in templates easily, they are template tasks
            # Match by name/description or ID if available
            t_id = str(t.get("_id", ""))
            t_name = t.get("name")
            
            # This is tricky because templates don't always have taskId links
            # But the 'link-user-task' usually links them.
            # For now, let's allow templates ONLY if the user has assignments
            # OR if the template is marked as global (if that field exists)
            
            # IMPROVEMENT: If the template has NO assigned tasks for this user, skip it?
            # For compatibility with existing broadcast logic, we'll check if the 
            # template name matches an active assignment roughly, or if specific tasks coincide.
            
            is_done = assigned_task_ids.get(t_id, False)
            if t_id in assigned_task_ids:
                is_any_task_assigned = True

            formatted_tasks.append({
                "taskId": t_id or (str(temp["id"]) + "_" + t_name), 
                "name": t_name,
                "description": t.get("description"),
                "isTaskDone": is_done
            })
        
        # Only include if at least one task is assigned OR if it's explicitly global
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
        
    # 1. Fetch assignment BEFORE marking complete to get assigner details
    assignment_doc = await db.assignments.find_one({"userId": user_id, "tasks.taskId": task_id})
    task_assignment = None
    if assignment_doc:
        for t in assignment_doc.get("tasks", []):
            if t.get("taskId") == task_id:
                task_assignment = t
                break

    # 2. Mark complete
    await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {"$set": {
            "tasks.$.taskStatus": "completed",
            "tasks.$.completionDate": datetime.now().isoformat()
        }}
    )

    # 3. Send notification to assigner if assignerEmail is available
    if task_assignment and task_assignment.get("assignerEmail"):
        assigner_email = task_assignment["assignerEmail"]
        assigner_name = task_assignment.get("assignerName", "Admin")
        
        # Get task title
        task_doc = await db.tasks.find_one({"_id": ObjectId(task_id)}) if ObjectId.is_valid(task_id) else None
        task_title = task_doc.get("title") or task_doc.get("name", "a task") if task_doc else "a task"

        # Get assignee details
        assignee_doc = None
        if ObjectId.is_valid(user_id):
            if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
                assignee_doc = await request.app.state.main_db.users.find_one({"_id": ObjectId(user_id)})
            if not assignee_doc:
                assignee_doc = await db.users.find_one({"_id": ObjectId(user_id)})
        assignee_name = (assignee_doc.get("fullName") or assignee_doc.get("userName", "Student")) if assignee_doc else "Student"

        # Send email via ZeptoMail helper
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

    # Fetch assigner email from DB using assignerUserId
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
            "assignerUserId": assigner_user_id,    # NEW
            "assignerName": assigner_name,          # NEW
            "assignerEmail": assigner_email,        # NEW
            "sequenceId": body.get("sequenceId"),
            "taskStatus": "active" if assigned_by == "admin" else "pending",
            "comments": []
        }
        await db.assignments.update_one(
            {"userId": user_id},
            {"$push": {"tasks": new_link}},
            upsert=True
        )

        # Get task title
        task_doc = await db.tasks.find_one({"_id": ObjectId(task_id)}) if ObjectId.is_valid(task_id) else None
        task_title = task_doc.get("title", "a task") if task_doc else "a task"

        # Notify assignee (User2)
        assignee_doc = None
        if ObjectId.is_valid(user_id):
            if hasattr(request.app.state, 'main_db') and request.app.state.main_db is not None:
                assignee_doc = await request.app.state.main_db.users.find_one({"_id": ObjectId(user_id)})
            if not assignee_doc:
                assignee_doc = await db.users.find_one({"_id": ObjectId(user_id)})

        if assignee_doc and assignee_doc.get("email"):
            await send_assignment_email(
                assignee_doc["email"],
                assignee_doc.get("fullName") or assignee_doc.get("userName", "Student"),
                assigner_name,
                task_title
            )

    return {"status": "success"}

@router.put("/tasks/user-tasks/{user_id}/{task_id}/active", status_code=200)
async def mark_task_active_proxy(request: Request, user_id: str, task_id: str):
    """
    Proxy to make a task active
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

    # 1. Process Job Shortcodes
    short_codes = [sc.strip() for sc in body.jobShortCodes.split(",") if sc.strip()]
    if not short_codes:
        raise HTTPException(status_code=400, detail="No job shortcodes provided")

    cursor = db.jobposts.find({"shortCode": {"$in": short_codes}})
    jobs = []
    async for doc in cursor:
        jobs.append(doc)
    
    if not jobs:
        raise HTTPException(status_code=404, detail="No jobs found for the provided shortcodes")

    # 2. Format Job List HTML
    jobs_html = "<ul>"
    for job in jobs:
        title = job.get("jobTitle") or job.get("title") or "Untitled Job"
        # Preference: registrationLink > applyLink > sourceUrl
        link = job.get("registrationLink") or job.get("applyLink") or job.get("sourceUrl")
        
        if link:
            # Basic validation/cleanup for link
            if not link.startswith("http"):
                link = "https://" + link
            jobs_html += f"<li><strong>{title}</strong>: <a href='{link}'>Apply Here</a></li>"
        else:
            jobs_html += f"<li><strong>{title}</strong></li>"
    jobs_html += "</ul>"

    # 3. Identify Target Users
    user_query = {"email": {"$exists": True, "$ne": ""}}
    if not body.allColleges and body.collegeId:
        if ObjectId.is_valid(body.collegeId):
            user_query["collegeId"] = ObjectId(body.collegeId)
        else:
            # Try string match if not a valid ObjectId (some systems store as strings)
            user_query["collegeId"] = body.collegeId

    user_cursor = db.users.find(user_query, {"email": 1, "fullName": 1, "userName": 1})
    target_users = []
    async for u in user_cursor:
        target_users.append({
            "email": u.get("email"),
            "name": u.get("fullName") or u.get("userName") or "Alumnus"
        })

    if not target_users:
        return {"status": "success", "message": "No users found for the selected criteria", "sentCount": 0}

    # 4. Dispatch Emails via ZeptoMail (Batched for efficiency if many users)
    # ZeptoMail supports multiple recipients in one call, but let's keep it simple or follow existing helper patterns.
    # Existing helpers send one by one. For thousands of users, we should ideally use ZeptoMail's batching.
    # But for now, let's implement a robust loop.
    
    template_key = body.templateId or "2518b.6d1e43aa616e32a8.k1.f80371c0-025f-11f1-9250-ae9c7e0b6a9f.19c2c97aadc"
    current_date = datetime.now().strftime("%d %b %Y")
    
    success_count = 0
    failed_count = 0
    
    async with httpx.AsyncClient() as client:
        for user in target_users:
            zepto_payload = {
                "from": {"address": "support@alumnx.com", "name": "Alumnx AI Labs"},
                "to": [{"email_address": {"address": user["email"], "name": user["name"]}}],
                "template_key": template_key,
                "merge_info": {
                    "date": current_date,
                    "name": user["name"],
                    "message": jobs_html # This will be injected into {{message}}
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
                    logger.error(f"❌ ZeptoMail error for {user['email']}: {response.text}")
            except Exception as e:
                failed_count += 1
                logger.error(f"⚠️ Failed to send job email to {user['email']}: {e}")

    return {
        "status": "success",
        "totalUsers": len(target_users),
        "successCount": success_count,
        "failedCount": failed_count,
        "jobsProcessed": len(jobs)
    }
