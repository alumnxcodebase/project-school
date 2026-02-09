import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from contextlib import asynccontextmanager
from dotenv import load_dotenv

from routers import projects, chat, goals, tasks, assignedprojects, preferences, notices, quizzes, assessments
from agents.learning_agent import get_learning_agent

load_dotenv()
# Force reload


import asyncio

async def create_db_indexes(db):
    """Create database indexes in the background to avoid blocking startup."""
    print("🔧 [Background] Starting index creation...")
    try:
        # Chats index
        await db.chats.create_index([("userId", 1), ("timestamp", 1)])
        
        # Agents index
        await db.agents.create_index([("userId", 1)], unique=True)
        
        # Resources index
        await db.resources.create_index([("taskId", 1)])
        await db.resources.create_index([("projectId", 1)])
        await db.resources.create_index([("userId", 1)])
        await db.resources.create_index([("name", 1)])
        
        # Assignedprojects index
        await db.assignedprojects.create_index([("userId", 1)])
        await db.assignedprojects.create_index([("userId", 1), ("sequenceId", 1)])
        
        # Preferences index
        await db.preferences.create_index([("userId", 1)], unique=True)
        
        # Notices index
        await db.notices.create_index([("createdAt", -1)])
        
        print("✅ [Background] All indexes verified/created")
    except Exception as e:
        print(f"⚠️ [Background] Index creation notice: {str(e)}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # DB Setup
    client = AsyncIOMotorClient(os.getenv("MONGODB_URL"))
    db = client[os.getenv("DATABASE_NAME", "projects")]
    app.state.db = db

    # Initialize Agent
    app.state.agent = get_learning_agent(db)

    # Start index creation in the background
    asyncio.create_task(create_db_indexes(db))

    print("🚀 API and Agent Ready")
    yield
    client.close()


app = FastAPI(title="Project + Agentic AI API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://projectschool.alumnx.com",
        "https://dashboard.alumnx.com",
        "https://alumnx.com",
        "https://www.alumnx.com",
        "https://alumnx-project-school-ui.vercel.app" # Added just in case
    ],
    allow_origin_regex="https://.*alumnx\.com", # Even more permissive for subdomains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Include Routers
app.include_router(goals.router, prefix="/goals", tags=["Goals"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(tasks.router, prefix="/tasks", tags=["Tasks"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(assignedprojects.router, prefix="/assignedprojects", tags=["Assigned Projects"])
app.include_router(preferences.router, prefix="/preferences", tags=["Preferences"])
app.include_router(notices.router, prefix="/notices", tags=["Notice Board"])
app.include_router(quizzes.router, prefix="/quizzes", tags=["Quizzes"])
app.include_router(assessments.router, prefix="/assessments", tags=["Assessments"])


@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": "2026-01-12T12:00:00Z"}

if __name__ == "__main__":
    import uvicorn
    # Bind to 0.0.0.0 for easier production/deployment access
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
