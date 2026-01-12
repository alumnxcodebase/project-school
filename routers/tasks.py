from fastapi import APIRouter, Request, Body, HTTPException
from models import Task, TaskUpdate, UserTaskLink, TaskResponse
from utils.helpers import serialize
from bson import ObjectId
from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel

router = APIRouter()


class TaskCommentRequest(BaseModel):
    """Request model for saving task comments"""
    userId: str
    taskId: str
    comment: str
    commentBy: Optional[Literal["user", "admin"]] = "user"


@router.post("/", response_model=Task, status_code=201)
async def create_task(request: Request, task: Task = Body(...)):
    db = request.app.state.db
    task_dict = task.model_dump(exclude={"id"})
    result = await db.tasks.insert_one(task_dict)

    new_task = await db.tasks.find_one({"_id": result.inserted_id})
    return serialize(new_task)


@router.get("/user/{user_id}", response_model=List[TaskResponse])
async def get_user_tasks(request: Request, user_id: str):
    """
    Get all tasks assigned to a user from the assignments collection.
    """
    db = request.app.state.db
    
    # Get user's assignment document
    assignment = await db.assignments.find_one({"userId": user_id})
    
    if not assignment or not assignment.get("tasks"):
        return []
    
    response_tasks = []
    
    for task_assignment in assignment["tasks"]:
        task_id = task_assignment["taskId"]
        
        # Validate ObjectId
        if not ObjectId.is_valid(task_id):
            continue
        
        # Fetch task details
        task = await db.tasks.find_one({"_id": ObjectId(task_id)})
        if not task:
            continue
        
        # Fetch project details
        project = await db.projects.find_one({"_id": ObjectId(task["project_id"])})
        if not project:
            continue
        
        # Build response
        task_response = TaskResponse(
            taskId=task_id,
            name=task.get("title", ""),
            description=task.get("description"),
            projectId=task["project_id"],
            projectName=project.get("name", ""),
            assignedBy=task_assignment.get("assignedBy", "admin"),
            sequenceId=task_assignment.get("sequenceId"),
            isCompleted=task_assignment.get("isCompleted", False),
            comments=task_assignment.get("comments", [])
        )
        
        response_tasks.append(task_response)
    
    return response_tasks


@router.put("/{task_id}", response_model=Task)
async def update_task_status(request: Request, task_id: str, update: TaskUpdate):
    db = request.app.state.db
    if not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=400, detail="Invalid Task ID")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    await db.tasks.update_one({"_id": ObjectId(task_id)}, {"$set": update_data})

    updated = await db.tasks.find_one({"_id": ObjectId(task_id)})
    return serialize(updated)


@router.post("/user-tasks", status_code=201)
async def link_user_to_task(request: Request, payload: UserTaskLink = Body(...)):
    """
    Assign a task to a user by adding it to the assignments collection.
    Creates or updates the user's assignment document.
    """
    db = request.app.state.db
    
    # Validate taskId
    if not ObjectId.is_valid(payload.taskId):
        raise HTTPException(status_code=400, detail="Invalid taskId format")
    
    # Verify task exists
    task = await db.tasks.find_one({"_id": ObjectId(payload.taskId)})
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Create task assignment object
    task_assignment = {
        "taskId": payload.taskId,
        "assignedBy": payload.assignedBy,
        "sequenceId": payload.sequenceId,
        "isCompleted": False,
        "comments": []
    }
    
    # Update or create assignment document
    result = await db.assignments.update_one(
        {"userId": payload.userId},
        {
            "$addToSet": {"tasks": task_assignment}
        },
        upsert=True
    )
    
    return {
        "status": "success", 
        "message": f"Task {payload.taskId} assigned to user {payload.userId}"
    }


