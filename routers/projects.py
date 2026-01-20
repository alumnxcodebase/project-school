# projects.py - Update endpoints
from fastapi import APIRouter, Request, Body, HTTPException
from models import Project, ProjectWithTasks, Task
from utils.helpers import serialize
from bson import ObjectId
from typing import List, Optional
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
async def list_projects(request: Request, userId: Optional[str] = None):
    """Get all projects - admin projects and user-created projects"""
    db = request.app.state.db
    
    # Build query to get admin projects (createdBy is None or admin user) 
    # and projects created by the current user
    if userId:
        query = {
            "$or": [
                {"createdBy": None},  # Admin projects
                {"createdBy": "6928870c5b168f52cf8bd77a"},  # Specific admin user
                {"createdBy": userId}  # User's own projects
            ]
        }
    else:
        query = {}
    
    print(f"🔍 Fetching projects with query: {query}")
    cursor = db.projects.find(query).sort("created_at", -1)
    projects = [serialize(doc) async for doc in cursor]
    print(f"✅ Found {len(projects)} projects")
    return projects


@router.post("/", response_model=Project, status_code=201)
async def create_new_project(request: Request, project: Project = Body(...)):
    db = request.app.state.db
    project_dict = project.model_dump(exclude={"id"})
    print(f"📝 Creating project: {project_dict}")
    result = await db.projects.insert_one(project_dict)

    new_project = await db.projects.find_one({"_id": result.inserted_id})
    print(f"✅ Created project with ID: {result.inserted_id}")
    return serialize(new_project)


@router.get("/{project_id}", response_model=ProjectWithTasks)
async def get_project_details(request: Request, project_id: str, userId: Optional[str] = None):
    """
    Get project details along with all associated tasks.
    Returns tasks created by admin or the specified userId with their assignment status.
    """
    db = request.app.state.db
    
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid Project ID")

    project = await db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    project_data = serialize(project)
    
    # Build query to get tasks created by admin or the specified user
    task_query = {"project_id": project_id}
    if userId:
        task_query["$or"] = [
            {"createdBy": None},
            {"createdBy": "admin"},
            {"createdBy": "6928870c5b168f52cf8bd77a"},
            {"createdBy": userId}
        ]
    
    # ONLY CHANGE: Add sorting by updatedAt descending (newest first)
    tasks_cursor = db.tasks.find(task_query).sort([("updatedAt", -1)])
    tasks = [serialize(task) async for task in tasks_cursor]
    
    # Get user's assignments if userId is provided
    task_status_map = {}
    if userId:
        assignment = await db.assignments.find_one({"userId": userId})
        if assignment and assignment.get("tasks"):
            for task_assignment in assignment.get("tasks", []):
                task_status_map[task_assignment.get("taskId")] = task_assignment.get("taskStatus")
    
    # Add taskStatus to each task
    tasks_with_status = []
    for task in tasks:
        task_id = task.get("id")
        task_with_status = {
            **task,
            "taskStatus": task_status_map.get(task_id),
            "isAssigned": task_id in task_status_map
        }
        tasks_with_status.append(task_with_status)
    
    project_with_tasks = {
        **project_data,
        "tasks": tasks_with_status
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


@router.post("/get-project-tasks-assigned-to-user", response_model=ProjectWithTasksAndAssignment)
async def get_project_tasks_assigned_to_user(
    request: Request, 
    req: GetProjectTasksRequest = Body(...)
):
    """
    Get all tasks for a project with assignment status for a specific user.
    Returns project details with tasks and isAssigned field for each task.
    Only returns tasks created by admin or the specified user.
    """
    db = request.app.state.db
    
    if not ObjectId.is_valid(req.projectId):
        raise HTTPException(status_code=400, detail="Invalid Project ID")
    
    # Get project details
    project = await db.projects.find_one({"_id": ObjectId(req.projectId)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Get all tasks for this project (admin or user-created)
    task_query = {
        "project_id": req.projectId,
        "$or": [
            {"createdBy": None},
            {"createdBy": "admin"},
            {"createdBy": "6928870c5b168f52cf8bd77a"},
            {"createdBy": req.userId}
        ]
    }
    # ONLY CHANGE: Add sorting by updatedAt descending (newest first)
    tasks_cursor = db.tasks.find(task_query).sort([("updatedAt", -1)])
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


@router.delete("/{project_id}", status_code=200)
async def delete_project(request: Request, project_id: str):
    """
    Delete a project and all associated data:
    1. Delete all tasks in the project
    2. Remove those tasks from user assignments
    3. Delete the project itself
    """
    db = request.app.state.db
    
    # Validate project ID format
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid Project ID format")
    
    # Check if project exists
    project = await db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    print(f"🗑️ Deleting project: {project_id}")
    
    # Step 1: Get all tasks for this project
    tasks_cursor = db.tasks.find({"project_id": project_id})
    tasks = await tasks_cursor.to_list(length=None)
    task_ids = [str(task["_id"]) for task in tasks]
    
    print(f"📋 Found {len(task_ids)} tasks to delete")
    
    # Step 2: Remove these tasks from all user assignments
    if task_ids:
        # Remove tasks from assignments collection
        result = await db.assignments.update_many(
            {},  # Match all assignment documents
            {"$pull": {"tasks": {"taskId": {"$in": task_ids}}}}
        )
        print(f"✅ Removed tasks from {result.modified_count} user assignments")
    
    # Step 3: Delete all tasks in this project
    if task_ids:
        delete_result = await db.tasks.delete_many({"project_id": project_id})
        print(f"✅ Deleted {delete_result.deleted_count} tasks")
    
    # Step 4: Delete the project itself
    await db.projects.delete_one({"_id": ObjectId(project_id)})
    print(f"✅ Deleted project {project_id}")
    
    return {
        "status": "success",
        "message": f"Successfully deleted project and associated data",
        "projectId": project_id,
        "tasksDeleted": len(task_ids),
        "assignmentsUpdated": result.modified_count if task_ids else 0
    }