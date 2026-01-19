# models.py
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
    created_at: datetime = Field(default_factory=datetime.now)

class Comment(BaseModel):
    """Model for task and resource comments"""
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
    updatedAt: Optional[datetime] = None

class TaskAssignment(BaseModel):
    """Individual task assignment details"""
    model_config = ConfigDict(populate_by_name=True)
    taskId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None
    taskStatus: Literal["pending", "active", "completed"] = "pending"  # Changed from isCompleted
    expectedCompletionDate: Optional[str] = None
    completionDate: Optional[str] = None
    comments: List[Comment] = Field(default_factory=list)

class Assignment(BaseModel):
    """User assignments collection - stores all tasks assigned to a user"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    userId: str
    tasks: List[TaskAssignment] = Field(default_factory=list)

class TaskResponse(BaseModel):
    """Response model for user tasks with project details"""
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
    taskStatus: Literal["pending", "active", "completed"]  # Changed from isCompleted
    expectedCompletionDate: Optional[str] = None
    completionDate: Optional[str] = None
    comments: List[Comment] = Field(default_factory=list)

class ProjectWithTasks(BaseModel):
    """Response model for project details with associated tasks"""
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
    userType: str  # "user" or "agent"
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

# ============================================
# Resource Models
# ============================================

class Resource(BaseModel):
    """Model for learning resources (videos, docs, tutorials)"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    link: str
    category: str = "General"
    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)

class ResourceAssignment(BaseModel):
    """Individual resource assignment details"""
    model_config = ConfigDict(populate_by_name=True)
    resourceId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None
    isCompleted: bool = False
    comments: List[Comment] = Field(default_factory=list)

class ResourceAssignmentCollection(BaseModel):
    """User resource assignments collection - stores all resources assigned to a user"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    userId: str
    resources: List[ResourceAssignment] = Field(default_factory=list)

class ResourceResponse(BaseModel):
    """Response model for user resources with full details"""
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
    """Model for updating resource fields"""
    model_config = ConfigDict(populate_by_name=True)
    name: Optional[str] = None
    description: Optional[str] = None
    link: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None

class UserResourceLink(BaseModel):
    """Model for linking a resource to a user"""
    model_config = ConfigDict(populate_by_name=True)
    userId: str
    resourceId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None

class TaskWithAssignment(BaseModel):
    """Task model with assignment status"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    project_id: str
    title: str
    description: Optional[str] = None
    estimatedTime: float
    skillType: str
    isAssigned: bool = False

class GetProjectTasksRequest(BaseModel):
    """Request model for getting project tasks with assignment status"""
    projectId: str
    userId: str

class ProjectWithTasksAndAssignment(BaseModel):
    """Response model for project details with tasks and their assignment status"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    projectType: Literal["project", "training"] = "project"
    status: str = "active"
    created_at: datetime
    tasks: List[TaskWithAssignment] = Field(default_factory=list)