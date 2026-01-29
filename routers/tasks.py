from fastapi import APIRouter, Request, Body, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime
from bson import ObjectId
import httpx
import json
import re
from models import (
    Task, 
    Assignment, 
    TaskAssignment, 
    TaskResponse, 
    TaskUpdate, 
    UserTaskLink,
    Comment,
    BulkLoadTasksRequest
)

class BulkTaskAssignment(BaseModel):
    taskId: str
    sequenceId: int


class BulkAssignTasksRequest(BaseModel):
    userId: str
    tasks: List[BulkTaskAssignment]

router = APIRouter()


def serialize(doc):
    """Helper to convert MongoDB _id to string id"""
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc

@router.get("/")
async def get_all_tasks(request: Request, project_id: str = None, userId: str = None):
    """Get all tasks, optionally filtered by project_id and userId (shows admin + user's own tasks)"""
    db = request.app.state.db
    query = {}
    
    if project_id:
        query["project_id"] = project_id
    
    # Filter tasks by createdBy if userId is provided
    if userId:
        query["$or"] = [
            {"createdBy": None},
            {"createdBy": "admin"},
            {"createdBy": userId}
        ]
    
    cursor = db.tasks.find(query)
    tasks = []
    async for doc in cursor:
        task = serialize(doc)
        # Ensure isEnabled is present with default value
        if "isEnabled" not in task:
            task["isEnabled"] = False
        tasks.append(task)
    return tasks


@router.post("/", status_code=201)
async def create_task(request: Request, task: Task = Body(...)):
    """Create a new task"""
    db = request.app.state.db
    task_dict = task.model_dump(exclude={"id"})
    
    # Ensure updatedAt is set to current time
    task_dict["updatedAt"] = datetime.now()
    
    # Ensure isEnabled has a default value if not provided
    if "isEnabled" not in task_dict or task_dict["isEnabled"] is None:
        task_dict["isEnabled"] = False
    
    result = await db.tasks.insert_one(task_dict)
    created_task = await db.tasks.find_one({"_id": result.inserted_id})
    return serialize(created_task)


@router.get("/{task_id}")
async def get_task(request: Request, task_id: str):
    """Get a specific task by ID"""
    db = request.app.state.db
    task = await db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task = serialize(task)
    # Ensure isEnabled is present
    if "isEnabled" not in task:
        task["isEnabled"] = False
    return task


