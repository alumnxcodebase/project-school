from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from langgraph.graph import StateGraph
from typing_extensions import TypedDict

# =========================================================
# ENV + DB
# =========================================================

load_dotenv()

MONGODB_URL = os.getenv(
    "MONGODB_URL",
    "mongodb+srv://agriculture_admin:<db_password>@agriculture.ayck7vs.mongodb.net/?appName=Agriculture"
)
DATABASE_NAME = os.getenv("DATABASE_NAME", "projects")

client = None
db = None

# =========================================================
# LIFESPAN
# =========================================================

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
    await db.goals.create_index("userId")
    await db.ai_agents.create_index("userId")

    print(f"✅ MongoDB connected: {DATABASE_NAME}")
    yield
    client.close()
    print("❌ MongoDB disconnected")

# =========================================================
# APP
# =========================================================

app = FastAPI(
    title="Project + Agentic AI API",
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

# =========================================================
# MODELS
# =========================================================

class Project(BaseModel):
    model_config = ConfigDict(json_encoders={ObjectId: str})
    id: Optional[str] = None
    name: str
    description: Optional[str] = None
    status: str = "active"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class ProjectUpdate(BaseModel):
    name: Optional[str]
    description: Optional[str]
    status: Optional[str]

class Task(BaseModel):
    model_config = ConfigDict(json_encoders={ObjectId: str})
    id: Optional[str] = None
    project_id: str
    title: str
    description: Optional[str]
    status: str = "pending"
    priority: str = "medium"
    assigned_to: Optional[str]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class TaskUpdate(BaseModel):
    title: Optional[str]
    description: Optional[str]
    status: Optional[str]
    priority: Optional[str]
    assigned_to: Optional[str]

class Chat(BaseModel):
    id: Optional[str] = None
    userId: str
    userType: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.now)

class Goal(BaseModel):
    id: Optional[str] = None
    userId: str
    goals: List[str]
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class AIAgent(BaseModel):
    id: Optional[str] = None
    userId: str
    name: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

# =========================================================
# HELPERS
# =========================================================

def serialize(doc):
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    return doc

# =========================================================
# AGENT STATE + LOGIC
# =========================================================

class AgentState(TypedDict):
    userId: str
    goals: List[str]
    has_history: bool
    active_task: Optional[dict]
    active_project: Optional[dict]
    response_text: str

async def analyze_state(state: AgentState):
    user_id = state["userId"]

    goals_doc = await db.goals.find_one({"userId": user_id})
    goals = goals_doc["goals"] if goals_doc else []

    history_count = await db.chats.count_documents({"userId": user_id})
    task = await db.tasks.find_one({"assigned_to": user_id, "status": {"$ne": "completed"}})

    return {
        "goals": goals,
        "has_history": history_count > 0,
        "active_task": task,
        "active_project": None
    }

def router(state: AgentState):
    if not state["goals"]:
        return "ask_goals"
    if state["active_task"]:
        return "query_task"
    return "general_chat"

workflow = StateGraph(AgentState)
workflow.add_node("analyze", analyze_state)
workflow.add_node("ask_goals", lambda _: {"response_text": "What are your learning goals?"})
workflow.add_node("query_task", lambda s: {
    "response_text": f"How is your task '{s['active_task']['title']}' going?"
})
workflow.add_node("general_chat", lambda _: {
    "response_text": "How can I help you today?"
})

workflow.set_entry_point("analyze")
workflow.add_conditional_edges("analyze", router)
agent = workflow.compile()

# =========================================================
# HEALTH
# =========================================================

@app.get("/")
async def root():
    return {"message": "Unified Project + Agentic AI API"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

# =========================================================
# PROJECTS
# =========================================================

@app.post("/project", response_model=Project, status_code=201)
async def create_project(project: Project):
    res = await db.projects.insert_one(project.dict(exclude={"id"}))
    return serialize(await db.projects.find_one({"_id": res.inserted_id}))

@app.get("/project", response_model=List[Project])
async def get_projects():
    return [serialize(p) async for p in db.projects.find()]

# =========================================================
# TASKS
# =========================================================

@app.post("/project-tasks", response_model=Task, status_code=201)
async def create_task(task: Task):
    res = await db.tasks.insert_one(task.dict(exclude={"id"}))
    return serialize(await db.tasks.find_one({"_id": res.inserted_id}))

# =========================================================
# GOALS
# =========================================================

@app.post("/goals", response_model=Goal, status_code=201)
async def create_goals(goal: Goal):
    res = await db.goals.insert_one(goal.dict(exclude={"id"}))
    return serialize(await db.goals.find_one({"_id": res.inserted_id}))

@app.get("/goals", response_model=List[Goal])
async def get_goals(userId: Optional[str] = None):
    q = {"userId": userId} if userId else {}
    return [serialize(g) async for g in db.goals.find(q)]

# =========================================================
# AI AGENT REGISTRY
# =========================================================

@app.post("/ai-agent", response_model=AIAgent, status_code=201)
async def create_ai_agent(agent: AIAgent):
    res = await db.ai_agents.insert_one(agent.dict(exclude={"id"}))
    return serialize(await db.ai_agents.find_one({"_id": res.inserted_id}))

@app.get("/ai-agent", response_model=List[AIAgent])
async def get_ai_agents(userId: Optional[str] = None):
    q = {"userId": userId} if userId else {}
    return [serialize(a) async for a in db.ai_agents.find(q)]

# =========================================================
# CHAT
# =========================================================

@app.post("/chat", response_model=Chat, status_code=201)
async def post_chat(chat: Chat):
    res = await db.chats.insert_one(chat.dict(exclude={"id"}))
    return serialize(await db.chats.find_one({"_id": res.inserted_id}))

@app.get("/chat/{user_id}", response_model=List[Chat])
async def get_chat(user_id: str):
    return [
        serialize(c)
        async for c in db.chats.find({"userId": user_id}).sort("timestamp", 1)
    ]

# =========================================================
# AGENT CHAT
# =========================================================

@app.post("/chat/agent", response_model=Chat, status_code=201)
async def chat_agent(chat: Chat = Body(...)):
    state = {"userId": chat.userId}
    result = await agent.ainvoke(state)

    await db.chats.insert_one(chat.dict(exclude={"id"}))
    agent_msg = {
        "userId": chat.userId,
        "userType": "agent",
        "message": result["response_text"],
        "timestamp": datetime.now()
    }
    res = await db.chats.insert_one(agent_msg)
    return serialize(await db.chats.find_one({"_id": res.inserted_id}))

# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
