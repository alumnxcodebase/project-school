from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal
from datetime import datetime
from bson import ObjectId

class Project(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.now)

class Comment(BaseModel):
    """Model for task comments"""
    model_config = ConfigDict(populate_by_name=True)
    comment: str
    commentBy: Literal["user", "admin"]
    createdAt: datetime = Field(default_factory=datetime.now)

class Task(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    project_id: str
    title: str
    description: Optional[str] = None
    status: str = "pending"

class TaskAssignment(BaseModel):
    """Individual task assignment details"""
    model_config = ConfigDict(populate_by_name=True)
    taskId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None
    isCompleted: bool = False
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
    projectId: str
    projectName: str
    assignedBy: Literal["user", "admin"]
    sequenceId: Optional[int] = None
    isCompleted: bool
    comments: List[Comment] = Field(default_factory=list)

class ProjectWithTasks(BaseModel):
    """Response model for project details with associated tasks"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    status: str = "active"
    created_at: datetime
    tasks: List[Task] = Field(default_factory=list)

class Chat(BaseModel):
    id: Optional[str] = None
    userId: str
    userType: str  # "user" or "agent"
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)

class Goal(BaseModel):
    userId: str
    goals: List[str]

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None

class UserTaskLink(BaseModel):
    userId: str
    taskId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None