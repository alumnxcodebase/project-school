from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager

load_dotenv()

MONGODB_URL = os.getenv(
    "MONGODB_URL",
    "mongodb+srv://agriculture_admin:<db_password>@agriculture.ayck7vs.mongodb.net/?appName=Agriculture"
)
DATABASE_NAME = os.getenv("DATABASE_NAME", "projects")

client = None
db = None

# ==================== LIFESPAN ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db
    client = AsyncIOMotorClient(MONGODB_URL)
    db = client[DATABASE_NAME]
    await client.server_info()

    await db.projects.create_index("name")
    await db.projects.create_index("status")
    await db.tasks.create_index("project_id")
    await db.chats.create_index([("userId", 1), ("timestamp", 1)])

    print(f"✅ Connected to MongoDB: {DATABASE_NAME}")
    yield
    client.close()
    print("❌ MongoDB disconnected")

# ==================== APP ====================

app = FastAPI(
    title="Project + AI Agent Management API",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== MODELS ====================

class Project(BaseModel):
    model_config = ConfigDict(json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    status: str = "active"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class Task(BaseModel):
    model_config = ConfigDict(json_encoders={ObjectId: str})
    id: Optional[str] = None
    project_id: str
    title: str
    description: Optional[str] = None
    status: str = "pending"
    priority: str = "medium"
    assigned_to: Optional[str] = None
    due_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class Goal(BaseModel):
    id: Optional[str] = None
    userId: str
    goals: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class GoalUpdate(BaseModel):
    userId: Optional[str] = None
    goals: Optional[str] = None

class AIAgent(BaseModel):
    id: Optional[str] = None
    userId: str
    name: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class AIAgentUpdate(BaseModel):
    userId: Optional[str] = None
    name: Optional[str] = None

class Chat(BaseModel):
    id: Optional[str] = None
    userId: str
    userType: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)

# ==================== HELPERS ====================

def to_id(doc):
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    return doc

# ==================== HEALTH ====================

@app.get("/")
async def root():
    return {"message": "Unified Project + AI Agent API"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

# ==================== PROJECTS ====================

@app.post("/project", response_model=Project, status_code=201)
async def create_project(project: Project):
    res = await db.projects.insert_one(project.dict(exclude={"id"}))
    return to_id(await db.projects.find_one({"_id": res.inserted_id}))

@app.get("/project", response_model=List[Project])
async def get_projects():
    return [to_id(p) async for p in db.projects.find()]

# ==================== TASKS ====================

@app.post("/project-tasks", response_model=Task, status_code=201)
async def create_task(task: Task):
    res = await db.tasks.insert_one(task.dict(exclude={"id"}))
    return to_id(await db.tasks.find_one({"_id": res.inserted_id}))

# ==================== GOALS ====================

@app.post("/goals", response_model=Goal, status_code=201)
async def create_goal(goal: Goal):
    res = await db.goals.insert_one(goal.dict(exclude={"id"}))
    return to_id(await db.goals.find_one({"_id": res.inserted_id}))

@app.get("/goals", response_model=List[Goal])
async def get_goals(userId: Optional[str] = None):
    q = {"userId": userId} if userId else {}
    return [to_id(g) async for g in db.goals.find(q)]

# ==================== AI AGENTS ====================

@app.post("/ai-agent", response_model=AIAgent, status_code=201)
async def create_ai_agent(agent: AIAgent):
    res = await db.ai_agents.insert_one(agent.dict(exclude={"id"}))
    return to_id(await db.ai_agents.find_one({"_id": res.inserted_id}))

@app.get("/ai-agent", response_model=List[AIAgent])
async def get_ai_agents(userId: Optional[str] = None):
    q = {"userId": userId} if userId else {}
    return [to_id(a) async for a in db.ai_agents.find(q)]

# ==================== CHAT ====================

@app.post("/chat", response_model=Chat, status_code=201)
async def post_chat(chat: Chat):
    res = await db.chats.insert_one(chat.dict(exclude={"id"}))
    return to_id(await db.chats.find_one({"_id": res.inserted_id}))

@app.get("/chat/{user_id}", response_model=List[Chat])
async def get_chat(user_id: str):
    return [to_id(c) async for c in db.chats.find({"userId": user_id}).sort("timestamp", 1)]

# ==================== RUN ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
