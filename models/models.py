from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from bson import ObjectId

class Project(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.now)

class Task(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    project_id: str
    title: str
    description: Optional[str] = None
    status: str = "pending"
    assigned_to: Optional[str] = None

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
    assigned_to: Optional[str] = None

class UserTaskLink(BaseModel):
    userId: str
    taskId: str  # objectId