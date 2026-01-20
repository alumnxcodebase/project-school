# tasks.py

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
    return [serialize(doc) async for doc in cursor]


@router.post("/", status_code=201)
async def create_task(request: Request, task: Task = Body(...)):
    """Create a new task"""
    db = request.app.state.db
    task_dict = task.model_dump(exclude={"id"})
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
    return serialize(task)


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
    return serialize(updated_task)


@router.delete("/{task_id}", status_code=204)
async def delete_task(request: Request, task_id: str):
    """Delete a task"""
    db = request.app.state.db
    result = await db.tasks.delete_one({"_id": ObjectId(task_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
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
            project_name = "Unknown Project"
            
            if project_id and ObjectId.is_valid(project_id):
                project = await db.projects.find_one({"_id": ObjectId(project_id)})
                if project:
                    project_name = project.get("name", "Unknown Project")
            
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
                comments=task_assignment.get("comments", [])
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


@router.delete("/user-tasks/{user_id}/{task_id}", status_code=200)
async def unlink_task_from_user(request: Request, user_id: str, task_id: str):
    """
    Remove a task from user's assignments.
    """
    db = request.app.state.db
    
    result = await db.assignments.update_one(
        {"userId": user_id},
        {"$pull": {"tasks": {"taskId": task_id}}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="User assignment not found")
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task not found in user's assignments")
    
    return {"status": "success", "message": "Task removed from user"}


@router.put("/user-tasks/{user_id}/{task_id}/complete", status_code=200)
async def mark_task_complete(request: Request, user_id: str, task_id: str):
    """
    Mark a task as completed for a user.
    """
    db = request.app.state.db
    
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
    
    return {"status": "success", "message": "Task marked as complete"}


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
            taskStatus="pending",
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