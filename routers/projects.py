# projects.py
from fastapi import APIRouter, Request, Body, HTTPException
from models import Project, ProjectWithTasks, Task
from utils.helpers import serialize
from bson import ObjectId
from typing import List
from models import (
    Project, 
    ProjectWithTasks, 
    Task,
    ProjectWithTasksAndAssignment,
    TaskWithAssignment,
    GetProjectTasksRequest
)
router = APIRouter()


@router.get("/", response_model=List[Project])
async def list_projects(request: Request):
    db = request.app.state.db
    cursor = db.projects.find().sort("created_at", -1)
    return [serialize(doc) async for doc in cursor]


@router.post("/", response_model=Project, status_code=201)
async def create_new_project(request: Request, project: Project = Body(...)):
    db = request.app.state.db
    project_dict = project.model_dump(exclude={"id"})
    result = await db.projects.insert_one(project_dict)

    new_project = await db.projects.find_one({"_id": result.inserted_id})
    return serialize(new_project)


@router.get("/{project_id}", response_model=ProjectWithTasks)
async def get_project_details(request: Request, project_id: str):
    """
    Get project details along with all associated tasks.
    """
    db = request.app.state.db
    
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid Project ID")

    project = await db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project_data = serialize(project)
    
    tasks_cursor = db.tasks.find({"project_id": project_id})
    tasks = [serialize(task) async for task in tasks_cursor]
    
    project_with_tasks = {
        **project_data,
        "tasks": tasks
    }
    
    return project_with_tasks


@router.get("/{project_id}/stats")
async def get_project_stats(request: Request, project_id: str):
    """Get statistics about tasks in a project"""
    db = request.app.state.db
    tasks = await db.tasks.find({"project_id": project_id}).to_list(length=100)
    return {
        "total_tasks": len(tasks),
        "total_time": sum(task.get("estimatedTime", 0) for task in tasks)
    }

# Add this endpoint to projects.py

@router.post("/get-project-tasks-assigned-to-user", response_model=ProjectWithTasksAndAssignment)
async def get_project_tasks_assigned_to_user(
    request: Request, 
    req: GetProjectTasksRequest = Body(...)
):
    """
    Get all tasks for a project with assignment status for a specific user.
    Returns project details with tasks and isAssigned field for each task.
    """
    db = request.app.state.db
    
    if not ObjectId.is_valid(req.projectId):
        raise HTTPException(status_code=400, detail="Invalid Project ID")
    
    # Get project details
    project = await db.projects.find_one({"_id": ObjectId(req.projectId)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get all tasks for this project
    tasks_cursor = db.tasks.find({"project_id": req.projectId})
    tasks = await tasks_cursor.to_list(length=None)
    
    # Get user's assignments
    assignment = await db.assignments.find_one({"userId": req.userId})
    assigned_task_ids = set()
    
    if assignment and assignment.get("tasks"):
        assigned_task_ids = {task.get("taskId") for task in assignment.get("tasks", [])}
    
    # Build response with isAssigned field
    tasks_with_assignment = []
    for task in tasks:
        task_id = str(task["_id"])
        task_with_assignment = TaskWithAssignment(
            id=task_id,
            project_id=task.get("project_id"),
            title=task.get("title", task.get("name", "Unnamed Task")),
            description=task.get("description"),
            estimatedTime=task.get("estimatedTime", 0),
            skillType=task.get("skillType", "General"),
            isAssigned=(task_id in assigned_task_ids)
        )
        tasks_with_assignment.append(task_with_assignment)
    
    # Build project response
    response = ProjectWithTasksAndAssignment(
        id=str(project["_id"]),
        name=project.get("name"),
        description=project.get("description"),
        projectType=project.get("projectType", "project"),
        status=project.get("status", "active"),
        created_at=project.get("created_at"),
        tasks=tasks_with_assignment
    )
    
    return response