@router.put("/{task_id}")
async def update_task(request: Request, task_id: str, task_update: TaskUpdate = Body(...)):
    """Update a task"""
    db = request.app.state.db
    update_data = {k: v for k, v in task_update.model_dump().items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    result = await db.tasks.update_one(
        {"_id": ObjectId(task_id)},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    
    updated_task = await db.tasks.find_one({"_id": ObjectId(task_id)})
    task = serialize(updated_task)
    # Ensure isEnabled is present
    if "isEnabled" not in task:
        task["isEnabled"] = False
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(request: Request, task_id: str):
    """Delete a task"""
    db = request.app.state.db
    result = await db.tasks.delete_one({"_id": ObjectId(task_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return None


@router.put("/{task_id}/user/{user_id}")
async def update_user_created_task(request: Request, task_id: str, user_id: str, task_update: TaskUpdate = Body(...)):
    """Update a task only if created by the specified user"""
    db = request.app.state.db
    update_data = {k: v for k, v in task_update.model_dump().items() if v is not None}
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    # Check ownership and update
    result = await db.tasks.update_one(
        {"_id": ObjectId(task_id), "createdBy": user_id},
        {"$set": update_data}
    )
    
    if result.matched_count == 0:
        # Check if task exists to return appropriate error
        task = await db.tasks.find_one({"_id": ObjectId(task_id)})
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        if task.get("createdBy") != user_id:
             raise HTTPException(status_code=403, detail="User not authorized to update this task")
    
    updated_task = await db.tasks.find_one({"_id": ObjectId(task_id)})
    task = serialize(updated_task)
    # Ensure isEnabled is present
    if "isEnabled" not in task:
        task["isEnabled"] = False
    return task


@router.delete("/{task_id}/user/{user_id}", status_code=204)
async def delete_user_created_task(request: Request, task_id: str, user_id: str):
    """Delete a task only if created by the specified user"""
    db = request.app.state.db
    
    result = await db.tasks.delete_one({
        "_id": ObjectId(task_id),
        "createdBy": user_id
    })
    
    if result.deleted_count == 0:
        # Check if task exists to return appropriate error
        task = await db.tasks.find_one({"_id": ObjectId(task_id)})
        if not task:
             raise HTTPException(status_code=404, detail="Task not found")
        if task.get("createdBy") != user_id:
             raise HTTPException(status_code=403, detail="User not authorized to delete this task")
             
    return None


@router.post("/link-user-task", status_code=200)
async def link_task_to_user(request: Request, link: UserTaskLink = Body(...)):
    """
    Link a task to a user by adding it to their assignments.
    Creates assignment document if it doesn't exist.
    """
    db = request.app.state.db
    
    # Verify task exists
    task = await db.tasks.find_one({"_id": ObjectId(link.taskId)})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check if user already has this task assigned
    assignment = await db.assignments.find_one({"userId": link.userId})
    
    if assignment:
        # Check for duplicate
        task_ids = [str(t.get("taskId")) for t in assignment.get("tasks", [])]
        if link.taskId in task_ids:
            raise HTTPException(status_code=400, detail="Task already assigned to user")
        
        # Add task to existing assignment
        new_task = TaskAssignment(
            taskId=link.taskId,
            assignedBy=link.assignedBy,
            sequenceId=link.sequenceId,
            expectedCompletionDate=link.expectedCompletionDate
        )
        
        await db.assignments.update_one(
            {"userId": link.userId},
            {"$push": {"tasks": new_task.model_dump()}}
        )
    else:
        # Create new assignment with this task
        new_assignment = Assignment(
            userId=link.userId,
            tasks=[
                TaskAssignment(
                    taskId=link.taskId,
                    assignedBy=link.assignedBy,
                    sequenceId=link.sequenceId,
                    expectedCompletionDate=link.expectedCompletionDate
                )
            ]
        )
        await db.assignments.insert_one(new_assignment.model_dump(exclude={"id"}))
    
    return {"status": "success", "message": "Task assigned to user"}


@router.get("/user-tasks/{user_id}", response_model=List[TaskResponse])
async def get_user_tasks(request: Request, user_id: str):
    """
    Get all tasks assigned to a user with full task and project details.
    """
    db = request.app.state.db
    
    try:
        # Get user's assignment document
        assignment = await db.assignments.find_one({"userId": user_id})
        if not assignment or not assignment.get("tasks"):
            return []
        
        task_responses = []
        
        for task_assignment in assignment.get("tasks", []):
            task_id = task_assignment.get("taskId")
            if not task_id:
                continue
                
            # Get task details
            try:
                task = await db.tasks.find_one({"_id": ObjectId(task_id)})
            except Exception:
                continue
                
            if not task:
                continue
            
            # Get project details
            project_id = task.get("project_id")
            project = None
            if project_id:
                try:
                    project = await db.projects.find_one({"_id": ObjectId(project_id)})
                except Exception:
                    pass
            
            # Build response
            task_response = TaskResponse(
                taskId=str(task["_id"]),
                name=task.get("title", task.get("name", "Unnamed Task")),
                description=task.get("description"),
                estimatedTime=task.get("estimatedTime", 0),
                skillType=task.get("skillType", "General"),
                projectId=project_id if project_id else "",
                projectName=project.get("name") if project else "Unknown Project",
                assignedBy=task_assignment.get("assignedBy", "admin"),
                sequenceId=task_assignment.get("sequenceId"),
                taskStatus=task_assignment.get("taskStatus", "pending"),
                expectedCompletionDate=task_assignment.get("expectedCompletionDate"),
                completionDate=task_assignment.get("completionDate"),
                comments=task_assignment.get("comments", []),
                createdBy=task.get("createdBy"),
                isEnabled=task.get("isEnabled", False)
            )
            
            task_responses.append(task_response)
        
        return task_responses
        
    except Exception as e:
        print(f"Error fetching user tasks: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching user tasks: {str(e)}")


@router.post("/update-task-status", status_code=200)
async def update_task_status(request: Request, update_data: Dict[str, Any] = Body(...)):
    """
    Update the status of a task in user's assignment.
    Expected payload: {"userId": "...", "taskId": "...", "taskStatus": "active|completed|pending"}
    """
    db = request.app.state.db
    
    user_id = update_data.get("userId")
    task_id = update_data.get("taskId")
    new_status = update_data.get("taskStatus")
    
    if not all([user_id, task_id, new_status]):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    if new_status not in ["pending", "active", "completed"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    # Find user's assignment
    assignment = await db.assignments.find_one({"userId": user_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="User assignment not found")
    
    # Update the specific task's status
    result = await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {"$set": {"tasks.$.taskStatus": new_status}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task not found in user's assignments")
    
    return {"status": "success", "message": "Task status updated"}


@router.post("/update-task-completion-date", status_code=200)
async def update_task_completion_date(request: Request, update_data: Dict[str, Any] = Body(...)):
    """
    Update the completion date of a task in user's assignment.
    Expected payload: {"userId": "...", "taskId": "...", "completionDate": "YYYY-MM-DD"}
    """
    db = request.app.state.db
    
    user_id = update_data.get("userId")
    task_id = update_data.get("taskId")
    completion_date = update_data.get("completionDate")
    
    if not all([user_id, task_id, completion_date]):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    # Find user's assignment
    assignment = await db.assignments.find_one({"userId": user_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="User assignment not found")
    
    # Update the specific task's completion date
    result = await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {"$set": {"tasks.$.completionDate": completion_date}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task not found in user's assignments")
    
    return {"status": "success", "message": "Task completion date updated"}


@router.post("/add-task-comment", status_code=200)
async def add_task_comment(request: Request, comment_data: Dict[str, Any] = Body(...)):
    """
    Add a comment to a task in user's assignment.
    Expected payload: {"userId": "...", "taskId": "...", "comment": "...", "commentBy": "user|admin"}
    """
    db = request.app.state.db
    
    user_id = comment_data.get("userId")
    task_id = comment_data.get("taskId")
    comment_text = comment_data.get("comment")
    comment_by = comment_data.get("commentBy", "user")
    
    if not all([user_id, task_id, comment_text]):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    if comment_by not in ["user", "admin"]:
        raise HTTPException(status_code=400, detail="Invalid commentBy value")
    
    # Create comment object
    new_comment = Comment(
        comment=comment_text,
        commentBy=comment_by,
        createdAt=datetime.now()
    )
    
    # Find user's assignment
    assignment = await db.assignments.find_one({"userId": user_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="User assignment not found")
    
    # Add comment to the specific task
    result = await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {"$push": {"tasks.$.comments": new_comment.model_dump()}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task not found in user's assignments")
    
    return {"status": "success", "message": "Comment added successfully"}


@router.post("/unlink-user-task", status_code=200)
async def unlink_task_from_user(request: Request, unlink_data: Dict[str, str] = Body(...)):
    """
    Remove a task from user's assignments.
    Expected payload: {"userId": "...", "taskId": "..."}
    """
    db = request.app.state.db
    
    user_id = unlink_data.get("userId")
    task_id = unlink_data.get("taskId")
    
    if not all([user_id, task_id]):
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    # Remove task from user's assignment
    result = await db.assignments.update_one(
        {"userId": user_id},
        {"$pull": {"tasks": {"taskId": task_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task not found in user's assignments")
    
    return {"status": "success", "message": "Task unlinked from user"}


@router.post("/bulk-assign-tasks", status_code=200)
async def bulk_assign_tasks(request: Request, payload: BulkAssignTasksRequest = Body(...)):
    """
    Assign multiple tasks to a user. Replaces all existing task assignments for the user.
    
    Request body:
    {
        "userId": "user123",
        "tasks": [
            {"taskId": "task1", "sequenceId": 1},
            {"taskId": "task2", "sequenceId": 2}
        ]
    }
    """
    db = request.app.state.db
    user_id = payload.userId
    tasks = payload.tasks

    print(f"📦 Assigning {len(tasks)} tasks to user: {user_id}")

    # Verify all tasks exist
    task_ids = [t.taskId for t in tasks]
    existing_tasks = await db.tasks.find(
        {"_id": {"$in": [ObjectId(tid) for tid in task_ids if ObjectId.is_valid(tid)]}}
    ).to_list(length=None)
    
    if len(existing_tasks) != len(task_ids):
        raise HTTPException(status_code=404, detail="One or more tasks not found")

    # Delete all existing assignments for this user
    delete_result = await db.assignments.delete_many({"userId": user_id})
    print(f"🗑️ Deleted existing assignment document")

    # Create new assignments
    if tasks:
        task_assignments = [
            TaskAssignment(
                taskId=task.taskId,
                sequenceId=task.sequenceId,
                assignedBy="admin",
                taskStatus="pending"
            )
            for task in tasks
        ]
        
        new_assignment = Assignment(
            userId=user_id,
            tasks=task_assignments
        )
        
        await db.assignments.insert_one(new_assignment.model_dump(exclude={"id"}))
        print(f"✅ Created new assignment with {len(tasks)} tasks")
    
    return {
        "status": "success",
        "message": f"Successfully assigned {len(tasks)} tasks to user {user_id}",
        "taskCount": len(tasks)
    }

@router.post("/bulk-add-tasks-to-project", status_code=201)
async def bulk_add_tasks_to_project(request: Request, bulk_req: BulkLoadTasksRequest = Body(...)):
    """
    Bulk add multiple tasks to a specific project.
    """
    db = request.app.state.db
    project_id = bulk_req.projectId
    tasks = bulk_req.tasks
    
    print(f"📦 Bulk adding {len(tasks)} tasks to project: {project_id}")
    
    # Verify project exists
    try:
        project = await db.projects.find_one({"_id": ObjectId(project_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project ID format")
        
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Prepare tasks for insertion
    new_tasks = []
    for task in tasks:
        task_data = task.model_dump()
        task_data["project_id"] = project_id
        task_data["updatedAt"] = datetime.now()
        # Ensure isEnabled has default value
        if "isEnabled" not in task_data or task_data["isEnabled"] is None:
            task_data["isEnabled"] = False
        new_tasks.append(task_data)
        
    if not new_tasks:
         return {"status": "success", "message": "No tasks provided", "count": 0}

    # Insert tasks
    result = await db.tasks.insert_many(new_tasks)
    
    print(f"✅ Bulk added {len(result.inserted_ids)} tasks to project {project_id}")
    
    return {
        "status": "success", 
        "message": f"Successfully created {len(result.inserted_ids)} tasks",
        "projectId": project_id,
        "taskIds": [str(id) for id in result.inserted_ids]
    }

@router.delete("/project/{project_id}/category/{skill_type}", status_code=200)
async def flush_tasks_by_category(request: Request, project_id: str, skill_type: str):
    """
    Flush (delete) all tasks in a project for a specific category (skillType).
    """
    db = request.app.state.db
    
    print(f"🧹 Flushing tasks for project {project_id} with category {skill_type}")
    
    # Delete tasks matching project_id and skillType
    result = await db.tasks.delete_many({
        "project_id": project_id,
        "skillType": skill_type
    })
    
    if result.deleted_count == 0:
        return {
             "status": "success",
             "message": "No tasks found to delete",
             "deletedCount": 0
        }

    print(f"✅ Flushed {result.deleted_count} tasks")
    
    return {
        "status": "success", 
        "message": f"Successfully deleted {result.deleted_count} tasks",
        "projectId": project_id,
        "category": skill_type,
        "deletedCount": result.deleted_count
    }

class UpdateTaskUpdatedDateRequest(BaseModel):
    projectId: str

@router.post("/update-task-updated-date", status_code=200)
async def update_task_updated_date(request: Request, req: UpdateTaskUpdatedDateRequest = Body(...)):
    """
    Update updatedAt field for all tasks in a project that don't have it set.
    Only updates tasks that don't already have an updatedAt value.
    """
    db = request.app.state.db
    project_id = req.projectId
    
    print(f"📅 Updating updatedAt for tasks in project: {project_id}")
    
    # Verify project exists
    try:
        project = await db.projects.find_one({"_id": ObjectId(project_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid project ID format")
        
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Find tasks without updatedAt field or with null updatedAt
    tasks_without_updated_at = await db.tasks.find({
        "project_id": project_id,
        "$or": [
            {"updatedAt": {"$exists": False}},
            {"updatedAt": None}
        ]
    }).to_list(length=None)
    
    if not tasks_without_updated_at:
        return {
            "status": "success",
            "message": "All tasks already have updatedAt field",
            "updatedCount": 0
        }
    
    # Update each task incrementally with current datetime
    current_datetime = datetime.now()
    updated_count = 0
    
    for task in tasks_without_updated_at:
        await db.tasks.update_one(
            {"_id": task["_id"]},
            {"$set": {"updatedAt": current_datetime}}
        )
        updated_count += 1
    
    print(f"✅ Updated {updated_count} tasks with updatedAt field")
    
    return {
        "status": "success",
        "message": f"Successfully updated {updated_count} tasks",
        "projectId": project_id,
        "updatedCount": updated_count
    }
class TriggerEmailRequest(BaseModel):
    userId: str

def get_ordinal_date_string(dt: datetime) -> str:
    """Returns date in format: 22nd Feb 2026"""
    suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(dt.day % 10 if dt.day > 20 or dt.day < 10 else 0, 'th')
    return dt.strftime(f"%-d{suffix} %b %Y")

@router.post("/trigger-email", status_code=200)
async def trigger_email(request: Request, req: TriggerEmailRequest = Body(...)):
    """
    Trigger a templated email with user task progress stats.
    """
    db = request.app.state.db
    user_id = req.userId
    
    # 1. Get user assignments
    assignment = await db.assignments.find_one({"userId": user_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="User assignments not found")
        
    tasks = assignment.get("tasks", [])
    
    # 2. Calculate Stats
    active_tasks = [t for t in tasks if t.get("taskStatus") == "active"]
    completed_tasks = [t for t in tasks if t.get("taskStatus") == "completed"]
    
    active_count = len(active_tasks)
    completed_count = len(completed_tasks)
    total_relevant = active_count + completed_count
    
    if total_relevant > 0:
        percentage = int((completed_count / total_relevant) * 100)
    else:
        percentage = 0
        
    formatted_percentage = f"{percentage}%"
    
    # 3. Get Active Task Names
    active_task_names = []
    if active_tasks:
        active_ids = [ObjectId(t["taskId"]) for t in active_tasks if ObjectId.is_valid(t["taskId"])]
        if active_ids:
            cursor = db.tasks.find({"_id": {"$in": active_ids}})
            async for task_doc in cursor:
                # Prefer 'name', fall back to 'title'
                name = task_doc.get("name") or task_doc.get("title") or "Unnamed Task"
                active_task_names.append(name)
    
    if active_task_names:
        agent_message3 = "<br>".join([f"{i+1}. {name}" for i, name in enumerate(active_task_names)])
    else:
        agent_message3 = "Oops! Looks like there are no tasks assigned to you. Please connect with Vijender and get yourself some tasks assigned to you at the earliest."
    
    # 4. Prepare Payload
    current_date = get_ordinal_date_string(datetime.now())
    
    email_payload = {
        "userId": user_id,
        "templateId": "2518b.6d1e43aa616e32a8.k1.a32f2371-f782-11f0-89cb-cabf48e1bf81.19be563ef1e",
        "email_parameters": {
            "date": current_date,
            "agent_message1": "Hope you are doing well",
            "agent_message2": formatted_percentage,
            "agent_message3": agent_message3
        }
    }
    
    print(f"📧 Triggering email for {user_id}: {json.dumps(email_payload, indent=2)}")
    
    # 5. Send External Request
    external_url = "https://api.alumnx.com/api/communication/sendTemplatedEmail"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(external_url, json=email_payload, timeout=10.0)
            
        if response.status_code >= 200 and response.status_code < 300:
            return {"status": "success", "message": "Email triggered successfully", "external_response": response.json()}
        else:
            print(f"❌ Email API failed: {response.status_code} - {response.text}")
            raise HTTPException(status_code=502, detail=f"External email service failed: {response.text}")
            
    except httpx.RequestError as e:
        print(f"❌ Network error calling email API: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Failed to connect to email service: {str(e)}")