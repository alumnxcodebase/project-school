"""
High-Level Overview of models.py
This file defines the core data models for a project-based learning and goal-tracking system.
It is built using Pydantic and is designed to work well with a MongoDB-style backend.
Key Concepts Covered:
Overall, this file serves as the single source of truth for the platform's data contracts,
ensuring consistency across project management, learning workflows, and user progress tracking.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Literal, Dict, Any
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
    """Model for task and resource comments"""
    model_config = ConfigDict(populate_by_name=True)
    comment: str
    commentBy: Literal["user", "admin"]
    createdAt: datetime = Field(default_factory=datetime.now)

# Update models.py - Task model

class Task(BaseModel):
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    project_id: str
    title: str
    description: Optional[str] = None
    estimatedTime: float
    skillType: str
    day: Optional[str] = None
    taskType: Optional[Literal["Theory", "Practical"]] = None
    createdBy: Optional[str] = None
    updatedAt: Optional[datetime] = None
    isEnabled: bool = False
    isValidation: bool = False
    autoAssign: bool = True  # Defaults to True for backward compatibility

class TaskAssignment(BaseModel):
    """Individual task assignment details"""
    model_config = ConfigDict(populate_by_name=True)
    taskId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None
    taskStatus: Literal["pending", "active", "completed"] = "pending"
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
    taskStatus: Literal["pending", "active", "completed"]
    expectedCompletionDate: Optional[str] = None
    completionDate: Optional[str] = None
    comments: List[Comment] = Field(default_factory=list)
    createdBy: Optional[str] = None
    isEnabled: bool = False
    isValidation: bool = False
    day: Optional[str] = None
    taskType: Optional[Literal["Theory", "Practical"]] = None

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
    isEnabled: bool = False
    isValidation: bool = False
    day: Optional[str] = None
    taskType: Optional[Literal["Theory", "Practical"]] = None

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

class UserPreferences(BaseModel):
    """Model for user skill preferences"""
    userId: str
    preferences: List[str]  # e.g., ["Frontend", "AI"] or ["All"]
    updated_at: datetime = Field(default_factory=datetime.now)

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    estimatedTime: Optional[float] = None
    skillType: Optional[str] = None
    priority: Optional[str] = None
    isEnabled: Optional[bool] = None
    isValidation: Optional[bool] = None
    day: Optional[str] = None
    taskType: Optional[Literal["Theory", "Practical"]] = None

class UserTaskLink(BaseModel):
    userId: str
    taskId: str
    assignedBy: Literal["user", "admin"] = "admin"
    sequenceId: Optional[int] = None
    expectedCompletionDate: Optional[str] = None

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
    day: Optional[str] = None
    taskType: Optional[Literal["Theory", "Practical"]] = None
    isAssigned: bool = False
    isEnabled: bool = False
    isValidation: bool = False

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

class TaskWithStatus(BaseModel):
    """Task model with assignment status"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    project_id: str
    title: str
    description: Optional[str] = None
    estimatedTime: float
    skillType: str
    day: Optional[str] = None
    taskType: Optional[Literal["Theory", "Practical"]] = None
    createdBy: Optional[str] = None
    updatedAt: Optional[datetime] = None
    taskStatus: Optional[Literal["pending", "active", "completed"]] = None
    isAssigned: bool = False
    isEnabled: bool = False
    isValidation: bool = False

class ProjectWithTasksAndStatus(BaseModel):
    """Response model for project details with tasks and their status"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    projectType: Literal["project", "training"] = "project"
    status: str = "active"
    created_at: datetime
    tasks: List[TaskWithStatus] = Field(default_factory=list)

class Notice(BaseModel):
    """Model for noticeboard messages"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    title: str
    content: str
    createdAt: datetime = Field(default_factory=datetime.now)
    createdBy: str = "admin"

class QuizQuestion(BaseModel):
    """Model for a single quiz question"""
    question: str
    options: List[str]
    correctAnswer: str
    explanation: str

class Quiz(BaseModel):
    """Model for a task quiz containing multiple questions"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    taskId: str
    questions: List[QuizQuestion]

class Achievement(BaseModel):
    id: str
    name: str
    icon: str
    unlockedAt: datetime = Field(default_factory=datetime.now)

class UserStats(BaseModel):
    """Model for user gamification stats (XP, Streak, Level)"""
    model_config = ConfigDict(populate_by_name=True, json_encoders={ObjectId: str})
    id: Optional[str] = None
    userId: str
    totalXP: int = 0
    level: int = 1
    currentStreak: int = 0
    lastActivityDate: Optional[datetime] = None
    achievements: List[Achievement] = Field(default_factory=list)

class DashboardStatsResponse(BaseModel):
    """Aggregated response for dashboard stats"""
    stats: Dict[str, Any]
    gamification: Dict[str, Any]
    skills: List[Dict[str, Any]]
