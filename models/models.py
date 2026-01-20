"""
High-Level Overview of models.py
This file defines the core data models for a project-based learning and goal-tracking system.
It is built using Pydantic and is designed to work well with a MongoDB-style backend.
Key Concepts Covered:
Overall, this file serves as the single source of truth for the platform’s data contracts,
ensuring consistency across project management, learning workflows, and user progress tracking.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime
from bson import ObjectId


class Project(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    projectType: Literal["project", "training"] = "project"
    status: str = "active"
    createdBy: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)

class Comment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    comment: str
    commentBy: Literal["user", "admin"]
    createdAt: datetime = Field(default_factory=datetime.now)

class Task(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    project_id: str
    title: str
    description: Optional[str] = None
    estimatedTime: float
    skillType: str
    createdBy: Optional[str] = None  # Added field
    updatedAt: Optional[datetime] = None

class TaskAssignment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    taskId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None
    taskStatus: Literal["pending", "active", "completed"] = "pending"
    expectedCompletionDate: Optional[str] = None
    completionDate: Optional[str] = None
    comments: List[Comment] = Field(default_factory=list)

class Assignment(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    userId: str
    tasks: List[TaskAssignment] = Field(default_factory=list)

class TaskResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    taskId: str
    name: str
    description: Optional[str] = None
    estimatedTime: float
    skillType: str
    projectId: str
    projectName: str
    assignedBy: Literal["user", "admin"]
    sequenceId: Optional[int] = None
    taskStatus: Literal["pending", "active", "completed"]
    expectedCompletionDate: Optional[str] = None
    completionDate: Optional[str] = None
    comments: List[Comment] = Field(default_factory=list)

class ProjectWithTasks(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    projectType: Literal["project", "training"] = "project"
    status: str = "active"
    created_at: datetime
    tasks: List[Task] = Field(default_factory=list)

class BulkTaskItem(BaseModel):
    title: str
    description: Optional[str] = None
    estimatedTime: float
    skillType: str

class BulkLoadTasksRequest(BaseModel):
    projectId: str
    tasks: List[BulkTaskItem]

class Chat(BaseModel):
    id: Optional[str] = None
    userId: str
    userType: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)

class Goal(BaseModel):
    userId: str
    goals: str

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    estimatedTime: Optional[float] = None
    skillType: Optional[str] = None
    priority: Optional[str] = None

class UserTaskLink(BaseModel):
    userId: str
    taskId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None
    expectedCompletionDate: Optional[str] = None

class Resource(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    link: str
    category: str = "General"
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)

class ResourceAssignment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resourceId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None
    isCompleted: bool = False
    comments: List[Comment] = Field(default_factory=list)

class ResourceAssignmentCollection(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    userId: str
    resources: List[ResourceAssignment] = Field(default_factory=list)

class ResourceResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resourceId: str
    name: str
    description: Optional[str] = None
    link: str
    category: str
    tags: List[str] = Field(default_factory=list)
    assignedBy: Literal["user", "admin"]
    sequenceId: Optional[int] = None
    isCompleted: bool
    comments: List[Comment] = Field(default_factory=list)

class ResourceUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    name: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None

class UserResourceLink(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    userId: str
    resourceId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None

class TaskWithAssignment(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    project_id: str
    title: str
    description: Optional[str] = None
    estimatedTime: float
    skillType: str
    isAssigned: bool = False

class GetProjectTasksRequest(BaseModel):
    projectId: str
    userId: str

class ProjectWithTasksAndAssignment(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    projectType: Literal["project", "training"] = "project"
    status: str = "active"
    created_at: datetime
    tasks: List[TaskWithAssignment] = Field(default_factory=list)python# projects.py - Update get_project_details endpoint
# Only showing the updated endpoint - rest remains the same

@router.get("/{project_id}", response_model=ProjectWithTasks)
async def get_project_details(request: Request, project_id: str, userId: Optional[str] = None):
    """
    Get project details along with all associated tasks.
    Returns tasks created by admin or the specified userId.
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
            {"createdBy": userId}
        ]
    
    tasks_cursor = db.tasks.find(task_query)
    tasks = [serialize(task) async for task in tasks_cursor]
    
    project_with_tasks = {
        **project_data,
        "tasks": tasks
    }
    
    return project_with_tasks


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
            {"createdBy": req.userId}
        ]
    }
    tasks_cursor = db.tasks.find(task_query)
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