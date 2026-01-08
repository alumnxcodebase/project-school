from fastapi import APIRouter, Request, Body, HTTPException
from models import Project, ProjectWithTasks, Task, ProjectWithRelevantTasks, TaskInfo
from utils.helpers import serialize, is_task_relevant_to_project
from bson import ObjectId
from typing import List

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


@router.get("/with-relevant-tasks", response_model=List[ProjectWithRelevantTasks])
async def get_projects_with_relevant_tasks(request: Request):
    """
    Get all projects with tasks filtered by LLM relevance.
    Only tasks whose titles are relevant to the project description are included.
    Results are cached to improve performance.
    """
    db = request.app.state.db
    
    # Fetch all projects
    projects_cursor = db.projects.find()
    projects = [serialize(doc) async for doc in projects_cursor]
    
    # Fetch all tasks
    tasks_cursor = db.tasks.find({})
    all_tasks = [serialize(doc) async for doc in tasks_cursor]
    
    result = []
    
    # Process each project
    for project in projects:
        project_id = project.get("id")
        project_description = project.get("description", "") or ""
        
        # Find tasks for this project
        project_tasks = [task for task in all_tasks if task.get("project_id") == project_id]
        
        relevant_tasks = []
        
        # Check relevance for each task
        for task in project_tasks:
            task_id = task.get("id")
            task_title = task.get("title", "")
            
            # Check if task is relevant using LLM (with caching)
            is_relevant = await is_task_relevant_to_project(
                project_description=project_description,
                task_title=task_title,
                project_id=project_id,
                task_id=task_id
            )
            
            if is_relevant:
                relevant_tasks.append(TaskInfo(
                    taskId=task_id,
                    taskName=task_title
                ))
        
        # Add project with relevant tasks to result
        result.append(ProjectWithRelevantTasks(
            projectId=project_id,
            tasks=relevant_tasks
        ))
    
    print(f"📊 Returned {len(result)} projects with relevant tasks")
    return result


@router.get("/{project_id}", response_model=ProjectWithTasks)
async def get_project_details(request: Request, project_id: str):
    """
    Get project details along with all associated tasks.
    
    Returns:
        - Project information (id, name, description, status, created_at)
        - List of all tasks belonging to this project
    """
    db = request.app.state.db
    
    # Validate project_id format
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid Project ID")

    # Fetch project details
    project = await db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Serialize project (convert _id to id)
    project_data = serialize(project)
    
    # Fetch all tasks for this project
    tasks_cursor = db.tasks.find({"project_id": project_id})
    tasks = [serialize(task) async for task in tasks_cursor]
    
    # Combine project data with tasks
    project_with_tasks = {
        **project_data,
        "tasks": tasks
    }
    
    print(f"📦 Retrieved project {project_id} with {len(tasks)} tasks")
    
    return project_with_tasks


@router.get("/{project_id}/stats")
async def get_project_stats(request: Request, project_id: str):
    """Get statistics about tasks in a project"""
    db = request.app.state.db
    tasks = await db.tasks.find({"project_id": project_id}).to_list(length=100)
    return {
        "total_tasks": len(tasks),
        "completed": len([t for t in tasks if t["status"] == "completed"]),
        "pending": len([t for t in tasks if t["status"] == "pending"]),
        "in_progress": len([t for t in tasks if t["status"] == "in_progress"])
    }