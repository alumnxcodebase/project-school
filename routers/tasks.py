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
    Comment
)

router = APIRouter()


def serialize(doc):
    """Helper to convert MongoDB _id to string id"""
    if not doc:
        return None
    doc["id"] = str(doc.pop("_id"))
    return doc

@router.get("/")
async def get_all_tasks(request: Request, project_id: str = None):
    """Get all tasks, optionally filtered by project_id"""
    db = request.app.state.db
    query = {"project_id": project_id} if project_id else {}
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


@router.post("/user-tasks", status_code=200)
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
    
    # Get user's assignment document
    assignment = await db.assignments.find_one({"userId": user_id})
    if not assignment or not assignment.get("tasks"):
        return []
    
    # Collect all task responses
    task_responses = []
    
    for task_assignment in assignment.get("tasks", []):
        task_id = task_assignment.get("taskId")
        
        # Get task details
        task = await db.tasks.find_one({"_id": ObjectId(task_id)})
        if not task:
            continue
        
        # Get project details
        project_id = task.get("project_id")
        project = await db.projects.find_one({"_id": ObjectId(project_id)})
        project_name = project.get("name", "Unknown Project") if project else "Unknown Project"
        
        # Build response
        task_response = TaskResponse(
            taskId=task_id,
            name=task.get("name", task.get("title", "Unnamed Task")),
            description=task.get("description", ""),
            estimatedTime=task.get("estimatedTime", 0),
            skillType=task.get("skillType", "General"),
            projectId=project_id,
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
                "tasks.$.taskStatus": "completed",  # Changed from isCompleted: True
                "tasks.$.completionDate": datetime.now().isoformat()
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task assignment not found")
    
    return {"status": "success", "message": "Task marked as complete"}


@router.put("/user-tasks/{user_id}/{task_id}/incomplete", status_code=200)
async def mark_task_incomplete(request: Request, user_id: str, task_id: str):
    """
    Mark a task as incomplete for a user.
    """
    db = request.app.state.db
    
    result = await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {
            "$set": {
                "tasks.$.taskStatus": "pending",  # Changed from isCompleted: False
                "tasks.$.completionDate": None
            }
        }
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task assignment not found")
    
    return {"status": "success", "message": "Task marked as incomplete"}


class AddCommentRequest(BaseModel):
    comment: str
    commentBy: str  # "user" or "admin"


@router.post("/user-tasks/{user_id}/{task_id}/comments", status_code=200)
async def add_task_comment(
    request: Request, 
    user_id: str, 
    task_id: str, 
    comment_req: AddCommentRequest = Body(...)
):
    """
    Add a comment to a user's task assignment.
    """
    db = request.app.state.db
    
    new_comment = Comment(
        comment=comment_req.comment,
        commentBy=comment_req.commentBy,
        createdAt=datetime.now()
    )
    
    result = await db.assignments.update_one(
        {"userId": user_id, "tasks.taskId": task_id},
        {"$push": {"tasks.$.comments": new_comment.model_dump()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task assignment not found")
    
    return {"status": "success", "message": "Comment added successfully"}    

@router.delete("/delete-assigned-tasks/{user_id}", status_code=200)
async def delete_assigned_tasks(request: Request, user_id: str):
    """
    Clear all tasks assigned to a specific user in the assignments collection.
    """
    db = request.app.state.db

    print(f"🗑️ Clearing all assigned tasks for user: {user_id}")

    try:
        # Update the assignment document to clear the tasks array
        result = await db.assignments.update_one(
            {"userId": user_id},
            {"$set": {"tasks": []}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="No assignments found for this user")
        
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