@router.put("/user-tasks/{user_id}/{task_id}", status_code=200)
async def update_user_task_assignment(
    request: Request, 
    user_id: str, 
    task_id: str,
    isCompleted: Optional[bool] = None,
    sequenceId: Optional[int] = None,
    comment: Optional[str] = None,
    commentBy: Optional[Literal["user", "admin"]] = None
):
    """
    Update a specific task assignment for a user.
    Can update completion status, sequence, or add comments.
    """
    db = request.app.state.db
    
    update_fields = {}
    
    if isCompleted is not None:
        update_fields["tasks.$[elem].isCompleted"] = isCompleted
    
    if sequenceId is not None:
        update_fields["tasks.$[elem].sequenceId"] = sequenceId
    
    # Add comment if provided
    if comment and commentBy:
        new_comment = {
            "comment": comment,
            "commentBy": commentBy,
            "createdAt": datetime.now()
        }
        await db.assignments.update_one(
            {"userId": user_id},
            {"$push": {"tasks.$[elem].comments": new_comment}},
            array_filters=[{"elem.taskId": task_id}]
        )
    
    # Update other fields if any
    if update_fields:
        result = await db.assignments.update_one(
            {"userId": user_id},
            {"$set": update_fields},
            array_filters=[{"elem.taskId": task_id}]
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Assignment not found")
    
    return {"status": "success", "message": "Assignment updated"}

@router.post("/rearrange-user-tasks", status_code=200)
async def rearrange_user_tasks(request: Request, payload: dict = Body(...)):
    """
    Rearrange tasks for a user by updating their sequenceId values.
    Accepts a list of tasks with updated sequenceIds.
    """
    db = request.app.state.db
    
    user_id = payload.get("userId")
    tasks = payload.get("tasks", [])
    
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
    
    if not tasks:
        raise HTTPException(status_code=400, detail="tasks array is required")
    
    # Verify user assignment exists
    assignment = await db.assignments.find_one({"userId": user_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="No assignments found for this user")
    
    # Update sequenceId for each task
    for task_update in tasks:
        task_id = task_update.get("taskId")
        sequence_id = task_update.get("sequenceId")
        
        if not task_id or sequence_id is None:
            continue
        
        # Update the sequenceId for the specific task in the array
        await db.assignments.update_one(
            {"userId": user_id},
            {"$set": {"tasks.$[elem].sequenceId": sequence_id}},
            array_filters=[{"elem.taskId": task_id}]
        )
    
    return {
        "status": "success",
        "message": f"Task order updated for user {user_id}"
    }


@router.post("/delete-user-task", status_code=200)
async def delete_user_task(request: Request, payload: dict = Body(...)):
    """
    Delete a task assignment from a user's task list.
    Removes the task from the assignments collection.
    """
    db = request.app.state.db
    
    user_id = payload.get("userId")
    task_id = payload.get("taskId")
    
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
    
    if not task_id:
        raise HTTPException(status_code=400, detail="taskId is required")
    
    # Verify user assignment exists
    assignment = await db.assignments.find_one({"userId": user_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="No assignments found for this user")
    
    # Remove the task from the user's tasks array
    result = await db.assignments.update_one(
        {"userId": user_id},
        {"$pull": {"tasks": {"taskId": task_id}}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=404, 
            detail=f"Task {task_id} not found in user's assignments"
        )
    
    return {
        "status": "success",
        "message": f"Task {task_id} deleted from user {user_id}'s assignments"
    }


@router.post("/task-comments", status_code=200)
async def save_task_comment(request: Request, payload: TaskCommentRequest = Body(...)):
    """
    Save a comment for a specific task in the assignments collection.
    Adds a new comment to the task's comments array.
    
    Request body:
    - userId: str (required) - The ID of the user
    - taskId: str (required) - The ID of the task
    - comment: str (required) - The comment text
    - commentBy: str (optional) - Either "user" or "admin", defaults to "user"
    """
    db = request.app.state.db
    
    # Validate that comment is not empty after stripping
    if not payload.comment.strip():
        raise HTTPException(status_code=400, detail="comment cannot be empty")
    
    # Verify user assignment exists
    assignment = await db.assignments.find_one({"userId": payload.userId})
    if not assignment:
        raise HTTPException(status_code=404, detail="No assignments found for this user")
    
    # Verify task exists in user's assignments
    task_found = any(task.get("taskId") == payload.taskId for task in assignment.get("tasks", []))
    if not task_found:
        raise HTTPException(
            status_code=404, 
            detail=f"Task {payload.taskId} not found in user's assignments"
        )
    
    # Create comment object
    new_comment = {
        "comment": payload.comment.strip(),
        "commentBy": payload.commentBy,
        "createdAt": datetime.now()
    }
    
    # Add comment to the task's comments array
    result = await db.assignments.update_one(
        {"userId": payload.userId},
        {"$push": {"tasks.$[elem].comments": new_comment}},
        array_filters=[{"elem.taskId": payload.taskId}]
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=500, 
            detail="Failed to save comment"
        )
    
    return {
        "status": "success",
        "message": "Comment saved successfully",
        "comment": new_comment
    }


@router.post("/update-task-completion-status", status_code=200)
async def update_task_completion_status(request: Request, payload: dict = Body(...)):
    """
    Update the completion status of a task in the assignments collection.
    
    Request body:
    - userId: str (required) - The ID of the user
    - taskId: str (required) - The ID of the task
    - isCompleted: bool (required) - The completion status (true for completed, false for pending)
    """
    db = request.app.state.db
    
    user_id = payload.get("userId")
    task_id = payload.get("taskId")
    is_completed = payload.get("isCompleted")
    
    # Validate required fields
    if not user_id:
        raise HTTPException(status_code=400, detail="userId is required")
    
    if not task_id:
        raise HTTPException(status_code=400, detail="taskId is required")
    
    if is_completed is None:
        raise HTTPException(status_code=400, detail="isCompleted is required")
    
    # Verify user assignment exists
    assignment = await db.assignments.find_one({"userId": user_id})
    if not assignment:
        raise HTTPException(status_code=404, detail="No assignments found for this user")
    
    # Verify task exists in user's assignments
    task_found = any(task.get("taskId") == task_id for task in assignment.get("tasks", []))
    if not task_found:
        raise HTTPException(
            status_code=404, 
            detail=f"Task {task_id} not found in user's assignments"
        )
    
    # Update the task completion status
    result = await db.assignments.update_one(
        {"userId": user_id},
        {"$set": {"tasks.$[elem].isCompleted": is_completed}},
        array_filters=[{"elem.taskId": task_id}]
    )
    
    if result.modified_count == 0:
        raise HTTPException(
            status_code=500, 
            detail="Failed to update task completion status"
        )
    
    return {
        "status": "success",
        "message": f"Task completion status updated to {'completed' if is_completed else 'pending'}",
        "isCompleted": is_completed
    }