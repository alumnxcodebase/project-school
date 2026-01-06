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
from langgraph.graph import StateGraph, END
from typing_extensions import TypedDict
from fastapi import Body

load_dotenv()

MONGODB_URL = os.getenv("MONGODB_URL", "mongodb+srv://agriculture_admin:<db_password>@agriculture.ayck7vs.mongodb.net/?appName=Agriculture")
DATABASE_NAME = os.getenv("DATABASE_NAME", "projects")

client = None
db = None

# Lifespan context manager (replaces on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    global client, db
    # Startup
    try:
        client = AsyncIOMotorClient(MONGODB_URL)
        db = client[DATABASE_NAME]
        await client.server_info()
        print(f"Connected to MongoDB: {DATABASE_NAME}")
        await db.projects.create_index("name")
        await db.projects.create_index("status")
        await db.tasks.create_index("project_id")
        await db.chats.create_index("timestamp")
        await db.chats.create_index([("userId", 1), ("timestamp", 1)])
        print("Indexes created")
    except Exception as e:
        print(f"Error: {e}")
        raise
    
    yield  # Application runs here
    
    # Shutdown
    if client:
        client.close()
        print("Disconnected from MongoDB")

# Initialize FastAPI with lifespan
app = FastAPI(title="Project Management API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Updated Pydantic models with ConfigDict
class Project(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={ObjectId: str},
        json_schema_extra={"examples": [{"name": "Example Project", "description": "Test"}]}
    )
    
    id: Optional[str] = Field(default=None)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    status: str = Field(default="active")
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class Task(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={ObjectId: str}
    )
    
    id: Optional[str] = Field(default=None)
    project_id: str
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    status: str = Field(default="pending")
    priority: str = Field(default="medium")
    assigned_to: Optional[str] = None
    due_date: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[datetime] = None

"""chat class"""

class ChatUpdate(BaseModel):
    message: Optional[str] = None
    model_config = ConfigDict(
        populate_by_name=True,
        json_encoders={ObjectId: str}
    )

    id: Optional[str] = Field(default=None)
    userId: str = Field(..., min_length=1)
    userType: str = Field(..., pattern="^(user|agent)$")  # Restricts to user or agent
    timestamp: datetime = Field(default_factory=datetime.now)


"""class for user profile"""

class UserProfile(BaseModel):
    userId: str
    goals: List[str] = []
    current_project_id: Optional[str] = None


"""This class represents the internal state of agent during a single turn"""

class AgentState(TypedDict):
    userId: str
    message: str
    goals: List[str]
    has_history: bool
    active_task: Optional[dict]
    active_project: Optional[dict]
    response_text: str


def project_helper(project) -> dict:
    """Convert MongoDB project document to API response format"""
    return {
        "id": str(project["_id"]),
        "_id": str(project["_id"]),
        "name": project["name"],
        "description": project.get("description"),
        "status": project.get("status", "active"),
        "start_date": project.get("start_date"),
        "end_date": project.get("end_date"),
        "created_at": project.get("created_at"),
        "updated_at": project.get("updated_at")
    }

def task_helper(task) -> dict:
    """Convert MongoDB task document to API response format"""
    return {
        "id": str(task["_id"]),
        "_id": str(task["_id"]),
        "project_id": task["project_id"],
        "title": task["title"],
        "description": task.get("description"),
        "status": task.get("status", "pending"),
        "priority": task.get("priority", "medium"),
        "assigned_to": task.get("assigned_to"),
        "due_date": task.get("due_date"),
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at")
    }

def chat_helper(chat) -> dict:
    return {
        "id": str(chat["_id"]),
        "userId": chat["userId"],
        "userType": chat["userType"],
        "message": chat["message"],
        "timestamp": chat.get("timestamp")
    }



""" --- AGENT NODES ---"""

async def analyze_user_state(state: AgentState):
    """Entry node: Gathers data from MongoDB to decide next steps."""
    user_id = state["userId"]

    # 1. Check Profile Goals
    profile = await db.profiles.find_one({"userId": user_id})
    goals = profile.get("goals", []) if profile else []

    # 2. Check Chat History
    history_count = await db.chats.count_documents({"userId": user_id})

    # 3. Check for Active Tasks
    task = await db.tasks.find_one({"assigned_to": user_id, "status": {"$ne": "completed"}})

    # 4. Check for Active Project
    project = None
    if profile and profile.get("current_project_id"):
        project = await db.projects.find_one({"_id": ObjectId(profile["current_project_id"])})

    return {
        "goals": goals,
        "has_history": history_count > 0,
        "active_task": task,
        "active_project": project
    }


def router_logic(state: AgentState):
    """The decision engine."""
    if not state["goals"] or not state["has_history"]:
        return "ask_goals"
    if state["active_task"]:
        return "query_task"
    if not state["active_project"]:
        return "assign_new_project"
    return "general_chat"


# --- GRAPH DEFINITION ---

workflow = StateGraph(AgentState)

workflow.add_node("analyze", analyze_user_state)

# Nodes for different responses
workflow.add_node("ask_goals",
                  lambda x: {"response_text": "Welcome! I don't see any goals yet. What would you like to learn?"})
workflow.add_node("query_task", lambda x: {
    "response_text": f"How is your task '{x['active_task']['title']}' coming along? Is it completed?"})
workflow.add_node("assign_new_project", lambda x: {
    "response_text": "You're all caught up! I'm assigning a new project from our pool based on your goals."})
workflow.add_node("general_chat",
                  lambda x: {"response_text": "Welcome back! What's on your mind today regarding your studies?"})

workflow.set_entry_point("analyze")
workflow.add_conditional_edges("analyze", router_logic)

# Compile the graph
agent_executor = workflow.compile()



@app.get("/")
async def root():
    return {"message": "Project API with MongoDB", "version": "2.0.0"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "database": "connected"}

@app.post("/project", response_model=Project, status_code=201)
async def create_project(project: Project):
    project_dict = project.model_dump(by_alias=True, exclude={"id"})
    project_dict["created_at"] = datetime.now()
    project_dict["updated_at"] = datetime.now()
    result = await db.projects.insert_one(project_dict)
    created = await db.projects.find_one({"_id": result.inserted_id})
    return project_helper(created)

@app.get("/project", response_model=List[Project])
async def get_all_projects():
    projects = []
    cursor = db.projects.find({}).sort("created_at", -1)
    async for project in cursor:
        projects.append(project_helper(project))
    return projects

@app.get("/project/{project_id}", response_model=Project)
async def get_project(project_id: str):
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid ID")
    project = await db.projects.find_one({"_id": ObjectId(project_id)})
    if not project:
        raise HTTPException(status_code=404, detail="Not found")
    return project_helper(project)

@app.put("/project/{project_id}", response_model=Project)
async def update_project(project_id: str, update: ProjectUpdate):
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid ID")
    data = {k: v for k, v in update.model_dump(exclude_unset=True).items() if v is not None}
    if data:
        data["updated_at"] = datetime.now()
        await db.projects.update_one({"_id": ObjectId(project_id)}, {"$set": data})
    updated = await db.projects.find_one({"_id": ObjectId(project_id)})
    if not updated:
        raise HTTPException(status_code=404, detail="Not found")
    return project_helper(updated)

@app.delete("/project/{project_id}", status_code=204)
async def delete_project(project_id: str):
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid ID")
    await db.tasks.delete_many({"project_id": project_id})
    result = await db.projects.delete_one({"_id": ObjectId(project_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")

@app.post("/project-tasks", response_model=Task, status_code=201)
async def create_task(task: Task):
    if not ObjectId.is_valid(task.project_id):
        raise HTTPException(status_code=400, detail="Invalid project ID")
    task_dict = task.model_dump(by_alias=True, exclude={"id"})
    task_dict["created_at"] = datetime.now()
    task_dict["updated_at"] = datetime.now()
    result = await db.tasks.insert_one(task_dict)
    created = await db.tasks.find_one({"_id": result.inserted_id})
    return task_helper(created)

@app.get("/project-tasks", response_model=List[Task])
async def get_all_tasks(project_id: Optional[str] = None):
    query = {"project_id": project_id} if project_id else {}
    tasks = []
    cursor = db.tasks.find(query).sort("created_at", -1)
    async for task in cursor:
        tasks.append(task_helper(task))
    return tasks

@app.get("/project-tasks/{task_id}", response_model=Task)
async def get_task(task_id: str):
    if not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=400, detail="Invalid ID")
    task = await db.tasks.find_one({"_id": ObjectId(task_id)})
    if not task:
        raise HTTPException(status_code=404, detail="Not found")
    return task_helper(task)

@app.put("/project-tasks/{task_id}", response_model=Task)
async def update_task(task_id: str, update: TaskUpdate):
    if not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=400, detail="Invalid ID")
    data = {k: v for k, v in update.model_dump(exclude_unset=True).items() if v is not None}
    if data:
        data["updated_at"] = datetime.now()
        await db.tasks.update_one({"_id": ObjectId(task_id)}, {"$set": data})
    updated = await db.tasks.find_one({"_id": ObjectId(task_id)})
    if not updated:
        raise HTTPException(status_code=404, detail="Not found")
    return task_helper(updated)

@app.delete("/project-tasks/{task_id}", status_code=204)
async def delete_task(task_id: str):
    if not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=400, detail="Invalid ID")
    result = await db.tasks.delete_one({"_id": ObjectId(task_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")

@app.get("/project/{project_id}/stats")
async def get_project_stats(project_id: str):
    if not ObjectId.is_valid(project_id):
        raise HTTPException(status_code=400, detail="Invalid ID")
    tasks = []
    cursor = db.tasks.find({"project_id": project_id})
    async for task in cursor:
        tasks.append(task)
    return {
        "total_tasks": len(tasks),
        "pending": len([t for t in tasks if t.get("status") == "pending"]),
        "in_progress": len([t for t in tasks if t.get("status") == "in_progress"]),
        "completed": len([t for t in tasks if t.get("status") == "completed"]),
        "blocked": len([t for t in tasks if t.get("status") == "blocked"])
    }


"""post method for chat to post messages in the chat"""
@app.post("/chat", response_model=ChatUpdate, status_code=201)
async def store_chat_message(chat: ChatUpdate):
    chat_dict = chat.model_dump(by_alias=True, exclude={"id"})
    # Ensure timestamp is set at the moment of insertion
    chat_dict["timestamp"] = datetime.now()

    result = await db.chats.insert_one(chat_dict)
    created = await db.chats.find_one({"_id": result.inserted_id})
    return chat_helper(created)


"""get method for chat to get the chat based upon the user id"""
@app.get("/chat/{user_id}", response_model=List[ChatUpdate])
async def get_conversation_history(user_id: str):
    chats = []
    # Sort by timestamp so the conversation reads in order
    cursor = db.chats.find({"userId": user_id}).sort("timestamp", 1)
    async for chat in cursor:
        chats.append(chat_helper(chat))

    if not chats:
        return []
    return chats

"""delete method for chat to delete the chat based upon the message id"""
@app.delete("/chat/{message_id}", status_code=204)
async def delete_chat_message(message_id: str):
    if not ObjectId.is_valid(message_id):
        raise HTTPException(status_code=400, detail="Invalid message ID")

    result = await db.chats.delete_one({"_id": ObjectId(message_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Message not found")


"""put method for chat to update the chat based upon the message id"""
@app.put("/chat/{message_id}", response_model=ChatUpdate)
async def update_chat_message(message_id: str, update: ChatUpdate):
    if not ObjectId.is_valid(message_id):
        raise HTTPException(status_code=400, detail="Invalid message ID")

    data = {k: v for k, v in update.model_dump(exclude_unset=True).items() if v is not None}
    if data:
        await db.chats.update_one({"_id": ObjectId(message_id)}, {"$set": data})

    updated = await db.chats.find_one({"_id": ObjectId(message_id)})
    if not updated:
        raise HTTPException(status_code=404, detail="Message not found")
    return chat_helper(updated)

"""end points for agent chat with user"""
@app.post("/chat/agent", response_model=ChatUpdate, status_code=201)
async def chat_with_agent(chat_req: ChatUpdate = Body(...)):
    user_id = chat_req.userId
    user_message = chat_req.message

    # 1. PRE-PROCESSING: Fetch Context from MongoDB
    # Check Profile for Goals
    profile = await db.profiles.find_one({"userId": user_id})
    user_goals = profile.get("goals", []) if profile else []

    # Check History
    history = await db.chats.find({"userId": user_id}).to_list(length=1)

    # Check Tasks
    active_task = await db.tasks.find_one({"assigned_to": user_id, "status": "pending"})

    # Check Projects
    active_project = await db.projects.find_one(
        {"_id": ObjectId(profile["current_project_id"])}) if profile and profile.get("current_project_id") else None

    # 2. LANGGRAPH LOGIC (Simplified for the endpoint)
    agent_response = ""

    if not user_goals or not history:
        # Scenario: First time or no goals defined
        agent_response = "Hi there! Welcome to the platform. To get started, what are your primary learning goals?"

    elif active_task:
        # Scenario: Task exists, ask for completion
        agent_response = f"I see you're working on '{active_task['title']}'. Have you completed this task yet?"

    elif not active_project:
        # Scenario: Goals exist but no project assigned
        # Logic to pick from pool
        project_pool = await db.projects.find({"status": "active"}).to_list(length=1)
        if project_pool:
            new_p = project_pool[0]
            await db.profiles.update_one(
                {"userId": user_id},
                {"$set": {"current_project_id": str(new_p["_id"])}},
                upsert=True
            )
            agent_response = f"Great goals! I've assigned you to the project: {new_p['name']}. Ready to dive in?"
        else:
            agent_response = "You're all set! I'm currently looking for a project that matches your goals."

    else:
        # General engagement
        agent_response = "Welcome back! How can I help you with your current project today?"

    # 3. STORAGE: Save both messages to History
    # Save User Message
    await db.chats.insert_one({
        "userId": user_id,
        "userType": "user",
        "message": user_message,
        "timestamp": datetime.now()
    })

    # Save Agent Response
    agent_chat_doc = {
        "userId": user_id,
        "userType": "agent",
        "message": agent_response,
        "timestamp": datetime.now()
    }
    result = await db.chats.insert_one(agent_chat_doc)

    return chat_helper(await db.chats.find_one({"_id": result.inserted_id}))



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)