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
import os

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
        ADMIN_ID = "6928870c5b168f52cf8bd77a"
        query["$or"] = [
            {"createdBy": None},
            {"createdBy": "admin"},
            {"createdBy": ADMIN_ID},
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
    
    # Handle new fields
    task_dict["day"] = task.day
    task_dict["taskType"] = task.taskType
    
    # Ensure isEnabled has a default value if not provided
    if "isEnabled" not in task_dict or task_dict["isEnabled"] is None:
        task_dict["isEnabled"] = False
    
    result = await db.tasks.insert_one(task_dict)
    created_task = await db.tasks.find_one({"_id": result.inserted_id})
    task_id_str = str(result.inserted_id)

    # --- Auto-assign logic based on Preferences ---
    # Find all users who want this skillType or "All"
    skill_type = task_dict.get("skillType")
    auto_assign = task_dict.get("autoAssign", True)
    
    ADMIN_ID = "6928870c5b168f52cf8bd77a"
    admin_creators = [None, "admin", ADMIN_ID]
    creator = task_dict.get("createdBy")

    if skill_type and auto_assign and (creator in admin_creators):
        print(f"🔄 Checking preferences for auto-assigning task {task_id_str} ({skill_type})")
        
        # Query for users with preferences containing "All" or the specific skillType
        matching_prefs_cursor = db.preferences.find({
            "preferences": {"$in": ["All", skill_type]}
        })
        
        assigned_count = 0
        
        async for pref_doc in matching_prefs_cursor:
            user_id = pref_doc["userId"]
            
            # --- Duplicate Prevention Check ---
            # Check if user already has this specific task ID OR a task with identical content
            assignment = await db.assignments.find_one({"userId": user_id})
            if assignment and assignment.get("tasks"):
                assigned_task_ids = [ObjectId(t["taskId"]) for t in assignment.get("tasks") if ObjectId.is_valid(t.get("taskId"))]
                
                # Check for exact taskId match first (fast)
                if task_id_str in [str(tid) for tid in assigned_task_ids]:
                    print(f"⏭️ Skipping user {user_id} - Task ID {task_id_str} already assigned")
                    continue
                    
                # Check for content match (Title, Description, SkillType)
                assigned_details = await db.tasks.find({"_id": {"$in": assigned_task_ids}}).to_list(length=None)
                is_content_duplicate = False
                for existing_task in assigned_details:
                    if (existing_task.get("title") == task_dict.get("title") and 
                        existing_task.get("description") == task_dict.get("description") and 
                        existing_task.get("skillType") == task_dict.get("skillType")):
                        is_content_duplicate = True
                        break
                
                if is_content_duplicate:
                    print(f"⏭️ Skipping user {user_id} - task with same content already assigned")
                    continue
            # ----------------------------------
            
            # Create the task assignment object
            new_assignment_data = TaskAssignment(
                taskId=task_id_str,
                assignedBy="admin", # System auto-assign
                sequenceId=None, # No specific sequence
                taskStatus="active", # Mark as active immediately as per requirement
                expectedCompletionDate=None
            ).model_dump()
            
            # Ensure the task itself is enabled if assigned by admin
            await db.tasks.update_one(
                {"_id": ObjectId(task_id_str)},
                {"$set": {"isEnabled": True}}
            )
            
            # Upsert into assignments collection
            await db.assignments.update_one(
                {"userId": user_id},
                {
                    "$push": {"tasks": new_assignment_data},
                    "$setOnInsert": {
                        "userId": user_id, 
                        "id": str(ObjectId()) 
                    } 
                },
                upsert=True
            )
            assigned_count += 1
            
        print(f"✅ Auto-assigned task {task_id_str} to {assigned_count} users")

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
    Includes content-based deduplication.
    """
    db = request.app.state.db
    
    # Verify task exists
    task_doc = await db.tasks.find_one({"_id": ObjectId(link.taskId)})
    if not task_doc:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Check if user already has this task assigned OR a content duplicate
    assignment = await db.assignments.find_one({"userId": link.userId})
    
    if assignment and assignment.get("tasks"):
        assigned_task_ids = [ObjectId(t["taskId"]) for t in assignment.get("tasks") if ObjectId.is_valid(t.get("taskId"))]
        
        # 1. Exact taskId match
        if link.taskId in [str(tid) for tid in assigned_task_ids]:
             return {"status": "success", "message": "Task already assigned (ID match)"}
             
        # 2. Content match
        assigned_details = await db.tasks.find({"_id": {"$in": assigned_task_ids}}).to_list(length=None)
        for existing_task in assigned_details:
            if (existing_task.get("title") == task_doc.get("title") and 
                existing_task.get("description") == task_doc.get("description") and 
                existing_task.get("skillType") == task_doc.get("skillType")):
                return {"status": "success", "message": "Task already assigned (content match)"}

    # Set status to active if assigned by admin
    is_admin_assignment = link.assignedBy == "admin" or link.userId == "6928870c5b168f52cf8bd77a"
    task_status = "active" if is_admin_assignment else "pending"
    
    # If admin assigns, ensure the task is enabled globally
    if is_admin_assignment:
        await db.tasks.update_one(
            {"_id": ObjectId(link.taskId)},
            {"$set": {"isEnabled": True}}
        )

    new_task_assignment = TaskAssignment(
        taskId=link.taskId,
        assignedBy=link.assignedBy,
        sequenceId=link.sequenceId,
        taskStatus=task_status,
        expectedCompletionDate=link.expectedCompletionDate
    ).model_dump()

    await db.assignments.update_one(
        {"userId": link.userId},
        {
            "$push": {"tasks": new_task_assignment},
            "$setOnInsert": {
                "userId": link.userId,
                "id": str(ObjectId())
            }
        },
        upsert=True
    )
    
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
        
        # Collect all task responses
        task_responses = []
        
        for task_assignment in assignment.get("tasks", []):
            task_id = task_assignment.get("taskId")
            
            # Validate task_id format
            if not task_id or not ObjectId.is_valid(task_id):
                print(f"⚠️ Invalid task_id: {task_id}, skipping...")
                continue
            
            # Get task details
            task = await db.tasks.find_one({"_id": ObjectId(task_id)})
            if not task:
                print(f"⚠️ Task not found: {task_id}, skipping...")
                continue
            
            # Get project details
            project_id = task.get("project_id")
            project_name = "Personal"
            
            ADMIN_ID = "6928870c5b168f52cf8bd77a"
            admin_creators = [None, "admin", ADMIN_ID]

            if project_id and ObjectId.is_valid(project_id):
                project = await db.projects.find_one({"_id": ObjectId(project_id)})
                if project:
                    project_name = project.get("name", "Personal")
                    
                    # --- Privacy Check ---
                    # Ensure user only sees tasks from:
                    # 1. Admin projects (Global)
                    # 2. Their own private projects
                    # 3. Tasks explicitly assigned to them? (Wait, if I assign a task to you in my private project, you should see it?
                    #    The user request says: "task created by the user in the project should also be visible to the user only"
                    #    So strict privacy is requested.)
                    
                    creator = project.get("createdBy")
                    is_admin_project = creator in admin_creators
                    is_owner = creator == user_id
                    is_admin_req = user_id == ADMIN_ID
                    
                    if not (is_admin_project or is_owner or is_admin_req):
                        # Skip this task if it belongs to a private project of another user
                        # excluding admin of course
                        continue
            
            # Build response
            task_response = TaskResponse(
                taskId=task_id,
                name=task.get("name", task.get("title", "Unnamed Task")),
                description=task.get("description", ""),
                estimatedTime=task.get("estimatedTime", 0),
                skillType=task.get("skillType", "General"),
                projectId=project_id if project_id else "",
                projectName=project_name,
                assignedBy=task_assignment.get("assignedBy", "admin"),
                sequenceId=task_assignment.get("sequenceId"),
                taskStatus=task_assignment.get("taskStatus", "pending"),
                expectedCompletionDate=task_assignment.get("expectedCompletionDate"),
                completionDate=task_assignment.get("completionDate"),
                comments=task_assignment.get("comments", []),
                createdBy=task.get("createdBy"),
                isEnabled=task.get("isEnabled", False),
                day=task.get("day"),
                taskType=task.get("taskType")
            )
            task_responses.append(task_response)
        
        # Sort by sequenceId
        task_responses.sort(key=lambda x: x.sequenceId if x.sequenceId is not None else 999)
        
        return task_responses
        
    except Exception as e:
        print(f"❌ Error in get_user_tasks: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching user tasks: {str(e)}")



@router.delete("/user-tasks/bulk-clear-all-users", status_code=200)
async def bulk_clear_all_users_tasks(request: Request):
    """
    Clear all assigned tasks for ALL users in the system.
    Sets the tasks array to empty for every assignment document.
    """
    try:
        db = request.app.state.db
        result = await db.assignments.update_many(
            {},
            {"$set": {"tasks": []}}
        )
        return {
            "status": "success",
            "message": f"Successfully cleared tasks for {result.modified_count} users",
            "modifiedCount": result.modified_count
        }
    except Exception as e:
        print(f"❌ Error in bulk_clear_all_users_tasks: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to clear all tasks: {str(e)}")


@router.delete("/user-tasks/{user_id}/clear", status_code=200)
async def clear_all_user_tasks(request: Request, user_id: str):
    """
    Clear all assigned tasks for a specific user.
    Sets the tasks array to empty while preserving the assignment document.
    """
    try:
        db = request.app.state.db
        
        # Check if assignment exists
        assignment = await db.assignments.find_one({"userId": user_id})
        
        if not assignment:
            raise HTTPException(
                status_code=404, 
                detail=f"No assignment document found for user {user_id}"
            )
        
        # Clear all tasks but keep the assignment document
        result = await db.assignments.update_one(
            {"userId": user_id},
            {"$set": {"tasks": []}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=404, 
                detail=f"Failed to update assignment for user {user_id}"
            )
        
        print(f"✅ Cleared all tasks for user {user_id}")
        
        return {
            "status": "success",
            "message": f"Successfully cleared all assigned tasks for user {user_id}",
            "userId": user_id
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error clearing assigned tasks: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to clear assigned tasks: {str(e)}")


@router.delete("/user-tasks/{user_id}/{task_id}", status_code=200)
async def delete_task_and_assignments(request: Request, user_id: str, task_id: str):
    """
    If user is creator: Delete task and remove from ALL users' assignments.
    If user is NOT creator: deny action (use unassign endpoint instead).
    """
    db = request.app.state.db
    
    # 1. Check task ownership
    task = await db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
         raise HTTPException(status_code=404, detail="Task not found")
         
    if task.get("createdBy") == user_id:
        # User IS the creator: Delete task and cleanup ALL assignments
        
        # Delete the task document
        await db.tasks.delete_one({"_id": ObjectId(task_id)})
        
        # Remove this task from ALL assignments documents
        await db.assignments.update_many(
            {"tasks.taskId": task_id},
            {"$pull": {"tasks": {"taskId": task_id}}}
        )
        
        return {"status": "success", "message": "Task deleted and removed from all assignments"}
    
    else:
        # User is NOT the creator
        raise HTTPException(
            status_code=403, 
            detail="Only the creator can delete this task. Use /task/user-task/{userId}/unassign/{taskId} to unassign yourself."
        )


@router.delete("/task/user-task/{user_id}/unassign/{task_id}", status_code=200)
async def unassign_user_from_task(request: Request, user_id: str, task_id: str):
    """
    Remove a task from user's assignments (Unassign only).
    Does not delete the task.
    """
    db = request.app.state.db
    
    result = await db.assignments.update_one(
        {"userId": user_id},
        {"$pull": {"tasks": {"taskId": task_id}}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User assignment not found")
    
    if result.modified_count == 0:
        return {"status": "success", "message": "Task was not in user's assignments"}
    
    return {"status": "success", "message": "Task removed from user assignments"}


@router.put("/user-tasks/{user_id}/{task_id}/complete", status_code=200)
async def mark_task_complete(request: Request, user_id: str, task_id: str):
    """
    Mark a task as completed for a user and trigger an agent proactive message.
    """
    db = request.app.state.db
    
    # 1. Update task status
    result = await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {
            "$set": {
                "tasks.$.taskStatus": "completed",
                "tasks.$.completionDate": datetime.now().isoformat()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task assignment not found")
    
    # 2. Get task details for the message
    task = await db.tasks.find_one({"_id": ObjectId(task_id)})
    if task:
        task_name = task.get("name") or task.get("title") or "the task"
    else:
        task_name = "the task"
    
    # 3. Get agent name
    agent_doc = await db.agents.find_one({"userId": user_id})
    agent_name = agent_doc.get("agentName", "Study Buddy") if agent_doc else "Study Buddy"
    
    # 4. Insert proactive message into chats
    # Check if a completion message was already sent recently to avoid duplicates if user toggles
    proactive_message = f"Great! You've completed '{task_name}'. Shall I assign the next task, or would you like to shift your learning preferences?"
    
    chat_doc = {
        "userId": user_id,
        "userType": "agent",
        "message": proactive_message,
        "timestamp": datetime.now()
    }
    await db.chats.insert_one(chat_doc)
    
    print(f"🤖 [AGENT] Proactive message added for user {user_id} after completing {task_name}")
    
    
    return {
        "status": "success", 
        "message": "Task marked as complete",
        "agentResponse": proactive_message
    }


@router.put("/user-tasks/{user_id}/{task_id}/comment", status_code=200)
async def add_comment_to_task(
    request: Request, 
    user_id: str, 
    task_id: str, 
    comment: Comment = Body(...)
):
    """
    Add a comment to a user's task.
    """
    db = request.app.state.db
    
    result = await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {"$push": {"tasks.$.comments": comment.model_dump()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task assignment not found")
    
    return {"status": "success", "message": "Comment added"}

@router.put("/user-tasks/{user_id}/{task_id}/active", status_code=200)
async def mark_task_active(request: Request, user_id: str, task_id: str):
    """
    Mark a task as active for a user.
    """
    db = request.app.state.db
    
    result = await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {
            "$set": {
                "tasks.$.taskStatus": "active"
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task assignment not found")
    
    return {"status": "success", "message": "Task marked as active"}

@router.post("/bulk-assign-tasks-to-user", status_code=200)
async def bulk_assign_tasks_to_user(request: Request, bulk_req: BulkAssignTasksRequest = Body(...)):
    """
    Bulk assign multiple tasks to a user with their sequence IDs.
    Replaces all existing task assignments for the user.
    
    Request body:
    {
        "userId": "user123",
        "tasks": [
            {"taskId": "task1", "sequenceId": 1},
            {"taskId": "task2", "sequenceId": 2},
            {"taskId": "task3", "sequenceId": 3}
        ]
    }
    """
    db = request.app.state.db
    user_id = bulk_req.userId
    tasks = bulk_req.tasks

    print(f"📦 Bulk assigning {len(tasks)} tasks to user: {user_id}")

    # Verify all tasks exist
    task_ids = [task.taskId for task in tasks]
    existing_tasks = await db.tasks.find(
        {"_id": {"$in": [ObjectId(tid) for tid in task_ids]}}
    ).to_list(length=None)
    
    existing_task_ids = {str(task["_id"]) for task in existing_tasks}
    invalid_tasks = set(task_ids) - existing_task_ids
    
    if invalid_tasks:
        raise HTTPException(
            status_code=404, 
            detail=f"Tasks not found: {', '.join(invalid_tasks)}"
        )

    # Create task assignments
    task_assignments = [
        TaskAssignment(
            taskId=task.taskId,
            assignedBy="admin",
            sequenceId=task.sequenceId,
            taskStatus="active",
            expectedCompletionDate=None
        ).model_dump()
        for task in tasks
    ]

    # Upsert assignment document (replace all tasks)
    result = await db.assignments.update_one(
        {"userId": user_id},
        {
            "$set": {"tasks": task_assignments}
        },
        upsert=True
    )

    print(f"✅ Bulk assigned {len(tasks)} tasks to user {user_id}")
    
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

class CustomEmailRequest(BaseModel):
    userId: str
    message: str
    userName: Optional[str] = None
    userEmail: Optional[str] = None

def get_ordinal_date_string(dt: datetime) -> str:
    """Returns date in format: 22nd Feb 2026"""
    day = dt.day
    suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(day % 10 if day > 20 or day < 10 else 0, 'th')
    return dt.strftime(f"{day}{suffix} %b %Y")

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
            print(f"❌ External email API returned error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=response.status_code, detail=f"Email service error: {response.text}")
            
    except httpx.RequestError as e:
        print(f"❌ Network error calling email API: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Failed to connect to email service: {str(e)}")


@router.post("/broadcast-task", status_code=200)
async def broadcast_task(request: Request, body: Dict[str, Any] = Body(...)):
    """
    Broadcast a task to ALL users in the system, bypassing skill preferences.
    """
    db = request.app.state.db
    task_id = body.get("taskId")
    admin_id = body.get("adminId") # For verification
    
    if admin_id != "6928870c5b168f52cf8bd77a":
        raise HTTPException(status_code=403, detail="Unauthorized broadcast attempt")

    task_doc = await db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task_doc:
        raise HTTPException(status_code=404, detail="Task not found")

    # Mark the task as enabled globally
    await db.tasks.update_one({"_id": ObjectId(task_id)}, {"$set": {"isEnabled": True}})

    users_cursor = db.users.find({}, {"_id": 1})
    assigned_count = 0
    
    async for user in users_cursor:
        user_id = str(user["_id"])
        
        # Check for duplicate
        assignment = await db.assignments.find_one({"userId": user_id})
        is_duplicate = False
        if assignment and assignment.get("tasks"):
            for t in assignment.get("tasks"):
                if t.get("taskId") == task_id:
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                 # Content check for broadcast too
                 task_ids = [ObjectId(t["taskId"]) for t in assignment["tasks"] if ObjectId.is_valid(t["taskId"])]
                 assigned_details = await db.tasks.find({"_id": {"$in": task_ids}}).to_list(length=None)
                 for existing_task in assigned_details:
                     if (existing_task.get("title") == task_doc.get("title") and 
                         existing_task.get("description") == task_doc.get("description")):
                         is_duplicate = True
                         break

        if is_duplicate:
            continue

        new_task_assignment = TaskAssignment(
            taskId=task_id,
            assignedBy="admin",
            taskStatus="active"
        ).model_dump()

        await db.assignments.update_one(
            {"userId": user_id},
            {
                "$push": {"tasks": new_task_assignment},
                "$setOnInsert": {"userId": user_id, "id": str(ObjectId())}
            },
            upsert=True
        )
        assigned_count += 1

    return {"status": "success", "message": f"Task broadcasted to {assigned_count} users"}


@router.post("/sync-admin-tasks/{user_id}", status_code=200)
async def sync_admin_tasks(request: Request, user_id: str):
    """
    Assign all existing admin/system-created tasks to a specific user.
    Skips tasks already assigned or with matching content.
    Uses bulk updates for performance.
    """
    db = request.app.state.db
    
    # 1. Fetch all admin/system tasks (createdBy is "admin" or None)
    admin_tasks_cursor = db.tasks.find({
        "$or": [
            {"createdBy": "admin"},
            {"createdBy": None}
        ]
    })
    admin_tasks = await admin_tasks_cursor.to_list(length=None)
    
    if not admin_tasks:
        return {"status": "success", "message": "No admin tasks found to sync", "addedCount": 0}

    # 2. Get user's current assignments to prevent duplicates
    assignment = await db.assignments.find_one({"userId": user_id})
    user_task_ids = set()
    user_task_contents = set()
    
    if assignment and assignment.get("tasks"):
        user_task_ids = {t.get("taskId") for t in assignment.get("tasks") if t.get("taskId")}
        
        # Fetch details of existing tasks to check content-based duplicates
        task_obj_ids = [ObjectId(tid) for tid in user_task_ids if ObjectId.is_valid(tid)]
        if task_obj_ids:
            assigned_details = await db.tasks.find({"_id": {"$in": task_obj_ids}}).to_list(length=None)
            user_task_contents = {(t.get("title", t.get("name")), t.get("description")) for t in assigned_details}

    # 3. Filter for tasks the user doesn't have yet
    new_assignments = []
    for task in admin_tasks:
        task_id_str = str(task["_id"])
        
        # Skip if ID match
        if task_id_str in user_task_ids:
            continue
            
        # Skip if content match
        if (task.get("title", task.get("name")), task.get("description")) in user_task_contents:
            continue

        # Prepare for bulk assignment
        new_task_assignment = TaskAssignment(
            taskId=task_id_str,
            assignedBy="admin",
            taskStatus="active"
        ).model_dump()
        new_assignments.append(new_task_assignment)
        
        # Update trackers to avoid duplicates within same scan
        user_task_ids.add(task_id_str)
        user_task_contents.add((task.get("title", task.get("name")), task.get("description")))

    if not new_assignments:
        return {"status": "success", "message": "User already has all admin tasks assigned", "addedCount": 0}

    # 4. Perform bulk update
    await db.assignments.update_one(
        {"userId": user_id},
        {
            "$push": {"tasks": {"$each": new_assignments}},
            "$setOnInsert": {"userId": user_id, "id": str(ObjectId())}
        },
        upsert=True
    )
        
    return {
        "status": "success", 
        "message": f"Successfully synced {len(new_assignments)} admin tasks to user {user_id}",
        "addedCount": len(new_assignments)
    }

@router.post("/send-custom-email", status_code=200)
async def send_custom_email(request: Request, req: CustomEmailRequest = Body(...)):
    """
    Send a custom templated email directly via ZeptoMail.
    """
    print(f"DEBUG: Received request for user: {req.userId}")
    user_id = req.userId
    custom_message = req.message
    user_name = req.userName
    user_email = req.userEmail
    
    if not user_id or not custom_message:
        raise HTTPException(status_code=422, detail="Missing userId or message")

    db = request.app.state.db
    
    # 1. Get User details (Use provided ones or fetch from DB)
    if not user_email or not user_name:
        # Try to fetch from DB if not provided
        try:
            obj_id = ObjectId(user_id)
            user_doc = await db.users.find_one({"_id": obj_id})
            if user_doc:
                user_email = user_email or user_doc.get("email")
                user_name = user_name or user_doc.get("fullName") or user_doc.get("userName") or "Student"
        except Exception:
            pass # Continue with what we have

    if not user_email:
        # Final fallback/error if we still don't have email
        raise HTTPException(status_code=404, detail="User email not found. Please provide it in the request.")
    
    user_name = user_name or "Student"

    # 2. Prepare Payload for ZeptoMail
    current_date = get_ordinal_date_string(datetime.now())
    template_id = "2518b.6d1e43aa616e32a8.k1.f80371c0-025f-11f1-9250-ae9c7e0b6a9f.19c2c97aadc"
    
    zepto_payload = {
        "from": {"address": "support@alumnx.com", "name": "Alumnx AI Labs"},
        "to": [{"email_address": {"address": user_email, "name": user_name}}],
        "template_key": template_id,
        "merge_info": {
            "date": current_date,
            "name": user_name,
            "agent_message": custom_message
        }
    }

    # 3. Send to ZeptoMail directly
    zepto_token = os.getenv("ZEPTO_MAIL_TOKEN")
    if not zepto_token:
        raise HTTPException(status_code=500, detail="ZeptoMail token not configured in backend")

    url = "https://api.zeptomail.in/v1.1/email/template"
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": zepto_token
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=zepto_payload, headers=headers, timeout=10.0)
            
        if response.status_code >= 200 and response.status_code < 300:
            print(f"✅ Custom email sent successfully to {user_email}")
            return {"status": "success", "message": "Custom email sent successfully", "zepto_response": response.json()}
        else:
            print(f"❌ ZeptoMail API returned error: {response.status_code} - {response.text}")
            raise HTTPException(status_code=response.status_code, detail=f"ZeptoMail service error: {response.text}")
            
    except httpx.RequestError as e:
        print(f"❌ Network error calling ZeptoMail: {str(e)}")
        raise HTTPException(status_code=503, detail=f"Failed to connect to ZeptoMail service: {str(e)}")
